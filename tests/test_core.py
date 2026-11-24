import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# تنظیم متغیرهای محیطی امن فقط برای اجرای تست‌های واحد بدون نیاز به توکن واقعی
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_FOR_UNIT_TESTS")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
os.environ.setdefault("ADMIN_IDS", "999001")
os.environ.setdefault("SUPPORT_IDS", "888001")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# شبیه‌سازی کامل ماژول‌های اختیاری در محیط تست سبک
if "telebot" not in sys.modules:
    fake_telebot = types.ModuleType("telebot")

    class _DummyBot:
        def __init__(self, *a, **kw):
            pass

        def message_handler(self, *a, **kw):
            return lambda fn: fn

        def callback_query_handler(self, *a, **kw):
            return lambda fn: fn

        def my_chat_member_handler(self, *a, **kw):
            return lambda fn: fn

    fake_telebot.TeleBot = _DummyBot
    fake_telebot.apihelper = types.SimpleNamespace(proxy=None, ApiTelegramException=Exception)
    fake_telebot.types = types.SimpleNamespace(
        ReplyKeyboardMarkup=MagicMock,
        ReplyKeyboardRemove=MagicMock,
        InlineKeyboardMarkup=MagicMock,
        InlineKeyboardButton=MagicMock,
        KeyboardButton=MagicMock,
        WebAppInfo=MagicMock,
        Message=object,
        CallbackQuery=object,
        ChatMemberUpdated=object,
    )
    sys.modules["telebot"] = fake_telebot
    sys.modules["telebot.types"] = fake_telebot.types
    sys.modules["telebot.apihelper"] = fake_telebot.apihelper

if "psycopg2" not in sys.modules:
    fake_pg = types.ModuleType("psycopg2")
    fake_pg.OperationalError = RuntimeError
    fake_pg.InterfaceError = RuntimeError
    fake_pg.connect = MagicMock()
    fake_pg.pool = types.SimpleNamespace(ThreadedConnectionPool=MagicMock)
    fake_pg.extras = types.SimpleNamespace(RealDictCursor=object)
    sys.modules["psycopg2"] = fake_pg
    sys.modules["psycopg2.pool"] = fake_pg.pool
    sys.modules["psycopg2.extras"] = fake_pg.extras

if "dotenv" not in sys.modules:
    fake_dotenv = types.ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = fake_dotenv

from rate_limiter import SlidingWindowRateLimiter
import config
import bot_instance
import migrations
import db
from handlers import registration, admin


class TestRateLimiter(unittest.TestCase):
    def test_sliding_window_blocks_spam_and_recovers(self):
        rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=5.0, warn_cooldown=4.0)
        self.assertEqual(rl.check(1, now=0.0), (True, False))
        self.assertEqual(rl.check(1, now=1.0), (True, False))
        self.assertEqual(rl.check(1, now=2.0), (True, False))
        self.assertEqual(rl.check(1, now=2.5), (False, True))
        self.assertEqual(rl.check(1, now=3.0), (False, False))
        self.assertEqual(rl.check(1, now=5.5), (True, False))


class TestNormalizationAndRoles(unittest.TestCase):
    def test_persian_arabic_digits_and_phone(self):
        self.assertEqual(bot_instance.normalize_digits("۱۲۳۴٥٦"), "123456")
        self.assertEqual(bot_instance.normalize_phone("+98 912-345 6789"), "09123456789")
        self.assertEqual(bot_instance.normalize_phone("۹۸۹۱۲۳۴۵۶۷۸۹"), "09123456789")

    def test_html_escape(self):
        self.assertEqual(bot_instance.esc("<b>test & 1</b>"), "&lt;b&gt;test &amp; 1&lt;/b&gt;")

    def test_role_checks(self):
        self.assertTrue(bot_instance.is_admin(999001))
        self.assertFalse(bot_instance.is_admin(888001))
        with patch.object(db, "get_support_agent_ids", return_value=[777001]):
            self.assertTrue(bot_instance.is_support(888001))
            self.assertTrue(bot_instance.is_support(777001))
            self.assertTrue(bot_instance.can_moderate(999001))
            self.assertTrue(bot_instance.can_moderate(777001))
            self.assertFalse(bot_instance.can_moderate(123456))


class TestMigrationsAndPoolSafety(unittest.TestCase):
    def test_migrations_order_and_idempotency(self):
        fake_cur = MagicMock()
        fake_cur.fetchall.return_value = [{"version": "001_initial_schema"}]
        applied_count = migrations.run_migrations(fake_cur)
        self.assertEqual(applied_count, len(migrations.MIGRATIONS) - 1)

    def test_get_cursor_closes_broken_connection(self):
        fake_conn = MagicMock()
        fake_conn.closed = 0
        fake_cursor = MagicMock()
        fake_cursor.__enter__.return_value = fake_cursor
        fake_cursor.execute.side_effect = db.psycopg2.OperationalError("connection lost")
        fake_conn.cursor.return_value = fake_cursor

        fake_pool = MagicMock()
        fake_pool.getconn.return_value = fake_conn

        with patch.object(db, "init_pool", return_value=fake_pool):
            with self.assertRaises(db.psycopg2.OperationalError):
                with db.get_cursor(commit=True) as cur:
                    cur.execute("SELECT 1")

        fake_pool.putconn.assert_called_once_with(fake_conn, close=True)

    def test_get_active_chat_uses_single_cursor_no_nested_pool_call(self):
        fake_cur = MagicMock()
        fake_cur.fetchone.return_value = {
            "session_id": 10,
            "lobby_id": 2,
            "requested_position": "مهاجم ⚡",
            "partner_id": 555,
            "partner_name": "علی",
            "partner_position": "دفاع",
            "lobby_title": "لابی تست",
            "lobby_status": "open",
            "lobby_current_players": 4,
            "lobby_max_players": 6,
            "lobby_creator_id": 111,
            "partner_already_in_lobby": False,
        }

        cm = MagicMock()
        cm.__enter__.return_value = fake_cur
        cm.__exit__.return_value = False

        with patch.object(db, "get_cursor", return_value=cm) as mocked_get_cursor:
            res = db.get_active_chat(111)
            self.assertEqual(mocked_get_cursor.call_count, 1)
            self.assertIsNotNone(res)
            self.assertTrue(res["can_approve_member"])
            self.assertEqual(res["requested_position"], "مهاجم ⚡")


class TestSecurityAndValidation(unittest.TestCase):
    def test_phone_verification_rejects_spoofed_contact_and_manual_text(self):
        spoof_msg = types.SimpleNamespace(
            content_type="contact",
            from_user=types.SimpleNamespace(id=1001),
            contact=types.SimpleNamespace(user_id=2002, phone_number="+989120000000"),
            text=None
        )
        phone, err = registration._extract_verified_phone(spoof_msg)
        self.assertIsNone(phone)
        self.assertIsNotNone(err)

        valid_msg = types.SimpleNamespace(
            content_type="contact",
            from_user=types.SimpleNamespace(id=1001),
            contact=types.SimpleNamespace(user_id=1001, phone_number="+98 912 345 6789"),
            text=None
        )
        phone, err = registration._extract_verified_phone(valid_msg)
        self.assertEqual(phone, "09123456789")
        self.assertIsNone(err)

        manual_msg = types.SimpleNamespace(
            content_type="text",
            from_user=types.SimpleNamespace(id=1001),
            contact=None,
            text="09123456789"
        )
        with patch.object(config, "ALLOW_MANUAL_PHONE", False):
            phone, err = registration._extract_verified_phone(manual_msg)
            self.assertIsNone(phone)
            self.assertIsNotNone(err)

    def test_extract_target_id_formats(self):
        self.assertEqual(admin._extract_target_id("/ban 5166475125"), 5166475125)
        self.assertEqual(admin._extract_target_id("/ban user 5166475125"), 5166475125)
        self.assertEqual(admin._extract_target_id("/deluser ۵۱۶۶۴۷۵۱۲۵"), 5166475125)
        self.assertIsNone(admin._extract_target_id("/ban user abc"))


if __name__ == "__main__":
    unittest.main()
