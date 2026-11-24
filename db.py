import json
import time
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

import config
from migrations import run_migrations

logger = logging.getLogger(__name__)
_connection_pool: Optional[pool.ThreadedConnectionPool] = None

ALLOWED_EDIT_FIELDS = {"full_name", "phone", "skill_level", "position"}


def init_pool(retries: int = 10, delay: float = 2.0) -> pool.ThreadedConnectionPool:
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=20,
                dsn=config.DATABASE_URL,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
            logger.info("✅ اتصال Connection Pool به PostgreSQL برقرار شد.")
            return _connection_pool
        except psycopg2.OperationalError as exc:
            last_err = exc
            logger.warning(f"⏳ در انتظار آماده شدن PostgreSQL (تلاش {attempt}/{retries})...")
            time.sleep(delay)

    raise RuntimeError(f"❌ خطا در اتصال به PostgreSQL: {last_err}")


def close_pool() -> None:
    """بستن تمیز تمام اتصالات دیتابیس هنگام خاموش شدن ربات"""
    global _connection_pool
    if _connection_pool is not None:
        try:
            _connection_pool.closeall()
            logger.info("🔌 Connection Pool دیتابیس به‌صورت ایمن بسته شد.")
        except Exception as exc:
            logger.warning(f"خطا هنگام بستن Pool: {exc}")
        finally:
            _connection_pool = None


@contextmanager
def get_cursor(commit: bool = False):
    """مدیریت امن دریافت اتصال با دور انداختن خودکار اتصالات خراب/قطع‌شده"""
    db_pool = init_pool()
    conn = db_pool.getconn()
    conn_broken = False
    try:
        if conn.closed:
            conn_broken = True
            db_pool.putconn(conn, close=True)
            conn = db_pool.getconn()
            conn_broken = False

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur

        if commit:
            conn.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        conn_broken = True
        try:
            if not conn.closed:
                conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        try:
            if not conn.closed:
                conn.rollback()
            else:
                conn_broken = True
        except Exception:
            conn_broken = True
        raise
    finally:
        if conn is not None:
            try:
                db_pool.putconn(conn, close=(conn_broken or bool(conn.closed)))
            except Exception:
                pass


def health_check() -> bool:
    """بررسی سریع و سبک سلامت اتصال به PostgreSQL (مناسب برای Docker HEALTHCHECK)"""
    conn = None
    try:
        conn = psycopg2.connect(config.DATABASE_URL, connect_timeout=3)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def init_db() -> None:
    with get_cursor(commit=True) as cur:
        run_migrations(cur)


def _sync_lobbies_sequence(cur) -> None:
    cur.execute("""
        SELECT setval(
            pg_get_serial_sequence('lobbies', 'id'),
            GREATEST(COALESCE((SELECT MAX(id) FROM lobbies), 1), 2),
            true
        )
    """)


def seed_demo_data() -> None:
    init_db()
    with get_cursor(commit=True) as cur:
        fake_players = [
            (101, "امیرحسین رضایی", "نمونه", "حرفه‌ای", "دروازه‌بان 🧤", True, "۱۹ تا ۲۳", True),
            (102, "محمدامین کریمی", "نمونه", "متوسط", "دفاع / عقب‌گیر 🛡️", True, "۲۰ تا ۲۴", True),
            (103, "سهراب مرادی", "نمونه", "حرفه‌ای", "مهاجم (راس) ⚡", True, "۱۸ تا ۲۲", True),
            (104, "کیارش نادری", "نمونه", "متوسط", "وینگر راست 🏃", True, "۲۱ تا ۲۴", True),
            (105, "پویا شمس", "نمونه", "مبتدی", "دفاع چپ 🛡️", True, "۱۹ تا ۲۲", True),
        ]
        cur.executemany("""
            INSERT INTO users (user_id, full_name, phone, skill_level, position, is_available, free_hours, is_registered)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, fake_players)

        demo_lobbies = [
            (1, "فوتسال ۵ به ۵ (تیم ناقص - ۱ نفر کم)", "تهران - سالن نمونه آزادی", "امشب ساعت ۲۱:۰۰ تا ۲۲:۳۰", 101, 6, 5, "متوسط به بالا", "open"),
            (2, "لابی عمومی فوتسال (افراد تکی)", "تهران - شرق (نمونه)", "امشب ساعت ۲۲:۳۰ تا ۲۴:۰۰", 102, 12, 8, "آزاد / دوستانه", "open"),
        ]
        cur.executemany("""
            INSERT INTO lobbies (id, title, area, slot_time, creator_id, max_players, current_players, skill_req, status, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW() + INTERVAL '365 days')
            ON CONFLICT (id) DO NOTHING
        """, demo_lobbies)

        lobby1_members = [
            (1, 101, "امیرحسین رضایی", "دروازه‌بان 🧤"),
            (1, 102, "محمدامین کریمی", "عقب‌گیر 🛡️"),
            (1, 103, "سهراب مرادی", "مهاجم ⚡"),
            (1, 104, "کیارش نادری", "وینگر راست 🏃"),
            (1, 105, "پویا شمس", "دفاع چپ 🛡️"),
        ]
        cur.executemany("""
            INSERT INTO lobby_members (lobby_id, user_id, player_name, position)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (lobby_id, user_id) DO NOTHING
        """, lobby1_members)

        _sync_lobbies_sequence(cur)


def reset_demo_data() -> None:
    init_db()
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM chat_sessions WHERE user1_id < 1000 OR user2_id < 1000")
        cur.execute("DELETE FROM lobby_members WHERE user_id < 1000 OR lobby_id IN (SELECT id FROM lobbies WHERE creator_id < 1000)")
        cur.execute("DELETE FROM lobbies WHERE creator_id < 1000")
        cur.execute("DELETE FROM users WHERE user_id < 1000")
    seed_demo_data()


# =====================================================================
# مدیریت پایدار وضعیت مراحل کاربر (DB-Backed FSM)
# =====================================================================

def set_user_state(user_id: int, state: str, data: Optional[Dict[str, Any]] = None) -> None:
    payload = json.dumps(data or {}, ensure_ascii=False)
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO user_states (user_id, state, data, updated_at)
            VALUES (%s, %s, %s::jsonb, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET state = EXCLUDED.state,
                data = EXCLUDED.data,
                updated_at = NOW()
        """, (user_id, state, payload))


def get_user_state(user_id: int) -> Optional[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute("SELECT state, data FROM user_states WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return {"state": row["state"], "data": dict(data or {})}


def clear_user_state(user_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM user_states WHERE user_id = %s", (user_id,))


# =====================================================================
# مدیریت پشتیبان‌ها (Support Agents)
# =====================================================================

def add_support_agent(user_id: int, added_by: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO support_agents (user_id, added_by)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, added_by))
        return cur.rowcount > 0


def remove_support_agent(user_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM support_agents WHERE user_id = %s", (user_id,))
        return cur.rowcount > 0


def get_support_agent_ids() -> List[int]:
    with get_cursor() as cur:
        cur.execute("SELECT user_id FROM support_agents ORDER BY created_at ASC")
        return [row["user_id"] for row in cur.fetchall()]


# =====================================================================
# مسدودسازی کاربر به کاربر (User-to-User Block)
# =====================================================================

def block_user(blocker_id: int, blocked_id: int) -> bool:
    if blocker_id == blocked_id:
        return False
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO user_blocks (blocker_id, blocked_id)
            VALUES (%s, %s)
            ON CONFLICT (blocker_id, blocked_id) DO NOTHING
        """, (blocker_id, blocked_id))
        return cur.rowcount > 0


def unblock_user(blocker_id: int, blocked_id: int) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM user_blocks WHERE blocker_id = %s AND blocked_id = %s",
            (blocker_id, blocked_id)
        )
        return cur.rowcount > 0


def is_blocked_between(user1_id: int, user2_id: int) -> bool:
    with get_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM user_blocks
            WHERE (blocker_id = %s AND blocked_id = %s)
               OR (blocker_id = %s AND blocked_id = %s)
            LIMIT 1
        """, (user1_id, user2_id, user2_id, user1_id))
        return cur.fetchone() is not None


def get_blocked_users(blocker_id: int) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT b.blocked_id, COALESCE(u.full_name, 'کاربر حذف‌شده') AS full_name
            FROM user_blocks b
            LEFT JOIN users u ON u.user_id = b.blocked_id
            WHERE b.blocker_id = %s
            ORDER BY b.created_at DESC
        """, (blocker_id,))
        return [dict(r) for r in cur.fetchall()]


# =====================================================================
# توابع کاربران، پروفایل، آمادگی و حذف ایمن
# =====================================================================

def upsert_user(user_id: int, full_name: str) -> Dict:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO users (user_id, full_name, is_registered)
            VALUES (%s, %s, FALSE)
            ON CONFLICT (user_id) DO NOTHING
        """, (user_id, full_name))
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        return dict(cur.fetchone())


def get_user_by_id(user_id: int) -> Optional[Dict]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_all_real_users(limit: int = 50) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT user_id, full_name, phone, skill_level, position,
                   is_available, is_registered, is_banned,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created_str
            FROM users
            WHERE user_id >= 1000
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]


def delete_user_completely(user_id: int) -> Optional[Dict]:
    """حذف ایمن کاربر: لابی‌های تکمیل/لغو/منقضی‌شده زنده نمی‌شوند و وابستگی‌ها تمیز پاک می‌شوند"""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        existing = cur.fetchone()
        if not existing:
            return None

        cur.execute("DELETE FROM user_states WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM user_blocks WHERE blocker_id = %s OR blocked_id = %s", (user_id, user_id))
        cur.execute("DELETE FROM chat_sessions WHERE user1_id = %s OR user2_id = %s", (user_id, user_id))

        # فقط لابی‌هایی که هم‌اکنون open هستند کاهش ظرفیت می‌یابند
        cur.execute("""
            SELECT lm.lobby_id
            FROM lobby_members lm
            JOIN lobbies l ON l.id = lm.lobby_id
            WHERE lm.user_id = %s AND l.status = 'open' AND l.creator_id != %s
        """, (user_id, user_id))
        open_lobby_ids = [r["lobby_id"] for r in cur.fetchall()]

        cur.execute("DELETE FROM lobby_members WHERE user_id = %s", (user_id,))

        for lob_id in open_lobby_ids:
            cur.execute("""
                UPDATE lobbies
                SET current_players = GREATEST(current_players - 1, 1)
                WHERE id = %s AND status = 'open'
            """, (lob_id,))

        cur.execute("DELETE FROM lobbies WHERE creator_id = %s", (user_id,))
        cur.execute("DELETE FROM support_agents WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

        return dict(existing)


def find_other_user_by_phone(phone: str, exclude_user_id: int) -> Optional[Dict]:
    if not phone or phone in ("ثبت نشده", "نمونه"):
        return None
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM users
            WHERE phone = %s AND user_id != %s AND user_id >= 1000
            LIMIT 1
        """, (phone, exclude_user_id))
        row = cur.fetchone()
        return dict(row) if row else None


def is_user_banned(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    return bool(user and user.get("is_banned"))


def set_user_ban(user_id: int, banned: bool) -> bool:
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET is_banned = %s WHERE user_id = %s", (banned, user_id))
        return cur.rowcount > 0


def complete_user_registration(
    user_id: int,
    full_name: str,
    phone: str,
    skill_level: str,
    position: str
) -> Tuple[Dict, bool]:
    existing = upsert_user(user_id, full_name)
    was_registered = bool(existing.get("is_registered"))
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE users
            SET full_name = %s, phone = %s, skill_level = %s, position = %s, is_registered = TRUE
            WHERE user_id = %s
            RETURNING *
        """, (full_name, phone, skill_level, position, user_id))
        return dict(cur.fetchone()), was_registered


def update_user_field(user_id: int, field_name: str, new_value: str) -> Optional[Dict]:
    if field_name not in ALLOWED_EDIT_FIELDS:
        raise ValueError(f"فیلد غیرمجاز: {field_name}")
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE users SET {field_name} = %s WHERE user_id = %s RETURNING *",
            (new_value, user_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def update_user_availability(
    user_id: int,
    is_available: int,
    tonight_position: Optional[str] = None,
    free_hours: str = "۲۰ تا ۲۴"
) -> None:
    """تغییر وضعیت آمادگی امشب بدون دستکاری پست‌های اصلی پروفایل (position)"""
    avail_bool = bool(is_available)
    with get_cursor(commit=True) as cur:
        if avail_bool:
            cur.execute("""
                UPDATE users
                SET is_available = TRUE, tonight_position = %s, free_hours = %s
                WHERE user_id = %s
            """, (tonight_position, free_hours, user_id))
        else:
            cur.execute("""
                UPDATE users
                SET is_available = FALSE, tonight_position = NULL
                WHERE user_id = %s
            """, (user_id,))


def get_available_players(viewer_id: Optional[int] = None) -> List[Dict]:
    """لیست بازیکنان آماده امشب با حذف کاربران بلاک‌شده بین دو طرف"""
    with get_cursor() as cur:
        if viewer_id is not None:
            cur.execute("""
                SELECT u.* FROM users u
                WHERE u.is_available = TRUE
                  AND u.is_banned = FALSE
                  AND NOT EXISTS (
                      SELECT 1 FROM user_blocks b
                      WHERE (b.blocker_id = %s AND b.blocked_id = u.user_id)
                         OR (b.blocker_id = u.user_id AND b.blocked_id = %s)
                  )
                ORDER BY CASE WHEN u.user_id >= 1000 THEN 0 ELSE 1 END, u.created_at DESC
            """, (viewer_id, viewer_id))
        else:
            cur.execute("""
                SELECT * FROM users
                WHERE is_available = TRUE AND is_banned = FALSE
                ORDER BY CASE WHEN user_id >= 1000 THEN 0 ELSE 1 END, created_at DESC
            """)
        return [dict(row) for row in cur.fetchall()]


# =====================================================================
# توابع لابی‌ها (همراه با محدوده، انقضای ۲۴ ساعته، خروج و لغو)
# =====================================================================

def expire_old_lobbies() -> int:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE lobbies
            SET status = 'expired'
            WHERE status = 'open'
              AND creator_id >= 1000
              AND expires_at IS NOT NULL
              AND expires_at <= NOW()
        """)
        return cur.rowcount


def get_open_lobbies() -> List[Dict]:
    expire_old_lobbies()
    with get_cursor() as cur:
        cur.execute("""
            SELECT * FROM lobbies
            WHERE status = 'open'
              AND current_players < max_players
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY CASE WHEN creator_id >= 1000 THEN 0 ELSE 1 END, id DESC
        """)
        return [dict(row) for row in cur.fetchall()]


def get_lobby_with_members(lobby_id: int) -> Tuple[Optional[Dict], List[Dict]]:
    expire_old_lobbies()
    with get_cursor() as cur:
        cur.execute("SELECT * FROM lobbies WHERE id = %s", (lobby_id,))
        lobby_row = cur.fetchone()
        if not lobby_row:
            return None, []
        cur.execute("SELECT * FROM lobby_members WHERE lobby_id = %s ORDER BY id ASC", (lobby_id,))
        members = [dict(r) for r in cur.fetchall()]
        return dict(lobby_row), members


def is_member_of_lobby(lobby_id: int, user_id: int) -> bool:
    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM lobby_members WHERE lobby_id = %s AND user_id = %s",
            (lobby_id, user_id)
        )
        return cur.fetchone() is not None


def create_new_lobby(
    title: str,
    area: str,
    slot_time: str,
    creator_id: int,
    creator_name: str,
    max_players: int = 6,
    initial_count: int = 1,
    ttl_hours: int = None
) -> int:
    ttl = config.LOBBY_TTL_HOURS if ttl_hours is None else ttl_hours
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO lobbies (title, area, slot_time, creator_id, max_players, current_players, status, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'open', NOW() + (%s || ' hours')::INTERVAL)
            RETURNING id
        """, (title, area, slot_time, creator_id, max_players, initial_count, str(ttl)))
        lobby_id = cur.fetchone()["id"]

        cur.execute("""
            INSERT INTO lobby_members (lobby_id, user_id, player_name, position)
            VALUES (%s, %s, %s, 'سرگروه ⭐')
            ON CONFLICT (lobby_id, user_id) DO NOTHING
        """, (lobby_id, creator_id, creator_name))
        return lobby_id


def join_lobby(lobby_id: int, user_id: int, player_name: str, position: str = "بازیکن آزاد") -> Dict:
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM lobbies WHERE id = %s FOR UPDATE", (lobby_id,))
        lobby = cur.fetchone()
        if not lobby:
            return {"ok": False, "reason": "not_found"}

        lobby = dict(lobby)
        if lobby["status"] != "open" or lobby["current_players"] >= lobby["max_players"]:
            return {"ok": False, "reason": "already_full", "lobby": lobby}

        cur.execute(
            "SELECT 1 FROM lobby_members WHERE lobby_id = %s AND user_id = %s",
            (lobby_id, user_id)
        )
        if cur.fetchone():
            return {"ok": False, "reason": "already_joined", "lobby": lobby}

        new_count = lobby["current_players"] + 1
        new_status = "full" if new_count >= lobby["max_players"] else "open"

        cur.execute("""
            INSERT INTO lobby_members (lobby_id, user_id, player_name, position)
            VALUES (%s, %s, %s, %s)
        """, (lobby_id, user_id, player_name, position))

        cur.execute("""
            UPDATE lobbies SET current_players = %s, status = %s WHERE id = %s
            RETURNING *
        """, (new_count, new_status, lobby_id))
        updated_lobby = dict(cur.fetchone())

        cur.execute("SELECT * FROM lobby_members WHERE lobby_id = %s ORDER BY id ASC", (lobby_id,))
        updated_members = [dict(r) for r in cur.fetchall()]

    return {
        "ok": True,
        "just_became_full": (new_status == "full"),
        "lobby": updated_lobby,
        "members": updated_members
    }


def leave_lobby(lobby_id: int, user_id: int) -> Dict:
    """خروج ایمن بازیکن از لابی باز و آزادسازی جای خالی"""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM lobbies WHERE id = %s FOR UPDATE", (lobby_id,))
        lobby = cur.fetchone()
        if not lobby:
            return {"ok": False, "reason": "not_found"}

        lobby = dict(lobby)
        if lobby["creator_id"] == user_id:
            return {"ok": False, "reason": "is_creator"}
        if lobby["status"] != "open":
            return {"ok": False, "reason": "not_open"}

        cur.execute(
            "DELETE FROM lobby_members WHERE lobby_id = %s AND user_id = %s",
            (lobby_id, user_id)
        )
        if cur.rowcount == 0:
            return {"ok": False, "reason": "not_member"}

        new_count = max(lobby["current_players"] - 1, 1)
        cur.execute(
            "UPDATE lobbies SET current_players = %s WHERE id = %s RETURNING *",
            (new_count, lobby_id)
        )
        updated = dict(cur.fetchone())
        return {"ok": True, "lobby": updated}


def cancel_lobby(lobby_id: int, creator_id: int) -> Dict:
    """لغو و بستن لابی توسط سرگروه"""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM lobbies WHERE id = %s FOR UPDATE", (lobby_id,))
        lobby = cur.fetchone()
        if not lobby:
            return {"ok": False, "reason": "not_found"}

        lobby = dict(lobby)
        if lobby["creator_id"] != creator_id:
            return {"ok": False, "reason": "not_creator"}
        if lobby["status"] != "open":
            return {"ok": False, "reason": "not_open"}

        cur.execute("SELECT user_id FROM lobby_members WHERE lobby_id = %s", (lobby_id,))
        member_ids = [r["user_id"] for r in cur.fetchall() if r["user_id"] != creator_id]

        cur.execute("UPDATE lobbies SET status = 'cancelled' WHERE id = %s", (lobby_id,))
        # بستن درخواست‌های در انتظار مربوط به این لابی
        cur.execute(
            "UPDATE chat_sessions SET status = 'ended' WHERE lobby_id = %s AND status = 'pending'",
            (lobby_id,)
        )
        return {"ok": True, "lobby": lobby, "member_ids": member_ids}


# =====================================================================
# توابع چت ناشناس (بدون کوئری تو در تو، دارای قفل اتمیک و ضد اسپم درخواست)
# =====================================================================

def expire_stale_pending_chats() -> int:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE chat_sessions
            SET status = 'ended'
            WHERE status = 'pending'
              AND created_at <= NOW() - (%s || ' hours')::INTERVAL
        """, (str(config.PENDING_CHAT_TTL_HOURS),))
        return cur.rowcount


def has_pending_chat_between(user1_id: int, user2_id: int) -> bool:
    expire_stale_pending_chats()
    with get_cursor() as cur:
        cur.execute("""
            SELECT 1 FROM chat_sessions
            WHERE status = 'pending'
              AND ((user1_id = %s AND user2_id = %s) OR (user1_id = %s AND user2_id = %s))
            LIMIT 1
        """, (user1_id, user2_id, user2_id, user1_id))
        return cur.fetchone() is not None


def create_chat_session(
    requester_id: int,
    target_id: int,
    auto_accept: bool = False,
    lobby_id: Optional[int] = None,
    requested_position: Optional[str] = None
) -> int:
    status = "active" if auto_accept else "pending"
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO chat_sessions (user1_id, user2_id, status, lobby_id, requested_position)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (requester_id, target_id, status, lobby_id, requested_position))
        return cur.fetchone()["id"]


def accept_chat_session_atomic(session_id: int, acceptor_id: int) -> Dict:
    """تایید اتمیک درخواست چت با قفل ترتیبی روی هر دو کاربر (رفع کامل Race Condition)"""
    expire_stale_pending_chats()
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM chat_sessions WHERE id = %s FOR UPDATE", (session_id,))
        session = cur.fetchone()
        if not session or session["status"] != "pending":
            return {"ok": False, "reason": "expired"}

        session = dict(session)
        if session["user2_id"] != acceptor_id:
            return {"ok": False, "reason": "unauthorized"}

        u1, u2 = session["user1_id"], session["user2_id"]
        low_id, high_id = sorted((u1, u2))
        cur.execute(
            "SELECT user_id FROM users WHERE user_id IN (%s, %s) ORDER BY user_id ASC FOR UPDATE",
            (low_id, high_id)
        )

        # بررسی نبودن چت فعال هم‌زمان برای هیچ‌کدام از دو طرف
        cur.execute("""
            SELECT 1 FROM chat_sessions
            WHERE status = 'active'
              AND (user1_id IN (%s, %s) OR user2_id IN (%s, %s))
            LIMIT 1
        """, (u1, u2, u1, u2))
        if cur.fetchone():
            return {"ok": False, "reason": "busy"}

        cur.execute("UPDATE chat_sessions SET status = 'active' WHERE id = %s", (session_id,))

        cur.execute("SELECT user_id, full_name, position, tonight_position FROM users WHERE user_id IN (%s, %s)", (u1, u2))
        users_map = {r["user_id"]: dict(r) for r in cur.fetchall()}

        lobby_id = session.get("lobby_id")
        can_approve = False
        lobby_title = ""
        if lobby_id:
            cur.execute("SELECT * FROM lobbies WHERE id = %s", (lobby_id,))
            lobby_row = cur.fetchone()
            if (
                lobby_row
                and lobby_row["status"] == "open"
                and lobby_row["current_players"] < lobby_row["max_players"]
                and lobby_row["creator_id"] == u2
            ):
                cur.execute(
                    "SELECT 1 FROM lobby_members WHERE lobby_id = %s AND user_id = %s",
                    (lobby_id, u1)
                )
                if cur.fetchone() is None:
                    can_approve = True
                    lobby_title = lobby_row["title"]

        return {
            "ok": True,
            "session": session,
            "user1": users_map.get(u1, {"full_name": "بازیکن ۱", "position": "آزاد"}),
            "user2": users_map.get(u2, {"full_name": "بازیکن ۲", "position": "آزاد"}),
            "lobby_id": lobby_id,
            "lobby_title": lobby_title,
            "can_approve": can_approve,
        }


def reject_chat_session_atomic(session_id: int, rejector_id: int) -> Dict:
    """رد ایمن درخواست چت فقط توسط گیرنده واقعی"""
    with get_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM chat_sessions WHERE id = %s FOR UPDATE", (session_id,))
        session = cur.fetchone()
        if not session or session["status"] != "pending":
            return {"ok": False, "reason": "expired"}

        session = dict(session)
        if session["user2_id"] != rejector_id:
            return {"ok": False, "reason": "unauthorized"}

        cur.execute("UPDATE chat_sessions SET status = 'ended' WHERE id = %s", (session_id,))
        cur.execute("SELECT full_name FROM users WHERE user_id = %s", (rejector_id,))
        target = cur.fetchone()
        return {
            "ok": True,
            "requester_id": session["user1_id"],
            "target_name": target["full_name"] if target else "بازیکن",
        }


def get_active_chat(user_id: int) -> Optional[Dict]:
    """دریافت اطلاعات چت فعال در یک کوئری واحد (بدون باز کردن اتصال دوم از Pool)"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                cs.id AS session_id,
                cs.lobby_id,
                cs.requested_position,
                CASE WHEN cs.user1_id = %s THEN cs.user2_id ELSE cs.user1_id END AS partner_id,
                COALESCE(p.full_name, 'بازیکن') AS partner_name,
                COALESCE(p.tonight_position, p.position, 'آزاد') AS partner_position,
                l.title AS lobby_title,
                l.status AS lobby_status,
                l.current_players AS lobby_current_players,
                l.max_players AS lobby_max_players,
                l.creator_id AS lobby_creator_id,
                EXISTS (
                    SELECT 1 FROM lobby_members lm
                    WHERE lm.lobby_id = cs.lobby_id
                      AND lm.user_id = CASE WHEN cs.user1_id = %s THEN cs.user2_id ELSE cs.user1_id END
                ) AS partner_already_in_lobby
            FROM chat_sessions cs
            LEFT JOIN users p
                ON p.user_id = CASE WHEN cs.user1_id = %s THEN cs.user2_id ELSE cs.user1_id END
            LEFT JOIN lobbies l
                ON l.id = cs.lobby_id
            WHERE cs.status = 'active'
              AND (cs.user1_id = %s OR cs.user2_id = %s)
            ORDER BY cs.id DESC
            LIMIT 1
        """, (user_id, user_id, user_id, user_id, user_id))
        row = cur.fetchone()
        if not row:
            return None

        can_approve = bool(
            row["lobby_id"]
            and row["lobby_status"] == "open"
            and row["lobby_current_players"] < row["lobby_max_players"]
            and row["lobby_creator_id"] == user_id
            and not row["partner_already_in_lobby"]
        )

        return {
            "session_id": row["session_id"],
            "partner_id": row["partner_id"],
            "partner_name": row["partner_name"],
            "partner_position": row["partner_position"],
            "lobby_id": row["lobby_id"],
            "lobby_title": row["lobby_title"],
            "requested_position": row["requested_position"],
            "can_approve_member": can_approve,
        }


def end_active_chat(user_id: int, keep_messages: bool = False) -> Optional[Dict]:
    active = get_active_chat(user_id)
    if not active:
        return None
    with get_cursor(commit=True) as cur:
        cur.execute("UPDATE chat_sessions SET status = 'ended' WHERE id = %s", (active["session_id"],))
        if not keep_messages:
            # حذف فوری پیام‌های موقت پس از پایان عادی چت برای حفظ حریم خصوصی
            cur.execute("DELETE FROM chat_messages WHERE session_id = %s", (active["session_id"],))
    return active


# =====================================================================
# ثبت شواهد ۵ پیام آخر چت برای گزارش تخلف و بازخوردها
# =====================================================================

def log_chat_message(session_id: int, sender_id: int, sender_name: str, content: str) -> None:
    snippet = (content or "").strip()[:300]
    if not snippet:
        return
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO chat_messages (session_id, sender_id, sender_name, content)
            VALUES (%s, %s, %s, %s)
        """, (session_id, sender_id, sender_name, snippet))
        # نگهداری حداکثر ۱۰ پیام آخر هر جلسه برای بهینه‌سازی فضا و حریم خصوصی
        cur.execute("""
            DELETE FROM chat_messages
            WHERE session_id = %s
              AND id NOT IN (
                  SELECT id FROM chat_messages
                  WHERE session_id = %s
                  ORDER BY id DESC
                  LIMIT 10
              )
        """, (session_id, session_id))


def get_recent_session_messages(session_id: int, limit: int = 5) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT sender_id, sender_name, content,
                   TO_CHAR(created_at, 'HH24:MI') AS time_str
            FROM (
                SELECT id, sender_id, sender_name, content, created_at
                FROM chat_messages
                WHERE session_id = %s
                ORDER BY id DESC
                LIMIT %s
            ) sub
            ORDER BY id ASC
        """, (session_id, limit))
        return [dict(r) for r in cur.fetchall()]


def purge_session_messages(session_id: int) -> None:
    with get_cursor(commit=True) as cur:
        cur.execute("DELETE FROM chat_messages WHERE session_id = %s", (session_id,))


def create_report(
    session_id: int,
    reporter_id: int,
    reported_id: int,
    reason: str = "مزاحمت در چت ناشناس",
    evidence: str = ""
) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO reports (session_id, reporter_id, reported_id, reason, evidence)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (session_id, reporter_id, reported_id, reason, evidence))
        return cur.fetchone()["id"]


def get_recent_reports(limit: int = 15) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT r.id, r.reporter_id, r.reported_id, r.reason, r.evidence,
                   COALESCE(u1.full_name, 'نامشخص') AS reporter_name,
                   COALESCE(u2.full_name, 'نامشخص') AS reported_name,
                   COALESCE(u2.is_banned, FALSE) AS reported_is_banned,
                   TO_CHAR(r.created_at, 'YYYY-MM-DD HH24:MI') AS created_str
            FROM reports r
            LEFT JOIN users u1 ON u1.user_id = r.reporter_id
            LEFT JOIN users u2 ON u2.user_id = r.reported_id
            ORDER BY r.id DESC
            LIMIT %s
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]


def save_feedback(user_id: int, user_name: str, message: str) -> int:
    with get_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO feedbacks (user_id, user_name, message)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (user_id, user_name, message))
        return cur.fetchone()["id"]


def get_recent_feedbacks(limit: int = 15) -> List[Dict]:
    with get_cursor() as cur:
        cur.execute("""
            SELECT id, user_id, user_name, message,
                   TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created_str
            FROM feedbacks
            ORDER BY id DESC LIMIT %s
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]


def get_bot_stats() -> Dict:
    expire_old_lobbies()
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE user_id >= 1000 AND is_registered = TRUE")
        real_users = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM users WHERE user_id >= 1000 AND is_available = TRUE")
        real_available = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM lobbies WHERE creator_id >= 1000 AND status = 'open'")
        real_open_lobbies = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM lobbies WHERE creator_id >= 1000 AND status = 'full'")
        real_full_lobbies = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM chat_sessions WHERE status = 'active'")
        active_chats = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM feedbacks")
        total_feedbacks = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM reports")
        total_reports = cur.fetchone()["c"]

    return {
        "real_users": real_users,
        "real_available": real_available,
        "real_lobbies": real_open_lobbies + real_full_lobbies,
        "real_open_lobbies": real_open_lobbies,
        "real_full_lobbies": real_full_lobbies,
        "active_chats": active_chats,
        "total_feedbacks": total_feedbacks,
        "total_reports": total_reports
    }
