"""导入 10 个新增景点（幂等）。封面优先用实景图，没有时退回带名称的占位图。"""
import pathlib
import sys
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from app.models import Attraction
from scripts.make_attraction_images import PLAN

IMAGES = ROOT / "app" / "static" / "images"


def cover_for(slug: str) -> str:
    """实景图已生成就用 <缩写>1.jpg，否则用占位 SVG。"""
    hit = PLAN.get(slug)
    abbr = hit[1] if hit else ""
    if abbr and (IMAGES / f"{abbr}1.jpg").exists():
        return f"/static/images/{abbr}1.jpg"
    return f"/static/images/placeholders/{slug}.svg"

SPOTS = [
    {
        "slug": "wanfenglin", "name": "万峰林", "category": "自然", "city": "黔西南", "region": "兴义",
        "summary": "中国最典型的喀斯特峰林之一，两万余座锥状山峰铺展在田园之间，八卦田与纳灰村构成经典画面。",
        "description": "万峰林位于兴义市郊，是典型的喀斯特峰丛地貌，两万余座锥峰与农田、村寨交织。景区分东峰林、西峰林，八卦田、纳灰村、万峰湖是主要看点，适合骑行与徒步。",
        "poetic": "万峰如林，铺向天边；田园如织，落在峰脚。晨雾起时，山是海，村是舟。",
        "price": "80", "open_time": "08:00-18:00", "visit_duration": 240, "best_months": "3,4,5,9,10",
        "address": "贵州省黔西南布依族苗族自治州兴义市万峰林街道",
        "transport": "兴义市区乘 19 路或旅游专线至万峰林景区。",
        "tips": "骑行西峰林绿道，傍晚光线最好。",
        "lng": 104.85, "lat": 25.02, "weather_code": "101260901", "tags": ["喀斯特", "田园", "骑行"],
    },
    {
        "slug": "pingba-cherry", "name": "贵安平坝樱花", "category": "季节", "city": "贵阳", "region": "贵安新区",
        "summary": "万亩樱花沿红枫湖畔铺开，三月花期如粉色云海，是国内规模最大的樱花基地之一。",
        "description": "平坝樱花园位于贵安新区红枫湖畔，占地逾万亩，早樱、晚樱次第开放。花期通常在三月，湖畔花海与茶园相间，适合半日到一日游览。",
        "poetic": "湖是镜，樱是云；风一过，粉色落满肩头。",
        "price": "0", "open_time": "08:00-18:00", "visit_duration": 180, "best_months": "3",
        "address": "贵州省贵阳市贵安新区平坝农场",
        "transport": "贵阳自驾约 1 小时；花期有专线巴士。",
        "tips": "花期短，出发前看官方花讯；周末早到。",
        "lng": 106.32, "lat": 26.36, "weather_code": "101260101", "tags": ["樱花", "湖景", "春季"], "seasonal": True,
    },
    {
        "slug": "huajiang-bridge", "name": "花江峡谷大桥", "category": "科技", "city": "安顺", "region": "关岭",
        "summary": "横跨花江大峡谷的世界级高桥，桥面距谷底近 800 米，是贵州“桥梁博物馆”的新地标。",
        "description": "花江峡谷大桥跨越北盘江花江大峡谷，主跨与桥高均居世界前列。观景平台可俯瞰峡谷深切、云雾穿桥的景观，是桥梁观光与工程研学目的地。",
        "poetic": "一桥飞架，云在脚下；峡谷千里，风从桥上来。",
        "price": "0", "open_time": "09:00-17:00", "visit_duration": 90, "best_months": "3,4,5,9,10,11",
        "address": "贵州省安顺市关岭布依族苗族自治县花江大峡谷",
        "transport": "关岭站或兴义方向自驾，导航“花江峡谷大桥观景台”。",
        "tips": "观景台风大，注意保暖；无人机需报备。",
        "lng": 105.55, "lat": 25.65, "weather_code": "101260301", "tags": ["大桥", "峡谷", "工程"],
    },
    {
        "slug": "zhaoxing-dong", "name": "肇兴侗寨", "category": "人文", "city": "黔东南", "region": "黎平",
        "summary": "全国最大的侗族村寨之一，五座鼓楼按“仁义礼智信”分布，侗族大歌与吊脚楼构成山地人文景观。",
        "description": "肇兴侗寨坐落于山谷之间，五座鼓楼、花桥、戏台与吊脚楼连成一片。这里是侗族大歌的重要传承地，可听歌、看织染、走堂安梯田。",
        "poetic": "鼓楼五座，歌声绕梁；梯田在山上，灯火在寨中。",
        "price": "80", "open_time": "全天开放（入园 08:00-22:00）", "visit_duration": 300, "best_months": "4,5,9,10",
        "address": "贵州省黔东南苗族侗族自治州黎平县肇兴镇",
        "transport": "贵广高铁从江站转车约 40 分钟。",
        "tips": "晚上有侗族大歌表演；住寨内客栈更方便。",
        "lng": 109.17, "lat": 25.90, "weather_code": "101260501", "tags": ["侗寨", "鼓楼", "大歌"],
    },
    {
        "slug": "zhenyuan", "name": "镇远古镇", "category": "人文", "city": "黔东南", "region": "镇远",
        "summary": "舞阳河呈“S”形穿城而过，青龙洞、古巷道与祝圣桥构成 2000 年历史的水上古城。",
        "description": "镇远古镇依舞阳河而建，北岸府城、南岸卫城，青龙洞古建筑群贴崖而建。夜晚灯火沿河铺开，古巷、码头、会馆保存完整。",
        "poetic": "一水分两城，灯火落河中；古巷深几许，钟声过桥东。",
        "price": "0", "open_time": "全天开放", "visit_duration": 240, "best_months": "4,5,9,10",
        "address": "贵州省黔东南苗族侗族自治州镇远县舞阳镇",
        "transport": "镇远站下车步行或打车 10 分钟。",
        "tips": "住河边客栈看夜景；青龙洞需另购票。",
        "lng": 108.43, "lat": 27.05, "weather_code": "101260501", "tags": ["古城", "舞阳河", "夜景"],
    },
    {
        "slug": "qingyan", "name": "青岩古镇", "category": "人文", "city": "贵阳", "region": "花溪",
        "summary": "明代军事屯堡演变而来的石头古镇，城墙、牌坊、寺庙与状元故居齐聚，距贵阳约 30 公里。",
        "description": "青岩古镇始建于明洪武年间，以石头城墙、明清古建和屯堡文化著称。古镇内有关帝庙、状元府、天主堂等，街巷以青石板铺就，适合半日游。",
        "poetic": "石墙围住旧时光，青石路通向牌坊；一盏玫瑰糖，甜了六百年。",
        "price": "10", "open_time": "08:30-17:30", "visit_duration": 180, "best_months": "3,4,5,9,10",
        "address": "贵州省贵阳市花溪区青岩镇",
        "transport": "贵阳公交 210/203 路直达。",
        "tips": "尝青岩猪脚、玫瑰糖；周末人多。",
        "lng": 106.68, "lat": 26.33, "weather_code": "101260101", "tags": ["古镇", "屯堡", "石头城"],
    },
    {
        "slug": "wumeng-grassland", "name": "乌蒙大草原", "category": "自然", "city": "六盘水", "region": "盘州",
        "summary": "西南地区海拔最高、面积最大的高山草甸之一，风车、云海、杜鹃与佛光构成高原景观。",
        "description": "乌蒙大草原位于盘州北部，平均海拔 2500 米，草甸起伏、风车成列。春夏杜鹃与野花盛开，秋冬云海频现，是避暑与露营目的地。",
        "poetic": "云在草上走，风在耳边停；高原的夏天，只有二十度。",
        "price": "50", "open_time": "08:00-18:00", "visit_duration": 240, "best_months": "5,6,7,8,9",
        "address": "贵州省六盘水市盘州市坪地乡",
        "transport": "盘州站转旅游专线或自驾约 1.5 小时。",
        "tips": "海拔高、昼夜温差大，带外套；自驾注意山路。",
        "lng": 104.55, "lat": 26.05, "weather_code": "101260801", "tags": ["草原", "风车", "避暑"],
    },
    {
        "slug": "baili-dujuan", "name": "毕节百里杜鹃", "category": "季节", "city": "毕节", "region": "百里杜鹃",
        "summary": "绵延百里的原生杜鹃林带，三月至四月马缨、露珠等品种次第开放，被誉为“地球彩带”。",
        "description": "百里杜鹃景区横跨普底、金坡等片区，原生杜鹃林带宽 1–3 公里、绵延 50 余公里。花期集中在三月至四月，彝族火把节与花海相映。",
        "poetic": "山是画布，花是颜料；百里杜鹃开，春天有了形状。",
        "price": "130", "open_time": "08:00-18:00", "visit_duration": 300, "best_months": "3,4",
        "address": "贵州省毕节市百里杜鹃管理区普底乡",
        "transport": "毕节站或大方站转景区专线。",
        "tips": "花期短，关注官方花讯；景区大，穿舒适鞋。",
        "lng": 105.95, "lat": 27.20, "weather_code": "101260701", "tags": ["杜鹃", "花海", "春季"], "seasonal": True,
    },
    {
        "slug": "xiaoqikong", "name": "荔波小七孔", "category": "自然", "city": "黔南", "region": "荔波",
        "summary": "响水河上的七孔古桥与叠瀑、翠谷、水上森林相连，是贵州最精致的喀斯特水景之一。",
        "description": "小七孔景区以响水河为主线，七孔古桥、68 级跌水瀑布、拉雅瀑布、水上森林、卧龙潭依次展开。水色随光线变化，徒步全程约 4–6 小时。",
        "poetic": "水从石上过，桥在绿中藏；一步一潭，一潭一色。",
        "price": "130", "open_time": "08:00-17:00", "visit_duration": 300, "best_months": "4,5,6,9,10",
        "address": "贵州省黔南布依族苗族自治州荔波县小七孔镇",
        "transport": "荔波站或荔波机场转景区巴士。",
        "tips": "从东门进西门出可少走回头路；雨季水大更壮观。",
        "lng": 107.73, "lat": 25.25, "weather_code": "101260401", "tags": ["喀斯特", "瀑布", "水景"],
    },
    {
        "slug": "zhijindong", "name": "织金洞", "category": "自然", "city": "毕节", "region": "织金",
        "summary": "中国规模最大、造型最丰富的喀斯特溶洞之一，洞内石笋、石幔、卷曲石密集，被誉为“溶洞之王”。",
        "description": "织金洞已开发洞段约 6.6 公里，最宽处 175 米，最高处 150 米。洞内“银雨树”“霸王盔”“卷曲石”等景观密集，灯光下层次分明。",
        "poetic": "地下有一座宫殿，石头在长，时间在滴；一万年，只长一寸。",
        "price": "120", "open_time": "08:30-17:00", "visit_duration": 180, "best_months": "3,4,5,9,10",
        "address": "贵州省毕节市织金县官寨乡",
        "transport": "织金站转景区专线约 40 分钟。",
        "tips": "洞内湿滑、恒温 16℃ 左右，带薄外套。",
        "lng": 105.75, "lat": 26.75, "weather_code": "101260701", "tags": ["溶洞", "地质", "喀斯特"],
    },
]


def main():
    app = create_app()
    with app.app_context():
        added = updated = 0
        for data in SPOTS:
            attraction = Attraction.query.filter_by(slug=data["slug"]).first()
            if attraction is None:
                attraction = Attraction(slug=data["slug"], rating=Decimal("4.5"), rating_count=0)
                db.session.add(attraction)
                added += 1
            else:
                updated += 1
            for key, value in {
                "name": data["name"], "summary": data["summary"], "description": data["description"],
                "poetic_description": data["poetic"], "address": data["address"],
                "transport": data["transport"], "tips": data["tips"], "city": data["city"],
                "region": data["region"], "province": "贵州省",
                "longitude": Decimal(str(data["lng"])), "latitude": Decimal(str(data["lat"])),
                "cover_image": cover_for(data["slug"]),
                "category": data["category"], "tags": data["tags"], "price": Decimal(data["price"]),
                "ticket_note": "", "open_time": data["open_time"], "best_months": data["best_months"],
                "seasonal": data.get("seasonal", False), "visit_duration": data["visit_duration"],
                "weather_code": data["weather_code"], "status": "published",
            }.items():
                setattr(attraction, key, value)
            print("upsert", data["slug"])
        db.session.commit()
        print("added", added, "updated", updated, "total", Attraction.query.count())


if __name__ == "__main__":
    main()
