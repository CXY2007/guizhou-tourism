import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _load_secret_key() -> str:
    """会话签名钥匙：优先 .env 的 SECRET_KEY；否则用 instance/.secret_key 里持久化的随机串。

    都没有就生成一个并落盘——这样 clone 下来不配 .env 也能直接跑，
    同时不会因为源码里写死的默认值让任何人都能伪造 session。
    """
    value = os.getenv("SECRET_KEY")
    if value:
        return value
    key_file = BASE_DIR / "instance" / ".secret_key"
    try:
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError:
        pass
    generated = secrets.token_hex(32)
    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(generated, encoding="utf-8")
        os.chmod(key_file, 0o600)
    except OSError:
        pass
    return generated


def _normalize_db_url(url: str) -> str:
    """把相对路径的 SQLite 连接串固定到项目根目录，避免换个工作目录就找不到库。"""
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith("sqlite:////"):
        relative = url[len(prefix):]
        if relative and ":" not in relative[:2] and not relative.startswith("/"):
            return f"{prefix}{(BASE_DIR / relative).resolve().as_posix()}"
    return url


class Config:
    SECRET_KEY = _load_secret_key()
    # 默认走随包的 SQLite 演示库（不写任何数据库口令）；
    # 需要 MySQL 时在 .env 里设置 DATABASE_URL，例如：
    #   DATABASE_URL=mysql+pymysql://<用户>:<密码>@127.0.0.1:3306/tourism_v2?charset=utf8mb4
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.getenv("DATABASE_URL") or "sqlite:///instance/guizhou.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = None

    BABEL_DEFAULT_LOCALE = "zh"
    BABEL_SUPPORTED_LOCALES = ["zh", "en"]
    ITEMS_PER_PAGE = 12
    HEFENG_KEY = os.getenv("HEFENG_KEY", "")
    HEFENG_HOST = os.getenv("HEFENG_HOST") or "devapi.qweather.com"
    AMAP_JS_KEY = os.getenv("AMAP_JS_KEY", "")
    AMAP_SECURITY_CODE = os.getenv("AMAP_SECURITY_CODE", "")
    AMAP_WEB_KEY = os.getenv("AMAP_WEB_KEY", "")
    AI_API_KEY = os.getenv("AI_API_KEY", "")
    AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
    AI_MODEL = os.getenv("AI_MODEL", "deepseek-chat")
    AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "15") or 15)
    AI_RATE_LIMIT = int(os.getenv("AI_RATE_LIMIT", "20") or 20)
    # 小红书笔记参考（AI 行程规划用）：整段 cookie 字符串；留空则用 content/xhs-notes.json 兜底
    XHS_COOKIE = os.getenv("XHS_COOKIE", "")
    # 住宿推荐（AI 行程用）：RollingGo 公共 MCP 代理，无需 Key；置空即整体关闭，行程照常生成
    HOTEL_PROXY_URL = os.getenv("HOTEL_PROXY_URL", "https://rollinggo-proxy-oekjonytob.cn-hangzhou.fcapp.run")
    HOTEL_TIMEOUT = float(os.getenv("HOTEL_TIMEOUT", "8") or 8)
