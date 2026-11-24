import os
from dotenv import load_dotenv

load_dotenv()


def load_bot_token() -> str:
    """خواندن توکن از متغیر محیطی (.env) یا Token.txt"""
    token = os.getenv("BOT_TOKEN", "").strip()
    if token:
        return token

    if os.path.exists("Token.txt"):
        with open("Token.txt", "r", encoding="utf-8") as f:
            raw = f.read().strip()
            parts = raw.split(":")
            if len(parts) >= 2:
                return f"{parts[-2]}:{parts[-1]}"

    raise RuntimeError("❌ توکن ربات تنظیم نشده است! BOT_TOKEN را در فایل .env وارد کنید.")


def load_id_set(env_key: str) -> set:
    raw = os.getenv(env_key, "").strip()
    return {int(item.strip()) for item in raw.split(",") if item.strip().isdigit()}


def load_bool(env_key: str, default: bool = False) -> bool:
    raw = os.getenv(env_key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    pg_user = os.getenv("POSTGRES_USER", "").strip()
    pg_pass = os.getenv("POSTGRES_PASSWORD", "").strip()
    pg_db = os.getenv("POSTGRES_DB", "team_finder").strip()
    pg_host = os.getenv("POSTGRES_HOST", "postgres").strip()
    pg_port = os.getenv("POSTGRES_PORT", "5432").strip()
    if pg_user and pg_pass:
        return f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    raise RuntimeError("❌ تنظیمات DATABASE_URL یا POSTGRES_USER/POSTGRES_PASSWORD در .env یافت نشد.")


BOT_TOKEN = load_bot_token()
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://viiv202.github.io/Sports-Hall-Reservation/index.html")
ADMIN_IDS = load_id_set("ADMIN_IDS")
SUPPORT_IDS = load_id_set("SUPPORT_IDS")
PROXY_URL = os.getenv("PROXY_URL", "").strip()
DATABASE_URL = load_database_url()

# امنیت احراز هویت شماره تماس: به صورت پیش‌فرض فقط از طریق دکمه رسمی تلگرام (request_contact)
ALLOW_MANUAL_PHONE = load_bool("ALLOW_MANUAL_PHONE", default=False)

# تنظیمات ضد اسپم چت ناشناس و انقضای خودکار
CHAT_RATE_LIMIT_MAX = int(os.getenv("CHAT_RATE_LIMIT_MAX", "5"))
CHAT_RATE_LIMIT_WINDOW_SEC = float(os.getenv("CHAT_RATE_LIMIT_WINDOW_SEC", "5.0"))
LOBBY_TTL_HOURS = int(os.getenv("LOBBY_TTL_HOURS", "24"))
PENDING_CHAT_TTL_HOURS = int(os.getenv("PENDING_CHAT_TTL_HOURS", "2"))

POSITIONS_MAP = {
    "gk": "دروازه‌بان 🧤",
    "def": "عقب‌گیر / دفاع 🛡️",
    "wing": "وینگر (چپ/راست) 🏃",
    "att": "مهاجم (راس) ⚡"
}

SKILL_MAP = {
    "beg": "مبتدی 🌱",
    "mid": "متوسط ⚽",
    "pro": "حرفه‌ای 🔥"
}

DEMO_CHAT_REPLIES = [
    "سلام رفیق! پایه‌ام، بازی دقیقاً چه ساعتی و کدوم محدوده هست؟",
    "عالیه 👌 من خودم راس ساعت اونجام. کفش سالنی هم آماده دارم.",
    "تعداد بچه‌ها الان چند نفر شده؟ یک نفر دیگه هم بخواید می‌تونم خبر بدم.",
    "حله داداش، روی من حساب کنید! ⚽🔥"
]
