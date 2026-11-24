from telebot import types

import config
import db
from bot_instance import esc, is_admin


def get_webapp_reply_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(
        types.KeyboardButton(
            text="⚽ باز کردن نمای گرافیکی زمین فوتسال (تیم‌یابی)",
            web_app=types.WebAppInfo(url=config.WEBAPP_URL)
        )
    )
    return kb


def get_contact_reply_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📱 اشتراک‌گذاری شماره تماس من", request_contact=True))
    return kb


def get_in_chat_reply_keyboard(can_approve_lobby: bool = False) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if can_approve_lobby:
        kb.add(types.KeyboardButton("✅ تایید عضویت در لابی"))
    kb.add(
        types.KeyboardButton("❌ پایان چت و بازگشت به منو"),
        types.KeyboardButton("🚨 گزارش مزاحمت و پایان چت")
    )
    return kb


def get_main_menu_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    user = db.upsert_user(user_id, "ورزشکار")
    avail_badge = "🟢 فعال" if user.get("is_available") else "⚪ غیرفعال"

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🤝 لابی‌های تیم‌یابی امشب (تکمیل تیم)", callback_data="menu_lobbies"),
        types.InlineKeyboardButton("🔍 پیدا کردن یار کمکی و چت ناشناس", callback_data="menu_players"),
        types.InlineKeyboardButton(f"⚡ وضعیت آمادگی من برای امشب: {avail_badge}", callback_data="menu_avail"),
        types.InlineKeyboardButton("💡 ارسال بازخورد و پیشنهاد (تست بتا)", callback_data="menu_feedback"),
        types.InlineKeyboardButton("📝 ویرایش پروفایل و تنظیمات حریم خصوصی", callback_data="edit_profile_menu"),
    )
    if is_admin(user_id) or not config.ADMIN_IDS:
        kb.add(types.InlineKeyboardButton("🎛 ریست دیتای نمونه تست (بدون حذف کاربران واقعی)", callback_data="demo_reset"))
    return kb


def get_main_menu_text(user_id: int, fallback_name: str = "ورزشکار") -> str:
    user = db.upsert_user(user_id, fallback_name)
    name = esc(user.get("full_name") or fallback_name)
    pos = esc(user.get("position") or "آزاد")
    skill = esc(user.get("skill_level") or "متوسط")
    return (
        f"👋 سلام <b>{name}</b> عزیز!\n"
        f"به ربات هوشمند <b>تیم‌یابی و هم‌تیمی‌یابی فوتسال</b> خوش آمدید.\n\n"
        f"⚽ <b>پست تخصصی:</b> {pos}\n"
        f"⭐ <b>سطح بازی:</b> {skill}\n"
        f"🔒 <i>شماره تماس شما محرمانه است و چت با بازیکنان کاملاً ناشناس داخل ربات انجام می‌شود.</i>\n\n"
        f"👇 بخش مورد نظر خود را انتخاب کنید:"
    )


def get_edit_profile_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✏️ تغییر نام نمایشی", callback_data="edit_field_name"),
        types.InlineKeyboardButton("📞 تغییر شماره تماس", callback_data="edit_field_phone"),
        types.InlineKeyboardButton("⭐ تغییر سطح بازی", callback_data="edit_field_skill"),
        types.InlineKeyboardButton("⚽ تغییر پست‌های تخصصی", callback_data="edit_field_positions"),
    )
    kb.add(types.InlineKeyboardButton("🔕 مدیریت کاربران مسدودشده من", callback_data="my_blocked_users"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    return kb


def get_edit_profile_text(user_id: int) -> str:
    user = db.upsert_user(user_id, "ورزشکار")
    return (
        f"📝 <b>ویرایش پروفایل بازیکن:</b>\n\n"
        f"👤 <b>نام نمایشی:</b> {esc(user.get('full_name'))}\n"
        f"📞 <b>شماره تماس (محرمانه):</b> <code>{esc(user.get('phone') or 'ثبت نشده')}</code>\n"
        f"⭐ <b>سطح بازی:</b> {esc(user.get('skill_level'))}\n"
        f"⚽ <b>پست تخصصی:</b> {esc(user.get('position'))}\n\n"
        f"👇 دقیقاً کدام مورد را می‌خواهید تغییر دهید؟"
    )


def build_positions_keyboard(selected: set, prefix: str, done_label: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    for code, label in config.POSITIONS_MAP.items():
        mark = "✅ " if code in selected else "⬜ "
        buttons.append(types.InlineKeyboardButton(f"{mark}{label}", callback_data=f"{prefix}_{code}"))
    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton(done_label, callback_data=f"{prefix}_done"))
    return kb
