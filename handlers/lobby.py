from telebot import types

import db
from bot_instance import bot, esc, check_not_banned, safe_edit_message, normalize_digits
from keyboards import get_in_chat_reply_keyboard, get_webapp_reply_keyboard


def approve_lobby_membership(
    creator_id: int,
    creator_chat_id: int,
    lobby_id: int,
    applicant_id: int,
    position_override: str = None
) -> dict:
    """تایید عضویت بازیکن توسط سرگروه؛ در صورت تکمیل ظرفیت، لابی از لیست فعال حذف می‌شود."""
    lobby, _ = db.get_lobby_with_members(lobby_id)
    if not lobby:
        if creator_id >= 1000:
            bot.send_message(creator_chat_id, "⚠️ این لابی دیگر وجود ندارد.")
        return {"ok": False, "reason": "not_found"}

    if lobby["creator_id"] != creator_id:
        if creator_id >= 1000:
            bot.send_message(creator_chat_id, "⛔ فقط سرگروه این لابی می‌تواند عضویت را تایید کند.")
        return {"ok": False, "reason": "not_creator"}

    applicant = db.upsert_user(applicant_id, "بازیکن")
    pos = position_override or applicant.get("tonight_position") or applicant.get("position") or "بازیکن آزاد ⚡"
    result = db.join_lobby(lobby_id, applicant_id, applicant["full_name"], pos)

    if not result["ok"]:
        reason = result.get("reason")
        if creator_id >= 1000:
            if reason == "already_joined":
                bot.send_message(creator_chat_id, "ℹ️ این بازیکن قبلاً عضو این لابی شده است.")
            elif reason == "already_full":
                bot.send_message(creator_chat_id, "⚠️ ظرفیت این لابی تکمیل یا بسته شده است.")
        return result

    updated_lobby = result["lobby"]
    members = result["members"]
    members_text = "\n".join([f"  {i}. ✅ {esc(m['player_name'])} ({esc(m['position'])})" for i, m in enumerate(members, 1)])

    creator_in_chat = db.get_active_chat(creator_id) is not None
    creator_kb = get_in_chat_reply_keyboard(can_approve_lobby=False) if creator_in_chat else get_webapp_reply_keyboard()

    if result["just_became_full"]:
        full_note = (
            f"🎉🎉 <b>عضویت تایید شد و ظرفیت لابی تکمیل گردید ({updated_lobby['current_players']}/{updated_lobby['max_players']} نفر)!</b> 🎉🎉\n\n"
            f"⚽ <b>{esc(updated_lobby['title'])}</b>\n"
            f"📍 محدوده: {esc(updated_lobby.get('area') or 'تعیین نشده')}\n"
            f"🕒 زمان: {esc(updated_lobby['slot_time'])}\n"
            f"🗑 <i>این لابی به‌طور خودکار از لیست لابی‌های فعال حذف شد.</i>\n\n"
            f"👥 <b>ترکیب نهایی تیم:</b>\n{members_text}"
        )
        if creator_id >= 1000:
            bot.send_message(
                creator_chat_id,
                f"{full_note}\n\n💬 <i>در صورت نیاز می‌توانید هماهنگی نهایی را در همین چت ادامه دهید یا چت را ببندید.</i>",
                reply_markup=creator_kb
            )
        if applicant_id >= 1000:
            try:
                bot.send_message(applicant_id, full_note)
            except Exception:
                pass
    else:
        if creator_id >= 1000:
            bot.send_message(
                creator_chat_id,
                f"✅ <b>عضویت «{esc(applicant['full_name'])}» در لابی تایید شد!</b>\n\n"
                f"⚽ لابی: <b>{esc(updated_lobby['title'])}</b>\n"
                f"👥 ظرفیت جدید: <b>{updated_lobby['current_players']} از {updated_lobby['max_players']} نفر</b>\n\n"
                f"💬 <i>چت ناشناس برای ادامه هماهنگی همچنان باز است.</i>",
                reply_markup=creator_kb
            )
        if applicant_id >= 1000:
            try:
                bot.send_message(
                    applicant_id,
                    f"🎉 <b>تبریک! سرگروه عضویت شما را در لابی تایید کرد!</b>\n\n"
                    f"⚽ لابی: <b>{esc(updated_lobby['title'])}</b>\n"
                    f"📍 محدوده: {esc(updated_lobby.get('area') or 'تعیین نشده')}\n"
                    f"👥 ظرفیت جدید: <b>{updated_lobby['current_players']} از {updated_lobby['max_players']} نفر</b>\n\n"
                    f"📋 <b>بازیکنان فعلی لابی:</b>\n{members_text}"
                )
            except Exception:
                pass

    return result


def initiate_lobby_join_request(
    requester_id: int,
    chat_id: int,
    lobby_id: int,
    message_id: int = None,
    callback_id: str = None,
    requested_position: str = None
):
    """شروع درخواست عضویت در لابی (ابتدا چت ناشناس با سرگروه + جلوگیری از اسپم درخواست)"""
    lobby, _ = db.get_lobby_with_members(lobby_id)
    if not lobby or lobby["status"] != "open" or lobby["current_players"] >= lobby["max_players"]:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🤝 مشاهده لابی‌های فعال امشب", callback_data="menu_lobbies"))
        if callback_id:
            bot.answer_callback_query(callback_id, "⛔ این لابی تکمیل یا منقضی شده و از لیست فعال حذف شده است.", show_alert=True)
        else:
            bot.send_message(chat_id, "⛔ این لابی تکمیل یا منقضی شده است. می‌توانید لابی‌های فعال دیگر را ببینید:", reply_markup=kb)
        return

    if lobby["creator_id"] == requester_id:
        if callback_id:
            bot.answer_callback_query(callback_id, "👑 شما سرگروه این لابی هستید!", show_alert=True)
        return

    if db.is_member_of_lobby(lobby_id, requester_id):
        if callback_id:
            bot.answer_callback_query(callback_id, "✅ شما هم‌اکنون عضو این لابی هستید!", show_alert=True)
        else:
            bot.send_message(chat_id, "✅ شما هم‌اکنون عضو این لابی هستید!")
        return

    if db.get_active_chat(requester_id):
        if callback_id:
            bot.answer_callback_query(callback_id, "⚠️ شما هم‌اکنون در یک چت فعال هستید! ابتدا با /endchat آن را ببندید.", show_alert=True)
        else:
            bot.send_message(chat_id, "⚠️ شما هم‌اکنون در یک چت فعال هستید! ابتدا با /endchat آن را ببندید.")
        return

    creator_id = lobby["creator_id"]
    if db.is_blocked_between(requester_id, creator_id):
        msg = "⛔ امکان ارسال درخواست به سرگروه این لابی وجود ندارد."
        if callback_id:
            bot.answer_callback_query(callback_id, msg, show_alert=True)
        else:
            bot.send_message(chat_id, msg)
        return

    if db.has_pending_chat_between(requester_id, creator_id):
        msg = "⏳ درخواست قبلی شما برای این سرگروه هنوز در انتظار پاسخ است."
        if callback_id:
            bot.answer_callback_query(callback_id, msg, show_alert=True)
        else:
            bot.send_message(chat_id, msg)
        return

    requester = db.upsert_user(requester_id, "بازیکن")
    creator = db.get_user_by_id(creator_id)
    if not creator or creator.get("is_banned"):
        if callback_id:
            bot.answer_callback_query(callback_id, "⚠️ سرگروه این لابی در دسترس نیست.", show_alert=True)
        return

    if creator_id < 1000:
        db.create_chat_session(
            requester_id,
            creator_id,
            auto_accept=True,
            lobby_id=lobby_id,
            requested_position=requested_position
        )
        if callback_id:
            bot.answer_callback_query(callback_id, "🟢 چت ناشناس با سرگروه آغاز شد!")
        bot.send_message(
            chat_id,
            f"🟢 <b>چت ناشناس قبل از عضویت در لابی آغاز شد!</b> (سرگروه نمونه تست)\n\n"
            f"🏟 لابی: <b>{esc(lobby['title'])}</b> ({lobby['current_players']}/{lobby['max_players']} نفر)\n"
            f"📍 محدوده: {esc(lobby.get('area') or 'تعیین نشده')}\n"
            f"👤 سرگروه: <b>{esc(creator['full_name'])}</b>\n"
            f"🔒 <i>آیدی و شماره تماس شما مخفی است.</i>\n\n"
            f"✍️ پیام هماهنگی خود را بفرستید تا سرگروه نمونه پاسخ دهد و عضویت شما را تایید کند:",
            reply_markup=get_in_chat_reply_keyboard(can_approve_lobby=False)
        )
        return

    if db.get_active_chat(creator_id):
        msg = "⏳ سرگروه این لابی الان در حال چت با شخص دیگری است. لطفاً کمی بعد تلاش کنید."
        if callback_id:
            bot.answer_callback_query(callback_id, msg, show_alert=True)
        else:
            bot.send_message(chat_id, msg)
        return

    session_id = db.create_chat_session(
        requester_id,
        creator_id,
        auto_accept=False,
        lobby_id=lobby_id,
        requested_position=requested_position
    )

    invite_kb = types.InlineKeyboardMarkup(row_width=1)
    invite_kb.add(
        types.InlineKeyboardButton("💬 قبول و شروع چت ناشناس (هماهنگی قبل از عضویت)", callback_data=f"chat_acc_{session_id}"),
        types.InlineKeyboardButton("❌ رد درخواست عضویت", callback_data=f"chat_rej_{session_id}")
    )

    pos_display = requested_position or requester.get("tonight_position") or requester.get("position") or "آزاد"
    try:
        bot.send_message(
            creator_id,
            f"📩 <b>درخواست عضویت در لابی + چت ناشناس!</b>\n\n"
            f"🏟 لابی: <b>{esc(lobby['title'])}</b> ({lobby['current_players']}/{lobby['max_players']} نفر)\n"
            f"👤 متقاضی: <b>{esc(requester['full_name'])}</b>\n"
            f"⚽ پست: {esc(pos_display)} | ⭐ سطح: {esc(requester['skill_level'])}\n\n"
            f"🔒 <i>ابتدا با او چت ناشناس کنید و در صورت تمایل، دکمه «✅ تایید عضویت در لابی» را بزنید:</i>",
            reply_markup=invite_kb
        )
        if callback_id:
            bot.answer_callback_query(callback_id, "📨 درخواست عضویت و چت ارسال شد!")

        kb_back = types.InlineKeyboardMarkup()
        kb_back.add(types.InlineKeyboardButton("🔙 بازگشت به لیست لابی‌ها", callback_data="menu_lobbies"))
        sent_text = (
            f"📨 <b>درخواست عضویت و چت ناشناس برای سرگروه «{esc(creator['full_name'])}» ارسال شد!</b>\n\n"
            f"🏟 لابی: <b>{esc(lobby['title'])}</b>\n"
            f"⏳ پس از تایید چت توسط سرگروه، به‌صورت ناشناس با هم گفتگو می‌کنید و سرگروه عضویت شما را تایید خواهد کرد."
        )
        if message_id:
            safe_edit_message(sent_text, chat_id, message_id, reply_markup=kb_back)
        else:
            bot.send_message(chat_id, sent_text, reply_markup=kb_back)
    except Exception:
        db.reject_chat_session_atomic(session_id, creator_id)
        if callback_id:
            bot.answer_callback_query(callback_id, "⚠️ امکان ارسال پیام به سرگروه این لابی وجود ندارد.", show_alert=True)
        else:
            bot.send_message(chat_id, "⚠️ امکان ارسال پیام به سرگروه این لابی وجود ندارد.")


@bot.callback_query_handler(func=lambda call: call.data == "menu_lobbies")
def cb_menu_lobbies(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    lobbies = db.get_open_lobbies()
    kb = types.InlineKeyboardMarkup(row_width=1)

    if not lobbies:
        text = (
            "🤝 <b>لابی‌های فعال تیم‌یابی:</b>\n\n"
            "ℹ️ در حال حاضر تمام لابی‌ها تکمیل یا منقضی شده‌اند و لابی بازی وجود ندارد.\n"
            "می‌توانید همین الان یک لابی جدید بسازید:"
        )
    else:
        text = "🤝 <b>لابی‌های فعال تیم‌یابی:</b>\n<i>(لابی‌ها پس از تکمیل یا گذشت ۲۴ ساعت به‌طور خودکار حذف می‌شوند)</i>\n\n"
        for lob in lobbies:
            area = esc(lob.get("area") or "تعیین نشده")
            text += (
                f"⚽ <b>{esc(lob['title'])}</b>\n"
                f"📍 {area} | 🕒 {esc(lob['slot_time'])}\n"
                f"👥 ظرفیت: <b>🟢 {lob['current_players']}/{lob['max_players']} نفر</b>\n\n"
            )
            kb.add(types.InlineKeyboardButton(
                f"👁️ {lob['title']} ({lob['current_players']}/{lob['max_players']})",
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

    kb_back = types.InlineKeyboardMarkup()
    kb_back.add(types.InlineKeyboardButton("🔙 بازگشت به لیست لابی‌ها", callback_data="menu_lobbies"))

    if not lobby or lobby["status"] != "open" or lobby["current_players"] >= lobby["max_players"]:
        safe_edit_message(
            "⛔ <b>این لابی تکمیل، لغو یا منقضی شده و از لیست لابی‌های فعال حذف شده است.</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb_back
        )
        return

    members_text = "\n".join([f"  {i}. 👤 {esc(m['player_name'])} ({esc(m['position'])})" for i, m in enumerate(members, 1)])
    uid = call.from_user.id
    already_member = db.is_member_of_lobby(lobby_id, uid)

    text = (
        f"🏟 <b>لابی: {esc(lobby['title'])}</b>\n\n"
        f"📍 <b>محدوده / سالن:</b> {esc(lobby.get('area') or 'تعیین نشده')}\n"
        f"🕒 <b>زمان بازی:</b> {esc(lobby['slot_time'])}\n"
        f"👥 <b>ظرفیت:</b> {lobby['current_players']} از {lobby['max_players']} نفر\n\n"
        f"📋 <b>بازیکنان ثبت‌شده در لابی:</b>\n{members_text}\n\n"
        f"🔒 <i>برای پیوستن به لابی، ابتدا درخواست عضویت می‌دهید و پس از چت ناشناس با سرگروه، عضویت شما تایید می‌شود.</i>"
    )

    kb = types.InlineKeyboardMarkup(row_width=1)
    if lobby["creator_id"] == uid:
        kb.add(types.InlineKeyboardButton("🗑 لغو و بستن این لابی", callback_data=f"lobby_cancel_{lobby_id}"))
    elif already_member:
        kb.add(types.InlineKeyboardButton("🚪 خروج از این لابی", callback_data=f"lobby_leave_{lobby_id}"))
    else:
        kb.add(types.InlineKeyboardButton(
            "📩 درخواست عضویت و چت ناشناس با سرگروه",
            callback_data=f"lobby_req_{lobby_id}"
        ))

    kb.add(types.InlineKeyboardButton("🔙 بازگشت به لیست لابی‌ها", callback_data="menu_lobbies"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_leave_"))
def cb_lobby_leave(call: types.CallbackQuery):
    lobby_id = int(call.data.split("_")[2])
    uid = call.from_user.id
    res = db.leave_lobby(lobby_id, uid)
    if not res["ok"]:
        bot.answer_callback_query(call.id, "⚠️ امکان خروج از این لابی وجود ندارد.", show_alert=True)
        return

    lobby = res["lobby"]
    user = db.get_user_by_id(uid) or {"full_name": "بازیکن"}
    bot.answer_callback_query(call.id, "🚪 شما از لابی خارج شدید.")
    if lobby["creator_id"] >= 1000:
        try:
            bot.send_message(
                lobby["creator_id"],
                f"🚪 بازیکن <b>{esc(user['full_name'])}</b> از لابی «{esc(lobby['title'])}» خارج شد.\n"
                f"👥 ظرفیت فعلی: <b>{lobby['current_players']}/{lobby['max_players']} نفر</b>"
            )
        except Exception:
            pass
    cb_menu_lobbies(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_cancel_"))
def cb_lobby_cancel(call: types.CallbackQuery):
    lobby_id = int(call.data.split("_")[2])
    uid = call.from_user.id
    res = db.cancel_lobby(lobby_id, uid)
    if not res["ok"]:
        bot.answer_callback_query(call.id, "⚠️ امکان لغو این لابی وجود ندارد.", show_alert=True)
        return

    lobby = res["lobby"]
    bot.answer_callback_query(call.id, "🗑 لابی با موفقیت لغو و بسته شد.", show_alert=True)
    for mid in res["member_ids"]:
        if mid >= 1000:
            try:
                bot.send_message(mid, f"🚫 لابی <b>«{esc(lobby['title'])}»</b> توسط سرگروه لغو شد.")
            except Exception:
                pass
    cb_menu_lobbies(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_req_"))
def cb_lobby_request(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    lobby_id = int(call.data.split("_")[2])
    initiate_lobby_join_request(
        requester_id=call.from_user.id,
        chat_id=call.message.chat.id,
        lobby_id=lobby_id,
        message_id=call.message.message_id,
        callback_id=call.id
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("lobby_approve_"))
def cb_lobby_approve_inline(call: types.CallbackQuery):
    parts = call.data.split("_")
    lobby_id = int(parts[2])
    applicant_id = int(parts[3])

    active = db.get_active_chat(call.from_user.id)
    req_pos = active.get("requested_position") if active and active.get("lobby_id") == lobby_id else None

    result = approve_lobby_membership(
        creator_id=call.from_user.id,
        creator_chat_id=call.message.chat.id,
        lobby_id=lobby_id,
        applicant_id=applicant_id,
        position_override=req_pos
    )
    if result.get("ok"):
        bot.answer_callback_query(call.id, "✅ عضویت با موفقیت تایید شد!")
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "⚠️ امکان تایید وجود ندارد (تکمیل شده یا قبلاً عضو شده).", show_alert=True)


# =====================================================================
# ساخت لابی ۳ مرحله‌ای پایدار در دیتابیس (تعداد ۱ تا ۶ -> محدوده -> ساعت بازی)
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "lobby_create_menu")
def cb_lobby_create_menu(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    db.set_user_state(call.from_user.id, "lobby_count", {})
    bot.send_message(
        call.message.chat.id,
        "➕ <b>ساخت لابی جدید تیم‌یابی (گام ۱ از ۳):</b>\n\n"
        "👥 در حال حاضر <b>چند نفر</b> هستید؟\n"
        "لطفاً یک عدد بین <b>۱ تا ۶</b> تایپ و ارسال کنید (برای انصراف /cancel بزنید):"
    )


def handle_lobby_count_step(message: types.Message, state_data: dict):
    user_id = message.from_user.id
    raw = normalize_digits(message.text or "") if message.content_type == "text" else ""
    if not raw.isdigit() or not (1 <= int(raw) <= 6):
        bot.send_message(
            message.chat.id,
            "⚠️ لطفاً فقط یک عدد بین <b>۱ تا ۶</b> وارد کنید (مثلاً <code>4</code>) یا /cancel بزنید:"
        )
        return

    state_data["count"] = int(raw)
    db.set_user_state(user_id, "lobby_area", state_data)
    bot.send_message(
        message.chat.id,
        "📍 <b>گام ۲ از ۳ (محدوده / شهر / نام سالن):</b>\n"
        "بازی در کدام محدوده یا سالن برگزار می‌شود؟ (مثلاً: <i>شرق تهران - سالن آزادی</i> یا <i>کرج - گوهردشت</i>):"
    )


def handle_lobby_area_step(message: types.Message, state_data: dict):
    user_id = message.from_user.id
    if message.content_type != "text" or not (message.text or "").strip():
        bot.send_message(message.chat.id, "⚠️ لطفاً نام محدوده یا سالن را به صورت متن ارسال کنید (یا /cancel بزنید):")
        return

    state_data["area"] = message.text.strip()[:80]
    db.set_user_state(user_id, "lobby_time", state_data)
    bot.send_message(
        message.chat.id,
        "🕒 <b>گام ۳ از ۳ (زمان و ساعت بازی):</b>\n"
        "ساعت دقیق بازی را بنویسید (مثلاً: <i>امشب ساعت ۲۱:۳۰ تا ۲۳:۰۰</i>):"
    )


def handle_lobby_time_step(message: types.Message, state_data: dict):
    user_id = message.from_user.id
    if message.content_type != "text" or not (message.text or "").strip():
        bot.send_message(message.chat.id, "⚠️ لطفاً ساعت بازی را به صورت متن ارسال کنید (یا /cancel بزنید):")
        return

    current_count = int(state_data.get("count", 1))
    area = state_data.get("area", "تعیین نشده")
    slot_time = message.text.strip()[:80]

    max_players = 6 if current_count < 6 else 12
    needed = max_players - current_count

    user = db.upsert_user(user_id, message.from_user.first_name or "سرگروه")
    title = f"لابی فوتسال {user['full_name']} (نیاز به {needed} نفر)"

    lobby_id = db.create_new_lobby(
        title=title,
        area=area,
        slot_time=slot_time,
        creator_id=user_id,
        creator_name=user["full_name"],
        max_players=max_players,
        initial_count=current_count
    )
    db.clear_user_state(user_id)

    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"👁️ مشاهده لابی ساخته‌شده ({current_count}/{max_players})", callback_data=f"lobby_view_{lobby_id}"),
        types.InlineKeyboardButton("🤝 مشاهده همه لابی‌ها", callback_data="menu_lobbies"),
        types.InlineKeyboardButton("🔙 منوی اصلی", callback_data="main_menu")
    )
    bot.send_message(
        message.chat.id,
        f"✅ <b>لابی شما با موفقیت ایجاد شد!</b>\n\n"
        f"⚽ <b>عنوان:</b> {esc(title)}\n"
        f"📍 <b>محدوده:</b> {esc(area)}\n"
        f"🕒 <b>زمان:</b> {esc(slot_time)}\n"
        f"👥 <b>وضعیت فعلی:</b> {current_count} از {max_players} نفر\n"
        f"📢 متقاضیان ابتدا درخواست چت ناشناس می‌دهند و پس از گفت‌وگو می‌توانید عضویت آن‌ها را تایید کنید.",
        reply_markup=kb
    )
