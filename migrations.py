import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# لیست مهاجرت‌های نسخه‌بندی‌شده دیتابیس (هر مهاجرت فقط یک بار اجرا می‌شود)
MIGRATIONS: List[Tuple[str, str]] = [
    (
        "001_initial_schema",
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            full_name TEXT NOT NULL,
            phone TEXT DEFAULT 'ثبت نشده',
            skill_level TEXT DEFAULT 'متوسط',
            position TEXT DEFAULT 'آزاد',
            tonight_position TEXT DEFAULT NULL,
            is_available BOOLEAN DEFAULT FALSE,
            free_hours TEXT DEFAULT '۲۰ تا ۲۴',
            is_registered BOOLEAN DEFAULT FALSE,
            is_banned BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS lobbies (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            area TEXT DEFAULT 'تعیین نشده',
            slot_time TEXT NOT NULL,
            creator_id BIGINT NOT NULL,
            max_players INTEGER DEFAULT 6,
            current_players INTEGER DEFAULT 1,
            skill_req TEXT DEFAULT 'متوسط',
            status TEXT DEFAULT 'open',
            expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours'),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS lobby_members (
            id SERIAL PRIMARY KEY,
            lobby_id INTEGER NOT NULL REFERENCES lobbies(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            player_name TEXT NOT NULL,
            position TEXT DEFAULT 'بازیکن',
            joined_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(lobby_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS chat_sessions (
            id SERIAL PRIMARY KEY,
            user1_id BIGINT NOT NULL,
            user2_id BIGINT NOT NULL,
            status TEXT DEFAULT 'pending',
            lobby_id INTEGER DEFAULT NULL,
            requested_position TEXT DEFAULT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            session_id INTEGER,
            reporter_id BIGINT NOT NULL,
            reported_id BIGINT NOT NULL,
            reason TEXT DEFAULT 'مزاحمت در چت ناشناس',
            evidence TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS feedbacks (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            user_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS support_agents (
            user_id BIGINT PRIMARY KEY,
            added_by BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    ),
    (
        "002_upgrade_existing_tables_v4",
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT 'ثبت نشده';
        ALTER TABLE users ADD COLUMN IF NOT EXISTS tonight_position TEXT DEFAULT NULL;

        ALTER TABLE lobbies ADD COLUMN IF NOT EXISTS area TEXT DEFAULT 'تعیین نشده';
        ALTER TABLE lobbies ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '24 hours');

        ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS lobby_id INTEGER DEFAULT NULL;
        ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS requested_position TEXT DEFAULT NULL;

        ALTER TABLE reports ADD COLUMN IF NOT EXISTS evidence TEXT DEFAULT '';
        """
    ),
    (
        "003_fsm_blocks_and_chat_evidence",
        """
        -- نگهداری پایدار مراحل کاربر (FSM) در دیتابیس جهت بقا پس از ری‌استارت کانتینر
        CREATE TABLE IF NOT EXISTS user_states (
            user_id BIGINT PRIMARY KEY,
            state TEXT NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );

        -- مسدودسازی کاربر به کاربر (User-to-User Block)
        CREATE TABLE IF NOT EXISTS user_blocks (
            blocker_id BIGINT NOT NULL,
            blocked_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (blocker_id, blocked_id)
        );

        -- بافر موقت پیام‌های چت برای ارائه شواهد ۵ پیام آخر به پشتیبان هنگام گزارش تخلف
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            sender_id BIGINT NOT NULL,
            sender_name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_chat_active_users
            ON chat_sessions (status, user1_id, user2_id);

        CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages (session_id, id DESC);

        CREATE INDEX IF NOT EXISTS idx_lobbies_status_expires
            ON lobbies (status, expires_at);
        """
    ),
]


def run_migrations(cur) -> int:
    """اجرای ایمن و ترتیبی مهاجرت‌های ثبت‌نشده"""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    cur.execute("SELECT version FROM schema_migrations")
    applied = {row["version"] for row in cur.fetchall()}

    newly_applied = 0
    for version, sql in MIGRATIONS:
        if version in applied:
            continue
        logger.info(f"🔧 در حال اعمال مهاجرت دیتابیس: {version}")
        cur.execute(sql)
        cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
        newly_applied += 1

    return newly_applied
