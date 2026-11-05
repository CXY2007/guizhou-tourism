"""写入 8 个已上线景点的英文翻译（幂等 upsert）。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import Attraction, AttractionTranslation

CONTENT = {
    "huangguoshu": {
        "name": "Huangguoshu Waterfall",
        "summary": "Asia's largest karst waterfall, on the upper Baishui River. The scenic area includes Doupotang, Tianxingqiao and the Main Waterfall; the main fall drops 77.8 metres.",
        "description": "Huangguoshu Waterfall is Asia's largest karst waterfall, located on the upper reaches of the Baishui River. The scenic area has three sections—Doupotang, Tianxingqiao and the Main Waterfall—with the main fall dropping 77.8 metres. It is Guizhou's signature natural 5A scenic area.",
        "poetic": "Like the Milky Way pouring down, Huangguoshu is a thundering, majestic sight. By the Baishui River, Doupotang lies quiet, Tianxingqiao runs deep, and the main fall plunges 77.8 metres, awe-inspiring. This is a poem of karst, a crescendo of nature—a 5A landscape of endless views.",
        "address": "Huangguoshu Town, Guanling Buyei and Miao Autonomous County, Anshun, Guizhou",
        "open_time": "07:30–18:00",
        "ticket_note": "",
    },
    "xijiang-miao": {
        "name": "Xijiang Qianhu Miao Village",
        "summary": "China's largest surviving Miao village, with over a thousand wooden stilt houses built into the hillside. At dusk the lights form a river of stars; silverwork, long-table banquets and lusheng performances are highlights.",
        "description": "Xijiang Qianhu Miao Village is the largest surviving Miao settlement in China, with more than a thousand wooden stilt houses rising along the slopes. At dusk, countless lights form a river of stars. Visitors can experience Miao silverwork, long-table banquets, lusheng music and dance—a benchmark for Qiandongnan's blend of landscape and ethnic culture.",
        "poetic": "Ringed by mountains, the stilt houses cling to the cliffs, and morning mist makes the village feel like a dream. As dusk falls, ten thousand lights come on one by one, like the Milky Way descending to earth. Silver ornaments chime, long-table feasts are laid, lusheng melodies drift—Miao culture unfolds across the hills.",
        "address": "Xijiang Town, Leishan County, Qiandongnan Miao and Dong Autonomous Prefecture, Guizhou",
        "open_time": "Open all day (ticket check 08:00–22:00)",
        "ticket_note": "",
    },
    "fanjingshan": {
        "name": "Mount Fanjing",
        "summary": "A UNESCO World Natural Heritage site and national nature reserve, the highest peak of the Wuling Mountains. Landmarks include the Red Cloud Golden Summit and Mushroom Rock; it is also a sacred Buddhist mountain.",
        "description": "Mount Fanjing is a UNESCO World Natural Heritage site and national nature reserve, and the main peak of the Wuling Mountains. Its iconic Red Cloud Golden Summit and Mushroom Rock draw pilgrims and hikers, while the reserve protects the rare Guizhou golden monkey. It is also a renowned Buddhist mountain and a national 5A scenic area.",
        "poetic": "Clouds drift around Mount Fanjing, peaks folded in green. The Red Cloud Golden Summit stands proud; Mushroom Rock seems carved by immortals. This is the secret home of the Guizhou golden monkey and a Buddhist sanctuary. From the summit, mountains stretch to the horizon and the heart drifts with the clouds.",
        "address": "Taiping Town, Jiangkou County, Tongren, Guizhou",
        "open_time": "07:00–18:00 (cable car until 17:00)",
        "ticket_note": "",
    },
    "fast-tianyan": {
        "name": "FAST (China Sky Eye)",
        "summary": "The world's largest single-dish radio telescope, a 500-metre spherical reflector and China's leading astronomical landmark, with a science centre and viewing platform.",
        "description": "FAST is the world's largest single-dish radio telescope, a 500-metre spherical reflector and one of China's leading astronomical landmarks. A science exhibition centre and viewing platform make it a dedicated destination for astronomy education and research visits.",
        "poetic": "FAST rests among the mountains like a giant eye gazing at the sky. Its 500-metre silver bowl brims with starlight, listening to whispers from the deep universe. Here technology and nature meet, at the frontier of human curiosity.",
        "address": "Dawodang, Kedu Town, Pingtang County, Qiannan Buyei and Miao Autonomous Prefecture, Guizhou",
        "open_time": "08:30–17:30 (closed Mondays)",
        "ticket_note": "",
    },
    "zunyi-conference": {
        "name": "Zunyi Conference Site",
        "summary": "The site of the 1935 Zunyi Conference, a turning point of the Long March, and a national key cultural relic and patriotic education base with a Party history exhibition.",
        "description": "The Zunyi Conference Site is where the pivotal 1935 conference took place, a turning point for the Red Army during the Long March. The building is a national key cultural relic and a national patriotic education base, with a dedicated exhibition on Party history.",
        "poetic": "Standing quietly by the Wu River, the Zunyi Conference Site is like a lamp that never goes out. In 1935 history turned here, and the spark of revolution lit hope. Grey bricks and tiles remember the wisdom and courage of those who came before.",
        "address": "96 Ziyin Road, Honghuagang District, Zunyi, Guizhou",
        "open_time": "09:00–17:00 (closed Mondays; last entry 16:30)",
        "ticket_note": "",
    },
    "loushanguan": {
        "name": "Loushan Pass",
        "summary": "A steep pass in northern Guizhou, site of the Red Army's Loushan Pass victory and the inspiration for Mao Zedong's poem \"Recalling Qin'e · Loushan Pass\", combining revolutionary sites with mountain scenery.",
        "description": "Loushan Pass is a steep strategic pass in northern Guizhou, where the Red Army won a key victory during the Long March. It inspired Mao Zedong's poem \"Recalling Qin'e · Loushan Pass\" and combines revolutionary battlefield sites with rugged mountain scenery.",
        "poetic": "Loushan Pass is a poem of steepness. Once a battlefield, it is now a landscape where nature and history meet. Between the peaks, the smoke of war has gone, leaving only pines and cypresses singing in the wind. \"Green mountains like a sea, the setting sun like blood\"—the vastness of the land and the spirit of heroes.",
        "address": "Loushanguan Town, Huichuan District, Zunyi, Guizhou",
        "open_time": "Mountain open all day; memorial hall 09:00–17:00",
        "ticket_note": "",
    },
    "xifeng-camp": {
        "name": "Xifeng Concentration Camp Site",
        "summary": "A secret prison established by the Kuomintang during the War of Resistance, where many patriots were held. Now a national patriotic education and Red tourism base with prison cells and a memorial hall.",
        "description": "The Xifeng Concentration Camp Site was a secret prison set up by the Kuomintang during the War of Resistance Against Japan, where many patriotic revolutionaries were detained and struggled. It is now a nationally known base for Red tourism and patriotic education, with historic cells and a memorial hall.",
        "poetic": "At Xifeng, iron bars once held a history of blood, and loyal souls forged a monument. The cells were dark, but conviction stood like iron. In the memorial hall, names endure and inspire those who come after.",
        "address": "Maodong Village, Yongjing Town, Xifeng County, Guiyang, Guizhou",
        "open_time": "09:00–17:00 (closed Mondays)",
        "ticket_note": "",
    },
    "liping-conference": {
        "name": "Liping Conference Site",
        "summary": "The site of the 1934 Liping Politburo meeting during the Long March, the first key strategic meeting after the Red Army entered Guizhou, which set the course for advancing into the province's interior. The exhibition is free.",
        "description": "The Liping Conference Site is where the Red Army's Politburo met in 1934 during the Long March—the first key strategic meeting after entering Guizhou. It confirmed the plan to advance into the province's interior. The dedicated Red history exhibition is free to visit.",
        "poetic": "Set among the green hills and waters of Qiandongnan, the Liping Conference Site witnessed a crucial turn in the Long March. In 1934 a new strategic direction was kindled here, pointing the Red Army toward victory. Grey-brick houses carry the weight of Red memory; the displays tell of an enduring revolutionary spirit.",
        "address": "Qiaojie, Defeng Subdistrict, Liping County, Qiandongnan Miao and Dong Autonomous Prefecture, Guizhou",
        "open_time": "08:30–17:00 (closed Mondays)",
        "ticket_note": "",
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
