import os
import json
import telebot
from telebot import types, apihelper
from dotenv import load_dotenv
import db  # ایمپورت کردن فایل دیتابیس کنار پروژه

# بارگذاری متغیرهای محیطی
load_dotenv()


def load_bot_token() -> str:
    """
    خواندن هوشمند توکن:
    این تابع ابتدا توکن شما را که از فایل Token.txt استخراج شده برمی‌گرداند.
    همچنین اگر فایل Token.txt را ویرایش کنید، به صورت خودکار پیشوندهایی مثل 'TestBot:' را حذف می‌کند.
    """
    default_token = "9106404923:AAHk4Kz0elPBr3BoeCr1tu1zvhFr2LA4ZHs"
    if os.path.exists("Token.txt"):
        try:
            with open("Token.txt", "r", encoding="utf-8") as f:
                raw = f.read().strip()
                # اگر عبارت دارای پیشوند مثل TestBot: باشد، فقط دو بخش آخر (آیدی و هش توکن) را برمی‌دارد
                parts = raw.split(":")
                if len(parts) >= 2:
                    return f"{parts[-2]}:{parts[-1]}"
        except Exception:
            pass
    return os.getenv("BOT_TOKEN", default_token)


# 🔑 ۱. توکن اختصاصی بات شما (جایگزین‌شده و آماده اجرا):
BOT_TOKEN = load_bot_token()

# 🌐 ۲. لینک HTTPS مربوط به فایل index.html مینی‌اپ:
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8000/index.html")

# 🛡️ ۳. تنظیم پروکسی برای عبور از فیلترینگ تلگرام در ایران:
# اگر فیلترشکن شما روی حالت Tun Mode یا System Proxy نیست، خط زیر را از کامنت خارج کنید (علامت # اول خط را بردارید) و پورت فیلترشکن خود را بنویسید:
apihelper.proxy = {'https': 'http://127.0.0.1:3067'}

# ساخت نمونه اصلی بات با پشتیبانی از تگ‌های HTML برای بولد کردن متن‌ها
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# راه‌اندازی خودکار دیتابیس و پر کردن دیتای دمو هنگام روشن شدن بات
db.init_db()
if not db.get_slots():
    db.reset_demo_data()


# =====================================================================
# توابع کمکی برای ساخت منوی اصلی و ویرایش بدون خطای پیام‌ها
# =====================================================================

def safe_edit_message(text: str, chat_id: int, message_id: int, reply_markup=None):
    """
    ویرایش پیام فعلی برای جلوگیری از شلوغ شدن صفحه چت.
    اگر کاربر دو بار روی یک دکمه کلیک کند، از بروز خطای تلگرام جلوگیری می‌کند.
    """
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


def get_main_menu_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    """ساخت دکمه‌های شیشه‌ای منوی اصلی با نمایش وضعیت لحظه‌ای کاربر و تعداد فیش‌های منتظر تایید"""
    user = db.upsert_user(user_id, "کاربر")
    avail_badge = "🟢 فعال" if user.get("is_available") else "⚪ غیرفعال"
    pending_count = len(db.get_pending_slots())
    pending_badge = f" ({pending_count} فیش جدید)" if pending_count > 0 else ""

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🏟 رزرو سانس سالن ورزشی", callback_data="menu_slots"),
        types.InlineKeyboardButton("🤝 لابی‌های تیم‌یابی امشب (تکمیل تیم)", callback_data="menu_lobbies"),
        types.InlineKeyboardButton("🔍 پیدا کردن یار کمکی (بازیکنان آماده)", callback_data="menu_players"),
        types.InlineKeyboardButton(f"⚡ وضعیت آمادگی من برای امشب: {avail_badge}", callback_data="menu_avail"),
        types.InlineKeyboardButton(f"⚙️ پنل اختصاصی مدیر سالن{pending_badge}", callback_data="menu_admin"),
        types.InlineKeyboardButton("🎛 ریست اطلاعات دمو (ویژه جلسه ارائه)", callback_data="demo_reset")
    )
    return kb


def get_main_menu_text(user_name: str) -> str:
    """متن خوش‌آمدگویی منوی اصلی"""
    return (
        f"👋 سلام <b>{user_name}</b> عزیز!\n"
        f"به سامانه هوشمند <b>رزرو سالن و هم‌تیمی‌یابی فوتسال</b> خوش آمدید.\n\n"
        f"🔹 <b>رزرو آنلاین سانس</b> با تایید آنی\n"
        f"🔹 <b>پیدا کردن یار کمکی</b> برای تیم‌های ناقص\n"
        f"🔹 <b>لابی‌های عمومی</b> برای هماهنگی افراد تکی\n\n"
        f"👇 لطفاً یکی از بخش‌های زیر را انتخاب کنید:"
    )


# =====================================================================
# هندلر دستور /start و دکمه ریست دمو
# =====================================================================

@bot.message_handler(commands=["start", "demo"])
def cmd_start(message: types.Message):
    """وقتی کاربر دستور /start را می‌زند، هم دکمه مینی‌اپ و هم منوی شیشه‌ای ارسال می‌شود"""
    user_name = message.from_user.first_name or "ورزشکار"
    db.upsert_user(message.from_user.id, user_name)

    # کیبورد پایین صفحه مخصوص باز کردن مینی‌اپ گرافیکی (Web App)
    webapp_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    webapp_kb.add(
        types.KeyboardButton(
            text="📱 باز کردن مینی‌اپ گرافیکی (چمن فوتسال و رزرو)",
            web_app=types.WebAppInfo(url=WEBAPP_URL)
        )
    )

    bot.send_message(
        message.chat.id,
        "✨ <b>نسخه مینی‌اپ گرافیکی فعال است!</b>\n"
        "می‌توانید از دکمه پایین صفحه نمای زمین فوتسال را باز کنید یا از منوی شیشه‌ای زیر استفاده نمایید:",
        reply_markup=webapp_kb
    )

    bot.send_message(
        message.chat.id,
        get_main_menu_text(user_name),
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )


@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def cb_main_menu(call: types.CallbackQuery):
    """بازگشت به منوی اصلی با کلیک روی دکمه بازگشت"""
    user_name = call.from_user.first_name or "ورزشکار"
    safe_edit_message(
        get_main_menu_text(user_name),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_main_menu_keyboard(call.from_user.id)
    )


@bot.callback_query_handler(func=lambda call: call.data == "demo_reset")
def cb_demo_reset(call: types.CallbackQuery):
    """ریست کامل دیتابیس به حالت اولیه برای تکرار سناریو در جلسه دمو"""
    db.reset_demo_data()
    user_name = call.from_user.first_name or "ورزشکار"
    db.upsert_user(call.from_user.id, user_name)
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
    """نمایش لیست سانس‌های سالن به همراه وضعیت هر سانس با رنگ‌بندی"""
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
    """نمایش پیغام هشدار در صورت کلیک روی سانس‌های پر"""
    bot.answer_callback_query(call.id, "⚠️ این سانس قبلاً رزرو شده یا در انتظار بررسی فیش است.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_select_"))
def cb_slot_select(call: types.CallbackQuery):
    """نمایش پیش‌فاکتور سانس انتخابی و دکمه ارسال فیش"""
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
    """ثبت فوری فیش فرضی با یک کلیک برای سرعت بخشیدن به جلسه ارائه دمو"""
    slot_id = int(call.data.split("_")[2])
    user_name = call.from_user.first_name or "سرگروه تیم"
    db.submit_booking_receipt(slot_id, call.from_user.id, user_name, "DEMO_FAST_RECEIPT")

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⚙️ رفتن مستقیم به پنل مدیر سالن برای تایید فیش", callback_data="admin_pending"),
        types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")
    )
    safe_edit_message(
        "✅ <b>فیش واریزی با موفقیت ثبت شد!</b>\n\n"
        "🟡 وضعیت سانس به <b>«در انتظار تایید مدیر سالن»</b> تغییر یافت.\n"
        "💡 <i>(نکته دمو: حالا دکمه زیر را بزنید تا در نقش مدیر سالن فیش را تایید کنید!)</i>",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("slot_upload_"))
def cb_slot_upload(call: types.CallbackQuery):
    """دریافت عکس یا متن فیش از کاربر با استفاده از register_next_step_handler"""
    slot_id = int(call.data.split("_")[2])
    msg = bot.send_message(call.message.chat.id, "📸 لطفاً تصویر فیش یا شماره پیگیری را ارسال کنید:")
    bot.register_next_step_handler(msg, process_receipt_step, slot_id)


def process_receipt_step(message: types.Message, slot_id: int):
    """ذخیره فیش ارسالی کاربر در دیتابیس"""
    user_name = message.from_user.first_name or "سرگروه تیم"
    receipt_info = message.photo[-1].file_id if message.content_type == "photo" else (message.text or "RECEIPT")
    db.submit_booking_receipt(slot_id, message.from_user.id, user_name, receipt_info)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    bot.send_message(message.chat.id, "✅ فیش شما دریافت و برای مدیر سالن ارسال شد.", reply_markup=kb)


# =====================================================================
# بخش ۲: اعلام آمادگی بازیکن و پیدا کردن یار کمکی (برای تیم‌های ناقص)
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_avail")
def cb_menu_avail(call: types.CallbackQuery):
    """منوی انتخاب پست تخصصی و روشن کردن چراغ آمادگی برای امشب"""
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
    """ثبت تغییر وضعیت آمادگی در دیتابیس"""
    parts = call.data.split("_")
    is_avail, position = int(parts[1]), parts[2]
    db.upsert_user(call.from_user.id, call.from_user.first_name or "بازیکن")
    db.update_user_availability(call.from_user.id, is_avail, position, "۲۰ تا ۲۴")
    bot.answer_callback_query(call.id, "✅ وضعیت آمادگی شما بروزرسانی شد!")
    cb_menu_avail(call)


@bot.callback_query_handler(func=lambda call: call.data == "menu_players")
def cb_menu_players(call: types.CallbackQuery):
    """نمایش لیست بازیکنانی که امشب آماده بازی هستند برای دعوت به عنوان یار کمکی"""
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
    """ارسال دعوت‌نامه به بازیکن انتخاب‌شده و نمایش شبیه‌سازی قبول دعوت در دمو"""
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
# بخش ۳: سیستم لابی‌های تیم‌یابی (جمع شدن افراد ناشناس و تکمیل ظرفیت)
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_lobbies")
def cb_menu_lobbies(call: types.CallbackQuery):
    """نمایش لیست لابی‌های باز امشب به همراه ظرفیت لحظه‌ای آن‌ها"""
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
    """نمایش جزئیات یک لابی و اسامی بازیکنان داخل آن"""
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
    """افزودن کاربر به لابی؛ اگر ظرفیت ۶ از ۶ شود پیام جشن تکمیل تیم را نمایش می‌دهد"""
    lobby_id = int(call.data.split("_")[2])
    user_name = call.from_user.first_name or "بازیکن جدید"
    result = db.join_lobby(lobby_id, call.from_user.id, user_name, "بازیکن آزاد ⚡")

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
    """منوی ساخت سریع لابی جدید"""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⚽ لابی ۶ نفره (تیم ۵ نفره داریم، ۱ یار کم)", callback_data="lobby_new_6_5"),
        types.InlineKeyboardButton("🏟 لابی ۱۲ نفره عمومی (جمع شدن افراد تکی)", callback_data="lobby_new_12_1"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_lobbies")
    )
    safe_edit_message("➕ <b>نوع لابی جدید را انتخاب کنید:</b>", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_new_"))
def cb_lobby_new_create(call: types.CallbackQuery):
    """ثبت لابی جدید در دیتابیس"""
    parts = call.data.split("_")
    max_p, init_p = int(parts[2]), int(parts[3])
    user_name = call.from_user.first_name or "سرگروه"
    title = f"لابی فوتسال {user_name} ({'۱ نفر کم' if init_p == 5 else 'عمومی'})"
    db.create_new_lobby(title, "امشب ساعت ۲۲:۳۰ تا ۲۴:۰۰", call.from_user.id, user_name, max_p, init_p)
    bot.answer_callback_query(call.id, "✅ لابی جدید با موفقیت ساخته شد!", show_alert=True)
    cb_menu_lobbies(call)


# =====================================================================
# بخش ۴: پنل اختصاصی مدیر سالن (تغییر وضعیت کلیکی، افزودن سانس و تایید فیش)
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_admin")
def cb_menu_admin(call: types.CallbackQuery):
    """منوی اصلی پنل مدیر سالن"""
    pending_count = len(db.get_pending_slots())
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🔄 باز و بسته کردن کلیکی سانس‌ها (🟢/🔴)", callback_data="admin_toggle_list"),
        types.InlineKeyboardButton(f"🧾 بررسی فیش‌های در انتظار تایید ({pending_count})", callback_data="admin_pending"),
        types.InlineKeyboardButton("➕ افزودن سریع سانس و قیمت جدید", callback_data="admin_add_day"),
        types.InlineKeyboardButton("📢 تبدیل سانس خالی مانده به لابی عمومی", callback_data="admin_slot_to_lobby"),
        types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu")
    )
    safe_edit_message(
        f"⚙️ <b>پنل مدیریت سالن ورزشی:</b>\n📥 فیش‌های منتظر بررسی: <b>{pending_count} مورد</b>",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data == "admin_toggle_list")
def cb_admin_toggle_list(call: types.CallbackQuery):
    """نمایش جدول کلیکی سانس‌ها برای باز یا بسته کردن فوری سانس‌های تلفنی توسط مدیر"""
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
    """تغییر وضعیت سانس در دیتابیس با یک کلیک"""
    slot_id = int(call.data.split("_")[2])
    db.toggle_slot_by_manager(slot_id)
    bot.answer_callback_query(call.id, "✅ وضعیت سانس تغییر کرد!")
    cb_admin_toggle_list(call)


@bot.callback_query_handler(func=lambda call: call.data == "admin_add_day")
def cb_admin_add_day(call: types.CallbackQuery):
    """گام اول افزودن سانس: انتخاب روز"""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📅 امروز", callback_data="addslot_day_امروز"),
        types.InlineKeyboardButton("📅 فردا", callback_data="addslot_day_فردا")
    )
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin"))
    safe_edit_message("➕ <b>گام ۱ از ۳:</b> روز سانس جدید را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addslot_day_"))
def cb_admin_add_time(call: types.CallbackQuery):
    """گام دوم افزودن سانس: انتخاب بازه زمانی"""
    day_label = call.data.split("_")[2]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for t in ["16:30 تا 18:00", "20:00 تا 21:30", "23:00 تا 00:30"]:
        kb.add(types.InlineKeyboardButton(f"🕒 {t}", callback_data=f"addslot_time_{day_label}_{t}"))
    safe_edit_message(f"➕ <b>گام ۲ از ۳ ({day_label}):</b> ساعت سانس را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addslot_time_"))
def cb_admin_add_price(call: types.CallbackQuery):
    """گام سوم افزودن سانس: انتخاب قیمت"""
    parts = call.data.split("_")
    day_label, time_range = parts[2], parts[3]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for price in [500000, 600000, 700000]:
        kb.add(types.InlineKeyboardButton(f"💳 {price:,} تومان", callback_data=f"addslot_save_{day_label}_{time_range}_{price}"))
    safe_edit_message("➕ <b>گام ۳ از ۳:</b> قیمت سانس را انتخاب کنید:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("addslot_save_"))
def cb_admin_save_slot(call: types.CallbackQuery):
    """ذخیره نهایی سانس جدید در دیتابیس"""
    parts = call.data.split("_")
    db.add_new_slot(parts[2], parts[3], int(parts[4]))
    bot.answer_callback_query(call.id, "✅ سانس جدید با موفقیت اضافه شد!", show_alert=True)
    cb_admin_toggle_list(call)


@bot.callback_query_handler(func=lambda call: call.data == "admin_pending")
def cb_admin_pending(call: types.CallbackQuery):
    """نمایش فیش‌های در انتظار تایید به مدیر سالن"""
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
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("verify_"))
def cb_admin_verify(call: types.CallbackQuery):
    """تایید یا رد کردن فیش توسط مدیر و ارسال پیام خودکار به مشتری"""
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
    """تبدیل یک سانس خالی مانده سالن به لابی عمومی ۱۲ نفره"""
    free_slots = [s for s in db.get_slots() if s["status"] == "free"]
    kb = types.InlineKeyboardMarkup(row_width=1)
    for s in free_slots:
        kb.add(types.InlineKeyboardButton(f"📢 تبدیل به لابی: {s['day_label']} ({s['time_range']})", callback_data=f"convlobby_{s['id']}"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin"))
    safe_edit_message("📢 روی سانس خالی کلیک کنید تا به لابی ۱۲ نفره تبدیل شود:", call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("convlobby_"))
def cb_convert_slot_to_lobby(call: types.CallbackQuery):
    """ثبت لابی ۱۲ نفره برای سانس خالی انتخاب‌شده"""
    slot = db.get_slot_by_id(int(call.data.split("_")[1]))
    if slot:
        db.create_new_lobby(f"سانس ویژه ({slot['day_label']})", f"{slot['day_label']} {slot['time_range']}", call.from_user.id, "مدیر سالن", 12, 0)
        bot.answer_callback_query(call.id, "✅ لابی ۱۲ نفره ساخته شد!", show_alert=True)
    cb_menu_lobbies(call)


# =====================================================================
# بخش ۵: دریافت اطلاعات ارسالی از مینی‌اپ گرافیکی (index.html)
# =====================================================================

@bot.message_handler(content_types=["web_app_data"])
def handle_webapp_response(message: types.Message):
    """وقتی کاربر داخل مینی‌اپ روی جای خالی زمین یا سانس کلیک می‌کند، JSON آن اینجا دریافت می‌شود"""
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    user_id = message.from_user.id
    user_name = message.from_user.first_name or "بازیکن مینی‌اپ"
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
            f"✅ <b>درخواست رزرو سانس ({data.get('slot_title')}) از مینی‌اپ ثبت شد و به پنل مدیر سالن رفت!</b>",
            reply_markup=get_main_menu_keyboard(user_id)
        )


if __name__ == "__main__":
    print("🚀 بات رزرو سالن و هم‌تیمی‌یابی با موفقیت روشن شد! در تلگرام /start را بزنید...")
    bot.infinity_polling(skip_pending=True)