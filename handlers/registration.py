from telebot import types

import config
import db
from bot_instance import (
    bot, esc, is_admin, notify_admins,
    check_not_banned, safe_edit_message, normalize_phone
)
from keyboards import (
    get_webapp_reply_keyboard,
    get_contact_reply_keyboard,
    get_in_chat_reply_keyboard,
    get_main_menu_keyboard,
    get_main_menu_text,
    get_edit_profile_keyboard,
    get_edit_profile_text,
    build_positions_keyboard,
)


def _extract_verified_phone(message: types.Message):
    """استخراج و احراز اصالت شماره تماس (تطبیق contact.user_id با فرستنده پیام)"""
    if message.content_type == "contact" and message.contact:
        if message.contact.user_id is not None and message.contact.user_id != message.from_user.id:
            return None, "⚠️ لطفاً فقط شماره تماس <b>اکانت خودتان</b> را از طریق دکمه پایین ارسال کنید (فوروارد شماره دیگران پذیرفته نمی‌شود)."
        return normalize_phone(message.contact.phone_number), None

    if not config.ALLOW_MANUAL_PHONE:
        return None, "⚠️ جهت احراز هویت واقعی، لطفاً شماره را تایپ نکنید و فقط روی دکمه <b>«📱 اشتراک‌گذاری شماره تماس من»</b> در پایین صفحه کلیک کنید."

    phone = normalize_phone(message.text or "")
    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if len(digits_only) < 10 or len(digits_only) > 15:
        return None, "⚠️ شماره تماس معتبر نیست! لطفاً روی دکمه اشتراک‌گذاری بزنید یا شماره صحیح وارد کنید."
    return phone, None


# =====================================================================
# ثبت‌نام اولیه ۴ مرحله‌ای (با وضعیت پایدار در PostgreSQL)
# =====================================================================

def start_registration_flow(chat_id: int, user_id: int):
    db.set_user_state(user_id, "reg_name", {"name": "", "phone": "", "skill": "متوسط ⚽", "positions": []})
    bot.send_message(
        chat_id,
        "📝 <b>ثبت‌نام بازیکن (گام ۱ از ۴):</b>\n\n"
        "لطفاً <b>نام نمایشی</b> خود را وارد کنید (این نام در لابی‌ها و چت ناشناس دیده می‌شود):",
        reply_markup=types.ReplyKeyboardRemove()
    )


def handle_reg_name_step(message: types.Message, state_data: dict):
    user_id = message.from_user.id
    if message.content_type != "text" or not (message.text or "").strip():
        bot.send_message(message.chat.id, "⚠️ لطفاً نام نمایشی خود را به صورت متن ارسال کنید:")
        return

    full_name = message.text.strip()[:50]
    state_data["name"] = full_name
    db.set_user_state(user_id, "reg_phone", state_data)

    bot.send_message(
        message.chat.id,
        f"✅ نام شما (<b>{esc(full_name)}</b>) ثبت شد.\n\n"
        f"📞 <b>گام ۲ از ۴ (احراز شماره تماس):</b>\n"
        f"🔒 <i>شماره شما صرفاً جهت احراز هویت در سامانه ذخیره می‌شود و به هیچ بازیکن دیگری نمایش داده نخواهد شد.</i>\n\n"
        f"👇 لطفاً روی دکمه <b>«📱 اشتراک‌گذاری شماره تماس من»</b> در پایین صفحه کلیک کنید:",
        reply_markup=get_contact_reply_keyboard()
    )


def handle_reg_phone_step(message: types.Message, state_data: dict):
    user_id = message.from_user.id
    phone, err = _extract_verified_phone(message)
    if err:
        bot.send_message(message.chat.id, err, reply_markup=get_contact_reply_keyboard())
        return

    state_data["phone"] = phone
    db.set_user_state(user_id, "reg_skill", state_data)

    bot.send_message(
        message.chat.id,
        "✅ شماره تماس شما با موفقیت احراز و به‌صورت محرمانه ثبت شد.",
        reply_markup=get_webapp_reply_keyboard()
    )

    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("🌱 مبتدی", callback_data="regskill_beg"),
        types.InlineKeyboardButton("⚽ متوسط", callback_data="regskill_mid"),
        types.InlineKeyboardButton("🔥 حرفه‌ای", callback_data="regskill_pro")
    )
    bot.send_message(
        message.chat.id,
        "⭐ <b>گام ۳ از ۴ (سطح بازی):</b>\nسطح مهارت خود را در فوتسال انتخاب کنید:",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("regskill_"))
def cb_register_skill(call: types.CallbackQuery):
    user_id = call.from_user.id
    st = db.get_user_state(user_id)
    if not st or st["state"] not in ("reg_skill", "reg_pos"):
        bot.answer_callback_query(call.id, "⚠️ جلسه ثبت‌نام منقضی شده است. لطفاً /start را بزنید.", show_alert=True)
        return

    code = call.data.split("_")[1]
    data = st["data"]
    data["skill"] = config.SKILL_MAP.get(code, "متوسط ⚽")
    data.setdefault("positions", [])
    db.set_user_state(user_id, "reg_pos", data)

    safe_edit_message(
        "⚽ <b>گام ۴ از ۴ (پست تخصصی):</b>\n\n"
        "در کدام پست‌ها تبحر بیشتری دارید؟\n"
        "<i>(یک یا چند پست را انتخاب کرده و سپس دکمه ثبت نهایی را بزنید):</i>",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=build_positions_keyboard(set(data["positions"]), "regpos", "🚀 ثبت نهایی و ورود به ربات")
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("regpos_"))
def cb_register_positions(call: types.CallbackQuery):
    user_id = call.from_user.id
    st = db.get_user_state(user_id)
    if not st or st["state"] != "reg_pos":
        bot.answer_callback_query(call.id, "⚠️ جلسه ثبت‌نام منقضی شده است. لطفاً /start را بزنید.", show_alert=True)
        return

    data = st["data"]
    selected = set(data.get("positions", []))
    action = call.data.split("_")[1]

    if action == "done":
        if not selected:
            bot.answer_callback_query(call.id, "⚠️ لطفاً حداقل یک پست را انتخاب کنید!", show_alert=True)
            return

        pos_str = " ، ".join([config.POSITIONS_MAP[c] for c in config.POSITIONS_MAP if c in selected])
        name = data.get("name") or call.from_user.first_name or "ورزشکار"
        phone = data.get("phone") or "ثبت نشده"
        skill = data.get("skill") or "متوسط ⚽"

        _, was_registered = db.complete_user_registration(user_id, name, phone, skill, pos_str)
        db.clear_user_state(user_id)
        bot.answer_callback_query(call.id, "🎉 ثبت‌نام تکمیل شد!")

        dup_user = db.find_other_user_by_phone(phone, user_id)
        dup_note = ""
        if dup_user:
            dup_note = (
                f"\n⚠️ <b>توجه:</b> این شماره قبلاً با اکانت دیگری ثبت شده بود "
                f"(<code>{dup_user['user_id']}</code> - {esc(dup_user['full_name'])})"
            )

        if was_registered:
            notify_admins(
                f"✏️ <b>اطلاعات کاربر قبلی به‌روزرسانی شد:</b>\n"
                f"👤 {esc(name)} | ID: <code>{user_id}</code>\n"
                f"📞 <code>{esc(phone)}</code>\n"
                f"⚽ {esc(pos_str)} | ⭐ {esc(skill)}{dup_note}"
            )
        else:
            notify_admins(
                f"🆕 <b>کاربر جدید ثبت‌نام کرد:</b>\n"
                f"👤 {esc(name)} | ID: <code>{user_id}</code>\n"
                f"📞 <code>{esc(phone)}</code>\n"
                f"⚽ {esc(pos_str)} | ⭐ {esc(skill)}{dup_note}"
            )

        safe_edit_message(
            get_main_menu_text(user_id, name),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_main_menu_keyboard(user_id)
        )
    else:
        if action in selected:
            selected.remove(action)
        else:
            selected.add(action)
        data["positions"] = list(selected)
        db.set_user_state(user_id, "reg_pos", data)

        safe_edit_message(
            "⚽ <b>گام ۴ از ۴ (پست تخصصی):</b>\n\n"
            "در کدام پست‌ها تبحر بیشتری دارید؟\n"
            "<i>(یک یا چند پست را انتخاب کرده و سپس دکمه ثبت نهایی را بزنید):</i>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_positions_keyboard(selected, "regpos", "🚀 ثبت نهایی و ورود به ربات")
        )


# =====================================================================
# منوی ویرایش تکی پروفایل و مدیریت کاربران مسدودشده شخصی
# =====================================================================

@bot.callback_query_handler(func=lambda call: call.data == "edit_profile_menu")
def cb_edit_profile_menu(call: types.CallbackQuery):
    if not check_not_banned(call.from_user.id, call.message.chat.id):
        return
    db.clear_user_state(call.from_user.id)
    bot.answer_callback_query(call.id)
    safe_edit_message(
        get_edit_profile_text(call.from_user.id),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_edit_profile_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_field_"))
def cb_edit_profile_field(call: types.CallbackQuery):
    user_id = call.from_user.id
    if not check_not_banned(user_id, call.message.chat.id):
        return

    field = call.data.split("_")[2]
    bot.answer_callback_query(call.id)

    if field == "name":
        db.set_user_state(user_id, "edit_name", {})
        bot.send_message(
            call.message.chat.id,
            "✏️ <b>تغییر نام نمایشی:</b>\nلطفاً نام جدید خود را تایپ و ارسال کنید (برای انصراف /cancel بزنید):"
        )

    elif field == "phone":
        db.set_user_state(user_id, "edit_phone", {})
        bot.send_message(
            call.message.chat.id,
            "📞 <b>تغییر شماره تماس:</b>\nلطفاً روی دکمه <b>«📱 اشتراک‌گذاری شماره تماس من»</b> در پایین صفحه کلیک کنید (برای انصراف /cancel بزنید):",
            reply_markup=get_contact_reply_keyboard()
        )

    elif field == "skill":
        kb = types.InlineKeyboardMarkup(row_width=3)
        kb.add(
            types.InlineKeyboardButton("🌱 مبتدی", callback_data="editskill_beg"),
            types.InlineKeyboardButton("⚽ متوسط", callback_data="editskill_mid"),
            types.InlineKeyboardButton("🔥 حرفه‌ای", callback_data="editskill_pro")
        )
        kb.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="edit_profile_menu"))
        safe_edit_message(
            "⭐ <b>تغییر سطح بازی:</b>\nسطح جدید خود را انتخاب کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=kb
        )

    elif field == "positions":
        user = db.upsert_user(user_id, call.from_user.first_name or "ورزشکار")
        current_pos_text = user.get("position") or ""
        selected = [code for code, label in config.POSITIONS_MAP.items() if label in current_pos_text]
        db.set_user_state(user_id, "edit_pos", {"positions": selected})
        safe_edit_message(
            "⚽ <b>تغییر پست‌های تخصصی:</b>\nپست‌های جدید را تیک بزنید و روی ذخیره کلیک کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_positions_keyboard(set(selected), "editpos", "💾 ذخیره تغییرات پست")
        )


def handle_edit_name_step(message: types.Message):
    user_id = message.from_user.id
    if message.content_type != "text" or not (message.text or "").strip():
        bot.send_message(message.chat.id, "⚠️ لطفاً نام جدید را به صورت متن ارسال کنید (یا /cancel بزنید):")
        return

    old_user = db.upsert_user(user_id, message.from_user.first_name or "ورزشکار")
    new_name = message.text.strip()[:50]
    db.update_user_field(user_id, "full_name", new_name)
    db.clear_user_state(user_id)

    notify_admins(
        f"✏️ <b>تغییر پروفایل (نام نمایشی):</b>\n"
        f"🆔 <code>{user_id}</code>\n"
        f"قبلی: {esc(old_user['full_name'])} ⬅️ جدید: <b>{esc(new_name)}</b>"
    )
    bot.send_message(message.chat.id, f"✅ نام شما به <b>{esc(new_name)}</b> تغییر یافت.")
    bot.send_message(message.chat.id, get_edit_profile_text(user_id), reply_markup=get_edit_profile_keyboard())


def handle_edit_phone_step(message: types.Message):
    user_id = message.from_user.id
    new_phone, err = _extract_verified_phone(message)
    if err:
        bot.send_message(message.chat.id, f"{err}\n(برای انصراف /cancel بزنید)", reply_markup=get_contact_reply_keyboard())
        return

    old_user = db.upsert_user(user_id, message.from_user.first_name or "ورزشکار")
    db.update_user_field(user_id, "phone", new_phone)
    db.clear_user_state(user_id)

    dup_user = db.find_other_user_by_phone(new_phone, user_id)
    dup_note = f"\n⚠️ تکراری با کاربر <code>{dup_user['user_id']}</code> ({esc(dup_user['full_name'])})" if dup_user else ""

    notify_admins(
        f"✏️ <b>تغییر پروفایل (شماره تماس):</b>\n"
        f"👤 {esc(old_user['full_name'])} | ID: <code>{user_id}</code>\n"
        f"قبلی: <code>{esc(old_user.get('phone'))}</code> ⬅️ جدید: <code>{esc(new_phone)}</code>{dup_note}"
    )
    bot.send_message(message.chat.id, "✅ شماره تماس شما با موفقیت احراز و به‌روزرسانی شد.", reply_markup=get_webapp_reply_keyboard())
    bot.send_message(message.chat.id, get_edit_profile_text(user_id), reply_markup=get_edit_profile_keyboard())


@bot.callback_query_handler(func=lambda call: call.data.startswith("editskill_"))
def cb_edit_skill_save(call: types.CallbackQuery):
    user_id = call.from_user.id
    code = call.data.split("_")[1]
    new_skill = config.SKILL_MAP.get(code, "متوسط ⚽")
    old_user = db.upsert_user(user_id, call.from_user.first_name or "ورزشکار")

    db.update_user_field(user_id, "skill_level", new_skill)
    notify_admins(
        f"✏️ <b>تغییر پروفایل (سطح بازی):</b>\n"
        f"👤 {esc(old_user['full_name'])} | ID: <code>{user_id}</code>\n"
        f"قبلی: {esc(old_user['skill_level'])} ⬅️ جدید: <b>{esc(new_skill)}</b>"
    )
    bot.answer_callback_query(call.id, "✅ سطح بازی تغییر کرد!")
    safe_edit_message(
        get_edit_profile_text(user_id),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=get_edit_profile_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("editpos_"))
def cb_edit_positions_save(call: types.CallbackQuery):
    user_id = call.from_user.id
    st = db.get_user_state(user_id)
    if not st or st["state"] != "edit_pos":
        bot.answer_callback_query(call.id, "⚠️ این صفحه منقضی شده است؛ دوباره وارد ویرایش پست شوید.", show_alert=True)
        return

    selected = set(st["data"].get("positions", []))
    action = call.data.split("_")[1]

    if action == "done":
        if not selected:
            bot.answer_callback_query(call.id, "⚠️ لطفاً حداقل یک پست انتخاب کنید!", show_alert=True)
            return

        new_pos = " ، ".join([config.POSITIONS_MAP[c] for c in config.POSITIONS_MAP if c in selected])
        old_user = db.upsert_user(user_id, call.from_user.first_name or "ورزشکار")
        db.update_user_field(user_id, "position", new_pos)
        db.clear_user_state(user_id)

        notify_admins(
            f"✏️ <b>تغییر پروفایل (پست تخصصی):</b>\n"
            f"👤 {esc(old_user['full_name'])} | ID: <code>{user_id}</code>\n"
            f"قبلی: {esc(old_user['position'])} ⬅️ جدید: <b>{esc(new_pos)}</b>"
        )
        bot.answer_callback_query(call.id, "✅ پست تخصصی تغییر کرد!")
        safe_edit_message(
            get_edit_profile_text(user_id),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=get_edit_profile_keyboard()
        )
    else:
        if action in selected:
            selected.remove(action)
        else:
            selected.add(action)
        db.set_user_state(user_id, "edit_pos", {"positions": list(selected)})

        safe_edit_message(
            "⚽ <b>تغییر پست‌های تخصصی:</b>\nپست‌های جدید را تیک بزنید و روی ذخیره کلیک کنید:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_positions_keyboard(selected, "editpos", "💾 ذخیره تغییرات پست")
        )


@bot.callback_query_handler(func=lambda call: call.data == "my_blocked_users")
def cb_my_blocked_users(call: types.CallbackQuery):
    user_id = call.from_user.id
    if not check_not_banned(user_id, call.message.chat.id):
        return
    blocked = db.get_blocked_users(user_id)
    kb = types.InlineKeyboardMarkup(row_width=1)

    if not blocked:
        text = "🔕 <b>لیست کاربران مسدودشده توسط شما:</b>\n\nℹ️ هیچ کاربری در لیست مسدودی شما نیست."
    else:
        text = "🔕 <b>لیست کاربران مسدودشده توسط شما:</b>\n<i>(برای رفع مسدودیت روی نام کاربر کلیک کنید)</i>\n\n"
        for item in blocked:
            kb.add(types.InlineKeyboardButton(
                f"🔓 رفع مسدودیت: {item['full_name']}",
                callback_data=f"unblock_user_{item['blocked_id']}"
            ))

    kb.add(types.InlineKeyboardButton("🔙 بازگشت به ویرایش پروفایل", callback_data="edit_profile_menu"))
    safe_edit_message(text, call.message.chat.id, call.message.message_id, reply_markup=kb)


@bot.callback_query_handler(func=lambda call: call.data.startswith("unblock_user_"))
def cb_unblock_user(call: types.CallbackQuery):
    target_id = int(call.data.split("_")[2])
    db.unblock_user(call.from_user.id, target_id)
    bot.answer_callback_query(call.id, "🔓 کاربر از لیست مسدودی شما خارج شد.")
    cb_my_blocked_users(call)


# =====================================================================
# دستورات /start ، /cancel و تشخیص مسدود کردن ربات
# =====================================================================

@bot.message_handler(commands=["cancel"])
def cmd_cancel(message: types.Message):
    user_id = message.from_user.id
    if not check_not_banned(user_id, message.chat.id):
        return
    db.clear_user_state(user_id)
    user = db.get_user_by_id(user_id)
    if not user or not user.get("is_registered"):
        bot.send_message(message.chat.id, "❌ عملیات لغو شد. برای شروع مجدد ثبت‌نام /start را بزنید.", reply_markup=types.ReplyKeyboardRemove())
        return

    bot.send_message(message.chat.id, "❌ عملیات جاری لغو شد.", reply_markup=get_webapp_reply_keyboard())
    bot.send_message(
        message.chat.id,
        get_main_menu_text(user_id, message.from_user.first_name or "ورزشکار"),
        reply_markup=get_main_menu_keyboard(user_id)
    )


@bot.message_handler(commands=["start", "demo"])
def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if not check_not_banned(user_id, message.chat.id):
        return

    db.clear_user_state(user_id)
    fallback_name = message.from_user.first_name or "ورزشکار"
    user = db.upsert_user(user_id, fallback_name)

    active_chat = db.get_active_chat(user_id)
    if active_chat:
        bot.send_message(
            message.chat.id,
            f"💬 شما هم‌اکنون در حال چت ناشناس با <b>{esc(active_chat['partner_name'])}</b> هستید.\n"
            f"برای بازگشت به منو، ابتدا دکمه «❌ پایان چت و بازگشت به منو» یا دستور /endchat را بزنید.",
            reply_markup=get_in_chat_reply_keyboard(can_approve_lobby=active_chat.get("can_approve_member", False))
        )
        return

    if not user.get("is_registered"):
        start_registration_flow(message.chat.id, user_id)
        return

    if not is_admin(user_id):
        notify_admins(
            f"🔄 <b>کاربر قدیمی دوباره ربات را استارت زد:</b>\n"
            f"👤 {esc(user['full_name'])} | ID: <code>{user_id}</code>\n"
            f"📞 <code>{esc(user.get('phone') or 'ثبت نشده')}</code>"
        )

    bot.send_message(
        message.chat.id,
        "⚽ <b>سامانه تیم‌یابی فعال است!</b>\n"
        "می‌توانید از دکمه پایین صفحه زمین فوتسال را باز کنید یا از منوی زیر وارد بخش‌های تیم‌یابی شوید:",
        reply_markup=get_webapp_reply_keyboard()
    )
    bot.send_message(
        message.chat.id,
        get_main_menu_text(user_id, fallback_name),
        reply_markup=get_main_menu_keyboard(user_id)
    )


@bot.my_chat_member_handler()
def handle_bot_block_status(update: types.ChatMemberUpdated):
    user_id = update.from_user.id
    if is_admin(user_id):
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    user = db.get_user_by_id(user_id)
    name = esc(user["full_name"]) if user else esc(update.from_user.first_name or "کاربر")

    if new_status in ("kicked", "left"):
        ended = db.end_active_chat(user_id)
        if ended and ended["partner_id"] >= 1000:
            try:
                bot.send_message(
                    ended["partner_id"],
                    f"🔴 <b>{name}</b> از ربات خارج شد و چت پایان یافت.",
                    reply_markup=get_webapp_reply_keyboard()
                )
            except Exception:
                pass
        notify_admins(f"🚫 <b>کاربر ربات را متوقف/مسدود کرد:</b>\n👤 {name} | ID: <code>{user_id}</code>")
    elif old_status in ("kicked", "left") and new_status == "member":
        notify_admins(f"♻️ <b>کاربر قدیمی ربات را دوباره فعال کرد:</b>\n👤 {name} | ID: <code>{user_id}</code>")
