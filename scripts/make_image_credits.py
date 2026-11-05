"""由 docs/shots/bg/_credits_preview.json 生成 docs/IMAGE-CREDITS.md。"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CREDITS = ROOT / "docs" / "shots" / "bg" / "_credits_preview.json"
OUT = ROOT / "docs" / "IMAGE-CREDITS.md"

NAMES = {
    "wanfenglin": "万峰林", "pingba-cherry": "贵安平坝樱花", "huajiang-bridge": "花江峡谷大桥",
    "zhaoxing-dong": "肇兴侗寨", "zhenyuan": "镇远古镇", "qingyan": "青岩古镇",
    "wumeng-grassland": "乌蒙大草原", "baili-dujuan": "毕节百里杜鹃",
    "xiaoqikong": "荔波小七孔", "zhijindong": "织金洞",
}


def clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip().replace("|", "/")


def main() -> None:
    rows = json.loads(CREDITS.read_text(encoding="utf-8"))
    lines = [
        "# 景点图片版权与来源",
        "",
        "`app/static/images/` 下 10 个新增景点的实景图来源与许可。新增或替换图片时请同步更新本文件。",
        "",
        "| 文件 | 景点 | 来源 | 许可 | 作者 |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        src = row["source"]
        if src.startswith("repo:"):
            src = f"项目自带素材 `{src[5:]}`"
        else:
            title = src.rsplit("/", 1)[-1].replace("_", " ")
            src = f"[{title}]({src})"
        lines.append(
            f"| `{row['file']}` | {NAMES.get(row['subject'], row['subject'])} | {src} | "
            f"{row.get('license', '')} | {clean(row.get('author', ''))} |"
        )
    lines += [
        "",
        "## 说明",
        "",
        "- 全部图片来自项目素材库 `新十大风景图/十大风景图/`（原图不入库，见 `.gitignore`），按景点分目录、`<缩写><序号>` 命名。",
        "- `scripts/make_attraction_images.py` 把原图裁成 1200×800 JPEG（q82）写入 `app/static/images/`，命名与素材库一致。",
        "- 每个景点 6 张，第一张作卡片/详情封面；替换或新增图片后重跑 `make_attraction_images.py` + `seed_attraction_images.py` 即可。",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
