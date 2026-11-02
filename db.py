import sqlite3
from typing import Dict, List, Optional, Tuple

# نام فایل دیتابیس که به صورت خودکار در پوشه پروژه ساخته می‌شود
DB_NAME = "venue_demo.db"


def get_connection() -> sqlite3.Connection:
    """برقراری اتصال امن به دیتابیس SQLite بدون تداخل تردها"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """ساخت ۴ جدول اصلی دیتابیس در صورت عدم وجود"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # ۱. جدول کاربران (بازیکنان، سرگروه‌ها و مدیر سالن) به همراه وضعیت ثبت‌نام
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,         -- آیدی عددی تلگرام کاربر
                full_name TEXT NOT NULL,             -- نام نمایشی یا ثبت‌نامی کاربر
                phone TEXT DEFAULT 'ثبت نشده',       -- شماره تماس کاربر
                role TEXT DEFAULT 'player',          -- نقش کاربر ('player' یا 'manager')
                skill_level TEXT DEFAULT 'متوسط',     -- سطح مهارت بازی
                position TEXT DEFAULT 'آزاد',         -- پست‌های تخصصی در زمین فوتسال
                is_available INTEGER DEFAULT 0,      -- وضعیت آمادگی امشب (0: غیرفعال، 1: آماده بازی)
                free_hours TEXT DEFAULT '۲۰ تا ۲۴',  -- ساعت آزاد بازیکن برای امشب
                is_registered INTEGER DEFAULT 0      -- وضعیت تکمیل ثبت‌نام اولیه (0: خیر، 1: بله)
            )
        """)

        # اطمینان از وجود ستون is_registered اگر فایل دیتابیس از قبل ساخته شده باشد
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_registered INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # ۲. جدول سانس‌های سالن ورزشی
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                day_label TEXT NOT NULL,
                time_range TEXT NOT NULL,
                price INTEGER NOT NULL,
                status TEXT DEFAULT 'free',
                booked_by_id INTEGER,
                booked_by_name TEXT,
                receipt_file_id TEXT
            )
        """)

        # ۳. جدول لابی‌های تیم‌یابی
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lobbies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slot_time TEXT NOT NULL,
                creator_id INTEGER NOT NULL,
                max_players INTEGER DEFAULT 6,
                current_players INTEGER DEFAULT 1,
                skill_req TEXT DEFAULT 'متوسط',
                status TEXT DEFAULT 'open'
            )
        """)

        # ۴. جدول لیست اعضای داخل هر لابی
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lobby_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lobby_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                player_name TEXT NOT NULL,
                position TEXT DEFAULT 'بازیکن',
                UNIQUE(lobby_id, user_id)
            )
        """)
        conn.commit()


def reset_demo_data() -> None:
    """ریست کردن دیتابیس و پر کردن آن با دیتای آماده جهت ارائه در جلسه دمو"""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM lobby_members")
        cursor.execute("DELETE FROM lobbies")
        cursor.execute("DELETE FROM slots")
        cursor.execute("DELETE FROM users WHERE user_id < 1000")

        # ۱. درج ۵ بازیکن فرضی که چراغ «آماده بازی امشب» را روشن کرده‌اند
        fake_players = [
            (101, "امیرحسین رضایی", "09121112233", "player", "حرفه‌ای", "دروازه‌بان 🧤", 1, "۱۹ تا ۲۳", 1),
            (102, "محمدامین کریمی", "09123334455", "player", "متوسط", "دفاع / عقب‌گیر 🛡️", 1, "۲۰ تا ۲۴", 1),
            (103, "سهراب مرادی", "09351112233", "player", "حرفه‌ای", "مهاجم (راس) ⚡", 1, "۱۸ تا ۲۲", 1),
            (104, "کیارش نادری", "09195556677", "player", "متوسط", "وینگر راست 🏃", 1, "۲۱ تا ۲۴", 1),
            (105, "پویا شمس", "09128889900", "player", "مبتدی", "دفاع چپ 🛡️", 1, "۱۹ تا ۲۲", 1),
        ]
        cursor.executemany("""
            INSERT INTO users (user_id, full_name, phone, role, skill_level, position, is_available, free_hours, is_registered)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, fake_players)

        # ۲. درج سانس‌های نمونه سالن برای امروز و فردا
        demo_slots = [
            ("امروز", "18:00 تا 19:30", 500000, "free", None, None, None),
            ("امروز", "19:30 تا 21:00", 600000, "closed", None, "رزرو تلفنی مدیر", None),
            ("امروز", "21:00 تا 22:30", 650000, "pending", 101, "امیرحسین رضایی", "DEMO_RECEIPT"),
            ("امروز", "22:30 تا 24:۰۰", 550000, "free", None, None, None),
            ("فردا", "18:00 تا 19:30", 500000, "free", None, None, None),
            ("فردا", "19:30 تا 21:00", 650000, "free", None, None, None),
        ]
        cursor.executemany("""
            INSERT INTO slots (day_label, time_range, price, status, booked_by_id, booked_by_name, receipt_file_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, demo_slots)

        # ۳. درج ۲ لابی نمونه
        cursor.execute("""
            INSERT INTO lobbies (id, title, slot_time, creator_id, max_players, current_players, skill_req, status)
            VALUES 
            (1, 'فوتسال ۵ به ۵ (تیم ناقص - ۱ نفر کم)', 'امشب ساعت ۲۱:۰۰ تا ۲۲:۳۰', 101, 6, 5, 'متوسط به بالا', 'open'),
            (2, 'لابی عمومی فوتسال (افراد تکی)', 'امشب ساعت ۲۲:۳۰ تا ۲۴:۰۰', 102, 12, 8, 'آزاد / دوستانه', 'open')
        """)

        lobby1_members = [
            (1, 101, "امیرحسین رضایی", "دروازه‌بان 🧤"),
            (1, 102, "محمدامین کریمی", "عقب‌گیر 🛡️"),
            (1, 103, "سهراب مرادی", "مهاجم ⚡"),
            (1, 104, "کیارش نادری", "وینگر راست 🏃"),
            (1, 105, "پویا شمس", "دفاع چپ 🛡️"),
        ]
        cursor.executemany("""
            INSERT INTO lobby_members (lobby_id, user_id, player_name, position)
            VALUES (?, ?, ?, ?)
        """, lobby1_members)

        conn.commit()


# =====================================================================
# توابع بخش کاربران، ثبت‌نام و تغییر نقش
# =====================================================================

def upsert_user(user_id: int, full_name: str) -> Dict:
    """بررسی وجود کاربر در دیتابیس؛ اگر وجود نداشت او را ثبت می‌کند"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO users (user_id, full_name, is_registered) VALUES (?, ?, 0)", (user_id, full_name))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
        return dict(row)


def complete_user_registration(user_id: int, full_name: str, phone: str, position: str) -> Dict:
    """ذخیره اطلاعات ثبت‌نام کاربر (نام، شماره تماس و پست‌های تخصصی)"""
    upsert_user(user_id, full_name)
    with get_connection() as conn:
        conn.execute("""
            UPDATE users 
            SET full_name = ?, phone = ?, position = ?, is_registered = 1
            WHERE user_id = ?
        """, (full_name, phone, position, user_id))
        conn.commit()
    return upsert_user(user_id, full_name)


def set_user_role(user_id: int, role: str) -> None:
    """تغییر نقش کاربر بین بازیکن (player) و مدیر سالن (manager)"""
    with get_connection() as conn:
        conn.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        conn.commit()


def update_user_availability(user_id: int, is_available: int, position: str = "آزاد", free_hours: str = "۲۰ تا ۲۴") -> None:
    """تغییر وضعیت آمادگی بازیکن برای بازی امشب و ذخیره پست تخصصی او"""
    with get_connection() as conn:
        conn.execute("""
            UPDATE users SET is_available = ?, position = ?, free_hours = ? WHERE user_id = ?
        """, (is_available, position, free_hours, user_id))
        conn.commit()


def get_available_players() -> List[Dict]:
    """برگرداندن لیست تمام بازیکنانی که برای امشب اعلام آمادگی کرده‌اند"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE is_available = 1 ORDER BY user_id ASC")
        return [dict(row) for row in cursor.fetchall()]


# =====================================================================
# توابع بخش سانس‌های سالن و پنل مدیر سالن
# =====================================================================

def get_slots() -> List[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM slots ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_slot_by_id(slot_id: int) -> Optional[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM slots WHERE id = ?", (slot_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def toggle_slot_by_manager(slot_id: int) -> Optional[str]:
    slot = get_slot_by_id(slot_id)
    if not slot:
        return None
    new_status = "closed" if slot["status"] == "free" else "free"
    booked_name = "رزرو تلفنی مدیر" if new_status == "closed" else None
    with get_connection() as conn:
        conn.execute(
            "UPDATE slots SET status = ?, booked_by_name = ? WHERE id = ?",
            (new_status, booked_name, slot_id)
        )
        conn.commit()
    return new_status


def add_new_slot(day_label: str, time_range: str, price: int) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO slots (day_label, time_range, price, status) VALUES (?, ?, ?, 'free')",
            (day_label, time_range, price)
        )
        conn.commit()
        return cursor.lastrowid


def submit_booking_receipt(slot_id: int, user_id: int, user_name: str, receipt_info: str) -> bool:
    slot = get_slot_by_id(slot_id)
    if not slot or slot["status"] != "free":
        return False
    with get_connection() as conn:
        conn.execute("""
            UPDATE slots 
            SET status = 'pending', booked_by_id = ?, booked_by_name = ?, receipt_file_id = ?
            WHERE id = ?
        """, (user_id, user_name, receipt_info, slot_id))
        conn.commit()
    return True


def get_pending_slots() -> List[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM slots WHERE status = 'pending'")
        return [dict(row) for row in cursor.fetchall()]


def verify_booking_by_manager(slot_id: int, approve: bool) -> Optional[Dict]:
    slot = get_slot_by_id(slot_id)
    if not slot:
        return None
    with get_connection() as conn:
        if approve:
            conn.execute("UPDATE slots SET status = 'booked' WHERE id = ?", (slot_id,))
        else:
            conn.execute("""
                UPDATE slots 
                SET status = 'free', booked_by_id = NULL, booked_by_name = NULL, receipt_file_id = NULL 
                WHERE id = ?
            """, (slot_id,))
        conn.commit()
    return get_slot_by_id(slot_id)


# =====================================================================
# توابع بخش لابی‌های تیم‌یابی (Matchmaking)
# =====================================================================

def get_open_lobbies() -> List[Dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lobbies ORDER BY id ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_lobby_with_members(lobby_id: int) -> Tuple[Optional[Dict], List[Dict]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lobbies WHERE id = ?", (lobby_id,))
        lobby_row = cursor.fetchone()
        if not lobby_row:
            return None, []
        cursor.execute("SELECT * FROM lobby_members WHERE lobby_id = ?", (lobby_id,))
        members = [dict(r) for r in cursor.fetchall()]
        return dict(lobby_row), members


def create_new_lobby(title: str, slot_time: str, creator_id: int, creator_name: str, max_players: int = 6, initial_count: int = 1) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO lobbies (title, slot_time, creator_id, max_players, current_players, status)
            VALUES (?, ?, ?, ?, ?, 'open')
        """, (title, slot_time, creator_id, max_players, initial_count))
        lobby_id = cursor.lastrowid
        cursor.execute("""
            INSERT OR IGNORE INTO lobby_members (lobby_id, user_id, player_name, position)
            VALUES (?, ?, ?, 'سرگروه ⭐')
        """, (lobby_id, creator_id, creator_name))
        conn.commit()
        return lobby_id


def join_lobby(lobby_id: int, user_id: int, player_name: str, position: str = "بازیکن آزاد") -> Dict:
    lobby, members = get_lobby_with_members(lobby_id)
    if not lobby:
        return {"ok": False, "reason": "not_found"}
    if lobby["status"] == "full" or lobby["current_players"] >= lobby["max_players"]:
        return {"ok": False, "reason": "already_full", "lobby": lobby}

    for m in members:
        if m["user_id"] == user_id:
            return {"ok": False, "reason": "already_joined", "lobby": lobby}

    new_count = lobby["current_players"] + 1
    new_status = "full" if new_count >= lobby["max_players"] else "open"

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO lobby_members (lobby_id, user_id, player_name, position)
            VALUES (?, ?, ?, ?)
        """, (lobby_id, user_id, player_name, position))
        conn.execute("""
            UPDATE lobbies SET current_players = ?, status = ? WHERE id = ?
        """, (new_count, new_status, lobby_id))
        conn.commit()

    updated_lobby, updated_members = get_lobby_with_members(lobby_id)
    return {
        "ok": True,
        "just_became_full": (new_status == "full"),
        "lobby": updated_lobby,
        "members": updated_members
    }


if __name__ == "__main__":
    reset_demo_data()
    print("✅ فایل دیتابیس (venue_demo.db) با موفقیت ساخته و با دیتای دمو پر شد!")