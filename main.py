import asyncio
import os
import time
import sqlite3
import json
import uuid
import base64
from urllib import request as urllib_request, error as urllib_error
from urllib.parse import quote as urlquote
from typing import Optional, List, Tuple, Dict, Any, Callable, Awaitable
import re
import secrets
from html import escape as html_escape

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
from aiohttp import web


# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "orders.sqlite")
YK_SHOP_ID = os.getenv("YK_SHOP_ID", "1308738").strip()
YK_SECRET_KEY = os.getenv("YK_SECRET_KEY", "test_*ghOsMlj3zv59sffhhg_T43lHUGcJW0I7e-Cy8Flx8c9c").strip()
BASE_URL = os.getenv("BASE_URL", "https://captivating-caring-production-aaaa.up.railway.app").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip()
GITHUB_STANDARD_PATH = os.getenv("GITHUB_STANDARD_PATH", "standard.txt").strip()
GITHUB_FAMILY_PATH = os.getenv("GITHUB_FAMILY_PATH", "family.txt").strip()

SUB_BASE_URL = os.getenv("SUB_BASE_URL", "https://skyzxc.up.railway.app").rstrip("/")
TRIAL_SHARED_SECRET = os.getenv("TRIAL_SHARED_SECRET", "").strip()
HAPP_PROVIDER_CODE = os.getenv("HAPP_PROVIDER_CODE", "").strip()
HAPP_AUTH_KEY = os.getenv("HAPP_AUTH_KEY", "").strip()
HAPP_CRYPT_API = os.getenv("HAPP_CRYPT_API", "https://crypto.happ.su/api-v2.php").strip()
TRIAL_DURATION_SEC = int(os.getenv("TRIAL_DURATION_SEC", "3600"))


# ================== PATHS ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANNER_PATH = os.path.join(BASE_DIR, os.getenv("BANNER_PATH", "banner.jpg"))

# ================== LINKS ==================
TG_CHANNEL = "https://t.me/sokxyybc"
TG_CHANNEL_USERNAME = "@sokxyybc"
PRIVATE_GROUP_LINK = "https://t.me/+wlbajMk9C984NzU6"
REVIEW_LINK = "https://t.me/sokxyybc/23"
AGREEMENT_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-08-15-10"
PRIVACY_URL = "https://telegra.ph/Politika-konfidencialnosti-08-15-17"
SUPPORT_EMAIL = "support@gmail.com"

HAPP_ANDROID_URL = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_IOS_URL = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"
HAPP_WINDOWS_URL = "https://happ.su/"

# ================== PREMIUM EMOJI ==================
EMOJI_IDS = {
    "globe": "5359596642506925824",
    "buy": "5778311685638984859",
    "my_sub": "6028171274939797252",
    "channel": "6028346797368283073",
    "tariff": "5766994197705921104",
    "standard": "6033108709213736873",
    "family": "6033125983572201397",
    "trial": "5778311685638984859",
}

def tg_emoji(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


BTN_BUY_STYLE = "success"
BTN_PRIMARY_STYLE = "default"
BTN_INFO_STYLE = "default"
BTN_DANGER_STYLE = "danger"

def ibtn(text: str, callback_data: str = None, url: str = None, style: str = "default", **extra):
    payload = {"text": text, "style": style}
    if callback_data is not None:
        payload["callback_data"] = callback_data
    if url is not None:
        payload["url"] = url
    payload.update(extra)
    return InlineKeyboardButton(**payload)

def plan_emoji(plan: str) -> str:
    return tg_emoji(EMOJI_IDS["standard"], "🟩") if plan == "standard" else tg_emoji(EMOJI_IDS["family"], "🟦")

def html_system_plan_name(plan: str) -> str:
    return f'{plan_emoji(plan)} Стандарт' if plan == "standard" else f'{plan_emoji(plan)} Семейная'

def html_pretty_plan_name(plan: str) -> str:
    return f'{plan_emoji(plan)} Стандартная' if plan == "standard" else f'{plan_emoji(plan)} Семейная'

def html_plan_conditions(plan: str) -> str:
    return "👤 1 пользователь • 📱 до 3 устройств" if plan == "standard" else "👥 до 8 пользователей • 📱 до 3 устройств каждому"

def payment_text_html() -> str:
    return (
        "💳 <b>Оплата через кассу</b>\n\n"
        "Нажми кнопку <b>Оплатить</b> ниже. После успешной оплаты бот автоматически выдаст ключ"
    )

# ================== PAYMENT ==================
PAYMENT_TEXT = (
    "💳 *Оплата через кассу*\n\n"
    "Нажми кнопку *Оплатить* ниже. После успешной оплаты бот автоматически выдаст ключ"
)

BOT_USERNAME = ""

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
    message_user_wait = State()
    user_search_wait = State()
    github_add_wait = State()
    github_edit_wait = State()


# ================== DB ==================
def db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


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
    _add_column_if_missing(con, "orders", "payment_provider_id", "ALTER TABLE orders ADD COLUMN payment_provider_id TEXT")
    _add_column_if_missing(con, "orders", "payment_url", "ALTER TABLE orders ADD COLUMN payment_url TEXT")

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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_status_created ON orders(status, created_at DESC)")
    con.commit()

    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS profit_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cur.execute("INSERT OR IGNORE INTO profit_meta(key, value) VALUES('profit_offset', '0')")
    con.commit()

    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS trial_subscriptions (
            user_id INTEGER PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            used INTEGER NOT NULL DEFAULT 1
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trial_token ON trial_subscriptions(token)")
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


def db_search_users(query: str, limit: int = 20, offset: int = 0, banned_only: bool = False):
    q = (query or "").strip()
    if not q:
        return []

    q_no_at = q[1:] if q.startswith("@") else q
    q_lower = q_no_at.lower()
    like_q = f"%{q_lower}%"

    conditions = []
    params: List[Any] = []

    if q.isdigit():
        conditions.append("CAST(user_id AS TEXT)=?")
        params.append(q)
        conditions.append("CAST(user_id AS TEXT) LIKE ?")
        params.append(f"{q}%")

    conditions.append("LOWER(COALESCE(username, ''))=?")
    params.append(q_lower)
    conditions.append("LOWER(COALESCE(username, '')) LIKE ?")
    params.append(like_q)
    conditions.append("LOWER(COALESCE(first_name, '')) LIKE ?")
    params.append(like_q)

    scope = "COALESCE(is_banned,0)=1 AND " if banned_only else ""
    sql = f"""
        SELECT user_id, username, first_name, last_seen, is_blocked, is_banned
        FROM users
        WHERE {scope}({' OR '.join(conditions)})
        ORDER BY
            CASE
                WHEN CAST(user_id AS TEXT)=? THEN 0
                WHEN LOWER(COALESCE(username, ''))=? THEN 1
                WHEN LOWER(COALESCE(first_name, ''))=? THEN 2
                ELSE 3
            END,
            last_seen DESC
        LIMIT ? OFFSET ?
    """

    con = db()
    try:
        cur = con.cursor()
        exact_id = q if q.isdigit() else ""
        cur.execute(sql, [*params, exact_id, q_lower, q_lower, limit, offset])
        return cur.fetchall()
    finally:
        con.close()


def db_count_search_users(query: str, banned_only: bool = False) -> int:
    q = (query or "").strip()
    if not q:
        return 0

    q_no_at = q[1:] if q.startswith("@") else q
    q_lower = q_no_at.lower()
    like_q = f"%{q_lower}%"

    conditions = []
    params: List[Any] = []

    if q.isdigit():
        conditions.append("CAST(user_id AS TEXT)=?")
        params.append(q)
        conditions.append("CAST(user_id AS TEXT) LIKE ?")
        params.append(f"{q}%")

    conditions.append("LOWER(COALESCE(username, ''))=?")
    params.append(q_lower)
    conditions.append("LOWER(COALESCE(username, '')) LIKE ?")
    params.append(like_q)
    conditions.append("LOWER(COALESCE(first_name, '')) LIKE ?")
    params.append(like_q)

    scope = "COALESCE(is_banned,0)=1 AND " if banned_only else ""
    sql = f"SELECT COUNT(*) FROM users WHERE {scope}({' OR '.join(conditions)})"

    con = db()
    try:
        cur = con.cursor()
        cur.execute(sql, params)
        return int(cur.fetchone()[0] or 0)
    finally:
        con.close()


def db_get_user_orders(user_id: int, limit: int = 10):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            SELECT id, plan, amount, status, created_at, accepted_at, issued_key
            FROM orders
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit))
        return cur.fetchall()
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
        SELECT id, plan, amount, status, payment_msg_id, admin_msg_id, resend_count, last_resend_at, payment_provider_id, payment_url
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
        "payment_provider_id": row[8],
        "payment_url": row[9],
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


def db_set_payment_provider(order_id: int, payment_provider_id: Optional[str], payment_url: Optional[str]):
    con = db()
    try:
        cur = con.cursor()
        cur.execute(
            "UPDATE orders SET payment_provider_id=?, payment_url=? WHERE id=?",
            (payment_provider_id, payment_url, order_id)
        )
        con.commit()
    finally:
        con.close()


def db_get_order_by_payment_provider(payment_provider_id: str):
    con = db()
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT id FROM orders WHERE payment_provider_id=? ORDER BY id DESC LIMIT 1",
            (payment_provider_id,)
        )
        row = cur.fetchone()
        return db_get_order(int(row[0])) if row else None
    finally:
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
               resend_count, last_resend_at, created_at, payment_provider_id, payment_url
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
        "payment_provider_id": row[13],
        "payment_url": row[14],
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


def db_get_trial(user_id: int):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT user_id, token, expires_at, created_at, used FROM trial_subscriptions WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "token": row[1],
            "expires_at": row[2],
            "created_at": row[3],
            "used": row[4],
        }
    finally:
        con.close()


def db_get_trial_by_token(token: str):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT user_id, token, expires_at, created_at, used FROM trial_subscriptions WHERE token=?", (token,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "token": row[1],
            "expires_at": row[2],
            "created_at": row[3],
            "used": row[4],
        }
    finally:
        con.close()


def db_trial_used(user_id: int) -> bool:
    return db_get_trial(user_id) is not None


def db_create_or_replace_trial(user_id: int, token: str, expires_at: int):
    con = db()
    try:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO trial_subscriptions(user_id, token, expires_at, created_at, used)
            VALUES(?,?,?,?,1)
            ON CONFLICT(user_id) DO UPDATE SET
                token=excluded.token,
                expires_at=excluded.expires_at,
                created_at=excluded.created_at,
                used=1
        """, (user_id, token, int(expires_at), int(time.time())))
        con.commit()
    finally:
        con.close()


def db_delete_trial(user_id: int) -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM trial_subscriptions WHERE user_id=?", (user_id,))
        con.commit()
        return int(cur.rowcount or 0)
    finally:
        con.close()


def build_trial_source_url(token: str) -> str:
    return f"{SUB_BASE_URL}/trial/{token}"


def _http_json(url: str, method: str = "GET", payload: Optional[dict] = None, headers: Optional[dict] = None, timeout: int = 20) -> dict:
    data = None
    hdrs = {
        "User-Agent": "curl/8.5.0",
        "Accept": "application/json, text/plain, */*",
        **(headers or {}),
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib_request.Request(url=url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib_error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(raw or f"HTTP {e.code}")


def happ_required_ready() -> bool:
    return bool(HAPP_PROVIDER_CODE and HAPP_AUTH_KEY and TRIAL_SHARED_SECRET and SUB_BASE_URL)


def happ_create_install_code(install_limit: int = 1) -> str:
    if not HAPP_PROVIDER_CODE or not HAPP_AUTH_KEY:
        raise RuntimeError("Не настроены HAPP_PROVIDER_CODE / HAPP_AUTH_KEY")
    url = (
        "https://api.happ-proxy.com/api/add-install?"
        f"provider_code={urlquote(HAPP_PROVIDER_CODE)}&"
        f"auth_key={urlquote(HAPP_AUTH_KEY)}&"
        f"install_limit={int(install_limit)}"
    )
    data = _http_json(url)
    if int(data.get("rc", 0) or 0) != 1:
        raise RuntimeError(str(data.get("msg") or "Не удалось получить InstallID"))
    code = str(data.get("install_code") or "").strip()
    if not code:
        raise RuntimeError("Пустой InstallID от Happ")
    return code


def happ_encrypt_url(url: str) -> str:
    data = _http_json(
        HAPP_CRYPT_API,
        method="POST",
        payload={"url": url},
        headers={
            "Origin": "https://crypto.happ.su",
            "Referer": "https://crypto.happ.su/",
        },
    )
    print("[trial][crypt5] raw response:", data, flush=True)
    for key in ("url", "result", "encrypted_url", "link"):
        value = str(data.get(key) or "").strip()
        if value.startswith("happ://crypt"):
            return value
    raise RuntimeError(str(data.get("msg") or f"Не удалось зашифровать ссылку crypt5; raw={data}"))


def build_trial_limited_url(token: str) -> str:
    raw_url = build_trial_source_url(token)
    install_code = happ_create_install_code(1)
    return f"{raw_url}?installid={urlquote(install_code)}"


def build_trial_happ_link(token: str) -> str:
    limited_url = build_trial_limited_url(token)
    return happ_encrypt_url(limited_url)


def build_trial_delivery(token: str) -> tuple[str, str]:
    limited_url = build_trial_limited_url(token)
    try:
        crypt_link = happ_encrypt_url(limited_url)
        return "crypt5", crypt_link
    except Exception:
        return "limited", limited_url


async def send_trial_link_message(message: Message, token: str, expires_at: int, is_repeat: bool = False):
    mode, link = await asyncio.to_thread(build_trial_delivery, token)
    prefix = "🎁 *Пробная подписка активирована!*" if not is_repeat else "🎁 *Твоя пробная подписка уже активна*"
    format_line = "🔐 Формат: *Happ crypt5*" if mode == "crypt5" else "🔗 Формат: *Happ limited link*"
    extra = ""
    if mode != "crypt5":
        extra = (
            "⚠️ Сейчас Happ crypt5 временно не собрался, поэтому отправляю рабочую limited-ссылку.\n"
            "Лимит на 1 устройство и срок 1 час сохраняются.\n\n"
        )
    await message.answer(
        f"{prefix}\n\n"
        "📦 Основа: *Стандартная*\n"
        "⏳ Срок действия: *1 час*\n"
        f"🕒 Осталось: *{md_escape(trial_time_left_text(expires_at))}*\n"
        "📱 Лимит устройств: *1 устройство*\n"
        f"{format_line}\n\n"
        f"{extra}"
        "Добавляй ссылку в Happ как подписку. После окончания часа подписка станет пустой и серверы пропадут после обновления.\n\n"
        f"`{link}`"
    )


def trial_time_left_text(expires_at: int) -> str:
    left = max(0, int(expires_at) - int(time.time()))
    mins = left // 60
    secs = left % 60
    return f"{mins} мин {secs} сек" if mins else f"{secs} сек"


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
        f"{tg_emoji(EMOJI_IDS['globe'], '🌐')} <b>SkyWhy VPN</b>\n\n"
        "┏ Быстрое и стабильное подключение\n"
        "┣ Стабильное и безопасное соединение\n"
        "┣ Ключ выдаётся после проверки оплаты\n"
        "┗ Доступ: <b>навсегда</b> ♾\n\n"
        "Выбери нужный раздел ниже 👇"
    )

def text_buy_intro():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return (
        f"{tg_emoji(EMOJI_IDS['tariff'], '🛍')} <b>Выбор тарифа</b>\n\n"
        f"{plan_emoji('standard')} <b>Стандарт</b>\n• 1 пользователь\n• До 3 устройств\n• <b>{std_price}₽</b>\n\n"
        f"{plan_emoji('family')} <b>Семейная</b>\n• До 8 пользователей\n• До 3 устройств каждому\n• <b>{fam_price}₽</b>\n\n"
        "Нажми на подходящий тариф ниже."
    )


def html_text_trial_offer() -> str:
    return (
        f"{tg_emoji(EMOJI_IDS['trial'], '🎁')} <b>Пробная подписка</b>\n\n"
        "• Берётся из твоей <b>Стандартной</b> подписки\n"
        "• Действует только <b>1 час</b>\n"
        "• Лимит: <b>1 устройство</b>\n"
        "• Ссылка выдаётся в формате <b>Happ crypt5</b>\n"
        "• Повторно пробник получить нельзя\n\n"
        "Нажми кнопку ниже, чтобы получить пробную подписку."
    )


def kb_trial_offer():
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text="🎁 Получить пробник на 1 час", callback_data="trial:get", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["trial"])],
        [ibtn(text="⬅️ Назад в меню", callback_data="menu:main", style=BTN_PRIMARY_STYLE)],
    ])


def pretty_plan_name(plan: str) -> str:
    return "🟩 Стандартная" if plan == "standard" else "🟦 Семейная"


def html_text_subscription_card(from_user, subs: Optional[list]):
    name = html_escape((from_user.first_name or "—").strip())
    uid = from_user.id

    if not subs:
        return (
            "👤 <b>Мой профиль</b>\n\n"
            f"Имя: <b>{name}</b>\n"
            f"ID: <code>{uid}</code>\n\n"
            "📦 <b>Подписки</b>\n"
            "• Активных подписок пока нет\n\n"
            "Нажми <b>Купить подписку</b>, чтобы оформить доступ."
        )

    parts = [
        "👤 <b>Мой профиль</b>",
        "",
        f"Имя: <b>{name}</b>",
        f"ID: <code>{uid}</code>",
        "",
        "📦 <b>Активные подписки</b>",
    ]

    for idx, sub in enumerate(subs, start=1):
        _plan_name, _conditions, device_limit, _amount = plan_meta(sub["plan"])
        parts.extend([
            "",
            f"<b>{idx}. {html_pretty_plan_name(sub['plan'])}</b>",
            f"• Тариф в системе: {html_system_plan_name(sub['plan'])}",
            "• Ключ: <b>скрыт для удобства</b>",
            "• Срок: <b>Навсегда</b> ♾",
            f"• Условия: {html_plan_conditions(sub['plan'])}",
            f"• Лимит устройств: {device_limit}",
            f"• Выдано: {html_escape(fmt_ts(sub.get('accepted_at')))}",
        ])

    parts.extend([
        "",
        "Нажми кнопку нужного тарифа ниже. Бот пришлёт ключ отдельным сообщением.",
        "На телефоне можно нажать на код или зажать его, чтобы скопировать.",
    ])
    return "\n".join(parts)


def text_subscription_card(from_user, subs: Optional[list]):
    name = (from_user.first_name or "—").strip()
    uid = from_user.id

    if not subs:
        return (
            "👤 *Мой профиль*\n\n"
            f"Имя: *{md_escape(name)}*\n"
            f"ID: `{uid}`\n\n"
            "📦 *Подписки*\n"
            "• Активных подписок пока нет\n\n"
            "Нажми *Купить подписку*, чтобы оформить доступ."
        )

    parts = [
        "👤 *Мой профиль*",
        "",
        f"Имя: *{md_escape(name)}*",
        f"ID: `{uid}`",
        "",
        "📦 *Активные подписки*",
    ]

    for idx, sub in enumerate(subs, start=1):
        plan_name, conditions, device_limit, _amount = plan_meta(sub["plan"])

        parts.extend([
            "",
            f"*{idx}. {pretty_plan_name(sub['plan'])}*",
            f"• Тариф в системе: {plan_name}",
            "• Ключ: *скрыт для удобства*",
            "• Срок: *Навсегда* ♾",
            f"• Условия: {conditions}",
            f"• Лимит устройств: {device_limit}",
            f"• Выдано: {fmt_ts(sub.get('accepted_at'))}",
        ])

    parts.extend([
        "",
        "Нажми кнопку нужного тарифа ниже. Бот пришлёт ключ отдельным сообщением.",
        "На телефоне можно нажать на код или зажать его, чтобы скопировать.",
    ])
    return "\n".join(parts)

def fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(int(ts)))
    except Exception:
        return "—"


def md_escape(value: Any) -> str:
    s = str(value or "")
    for ch in r'_[]()~`>#+-=|{}.!':
        s = s.replace(ch, f'\\{ch}')
    return s


def build_admin_user_text(user_id: int) -> str:
    user = db_get_user(user_id)
    if not user:
        return "Пользователь не найден."

    uname_raw = user.get("username") or ""
    uname = f"@{uname_raw}" if uname_raw else "—"
    fname = user.get("first_name") or "—"
    sub_count = db_count_user_subscriptions(user_id)
    active_order = db_get_active_order(user_id)
    orders = db_get_user_orders(user_id, limit=10)
    subs = db_get_accepted_subscriptions(user_id)
    trial = db_get_trial(user_id)

    status_parts = []
    status_parts.append("⛔ Забанен" if user.get("is_banned") else "✅ Не забанен")
    status_parts.append("🚫 Бот заблокирован" if user.get("is_blocked") else "✅ Бот доступен")

    lines = [
        "👤 *Карточка пользователя*",
        "",
        f"🆔 ID: `{user_id}`",
        f"👤 Имя: {md_escape(fname)}",
        f"🔹 Username: {md_escape(uname)}",
        f"🕒 Последняя активность: {md_escape(fmt_ts(user.get('last_seen')))}",
        f"📦 Активных подписок: *{sub_count}*",
        f"🧾 Активный заказ: *{'Да' if active_order else 'Нет'}*",
        f"📌 Статус: {md_escape(' • '.join(status_parts))}",
    ]

    if trial:
        trial_status = "⏳ Активен" if int(trial.get("expires_at") or 0) > int(time.time()) else "⌛ Истёк"
        lines.append(f"🎁 Пробник: *{trial_status}* до *{md_escape(fmt_ts(trial.get('expires_at')))}*")

    if subs:
        lines.append("\n*Подписки:*" )
        for sub in subs[:10]:
            plan_title = "🟩 Стандарт" if sub["plan"] == "standard" else "🟦 Семейная"
            key_text = sub.get("issued_key") or "—"
            lines.append(
                f"• {plan_title} | {sub['amount']}₽ | ключ: `{md_escape(key_text)}`"
            )

    if orders:
        lines.append("\n*Последние заказы:*" )
        for oid, plan, amount, status, created_at, accepted_at, issued_key in orders:
            plan_title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
            lines.append(
                f"• #{oid} | {plan_title} | {amount}₽ | {md_escape(status)} | {md_escape(fmt_ts(created_at))}"
            )

    return "\n".join(lines)


# ================== KEYBOARDS ==================
def kb_reply_menu(user_id: int):
    active = db_get_active_order(user_id)

    if is_admin(user_id):
        rows = [
            [KeyboardButton(text="🏠 Меню"), KeyboardButton(text="⚙️ Админ")],
            [KeyboardButton(text="📦 Заказы"), KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="💰 Прибыль"), KeyboardButton(text="📦 Моя подписка")],
        ]
        if active:
            rows.append([KeyboardButton(text="❌ Отменить заказ")])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)

    rows = [
        [KeyboardButton(text="🏠 Меню"), KeyboardButton(text="📦 Моя подписка")],
        [KeyboardButton(text="🛒 Купить"), KeyboardButton(text="🎁 Пробная подписка")],
        [KeyboardButton(text="📢 Канал"), KeyboardButton(text="🆘 Поддержка")],
    ]
    if active:
        rows.append([KeyboardButton(text="❌ Отменить заказ")])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)

def kb_main(user_id: int):
    active = db_get_active_order(user_id)
    rows = [
        [ibtn(text="Купить подписку", callback_data="menu:buy", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["buy"])],
        [ibtn(text="🎁 Пробная подписка", callback_data="menu:trial", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["trial"])],
        [ibtn(text="Моя подписка", callback_data="menu:sub", style=BTN_PRIMARY_STYLE, icon_custom_emoji_id=EMOJI_IDS["my_sub"])],
        [ibtn(text="ℹ️ Информация", callback_data="menu:info", style=BTN_INFO_STYLE)],
    ]

    if active:
        rows.append([ibtn(text="⏳ Активный заказ", callback_data="noop", style=BTN_INFO_STYLE)])
        rows.append([ibtn(text="❌ Отменить заказ", callback_data="menu:cancel_order", style=BTN_DANGER_STYLE)])

    rows.extend([
        [ibtn(text="Наш канал", url=TG_CHANNEL, style=BTN_PRIMARY_STYLE, icon_custom_emoji_id=EMOJI_IDS["channel"])],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_buy():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text=f"Стандарт • {std_price}₽", callback_data="buy:standard", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["standard"])],
        [ibtn(text="1 пользователь • до 3 устройств", callback_data="noop", style=BTN_INFO_STYLE)],
        [ibtn(text=f"Семейная • {fam_price}₽", callback_data="buy:family", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["family"])],
        [ibtn(text="до 8 пользователей • до 3 устройств", callback_data="noop", style=BTN_INFO_STYLE)],
        [ibtn(text="⬅️ Назад в меню", callback_data="menu:main", style=BTN_PRIMARY_STYLE)],
    ])

def kb_agreement(plan: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text="📄 Пользовательское соглашение", url=AGREEMENT_URL, style=BTN_INFO_STYLE)],
        [ibtn(text="🔐 Политика конфиденциальности", url=PRIVACY_URL, style=BTN_INFO_STYLE)],
        [ibtn(text="✅ Согласен, продолжить", callback_data=f"agree:{plan}", style=BTN_BUY_STYLE)],
        [ibtn(text="⬅️ К тарифам", callback_data="menu:buy", style=BTN_PRIMARY_STYLE)],
    ])

def kb_payment(order_id: int, payment_url: Optional[str] = None):
    rows = []
    if payment_url:
        rows.append([ibtn(text="💳 Оплатить", url=payment_url, style=BTN_BUY_STYLE)])
    rows.append([ibtn(text="🔄 Проверить оплату", callback_data=f"checkpay:{order_id}", style=BTN_PRIMARY_STYLE)])
    rows.append([ibtn(text="❌ Отменить заказ", callback_data=f"cancel:{order_id}", style=BTN_DANGER_STYLE)])
    rows.append([ibtn(text="🏠 В меню", callback_data="menu:main", style=BTN_PRIMARY_STYLE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin_decision(order_id: int):
    order = db_get_order(order_id)
    keyboard = [
        [ibtn(text="✅ Принять", callback_data=f"admin:ok:{order_id}", style=BTN_BUY_STYLE),
         ibtn(text="❌ Отклонить", callback_data=f"admin:no:{order_id}", style=BTN_DANGER_STYLE)]
    ]
    if order:
        keyboard.append([ibtn(text="⛔ Бан", callback_data=f"admin:ban:{order['user_id']}:users:0", style=BTN_DANGER_STYLE)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_after_issue(plan: Optional[str] = None):
    rows = []

    if plan in ("standard", "family"):
        rows.append([ibtn(text=("Стандартная" if plan == "standard" else "Семейная"), callback_data=f"sub:key:{plan}", style=BTN_PRIMARY_STYLE, icon_custom_emoji_id=EMOJI_IDS["standard"] if plan == "standard" else EMOJI_IDS["family"])])

    rows.extend([
        [ibtn(text="📱 Android", url=HAPP_ANDROID_URL, style=BTN_PRIMARY_STYLE),
         ibtn(text="🍎 iPhone", url=HAPP_IOS_URL, style=BTN_PRIMARY_STYLE)],
        [ibtn(text="💻 Windows", url=HAPP_WINDOWS_URL, style=BTN_PRIMARY_STYLE)],
        [ibtn(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK, style=BTN_INFO_STYLE)],
        [ibtn(text="⭐ Оставить отзыв", url=REVIEW_LINK, style=BTN_INFO_STYLE)],
        [ibtn(text="🏠 В меню", callback_data="menu:main", style=BTN_PRIMARY_STYLE)],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_require_subscription():
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text="📣 Подписаться на канал", url=TG_CHANNEL, style=BTN_PRIMARY_STYLE)],
        [ibtn(text="✅ Проверить подписку", callback_data="checksub", style=BTN_BUY_STYLE)],
    ])

def kb_sub_no_sub(user_id: int):
    rows = [[ibtn(text="Купить подписку", callback_data="menu:buy", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["buy"] )]]

    if not db_trial_used(user_id):
        rows.append([ibtn(text="🎁 Пробная подписка", callback_data="menu:trial", style=BTN_BUY_STYLE, icon_custom_emoji_id=EMOJI_IDS["trial"])])

    active = db_get_active_order(user_id)
    if active:
        rows.append([ibtn(text="❌ Отменить заказ", callback_data="menu:cancel_order", style=BTN_DANGER_STYLE)])

    rows.append([ibtn(text="🏠 В меню", callback_data="menu:main", style=BTN_PRIMARY_STYLE)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_sub_with_refresh(user_id: int):
    rows = []
    subs = db_get_accepted_subscriptions(user_id)

    plan_buttons = []
    for sub in subs:
        plan = sub.get("plan")
        if plan in ("standard", "family"):
            plan_buttons.append(
                InlineKeyboardButton(text=("Стандартная" if plan == "standard" else "Семейная"), callback_data=f"sub:key:{plan}", icon_custom_emoji_id=EMOJI_IDS["standard"] if plan == "standard" else EMOJI_IDS["family"])
            )

    if plan_buttons:
        rows.append(plan_buttons[:2])

    rows.append([InlineKeyboardButton(text="🔄 Обновить ключ", callback_data="sub:refresh")])

    active = db_get_active_order(user_id)
    if active:
        rows.append([InlineKeyboardButton(text="❌ Отменить заказ", callback_data="menu:cancel_order")])

    rows.extend([
        [InlineKeyboardButton(text="📱 Android", url=HAPP_ANDROID_URL),
         InlineKeyboardButton(text="🍎 iPhone", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Windows", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text="📦 Заказы", callback_data="admin:list", style=BTN_PRIMARY_STYLE),
         ibtn(text="🔎 Найти заказ", callback_data="admin:search", style=BTN_INFO_STYLE)],
        [ibtn(text="👥 Пользователи", callback_data="admin:users:0", style=BTN_PRIMARY_STYLE),
         ibtn(text="⛔ Баны", callback_data="admin:banned:0", style=BTN_DANGER_STYLE)],
        [ibtn(text="💰 Прибыль", callback_data="admin:profit", style=BTN_BUY_STYLE),
         ibtn(text="📢 Рассылка", callback_data="admin:broadcast", style=BTN_INFO_STYLE)],
        [ibtn(text="🏷 Цены", callback_data="admin:prices", style=BTN_PRIMARY_STYLE),
         ibtn(text="🔑 Ключи", callback_data="admin:keys", style=BTN_INFO_STYLE)],
        [ibtn(text="📝 GitHub TXT", callback_data="admin:github", style=BTN_PRIMARY_STYLE)],
    ])

def kb_admin_list(rows):
    keyboard = []
    for oid, uid, uname, plan, amount, created_at in rows[:20]:
        u = f"@{uname}" if uname else str(uid)
        plan_badge = "🟩" if plan == "standard" else "🟦"
        keyboard.append([InlineKeyboardButton(
            text=f"{plan_badge} #{oid} • {amount}₽ • {u}",
            callback_data=f"admin:view:{oid}"
        )])
    keyboard.append([
        ibtn(text="🔄 Обновить", callback_data="admin:list", style=BTN_BUY_STYLE),
        ibtn(text="⬅️ Назад", callback_data="admin:home", style=BTN_PRIMARY_STYLE)
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def kb_admin_prices():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text=f"🟩 Стандарт • {std_price}₽", callback_data="admin:price:set:standard", style=BTN_PRIMARY_STYLE)],
        [ibtn(text=f"🟦 Семейная • {fam_price}₽", callback_data="admin:price:set:family", style=BTN_PRIMARY_STYLE)],
        [ibtn(text="⬅️ Назад", callback_data="admin:home", style=BTN_PRIMARY_STYLE)],
    ])

def kb_admin_keys():
    s = db_keys_count("standard")
    f = db_keys_count("family")
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text=f"➕ Добавить в Стандарт ({s})", callback_data="admin:keys:add:standard", style=BTN_BUY_STYLE)],
        [ibtn(text=f"➕ Добавить в Семейную ({f})", callback_data="admin:keys:add:family", style=BTN_BUY_STYLE)],
        [ibtn(text="🧹 Очистить Стандарт", callback_data="admin:keys:clear:standard", style=BTN_DANGER_STYLE)],
        [ibtn(text="🧹 Очистить Семейную", callback_data="admin:keys:clear:family", style=BTN_DANGER_STYLE)],
        [ibtn(text="⬅️ Назад", callback_data="admin:home", style=BTN_PRIMARY_STYLE)],
    ])


def kb_admin_github_menu():
    enabled = bool(GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO)
    status = "🟢 GitHub подключен" if enabled else "🔴 GitHub не настроен"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text=status, callback_data="noop", style=BTN_INFO_STYLE)],
        [ibtn(text="🟩 Стандарт TXT", callback_data="admin:github:file:standard:0", style=BTN_PRIMARY_STYLE)],
        [ibtn(text="🟦 Семейная TXT", callback_data="admin:github:file:family:0", style=BTN_PRIMARY_STYLE)],
        [ibtn(text="⬅️ Назад", callback_data="admin:home", style=BTN_PRIMARY_STYLE)],
    ])


def kb_admin_github_file(plan: str, lines: List[str], page: int = 0, page_size: int = 15):
    keyboard = []
    total = len(lines)
    start = page * page_size
    end = min(total, start + page_size)

    for idx in range(start, end):
        title, url = parse_named_vless_line(lines[idx])
        label = title or shorten_vless(url or lines[idx], 28)
        prefix = "🟩" if plan == "standard" else "🟦"
        keyboard.append([ibtn(text=f"{prefix} {idx + 1}. {label}", callback_data=f"admin:gh:item:{plan}:{page}:{idx}", style=BTN_INFO_STYLE)])

    nav = []
    max_page = max(0, (total - 1) // page_size) if total > 0 else 0
    if page > 0:
        nav.append(ibtn(text="⬅️", callback_data=f"admin:github:file:{plan}:{page - 1}", style=BTN_PRIMARY_STYLE))
    nav.append(ibtn(text=f"{page + 1}/{max_page + 1}", callback_data="noop", style=BTN_INFO_STYLE))
    if page < max_page:
        nav.append(ibtn(text="➡️", callback_data=f"admin:github:file:{plan}:{page + 1}", style=BTN_PRIMARY_STYLE))
    if nav:
        keyboard.append(nav)

    keyboard.append([ibtn(text="➕ Добавить новую строку", callback_data=f"admin:gh:add:{plan}", style=BTN_BUY_STYLE)])
    keyboard.append([ibtn(text="⬅️ GitHub TXT", callback_data="admin:github", style=BTN_PRIMARY_STYLE)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_admin_github_item(plan: str, idx: int, page: int):
    back = f"admin:github:file:{plan}:{page}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text="✏️ Заменить строку", callback_data=f"admin:gh:edit:{plan}:{idx}:{page}", style=BTN_BUY_STYLE)],
        [ibtn(text="🗑 Удалить строку", callback_data=f"admin:gh:delete:{plan}:{idx}:{page}", style=BTN_DANGER_STYLE)],
        [ibtn(text="⬅️ Назад к списку", callback_data=back, style=BTN_PRIMARY_STYLE)],
    ])


def kb_confirm_clear(plan: str):
    title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text=f"✅ Да, очистить {title}", callback_data=f"admin:keys:clear_yes:{plan}", style=BTN_DANGER_STYLE)],
        [ibtn(text="⬅️ Не очищать", callback_data="admin:keys", style=BTN_PRIMARY_STYLE)],
    ])

def kb_admin_profit():
    return InlineKeyboardMarkup(inline_keyboard=[
        [ibtn(text="♻️ Сбросить прибыль", callback_data="admin:profit:reset", style=BTN_DANGER_STYLE)],
        [ibtn(text="⬅️ Админ", callback_data="admin:home", style=BTN_PRIMARY_STYLE)],
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

    if mode == "users":
        keyboard.append([InlineKeyboardButton(text="🔎 Поиск пользователя", callback_data="admin:usersearch")])
    elif mode == "banned":
        keyboard.append([InlineKeyboardButton(text="🔎 Поиск среди банов", callback_data="admin:usersearch:banned")])

    keyboard.append([ibtn(text="⬅️ Админ", callback_data="admin:home", style=BTN_PRIMARY_STYLE)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def kb_admin_user_view(user_id: int, mode: str, page: int):
    user = db_get_user(user_id)
    buttons = []

    if user:
        if user.get("is_banned"):
            buttons.append([InlineKeyboardButton(text="✅ Разбанить", callback_data=f"admin:unban:{user_id}:{mode}:{page}")])
        else:
            buttons.append([InlineKeyboardButton(text="⛔ Забанить и аннулировать", callback_data=f"admin:ban:{user_id}:{mode}:{page}")])

    buttons.append([
        InlineKeyboardButton(text="🟩 Выдать стандарт", callback_data=f"admin:give:{user_id}:standard:{mode}:{page}"),
        InlineKeyboardButton(text="🟦 Выдать семейную", callback_data=f"admin:give:{user_id}:family:{mode}:{page}"),
    ])
    buttons.append([InlineKeyboardButton(text="🎁 Сбросить пробник", callback_data=f"admin:trialreset:{user_id}:{mode}:{page}")])

    # ===== ДОБАВЛЕНА КНОПКА ДЛЯ ОТПРАВКИ ЛИЧНОГО СООБЩЕНИЯ =====
    buttons.append([InlineKeyboardButton(text="✉️ Написать сообщение", callback_data=f"msguser:{user_id}")])

    back_target = "users" if mode == "users" else "banned"
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:{back_target}:{page}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ================== SUBSCRIPTION CHECK ==================
async def is_user_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(TG_CHANNEL_USERNAME, user_id)
        return member.status in {"member", "administrator", "creator"}
    except Exception:
        return False


async def send_subscription_required(chat_id: int):
    await bot.send_message(
        chat_id,
        "🔒 *Доступ к боту только для подписчиков канала.*\n\n"
        "1. Подпишись на канал\n"
        "2. Нажми *Проверить подписку*\n\n"
        "После этого бот откроет меню.",
        reply_markup=kb_require_subscription()
    )


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


class SubscriptionMiddleware(BaseMiddleware):
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

        if isinstance(event, CallbackQuery) and event.data == "checksub":
            return await handler(event, data)

        if await is_user_subscribed(from_user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            await send_subscription_required(event.chat.id)
        elif isinstance(event, CallbackQuery):
            await event.answer("Сначала подпишись на канал", show_alert=True)
            try:
                await send_subscription_required(event.message.chat.id)
            except Exception:
                pass
        return


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

dp.message.middleware(SubscriptionMiddleware())
dp.callback_query.middleware(SubscriptionMiddleware())

dp.message.middleware(BanMiddleware())
dp.callback_query.middleware(BanMiddleware())


# ================== HELPERS ==================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def github_is_configured() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO and GITHUB_BRANCH)


def github_plan_path(plan: str) -> str:
    return GITHUB_STANDARD_PATH if plan == "standard" else GITHUB_FAMILY_PATH


def parse_named_vless_line(line: str) -> Tuple[str, str]:
    raw = (line or "").strip()
    if not raw:
        return "", ""
    if "|" in raw:
        left, right = raw.split("|", 1)
        return left.strip(), right.strip()
    return "", raw


def shorten_vless(value: str, limit: int = 42) -> str:
    value = (value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def github_get_file(path: str) -> Tuple[str, str]:
    if not github_is_configured():
        raise RuntimeError("GitHub не настроен")

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{urlquote(path)}?ref={urlquote(GITHUB_BRANCH)}"
    req = urllib_request.Request(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "SkyWhyBot"
    })
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub HTTP {e.code}: {body[:300]}")

    content = data.get("content", "") or ""
    decoded = base64.b64decode(content).decode("utf-8") if content else ""
    sha = data.get("sha", "")
    return decoded, sha


def github_update_file(path: str, content: str, sha: str, message: str):
    if not github_is_configured():
        raise RuntimeError("GitHub не настроен")

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{urlquote(path)}"
    payload = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": GITHUB_BRANCH,
        "sha": sha,
    }
    req = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "SkyWhyBot",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub HTTP {e.code}: {body[:300]}")


def github_read_lines(plan: str) -> Tuple[List[str], str, str]:
    path = github_plan_path(plan)
    text, sha = github_get_file(path)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    return lines, sha, path


def github_write_lines(plan: str, lines: List[str], sha: str, action_text: str):
    path = github_plan_path(plan)
    content = "\n".join([x.rstrip() for x in lines if (x or "").strip()])
    if content:
        content += "\n"
    github_update_file(path, content, sha, action_text)


def build_github_lines_text(plan: str, lines: List[str], page: int = 0, page_size: int = 15) -> str:
    title = "🟩 *Стандарт TXT*" if plan == "standard" else "🟦 *Семейная TXT*"
    total = len(lines)
    start = page * page_size
    end = min(total, start + page_size)

    out = [title, "", f"📄 Файл: `{md_escape(github_plan_path(plan))}`", f"📦 Строк: *{total}*"]

    if total == 0:
        out.append("\nФайл пуст. Можешь добавить новую строку.")
        return "\n".join(out)

    out.append("")
    for idx in range(start, end):
        name, url = parse_named_vless_line(lines[idx])
        label = name or shorten_vless(url or lines[idx], 55)
        out.append(f"`{idx + 1}.` {md_escape(label)}")

    return "\n".join(out)


def build_github_item_text(plan: str, idx: int, line: str) -> str:
    title = "🟩 *Стандарт TXT*" if plan == "standard" else "🟦 *Семейная TXT*"
    name, url = parse_named_vless_line(line)
    out = [title, "", f"🔢 Строка: *{idx + 1}*"]
    if name:
        out.append(f"🏷 Название: *{md_escape(name)}*")
    out.append(f"🔗 Текущее значение:\n`{md_escape(url or line)}`")
    out.append("\nМожно прислать только новую `vless://...` — тогда название слева сохранится. Или пришли полную новую строку.")
    return "\n".join(out)


async def send_banner_or_text(chat_id: int, text: str, reply_markup=None, parse_mode: Optional[str] = None):
    try:
        if os.path.exists(BANNER_PATH):
            await bot.send_photo(chat_id, FSInputFile(BANNER_PATH), caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)


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
        await bot.send_message(chat_id, "Нижнее меню обновлено 👇", reply_markup=kb_reply_menu(user_id))
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


async def send_admin_user_search_results(message: Message, query: str, page: int = 0, banned_only: bool = False):
    page = max(0, page)
    total = db_count_search_users(query, banned_only=banned_only)
    rows = db_search_users(query, limit=USERS_PAGE_SIZE, offset=page * USERS_PAGE_SIZE, banned_only=banned_only)
    mode = "banned" if banned_only else "users"

    title = "⛔ *Поиск среди банов*" if banned_only else "👥 *Поиск пользователей*"
    text = (
        f"{title}\n\n"
        f"🔎 Запрос: *{md_escape(query)}*\n"
        f"📄 Найдено: *{total}*\n"
        f"📦 На странице: *{len(rows)}*"
    )

    if total == 0:
        text += "\n\nНичего не найдено. Ищи по ID, @username или имени."

    await message.answer(text, reply_markup=kb_admin_users_page(rows, page, total, mode))




@dp.message(F.text == "🛒 Купить")
async def reply_buy_btn(m: Message):
    await m.answer(text_buy_intro(), reply_markup=kb_buy(), parse_mode="HTML")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "🎁 Пробная подписка")
async def reply_trial_btn(m: Message):
    await m.answer(html_text_trial_offer(), reply_markup=kb_trial_offer(), parse_mode="HTML")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "📢 Канал")
async def reply_channel_btn(m: Message):
    await m.answer(f"📢 Наш канал: {TG_CHANNEL}")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "🆘 Поддержка")
async def reply_support_btn(m: Message):
    await m.answer(f"🆘 Поддержка: {TG_CHANNEL}")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "⚙️ Админ")
async def reply_admin_btn(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("⚙️ *Админ-панель*", reply_markup=kb_admin_menu())
    await m.answer("Нижнее меню админа 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "📦 Заказы")
async def reply_admin_orders_btn(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = db_list_pending()
    if not rows:
        await m.answer("📦 Активных заявок сейчас нет.", reply_markup=kb_admin_menu())
    else:
        await m.answer("📦 *Заявки на проверку*", reply_markup=kb_admin_list(rows))
    await m.answer("Нижнее меню админа 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "👥 Пользователи")
async def reply_admin_users_btn(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = db_list_users(limit=USERS_PAGE_SIZE, offset=0)
    total = db_count_users()
    stats = db_users_stats()
    text = (
        "👥 *Пользователи*\n\n"
        f"👤 Всего в базе: *{stats['total']}*\n"
        f"🟢 Активны за 24ч: *{stats['active_day']}*\n"
        f"🟡 Активны за 7д: *{stats['active_week']}*\n"
        f"🚫 Заблокировали бота: *{stats['blocked']}*\n"
        f"⛔ Забанены: *{stats['banned']}*"
    )
    await m.answer(text, reply_markup=kb_admin_users_page(rows, 0, total, "users"))
    await m.answer("Нижнее меню админа 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "💰 Прибыль")
async def reply_admin_profit_btn(m: Message):
    if not is_admin(m.from_user.id):
        return
    profit = db_profit_totals()
    text = (
        "💰 *Прибыль SkyWhy*\n\n"
        f"За 24ч: *{profit['day']}₽*\n"
        f"За 7 дней: *{profit['week']}₽*\n"
        f"За 30 дней: *{profit['month']}₽*\n"
        f"Всего после сброса: *{profit['total']}₽*"
    )
    await m.answer(text, reply_markup=kb_admin_profit())
    await m.answer("Нижнее меню админа 👇", reply_markup=kb_reply_menu(m.from_user.id))


# ================== YOOKASSA ==================
def yk_enabled() -> bool:
    return bool(YK_SHOP_ID and YK_SECRET_KEY and BASE_URL)


def yk_auth_header() -> str:
    token = base64.b64encode(f"{YK_SHOP_ID}:{YK_SECRET_KEY}".encode("utf-8")).decode("utf-8")
    return f"Basic {token}"


def _yk_http_request(method: str, path: str, payload: Optional[dict] = None, idempotence_key: Optional[str] = None) -> dict:
    url = f"https://api.yookassa.ru{path}"
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": yk_auth_header(),
        "Content-Type": "application/json",
    }
    if idempotence_key:
        headers["Idempotence-Key"] = idempotence_key

    req = urllib_request.Request(url=url, data=body, headers=headers, method=method.upper())
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib_error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(raw or f"HTTP {e.code}")


async def yk_request(method: str, path: str, payload: Optional[dict] = None, idempotence_key: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_yk_http_request, method, path, payload, idempotence_key)


async def yk_create_payment(order: dict) -> tuple[str, str]:
    amount_value = f"{int(order['amount'])}.00"
    return_url = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else TG_CHANNEL
    payload = {
        "amount": {
            "value": amount_value,
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "description": f"SkyWhy VPN order #{order['id']} ({order['plan']})",
        "metadata": {
            "order_id": str(order["id"]),
            "user_id": str(order["user_id"]),
            "plan": str(order["plan"]),
        },
    }
    data = await yk_request("POST", "/v3/payments", payload=payload, idempotence_key=str(uuid.uuid4()))
    payment_id = str(data.get("id") or "")
    payment_url = str((data.get("confirmation") or {}).get("confirmation_url") or "")
    if not payment_id or not payment_url:
        raise RuntimeError("YooKassa не вернула payment_id или confirmation_url")
    db_set_payment_provider(order["id"], payment_id, payment_url)
    return payment_id, payment_url


async def yk_get_payment(payment_id: str) -> dict:
    return await yk_request("GET", f"/v3/payments/{payment_id}")


async def ensure_order_payment(order: dict) -> tuple[str, str]:
    payment_id = (order.get("payment_provider_id") or "").strip()
    payment_url = (order.get("payment_url") or "").strip()

    if payment_id and payment_url and order.get("status") == "waiting_receipt":
        return payment_id, payment_url

    return await yk_create_payment(order)


async def issue_paid_order(order_id: int, payment_data: Optional[dict] = None) -> tuple[bool, str]:
    order = db_get_order(order_id)
    if not order:
        return False, "Заказ не найден"

    if order["status"] == "accepted":
        return True, "Уже выдано"

    if db_is_banned(order["user_id"]):
        return False, "Пользователь забанен"

    if payment_data is not None:
        provider_id = str(payment_data.get("id") or "")
        if provider_id:
            db_set_payment_provider(order_id, provider_id, order.get("payment_url"))
        if str(payment_data.get("status") or "") != "succeeded":
            return False, "Оплата ещё не подтверждена"

    key = take_key(order["plan"], order_id=order_id)
    if not key:
        return False, "Для этого тарифа нет ключей в базе"

    try:
        await send_key_to_user(order["user_id"], order["plan"], key)
    except TelegramForbiddenError:
        return False, "Пользователь не открыл бот / заблокировал его"
    except TelegramBadRequest as e:
        return False, f"TelegramBadRequest: {e}"
    except Exception as e:
        return False, f"Ошибка отправки ключа: {type(e).__name__}"

    db_set_issued(order_id, key)
    db_set_status(order_id, "accepted")

    try:
        await refresh_reply_menu(order["user_id"], order["user_id"])
    except Exception:
        pass

    return True, key


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    event = str(payload.get("event") or "")
    obj = payload.get("object") or {}
    payment_id = str(obj.get("id") or "")

    if not payment_id:
        return web.json_response({"ok": True})

    try:
        payment = await yk_get_payment(payment_id)
    except Exception as e:
        print("YOO_WEBHOOK_VERIFY_ERROR:", repr(e))
        return web.json_response({"ok": False}, status=500)

    metadata = payment.get("metadata") or {}
    order_id_raw = metadata.get("order_id")
    if not order_id_raw:
        order = db_get_order_by_payment_provider(payment_id)
        order_id_raw = order["id"] if order else None

    if not order_id_raw:
        return web.json_response({"ok": True})

    try:
        order_id = int(order_id_raw)
    except Exception:
        return web.json_response({"ok": True})

    order = db_get_order(order_id)
    if order:
        db_set_payment_provider(order_id, payment_id, order.get("payment_url"))

    if event == "payment.succeeded" or str(payment.get("status") or "") == "succeeded":
        ok, info = await issue_paid_order(order_id, payment)
        if not ok:
            print("YOO_WEBHOOK_ISSUE_FAIL:", order_id, info)

    return web.json_response({"ok": True})


async def healthcheck_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "skywhy-vpn-bot"})


async def trial_info_handler(request: web.Request) -> web.Response:
    secret = str(request.query.get("secret") or "")
    token = str(request.match_info.get("token") or "").strip()

    if not TRIAL_SHARED_SECRET or secret != TRIAL_SHARED_SECRET:
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    trial = db_get_trial_by_token(token)
    if not trial:
        return web.json_response({"ok": False, "error": "not_found"}, status=404)

    return web.json_response({
        "ok": True,
        "user_id": trial["user_id"],
        "token": trial["token"],
        "expires_at": int(trial["expires_at"]),
        "is_active": int(trial["expires_at"]) > int(time.time()),
        "plan": "standard",
    })


async def start_http_server() -> tuple[web.AppRunner, web.TCPSite]:
    app = web.Application()
    app.router.add_get("/", healthcheck_handler)
    app.router.add_get("/trial-info/{token}", trial_info_handler)
    app.router.add_post("/yookassa/webhook", yookassa_webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    print(f"HTTP SERVER STARTED ON :{PORT}")
    return runner, site


# ================== START / MENU ==================
@dp.message(CommandStart())
async def start(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main(m.from_user.id), parse_mode="HTML")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main(m.from_user.id), parse_mode="HTML")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "🏠 Меню")
async def menu_btn(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main(m.from_user.id), parse_mode="HTML")
    await m.answer("Нижнее меню 👇", reply_markup=kb_reply_menu(m.from_user.id))


@dp.message(F.text == "📦 Моя подписка")
async def mysub_btn(m: Message):
    subs = db_get_accepted_subscriptions(m.from_user.id)
    if not subs:
        await m.answer(html_text_subscription_card(m.from_user, None), reply_markup=kb_sub_no_sub(m.from_user.id), parse_mode="HTML")
        await refresh_reply_menu(m.chat.id, m.from_user.id)
        return

    await m.answer(html_text_subscription_card(m.from_user, subs), reply_markup=kb_sub_with_refresh(m.from_user.id), parse_mode="HTML")
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

    await m.answer("✅ Заказ отменён. Можешь сразу оформить новый через меню.", reply_markup=kb_main(m.from_user.id))
    await refresh_reply_menu(m.chat.id, m.from_user.id)


# ================== ADMIN COMMAND ==================


@dp.message(Command("etest"))
async def etest(m: Message):
    await m.answer(
        f"{tg_emoji(EMOJI_IDS['globe'], '🌐')} TEST\n"
        f"{tg_emoji(EMOJI_IDS['tariff'], '🛍')} TEST\n"
        f"{tg_emoji(EMOJI_IDS['standard'], '🟩')} TEST\n"
        f"{tg_emoji(EMOJI_IDS['family'], '🟦')} TEST",
        parse_mode="HTML"
    )

@dp.message(Command("resettrial"))
async def reset_trial_cmd(m: Message):
    if not is_admin(m.from_user.id):
        await m.answer("Нет доступа")
        return

    parts = (m.text or "").strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await m.answer("Использование: /resettrial USER_ID")
        return

    user_id = int(parts[1].strip())
    deleted = db_delete_trial(user_id)

    try:
        await bot.send_message(
            user_id,
            "🎁 Администратор сбросил твой пробный доступ. Теперь ты можешь получить пробник заново."
        )
    except Exception:
        pass

    if deleted:
        await m.answer(f"✅ Пробник для пользователя `{md_escape(str(user_id))}` сброшен.")
    else:
        await m.answer(f"ℹ️ У пользователя `{md_escape(str(user_id))}` не было записи пробника.")


@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("🛠 *Админ-панель*\nВыбери раздел 👇", reply_markup=kb_admin_menu())


# ================== CALLBACK: MENU ==================
@dp.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data == "checksub")
async def check_subscription(call: CallbackQuery):
    if await is_user_subscribed(call.from_user.id):
        await call.message.answer("✅ Подписка найдена. Добро пожаловать!", reply_markup=kb_main(call.from_user.id))
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
        await call.answer("Готово ✅", show_alert=True)
        return

    await call.answer("Подписка на канал не найдена", show_alert=True)
    try:
        await call.message.answer(
            "⚠️ Я всё ещё не вижу подписку на канал. Подпишись и нажми кнопку ещё раз.",
            reply_markup=kb_require_subscription()
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(call: CallbackQuery):
    try:
        action = call.data.split(":", 1)[1]

        if action == "main":
            await send_banner_or_text(call.message.chat.id, text_menu(), reply_markup=kb_main(call.from_user.id), parse_mode="HTML")
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "buy":
            await call.message.answer(text_buy_intro(), reply_markup=kb_buy(), parse_mode="HTML")
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "trial":
            await call.message.answer(html_text_trial_offer(), reply_markup=kb_trial_offer(), parse_mode="HTML")
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "sub":
            subs = db_get_accepted_subscriptions(call.from_user.id)
            if not subs:
                await call.message.answer(
                    html_text_subscription_card(call.from_user, None),
                    reply_markup=kb_sub_no_sub(call.from_user.id),
                    parse_mode="HTML"
                )
                await refresh_reply_menu(call.message.chat.id, call.from_user.id)
                return

            await call.message.answer(
                html_text_subscription_card(call.from_user, subs),
                reply_markup=kb_sub_with_refresh(call.from_user.id),
                parse_mode="HTML"
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if action == "info":
            await call.message.answer(
                f"{tg_emoji(EMOJI_IDS['globe'], 'ℹ️')} <b>Информация</b>\n\n"
                f"📄 <b>Пользовательское соглашение:</b>\n{AGREEMENT_URL}\n\n"
                f"🔐 <b>Политика конфиденциальности:</b>\n{PRIVACY_URL}\n\n"
                f"📩 <b>Поддержка:</b>\n{SUPPORT_EMAIL}",
                parse_mode="HTML"
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
                "✅ Заказ отменён. Можешь сразу оформить новый через меню.",
                reply_markup=kb_main(call.from_user.id)
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return
    finally:
        try:
            await call.answer()
        except Exception:
            pass


@dp.callback_query(F.data == "trial:get")
async def trial_get(call: CallbackQuery):
    try:
        trial = db_get_trial(call.from_user.id)
        now_ts = int(time.time())

        if trial and int(trial.get("expires_at") or 0) > now_ts:
            await call.answer("Пробник уже активирован", show_alert=True)
            await send_trial_link_message(call.message, trial["token"], int(trial["expires_at"]), is_repeat=True)
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        if db_trial_used(call.from_user.id):
            await call.answer("Пробник можно получить только один раз", show_alert=True)
            return

        if not happ_required_ready():
            await call.answer("Пробник пока не настроен", show_alert=True)
            await call.message.answer(
                "⚠️ Пробная подписка ещё не готова.

"
                "Для неё нужно настроить переменные HAPP_PROVIDER_CODE, HAPP_AUTH_KEY и TRIAL_SHARED_SECRET."
            )
            return

        token = secrets.token_urlsafe(24)
        expires_at = now_ts + TRIAL_DURATION_SEC
        db_create_or_replace_trial(call.from_user.id, token, expires_at)

        await send_trial_link_message(call.message, token, expires_at, is_repeat=False)
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
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
                f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\nНажми *🔄 Проверить оплату* после оплаты или *❌ Отменить заказ*."
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        plan = call.data.split(":", 1)[1]
        if plan not in ("standard", "family"):
            await call.answer("Ошибка тарифа", show_alert=True)
            return

        plan_name, conditions, _device_limit, amount = plan_meta(plan)

        await call.message.answer(
            f"📄 *Перед покупкой ознакомься с условиями использования.*\n\n"
            f"📦 Тариф: *{plan_name}*\n"
            f"{conditions}\n"
            f"💰 Сумма: *{amount}₽*\n\n"
            "Нажимая кнопку *«Принять условия»*, ты подтверждаешь согласие с пользовательским соглашением.",
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
                f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\nНажми *🔄 Проверить оплату* после оплаты или *❌ Отменить заказ*."
            )
            await refresh_reply_menu(call.message.chat.id, call.from_user.id)
            return

        plan = call.data.split(":", 1)[1]
        if plan not in ("standard", "family"):
            await call.answer("Ошибка тарифа", show_alert=True)
            return

        plan_name, conditions, _device_limit, amount = plan_meta(plan)
        order_id = db_create_order(user_id, username, plan, amount)

        try:
            _payment_id, payment_url = await ensure_order_payment(db_get_order(order_id))
        except Exception as e:
            db_set_status(order_id, "cancelled")
            await call.message.answer(f"⚠️ Не удалось создать оплату: `{md_escape(str(e))}`")
            return

        msg = await call.message.answer(
            f"🧾 *Заказ #{order_id}*\n\n"
            f"📦 Тариф: *{plan_name}*\n"
            f"{conditions}\n"
            f"💰 Сумма: *{amount}₽*\n\n"
            f"{PAYMENT_TEXT}\n\n"
            "После оплаты бот сам пришлёт ключ. Если оплата уже прошла — нажми *🔄 Проверить оплату*.",
            reply_markup=kb_payment(order_id, payment_url)
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

        await bot.send_message(user_id, "✅ Заказ отменён. Можешь сразу оформить новый через меню.", reply_markup=kb_main(user_id))
        await refresh_reply_menu(call.message.chat.id, call.from_user.id)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


@dp.callback_query(F.data.startswith("checkpay:"))
async def check_payment_status(call: CallbackQuery):
    try:
        order_id = int(call.data.split(":", 1)[1])
        order = db_get_order(order_id)
        if not order or order["user_id"] != call.from_user.id:
            await call.answer("Заказ не найден", show_alert=True)
            return

        if order["status"] == "accepted":
            await call.answer("Оплата уже подтверждена ✅", show_alert=True)
            return

        payment_id = (order.get("payment_provider_id") or "").strip()
        payment_url = (order.get("payment_url") or "").strip()

        if not payment_id or not payment_url:
            try:
                payment_id, payment_url = await ensure_order_payment(order)
            except Exception as e:
                await call.answer(f"Не удалось создать оплату: {e}", show_alert=True)
                return

            await call.message.answer(
                f"💳 *Ссылка на оплату обновлена для заказа #{order_id}*",
                reply_markup=kb_payment(order_id, payment_url)
            )
            await call.answer("Ссылка обновлена", show_alert=True)
            return

        try:
            payment = await yk_get_payment(payment_id)
        except Exception as e:
            await call.answer(f"Не удалось проверить оплату: {e}", show_alert=True)
            return

        status = str(payment.get("status") or "")
        if status == "succeeded":
            ok, info = await issue_paid_order(order_id, payment)
            if ok:
                await call.answer("Оплата подтверждена ✅", show_alert=True)
            else:
                await call.answer(info, show_alert=True)
            return

        if status in ("canceled", "cancelled"):
            try:
                _new_id, new_url = await yk_create_payment(order)
            except Exception as e:
                await call.answer(f"Платёж отменён и новый не создался: {e}", show_alert=True)
                return

            await call.message.answer(
                f"⚠️ Предыдущий платёж отменён. Вот новая ссылка для заказа #{order_id}.",
                reply_markup=kb_payment(order_id, new_url)
            )
            await call.answer("Создал новую ссылку", show_alert=True)
            return

        await call.answer("Платёж ещё не подтверждён. Если уже оплатил — подожди пару секунд и нажми ещё раз.", show_alert=True)
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

    if (m.text or "").strip() in {"🏠 Меню", "📦 Моя подписка", "❌ Отменить заказ"}:
        return

    active = db_get_active_order(m.from_user.id)
    if not active:
        return

    await m.answer(
        "💳 Оплата теперь проходит автоматически через ЮKassa. Нажми кнопку ниже.",
        reply_markup=kb_payment(active["id"], active.get("payment_url"))
    )


# ================== ISSUE KEY ==================
async def send_key_to_user(user_id: int, plan: str, key: str):
    _plan_name, conditions, _device_limit, _amount = plan_meta(plan)
    await bot.send_message(
        user_id,
        "🎉 *Оплата подтверждена!*\n\n"
        f"📦 Тариф: *{pretty_plan_name(plan)}*\n"
        "♾ Срок действия: *Навсегда*\n"
        f"{conditions}\n\n"
        "🔑 *Ключ не показываю длинной строкой в сообщении, чтобы было аккуратнее.*\n"
        "Нажми кнопку с тарифом ниже. Бот пришлёт ключ отдельным сообщением.\n"
        "На телефоне можно нажать на код или зажать его, чтобы скопировать.\n\n"
        "📲 *Как подключить в Happ:*\n"
        "1. Установи приложение Happ\n"
        "2. Открой его\n"
        "3. Нажми Add / Import / Подписка\n"
        "4. Вставь ключ и сохрани\n\n"
        "Все нужные ссылки уже ниже 👇",
        reply_markup=kb_after_issue(plan)
    )


@dp.callback_query(F.data.startswith("sub:key:"))
async def show_subscription_key(call: CallbackQuery):
    try:
        plan = call.data.split(":", 2)[2]
        if plan not in ("standard", "family"):
            await call.answer("Неизвестный тариф", show_alert=True)
            return

        subs = db_get_accepted_subscriptions(call.from_user.id)
        selected_sub = next((sub for sub in subs if sub.get("plan") == plan), None)
        if not selected_sub:
            await call.answer("У тебя нет такого тарифа", show_alert=True)
            return

        key = selected_sub.get("issued_key") or ""
        if not key:
            await call.answer("Ключ пока не найден", show_alert=True)
            return

        await call.message.answer(
            f"📋 *{pretty_plan_name(plan)}*\n\n"
            f"💳 Системное название: *{plan_meta(plan)[0]}*\n\n"
            "Нажми на ключ ниже или зажми его, чтобы скопировать:\n\n"
            f"`{key}`"
        )
    finally:
        try:
            await call.answer()
        except Exception:
            pass

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
    await call.message.answer("📦 *Заказы на проверке*", reply_markup=kb_admin_list(rows))
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


@dp.callback_query(F.data == "admin:usersearch")
async def admin_user_search(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()
    await state.set_state(AdminStates.user_search_wait)
    await state.update_data(user_search_banned_only=False)
    await call.message.answer(
        "🔎 *Поиск пользователя*\n\n"
        "Отправь сюда:\n"
        "• user_id (`123456789`)\n"
        "• username (`@username`)\n"
        "• имя (`Иван`)\n\n"
        "Отмена: `отмена`",
        reply_markup=kb_admin_menu()
    )


@dp.callback_query(F.data == "admin:usersearch:banned")
async def admin_user_search_banned(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()
    await state.set_state(AdminStates.user_search_wait)
    await state.update_data(user_search_banned_only=True)
    await call.message.answer(
        "🔎 *Поиск среди банов*\n\n"
        "Отправь сюда user_id, @username или имя.\n\n"
        "Отмена: `отмена`",
        reply_markup=kb_admin_menu()
    )


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


@dp.callback_query(F.data == "admin:github")
async def admin_github(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.message.answer("📝 *GitHub TXT*\nУправление файлами стандарт/семейка:", reply_markup=kb_admin_github_menu())
    await call.answer()


@dp.callback_query(F.data.startswith("admin:github:file:"))
async def admin_github_file(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 5:
        await call.answer("Ошибка", show_alert=True)
        return

    plan = parts[3]
    page = int(parts[4]) if parts[4].isdigit() else 0
    if plan not in ("standard", "family"):
        await call.answer("Ошибка", show_alert=True)
        return

    try:
        lines, _sha, _path = github_read_lines(plan)
    except Exception as e:
        await call.message.answer(f"❌ Не удалось открыть GitHub TXT.\n`{md_escape(str(e))}`", reply_markup=kb_admin_github_menu())
        await call.answer()
        return

    await call.message.answer(build_github_lines_text(plan, lines, page=page), reply_markup=kb_admin_github_file(plan, lines, page=page))
    await call.answer()


@dp.callback_query(F.data.startswith("admin:gh:item:"))
async def admin_github_item(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 6:
        await call.answer("Ошибка", show_alert=True)
        return

    plan = parts[3]
    page = int(parts[4]) if parts[4].isdigit() else 0
    idx = int(parts[5]) if parts[5].isdigit() else -1
    if plan not in ("standard", "family") or idx < 0:
        await call.answer("Ошибка", show_alert=True)
        return

    try:
        lines, _sha, _path = github_read_lines(plan)
        if idx >= len(lines):
            raise RuntimeError("Строка уже изменилась или пропала")
    except Exception as e:
        await call.message.answer(f"❌ Не удалось открыть строку.\n`{md_escape(str(e))}`", reply_markup=kb_admin_github_menu())
        await call.answer()
        return

    await call.message.answer(build_github_item_text(plan, idx, lines[idx]), reply_markup=kb_admin_github_item(plan, idx, page))
    await call.answer()


@dp.callback_query(F.data.startswith("admin:gh:add:"))
async def admin_github_add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    plan = call.data.split(":")[-1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка", show_alert=True)
        return

    await state.update_data(github_plan=plan)
    await state.set_state(AdminStates.github_add_wait)
    title = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    await call.message.answer(
        f"➕ *Добавление строки в GitHub TXT*\n\nТариф: *{title}*\nПришли новую строку целиком.\n\nПримеры:\n`vless://...`\n`Germany 1|vless://...`\n\nОтмена: `отмена`",
        reply_markup=kb_admin_github_menu()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("admin:gh:edit:"))
async def admin_github_edit_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 6:
        await call.answer("Ошибка", show_alert=True)
        return

    plan = parts[3]
    idx = int(parts[4]) if parts[4].isdigit() else -1
    page = int(parts[5]) if parts[5].isdigit() else 0
    if plan not in ("standard", "family") or idx < 0:
        await call.answer("Ошибка", show_alert=True)
        return

    try:
        lines, _sha, _path = github_read_lines(plan)
        if idx >= len(lines):
            raise RuntimeError("Строка уже изменилась или пропала")
    except Exception as e:
        await call.message.answer(f"❌ Не удалось открыть строку.\n`{md_escape(str(e))}`", reply_markup=kb_admin_github_menu())
        await call.answer()
        return

    await state.update_data(github_plan=plan, github_index=idx, github_page=page, github_old_line=lines[idx])
    await state.set_state(AdminStates.github_edit_wait)
    await call.message.answer(build_github_item_text(plan, idx, lines[idx]), reply_markup=kb_admin_github_item(plan, idx, page))
    await call.answer("Пришли новую строку")


@dp.callback_query(F.data.startswith("admin:gh:delete:"))
async def admin_github_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = call.data.split(":")
    if len(parts) < 6:
        await call.answer("Ошибка", show_alert=True)
        return

    plan = parts[3]
    idx = int(parts[4]) if parts[4].isdigit() else -1
    page = int(parts[5]) if parts[5].isdigit() else 0
    if plan not in ("standard", "family") or idx < 0:
        await call.answer("Ошибка", show_alert=True)
        return

    try:
        lines, sha, _path = github_read_lines(plan)
        if idx >= len(lines):
            raise RuntimeError("Строка уже изменилась или пропала")
        deleted = lines.pop(idx)
        github_write_lines(plan, lines, sha, f"Delete line {idx + 1} in {github_plan_path(plan)}")
    except Exception as e:
        await call.message.answer(f"❌ Не удалось удалить строку.\n`{md_escape(str(e))}`", reply_markup=kb_admin_github_menu())
        await call.answer()
        return

    label = shorten_vless((parse_named_vless_line(deleted)[0] or parse_named_vless_line(deleted)[1] or deleted), 50)
    await call.message.answer(
        f"✅ Строка удалена:\n`{md_escape(label)}`",
        reply_markup=kb_admin_github_file(plan, lines, page=min(page, max(0, (len(lines) - 1) // 15)) if lines else 0)
    )
    await call.answer("Удалено ✅")


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
    await call.message.answer("✅ Все ключи этого тарифа удалены из базы.", reply_markup=kb_admin_keys())
    await call.answer()


@dp.callback_query(F.data.startswith("admin:users:"))
async def admin_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    try:
        page = int(call.data.split(":")[-1])
    except Exception:
        page = 0

    await send_admin_users_page(call, page=page, banned_only=False)


@dp.callback_query(F.data.startswith("admin:banned:"))
async def admin_banned(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    try:
        page = int(call.data.split(":")[-1])
    except Exception:
        page = 0

    await send_admin_users_page(call, page=page, banned_only=True)


@dp.callback_query(F.data.startswith("admin:user:"))
async def admin_user_view(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    parts = call.data.split(":")
    if len(parts) < 5:
        await call.message.answer("Ошибка открытия карточки пользователя.")
        return

    try:
        user_id = int(parts[2])
        mode = parts[3]
        page = int(parts[4])
    except Exception:
        await call.message.answer("Ошибка открытия карточки пользователя.")
        return

    if not db_get_user(user_id):
        await call.message.answer("Пользователь не найден")
        return

    try:
        await call.message.answer(
            build_admin_user_text(user_id),
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )
    except Exception as e:
        await call.message.answer(f"Не удалось открыть карточку пользователя: `{md_escape(type(e).__name__)}`")


@dp.callback_query(F.data.startswith("admin:trialreset:"))
async def admin_trial_reset(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer("Сбрасываю пробник...")

    parts = call.data.split(":")
    if len(parts) < 5:
        await call.message.answer("Ошибка сброса пробника.")
        return

    user_id = int(parts[2])
    mode = parts[3]
    page = int(parts[4])

    deleted = db_delete_trial(user_id)

    try:
        await bot.send_message(
            user_id,
            "🎁 Администратор сбросил твой пробный доступ. Теперь ты можешь получить пробник заново."
        )
    except Exception:
        pass

    if deleted:
        await call.message.answer(
            f"✅ Пробник для пользователя `{user_id}` сброшен.",
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )
    else:
        await call.message.answer(
            f"ℹ️ У пользователя `{user_id}` не было записи пробника.",
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )


@dp.callback_query(F.data.startswith("admin:ban:"))
async def admin_ban_user(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    parts = call.data.split(":")
    user_id = int(parts[2])
    mode = parts[3] if len(parts) > 3 else "users"
    page = int(parts[4]) if len(parts) > 4 else 0

    if user_id == ADMIN_ID:
        await call.message.answer("Админа банить нельзя")
        return

    db_ban_user_and_revoke(user_id)

    try:
        await bot.send_message(
            user_id,
            "⛔ Твой доступ аннулирован.\nПодписки отключены, пользоваться ботом больше нельзя."
        )
    except Exception:
        pass

    await call.message.answer(
        f"⛔ *Пользователь* `{user_id}` *забанен.*\n\n"
        "✅ Подписки аннулированы\n"
        "✅ Активные заказы отменены\n"
        "✅ Доступ к боту закрыт",
        reply_markup=kb_admin_user_view(user_id, mode, page)
    )


@dp.callback_query(F.data.startswith("admin:unban:"))
async def admin_unban_user(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await call.answer()

    parts = call.data.split(":")
    if len(parts) < 5:
        await call.message.answer("Ошибка разбана пользователя.")
        return

    user_id = int(parts[2])
    mode = parts[3]
    page = int(parts[4])

    db_unban_user(user_id)

    try:
        await bot.send_message(
            user_id,
            "✅ Ты был разбанен.\nМожешь снова пользоваться ботом.\nПодписок после разбана не возвращается."
        )
    except Exception:
        pass

    await call.message.answer(
        f"✅ *Пользователь* `{user_id}` *разбанен.*\n\n"
        "⚠️ Подписки не восстановлены.\n"
        "После разбана у пользователя *нет никаких подписок*.",
        reply_markup=kb_admin_user_view(user_id, mode, page)
    )


@dp.callback_query(F.data.startswith("admin:give:"))
async def admin_give_subscription(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return

    await call.answer()

    parts = call.data.split(":")
    if len(parts) < 6:
        await call.message.answer("Ошибка выдачи подписки.")
        return

    try:
        user_id = int(parts[2])
        plan = parts[3]
        mode = parts[4]
        page = int(parts[5])
    except Exception:
        await call.message.answer("Ошибка выдачи подписки.")
        return

    if plan not in ("standard", "family"):
        await call.message.answer("Неизвестный тариф.")
        return

    user = db_get_user(user_id)
    if not user:
        await call.message.answer("Пользователь не найден.")
        return

    if user.get("is_banned"):
        await call.message.answer("Пользователь забанен. Сначала разбань его.", reply_markup=kb_admin_user_view(user_id, mode, page))
        return

    key = take_key(plan)
    if not key:
        await call.message.answer(
            "⚠️ Для этого тарифа нет ключей в базе.\nОткрой /admin → 🔑 Ключи → ➕ Добавить.",
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )
        return

    try:
        await send_key_to_user(user_id, plan, key)
    except TelegramForbiddenError:
        await call.message.answer(
            f"⚠️ Не смог отправить пользователю {user_id}. Пусть нажмёт /start.",
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )
        return
    except TelegramBadRequest as e:
        await call.message.answer(
            f"⚠️ TelegramBadRequest при выдаче: {e}",
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )
        return
    except Exception as e:
        await call.message.answer(
            f"⚠️ Ошибка при выдаче: {type(e).__name__}",
            reply_markup=kb_admin_user_view(user_id, mode, page)
        )
        return

    amount = plan_meta(plan)[3]
    order_id = db_create_order(user_id, user.get("username"), plan, amount)
    db_set_issued(order_id, key)
    db_set_status(order_id, "accepted")

    try:
        await refresh_reply_menu(user_id, user_id)
    except Exception:
        pass

    await call.message.answer(
        f"✅ Пользователю `{user_id}` выдана {md_escape(pretty_plan_name(plan))}.\n"
        f"🧾 Создан заказ `#{order_id}` со статусом `accepted`.",
        reply_markup=kb_admin_user_view(user_id, mode, page)
    )


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
            await bot.send_message(order["user_id"], "❌ Оплата отклонена. Создай новый заказ и попробуй ещё раз.")
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


@dp.message(AdminStates.user_search_wait)
async def admin_user_search_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if not txt:
        await m.answer("Пришли user_id, @username или имя.", reply_markup=kb_admin_menu())
        return

    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_menu())
        return

    data = await state.get_data()
    banned_only = bool(data.get("user_search_banned_only"))
    await send_admin_user_search_results(m, txt, page=0, banned_only=banned_only)
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
    await m.answer("✅ Цена успешно обновлена.", reply_markup=kb_admin_prices())


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


@dp.message(AdminStates.github_add_wait)
async def admin_github_add_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_github_menu())
        return

    data = await state.get_data()
    plan = data.get("github_plan")
    if plan not in ("standard", "family"):
        await state.clear()
        await m.answer("⚠️ Ошибка состояния. Открой раздел GitHub TXT заново.", reply_markup=kb_admin_github_menu())
        return

    try:
        lines, sha, _path = github_read_lines(plan)
        lines.append(txt)
        github_write_lines(plan, lines, sha, f"Add line to {github_plan_path(plan)}")
    except Exception as e:
        await m.answer(f"❌ Не удалось сохранить строку.\n`{md_escape(str(e))}`", reply_markup=kb_admin_github_menu())
        return

    await state.clear()
    await m.answer(
        f"✅ Новая строка добавлена в `{md_escape(github_plan_path(plan))}`",
        reply_markup=kb_admin_github_file(plan, lines, page=max(0, (len(lines) - 1) // 15))
    )


@dp.message(AdminStates.github_edit_wait)
async def admin_github_edit_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_github_menu())
        return

    data = await state.get_data()
    plan = data.get("github_plan")
    idx = int(data.get("github_index", -1))
    page = int(data.get("github_page", 0))
    old_line = (data.get("github_old_line") or "").strip()

    if plan not in ("standard", "family") or idx < 0:
        await state.clear()
        await m.answer("⚠️ Ошибка состояния. Открой раздел GitHub TXT заново.", reply_markup=kb_admin_github_menu())
        return

    try:
        lines, sha, _path = github_read_lines(plan)
        if idx >= len(lines):
            raise RuntimeError("Строка уже изменилась или пропала")

        old_name, _old_url = parse_named_vless_line(old_line or lines[idx])
        new_line = txt
        if txt.startswith("vless://") and old_name:
            new_line = f"{old_name}|{txt}"

        lines[idx] = new_line
        github_write_lines(plan, lines, sha, f"Update line {idx + 1} in {github_plan_path(plan)}")
    except Exception as e:
        await m.answer(f"❌ Не удалось обновить строку.\n`{md_escape(str(e))}`", reply_markup=kb_admin_github_menu())
        return

    await state.clear()
    await m.answer(
        f"✅ Строка *{idx + 1}* обновлена.",
        reply_markup=kb_admin_github_item(plan, idx, page)
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
    await m.answer(f"📢 Запускаю рассылку по *{len(user_ids)}* пользователям…")

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


# ================== ADMIN MESSAGE USER ==================
@dp.callback_query(F.data.startswith("msguser:"))
async def admin_write_user_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): 
        return await call.answer("Нет доступа", show_alert=True)
    
    await call.answer()
    user_id = int(call.data.split(":")[1])
    await state.update_data(target_user=user_id)
    await state.set_state(AdminStates.message_user_wait)
    
    await call.message.answer(
        f"✉️ Введите сообщение для отправки пользователю `{user_id}`:\n\n"
        "_Поддерживается текст, фото, видео и кружочки. Для отмены напишите_ `отмена`.",
        parse_mode="Markdown"
    )

@dp.message(AdminStates.message_user_wait)
async def admin_send_user_final(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    if message.text and message.text.lower() == "отмена":
        await state.clear()
        await message.answer("❌ Отправка сообщения отменена.", reply_markup=kb_admin_menu())
        return

    data = await state.get_data()
    uid = data.get("target_user")

    if not uid:
        await state.clear()
        await message.answer("❌ Ошибка: ID пользователя не найден.")
        return

    try:
        # Отправляем заголовок от админа
        await bot.send_message(
            chat_id=uid,
            text="🔔 *Сообщение от администрации SkyWhy VPN:*",
            parse_mode="Markdown"
        )
        # Копируем само сообщение (чтобы поддерживались фото и т.д.)
        await message.copy_to(uid)
        
        await message.answer(f"✅ Сообщение успешно отправлено пользователю `{uid}`!", reply_markup=kb_admin_menu())
    except TelegramForbiddenError:
        await message.answer(f"❌ Ошибка: Пользователь `{uid}` заблокировал бота.", reply_markup=kb_admin_menu())
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}", reply_markup=kb_admin_menu())
    finally:
        await state.clear()


# ================== MAIN ==================
print("VPN BOT STARTED OK")

async def main():
    global BOT_USERNAME

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set")
    if not yk_enabled():
        raise RuntimeError("YooKassa env vars are not set")

    db_init()
    import_keys_from_files_if_empty()

    me = await bot.get_me()
    BOT_USERNAME = me.username or ""

    runner, _site = await start_http_server()
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
