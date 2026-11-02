import os
import json
import telebot
from telebot import types, apihelper
from dotenv import load_dotenv
import db

# بارگذاری متغیرهای محیطی
load_dotenv()


def load_bot_token() -> str:
    """خواندن هوشمند توکن از فایل Token.txt یا متغیر محیطی"""
    default_token = "9106404923:AAHk4Kz0elPBr3BoeCr1tu1zvhFr2LA4ZHs"
    if os.path.exists("Token.txt"):
        try:
            with open("Token.txt", "r", encoding="utf-8") as f:
                raw = f.read().strip()
                parts = raw.split(":")
                if len(parts) >= 2:
                    return f"{parts[-2]}:{parts[-1]}"
        except Exception:
            pass
    return os.getenv("BOT_TOKEN", default_token)


BOT_TOKEN = load_bot_token()
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://viiv202.github.io/Sports-Hall-Reservation/index.html")

# تنظیم پروکسی در صورت نیاز
apihelper.proxy = {'https': 'http://127.0.0.1:3067'}

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# راه‌اندازی دیتابیس هنگام روشن شدن بات
db.init_db()
if not db.get_slots():
    db.reset_demo_data()

# حافظه موقت برای نگهداری مراحل ثبت‌نام کاربران
reg_temp = {}

# لیست پست‌های قابل انتخاب در مرحله سوم ثبت‌نام
POSITIONS_MAP = {
    "gk": "دروازه‌بان 🧤",
    "def": "عقب‌گیر / دفاع 🛡️",
    "wing": "وینگر (چپ/راست) 🏃",
    "att": "مهاجم (راس) ⚡"
}


# =====================================================================
# توابع کمکی منوها و کیبوردها
# =====================================================================

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


def get_webapp_reply_keyboard() -> types.ReplyKeyboardMarkup:
    """کیبورد پایین صفحه مخصوص باز کردن مینی‌اپ گرافیکی"""
    webapp_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    webapp_kb.add(
        types.KeyboardButton(
            text="📱 باز کردن مینی‌اپ گرافیکی (چمن فوتسال و رزرو)",
            web_app=types.WebAppInfo(url=WEBAPP_URL)
        )
    )
    return webapp_kb


def get_main_menu_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    """منوی اصلی بازیکن (بدون دکمه پنل مدیر سالن)"""
    user = db.upsert_user(user_id, "کاربر")
    avail_badge = "🟢 فعال" if user.get("is_available") else "⚪ غیرفعال"

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🏟 رزرو سانس سالن ورزشی", callback_data="menu_slots"),
        types.InlineKeyboardButton("🤝 لابی‌های تیم‌یابی امشب (تکمیل تیم)", callback_data="menu_lobbies"),
        types.InlineKeyboardButton("🔍 پیدا کردن یار کمکی (بازیکنان آماده)", callback_data="menu_players"),
        types.InlineKeyboardButton(f"⚡ وضعیت آمادگی من برای امشب: {avail_badge}", callback_data="menu_avail"),
        types.InlineKeyboardButton("📝 ثبت‌نام مجدد / ویرایش پروفایل بازیکن", callback_data="start_register"),
        types.InlineKeyboardButton("🎛 ریست اطلاعات دمو (ویژه جلسه ارائه)", callback_data="demo_reset")
    )
    return kb


def get_main_menu_text(user_id: int, fallback_name: str = "ورزشکار") -> str:
    """متن خوش‌آمدگویی منوی اصلی به همراه خلاصه پروفایل بازیکن"""
    user = db.upsert_user(user_id, fallback_name)
    name = user.get("full_name") or fallback_name
    pos = user.get("position") or "آزاد"
    phone = user.get("phone") or "ثبت نشده"
    return (
        f"👋 سلام <b>{name}</b> عزیز!\n"
        f"به سامانه هوشمند <b>رزرو سالن و هم‌تیمی‌یابی فوتسال</b> خوش آمدید.\n\n"
        f"👤 <b>پست تخصصی شما:</b> {pos}\n"
        f"📞 <b>شماره هماهنگی:</b> <code>{phone}</code>\n\n"
        f"🔹 <b>رزرو آنلاین سانس</b> با تایید آنی\n"
        f"🔹 <b>پیدا کردن یار کمکی</b> برای تیم‌های ناقص\n"
        f"🔹 <b>لابی‌های عمومی</b> برای هماهنگی افراد تکی\n\n"
        f"👇 لطفاً یکی از بخش‌های زیر را انتخاب کنید:"
    )


def get_admin_menu_keyboard() -> types.InlineKeyboardMarkup:
    """ساخت کیبورد شیشه‌ای پنل اختصاصی مدیر سالن"""
    pending_count = len(db.get_pending_slots())
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 باز و بسته کردن کلیکی سانس‌ها (🟢/🔴)", callback_data="admin_toggle_list"),
        types.InlineKeyboardButton(f"🧾 بررسی فیش‌های در انتظار تایید ({pending_count})", callback_data="admin_pending"),
        types.InlineKeyboardButton("➕ افزودن سریع سانس و قیمت جدید", callback_data="admin_add_day"),
        types.InlineKeyboardButton("📢 تبدیل سانس خالی مانده به لابی عمومی", callback_data="admin_slot_to_lobby")
    )
    return kb


def get_admin_menu_text() -> str:
    pending_count = len(db.get_pending_slots())
    return (
        f"⚙️ <b>پنل اختصاصی مدیریت سالن ورزشی:</b>\n\n"
        f"📥 فیش‌های منتظر بررسی: <b>{pending_count} مورد</b>\n"
        f"💡 <i>برای بازگشت به پنل بازیکن از دستور</i> /rule_player <i>استفاده کنید.</i>"
    )


# =====================================================================
# دستورات تغییر نقش مستقیم (/rule_Hallad و /rule_player)
# =====================================================================

@bot.message_handler(commands=["rule_Hallad", "rule_hallad"])
def cmd_rule_hall_admin(message: types.Message):
    """ورود مستقیم به پنل مدیر سالن با دستور /rule_Hallad"""
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_id = message.from_user.id
    db.upsert_user(user_id, message.from_user.first_name or "مدیر سالن")
    db.set_user_role(user_id, "manager")

    bot.send_message(
        message.chat.id,
        get_admin_menu_text(),
        reply_markup=get_admin_menu_keyboard()
    )


@bot.message_handler(commands=["rule_player", "rule_Player"])
def cmd_rule_player(message: types.Message):
    """ورود مستقیم به پنل بازیکن با دستور /rule_player"""
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_id = message.from_user.id
    fallback_name = message.from_user.first_name or "ورزشکار"
    db.upsert_user(user_id, fallback_name)
    db.set_user_role(user_id, "player")

    bot.send_message(
        message.chat.id,
        "🏃 <b>پنل کاربری بازیکن فعال شد!</b>\n"
        "از دکمه پایین صفحه می‌توانید نمای گرافیکی زمین و سانس‌ها را باز کنید:",
        reply_markup=get_webapp_reply_keyboard()
    )
    bot.send_message(
        message.chat.id,
        get_main_menu_text(user_id, fallback_name),
        reply_markup=get_main_menu_keyboard(user_id)
    )


# =====================================================================
# فرآیند ثبت‌نام ۳ مرحله‌ای در شروع ربات (نام -> شماره تماس -> پست تخصصی)
# =====================================================================

def start_registration_flow(chat_id: int, user_id: int):
    """شروع مرحله ۱ ثبت‌نام: دریافت نام و نام خانوادگی"""
    bot.clear_step_handler_by_chat_id(chat_id)
    reg_temp[user_id] = {"name": "", "phone": "", "positions": set()}

    msg = bot.send_message(
        chat_id,
        "📝 <b>خوش آمدید! ثبت‌نام اولیه بازیکن (گام ۱ از ۳):</b>\n\n"
        "لطفاً <b>نام و نام خانوادگی</b> خود را وارد کنید:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    bot.register_next_step_handler(msg, process_reg_name_step)


def process_reg_name_step(message: types.Message):
    """ذخیره نام و رفتن به مرحله ۲: دریافت شماره تماس"""
    if message.text and message.text.startswith("/"):
        # اگر کاربر وسط ثبت‌نام دستور جدیدی زد
        if message.text.lower().startswith("/rule_hallad"):
            cmd_rule_hall_admin(message)
        elif message.text.lower().startswith("/rule_player"):
            cmd_rule_player(message)
        elif message.text.lower().startswith("/start"):
            cmd_start(message)
        return

    user_id = message.from_user.id
    full_name = (message.text or message.from_user.first_name or "ورزشکار").strip()
    if user_id not in reg_temp:
        reg_temp[user_id] = {"name": full_name, "phone": "", "positions": set()}
    else:
        reg_temp[user_id]["name"] = full_name

    # کیبورد اشتراک‌گذاری شماره تماس تلگرام
    contact_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    contact_kb.add(
        types.KeyboardButton("📱 اشتراک‌گذاری شماره تماس من", request_contact=True)
    )

    msg = bot.send_message(
        message.chat.id,
        f"✅ نام شما (<b>{full_name}</b>) ثبت شد.\n\n"
        f"📞 <b>گام ۲ از ۳ (شماره تماس):</b>\n"
        f"برای هماهنگی بازی‌ها و لابی‌ها، لطفاً روی دکمه <b>«📱 اشتراک‌گذاری شماره تماس من»</b> در پایین صفحه بزنید (یا شماره موبایل خود را تایپ کنید):",
        reply_markup=contact_kb
    )
    bot.register_next_step_handler(msg, process_reg_phone_step)


def process_reg_phone_step(message: types.Message):
    """ذخیره شماره تماس و رفتن به مرحله ۳: انتخاب پست‌های تخصصی"""
    if message.text and message.text.startswith("/"):
        if message.text.lower().startswith("/rule_hallad"):
            cmd_rule_hall_admin(message)
        elif message.text.lower().startswith("/rule_player"):
            cmd_rule_player(message)
        elif message.text.lower().startswith("/start"):
            cmd_start(message)
        return

    user_id = message.from_user.id
    if message.content_type == "contact" and message.contact:
        phone = message.contact.phone_number
    else:
        phone = (message.text or "09120000000").strip()

    if user_id not in reg_temp:
        reg_temp[user_id] = {"name": message.from_user.first_name or "ورزشکار", "phone": phone, "positions": set()}
    else:
        reg_temp[user_id]["phone"] = phone

    # فعال‌سازی مجدد کیبورد مینی‌اپ در پایین صفحه
    bot.send_message(
        message.chat.id,
        "✅ شماره تماس دریافت شد!",
        reply_markup=get_webapp_reply_keyboard()
    )

    # ارسال کیبورد شیشه‌ای انتخاب پست‌های تخصصی
    bot.send_message(
        message.chat.id,
        "⚽ <b>گام ۳ از ۳ (پست تخصصی):</b>\n\n"
        "در کدام پست‌ها تبحر بیشتری دارید؟\n"
        "<i>(می‌توانید یک یا چند پست را تیک بزنید و سپس روی دکمه ثبت نهایی کلیک کنید):</i>",
        reply_markup=build_positions_keyboard(user_id)
    )


def build_positions_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    """ساخت کیبورد چندانتخابی برای پست‌های تخصصی فوتسال"""
    selected = reg_temp.get(user_id, {}).get("positions", set())
    kb = types.InlineKeyboardMarkup(row_width=2)

    buttons = []
    for code, label in POSITIONS_MAP.items():
        mark = "✅ " if code in selected else "⬜ "
        buttons.append(types.InlineKeyboardButton(f"{mark}{label}", callback_data=f"regpos_{code}"))

    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton("🚀 ثبت نهایی اطلاعات و ورود به ربات", callback_data="regpos_done"))
    return kb


@bot.callback_query_handler(func=lambda call: call.data.startswith("regpos_"))
def cb_register_positions(call: types.CallbackQuery):
    """مدیریت تیک زدن پست‌ها و اتمام ثبت‌نام"""
    user_id = call.from_user.id
    if user_id not in reg_temp:
        reg_temp[user_id] = {
            "name": call.from_user.first_name or "ورزشکار",
            "phone": "09120000000",
            "positions": set()
        }

    action = call.data.split("_")[1]
    if action == "done":
        chosen_codes = reg_temp[user_id]["positions"]
        if not chosen_codes:
            bot.answer_callback_query(call.id, "⚠️ لطفاً حداقل یک پست را انتخاب کنید!", show_alert=True)
            return

        pos_str = " ، ".join([POSITIONS_MAP[c] for c in chosen_codes])
        name = reg_temp[user_id]["name"]
        phone = reg_temp[user_id]["phone"]

        db.complete_user_registration(user_id, name, phone, pos_str)
        bot.answer_callback_query(call.id, "🎉 ثبت‌نام شما با موفقیت تکمیل شد!")

        safe_edit_message(
            get_main_menu_text(user_id, name),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_menu_keyboard(user_id)
        )
    else:
        # اضافه یا کم کردن پست انتخابی (Toggle)
        if action in reg_temp[user_id]["positions"]:
            reg_temp[user_id]["positions"].remove(action)
        else:
            reg_temp[user_id]["positions"].add(action)

        safe_edit_message(
            "⚽ <b>گام ۳ از ۳ (پست تخصصی):</b>\n\n"
            "در کدام پست‌ها تبحر بیشتری دارید؟\n"
            "<i>(می‌توانید یک یا چند پست را تیک بزنید و سپس روی دکمه ثبت نهایی کلیک کنید):</i>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_positions_keyboard(user_id)
        )


@bot.callback_query_handler(func=lambda call: call.data == "start_register")
def cb_start_register_again(call: types.CallbackQuery):
    """شروع مجدد فرآیند ثبت‌نام با کلیک روی دکمه ویرایش پروفایل"""
    bot.answer_callback_query(call.id)
    start_registration_flow(call.message.chat.id, call.from_user.id)


# =====================================================================
# هندلر دستور /start و دکمه ریست دمو
# =====================================================================

@bot.message_handler(commands=["start", "demo"])
def cmd_start(message: types.Message):
    """بررسی ثبت‌نام کاربر در دستور /start؛ اگر ثبت‌نام نکرده باشد، مراحل ثبت‌نام آغاز می‌شود"""
    bot.clear_step_handler_by_chat_id(message.chat.id)
    user_id = message.from_user.id
    fallback_name = message.from_user.first_name or "ورزشکار"
    user = db.upsert_user(user_id, fallback_name)

    # اگر کاربر هنوز ثبت‌نام اولیه را انجام نداده است، وارد فرآیند ثبت‌نام شود
    if not user.get("is_registered"):
        start_registration_flow(message.chat.id, user_id)
        return

    bot.send_message(
        message.chat.id,
        "✨ <b>نسخه مینی‌اپ گرافیکی فعال است!</b>\n"
        "می‌توانید از دکمه پایین صفحه نمای زمین فوتسال را باز کنید یا از منوی شیشه‌ای زیر استفاده نمایید:",
        reply_markup=get_webapp_reply_keyboard()
    )

    bot.send_message(
        message.chat.id,
        get_main_menu_text(user_id, fallback_name),
        reply_markup=get_main_menu_keyboard(user_id)
    )


@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def cb_main_menu(call: types.CallbackQuery):
    fallback_name = call.from_user.first_name or "ورزشکار"
    safe_edit_message(
        get_main_menu_text(call.from_user.id, fallback_name),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_main_menu_keyboard(call.from_user.id)
    )


@bot.callback_query_handler(func=lambda call: call.data == "demo_reset")
def cb_demo_reset(call: types.CallbackQuery):
    """ریست کامل دیتابیس به حالت اولیه برای تکرار سناریو در جلسه دمو"""
    db.reset_demo_data()
    bot.answer_callback_query(
        call.id,
        "♻️ دیتابیس دمو با موفقیت به حالت اولیه (لابی ۵ از ۶ نفر و سانس‌های نمونه) ریست شد!",
        show_alert=True
    )
    cb_main_menu(call)


# =====================================================================
# بخش ۱: رزرو سانس سالن و ارسال فیش واریزی
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_slots")
def cb_menu_slots(call: types.CallbackQuery):
    slots = db.get_slots()
    kb = types.InlineKeyboardMarkup(row_width=1)

    for s in slots:
        price_str = f"{s['price']:,}"
        if s["status"] == "free":
            btn_text = f"🟢 {s['day_label']} | 🕒 {s['time_range']} | {price_str} تومان"
            kb.add(types.InlineKeyboardButton(btn_text, callback_data=f"slot_select_{s['id']}"))
        elif s["status"] == "pending":
            btn_text = f"🟡 {s['day_label']} | 🕒 {s['time_range']} (در انتظار تایید فیش)"
            kb.add(types.InlineKeyboardButton(btn_text, callback_data="slot_busy"))
        else:
            btn_text = f"🔴 {s['day_label']} | 🕒 {s['time_range']} (رزرو شده)"
            kb.add(types.InlineKeyboardButton(btn_text, callback_data="slot_busy"))

    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    safe_edit_message(
        "🏟 <b>جدول سانس‌های سالن ورزشی:</b>\n\n"
        "🟢 سانس‌های سبز آزاد هستند. برای رزرو روی سانس دلخواه کلیک کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data == "slot_busy")
def cb_slot_busy(call: types.CallbackQuery):
    bot.answer_callback_query(call.id, "⚠️ این سانس قبلاً رزرو شده یا در انتظار بررسی فیش است.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_select_"))
def cb_slot_select(call: types.CallbackQuery):
    slot_id = int(call.data.split("_")[2])
    slot = db.get_slot_by_id(slot_id)
    if not slot or slot["status"] != "free":
        bot.answer_callback_query(call.id, "این سانس دیگر آزاد نیست!", show_alert=True)
        return

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⚡ ارسال فیش فرضی (ویژه تست سریع دمو)", callback_data=f"slot_fastpay_{slot_id}"),
        types.InlineKeyboardButton("📸 آپلود عکس فیش واقعی", callback_data=f"slot_upload_{slot_id}"),
        types.InlineKeyboardButton("🔙 بازگشت به لیست سانس‌ها", callback_data="menu_slots")
    )

    text = (
        f"🧾 <b>پیش‌فاکتور رزرو سانس:</b>\n\n"
        f"📅 روز: <b>{slot['day_label']}</b>\n"
        f"🕒 ساعت: <b>{slot['time_range']}</b>\n"
        f"💳 مبلغ قابل پرداخت: <b>{slot['price']:,} تومان</b>\n"
        f"🏦 شماره کارت سالن: <code>6037-9975-0000-1234</code>\n\n"
        f"لطفاً روش ارسال فیش واریزی را انتخاب کنید:"
    )
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_fastpay_"))
def cb_slot_fastpay(call: types.CallbackQuery):
    slot_id = int(call.data.split("_")[2])
    user = db.upsert_user(call.from_user.id, call.from_user.first_name or "سرگروه تیم")
    db.submit_booking_receipt(slot_id, call.from_user.id, user["full_name"], "DEMO_FAST_RECEIPT")

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    safe_edit_message(
        "✅ <b>فیش واریزی با موفقیت ثبت شد!</b>\n\n"
        "🟡 وضعیت سانس به <b>«در انتظار تایید مدیر سالن»</b> تغییر یافت.\n"
        "💡 <i>(نکته دمو: برای ورود به پنل مدیر و تایید فیش، دستور</i> /rule_Hallad <i>را ارسال کنید!)</i>",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_upload_"))
def cb_slot_upload(call: types.CallbackQuery):
    slot_id = int(call.data.split("_")[2])
    msg = bot.send_message(call.message.chat.id, "📸 لطفاً تصویر فیش یا شماره پیگیری را ارسال کنید:")
    bot.register_next_step_handler(msg, process_receipt_step, slot_id)


def process_receipt_step(message: types.Message, slot_id: int):
    user = db.upsert_user(message.from_user.id, message.from_user.first_name or "سرگروه تیم")
    receipt_info = message.photo[-1].file_id if message.content_type == "photo" else (message.text or "RECEIPT")
    db.submit_booking_receipt(slot_id, message.from_user.id, user["full_name"], receipt_info)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    bot.send_message(
        message.chat.id,
        "✅ فیش شما دریافت و برای مدیر سالن ارسال شد.\n"
        "💡 <i>(برای بررسی در نقش مدیر، دستور</i> /rule_Hallad <i>را بزنید).</i>",
        reply_markup=kb
    )


# =====================================================================
# بخش ۲: اعلام آمادگی بازیکن و پیدا کردن یار کمکی
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_avail")
def cb_menu_avail(call: types.CallbackQuery):
    user = db.upsert_user(call.from_user.id, call.from_user.first_name or "بازیکن")
    status_str = "🟢 آماده بازی امشب" if user["is_available"] else "⚪ غیرفعال"

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧤 دروازه‌بان", callback_data="setavail_1_دروازه‌بان 🧤"),
        types.InlineKeyboardButton("🛡️ دفاع / عقب‌گیر", callback_data="setavail_1_دفاع 🛡️"),
        types.InlineKeyboardButton("⚡ مهاجم", callback_data="setavail_1_مهاجم ⚡"),
        types.InlineKeyboardButton("🏃 بازیکن آزاد", callback_data="setavail_1_بازیکن آزاد 🏃")
    )
    kb.add(types.InlineKeyboardButton("🔴 خاموش کردن وضعیت آمادگی", callback_data="setavail_0_آزاد"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))

    text = (
        f"⚡ <b>وضعیت آمادگی من برای امشب:</b>\n\n"
        f"وضعیت فعلی: <b>{status_str}</b> | پست: <b>{user['position']}</b>\n\n"
        f"اگر امشب وقت آزاد دارید، پست خود را انتخاب کنید تا تیم‌هایی که بازیکن کم دارند شما را دعوت کنند:"
    )
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("setavail_"))
def cb_set_avail(call: types.CallbackQuery):
    parts = call.data.split("_")
    is_avail, position = int(parts[1]), parts[2]
    db.upsert_user(call.from_user.id, call.from_user.first_name or "بازیکن")
    db.update_user_availability(call.from_user.id, is_avail, position, "۲۰ تا ۲۴")
    bot.answer_callback_query(call.id, "✅ وضعیت آمادگی شما بروزرسانی شد!")
    cb_menu_avail(call)


@bot.callback_query_handler(func=lambda call: call.data == "menu_players")
def cb_menu_players(call: types.CallbackQuery):
    players = db.get_available_players()
    kb = types.InlineKeyboardMarkup(row_width=1)

    text = "🔍 <b>لیست بازیکنان آماده امشب (یار کمکی):</b>\n\n"
    for idx, p in enumerate(players, start=1):
        text += (
            f"{idx}. 👤 <b>{p['full_name']}</b> | پست: {p['position']}\n"
            f"   ⭐ سطح: {p['skill_level']} | 🕒 ساعت آزاد: {p['free_hours']}\n\n"
        )
        kb.add(types.InlineKeyboardButton(
            f"📩 ارسال دعوت‌نامه بازی به {p['full_name']}",
            callback_data=f"invite_{p['user_id']}_{p['full_name']}"
        ))

    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("invite_"))
def cb_invite_player(call: types.CallbackQuery):
    target_name = call.data.split("_", 2)[2]
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔍 مشاهده سایر بازیکنان آماده", callback_data="menu_players"),
        types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")
    )
    text = (
        f"📨 <b>دعوت‌نامه بازی برای «{target_name}» ارسال شد!</b>\n\n"
        f"🔔 <b>[شبیه‌ساز زنده دمو - پاسخ بازیکن]:</b>\n"
        f"✅ <b>{target_name}</b> دعوت تیم شما را برای بازی امشب <b>قبول کرد!</b>\n"
        f"📞 شماره هماهنگی بازیکن: <code>0912-111-2233</code>"
    )
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


# =====================================================================
# بخش ۳: سیستم لابی‌های تیم‌یابی
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_lobbies")
def cb_menu_lobbies(call: types.CallbackQuery):
    lobbies = db.get_open_lobbies()
    kb = types.InlineKeyboardMarkup(row_width=1)

    text = "🤝 <b>لابی‌های فعال تیم‌یابی امشب:</b>\n\n"
    for lob in lobbies:
        badge = "✅ تکمیل" if lob["status"] == "full" else f"🟢 باز ({lob['current_players']}/{lob['max_players']})"
        text += f"⚽ <b>{lob['title']}</b>\n🕒 {lob['slot_time']} | وضعیت: <b>{badge}</b>\n\n"
        kb.add(types.InlineKeyboardButton(
            f"👁️ مشاهده و پیوستن: {lob['title']} ({lob['current_players']}/{lob['max_players']})",
            callback_data=f"lobby_view_{lob['id']}"
        ))

    kb.add(
        types.InlineKeyboardButton("➕ ساخت لابی جدید تیم‌یابی", callback_data="lobby_create_menu"),
        types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")
    )
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_view_"))
def cb_lobby_view(call: types.CallbackQuery):
    lobby_id = int(call.data.split("_")[2])
    lobby, members = db.get_lobby_with_members(lobby_id)
    if not lobby:
        return

    members_text = "\n".join([f"  {i}. 👤 {m['player_name']} ({m['position']})" for i, m in enumerate(members, 1)])
    remaining = lobby["max_players"] - lobby["current_players"]

    text = (
        f"🏟 <b>لابی: {lobby['title']}</b>\n\n"
        f"🕒 <b>سانس:</b> {lobby['slot_time']}\n"
        f"👥 <b>ظرفیت:</b> {lobby['current_players']} از {lobby['max_players']} نفر\n\n"
        f"📋 <b>بازیکنان حاضر در لابی:</b>\n{members_text}\n"
    )

    kb = types.InlineKeyboardMarkup(row_width=1)
    if remaining > 0 and lobby["status"] != "full":
        kb.add(types.InlineKeyboardButton(
            f"➕ پیوستن من به این بازی ({lobby['current_players'] + 1}/{lobby['max_players']})",
            callback_data=f"lobby_join_{lobby_id}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست لابی‌ها", callback_data="menu_lobbies"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_join_"))
def cb_lobby_join(call: types.CallbackQuery):
    lobby_id = int(call.data.split("_")[2])
    user = db.upsert_user(call.from_user.id, call.from_user.first_name or "بازیکن جدید")
    result = db.join_lobby(lobby_id, call.from_user.id, user["full_name"], user.get("position") or "بازیکن آزاد ⚡")

    if not result["ok"]:
        bot.answer_callback_query(call.id, "شما قبلاً عضو شده‌اید یا ظرفیت لابی پر است!", show_alert=True)
        return

    lobby = result["lobby"]
    members = result["members"]
    members_text = "\n".join([f"  {i}. ✅ {m['player_name']} ({m['position']})" for i, m in enumerate(members, 1)])

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🏟 رزرو قطعی سانس برای این تیم", callback_data="menu_slots"),
        types.InlineKeyboardButton("🔙 بازگشت به لیست لابی‌ها", callback_data="menu_lobbies")
    )

    if result["just_became_full"]:
        safe_edit_message(
            f"🎉🎉 <b>تبریک! ظرفیت لابی تکمیل شد ({lobby['current_players']}/{lobby['max_players']} نفر)!</b> 🎉🎉\n\n"
            f"⚽ <b>{lobby['title']}</b>\n"
            f"🕒 <b>زمان بازی:</b> {lobby['slot_time']}\n\n"
            f"👥 <b>ترکیب نهایی تیم امشب:</b>\n{members_text}\n\n"
            f"🔒 <b>لابی قفل شد و اطلاعات هماهنگی برای هر {lobby['max_players']} نفر ارسال گردید!</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb
        )
    else:
        bot.answer_callback_query(call.id, "✅ شما وارد لابی شدید!")
        cb_lobby_view(call)


@bot.callback_query_handler(func=lambda call: call.data == "lobby_create_menu")
def cb_lobby_create_menu(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⚽ لابی ۶ نفره (تیم ۵ نفره داریم، ۱ یار کم)", callback_data="lobby_new_6_5"),
        types.InlineKeyboardButton("🏟 لابی ۱۲ نفره عمومی (جمع شدن افراد تکی)", callback_data="lobby_new_12_1"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_lobbies")
    )
    safe_edit_message("➕ <b>نوع لابی جدید را انتخاب کنید:</b>", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_new_"))
def cb_lobby_new_create(call: types.CallbackQuery):
    parts = call.data.split("_")
    max_p, init_p = int(parts[2]), int(parts[3])
    user = db.upsert_user(call.from_user.id, call.from_user.first_name or "سرگروه")
    title = f"لابی فوتسال {user['full_name']} ({'۱ نفر کم' if init_p == 5 else 'عمومی'})"
    db.create_new_lobby(title, "امشب ساعت ۲۲:۳۰ تا ۲۴:۰۰", call.from_user.id, user["full_name"], max_p, init_p)
    bot.answer_callback_query(call.id, "✅ لابی جدید با موفقیت ساخته شد!", show_alert=True)
    cb_menu_lobbies(call)


# =====================================================================
# بخش ۴: پنل اختصاصی مدیر سالن (فعال‌سازی با /rule_Hallad)
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_admin")
def cb_menu_admin(call: types.CallbackQuery):
    """بازگشت از زیرمنوهای ادمین به صفحه اصلی پنل مدیر"""
    safe_edit_message(
        get_admin_menu_text(),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_admin_menu_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data == "admin_toggle_list")
def cb_admin_toggle_list(call: types.CallbackQuery):
    slots = db.get_slots()
    kb = types.InlineKeyboardMarkup(row_width=1)
    for s in slots:
        icon = "🟢 آزاد" if s["status"] == "free" else ("🔴 بسته" if s["status"] == "closed" else "🟡 منتظر/رزرو")
        kb.add(types.InlineKeyboardButton(
            f"{icon} | {s['day_label']} ({s['time_range']}) - {s['price']:,} ت",
            callback_data=f"admin_flip_{s['id']}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیر", callback_data="menu_admin"))
    safe_edit_message(
        "🔄 <b>تغییر وضعیت کلیکی سانس‌ها:</b>\nروی هر سانس کلیک کنید تا بین حالت آزاد (🟢) و رزرو تلفنی (🔴) تغییر کند:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_flip_"))
def cb_admin_flip_slot(call: types.CallbackQuery):
    slot_id = int(call.data.split("_")[2])
    db.toggle_slot_by_manager(slot_id)
    bot.answer_callback_query(call.id, "✅ وضعیت سانس تغییر کرد!")
    cb_admin_toggle_list(call)


@bot.callback_query_handler(func=lambda call: call.data == "admin_add_day")
def cb_admin_add_day(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📅 امروز", callback_data="addslot_day_امروز"),
        types.InlineKeyboardButton("📅 فردا", callback_data="addslot_day_فردا")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin"))
    safe_edit_message("➕ <b>گام ۱ از ۳:</b> روز سانس جدید را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addslot_day_"))
def cb_admin_add_time(call: types.CallbackQuery):
    day_label = call.data.split("_")[2]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for t in ["16:30 تا 18:00", "20:00 تا 21:30", "23:00 تا 00:30"]:
        kb.add(types.InlineKeyboardButton(f"🕒 {t}", callback_data=f"addslot_time_{day_label}_{t}"))
    safe_edit_message(f"➕ <b>گام ۲ از ۳ ({day_label}):</b> ساعت سانس را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addslot_time_"))
def cb_admin_add_price(call: types.CallbackQuery):
    parts = call.data.split("_")
    day_label, time_range = parts[2], parts[3]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for price in [500000, 600000, 700000]:
        kb.add(types.InlineKeyboardButton(f"💳 {price:,} تومان", callback_data=f"addslot_save_{day_label}_{time_range}_{price}"))
    safe_edit_message("➕ <b>گام ۳ از ۳:</b> قیمت سانس را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addslot_save_"))
def cb_admin_save_slot(call: types.CallbackQuery):
    parts = call.data.split("_")
    db.add_new_slot(parts[2], parts[3], int(parts[4]))
    bot.answer_callback_query(call.id, "✅ سانس جدید با موفقیت اضافه شد!", show_alert=True)
    cb_admin_toggle_list(call)


@bot.callback_query_handler(func=lambda call: call.data == "admin_pending")
def cb_admin_pending(call: types.CallbackQuery):
    pendings = db.get_pending_slots()
    kb = types.InlineKeyboardMarkup(row_width=2)
    if not pendings:
        kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیر", callback_data="menu_admin"))
        safe_edit_message("✅ هیچ فیش بررسی‌نشده‌ای وجود ندارد.", call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    text = "🧾 <b>فیش‌های منتظر تایید:</b>\n\n"
    for p in pendings:
        text += f"🔹 سانس #{p['id']}: {p['day_label']} ({p['time_range']}) - رزرو: {p['booked_by_name']}\n"
        kb.add(
            types.InlineKeyboardButton(f"✅ تایید #{p['id']}", callback_data=f"verify_ok_{p['id']}"),
            types.InlineKeyboardButton(f"❌ رد #{p['id']}", callback_data=f"verify_no_{p['id']}")
        )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیر", callback_data="menu_admin"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("verify_"))
def cb_admin_verify(call: types.CallbackQuery):
    parts = call.data.split("_")
    approve = (parts[1] == "ok")
    updated = db.verify_booking_by_manager(int(parts[2]), approve)
    if approve and updated:
        bot.send_message(
            call.message.chat.id,
            f"🔔 <b>[پیام خودکار به مشتری]:</b>\n✅ رزرو سانس <b>{updated['day_label']} ساعت {updated['time_range']}</b> قطعی شد!"
        )
    cb_admin_pending(call)


@bot.callback_query_handler(func=lambda call: call.data == "admin_slot_to_lobby")
def cb_admin_slot_to_lobby(call: types.CallbackQuery):
    free_slots = [s for s in db.get_slots() if s["status"] == "free"]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for s in free_slots:
        kb.add(types.InlineKeyboardButton(f"📢 تبدیل به لابی: {s['day_label']} ({s['time_range']})", callback_data=f"convlobby_{s['id']}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به پنل مدیر", callback_data="menu_admin"))
    safe_edit_message("📢 روی سانس خالی کلیک کنید تا به لابی ۱۲ نفره تبدیل شود:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("convlobby_"))
def cb_convert_slot_to_lobby(call: types.CallbackQuery):
    slot = db.get_slot_by_id(int(call.data.split("_")[1]))
    if slot:
        db.create_new_lobby(f"سانس ویژه ({slot['day_label']})", f"{slot['day_label']} {slot['time_range']}", call.from_user.id, "مدیر سالن", 12, 0)
        bot.answer_callback_query(call.id, "✅ لابی ۱۲ نفره ساخته شد!", show_alert=True)
    cb_menu_admin(call)


# =====================================================================
# بخش ۵: دریافت اطلاعات ارسالی از مینی‌اپ گرافیکی (index.html)
# =====================================================================

@bot.message_handler(content_types=["web_app_data"])
def handle_webapp_response(message: types.Message):
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    user_id = message.from_user.id
    user = db.upsert_user(user_id, message.from_user.first_name or "بازیکن مینی‌اپ")
    user_name = user["full_name"]
    action = data.get("action")

    if action == "join_lobby":
        position = data.get("position", "وینگر چپ ⚡")
        result = db.join_lobby(int(data.get("lobby_id", 1)), user_id, user_name, position)
        if not result["ok"]:
            bot.send_message(message.chat.id, "⚠️ شما قبلاً عضو شده‌اید یا لابی پر است!", reply_markup=get_main_menu_keyboard(user_id))
            return
        lobby, members = result["lobby"], result["members"]
        members_text = "\n".join([f"  {i}. ✅ {m['player_name']} ({m['position']})" for i, m in enumerate(members, 1)])
        bot.send_message(
            message.chat.id,
            f"🎉 <b>تکمیل تیم از طریق مینی‌اپ گرافیکی!</b>\n\n"
            f"⚽ <b>{lobby['title']}</b>\n"
            f"🏃 پست انتخابی شما: <b>{position}</b>\n"
            f"👥 ظرفیت نهایی: <b>{lobby['current_players']}/{lobby['max_players']} نفر (تکمیل ✅)</b>\n\n"
            f"📋 <b>ترکیب نهایی زمین:</b>\n{members_text}",
            reply_markup=get_main_menu_keyboard(user_id)
        )

    elif action == "book_slot":
        db.submit_booking_receipt(int(data.get("slot_id", 1)), user_id, user_name, "WEBAPP_RECEIPT")
        bot.send_message(
            message.chat.id,
            f"✅ <b>درخواست رزرو سانس ({data.get('slot_title')}) از مینی‌اپ ثبت شد!</b>\n"
            f"💡 <i>برای تایید فیش در نقش مدیر سالن، دستور</i> /rule_Hallad <i>را ارسال کنید.</i>",
            reply_markup=get_main_menu_keyboard(user_id)
        )


if __name__ == "__main__":
    print("🚀 بات رزرو سالن و هم‌تیمی‌یابی با موفقیت روشن شد! در تلگرام /start را بزنید...")
    bot.infinity_polling(skip_pending=True)