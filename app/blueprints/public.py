import math

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user
from sqlalchemy import or_

from ..extensions import db
from ..i18n import current_lang
from ..models import Attraction
from ..services.history import daily_recommendation, record_view
from ..services.traffic import record_traffic

bp = Blueprint("public", __name__)

CATEGORIES = [
    {"key": "自然", "label": "自然山水", "en": "NATURE", "image": "/static/images/HGSPB1.jpg"},
    {"key": "人文", "label": "人文村寨", "en": "CULTURE", "image": "/static/images/XJQHMZ1.jpg"},
    {"key": "红色", "label": "红色记忆", "en": "RED MEMORY", "image": "/static/images/LSG1.jpg"},
    {"key": "科技", "label": "科技奇观", "en": "SCIENCE", "image": "/static/images/ZGTY1.jpg"},
    {"key": "季节", "label": "艳季花海", "en": "SEASONAL", "image": "/static/images/GAPBYH1.jpg"},
]

SEASONAL_PICKS = [
    {"name": "贵安平坝樱花", "months": "3 月", "slug": "pingba-cherry"},
    {"name": "毕节百里杜鹃", "months": "3–4 月", "slug": "baili-dujuan"},
]

# 首屏轮播：只用实景照片（品牌海报自带文字，叠 UI 会压字，改作独立物料）
HERO_SLIDES = [
    {"image": "/static/images/HGSPB1.jpg", "thumb": "/static/images/HGSPB1.jpg", "label": "黄果树瀑布 · 夜"},
    {"image": "/static/images/XJQHMZ1.jpg", "thumb": "/static/images/XJQHMZ1.jpg", "label": "西江千户苗寨 · 夜"},
    {"image": "/static/images/FJS2.jpg", "thumb": "/static/images/FJS2.jpg", "label": "梵净山"},
    {"image": "/static/images/ZGTY1.jpg", "thumb": "/static/images/ZGTY1.jpg", "label": "中国天眼"},
    {"image": "/static/images/ZYHY2.jpg", "thumb": "/static/images/ZYHY2.jpg", "label": "遵义会议会址"},
    {"image": "/static/images/LPHY1.jpg", "thumb": "/static/images/LPHY1.jpg", "label": "黎平古城"},
    {"image": "/static/images/LSG1.jpg", "thumb": "/static/images/LSG1.jpg", "label": "娄山关"},
    # 新十大风景图 · 横屏（海报未做，先入连播）
    {"image": "/static/images/hero/new/WFL2.jpg", "thumb": "/static/images/hero/new/WFL2.jpg", "label": "万峰林 · 峰林"},
    {"image": "/static/images/hero/new/WFL5.jpg", "thumb": "/static/images/hero/new/WFL5.jpg", "label": "万峰林 · 田园"},
    {"image": "/static/images/hero/new/WJZ2.jpg", "thumb": "/static/images/hero/new/WJZ2.jpg", "label": "乌江寨 · 吊脚楼"},
    {"image": "/static/images/hero/new/WNCH1.jpg", "thumb": "/static/images/hero/new/WNCH1.jpg", "label": "威宁草海 · 湿地"},
    {"image": "/static/images/hero/new/WNCH2.jpg", "thumb": "/static/images/hero/new/WNCH2.jpg", "label": "威宁草海 · 候鸟"},
    {"image": "/static/images/hero/new/WNCH3.jpg", "thumb": "/static/images/hero/new/WNCH3.jpg", "label": "威宁草海 · 湖面"},
    {"image": "/static/images/hero/new/YLG1.jpg", "thumb": "/static/images/hero/new/YLG1.jpg", "label": "花溪夜郎谷 · 石堡"},
    {"image": "/static/images/hero/new/JCP1.jpg", "thumb": "/static/images/hero/new/JCP1.jpg", "label": "韭菜坪 · 花海"},
    {"image": "/static/images/hero/new/JCP3.jpg", "thumb": "/static/images/hero/new/JCP3.jpg", "label": "韭菜坪 · 山脊"},
    {"image": "/static/images/hero/new/MLHXG1.jpg", "thumb": "/static/images/hero/new/MLHXG1.jpg", "label": "马岭河峡谷 · 瀑布"},
    {"image": "/static/images/hero/new/MLHXG3.jpg", "thumb": "/static/images/hero/new/MLHXG3.jpg", "label": "马岭河峡谷 · 河谷"},
    {"image": "/static/images/hero/new/HJXGDQ1.jpg", "thumb": "/static/images/hero/new/HJXGDQ1.jpg", "label": "花江峡谷大桥 · 大桥"},
    {"image": "/static/images/hero/new/HJXGDQ3.jpg", "thumb": "/static/images/hero/new/HJXGDQ3.jpg", "label": "花江峡谷大桥 · 峡谷"},
    {"image": "/static/images/hero/new/HJXGDQ6.jpg", "thumb": "/static/images/hero/new/HJXGDQ6.jpg", "label": "花江峡谷大桥 · 远眺"},
    {"image": "/static/images/hero/new/LBXQK1.jpg", "thumb": "/static/images/hero/new/LBXQK1.jpg", "label": "荔波小七孔 · 碧水"},
    {"image": "/static/images/hero/new/LBXQK3.jpg", "thumb": "/static/images/hero/new/LBXQK3.jpg", "label": "荔波小七孔 · 瀑布"},
    {"image": "/static/images/hero/new/LBXQK5.jpg", "thumb": "/static/images/hero/new/LBXQK5.jpg", "label": "荔波小七孔 · 林间"},
    {"image": "/static/images/hero/new/LBXQK6.jpg", "thumb": "/static/images/hero/new/LBXQK6.jpg", "label": "荔波小七孔 · 碧潭"},
    {"image": "/static/images/hero/new/GAPBYH5.jpg", "thumb": "/static/images/hero/new/GAPBYH5.jpg", "label": "贵安平坝樱花 · 花海"},
    {"image": "/static/images/hero/new/ZYGZ1.jpg", "thumb": "/static/images/hero/new/ZYGZ1.jpg", "label": "镇远古镇 · 㵲阳河"},
    {"image": "/static/images/hero/new/ZYGZ6.jpg", "thumb": "/static/images/hero/new/ZYGZ6.jpg", "label": "镇远古镇 · 夜色"},
    {"image": "/static/images/hero/new/QYGZ2.jpg", "thumb": "/static/images/hero/new/QYGZ2.jpg", "label": "青岩古镇 · 石巷"},
]


@bp.route("/")
def home():
    featured = (
        Attraction.query.filter_by(status="published")
        .order_by(Attraction.rating.desc(), Attraction.id.asc())
        .limit(8)
        .all()
    )
    # 当季卡片：带上数据库里的实景图与票价，避免首页还写着“图片待补”
    slugs = [item["slug"] for item in SEASONAL_PICKS]
    by_slug = {
        a.slug: a
        for a in Attraction.query.filter(Attraction.slug.in_(slugs)).all()
    }
    seasonal_picks = [
        {**item, "attraction": by_slug[item["slug"]]}
        for item in SEASONAL_PICKS
        if item["slug"] in by_slug
    ]
    slides = [s for s in HERO_SLIDES if not (current_lang() == "en" and s.get("poster"))]
    return render_template(
        "pages/home.html",
        featured=featured,
        categories=CATEGORIES,
        seasonal_picks=seasonal_picks,
        hero_slides=slides,
        daily=daily_recommendation(current_user),
    )


@bp.route("/attractions")
def attractions():
    category = request.args.get("category", "").strip()
    keyword = request.args.get("q", "").strip()
    page = max(int(request.args.get("page", 1) or 1), 1)
    per_page = 12

    query = Attraction.query.filter_by(status="published")
    if category:
        # 兼容历史数据：库里是「红色文化」，导航链接是「红色」
        query = query.filter(Attraction.category.startswith(category, autoescape=True))
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            or_(
                Attraction.name.like(like),
                Attraction.summary.like(like),
                Attraction.description.like(like),
            )
        )
    total = query.count()
    items = (
        query.order_by(Attraction.rating.desc(), Attraction.id.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    pages = max(math.ceil(total / per_page), 1)
    return render_template(
        "pages/attractions.html",
        items=items,
        categories=CATEGORIES,
        current_category=category,
        keyword=keyword,
        page=page,
        pages=pages,
        total=total,
    )


@bp.route("/attractions/<slug>")
def attraction_detail(slug):
    attraction = Attraction.query.filter_by(slug=slug, status="published").first_or_404()
    record_traffic(attraction.id)
    if current_user.is_authenticated:
        record_view(current_user.id, attraction.id)
        db.session.refresh(attraction)
    related = (
        Attraction.query.filter(
            Attraction.status == "published",
            Attraction.category == attraction.category,
            Attraction.id != attraction.id,
        )
        .limit(3)
        .all()
    )
    return render_template("pages/attraction_detail.html", attraction=attraction, related=related)


@bp.route("/attractions/<slug>/map")
def attraction_map(slug):
    """详情页地图卡的「大屏版」：整屏高德地图，可缩放/拖动/切换卫星图。"""
    attraction = Attraction.query.filter_by(slug=slug, status="published").first_or_404()
    return render_template("pages/attraction_map.html", attraction=attraction)


@bp.route("/healthz")
def healthz():
    return jsonify({"ok": True, "app": "guizhou-tourism"})
