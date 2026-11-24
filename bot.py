import signal
import sys

import db
from bot_instance import bot, logger

# راه‌اندازی دیتابیس، اجرای مهاجرت‌های نسخه‌بندی‌شده و درج امن دیتای نمونه
db.seed_demo_data()

# ثبت تمام ماژول‌های هندلر (ماژول chat شامل مسیریاب پیام‌های غیردستوری باید آخرین مورد باشد)
import handlers.registration  # noqa: F401, E402
import handlers.lobby         # noqa: F401, E402
import handlers.admin         # noqa: F401, E402
import handlers.chat          # noqa: F401, E402


def _graceful_shutdown(signum, _frame):
    logger.info(f"🛑 سیگنال توقف ({signum}) دریافت شد. در حال خاموش کردن ایمن ربات...")
    try:
        bot.stop_polling()
    except Exception:
        pass
    db.close_pool()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _graceful_shutdown)
    signal.signal(signal.SIGINT, _graceful_shutdown)
    logger.info("🚀 ربات تیم‌یابی (نسخه v4 مهندسی‌شده + PostgreSQL + FSM پایدار) روشن شد!")
    try:
        bot.infinity_polling(
            skip_pending=True,
            allowed_updates=["message", "callback_query", "my_chat_member"]
        )
    finally:
        db.close_pool()
