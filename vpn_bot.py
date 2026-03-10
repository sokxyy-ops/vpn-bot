import asyncio
import os
import time
import sqlite3
from typing import Optional, List, Tuple, Dict, Any, Callable, Awaitable

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    FSInputFile
)
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "orders.sqlite")

# ================== PATHS ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANNER_PATH = os.path.join(BASE_DIR, os.getenv("BANNER_PATH", "banner.jpg"))

# ================== LINKS ==================
TG_CHANNEL = "https://t.me/sokxyybc"
PRIVATE_GROUP_LINK = "https://t.me/+6ahhnSMk7740NmQy"
REVIEW_LINK = "https://t.me/sokxyybc/23"
AGREEMENT_URL = "https://telegra.ph/Soglashenie-03-10-3"

HAPP_ANDROID_URL = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_IOS_URL = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"
HAPP_WINDOWS_URL = "https://happ.su/"

# ================== PAYMENT ==================
PAYMENT_TEXT = (
    "💳 *Оплата*\n\n"
    "✅ *Карта:*\n"
    "`2204320913014587`\n\n"
    "🔁 *Если есть комиссия — переводи через Ozon по номеру:*\n"
    "`+79951253391`\n\n"
    "📎 После оплаты отправь сюда *чек / скрин*.\n"
    "Я проверю — бот выдаст ключ 🔑"
)

# ================== LEGACY KEY FILES ==================
STANDARD_KEYS_FILE = os.path.join(BASE_DIR, "standard_keys.txt")
FAMILY_KEYS_FILE = os.path.join(BASE_DIR, "family_keys.txt")

# ================== RESEND LIMITS ==================
RESEND_COOLDOWN_SEC = 10 * 60
RESEND_MAX = 3

# ================== PAGINATION ==================
USERS_PAGE_SIZE = 10

# ================== BOT ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(storage=MemoryStorage())


# ================== FSM ==================
class AdminStates(StatesGroup):
    broadcast_wait = State()
    price_wait = State()
    keys_wait = State()
    search_wait = State()


# ================== DB ==================
def db():
    return sqlite3.connect(DB_PATH)


def _add_column_if_missing(con: sqlite3.Connection, table: str, col: str, ddl: str):
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cur.fetchall()}
    if col not in cols:
        cur.execute(ddl)
        con.commit()


def _ensure_table(con: sqlite3.Connection, ddl: str):
    cur = con.cursor()
    cur.execute(ddl)
    con.commit()


def _settings_set_if_missing(con: sqlite3.Connection, key: str, value: str):
    cur = con.cursor()
    cur.execute("SELECT 1 FROM settings WHERE key=? LIMIT 1", (key,))
    if not cur.fetchone():
        cur.execute("INSERT INTO settings(key,value) VALUES(?,?)", (key, value))
        con.commit()


def db_init():
    con = db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    con.commit()

    _add_column_if_missing(con, "orders", "payment_msg_id", "ALTER TABLE orders ADD COLUMN payment_msg_id INTEGER")
    _add_column_if_missing(con, "orders", "issued_key", "ALTER TABLE orders ADD COLUMN issued_key TEXT")
    _add_column_if_missing(con, "orders", "accepted_at", "ALTER TABLE orders ADD COLUMN accepted_at INTEGER")
    _add_column_if_missing(con, "orders", "admin_msg_id", "ALTER TABLE orders ADD COLUMN admin_msg_id INTEGER")
    _add_column_if_missing(con, "orders", "resend_count", "ALTER TABLE orders ADD COLUMN resend_count INTEGER DEFAULT 0")
    _add_column_if_missing(con, "orders", "last_resend_at", "ALTER TABLE orders ADD COLUMN last_resend_at INTEGER DEFAULT 0")

    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_seen INTEGER NOT NULL,
            is_blocked INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    _add_column_if_missing(con, "users", "is_blocked", "ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
    _add_column_if_missing(con, "users", "is_banned", "ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")

    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    _settings_set_if_missing(con, "price_standard", "200")
    _settings_set_if_missing(con, "price_family", "310")

    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS keys_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan TEXT NOT NULL,
            key TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            used_at INTEGER,
            order_id INTEGER
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_keys_unique ON keys_store(plan, key)")
    con.commit()

    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS profit_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cur.execute("INSERT OR IGNORE INTO profit_meta(key, value) VALUES('profit_offset', '0')")
    con.commit()

    con.close()


def db_settings_get(key: str, default: Optional[str] = None) -> Optional[str]:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default
    finally:
        con.close()


def db_settings_set(key: str, value: str):
    con = db()
    try:
        cur = con.cursor()
        cur.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
        con.commit()
    finally:
        con.close()


def db_upsert_user(user_id: int, username: Optional[str], first_name: Optional[str], last_seen: Optional[int] = None):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO users(user_id, username, first_name, last_seen, is_blocked, is_banned)
            VALUES(?,?,?,?,0,0)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_seen=excluded.last_seen
        """, (user_id, username or "", first_name or "", int(last_seen or time.time())))
        con.commit()
    finally:
        con.close()


def db_mark_blocked(user_id: int, blocked: bool):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if blocked else 0, user_id))
        con.commit()
    finally:
        con.close()


def db_is_banned(user_id: int) -> bool:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COALESCE(is_banned,0) FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        return bool(row and int(row[0] or 0) == 1)
    finally:
        con.close()


def db_set_banned(user_id: int, banned: bool):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO users(user_id, username, first_name, last_seen, is_blocked, is_banned)
            VALUES(?, '', '', ?, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                is_banned=excluded.is_banned,
                last_seen=excluded.last_seen
        """, (user_id, int(time.time()), 1 if banned else 0))
        con.commit()
    finally:
        con.close()


def db_ban_user_and_revoke(user_id: int):
    con = db()
    try:
        cur = con.cursor()

        cur.execute("""
            UPDATE orders
            SET status='revoked', issued_key=NULL
            WHERE user_id=? AND status='accepted'
        """, (user_id,))

        cur.execute("""
            UPDATE orders
            SET status='cancelled'
            WHERE user_id=? AND status IN ('waiting_receipt','pending_admin')
        """, (user_id,))

        cur.execute("""
            INSERT INTO users(user_id, username, first_name, last_seen, is_blocked, is_banned)
            VALUES(?, '', '', ?, 0, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                is_banned=1,
                last_seen=excluded.last_seen
        """, (user_id, int(time.time())))

        con.commit()
    finally:
        con.close()


def db_unban_user(user_id: int):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            UPDATE users
            SET is_banned=0,
                last_seen=?
            WHERE user_id=?
        """, (int(time.time()), user_id))
        con.commit()
    finally:
        con.close()


def db_list_users_for_broadcast() -> List[int]:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT user_id FROM users WHERE COALESCE(is_blocked,0)=0 AND COALESCE(is_banned,0)=0")
        return [r[0] for r in cur.fetchall()]
    finally:
        con.close()


def db_users_stats() -> Dict[str, int]:
    now = int(time.time())
    day_ago = now - 24 * 3600
    week_ago = now - 7 * 24 * 3600

    con = db()
    try:
        cur = con.cursor()

        cur.execute("SELECT COUNT(*) FROM users")
        total = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COUNT(*) FROM users WHERE COALESCE(is_blocked,0)=1")
        blocked = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COUNT(*) FROM users WHERE COALESCE(is_banned,0)=1")
        banned = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COUNT(*) FROM users WHERE last_seen>=?", (day_ago,))
        active_day = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COUNT(*) FROM users WHERE last_seen>=?", (week_ago,))
        active_week = int(cur.fetchone()[0] or 0)

        return {
            "total": total,
            "blocked": blocked,
            "banned": banned,
            "active_day": active_day,
            "active_week": active_week,
        }
    finally:
        con.close()


def db_list_users(limit: int = 20, offset: int = 0):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_seen, is_blocked, is_banned
            FROM users
            ORDER BY last_seen DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return cur.fetchall()
    finally:
        con.close()


def db_list_banned_users(limit: int = 20, offset: int = 0):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_seen, is_blocked, is_banned
            FROM users
            WHERE COALESCE(is_banned,0)=1
            ORDER BY last_seen DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return cur.fetchall()
    finally:
        con.close()


def db_count_users() -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return int(cur.fetchone()[0] or 0)
    finally:
        con.close()


def db_count_banned_users() -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM users WHERE COALESCE(is_banned,0)=1")
        return int(cur.fetchone()[0] or 0)
    finally:
        con.close()


def db_get_user(user_id: int):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT user_id, username, first_name, last_seen, is_blocked, is_banned
            FROM users
            WHERE user_id=?
        """, (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "username": row[1],
            "first_name": row[2],
            "last_seen": row[3],
            "is_blocked": row[4] or 0,
            "is_banned": row[5] or 0,
        }
    finally:
        con.close()


def db_get_active_order(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, status, payment_msg_id, admin_msg_id, resend_count, last_resend_at
        FROM orders
        WHERE user_id=? AND status IN ('waiting_receipt','pending_admin')
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "id": row[0],
        "plan": row[1],
        "amount": row[2],
        "status": row[3],
        "payment_msg_id": row[4],
        "admin_msg_id": row[5],
        "resend_count": row[6] or 0,
        "last_resend_at": row[7] or 0,
    }


def db_create_order(user_id: int, username: Optional[str], plan: str, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders(
            user_id, username, plan, amount, status, created_at,
            payment_msg_id, issued_key, accepted_at, admin_msg_id,
            resend_count, last_resend_at
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        user_id, username or "", plan, amount, "waiting_receipt", int(time.time()),
        None, None, None, None, 0, 0
    ))
    con.commit()
    order_id = cur.lastrowid
    con.close()
    return order_id


def db_set_status(order_id: int, status: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    con.commit()
    con.close()


def db_set_payment_msg(order_id: int, msg_id: Optional[int]):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET payment_msg_id=? WHERE id=?", (msg_id, order_id))
    con.commit()
    con.close()


def db_set_admin_msg(order_id: int, msg_id: Optional[int]):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET admin_msg_id=? WHERE id=?", (msg_id, order_id))
    con.commit()
    con.close()


def db_set_issued(order_id: int, key: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET issued_key=?, accepted_at=? WHERE id=?", (key, int(time.time()), order_id))
    con.commit()
    con.close()


def db_get_order(order_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, user_id, username, plan, amount, status,
               payment_msg_id, issued_key, accepted_at, admin_msg_id,
               resend_count, last_resend_at, created_at
        FROM orders WHERE id=?
    """, (order_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "username": row[2],
        "plan": row[3],
        "amount": row[4],
        "status": row[5],
        "payment_msg_id": row[6],
        "issued_key": row[7],
        "accepted_at": row[8],
        "admin_msg_id": row[9],
        "resend_count": row[10] or 0,
        "last_resend_at": row[11] or 0,
        "created_at": row[12],
    }


def db_get_accepted_subscriptions(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, issued_key, accepted_at
        FROM orders
        WHERE user_id=? AND status='accepted'
        ORDER BY accepted_at DESC, id DESC
    """, (user_id,))
    rows = cur.fetchall()
    con.close()

    result = []
    seen_plans = set()

    for row in rows:
        plan = row[1]
        if plan in seen_plans:
            continue
        seen_plans.add(plan)
        result.append({
            "id": row[0],
            "plan": row[1],
            "amount": row[2],
            "issued_key": row[3],
            "accepted_at": row[4],
        })
    return result


def db_update_user_plan_key(user_id: int, plan: str, new_key: str) -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            UPDATE orders
            SET issued_key=?
            WHERE user_id=? AND plan=? AND status='accepted'
        """, (new_key, user_id, plan))
        con.commit()
        return cur.rowcount or 0
    finally:
        con.close()


def db_count_user_subscriptions(user_id: int) -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT plan
                FROM orders
                WHERE user_id=? AND status='accepted'
            )
        """, (user_id,))
        return int(cur.fetchone()[0] or 0)
    finally:
        con.close()


def db_list_pending(limit: int = 20):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, user_id, username, plan, amount, created_at
        FROM orders
        WHERE status='pending_admin'
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    con.close()
    return rows


def db_can_resend(order_id: int):
    order = db_get_order(order_id)
    if not order:
        return False, "Заказ не найден"

    if order["status"] not in ("waiting_receipt", "pending_admin"):
        return False, "Этот заказ уже закрыт"

    if order["resend_count"] >= RESEND_MAX:
        return False, f"Лимит пересылок достигнут ({RESEND_MAX})"

    now = int(time.time())
    last = int(order["last_resend_at"] or 0)
    if now - last < RESEND_COOLDOWN_SEC:
        left = RESEND_COOLDOWN_SEC - (now - last)
        mins = max(1, left // 60)
        return False, f"Подожди ещё ~{mins} мин"

    return True, "OK"


def db_mark_resend(order_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        UPDATE orders
        SET resend_count = COALESCE(resend_count,0) + 1,
            last_resend_at = ?
        WHERE id=?
    """, (int(time.time()), order_id))
    con.commit()
    con.close()


def db_profit_offset_get() -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT value FROM profit_meta WHERE key='profit_offset'")
        row = cur.fetchone()
        return int(row[0]) if row and str(row[0]).isdigit() else 0
    finally:
        con.close()


def db_profit_reset():
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted'")
        total = int(cur.fetchone()[0] or 0)
        cur.execute("""
            INSERT INTO profit_meta(key, value) VALUES('profit_offset', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (str(total),))
        con.commit()
    finally:
        con.close()


def db_profit_totals() -> Dict[str, int]:
    now = int(time.time())
    day_ago = now - 24 * 3600
    week_ago = now - 7 * 24 * 3600
    month_ago = now - 30 * 24 * 3600

    con = db()
    try:
        cur = con.cursor()

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted'")
        total_raw = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted' AND accepted_at>=?", (day_ago,))
        day = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted' AND accepted_at>=?", (week_ago,))
        week = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted' AND accepted_at>=?", (month_ago,))
        month = int(cur.fetchone()[0] or 0)

        offset = db_profit_offset_get()
        total = max(0, total_raw - offset)

        return {"total": total, "day": day, "week": week, "month": month}
    finally:
        con.close()


def db_search_orders(query: str, limit: int = 10) -> List[Tuple]:
    q = (query or "").strip()
    if not q:
        return []

    if q.startswith("#"):
        q = q[1:].strip()

    username_query = q[1:].strip() if q.startswith("@") else q

    con = db()
    try:
        cur = con.cursor()

        if q.isdigit():
            num = int(q)

            cur.execute("""
                SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
                FROM orders
                WHERE id=?
                LIMIT 1
            """, (num,))
            rows = cur.fetchall()
            if rows:
                return rows

            cur.execute("""
                SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
                FROM orders
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
            """, (num, limit))
            rows = cur.fetchall()
            if rows:
                return rows

        cur.execute("""
            SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
            FROM orders
            WHERE LOWER(COALESCE(username, '')) = LOWER(?)
            ORDER BY id DESC
            LIMIT ?
        """, (username_query, limit))
        rows = cur.fetchall()
        if rows:
            return rows

        cur.execute("""
            SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
            FROM orders
            WHERE LOWER(COALESCE(username, '')) LIKE LOWER(?)
            ORDER BY id DESC
            LIMIT ?
        """, (f"%{username_query}%", limit))
        rows = cur.fetchall()
        if rows:
            return rows

        cur.execute("""
            SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
            FROM orders
            WHERE LOWER(plan) LIKE LOWER(?) OR LOWER(status) LIKE LOWER(?)
            ORDER BY id DESC
            LIMIT ?
        """, (f"%{q}%", f"%{q}%", limit))
        return cur.fetchall()
    finally:
        con.close()


# ================== KEYS ==================
def db_keys_count(plan: str) -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM keys_store WHERE plan=?", (plan,))
        return int(cur.fetchone()[0] or 0)
    finally:
        con.close()


def db_keys_add(plan: str, keys: List[str]) -> Tuple[int, int]:
    con = db()
    try:
        cur = con.cursor()
        added, skipped = 0, 0
        for k in keys:
            k = k.strip()
            if not k:
                continue
            cur.execute(
                "INSERT OR IGNORE INTO keys_store(plan, key, used, used_at, order_id) VALUES(?,?,0,NULL,NULL)",
                (plan, k)
            )
            if cur.rowcount == 1:
                added += 1
            else:
                skipped += 1
        con.commit()
        return added, skipped
    finally:
        con.close()


def db_keys_clear(plan: str):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM keys_store WHERE plan=?", (plan,))
        con.commit()
    finally:
        con.close()


def take_key(plan: str, order_id: int = 0) -> Optional[str]:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT key FROM keys_store WHERE plan=? ORDER BY id ASC LIMIT 1", (plan,))
        row = cur.fetchone()
        if not row:
            return None
        return row[0]
    finally:
        con.close()


def get_latest_key_for_plan(plan: str) -> Optional[str]:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT key
            FROM keys_store
            WHERE plan=?
            ORDER BY id DESC
            LIMIT 1
        """, (plan,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        con.close()


def import_keys_from_files_if_empty():
    std = db_keys_count("standard")
    fam = db_keys_count("family")

    if std == 0 and os.path.exists(STANDARD_KEYS_FILE):
        with open(STANDARD_KEYS_FILE, "r", encoding="utf-8") as f:
            keys = [x.strip() for x in f.read().splitlines() if x.strip()]
        if keys:
            db_keys_add("standard", keys)

    if fam == 0 and os.path.exists(FAMILY_KEYS_FILE):
        with open(FAMILY_KEYS_FILE, "r", encoding="utf-8") as f:
            keys = [x.strip() for x in f.read().splitlines() if x.strip()]
        if keys:
            db_keys_add("family", keys)


# ================== PLANS ==================
def plan_meta(plan: str):
    price_standard = int(db_settings_get("price_standard", "200") or 200)
    price_family = int(db_settings_get("price_family", "310") or 310)

    if plan == "standard":
        return "🟩 Стандарт", "👤 1 пользователь • 📱 до 3 устройств", "3", price_standard
    return "🟦 Семейная", "👥 до 8 пользователей • 📱 до 3 устройств каждому", "3", price_family


# ================== UI TEXT ==================
def text_menu():
    return (
        "⚡ *sokxyy обход VPN*\n\n"
        "🛡 Обычный VPN + режим обхода блокировок\n"
        "♾ Доступ *навсегда*\n"
        "🔑 Выдача подписки для *Happ* после оплаты\n\n"
        "👇 Выбери действие ниже"
    )


def text_buy_intro():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return (
        "🛒 *Покупка подписки*\n\n"
        f"🟩 *Стандарт* — 1 пользователь • до 3 устройств — *{std_price}₽*\n"
        f"🟦 *Семейная* — до 8 пользователей • до 3 устройств каждому — *{fam_price}₽*\n\n"
        "Выбери тариф ниже 👇"
    )


def text_subscription_card(from_user, subs: Optional[list]):
    name = (from_user.first_name or "—").strip()
    uid = from_user.id

    if not subs:
        return (
            "👤 *Профиль:*\n"
            f"> Имя: {name}\n"
            f"> ID: {uid}\n\n"
            "🔗 *Подписки:*\n"
            "> Нет активных подписок\n\n"
            "Нажми *Купить подписку* 👇"
        )

    parts = [
        "👤 *Профиль:*",
        f"> Имя: {name}",
        f"> ID: {uid}",
        "",
        "🔗 *Ваши подписки:*",
    ]

    for idx, sub in enumerate(subs, start=1):
        plan_name, conditions, device_limit, _amount = plan_meta(sub["plan"])
        key = sub.get("issued_key") or "—"

        parts.extend([
            "",
            f"*{idx}. {plan_name}*",
            f"> Ключ: `{key}`",
            f"> Срок: ♾ Навсегда",
            f"> {conditions}",
            f"> Лимит устройств: {device_limit}",
            f"> Выдано: {fmt_ts(sub.get('accepted_at'))}",
        ])

    parts.extend(["", "👇 Используй кнопки ниже"])
    return "\n".join(parts)


def fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(int(ts)))
    except Exception:
        return "—"


# ================== KEYBOARDS ==================
def kb_reply_menu(user_id: int):
    active = db_get_active_order(user_id)
    rows = [[KeyboardButton(text="📋 Меню"), KeyboardButton(text="🧾 Моя подписка")]]

    if active:
        rows.append([KeyboardButton(text="❌ Отменить заказ")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_main(user_id: int):
    active = db_get_active_order(user_id)
    rows = [
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")],
        [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="menu:sub")],
    ]

    if active:
        rows.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data="menu:cancel_order")])

    rows.append([InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_buy():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟩 Стандарт — {std_price}₽ (1 пользователь • до 3 устройств)", callback_data="buy:standard")],
        [InlineKeyboardButton(text=f"🟦 Семейная — {fam_price}₽ (до 8 пользователей • до 3 устройств)", callback_data="buy:family")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])


def kb_agreement(plan: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Открыть соглашение", url=AGREEMENT_URL)],
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"agree:{plan}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy")],
    ])


def kb_payment(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{order_id}")],
        [InlineKeyboardButton(text="🔁 Переслать админу", callback_data=f"resend:{order_id}")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])


def kb_admin_decision(order_id: int):
    order = db_get_order(order_id)
    keyboard = [
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:ok:{order_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}")]
    ]
    if order:
        keyboard.append([InlineKeyboardButton(text="⛔ Бан", callback_data=f"admin:ban:{order['user_id']}:users:0")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_after_issue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Happ (Android)", url=HAPP_ANDROID_URL)],
        [InlineKeyboardButton(text="🍎 Happ (iOS)", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Happ (Windows)", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])


def kb_sub_no_sub(user_id: int):
    rows = [[InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")]]

    active = db_get_active_order(user_id)
    if active:
        rows.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data="menu:cancel_order")])

    rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_sub_with_refresh(user_id: int):
    rows = [[InlineKeyboardButton(text="🔄 Обновить подписку", callback_data="sub:refresh")]]

    active = db_get_active_order(user_id)
    if active:
        rows.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data="menu:cancel_order")])

    rows.extend([
        [InlineKeyboardButton(text="📱 Happ (Android)", url=HAPP_ANDROID_URL)],
        [InlineKeyboardButton(text="🍎 Happ (iOS)", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Happ (Windows)", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Заказы", callback_data="admin:list"),
         InlineKeyboardButton(text="🔎 Поиск", callback_data="admin:search")],
        [InlineKeyboardButton(text="💰 Прибыль", callback_data="admin:profit"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🏷 Цены", callback_data="admin:prices"),
         InlineKeyboardButton(text="🔑 Ключи", callback_data="admin:keys")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users:0"),
         InlineKeyboardButton(text="⛔ Заблокированные", callback_data="admin:banned:0")],
    ])


def kb_admin_list(rows):
    keyboard = []
    for oid, uid, uname, plan, amount, created_at in rows[:20]:
        u = f"@{uname}" if uname else str(uid)
        keyboard.append([InlineKeyboardButton(
            text=f"🧾 #{oid} • {plan} • {amount}₽ • {u}",
            callback_data=f"admin:view:{oid}"
        )])
    keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:list"),
        InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_admin_prices():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟩 Стандарт: {std_price}₽", callback_data="admin:price:set:standard")],
        [InlineKeyboardButton(text=f"🟦 Семейная: {fam_price}₽", callback_data="admin:price:set:family")],
        [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
    ])


def kb_admin_keys():
    s = db_keys_count("standard")
    f = db_keys_count("family")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Добавить 🟩 (в базе {s})", callback_data="admin:keys:add:standard")],
        [InlineKeyboardButton(text=f"➕ Добавить 🟦 (в базе {f})", callback_data="admin:keys:add:family")],
        [InlineKeyboardButton(text="🧹 Очистить 🟩", callback_data="admin:keys:clear:standard"),
         InlineKeyboardButton(text="🧹 Очистить 🟦", callback_data="admin:keys:clear:family")],
        [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
    ])


def kb_confirm_clear(plan: str):
    title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Да, очистить {title}", callback_data=f"admin:keys:clear_yes:{plan}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin:keys")],
    ])


def kb_admin_profit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♻️ Сбросить прибыль", callback_data="admin:profit:reset")],
        [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
    ])


def _user_button_title(user_id, username, first_name, is_blocked, is_banned):
    name = first_name or "—"
    uname = f"@{username}" if username else "—"
    status = "⛔" if is_banned else ("🚫" if is_blocked else "✅")
    title = f"{status} {name} • {uname} • {user_id}"
    return title[:60] if len(title) <= 60 else title[:57] + "..."


def kb_admin_users_page(rows, page: int, total: int, mode: str):
    keyboard = []

    for user_id, username, first_name, last_seen, is_blocked, is_banned in rows:
        keyboard.append([InlineKeyboardButton(
            text=_user_button_title(user_id, username, first_name, is_blocked, is_banned),
            callback_data=f"admin:user:{user_id}:{mode}:{page}"
        )])

    nav = []
    max_page = max(0, (total - 1) // USERS_PAGE_SIZE) if total > 0 else 0

    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin:{mode}:{page - 1}"))

    nav.append(InlineKeyboardButton(text=f"{page + 1}/{max_page + 1}", callback_data="noop"))

    if page < max_page:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"admin:{mode}:{page + 1}"))

    if nav:
        keyboard.append(nav)

    keyboard.append([InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_admin_user_view(user_id: int, mode: str, page: int):
    user = db_get_user(user_id)
    buttons = []

    if user:
        if user.get("is_banned"):
            buttons.append([InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin:unban:{user_id}:{mode}:{page}")])
        else:
            buttons.append([InlineKeyboardButton(text="⛔ Забанить и аннулировать подписку", callback_data=f"admin:ban:{user_id}:{mode}:{page}")])

    back_target = "users" if mode == "users" else "banned"
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:{back_target}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ================== MIDDLEWARE ==================
class TrackUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message) and event.from_user:
                db_upsert_user(
                    event.from_user.id,
                    event.from_user.username,
                    event.from_user.first_name,
                    int(time.time())
                )
            elif isinstance(event, CallbackQuery) and event.from_user:
                db_upsert_user(
                    event.from_user.id,
                    event.from_user.username,
                    event.from_user.first_name,
                    int(time.time())
                )
        except Exception:
            pass
        return await handler(event, data)


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if not from_user:
            return await handler(event, data)

        if from_user.id == ADMIN_ID:
            return await handler(event, data)

        try:
            if db_is_banned(from_user.id):
                if isinstance(event, Message):
                    await event.answer("⛔ Ты заблокирован и не можешь пользоваться ботом.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔ Ты заблокирован", show_alert=True)
                return
        except Exception:
            pass

        return await handler(event, data)


dp.message.middleware(TrackUserMiddleware())
dp.callback_query.middleware(TrackUserMiddleware())

dp.message.middleware(BanMiddleware())
dp.callback_query.middleware(BanMiddleware())


# ================== HELPERS ==================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def send_banner_or_text(chat_id: int, text: str, reply_markup=None):
    try:
        if os.path.exists(BANNER_PATH):
            await bot.send_photo(chat_id, FSInputFile(BANNER_PATH), caption=text, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)


async def send_check_to_admin(order_id: int, user_id: int, username: Optional[str], plan: str, amount: int):
    safe_username = f"@{username}" if username else "—"

    text = (
        "🔔 Чек на проверку\n\n"
        f"🧾 Заказ: #{order_id}\n"
        f"👤 Пользователь: {user_id} ({safe_username})\n"
        f"📦 Тариф: {plan}\n"
        f"💰 Сумма: {amount}₽\n\n"
        "Принять оплату?"
    )

    msg = await bot.send_message(
        ADMIN_ID,
        text,
        reply_markup=kb_admin_decision(order_id),
        parse_mode=None,
    )
    db_set_admin_msg(order_id, msg.message_id)
    return msg


async def refresh_reply_menu(chat_id: int, user_id: int):
    try:
        await bot.send_message(chat_id, " ", reply_markup=kb_reply_menu(user_id))
    except Exception:
        pass


async def send_admin_users_page(call: CallbackQuery, page: int, banned_only: bool):
    page = max(0, page)
    offset = page * USERS_PAGE_SIZE

    if banned_only:
        rows = db_list_banned_users(limit=USERS_PAGE_SIZE, offset=offset)
        total = db_count_banned_users()
        title = "⛔ *Заблокированные пользователи*"
        mode = "banned"
    else:
        rows = db_list_users(limit=USERS_PAGE_SIZE, offset=offset)
        total = db_count_users()
        title = "👥 *Пользователи*"
        mode = "users"

    max_page = max(0, (total - 1) // USERS_PAGE_SIZE) if total > 0 else 0
    if page > max_page:
        page = max_page
        offset = page * USERS_PAGE_SIZE
        rows = db_list_banned_users(limit=USERS_PAGE_SIZE, offset=offset) if banned_only else db_list_users(limit=USERS_PAGE_SIZE, offset=offset)

    stats = db_users_stats()

    text = (
        f"{title}\n\n"
        f"👤 Всего в базе: *{stats['total']}*\n"
        f"🟢 Активны за 24ч: *{stats['active_day']}*\n"
        f"🟡 Активны за 7д: *{stats['active_week']}*\n"
        f"🚫 Заблокировали бота: *{stats['blocked']}*\n"
        f"⛔ Забанены: *{stats['banned']}*\n\n"
        f"📄 Страница: *{page + 1}/{max_page + 1 if total > 0 else 1}*\n"
        f"📦 На этой странице: *{len(rows)}*"
    )

    if total == 0:
        text += "\n\nСписок пуст."

    await call.message.answer(
        text,
        reply_markup=kb_admin_users_page(rows, page, total, mode)
    )


# ================== START / MENU ==================
@dp.message(CommandStart())
async def start(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main(m.from_user.id))
    await refresh_reply_menu(m.chat.id, m.from_user.id)


@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main(m.from_user.id))
    await refresh_reply_menu(m.chat.id, m.from_user.id)


@dp.message(F.text == "📋 Меню")
async def menu_btn(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main(m.from_user.id))
    await refresh_reply_menu(m.chat.id, m.from_user.id)


@dp.message(F.text == "🧾 Моя подписка")
async def mysub_btn(m: Message):
    subs = db_get_accepted_subscriptions(m.from_user.id)
    if not subs:
        await m.answer(text_subscription_card(m.from_user, None), reply_markup=kb_sub_no_sub(m.from_user.id))
        await refresh_reply_menu(m.chat.id, m.from_user.id)
        return

    await m.answer(text_subscription_card(m.from_user, subs), reply_markup=kb_sub_with_refresh(m.from_user.id))
    await refresh_reply_menu(m.chat.id, m.from_user.id)


@dp.message(F.text == "❌ Отменить заказ")
async def cancel_order_from_reply(m: Message):
    active = db_get_active_order(m.from_user.id)
    if not active:
        await m.answer("❌ Активного заказа нет.", reply_markup=kb_main(m.from_user.id))
        await refresh_reply_menu(m.chat.id, m.from_user.id)
        return

    order_id = active["id"]
    db_set_status(order_id, "cancelled")

    try:
        if active.get("payment_msg_id"):
            await bot.delete_message(chat_id=m.from_user.id, message_id=active["payment_msg_id"])
    except Exception:
        pass

    await m.answer("✅ Заказ отменён. Можешь оформить новый через меню.", reply_markup=kb_main(m.from_user.id))
    await refresh_reply_menu(m.chat.id, m.from_user.id)


# ================== ADMIN COMMAND ==================
@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("🛠 *Админ-панель*\nВыбери раздел 👇", reply_markup=kb_admin_menu())


# ================== CALLBACK: MENU ==================
@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(call: CallbackQuery):
    try:
        action = call.data.split(":", 1)[1]

        if action == "main":
            await send_banner_or_text(call.message.chat.id, text_menu(), reply_markup=kb_main(call.from_user.id))
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "buy":
            await call.message.answer(text_buy_intro(), reply_markup=kb_buy())
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "sub":
            subs = db_get_accepted_subscriptions(call.from_user.id)
            if not subs:
                await call.message.answer(
                    text_subscription_card(call.from_user, None),
                    reply_markup=kb_sub_no_sub(call.from_user.id)
                )
                await refresh_reply_menu(call.message.chat.id, call.from_user.id)
                return

            await call.message.answer(
                text_subscription_card(call.from_user, subs),
                reply_markup=kb_sub_with_refresh(call.from_user.id)
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "cancel_order":
            active = db_get_active_order(call.from_user.id)
            if not active:
                await call.answer("Активного заказа нет", show_alert=True)
                return

            order_id = active["id"]
            db_set_status(order_id, "cancelled")

            try:
                if active.get("payment_msg_id"):
                    await bot.delete_message(chat_id=call.from_user.id, message_id=active["payment_msg_id"])
            except Exception:
                pass

            await bot.send_message(
                call.from_user.id,
                "✅ Заказ отменён. Можешь оформить новый через меню.",
                reply_markup=kb_main(call.from_user.id)
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return
    finally:
        try:
            await call.answer()
        except Exception:
            pass


# ================== BUY FLOW ==================
@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    try:
        user_id = call.from_user.id

        active = db_get_active_order(user_id)
        if active:
            await call.message.answer(
                f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n"
                "Если админ не отвечает — можно *❌ Отменить заказ* или *🔁 Переслать админу* (ограничено)."
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        plan = call.data.split(":", 1)[1]
        if plan not in ("standard", "family"):
            await call.answer("Ошибка тарифа", show_alert=True)
            return

        plan_name, conditions, _device_limit, amount = plan_meta(plan)

        await call.message.answer(
            f"📄 *Перед покупкой нужно принять пользовательское соглашение.*\n\n"
            f"📦 Тариф: *{plan_name}*\n"
            f"{conditions}\n"
            f"💰 Сумма: *{amount}₽*\n\n"
            "1) Нажми кнопку *Открыть соглашение*\n"
            "2) Ознакомься с условиями\n"
            "3) Нажми *Принять*",
            reply_markup=kb_agreement(plan)
        )
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


@dp.callback_query(F.data.startswith("agree:"))
async def agree(call: CallbackQuery):
    try:
        user_id = call.from_user.id
        username = call.from_user.username

        active = db_get_active_order(user_id)
        if active:
            await call.message.answer(
                f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n"
                "Если админ не отвечает — можно *❌ Отменить заказ* или *🔁 Переслать админу* (ограничено)."
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        plan = call.data.split(":", 1)[1]
        if plan not in ("standard", "family"):
            await call.answer("Ошибка тарифа", show_alert=True)
            return

        plan_name, conditions, _device_limit, amount = plan_meta(plan)
        order_id = db_create_order(user_id, username, plan, amount)

        msg = await call.message.answer(
            f"🧾 *Заказ #{order_id}*\n\n"
            f"📦 Тариф: *{plan_name}*\n"
            f"{conditions}\n"
            f"💰 Сумма: *{amount}₽*\n\n"
            f"{PAYMENT_TEXT}\n\n"
            "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст).",
            reply_markup=kb_payment(order_id)
        )
        db_set_payment_msg(order_id, msg.message_id)
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_order(call: CallbackQuery):
    try:
        user_id = call.from_user.id
        order_id = int(call.data.split(":", 1)[1])

        order = db_get_order(order_id)
        if not order or order["user_id"] != user_id:
            await call.answer("Заказ не найден", show_alert=True)
            return

        if order["status"] not in ("waiting_receipt", "pending_admin"):
            await call.answer("Этот заказ уже закрыт", show_alert=True)
            return

        db_set_status(order_id, "cancelled")

        try:
            msg_id = order.get("payment_msg_id") or call.message.message_id
            await bot.delete_message(chat_id=user_id, message_id=msg_id)
        except Exception:
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

        await bot.send_message(user_id, "✅ Заказ отменён. Можешь оформить новый через меню.", reply_markup=kb_main(user_id))
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


@dp.callback_query(F.data.startswith("resend:"))
async def resend_to_admin(call: CallbackQuery):
    try:
        user_id = call.from_user.id
        order_id = int(call.data.split(":", 1)[1])

        order = db_get_order(order_id)
        if not order or order["user_id"] != user_id:
            await call.answer("Заказ не найден", show_alert=True)
            return

        ok, reason = db_can_resend(order_id)
        if not ok:
            await call.answer(f"⛔ {reason}", show_alert=True)
            return

        try:
            await send_check_to_admin(order_id, order["user_id"], order["username"], order["plan"], order["amount"])
        except Exception as e:
            print("RESEND ADMIN ERROR:", repr(e))
            await call.answer("Не смог переслать админу", show_alert=True)
            return

        db_mark_resend(order_id)

        if order["status"] == "waiting_receipt":
            db_set_status(order_id, "pending_admin")

        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
        await call.answer("✅ Переслал админу", show_alert=True)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


# ================== RECEIPT ==================
@dp.message(StateFilter(None), F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    if m.from_user and m.from_user.id == ADMIN_ID:
        return

    if (m.text or "").strip() in {"📋 Меню", "🧾 Моя подписка", "❌ Отменить заказ"}:
        return

    user_id = m.from_user.id
    username = m.from_user.username

    active = db_get_active_order(user_id)
    if not active:
        await m.answer("⚠️ Нет активного заказа. Открой /start и выбери тариф.")
        await refresh_reply_menu(m.chat.id, m.from_user.id)
        return

    if active["status"] == "pending_admin":
        await m.answer(
            "⏳ Чек уже был отправлен админу.\n"
            "Если админ не отвечает — можно *❌ Отменить заказ* или *🔁 Переслать админу* (ограничено).",
            reply_markup=kb_payment(active["id"])
        )
        await refresh_reply_menu(m.chat.id, m.from_user.id)
        return

    try:
        await send_check_to_admin(active["id"], user_id, username, active["plan"], active["amount"])
    except Exception as e:
        print("ADMIN SEND ERROR:", repr(e))
        await m.answer("⚠️ Не смог отправить админу. Попробуй ещё раз через минуту.")
        return

    db_set_status(active["id"], "pending_admin")

    try:
        await m.copy_to(ADMIN_ID)
    except Exception as e:
        print("COPY TO ADMIN ERROR:", repr(e))

    await m.answer("✅ Чек отправлен админу. Жди подтверждения ⏳")
    await refresh_reply_menu(m.chat.id, m.from_user.id)


# ================== ISSUE KEY ==================
async def send_key_to_user(user_id: int, plan: str, key: str):
    plan_name, conditions, _device_limit, _amount = plan_meta(plan)
    await bot.send_message(
        user_id,
        "✅ *Оплата подтверждена!*\n\n"
        f"📦 Тариф: *{plan_name}* • ♾ *Навсегда*\n"
        f"{conditions}\n\n"
        "🔑 *Твой ключ:*\n"
        f"> `{key}`\n\n"
        "📲 *Как подключиться (Happ):*\n"
        "1) Скачай Happ (кнопки ниже)\n"
        "2) Открой приложение\n"
        "3) Нажми «Добавить / Import / Подписка»\n"
        "4) Вставь ключ\n\n"
        "Нажми кнопки ниже 👇",
        reply_markup=kb_after_issue()
    )


# ================== SUBSCRIPTION REFRESH ==================
@dp.callback_query(F.data == "sub:refresh")
async def refresh_subscription(call: CallbackQuery):
    try:
        subs = db_get_accepted_subscriptions(call.from_user.id)
        if not subs:
            await call.answer("У тебя нет купленных подписок", show_alert=True)
            return

        refreshed = []
        not_found = []

        for sub in subs:
            plan = sub["plan"]
            latest_key = get_latest_key_for_plan(plan)

            if not latest_key:
                not_found.append(plan)
                continue

            db_update_user_plan_key(call.from_user.id, plan, latest_key)
            refreshed.append((plan, latest_key))

        subs_updated = db_get_accepted_subscriptions(call.from_user.id)
        text = text_subscription_card(call.from_user, subs_updated)

        if refreshed:
            text += "\n\n✅ *Подписки обновлены по актуальным ключам.*"

        if not_found:
            labels = []
            for p in not_found:
                labels.append("🟩 Стандарт" if p == "standard" else "🟦 Семейная")
            text += "\n\n⚠️ Не найден новый ключ для: " + ", ".join(labels)

        await call.message.answer(text, reply_markup=kb_sub_with_refresh(call.from_user.id))
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


# ================== ADMIN CALLBACKS ==================
@dp.callback_query(F.data == "admin:home")
async def admin_home(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.answer("🛠 *Админ-панель*\nВыбери раздел 👇", reply_markup=kb_admin_menu())
    await call.answer()


@dp.callback_query(F.data == "admin:list")
async def admin_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    rows = db_list_pending(limit=20)
    if not rows:
        await call.message.answer("✅ Нет заказов на проверке.", reply_markup=kb_admin_menu())
        await call.answer()
        return
    await call.message.answer("📦 *Заказы на проверке:*", reply_markup=kb_admin_list(rows))
    await call.answer()


@dp.callback_query(F.data.startswith("admin:view:"))
async def admin_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    order_id = int(call.data.split(":")[-1])
    order = db_get_order(order_id)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    safe_username = f"@{order['username']}" if order["username"] else "—"

    await call.message.answer(
        "🧾 Заказ для решения\n\n"
        f"🧾 Заказ: #{order['id']}\n"
        f"👤 User: {order['user_id']} ({safe_username})\n"
        f"📦 План: {order['plan']}\n"
        f"💰 Сумма: {order['amount']}₽\n"
        f"📌 Статус: {order['status']}\n"
        f"🕒 Создан: {fmt_ts(order['created_at'])}\n\n"
        "Выбери действие:",
        reply_markup=kb_admin_decision(order_id),
        parse_mode=None
    )
    await call.answer()


@dp.callback_query(F.data == "admin:profit")
async def admin_profit(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    p = db_profit_totals()
    await call.message.answer(
        "💰 *Прибыль*\n\n"
        f"📅 За 24ч: *{p['day']}₽*\n"
        f"🗓 За 7д: *{p['week']}₽*\n"
        f"🗓 За 30д: *{p['month']}₽*\n\n"
        f"🏦 Всего после сброса: *{p['total']}₽*",
        reply_markup=kb_admin_profit()
    )
    await call.answer()


@dp.callback_query(F.data == "admin:profit:reset")
async def admin_profit_reset(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    db_profit_reset()
    await call.message.answer(
        "♻️ *Прибыль сброшена.*\n\n"
        "История заказов сохранена, сброшен только счётчик общей прибыли.",
        reply_markup=kb_admin_profit()
    )
    await call.answer("Прибыль сброшена ✅", show_alert=True)


@dp.callback_query(F.data == "admin:search")
async def admin_search(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.search_wait)
    await call.message.answer(
        "🔎 *Поиск заказа*\n\n"
        "Отправь сюда:\n"
        "• номер заказа (`#12` или `12`)\n"
        "• user_id (`123456789`)\n"
        "• username (`@username`)\n\n"
        "Отмена: `отмена`",
        reply_markup=kb_admin_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.broadcast_wait)
    await call.message.answer(
        "📢 *Рассылка*\n\n"
        "Пришли следующим сообщением то, что нужно разослать.\n"
        "Поддержка: текст / фото / документ.\n\n"
        "Отмена: `отмена`",
        reply_markup=kb_admin_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "admin:prices")
async def admin_prices(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.answer("🏷 *Цены*\nВыбери что менять:", reply_markup=kb_admin_prices())
    await call.answer()


@dp.callback_query(F.data.startswith("admin:price:set:"))
async def admin_price_set(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    plan = call.data.split(":")[-1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка", show_alert=True)
        return

    await state.update_data(price_plan=plan)
    await state.set_state(AdminStates.price_wait)

    title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    await call.message.answer(
        f"🏷 *Изменение цены*\n\n"
        f"Тариф: *{title}*\n"
        "Отправь новую цену числом, например: `250`\n\n"
        "Отмена: `отмена`",
        reply_markup=kb_admin_menu()
    )
    await call.answer()


@dp.callback_query(F.data == "admin:keys")
async def admin_keys(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.answer("🔑 *Ключи*\nУправление ключами:", reply_markup=kb_admin_keys())
    await call.answer()


@dp.callback_query(F.data.startswith("admin:keys:add:"))
async def admin_keys_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    plan = call.data.split(":")[-1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка", show_alert=True)
        return

    await state.update_data(keys_plan=plan)
    await state.set_state(AdminStates.keys_wait)

    title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    await call.message.answer(
        f"🔑 *Добавление ключей*\n\n"
        f"Тариф: *{title}*\n"
        "Пришли ключи одним сообщением.\n"
        "*Каждый ключ с новой строки.*\n\n"
        "Отмена: `отмена`",
        reply_markup=kb_admin_menu()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:keys:clear:"))
async def admin_keys_clear(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    plan = call.data.split(":")[-1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка", show_alert=True)
        return

    await call.message.answer(
        "⚠️ *Очистка ключей*\n"
        "Это удалит *все* ключи этого тарифа.\n\n"
        "Подтвердить?",
        reply_markup=kb_confirm_clear(plan)
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:keys:clear_yes:"))
async def admin_keys_clear_yes(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    plan = call.data.split(":")[-1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка", show_alert=True)
        return

    db_keys_clear(plan)
    await call.message.answer("✅ Ключи очищены.", reply_markup=kb_admin_keys())
    await call.answer()


@dp.callback_query(F.data.startswith("admin:users:"))
async def admin_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    try:
        page = int(call.data.split(":")[-1])
    except Exception:
        page = 0

    await send_admin_users_page(call, page=page, banned_only=False)
    await call.answer()


@dp.callback_query(F.data.startswith("admin:banned:"))
async def admin_banned(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    try:
        page = int(call.data.split(":")[-1])
    except Exception:
        page = 0

    await send_admin_users_page(call, page=page, banned_only=True)
    await call.answer()


@dp.callback_query(F.data.startswith("admin:user:"))
async def admin_user_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 5:
        await call.answer("Ошибка", show_alert=True)
        return

    user_id = int(parts[2])
    mode = parts[3]
    page = int(parts[4])

    user = db_get_user(user_id)
    if not user:
        await call.answer("Пользователь не найден", show_alert=True)
        return

    uname = f"@{user['username']}" if user["username"] else "—"
    fname = user["first_name"] or "—"
    sub_count = db_count_user_subscriptions(user_id)
    active_order = db_get_active_order(user_id)

    status_parts = []
    status_parts.append("⛔ Забанен" if user["is_banned"] else "✅ Не забанен")
    status_parts.append("🚫 Бот заблокирован" if user["is_blocked"] else "✅ Бот доступен")

    await call.message.answer(
        "👤 *Карточка пользователя*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Имя: {fname}\n"
        f"🔹 Username: {uname}\n"
        f"🕒 Последняя активность: {fmt_ts(user['last_seen'])}\n"
        f"📦 Активных подписок: *{sub_count}*\n"
        f"🧾 Активный заказ: *{'Да' if active_order else 'Нет'}*\n"
        f"📌 Статус: {' • '.join(status_parts)}",
        reply_markup=kb_admin_user_view(user_id, mode, page)
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:ban:"))
async def admin_ban_user(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    user_id = int(parts[2])
    mode = parts[3] if len(parts) > 3 else "users"
    page = int(parts[4]) if len(parts) > 4 else 0

    if user_id == ADMIN_ID:
        await call.answer("Админа банить нельзя", show_alert=True)
        return

    db_ban_user_and_revoke(user_id)

    try:
        await bot.send_message(
            user_id,
            "⛔ Твой доступ аннулирован.\n"
            "Подписки отключены, пользоваться ботом больше нельзя."
        )
    except Exception:
        pass

    await call.message.answer(
        f"⛔ *Пользователь `{user_id}` забанен.*\n\n"
        "✅ Подписки аннулированы\n"
        "✅ Активные заказы отменены\n"
        "✅ Доступ к боту закрыт",
        reply_markup=kb_admin_user_view(user_id, mode, page)
    )
    await call.answer("Пользователь забанен ✅", show_alert=True)


@dp.callback_query(F.data.startswith("admin:unban:"))
async def admin_unban_user(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 5:
        await call.answer("Ошибка", show_alert=True)
        return

    user_id = int(parts[2])
    mode = parts[3]
    page = int(parts[4])

    db_unban_user(user_id)

    try:
        await bot.send_message(
            user_id,
            "✅ Ты был разбанен.\n"
            "Можешь снова пользоваться ботом.\n"
            "Подписок после разбана не возвращается."
        )
    except Exception:
        pass

    await call.message.answer(
        f"✅ *Пользователь `{user_id}` разбанен.*\n\n"
        "⚠️ Подписки не восстановлены.\n"
        "После разбана у пользователя *нет никаких подписок*.",
        reply_markup=kb_admin_user_view(user_id, mode, page)
    )
    await call.answer("Пользователь разбанен ✅", show_alert=True)


@dp.callback_query(F.data.startswith("admin:ok:") | F.data.startswith("admin:no:"))
async def admin_decision(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    _, action, order_id_str = call.data.split(":")
    order_id = int(order_id_str)
    order = db_get_order(order_id)

    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order["status"] in ("accepted", "rejected", "cancelled", "revoked"):
        await call.answer("Уже решено", show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if db_is_banned(order["user_id"]):
        await call.answer("Пользователь забанен", show_alert=True)
        return

    if action == "no":
        db_set_status(order_id, "rejected")
        try:
            await bot.send_message(order["user_id"], "❌ Оплата отклонена. Отправь корректный чек ещё раз.")
        except Exception:
            pass
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await call.answer("Отклонено ✅")
        return

    if action == "ok":
        key = take_key(order["plan"], order_id=order_id)
        if not key:
            await call.answer("Ключей нет", show_alert=True)
            await bot.send_message(
                ADMIN_ID,
                "⚠️ В базе ключей пусто.\n"
                "Открой /admin → 🔑 Ключи → ➕ Добавить.",
                parse_mode="Markdown"
            )
            return

        try:
            await send_key_to_user(order["user_id"], order["plan"], key)
        except TelegramForbiddenError:
            await call.answer("Не могу написать юзеру", show_alert=True)
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Не смог отправить пользователю {order['user_id']}. Пусть нажмёт /start.",
                parse_mode=None
            )
            return
        except TelegramBadRequest as e:
            await call.answer("TelegramBadRequest", show_alert=True)
            await bot.send_message(ADMIN_ID, f"⚠️ TelegramBadRequest при выдаче: {e}", parse_mode=None)
            return
        except Exception as e:
            await call.answer("Ошибка", show_alert=True)
            await bot.send_message(ADMIN_ID, f"⚠️ Ошибка при выдаче: {type(e).__name__}", parse_mode=None)
            return

        db_set_issued(order_id, key)
        db_set_status(order_id, "accepted")

        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        try:
            await refresh_reply_menu(order["user_id"], order["user_id"])
        except Exception:
            pass

        await call.answer("Выдано ✅")


# ================== FSM INPUTS ==================
@dp.message(AdminStates.search_wait)
async def admin_search_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if not txt:
        await m.answer("Пришли номер заказа, user_id или username.", reply_markup=kb_admin_menu())
        return

    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_menu())
        return

    rows = db_search_orders(txt, limit=15)
    if not rows:
        await m.answer(
            "❌ Ничего не найдено.\n\n"
            "Попробуй так:\n"
            "• `#12`\n"
            "• `12`\n"
            "• `@username`\n"
            "• `123456789`",
            reply_markup=kb_admin_menu()
        )
        return

    out = ["🔎 *Результаты поиска:*"]
    for (oid, uid, uname, plan, amount, status, created_at, accepted_at) in rows:
        username_text = f"@{uname}" if uname else "—"
        plan_title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
        out.append(
            f"\n━━━━━━━━━━\n"
            f"🧾 *Заказ #{oid}*\n"
            f"👤 User ID: `{uid}`\n"
            f"🔹 Username: {username_text}\n"
            f"📦 Тариф: {plan_title}\n"
            f"💰 Сумма: *{amount}₽*\n"
            f"📌 Статус: *{status}*\n"
            f"🕒 Создан: {fmt_ts(created_at)}\n"
            f"✅ Принят: {fmt_ts(accepted_at) if accepted_at else '—'}"
        )

    await m.answer("\n".join(out), reply_markup=kb_admin_menu())
    await state.clear()


@dp.message(AdminStates.price_wait)
async def admin_price_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_menu())
        return

    data = await state.get_data()
    plan = data.get("price_plan")
    if plan not in ("standard", "family"):
        await state.clear()
        await m.answer("⚠️ Ошибка состояния. Открой /admin заново.", reply_markup=kb_admin_menu())
        return

    if not txt.isdigit():
        await m.answer("Пришли цену числом, например `250`.", reply_markup=kb_admin_menu())
        return

    price = int(txt)
    if price < 1 or price > 1_000_000:
        await m.answer("Цена странная 😄 Пришли норм число.", reply_markup=kb_admin_menu())
        return

    if plan == "standard":
        db_settings_set("price_standard", str(price))
    else:
        db_settings_set("price_family", str(price))

    await state.clear()
    await m.answer("✅ Цена обновлена.", reply_markup=kb_admin_prices())


@dp.message(AdminStates.keys_wait)
async def admin_keys_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_menu())
        return

    data = await state.get_data()
    plan = data.get("keys_plan")
    if plan not in ("standard", "family"):
        await state.clear()
        await m.answer("⚠️ Ошибка состояния. Открой /admin заново.", reply_markup=kb_admin_menu())
        return

    keys = [x.strip() for x in (m.text or "").splitlines() if x.strip()]
    if not keys:
        await m.answer("Пусто. Пришли ключи строками.", reply_markup=kb_admin_menu())
        return

    added, skipped = db_keys_add(plan, keys)
    title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    count_all = db_keys_count(plan)

    await state.clear()
    await m.answer(
        f"✅ Ключи добавлены ({title})\n\n"
        f"➕ Добавлено: *{added}*\n"
        f"⏭ Пропущено (дубли): *{skipped}*\n"
        f"📦 Всего ключей в базе: *{count_all}*",
        reply_markup=kb_admin_keys()
    )


@dp.message(AdminStates.broadcast_wait)
async def admin_broadcast_send(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    if (m.text or "").strip().lower() == "отмена":
        await state.clear()
        await m.answer("❌ Рассылка отменена.", reply_markup=kb_admin_menu())
        return

    user_ids = db_list_users_for_broadcast()
    if not user_ids:
        await state.clear()
        await m.answer("Нет пользователей для рассылки.", reply_markup=kb_admin_menu())
        return

    ok, bad = 0, 0
    await m.answer(f"📢 Начинаю рассылку по *{len(user_ids)}* пользователям…")

    for uid in user_ids:
        try:
            await m.copy_to(uid)
            ok += 1
        except TelegramForbiddenError:
            bad += 1
            db_mark_blocked(uid, True)
        except Exception:
            bad += 1
        await asyncio.sleep(0.03)

    await state.clear()
    await m.answer(
        "✅ *Рассылка завершена*\n\n"
        f"📬 Успешно: *{ok}*\n"
        f"🚫 Недоступны/ошибки: *{bad}*",
        reply_markup=kb_admin_menu()
    )


# ================== MAIN ==================
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set")

    db_init()
    import_keys_from_files_if_empty()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
