"""补充 10 个景点的英文翻译（幂等 upsert）。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import Attraction, AttractionTranslation

CONTENT = {
    "wanfenglin": {
        'name': 'Wanfenglin',
        'summary': "One of China's most typical karst peak forests: over 20,000 cone-shaped peaks rise among farmland, with the Bagua fields and Nahui village forming the classic view.",
        'description': 'Wanfenglin lies on the edge of Xingyi, a classic karst peak-cluster landscape where more than 20,000 cone peaks interweave with fields and villages. The scenic area is split into East and West forests; the Bagua fields, Nahui village and Wanfeng Lake are the highlights, best explored by bike or on foot.',
        'poetic': 'Ten thousand peaks like a forest to the horizon; fields like brocade at their feet. When morning mist rises, the mountains become a sea and the villages become boats.',
        'address': 'Wanfenglin Subdistrict, Xingyi, Qianxinan, Guizhou',
        'transport': 'Take bus 19 or the tourist shuttle from Xingyi city center to Wanfenglin.',
        'tips': 'Ride the West Forest greenway; the light is best in the late afternoon.',
        'open_time': '08:00-18:00',
    },
    "pingba-cherry": {
        'name': "Pingba Cherry Blossom (Gui'an)",
        'summary': "Tens of thousands of cherry trees spread along the shore of Hongfeng Lake; in March the bloom becomes a pink sea of clouds, one of China's largest cherry bases.",
        'description': "Pingba Cherry Garden sits on the shore of Hongfeng Lake in Gui'an New Area and covers more than 10,000 mu, with early and late varieties blooming in succession. The season is usually March; flower fields alternate with tea gardens, making it a half-day to one-day trip.",
        'poetic': 'The lake is a mirror, the blossoms are clouds; when the wind passes, pink falls on your shoulders.',
        'address': "Pingba Farm, Gui'an New Area, Guiyang, Guizhou",
        'transport': 'About 1 hour by car from Guiyang; shuttle buses run during the blossom season.',
        'tips': 'The season is short: check the official bloom report before you go and arrive early on weekends.',
        'open_time': '08:00-18:00',
    },
    "huajiang-bridge": {
        'name': 'Huajiang Canyon Bridge',
        'summary': "A world-class high bridge spanning the Huajiang Grand Canyon, its deck nearly 800 m above the valley floor, a new landmark of Guizhou's museum of bridges.",
        'description': "The Huajiang Canyon Bridge crosses the Huajiang Grand Canyon of the Beipan River, with one of the world's longest main spans and highest decks. From the viewing platform you can look down into the deep gorge and watch clouds drift through the bridge, a destination for bridge sightseeing and engineering study tours.",
        'poetic': 'One bridge flies across, clouds beneath your feet; a canyon a thousand li wide, wind rising from the bridge.',
        'address': 'Huajiang Grand Canyon, Guanling, Anshun, Guizhou',
        'transport': 'Drive from Guanling Station or from Xingyi; navigate to the Huajiang Canyon Bridge viewing platform.',
        'tips': 'It is windy on the platform, so dress warmly; drones must be registered.',
        'open_time': '09:00-17:00',
    },
    "zhaoxing-dong": {
        'name': 'Zhaoxing Dong Village',
        'summary': "One of China's largest Dong villages: five drum towers named for the virtues, Dong grand song and stilt houses shaping a mountain culture landscape.",
        'description': "Zhaoxing Dong Village sits in a valley, where five drum towers, flower bridges, opera stages and stilt houses form a continuous whole. It is an important home of Dong grand song: listen to the singing, watch weaving and dyeing, and walk the terraces of Tang'an.",
        'poetic': 'Five drum towers, song lingering in the rafters; terraces on the hills, lights in the village.',
        'address': 'Zhaoxing Town, Liping, Qiandongnan, Guizhou',
        'transport': 'About 40 minutes by shuttle from Congjiang Station on the Guiyang-Guangzhou high-speed line.',
        'tips': 'Dong grand song performances are held in the evening; staying in a village guesthouse is convenient.',
        'open_time': 'Open all day (entry 08:00-22:00)',
    },
    "zhenyuan": {
        'name': 'Zhenyuan Ancient Town',
        'summary': 'The Wuyang River runs through in an S-shape; Qinglong Cave, old lanes and Zhusheng Bridge form a water town 2,000 years old.',
        'description': 'Zhenyuan was built along the Wuyang River: the prefectural city on the north bank, the garrison city on the south, and the Qinglong Cave complex clinging to the cliff. At night lights spread along the river; old lanes, wharves and guild halls survive intact.',
        'poetic': 'One river divides two cities, lights fall into the water; how deep the old lanes, a bell sounds east of the bridge.',
        'address': 'Wuyang Town, Zhenyuan, Qiandongnan, Guizhou',
        'transport': '10 minutes on foot or by taxi from Zhenyuan Station.',
        'tips': 'Stay in a riverside guesthouse for the night view; Qinglong Cave needs a separate ticket.',
        'open_time': 'Open all day',
    },
    "qingyan": {
        'name': 'Qingyan Ancient Town',
        'summary': 'A stone town grown from a Ming military fort: walls, archways, temples and the Zhuangyuan residence cluster together, about 30 km from Guiyang.',
        'description': 'Founded in the Hongwu era of the Ming, Qingyan is known for its stone walls, Ming-Qing buildings and fort culture. Inside are the Guandi Temple, the Zhuangyuan Mansion and a Catholic church; streets are paved with bluestone, a good half-day trip.',
        'poetic': 'Stone walls hold old times, bluestone roads lead to the archway; a piece of rose candy, sweet for six hundred years.',
        'address': 'Qingyan Town, Huaxi, Guiyang, Guizhou',
        'transport': 'Bus 210/203 from Guiyang goes direct.',
        'tips': 'Try Qingyan pig trotters and rose candy; weekends are crowded.',
        'open_time': '08:30-17:30',
    },
    "wumeng-grassland": {
        'name': 'Wumeng Grassland',
        'summary': "One of the highest and largest alpine meadows in southwest China; wind turbines, sea of clouds, azaleas and the Buddha's halo make up the plateau scenery.",
        'description': 'Wumeng Grassland lies north of Panzhou at an average altitude of 2,500 m, with rolling meadows and rows of wind turbines. Azaleas and wildflowers bloom in spring and summer, sea of clouds appears often in autumn and winter, a destination for escaping the heat and camping.',
        'poetic': 'Clouds walk on the grass, wind stops at your ear; summer on the plateau is only twenty degrees.',
        'address': 'Pingdi Township, Panzhou, Liupanshui, Guizhou',
        'transport': 'About 1.5 hours by shuttle or car from Panzhou Station.',
        'tips': 'High altitude and a big day-night temperature gap: bring a jacket; take care on mountain roads.',
        'open_time': '08:00-18:00',
    },
    "baili-dujuan": {
        'name': 'Baili Azalea (Bijie)',
        'summary': 'A primeval azalea forest belt stretching a hundred li; from March to April varieties such as horse-tassel and dew-pearl bloom in turn, praised as the color ribbon of the earth.',
        'description': 'The Baili Azalea scenic area spans the Pudi and Jinpo sections, with a primeval azalea belt 1-3 km wide and over 50 km long. The bloom peaks from March to April, when the Yi torch festival meets the flower sea.',
        'poetic': 'The mountain is a canvas, flowers are paint; when a hundred li of azaleas open, spring takes shape.',
        'address': 'Pudi Township, Baili Azalea Management Area, Bijie, Guizhou',
        'transport': 'Take the scenic-area shuttle from Bijie or Dafang Station.',
        'tips': 'The season is short: follow the official bloom report; the area is large, so wear comfortable shoes.',
        'open_time': '08:00-18:00',
    },
    "xiaoqikong": {
        'name': 'Libo Xiaoqikong',
        'summary': "The seven-arch ancient bridge over the Xiangshui River links cascades, emerald valleys and a water forest, one of Guizhou's finest karst water scenes.",
        'description': 'Xiaoqikong follows the Xiangshui River: the seven-arch bridge, the 68-step waterfall, Laya Falls, the water forest and Wolong Pool unfold in turn. The water changes color with the light; the full walk takes about 4-6 hours.',
        'poetic': 'Water passes over stone, the bridge hides in green; a pool at every step, a color in every pool.',
        'address': 'Xiaoqikong Town, Libo, Qiannan, Guizhou',
        'transport': 'Take the scenic-area bus from Libo Station or Libo Airport.',
        'tips': 'Enter at the East Gate and exit at the West Gate to avoid backtracking; the falls are grander in the rainy season.',
        'open_time': '08:00-17:00',
    },
    "zhijindong": {
        'name': 'Zhijin Cave',
        'summary': "One of China's largest and most varied karst caves: stalagmites, stone curtains and helictites crowd the chambers, known as the king of caves.",
        'description': "About 6.6 km of Zhijin Cave is open, up to 175 m wide and 150 m high. Formations such as the Silver Rain Tree, the Overlord's Helmet and helictites are densely packed and layered under the lighting.",
        'poetic': 'A palace underground, where stone grows and time drips; ten thousand years, one inch.',
        'address': 'Guanzhai Township, Zhijin, Bijie, Guizhou',
        'transport': 'About 40 minutes by scenic-area shuttle from Zhijin Station.',
        'tips': 'The cave is wet and slippery, with a constant temperature around 16 degrees C; bring a light jacket.',
        'open_time': '08:30-17:00',
    },
}


def main():
    app = create_app()
    with app.app_context():
        for slug, data in CONTENT.items():
            attraction = Attraction.query.filter_by(slug=slug).first()
            if attraction is None:
                print("missing attraction", slug)
                continue
            translation = AttractionTranslation.query.filter_by(attraction_id=attraction.id, lang="en").first()
            if translation is None:
                translation = AttractionTranslation(attraction_id=attraction.id, lang="en")
                db.session.add(translation)
            for key, value in data.items():
                setattr(translation, key, value)
            print("ok", slug)
        db.session.commit()


if __name__ == "__main__":
    main()
