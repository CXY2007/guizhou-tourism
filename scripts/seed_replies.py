"""给已有评论补几条自然回复（楼中楼演示）。幂等。"""
import pathlib
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import Comment, User

# (父评论内容片段, 回复内容)
REPLIES = [
    ("水帘洞一定会湿身，雨衣景区里卖 5 块", "门口那家两块的质量差点，但拍照够用了，自己带厚的更舒服。"),
    ("红云金顶不能提前约", "我上周去叫号等了四十分钟，八点前进园确实能少等一大截。"),
    ("一定西门进东门出，全程下坡", "赞同，上次东门进爬坡爬到怀疑人生，腿疼了三天。"),
    ("观景台最好早上七点半前去", "七点到拍到了云海，雾散得很快，值回早起。"),
    ("洞内常年十六度", "夏天进去真的像开空调，我穿短袖差点冻出来，外套必须带。"),
]

app = create_app()
with app.app_context():
    rng = random.Random(20261104)
    posters = [u for u in User.query.filter(User.status == "active", User.role != "admin").all()]
    created = skipped = 0
    for needle, reply_text in REPLIES:
        parent = Comment.query.filter(Comment.content.like(f"%{needle}%"), Comment.status == "approved").first()
        if parent is None:
            print("  跳过（找不到父评论）:", needle[:16])
            skipped += 1
            continue
        exists = Comment.query.filter_by(parent_id=parent.id, content=reply_text).first()
        if exists:
            skipped += 1
            continue
        candidates = [u for u in posters if u.id != parent.user_id] or posters
        db.session.add(Comment(
            user_id=rng.choice(candidates).id,
            attraction_id=parent.attraction_id,
            content=reply_text,
            parent_id=parent.id,
            status="approved",
            created_at=(parent.created_at or datetime.utcnow()) + timedelta(hours=rng.randint(2, 40)),
        ))
        created += 1
    db.session.commit()
    total = Comment.query.count()
    replies = Comment.query.filter(Comment.parent_id.isnot(None)).count()
    print(f"新增回复 {created} 条，跳过 {skipped} 条；当前评论 {total} 条（含回复 {replies} 条）")
