import html
import logging
import telebot
from telebot import apihelper

import config
import db
from rate_limiter import SlidingWindowRateLimiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

if config.PROXY_URL:
    apihelper.proxy = {"https": config.PROXY_URL, "http": config.PROXY_URL}
    logger.info(f"🔌 پروکسی تنظیم شد: {config.PROXY_URL}")

bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML")

chat_rate_limiter = SlidingWindowRateLimiter(
    max_requests=config.CHAT_RATE_LIMIT_MAX,
    window_seconds=config.CHAT_RATE_LIMIT_WINDOW_SEC,
    warn_cooldown=5.0,
)

_PERSIAN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def esc(text: str) -> str:
    """پاک‌سازی متن کاربر برای جلوگیری از خطای تگ‌های HTML"""
    return html.escape(str(text or ""))


def normalize_digits(text: str) -> str:
    """تبدیل اعداد فارسی و عربی به انگلیسی"""
    return (text or "").translate(_PERSIAN_ARABIC_DIGITS).strip()


def normalize_phone(raw_phone: str) -> str:
    """پاک‌سازی و یکدست‌سازی شماره تماس"""
    cleaned = normalize_digits(raw_phone)
    cleaned = cleaned.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("+98"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("98") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    return cleaned


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def get_all_support_ids() -> set:
    try:
        db_ids = set(db.get_support_agent_ids())
    except Exception:
        db_ids = set()
    return set(config.SUPPORT_IDS) | db_ids


def is_support(user_id: int) -> bool:
    return user_id in get_all_support_ids()


def can_moderate(user_id: int) -> bool:
    return is_admin(user_id) or is_support(user_id)


def notify_admins(text: str) -> None:
    for admin_id in config.ADMIN_IDS:
        try:
            bot.send_message(admin_id, text)
        except Exception as exc:
            logger.warning(f"عدم امکان ارسال اعلان به ادمین {admin_id}: {exc}")


def notify_support(text: str) -> None:
    support_ids = get_all_support_ids()
    if not support_ids:
        notify_admins(f"{text}\n\n<i>ℹ️ هنوز پشتیبانی تعریف نشده است (با /addsupport اضافه کنید).</i>")
        return

    for sid in support_ids:
        try:
            bot.send_message(sid, text)
        except Exception as exc:
            logger.warning(f"عدم امکان ارسال گزارش به پشتیبان {sid}: {exc}")


def check_not_banned(user_id: int, chat_id: int) -> bool:
    if db.is_user_banned(user_id):
        bot.send_message(chat_id, "⛔ دسترسی شما به ربات محدود شده است.")
        return False
    return True


def safe_edit_message(text: str, chat_id: int, message_id: int, reply_markup=None):
    try:
        bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e):
            bot.send_message(chat_id, text, reply_markup=reply_markup)
