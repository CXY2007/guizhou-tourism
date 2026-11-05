"""给 18 个景点灌真实感的评论（每条都绑定具体景点的事实/体验细节）。

    python scripts/seed_comments.py            # 幂等：同内容已存在则跳过
    python scripts/seed_comments.py --reset    # 先删掉本脚本灌过的评论

内容来源：公开攻略与游客反馈（票价、观光车、排队/预约规则、机位、避坑），
并结合站内景点数据（票价、开放时间、建议时长），避免和小红书兜底笔记重复。
"""
from __future__ import annotations

import pathlib
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Attraction, Comment, User  # noqa: E402

# slug -> [(评论内容, 几天前)]
COMMENTS: dict[str, list[tuple[str, int]]] = {
    "huangguoshu": [
        ("陡坡塘—大瀑布—天星桥这个顺序最省力，天星桥要走两个多小时，鞋一定穿舒服的。", 3),
        ("水帘洞一定会湿身，雨衣景区里卖 5 块、门口 2 块，建议门口先买。", 9),
        ("下午三点之后大瀑布那边逆光少，水雾里能看到彩虹，照片比上午好看。", 21),
    ],
    "xijiang-miao": [
        ("观景台最好早上七点半前去，云海概率高，人也少一半。", 5),
        ("晚上八点全寨灯亮，从半山腰往下拍千户灯火，像动画里的场景。", 12),
        ("长桌宴气氛足但味道一般，酸汤鱼还是寨子里的小店更靠谱。", 26),
    ],
    "fanjingshan": [
        ("门票、观光车、索道都要在公众号上实名预约，现场真的没有售票窗口。", 4),
        ("红云金顶不能提前约，到普渡广场现场扫码叫号，过号作废；赶第一波入园基本不用等。", 11),
        ("索道斜长三公里多、高差一千多米，二十分钟上去，耳朵会堵，咽口水就好。", 30),
    ],
    "fast-tianyan": [
        ("全程不能带手机相机，寄存柜要排队，建议提前二十分钟到。", 6),
        ("摆渡车班次固定，观景台只能远看，望远镜里能看到天线面板的格子。", 18),
    ],
    "zunyi-conference": [
        ("免费但必须预约，周一闭馆，16:30 就不让进了，别掐点到。", 7),
        ("跟着讲解走一圈四十分钟，比自己看收获大很多，馆内不能拍照。", 15),
    ],
    "loushanguan": [
        ("从遵义市区自驾四十分钟，山路弯多，开慢一点。", 10),
        ("观景台风大，帽子会被吹跑；秋天去层林尽染最出片。", 24),
    ],
    "xifeng-camp": [
        ("讲解很震撼，建议留两小时，洞里阴凉记得带件外套。", 8),
        ("从贵阳过去一小时，周边没什么吃的，回市区解决。", 20),
    ],
    "liping-conference": [
        ("会址和翘街连在一起逛，傍晚灯笼亮起来，石板路很好看。", 13),
        ("翘街的油茶一定要试，本地人早上都在喝。", 28),
    ],
    "wanfenglin": [
        ("西峰林租电动车三十块一天，沿绿道慢慢骑，比坐观光车自由。", 5),
        ("八卦田日出六点半前到，纳灰村吃饭比景区里便宜一半。", 17),
    ],
    "pingba-cherry": [
        ("三月中旬花开得最好，周末非常堵，六点半出发才不排队。", 2),
        ("红枫湖边逆光拍樱花最好看，无人机限飞的地方看提示牌。", 19),
    ],
    "huajiang-bridge": [
        ("观景台风特别大，帽子和围巾一定拿稳，会被吹飞。", 6),
        ("上午顺光拍桥更清楚，下午过去基本都是背光。", 22),
    ],
    "zhaoxing-dong": [
        ("晚上八点侗族大歌表演，鼓楼下坐满人，早点去占前排。", 9),
        ("堂安梯田从寨子后面开车二十分钟，徒步下来一个半小时，日落时有雾。", 23),
    ],
    "zhenyuan": [
        ("祝圣桥晚上七点亮灯，河对岸拍最好看。", 4),
        ("青龙洞门票五十，不进去在外面看那排吊脚楼建筑也够。", 16),
    ],
    "qingyan": [
        ("下午四点以后游客少，光线也柔和，石巷里拍人像很出片。", 7),
        ("状元蹄和玫瑰冰浆必吃，出南门那几家比古镇里便宜一半。", 25),
    ],
    "wumeng-grassland": [
        ("盘州上山一个小时，山顶比山下低七八度，外套一定要带。", 11),
        ("风机底下逆光拍剪影很出片，佛光得雨后天晴才碰得到。", 27),
    ],
    "baili-dujuan": [
        ("三月下旬到四月中旬最好，景区车一定要坐，走路根本走不完。", 3),
        ("普底和金坡两个片区风格不一样，时间够可以都去。", 14),
    ],
    "xiaoqikong": [
        ("一定西门进东门出，全程下坡；东门进全是上坡，走完腿废。", 2),
        ("水上森林会湿鞋，穿防滑凉鞋或溯溪鞋，千万别穿白鞋。", 8),
        ("观光车必买，古桥清晨和傍晚拍倒影最好看，浅色衣服出片。", 21),
    ],
    "zhijindong": [
        ("洞内常年十六度，夏天进去像开了空调，带件薄外套。", 5),
        ("全程两小时跟着讲解走，自己逛容易迷路，也看不懂钟乳石的讲究。", 16),
    ],
}


def main() -> None:
    reset = "--reset" in sys.argv
    rng = random.Random(20261103)
    app = create_app()

    with app.app_context():
        attractions = {a.slug: a for a in Attraction.query.all()}
        users = User.query.filter(User.status == "active").order_by(User.id).all()
        if not users:
            raise SystemExit("没有可用用户，先跑 seed_ratings.py")
        # 尽量不用 admin 账号发评论
        posters = [u for u in users if u.role != "admin"] or users

        if reset:
            removed = Comment.query.filter(Comment.image_url.is_(None)).delete(synchronize_session=False)
            db.session.commit()
            print("已清空纯文字评论:", removed)

        now = datetime.utcnow()
        created = skipped = 0
        for slug, items in COMMENTS.items():
            attraction = attractions.get(slug)
            if attraction is None:
                print("  跳过（景点不存在）:", slug)
                continue
            for content, days_ago in items:
                exists = Comment.query.filter_by(attraction_id=attraction.id, content=content).first()
                if exists:
                    skipped += 1
                    continue
                db.session.add(Comment(
                    user_id=rng.choice(posters).id,
                    attraction_id=attraction.id,
                    content=content,
                    status="approved",
                    created_at=now - timedelta(days=days_ago, hours=rng.randint(0, 8)),
                ))
                created += 1
        db.session.commit()

        total = Comment.query.filter_by(status="approved").count()
        print(f"新增 {created} 条，跳过 {skipped} 条；当前已通过评论共 {total} 条")
        for slug in ("huangguoshu", "fanjingshan", "xiaoqikong"):
            attraction = attractions[slug]
            count = Comment.query.filter_by(attraction_id=attraction.id, status="approved").count()
            print(f"  {attraction.name}: {count} 条")


if __name__ == "__main__":
    main()
