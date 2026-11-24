import json
from typing import Optional
from telebot import types

import config
import db
from bot_instance import (
    bot, esc, is_admin, is_support, can_moderate,
    get_all_support_ids, notify_admins, check_not_banned,
    safe_edit_message, normalize_digits
)
from keyboards import get_main_menu_keyboard, get_main_menu_text, get_webapp_reply_keyboard
from handlers.lobby import initiate_lobby_join_request


def _extract_target_id(text: str) -> Optional[int]:
    """استخراج آیدی عددی از فرمت‌هایی مثل '/ban 123456' یا '/ban user 123456'"""
    parts = (text or "").split()
    for token in parts[1:]:
        cleaned = normalize_digits(token)
        if cleaned.isdigit():
            return int(cleaned)
    return None


@bot.message_handler(commands=["admin"])
def cmd_admin_help(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "👑 <b>پنل دستورات مدیر کامل:</b>\n\n"
        "📊 <code>/stats</code> — آمار زنده دیتابیس\n"
        "👥 <code>/users</code> — مشاهده لیست کاربران واقعی + شماره تماس\n"
        "🗑 <code>/deluser آیدی</code> — حذف کامل یک کاربر (همراه با تاییدیه)\n"
        "💡 <code>/feedbacks</code> — مشاهده بازخوردهای کاربران\n"
        "🚨 <code>/reports</code> — مشاهده گزارش‌های تخلف و شواهد\n"
        "🚫 <code>/ban آیدی</code> | ✅ <code>/unban آیدی</code> — مسدود/رفع مسدودیت\n\n"
        "🛡️ <b>مدیریت تیم پشتیبانی:</b>\n"
        "➕ <code>/addsupport آیدی</code> — افزودن پشتیبان جدید\n"
        "➖ <code>/delsupport آیدی</code> — حذف پشتیبان\n"
        "📋 <code>/staff</code> — لیست مدیران و پشتیبان‌ها\n\n"
        "🌐 <i>پنل گرافیکی کامل دیتابیس (Adminer):</i>\n"
        "<code>docker compose --profile tools up -d</code> ⬅️ <code>http://localhost:8080</code>"
    )


@bot.message_handler(commands=["support"])
def cmd_support_help(message: types.Message):
    if not can_moderate(message.from_user.id):
        return
    bot.send_message(
        message.chat.id,
        "🛡️ <b>پنل دستورات پشتیبان:</b>\n\n"
        "🚨 <code>/reports</code> — مشاهده ۱۵ گزارش تخلف آخر به همراه شواهد\n"
        "🚫 <code>/ban آیدی</code> (یا <code>/ban user آیدی</code>) — مسدود کردن کاربر متخلف\n"
        "✅ <code>/unban آیدی</code> — رفع مسدودیت کاربر"
    )


@bot.message_handler(commands=["stats"])
def cmd_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    s = db.get_bot_stats()
    bot.send_message(
        message.chat.id,
        f"📊 <b>آمار زنده سامانه تیم‌یابی (PostgreSQL):</b>\n\n"
        f"👥 کاربران واقعی ثبت‌نام‌شده: <b>{s['real_users']}</b>\n"
        f"🟢 بازیکنان واقعی آماده بازی: <b>{s['real_available']}</b>\n"
        f"🏟 لابی‌های فعال کاربران: <b>{s['real_open_lobbies']}</b> | تکمیل‌شده: <b>{s['real_full_lobbies']}</b>\n"
        f"💬 چت‌های ناشناس فعال اکنون: <b>{s['active_chats']}</b>\n"
        f"💡 کل بازخوردهای دریافتی: <b>{s['total_feedbacks']}</b>\n"
        f"🚨 گزارش‌های تخلف ثبت‌شده: <b>{s['total_reports']}</b>"
    )


@bot.message_handler(commands=["users"])
def cmd_users_list(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    users = db.get_all_real_users(50)
    if not users:
        bot.send_message(message.chat.id, "ℹ️ هنوز هیچ کاربر واقعی در دیتابیس ثبت نشده است.")
        return

    chunks = []
    current = f"👥 <b>لیست کاربران واقعی دیتابیس ({len(users)} نفر آخر):</b>\n\n"
    for idx, u in enumerate(users, start=1):
        ban_badge = " 🚫<b>[مسدود]</b>" if u["is_banned"] else ""
        avail_badge = " 🟢" if u["is_available"] else ""
        entry = (
            f"{idx}. 👤 <b>{esc(u['full_name'])}</b>{avail_badge}{ban_badge}\n"
            f"   🆔 <code>{u['user_id']}</code> | 📞 <code>{esc(u.get('phone') or 'ثبت نشده')}</code>\n"
            f"   ⚽ {esc(u['position'])} | ⭐ {esc(u['skill_level'])}\n"
            f"   🗑 حذف: <code>/deluser {u['user_id']}</code>\n\n"
        )
        if len(current) + len(entry) > 3800:
            chunks.append(current)
            current = entry
        else:
            current += entry

    if current:
        chunks.append(current)

    for part in chunks:
        bot.send_message(message.chat.id, part)


# =====================================================================
# حذف کاربر همراه با مرحله تایید دوگانه و اطلاع به طرف چت
# =====================================================================

@bot.message_handler(commands=["deluser"])
def cmd_delete_user(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    target_id = _extract_target_id(message.text)
    if target_id is None:
        bot.send_message(message.chat.id, "⚠️ فرمت صحیح:\n<code>/deluser 5166475125</code>")
        return

    if is_admin(target_id):
        bot.send_message(message.chat.id, "⛔ امکان حذف اکانت مدیر کامل وجود ندارد.")
        return

    user = db.get_user_by_id(target_id)
    if not user:
        bot.send_message(message.chat.id, f"⚠️ کاربری با شناسه <code>{target_id}</code> در دیتابیس یافت نشد.")
        return

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🗑 بله، حذف کامل شود", callback_data=f"confirm_deluser_{target_id}"),
        types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_deluser")
    )
    bot.send_message(
        message.chat.id,
        f"⚠️ <b>تایید حذف کامل کاربر از دیتابیس:</b>\n\n"
        f"👤 نام: <b>{esc(user['full_name'])}</b>\n"
        f"🆔 شناسه: <code>{target_id}</code>\n"
        f"📞 شماره: <code>{esc(user.get('phone') or 'ثبت نشده')}</code>\n\n"
        f"آیا از حذف کامل این کاربر مطمئن هستید؟",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_deluser")
def cb_cancel_deluser(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    bot.answer_callback_query(call.id, "عملیات لغو شد.")
    safe_edit_message("❌ عملیات حذف کاربر لغو شد.", call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_deluser_"))
def cb_confirm_deluser(call: types.CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split("_")[2])
    if is_admin(target_id):
        bot.answer_callback_query(call.id, "⛔ امکان حذف مدیر وجود ندارد.", show_alert=True)
        return

    # اطلاع‌رسانی به طرف مقابل در صورت داشتن چت فعال قبل از حذف
    active_chat = db.end_active_chat(target_id)
    if active_chat and active_chat["partner_id"] >= 1000:
        try:
            bot.send_message(
                active_chat["partner_id"],
                "🔴 چت ناشناس به دلیل حذف حساب طرف مقابل توسط مدیریت پایان یافت.",
                reply_markup=get_webapp_reply_keyboard()
            )
            bot.send_message(
                active_chat["partner_id"],
                get_main_menu_text(active_chat["partner_id"]),
                reply_markup=get_main_menu_keyboard(active_chat["partner_id"])
            )
        except Exception:
            pass

    deleted = db.delete_user_completely(target_id)
    if deleted:
        bot.answer_callback_query(call.id, "🗑 کاربر حذف شد.")
        safe_edit_message(
            f"🗑 <b>کاربر با موفقیت از دیتابیس حذف شد:</b>\n"
            f"👤 {esc(deleted['full_name'])} | ID: <code>{target_id}</code>\n"
            f"📞 <code>{esc(deleted.get('phone') or 'ثبت نشده')}</code>",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, "کاربر یافت نشد.")
        safe_edit_message("⚠️ این کاربر قبلاً حذف شده است.", call.message.chat.id, call.message.message_id)


# =====================================================================
# مدیریت پشتیبان‌ها و مشاهده گزارش‌ها / بازخوردها
# =====================================================================

@bot.message_handler(commands=["addsupport", "delsupport"])
def cmd_manage_support(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    target_id = _extract_target_id(message.text)
    if target_id is None:
        bot.send_message(
            message.chat.id,
            "⚠️ فرمت صحیح:\n<code>/addsupport 123456789</code>\n<code>/delsupport 123456789</code>"
        )
        return

    if message.text.lower().startswith("/addsupport"):
        added = db.add_support_agent(target_id, message.from_user.id)
        if added or target_id in config.SUPPORT_IDS:
            bot.send_message(
                message.chat.id,
                f"✅ کاربر <code>{target_id}</code> به تیم <b>پشتیبانی</b> اضافه شد.\n"
                f"از این پس گزارش‌های تخلف همراه با شواهد ۵ پیام آخر برای او ارسال می‌شود."
            )
            try:
                bot.send_message(
                    target_id,
                    "🛡️ <b>شما به عنوان پشتیبان سامانه تیم‌یابی انتخاب شدید!</b>\n"
                    "برای مشاهده دستورات پشتیبانی دستور /support را بزنید."
                )
            except Exception:
                pass
        else:
            bot.send_message(message.chat.id, f"ℹ️ کاربر <code>{target_id}</code> قبلاً در لیست پشتیبان‌ها بوده است.")
    else:
        removed = db.remove_support_agent(target_id)
        if target_id in config.SUPPORT_IDS:
            bot.send_message(
                message.chat.id,
                f"⚠️ شناسه <code>{target_id}</code> در فایل <code>.env</code> (SUPPORT_IDS) نیز ثبت است؛ برای حذف کامل، آن را از <code>.env</code> هم بردارید."
            )
        elif removed:
            bot.send_message(message.chat.id, f"🗑 کاربر <code>{target_id}</code> از لیست پشتیبان‌ها حذف شد.")
        else:
            bot.send_message(message.chat.id, f"⚠️ کاربر <code>{target_id}</code> در لیست پشتیبان‌ها نبود.")


@bot.message_handler(commands=["staff"])
def cmd_staff_list(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    admins_lines = []
    for aid in sorted(config.ADMIN_IDS):
        u = db.get_user_by_id(aid)
        name = esc(u["full_name"]) if u else "ثبت‌نام نشده"
        admins_lines.append(f"  👑 <code>{aid}</code> — {name}")

    support_ids = sorted(get_all_support_ids())
    support_lines = []
    for sid in support_ids:
        u = db.get_user_by_id(sid)
        name = esc(u["full_name"]) if u else "ثبت‌نام نشده"
        src = " (.env)" if sid in config.SUPPORT_IDS else ""
        support_lines.append(f"  🛡️ <code>{sid}</code> — {name}{src}")

    admins_txt = "\n".join(admins_lines) if admins_lines else "  (تعریف نشده)"
    support_txt = "\n".join(support_lines) if support_lines else "  (هنوز پشتیبانی اضافه نشده — با /addsupport اضافه کنید)"

    bot.send_message(
        message.chat.id,
        f"📋 <b>لیست مدیران و پشتیبان‌های سامانه:</b>\n\n"
        f"<b>مدیران کامل:</b>\n{admins_txt}\n\n"
        f"<b>پشتیبان‌ها:</b>\n{support_txt}"
    )


@bot.message_handler(commands=["feedbacks"])
def cmd_feedbacks(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    items = db.get_recent_feedbacks(15)
    if not items:
        bot.send_message(message.chat.id, "ℹ️ هنوز هیچ بازخوردی ثبت نشده است.")
        return

    lines = ["💡 <b>آخرین بازخوردهای کاربران واقعی:</b>\n"]
    for f in items:
        lines.append(
            f"🔹 <b>{esc(f['user_name'])}</b> (<code>{f['user_id']}</code>) | <i>{f['created_str']}</i>\n"
            f"   {esc(f['message'])}\n"
        )
    bot.send_message(message.chat.id, "\n".join(lines))


@bot.message_handler(commands=["reports"])
def cmd_reports(message: types.Message):
    if not can_moderate(message.from_user.id):
        return
    items = db.get_recent_reports(10)
    if not items:
        bot.send_message(message.chat.id, "ℹ️ هنوز هیچ گزارش تخلفی ثبت نشده است.")
        return

    lines = ["🚨 <b>آخرین گزارش‌های تخلف ثبت‌شده:</b>\n"]
    for r in items:
        status_tag = "🚫 مسدود شده" if r["reported_is_banned"] else "⚠️ فعال"
        ev = f"\n   📜 <b>شواهد:</b>\n{esc(r['evidence'])}" if r.get("evidence") else ""
        lines.append(
            f"🔹 گزارش <b>#{r['id']}</b> | <i>{r['created_str']}</i> | {status_tag}\n"
            f"   گزارش‌دهنده: {esc(r['reporter_name'])} (<code>{r['reporter_id']}</code>)\n"
            f"   متخلف: <b>{esc(r['reported_name'])}</b> (<code>{r['reported_id']}</code>)\n"
            f"   دستور سریع: <code>/ban {r['reported_id']}</code>{ev}\n"
        )
    full_text = "\n".join(lines)
    for start in range(0, len(full_text), 3800):
        bot.send_message(message.chat.id, full_text[start:start + 3800])


@bot.message_handler(commands=["ban", "unban"])
def cmd_ban_unban(message: types.Message):
    actor_id = message.from_user.id
    if not can_moderate(actor_id):
        return

    target_id = _extract_target_id(message.text)
    if target_id is None:
        bot.send_message(
            message.chat.id,
            "⚠️ فرمت صحیح:\n<code>/ban 123456789</code> یا <code>/ban user 123456789</code>\n<code>/unban 123456789</code>"
        )
        return

    ban_flag = message.text.lower().startswith("/ban")

    if ban_flag:
        if is_admin(target_id):
            bot.send_message(message.chat.id, "⛔ امکان مسدود کردن مدیر کامل وجود ندارد.")
            return
        if is_support(target_id) and not is_admin(actor_id):
            bot.send_message(message.chat.id, "⛔ پشتیبان نمی‌تواند پشتیبان دیگر را مسدود کند.")
            return

    ok = db.set_user_ban(target_id, ban_flag)
    if ok:
        if ban_flag:
            ended = db.end_active_chat(target_id)
            if ended and ended["partner_id"] >= 1000:
                try:
                    bot.send_message(
                        ended["partner_id"],
                        "🔴 چت ناشناس توسط تیم پشتیبانی پایان یافت.",
                        reply_markup=get_webapp_reply_keyboard()
                    )
                except Exception:
                    pass

        status_lbl = "مسدود (Ban)" if ban_flag else "رفع مسدودیت (Unban)"
        bot.send_message(message.chat.id, f"✅ کاربر <code>{target_id}</code> با موفقیت {status_lbl} شد.")

        if not is_admin(actor_id):
            actor = db.get_user_by_id(actor_id)
            actor_name = esc(actor["full_name"]) if actor else str(actor_id)
            notify_admins(
                f"🛡️ <b>اقدام پشتیبان ({actor_name} - <code>{actor_id}</code>):</b>\n"
                f"کاربر <code>{target_id}</code> را <b>{status_lbl}</b> کرد."
            )
    else:
        bot.send_message(message.chat.id, "⚠️ کاربری با این شناسه در دیتابیس یافت نشد.")


# =====================================================================
# منوی اصلی، ثبت بازخورد (DB-Backed FSM) و دریافت داده مینی‌اپ
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def cb_main_menu(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    db.clear_user_state(call.from_user.id)
    fallback_name = call.from_user.first_name or "ورزشکار"
    safe_edit_message(
        get_main_menu_text(call.from_user.id, fallback_name),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_main_menu_keyboard(call.from_user.id)
    )


@bot.callback_query_handler(func=lambda call: call.data == "demo_reset")
def cb_demo_reset(call: types.CallbackQuery):
    if config.ADMIN_IDS and not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ فقط مدیر کامل اجازه ریست دیتای نمونه را دارد.", show_alert=True)
        return
    db.reset_demo_data()
    bot.answer_callback_query(call.id, "♻️ فقط دیتای نمونه تست ریست شد (کاربران واقعی حفظ شدند).", show_alert=True)
    cb_main_menu(call)


@bot.callback_query_handler(func=lambda call: call.data == "menu_feedback")
def cb_menu_feedback(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    db.set_user_state(call.from_user.id, "feedback_wait", {})
    bot.send_message(
        call.message.chat.id,
        "💡 <b>ارسال بازخورد و پیشنهاد:</b>\n\n"
        "هر نظر، باگ یا پیشنهادی درباره ربات تیم‌یابی دارید در یک پیام بنویسید و بفرستید (برای انصراف /cancel بزنید):"
    )


def handle_feedback_step(message: types.Message):
    user_id = message.from_user.id
    if message.content_type != "text" or not (message.text or "").strip():
        bot.send_message(message.chat.id, "⚠️ لطفاً بازخورد خود را به صورت متن ارسال کنید (یا /cancel بزنید):")
        return

    user = db.upsert_user(user_id, message.from_user.first_name or "ورزشکار")
    text = message.text.strip()[:1000]
    fb_id = db.save_feedback(user_id, user["full_name"], text)
    db.clear_user_state(user_id)

    notify_admins(
        f"💡 <b>بازخورد جدید (#{fb_id}):</b>\n"
        f"👤 {esc(user['full_name'])} (<code>{user_id}</code>)\n"
        f"📝 {esc(text)}"
    )
    bot.send_message(
        message.chat.id,
        "🙏 <b>ممنون از بازخورد ارزشمند شما!</b>\nپیام شما با موفقیت ثبت شد.",
        reply_markup=get_main_menu_keyboard(user_id)
    )


@bot.message_handler(content_types=["web_app_data"])
def handle_webapp_response(message: types.Message):
    if not check_not_banned(message.from_user.id, message.chat.id):
        return
    try:
        data = json.loads(message.web_app_data.data)
    except Exception:
        return

    user_id = message.from_user.id
    db.upsert_user(user_id, message.from_user.first_name or "بازیکن مینی‌اپ")

    if data.get("action") == "join_lobby":
        lobby_id = int(data.get("lobby_id", 1))
        chosen_position = data.get("position")
        initiate_lobby_join_request(
            requester_id=user_id,
            chat_id=message.chat.id,
            lobby_id=lobby_id,
            requested_position=chosen_position
        )
