from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("user", "admin", name="user_role"), nullable=False, default="user")
    nickname = db.Column(db.String(50))
    avatar = db.Column(db.String(255))
    avatar_data = db.Column(db.LargeBinary)      # 头像二进制（上传后统一压成 256×256 JPEG）
    avatar_mime = db.Column(db.String(30))
    avatar_version = db.Column(db.Integer, default=0)
    status = db.Column(db.Enum("active", "disabled", name="user_status"), nullable=False, default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    @property
    def is_active(self):  # Flask-Login 会读这个属性
        return self.status == "active"

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def display_name(self):
        return self.nickname or self.username

    @property
    def avatar_url(self):
        """头像地址（带版本号做缓存失效）；没有上传时返回空串，模板回落到首字。"""
        if not self.avatar_data:
            return ""
        return f"/avatar/{self.id}?v={self.avatar_version or 1}"

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Attraction(db.Model):
    __tablename__ = "attractions"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    summary = db.Column(db.String(200))
    description = db.Column(db.Text)
    address = db.Column(db.String(255))
    transport = db.Column(db.Text)
    tips = db.Column(db.Text)
    city = db.Column(db.String(50))
    province = db.Column(db.String(50))
    region = db.Column(db.String(50))
    longitude = db.Column(db.Numeric(10, 7))
    latitude = db.Column(db.Numeric(10, 7))
    cover_image = db.Column(db.String(255))
    category = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.JSON)
    rating = db.Column(db.Numeric(2, 1), default=0)
    rating_count = db.Column(db.Integer, default=0)
    price = db.Column(db.Numeric(10, 2), default=0)
    open_time = db.Column(db.String(100))
    ticket_note = db.Column(db.String(255))
    best_months = db.Column(db.String(50))
    seasonal = db.Column(db.Boolean, default=False, nullable=False)
    visit_duration = db.Column(db.Integer)
    poetic_description = db.Column(db.Text)
    weather_code = db.Column(db.String(20))
    sources = db.Column(db.JSON)
    verified_at = db.Column(db.Date)
    status = db.Column(db.Enum("draft", "published", name="attr_status"), nullable=False, default="published")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = db.relationship(
        "AttractionImage",
        backref="attraction",
        lazy="selectin",
        order_by="AttractionImage.sort_order",
        cascade="all, delete-orphan",
    )
    translations = db.relationship(
        "AttractionTranslation",
        backref="attraction",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    @property
    def price_label(self):
        if not self.price:
            return "免费"
        return f"¥{int(self.price)}"

    @property
    def card_image(self):
        """卡片/详情首图：优先用实景图集第一张；没有图时用“图片待补”占位。"""
        if self.images:
            return self.images[0].image_url
        return self.cover_image or "/static/images/placeholder.svg"

    @property
    def rating_label(self):
        return f"{float(self.rating or 0):.1f}"


class AttractionImage(db.Model):
    __tablename__ = "attraction_images"

    id = db.Column(db.Integer, primary_key=True)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    caption = db.Column(db.String(120))
    sort_order = db.Column(db.Integer, default=0)
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(255))
    status = db.Column(db.Enum("pending", "approved", "rejected", name="comment_status"), default="pending")
    review_by = db.Column(db.String(10), default="human")   # ai / human / seed
    ai_reason = db.Column(db.String(255))                   # AI 的判定说明（存疑原因）
    parent_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="comments")


class Favorite(db.Model):
    __tablename__ = "favorites"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "attraction_id", name="uk_favorites_user_attraction"),)


class Rating(db.Model):
    __tablename__ = "ratings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "attraction_id", name="uk_ratings_user_attraction"),)


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="RESTRICT"), nullable=False)
    visit_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum("pending", "paid", "cancelled", name="booking_status"), default="pending")
    payment_method = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Itinerary(db.Model):
    __tablename__ = "itineraries"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    days = db.Column(db.Integer, nullable=False)
    items = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AssistantLog(db.Model):
    __tablename__ = "assistant_logs"

    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.Integer)
    session_id = db.Column(db.String(64), nullable=False)
    message = db.Column(db.Text, nullable=False)
    intent = db.Column(db.String(20))
    action = db.Column(db.JSON)
    latency_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AttractionTranslation(db.Model):
    __tablename__ = "attraction_translations"

    id = db.Column(db.Integer, primary_key=True)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    lang = db.Column(db.Enum("zh", "en", name="trans_lang"), nullable=False)
    name = db.Column(db.String(120))
    summary = db.Column(db.String(400))
    description = db.Column(db.Text)
    poetic = db.Column(db.Text)
    address = db.Column(db.String(255))
    transport = db.Column(db.Text)
    tips = db.Column(db.Text)
    open_time = db.Column(db.String(100))
    ticket_note = db.Column(db.String(255))

    __table_args__ = (db.UniqueConstraint("attraction_id", "lang", name="uk_attr_lang"),)


class ViewLog(db.Model):
    __tablename__ = "view_logs"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    view_date = db.Column(db.Date, nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "attraction_id", "view_date", name="uk_view_user_attr_day"),
    )


class TrafficDaily(db.Model):
    """景点访问量按天汇总（登录用户 + 游客都算），供后台看流量。"""

    __tablename__ = "traffic_daily"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    attraction_id = db.Column(db.Integer, db.ForeignKey("attractions.id", ondelete="CASCADE"), nullable=False)
    day = db.Column(db.Date, nullable=False)
    views = db.Column(db.Integer, nullable=False, default=0)
    visitors = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("attraction_id", "day", name="uk_traffic_attr_day"),
    )
