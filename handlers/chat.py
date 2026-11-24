import random
from telebot import types

import config
import db
from bot_instance import (
    bot, logger, esc, notify_support, check_not_banned,
    safe_edit_message, chat_rate_limiter
)
from keyboards import (
    get_webapp_reply_keyboard,
    get_in_chat_reply_keyboard,
    get_main_menu_keyboard,
    get_main_menu_text,
)
from handlers.lobby import (
    approve_lobby_membership,
    handle_lobby_count_step,
    handle_lobby_area_step,
    handle_lobby_time_step,
)
from handlers.registration import (
    handle_reg_name_step,
    handle_reg_phone_step,
    handle_edit_name_step,
    handle_edit_phone_step,
)
from handlers.admin import handle_feedback_step


# =====================================================================
# بخش وضعیت آمادگی امشب (بدون تغییر روی پست‌های اصلی پروفایل)
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "menu_avail")
def cb_menu_avail(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    user = db.upsert_user(call.from_user.id, call.from_user.first_name or "بازیکن")
    status_str = "🟢 آماده بازی امشب" if user["is_available"] else "⚪ غیرفعال"
    tonight_pos = user.get("tonight_position") or user.get("position") or "آزاد"

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧤 دروازه‌بان", callback_data="setavail_1_دروازه‌بان 🧤"),
        types.InlineKeyboardButton("🛡️ دفاع / عقب‌گیر", callback_data="setavail_1_دفاع 🛡️"),
        types.InlineKeyboardButton("⚡ مهاجم", callback_data="setavail_1_مهاجم ⚡"),
        types.InlineKeyboardButton("🏃 بازیکن آزاد", callback_data="setavail_1_بازیکن آزاد 🏃")
    )
    kb.add(types.InlineKeyboardButton("🔴 خاموش کردن وضعیت آمادگی", callback_data="setavail_0_"))
    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))

    text = (
        f"⚡ <b>وضعیت آمادگی من برای امشب:</b>\n\n"
        f"وضعیت فعلی: <b>{status_str}</b> | پست امشب: <b>{esc(tonight_pos)}</b>\n"
        f"<i>(تغییر این بخش هیچ تغییری روی پست‌های دائمی پروفایل شما نمی‌دهد)</i>\n\n"
        f"با روشن کردن آمادگی، در لیست یار کمکی نمایش داده می‌شوید:"
    )
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("setavail_"))
def cb_set_avail(call: types.CallbackQuery):
    parts = call.data.split("_", 2)
    is_avail = int(parts[1])
    tonight_pos = parts[2] if len(parts) > 2 and parts[2] else None
    db.upsert_user(call.from_user.id, call.from_user.first_name or "بازیکن")
    db.update_user_availability(call.from_user.id, is_avail, tonight_pos, "۲۰ تا ۲۴")
    bot.answer_callback_query(call.id, "✅ وضعیت آمادگی امشب شما بروزرسانی شد!")
    cb_menu_avail(call)


@bot.callback_query_handler(func=lambda call: call.data == "menu_players")
def cb_menu_players(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    current_uid = call.from_user.id
    players = db.get_available_players(viewer_id=current_uid)
    kb = types.InlineKeyboardMarkup(row_width=1)

    text = "🔍 <b>لیست بازیکنان آماده امشب (یار کمکی):</b>\n🔒 <i>بدون نمایش شماره یا آیدی — چت مستقیم داخل ربات</i>\n\n"
    for idx, p in enumerate(players, start=1):
        is_me = (p["user_id"] == current_uid)
        if is_me:
            tag = " <b>(شما)</b>"
        elif p["user_id"] < 1000:
            tag = " <i>(نمونه تست)</i>"
        else:
            tag = " 🟢 <i>(بازیکن واقعی)</i>"

        display_pos = p.get("tonight_position") or p.get("position") or "آزاد"
        text += (
            f"{idx}. 👤 <b>{esc(p['full_name'])}</b>{tag} | پست: {esc(display_pos)}\n"
            f"   ⭐ سطح: {esc(p['skill_level'])} | 🕒 ساعت آزاد: {esc(p['free_hours'])}\n\n"
        )
        if not is_me:
            kb.add(types.InlineKeyboardButton(
                f"💬 درخواست چت ناشناس با {p['full_name']}",
                callback_data=f"chat_req_{p['user_id']}"
            ))

    kb.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


# =====================================================================
# درخواست، تایید اتمیک و مدیریت چت ناشناس + بلاک کاربر به کاربر
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_req_"))
def cb_request_anonymous_chat(call: types.CallbackQuery):
    requester_id = call.from_user.id
    if not check_not_banned(requester_id, call.message.chat.id):
        return
    target_id = int(call.data.split("_")[2])

    if requester_id == target_id:
        bot.answer_callback_query(call.id, "⚠️ نمی‌توانید با خودتان چت کنید!", show_alert=True)
        return

    if db.get_active_chat(requester_id):
        bot.answer_callback_query(call.id, "⚠️ شما هم‌اکنون در یک چت فعال هستید! ابتدا با /endchat آن را ببندید.", show_alert=True)
        return

    if db.is_blocked_between(requester_id, target_id):
        bot.answer_callback_query(call.id, "⛔ امکان ارسال درخواست چت به این بازیکن وجود ندارد.", show_alert=True)
        return

    if db.has_pending_chat_between(requester_id, target_id):
        bot.answer_callback_query(call.id, "⏳ درخواست قبلی شما برای این بازیکن هنوز در انتظار پاسخ است.", show_alert=True)
        return

    requester = db.upsert_user(requester_id, call.from_user.first_name or "بازیکن")
    target = db.get_user_by_id(target_id)
    if not target or target.get("is_banned"):
        bot.answer_callback_query(call.id, "⚠️ بازیکن مورد نظر در دسترس نیست.", show_alert=True)
        return

    if target_id < 1000:
        db.create_chat_session(requester_id, target_id, auto_accept=True)
        bot.answer_callback_query(call.id, "✅ چت ناشناس متصل شد!")
        bot.send_message(
            call.message.chat.id,
            f"🟢 <b>اتصال به چت ناشناس برقرار شد!</b> (بازیکن نمونه تست)\n\n"
            f"👤 طرف مقابل: <b>{esc(target['full_name'])}</b> ({esc(target['position'])})\n"
            f"🔒 <i>آیدی و شماره تماس هیچ‌کدام از دو طرف نمایش داده نمی‌شود.</i>\n\n"
            f"✍️ پیام خود را همین‌جا بفرستید:",
            reply_markup=get_in_chat_reply_keyboard()
        )
        return

    if db.get_active_chat(target_id):
        bot.answer_callback_query(call.id, "⏳ این بازیکن در حال حاضر مشغول چت با شخص دیگری است.", show_alert=True)
        return

    session_id = db.create_chat_session(requester_id, target_id, auto_accept=False)

    invite_kb = types.InlineKeyboardMarkup(row_width=2)
    invite_kb.add(
        types.InlineKeyboardButton("✅ قبول و شروع چت", callback_data=f"chat_acc_{session_id}"),
        types.InlineKeyboardButton("❌ رد درخواست", callback_data=f"chat_rej_{session_id}")
    )

    try:
        bot.send_message(
            target_id,
            f"📩 <b>درخواست چت و هماهنگی بازی جدید!</b>\n\n"
            f"👤 بازیکن: <b>{esc(requester['full_name'])}</b>\n"
            f"⚽ پست: {esc(requester['position'])} | ⭐ سطح: {esc(requester['skill_level'])}\n\n"
            f"🔒 <i>در صورت قبول، چت به‌صورت ناشناس داخل همین ربات (بدون نمایش آیدی و شماره) آغاز می‌شود:</i>",
            reply_markup=invite_kb
        )
        bot.answer_callback_query(call.id, "📨 درخواست چت ارسال شد!")
        kb_back = types.InlineKeyboardMarkup()
        kb_back.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="main_menu"))
        safe_edit_message(
            f"📨 <b>درخواست چت ناشناس برای «{esc(target['full_name'])}» ارسال شد!</b>\n\n"
            f"⏳ به محض اینکه درخواست شما را تایید کند، هر دو طرف به‌طور خودکار در همین ربات به هم متصل می‌شوید.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb_back
        )
    except Exception:
        db.reject_chat_session_atomic(session_id, target_id)
        bot.answer_callback_query(call.id, "⚠️ امکان ارسال پیام به این بازیکن وجود ندارد.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_acc_"))
def cb_accept_chat(call: types.CallbackQuery):
    session_id = int(call.data.split("_")[2])
    res = db.accept_chat_session_atomic(session_id, call.from_user.id)

    if not res["ok"]:
        reason = res["reason"]
        if reason == "unauthorized":
            bot.answer_callback_query(call.id, "⛔ شما گیرنده این درخواست نیستید.", show_alert=True)
        elif reason == "busy":
            bot.answer_callback_query(call.id, "⚠️ یکی از دو طرف هم‌اکنون در چت فعال دیگری است.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "⚠️ این درخواست منقضی شده یا قبلاً پاسخ داده شده است.", show_alert=True)
        return

    session = res["session"]
    u1, u2 = session["user1_id"], session["user2_id"]
    user1, user2 = res["user1"], res["user2"]
    can_approve = res["can_approve"]
    lobby_id = res["lobby_id"]
    lobby_title = res["lobby_title"]

    bot.answer_callback_query(call.id, "🟢 چت متصل شد!")
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass

    u1_pos = user1.get("tonight_position") or user1.get("position") or "آزاد"
    u2_pos = user2.get("tonight_position") or user2.get("position") or "آزاد"

    if can_approve:
        bot.send_message(
            u2,
            f"🟢 <b>چت ناشناس با متقاضی عضویت «{esc(user1['full_name'])}» ({esc(u1_pos)}) آغاز شد!</b>\n"
            f"🏟 لابی: <b>{esc(lobby_title)}</b>\n\n"
            f"🔒 آیدی و شماره شما مخفی است.\n"
            f"✅ هر زمان پس از گفت‌وگو به توافق رسیدید، دکمه <b>«✅ تایید عضویت در لابی»</b> را بزنید:",
            reply_markup=get_in_chat_reply_keyboard(can_approve_lobby=True)
        )
        inline_approve = types.InlineKeyboardMarkup()
        inline_approve.add(types.InlineKeyboardButton(
            f"✅ تایید عضویت {user1['full_name']} در لابی",
            callback_data=f"lobby_approve_{lobby_id}_{u1}"
        ))
        bot.send_message(
            u2,
            f"👇 همچنین می‌توانید هر لحظه از دکمه زیر برای تایید عضویت <b>{esc(user1['full_name'])}</b> استفاده کنید:",
            reply_markup=inline_approve
        )
    else:
        bot.send_message(
            u2,
            f"🟢 <b>چت ناشناس با «{esc(user1['full_name'])}» ({esc(u1_pos)}) آغاز شد!</b>\n"
            f"🔒 آیدی و شماره شما مخفی است. پیام خود را بنویسید (برای خروج دکمه پایین صفحه را بزنید):",
            reply_markup=get_in_chat_reply_keyboard(can_approve_lobby=False)
        )

    try:
        extra_note = f"\n🏟 پس از هماهنگی، سرگروه عضویت شما را در لابی <b>{esc(lobby_title)}</b> تایید خواهد کرد." if can_approve else ""
        bot.send_message(
            u1,
            f"🟢 <b>«{esc(user2['full_name'])}» ({esc(u2_pos)}) درخواست چت شما را قبول کرد!</b>\n"
            f"🔒 چت ناشناس داخل ربات فعال شد.{extra_note}\n"
            f"✍️ پیام خود را همین‌جا ارسال کنید:",
            reply_markup=get_in_chat_reply_keyboard(can_approve_lobby=False)
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("chat_rej_"))
def cb_reject_chat(call: types.CallbackQuery):
    session_id = int(call.data.split("_")[2])
    res = db.reject_chat_session_atomic(session_id, call.from_user.id)

    if not res["ok"]:
        if res["reason"] == "unauthorized":
            bot.answer_callback_query(call.id, "⛔ شما گیرنده این درخواست نیستید.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "این درخواست قبلاً بررسی یا منقضی شده است.")
        return

    safe_edit_message("❌ درخواست رد شد.", call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(
            res["requester_id"],
            f"❌ <b>{esc(res['target_name'])}</b> در حال حاضر درخواست شما را رد کرد.",
            reply_markup=get_main_menu_keyboard(res["requester_id"])
        )
    except Exception:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("block_user_"))
def cb_block_user(call: types.CallbackQuery):
    target_id = int(call.data.split("_")[2])
    if target_id < 1000:
        bot.answer_callback_query(call.id, "ℹ️ بازیکنان نمونه تست قابل بلاک نیستند.", show_alert=True)
        return
    db.block_user(call.from_user.id, target_id)
    bot.answer_callback_query(call.id, "🔕 این کاربر برای شما مسدود شد و دیگر نمی‌تواند درخواست چت بفرستد.", show_alert=True)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    except Exception:
        pass


@bot.message_handler(commands=["endchat"])
def cmd_end_chat(message: types.Message):
    end_chat_for_user(message.from_user.id, message.chat.id, message.from_user.first_name or "بازیکن")


def end_chat_for_user(user_id: int, chat_id: int, fallback_name: str, reported: bool = False):
    user = db.upsert_user(user_id, fallback_name)
    ended = db.end_active_chat(user_id, keep_messages=reported)

    if not ended:
        bot.send_message(chat_id, "ℹ️ شما در حال حاضر در هیچ چت فعالی نیستید.", reply_markup=get_webapp_reply_keyboard())
        bot.send_message(chat_id, get_main_menu_text(user_id, fallback_name), reply_markup=get_main_menu_keyboard(user_id))
        return

    partner_id = ended["partner_id"]
    if reported:
        recent_msgs = db.get_recent_session_messages(ended["session_id"], limit=5)
        if recent_msgs:
            evidence_lines = [
                f"[{m['time_str']}] {m['sender_name']} ({m['sender_id']}): {m['content']}"
                for m in recent_msgs
            ]
            evidence_text = "\n".join(evidence_lines)
        else:
            evidence_text = "(هنوز پیامی ردوبدل نشده بود)"

        rep_id = db.create_report(
            ended["session_id"],
            user_id,
            partner_id,
            reason="مزاحمت در چت ناشناس",
            evidence=evidence_text
        )
        # پاک‌سازی بافر پیام پس از ثبت در گزارش
        db.purge_session_messages(ended["session_id"])

        # مسدودسازی خودکار طرف مقابل برای گزارش‌دهنده
        if partner_id >= 1000:
            db.block_user(user_id, partner_id)

        notify_support(
            f"🚨 <b>گزارش تخلف جدید (#{rep_id}):</b>\n"
            f"گزارش‌دهنده: <code>{user_id}</code> ({esc(user['full_name'])})\n"
            f"کاربر گزارش‌شده: <code>{partner_id}</code> ({esc(ended['partner_name'])})\n\n"
            f"📜 <b>شواهد (۵ پیام آخر چت):</b>\n<pre>{esc(evidence_text)}</pre>\n\n"
            f"برای مسدودسازی از کل ربات:\n<code>/ban {partner_id}</code>"
        )
        bot.send_message(
            chat_id,
            "🚨 گزارش شما همراه با شواهد چت برای تیم پشتیبانی ارسال شد و طرف مقابل نیز برای شما مسدود گردید.",
            reply_markup=get_webapp_reply_keyboard()
        )
    else:
        bot.send_message(
            chat_id,
            f"🔴 چت ناشناس با <b>{esc(ended['partner_name'])}</b> پایان یافت.",
            reply_markup=get_webapp_reply_keyboard()
        )
        if partner_id >= 1000:
            block_kb = types.InlineKeyboardMarkup()
            block_kb.add(types.InlineKeyboardButton(
                f"🔕 مسدود کردن {ended['partner_name']} (دیگر درخواست نفرستد)",
                callback_data=f"block_user_{partner_id}"
            ))
            bot.send_message(
                chat_id,
                "🛡️ اگر تمایل ندارید مجدداً از این بازیکن درخواست چت دریافت کنید:",
                reply_markup=block_kb
            )

    bot.send_message(chat_id, get_main_menu_text(user_id, fallback_name), reply_markup=get_main_menu_keyboard(user_id))

    if partner_id >= 1000:
        try:
            bot.send_message(
                partner_id,
                f"🔴 <b>{esc(user['full_name'])}</b> به چت پایان داد.",
                reply_markup=get_webapp_reply_keyboard()
            )
            bot.send_message(partner_id, get_main_menu_text(partner_id), reply_markup=get_main_menu_keyboard(partner_id))
        except Exception:
            pass


# =====================================================================
# مسیریاب واحد پیام‌های غیر دستوری (FSM پایدار + موتور چت ناشناس ضد اسپم)
# =====================================================================

@bot.message_handler(
    func=lambda m: not (m.text and m.text.startswith("/")),
    content_types=[
        "text", "contact", "photo", "voice", "sticker", "location",
        "audio", "video", "animation", "video_note", "document"
    ]
)
def unified_message_router(message: types.Message):
    user_id = message.from_user.id
    if not check_not_banned(user_id, message.chat.id):
        return

    # ۱. دکمه‌های کنترلی داخل چت ناشناس
    if message.content_type == "text":
        if message.text == "❌ پایان چت و بازگشت به منو":
            end_chat_for_user(user_id, message.chat.id, message.from_user.first_name or "بازیکن")
            return
        if message.text == "🚨 گزارش مزاحمت و پایان چت":
            end_chat_for_user(user_id, message.chat.id, message.from_user.first_name or "بازیکن", reported=True)
            return
        if message.text == "✅ تایید عضویت در لابی":
            active_for_approve = db.get_active_chat(user_id)
            if active_for_approve and active_for_approve.get("can_approve_member") and active_for_approve.get("lobby_id"):
                approve_lobby_membership(
                    creator_id=user_id,
                    creator_chat_id=message.chat.id,
                    lobby_id=active_for_approve["lobby_id"],
                    applicant_id=active_for_approve["partner_id"],
                    position_override=active_for_approve.get("requested_position")
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "ℹ️ در حال حاضر درخواست عضویت بازی برای تایید در این چت وجود ندارد.",
                    reply_markup=get_in_chat_reply_keyboard(can_approve_lobby=False)
                )
            return

    # ۲. بررسی وضعیت فعال مرحله‌ای کاربر در دیتابیس (DB-Backed FSM)
    st = db.get_user_state(user_id)
    if st:
        state_name = st["state"]
        state_data = st["data"]
        if state_name == "reg_name":
            handle_reg_name_step(message, state_data)
            return
        if state_name == "reg_phone":
            handle_reg_phone_step(message, state_data)
            return
        if state_name == "edit_name":
            handle_edit_name_step(message)
            return
        if state_name == "edit_phone":
            handle_edit_phone_step(message)
            return
        if state_name == "lobby_count":
            handle_lobby_count_step(message, state_data)
            return
        if state_name == "lobby_area":
            handle_lobby_area_step(message, state_data)
            return
        if state_name == "lobby_time":
            handle_lobby_time_step(message, state_data)
            return
        if state_name == "feedback_wait":
            handle_feedback_step(message)
            return

    # ۳. انتقال پیام در چت ناشناس فعال (همراه با Rate Limiting و ثبت شواهد)
    active = db.get_active_chat(user_id)
    if not active:
        return

    allowed, should_warn = chat_rate_limiter.check(user_id)
    if not allowed:
        if should_warn:
            bot.send_message(message.chat.id, "⏳ سرعت ارسال پیام شما زیاد است! لطفاً چند ثانیه صبر کنید.")
        return

    sender = db.upsert_user(user_id, message.from_user.first_name or "بازیکن")
    sender_name_raw = sender["full_name"]
    sender_name = esc(sender_name_raw)
    partner_id = active["partner_id"]
    partner_name = esc(active["partner_name"])

    if partner_id < 1000:
        reply_text = random.choice(config.DEMO_CHAT_REPLIES)
        bot.send_message(message.chat.id, f"💬 <b>{partner_name}:</b>\n{reply_text}")
        lobby_id = active.get("lobby_id")
        if lobby_id and not db.is_member_of_lobby(lobby_id, user_id):
            approve_lobby_membership(
                creator_id=partner_id,
                creator_chat_id=message.chat.id,
                lobby_id=lobby_id,
                applicant_id=user_id,
                position_override=active.get("requested_position")
            )
        return

    try:
        header = f"💬 <b>{sender_name}:</b>"
        evidence_summary = ""

        if message.content_type == "text":
            bot.send_message(partner_id, f"{header}\n{esc(message.text)}")
            evidence_summary = message.text
        elif message.content_type == "photo":
            caption = f"{header}\n{esc(message.caption)}" if message.caption else header
            bot.send_photo(partner_id, message.photo[-1].file_id, caption=caption)
            evidence_summary = f"[عکس] {message.caption or ''}".strip()
        elif message.content_type == "voice":
            bot.send_voice(partner_id, message.voice.file_id, caption=header)
            evidence_summary = "[پیام صوتی]"
        elif message.content_type == "audio":
            bot.send_audio(partner_id, message.audio.file_id, caption=header)
            evidence_summary = "[فایل صوتی]"
        elif message.content_type == "video":
            caption = f"{header}\n{esc(message.caption)}" if message.caption else header
            bot.send_video(partner_id, message.video.file_id, caption=caption)
            evidence_summary = f"[ویدیو] {message.caption or ''}".strip()
        elif message.content_type == "animation":
            caption = f"{header}\n{esc(message.caption)}" if message.caption else header
            bot.send_animation(partner_id, message.animation.file_id, caption=caption)
            evidence_summary = "[GIF]"
        elif message.content_type == "video_note":
            bot.send_message(partner_id, f"{header} (ویدیو دایره‌ای ارسال کرد 👇)")
            bot.send_video_note(partner_id, message.video_note.file_id)
            evidence_summary = "[ویدیو دایره‌ای]"
        elif message.content_type == "document":
            caption = f"{header}\n{esc(message.caption)}" if message.caption else header
            bot.send_document(partner_id, message.document.file_id, caption=caption)
            evidence_summary = f"[فایل: {message.document.file_name or 'document'}]"
        elif message.content_type == "sticker":
            bot.send_message(partner_id, f"{header} (استیکر ارسال کرد 👇)")
            bot.send_sticker(partner_id, message.sticker.file_id)
            evidence_summary = "[استیکر]"
        elif message.content_type == "location":
            bot.send_message(partner_id, f"{header} (موقعیت مکانی ارسال کرد 👇)")
            bot.send_location(partner_id, message.location.latitude, message.location.longitude)
            evidence_summary = "[موقعیت مکانی]"
        else:
            bot.send_message(message.chat.id, "⚠️ این نوع پیام در چت ناشناس پشتیبانی نمی‌شود.")
            return

        if evidence_summary:
            db.log_chat_message(active["session_id"], user_id, sender_name_raw, evidence_summary)
    except Exception as exc:
        logger.error(f"خطا در ارسال پیام چت از {user_id} به {partner_id}: {exc}")
        bot.send_message(message.chat.id, "⚠️ خطا در ارسال پیام به طرف مقابل.")
