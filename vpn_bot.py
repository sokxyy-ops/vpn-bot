import asyncio
import os
import time
import sqlite3
from typing import Optional, List, Tuple, Dict, Any, Callable, Awaitable

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    FSInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import BaseMiddleware


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

# ================== KEY FILES (для первого импорта) ==================
STANDARD_KEYS_FILE = os.path.join(BASE_DIR, "standard_keys.txt")
FAMILY_KEYS_FILE = os.path.join(BASE_DIR, "family_keys.txt")

# ================== RESEND LIMITS ==================
RESEND_COOLDOWN_SEC = 10 * 60   # 10 минут
RESEND_MAX = 3                 # максимум 3 пересылки на заказ


# ================== BOT ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(storage=MemoryStorage())


# ================== FSM ==================
class AdminStates(StatesGroup):
    broadcast_wait = State()
    price_wait = State()   # ждём число
    keys_wait = State()    # ждём список ключей
    search_wait = State()  # ждём запрос


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

    # orders
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL,         -- waiting_receipt / pending_admin / accepted / rejected / cancelled
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    con.commit()

    # migrations
    _add_column_if_missing(con, "orders", "payment_msg_id", "ALTER TABLE orders ADD COLUMN payment_msg_id INTEGER")
    _add_column_if_missing(con, "orders", "issued_key", "ALTER TABLE orders ADD COLUMN issued_key TEXT")
    _add_column_if_missing(con, "orders", "accepted_at", "ALTER TABLE orders ADD COLUMN accepted_at INTEGER")
    _add_column_if_missing(con, "orders", "admin_msg_id", "ALTER TABLE orders ADD COLUMN admin_msg_id INTEGER")
    _add_column_if_missing(con, "orders", "resend_count", "ALTER TABLE orders ADD COLUMN resend_count INTEGER DEFAULT 0")
    _add_column_if_missing(con, "orders", "last_resend_at", "ALTER TABLE orders ADD COLUMN last_resend_at INTEGER DEFAULT 0")

    # users
    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_seen INTEGER NOT NULL,
            is_blocked INTEGER DEFAULT 0
        )
    """)

    # settings
    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    _settings_set_if_missing(con, "price_standard", "200")
    _settings_set_if_missing(con, "price_family", "310")

    # keys storage
    _ensure_table(con, """
        CREATE TABLE IF NOT EXISTS keys_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan TEXT NOT NULL,          -- standard/family
            key TEXT NOT NULL,
            used INTEGER DEFAULT 0,
            used_at INTEGER,
            order_id INTEGER
        )
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_keys_unique ON keys_store(plan, key)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_keys_used ON keys_store(plan, used)")
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
            INSERT INTO users(user_id, username, first_name, last_seen, is_blocked)
            VALUES(?,?,?,?,0)
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

def db_list_users_for_broadcast() -> List[int]:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT user_id FROM users WHERE COALESCE(is_blocked,0)=0")
        return [r[0] for r in cur.fetchall()]
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
        "id": row[0], "plan": row[1], "amount": row[2], "status": row[3],
        "payment_msg_id": row[4], "admin_msg_id": row[5],
        "resend_count": row[6] or 0, "last_resend_at": row[7] or 0
    }

def db_create_order(user_id: int, username: Optional[str], plan: str, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders(user_id, username, plan, amount, status, created_at,
                           payment_msg_id, issued_key, accepted_at, admin_msg_id,
                           resend_count, last_resend_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    """, (user_id, username or "", plan, amount, "waiting_receipt", int(time.time()),
          None, None, None, None, 0, 0))
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
        "id": row[0], "user_id": row[1], "username": row[2], "plan": row[3],
        "amount": row[4], "status": row[5], "payment_msg_id": row[6],
        "issued_key": row[7], "accepted_at": row[8], "admin_msg_id": row[9],
        "resend_count": row[10] or 0, "last_resend_at": row[11] or 0,
        "created_at": row[12],
    }

def db_get_last_accepted(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, issued_key, accepted_at
        FROM orders
        WHERE user_id=? AND status='accepted'
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "plan": row[1], "amount": row[2], "issued_key": row[3], "accepted_at": row[4]}

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

def db_profit_totals() -> Dict[str, int]:
    now = int(time.time())
    day_ago = now - 24 * 3600
    week_ago = now - 7 * 24 * 3600
    month_ago = now - 30 * 24 * 3600

    con = db()
    try:
        cur = con.cursor()

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted'")
        total = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted' AND accepted_at>=?", (day_ago,))
        day = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted' AND accepted_at>=?", (week_ago,))
        week = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='accepted' AND accepted_at>=?", (month_ago,))
        month = int(cur.fetchone()[0] or 0)

        return {"total": total, "day": day, "week": week, "month": month}
    finally:
        con.close()

def db_search_orders(query: str, limit: int = 10) -> List[Tuple]:
    q = (query or "").strip()
    con = db()
    try:
        cur = con.cursor()

        # order_id или user_id
        if q.isdigit():
            num = int(q)

            # пробуем как order_id
            cur.execute("""
                SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
                FROM orders
                WHERE id=?
                LIMIT 1
            """, (num,))
            r = cur.fetchall()
            if r:
                return r

            # иначе как user_id
            cur.execute("""
                SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
                FROM orders
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
            """, (num, limit))
            return cur.fetchall()

        if q.startswith("@"):
            q = q[1:]

        # точный username
        cur.execute("""
            SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
            FROM orders
            WHERE LOWER(username)=LOWER(?)
            ORDER BY id DESC
            LIMIT ?
        """, (q, limit))
        rows = cur.fetchall()
        if rows:
            return rows

        # частичный username
        cur.execute("""
            SELECT id, user_id, username, plan, amount, status, created_at, accepted_at
            FROM orders
            WHERE LOWER(username) LIKE LOWER(?)
            ORDER BY id DESC
            LIMIT ?
        """, (f"%{q}%", limit))
        return cur.fetchall()
    finally:
        con.close()


# ================== KEYS (DB) ==================
def db_keys_count(plan: str) -> int:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM keys_store WHERE plan=? AND COALESCE(used,0)=0", (plan,))
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
            cur.execute("INSERT OR IGNORE INTO keys_store(plan, key, used, used_at, order_id) VALUES(?,?,0,NULL,NULL)", (plan, k))
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

def take_key(plan: str, order_id: int) -> Optional[str]:
    con = db()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, key FROM keys_store WHERE plan=? AND COALESCE(used,0)=0 ORDER BY id ASC LIMIT 1", (plan,))
        row = cur.fetchone()
        if not row:
            return None
        kid, key = row[0], row[1]
        cur.execute("UPDATE keys_store SET used=1, used_at=?, order_id=? WHERE id=?", (int(time.time()), order_id, kid))
        con.commit()
        return key
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

def text_subscription_card(from_user, sub: Optional[dict]):
    name = (from_user.first_name or "—").strip()
    uid = from_user.id

    if not sub or not sub.get("issued_key"):
        return (
            "👤 *Профиль:*\n"
            f"> Имя: {name}\n"
            f"> ID: {uid}\n\n"
            "🔗 *Подписка:*\n"
            "> Нет активной подписки\n\n"
            "Нажми *Купить подписку* 👇"
        )

    plan_name, conditions, device_limit, _amount = plan_meta(sub["plan"])
    key = sub["issued_key"]
    return (
        "👤 *Профиль:*\n"
        f"> Имя: {name}\n"
        f"> ID: {uid}\n\n"
        "🔗 *Ваш ключ:*\n"
        f"> `{key}`\n\n"
        "📄 *Информация о тарифе:*\n"
        f"> Тариф: {plan_name} • ♾ Навсегда\n"
        f"> {conditions}\n"
        f"> Лимит устройств: {device_limit}\n\n"
        "👇 Используй кнопки ниже"
    )

def fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return time.strftime("%d.%m.%Y %H:%M", time.localtime(int(ts)))
    except Exception:
        return "—"


# ================== KEYBOARDS ==================
def kb_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Меню"), KeyboardButton(text="🧾 Моя подписка")]],
        resize_keyboard=True
    )

def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")],
        [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="menu:sub")],
        [InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL)],
    ])

def kb_buy():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟩 Стандарт — {std_price}₽ (1 пользователь • до 3 устройств)", callback_data="buy:standard")],
        [InlineKeyboardButton(text=f"🟦 Семейная — {fam_price}₽ (до 8 пользователей • до 3 устройств)", callback_data="buy:family")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])

def kb_payment(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{order_id}")],
        [InlineKeyboardButton(text="🔁 Переслать админу", callback_data=f"resend:{order_id}")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])

def kb_admin_decision(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:ok:{order_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}")]
    ])

def kb_after_issue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Happ (Android)", url=HAPP_ANDROID_URL)],
        [InlineKeyboardButton(text="🍎 Happ (iOS)", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Happ (Windows)", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])

def kb_sub_no_sub():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])

def kb_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Заказы", callback_data="admin:list"),
         InlineKeyboardButton(text="🔎 Поиск", callback_data="admin:search")],
        [InlineKeyboardButton(text="💰 Прибыль", callback_data="admin:profit"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🏷 Цены", callback_data="admin:prices"),
         InlineKeyboardButton(text="🔑 Ключи", callback_data="admin:keys")],
    ])

def kb_admin_list(rows):
    keyboard = []
    for oid, uid, uname, plan, amount, created_at in rows[:20]:
        u = f"@{uname}" if uname else str(uid)
        keyboard.append([InlineKeyboardButton(
            text=f"🧾 #{oid} • {plan} • {amount}₽ • {u}",
            callback_data=f"admin:view:{oid}"
        )])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:list"),
                     InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")])
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
        [InlineKeyboardButton(text=f"➕ Добавить 🟩 (осталось {s})", callback_data="admin:keys:add:standard")],
        [InlineKeyboardButton(text=f"➕ Добавить 🟦 (осталось {f})", callback_data="admin:keys:add:family")],
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


# ================== MIDDLEWARE (трек пользователей БЕЗ ломания /start) ==================
class TrackUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message) and event.from_user:
                db_upsert_user(event.from_user.id, event.from_user.username, event.from_user.first_name, int(time.time()))
            elif isinstance(event, CallbackQuery) and event.from_user:
                db_upsert_user(event.from_user.id, event.from_user.username, event.from_user.first_name, int(time.time()))
        except Exception:
            pass
        return await handler(event, data)

dp.message.middleware(TrackUserMiddleware())
dp.callback_query.middleware(TrackUserMiddleware())


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
    safe_username = username or "—"
    msg = await bot.send_message(
        ADMIN_ID,
        "🔔 *Чек на проверку*\n\n"
        f"🧾 Заказ: *#{order_id}*\n"
        f"👤 Пользователь: `{user_id}` (@{safe_username})\n"
        f"📦 Тариф: *{plan}*\n"
        f"💰 Сумма: *{amount}₽*\n\n"
        "Принять оплату?",
        reply_markup=kb_admin_decision(order_id),
        parse_mode="Markdown",
    )
    db_set_admin_msg(order_id, msg.message_id)
    return msg


# ================== START / MENU ==================
@dp.message(CommandStart())
async def start(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())
    try:
        await bot.send_message(m.chat.id, " ", reply_markup=kb_reply_menu())
    except Exception:
        pass

@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())

@dp.message(F.text == "📋 Меню")
async def menu_btn(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())

@dp.message(F.text == "🧾 Моя подписка")
async def mysub_btn(m: Message):
    sub = db_get_last_accepted(m.from_user.id)
    if not sub:
        await m.answer(text_subscription_card(m.from_user, None), reply_markup=kb_sub_no_sub())
        return
    await m.answer(text_subscription_card(m.from_user, sub), reply_markup=kb_after_issue())


# ================== ADMIN COMMAND ==================
@dp.message(Command("admin"))
async def admin_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("🛠 *Админ-панель*\nВыбери раздел 👇", reply_markup=kb_admin_menu())


# ================== CALLBACK: MENU ==================
@dp.callback_query(F.data.startswith("menu:"))
async def menu_router(call: CallbackQuery):
    try:
        action = call.data.split(":", 1)[1]
        if action == "main":
            await send_banner_or_text(call.message.chat.id, text_menu(), reply_markup=kb_main())
            return
        if action == "buy":
            await call.message.answer(text_buy_intro(), reply_markup=kb_buy())
            return
        if action == "sub":
            sub = db_get_last_accepted(call.from_user.id)
            if not sub:
                await call.message.answer(text_subscription_card(call.from_user, None), reply_markup=kb_sub_no_sub())
                return
            await call.message.answer(text_subscription_card(call.from_user, sub), reply_markup=kb_after_issue())
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
        username = call.from_user.username

        active = db_get_active_order(user_id)
        if active:
            await call.message.answer(
                f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n"
                "Если админ не отвечает — можно *❌ Отменить заказ* или *🔁 Переслать админу* (ограничено)."
            )
            return

        plan = call.data.split(":", 1)[1]
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

        await bot.send_message(user_id, "✅ Заказ отменён. Можешь оформить новый через меню.")
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

        await call.answer("✅ Переслал админу", show_alert=True)
    finally:
        try:
            await call.answer()
        except Exception:
            pass


# ================== RECEIPT ==================
@dp.message(F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    # Важно: /start и /admin обработаются выше, потому что они Command handlers
    user_id = m.from_user.id
    username = m.from_user.username

    active = db_get_active_order(user_id)
    if not active:
        return  # просто молча, чтобы не мешать обычным сообщениям

    if active["status"] == "pending_admin":
        await m.answer(
            "⏳ Чек уже был отправлен админу.\n"
            "Если админ не отвечает — можно *❌ Отменить заказ* или *🔁 Переслать админу* (ограничено).",
            reply_markup=kb_payment(active["id"])
        )
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

    await call.message.answer(
        "🧾 *Заказ для решения*\n\n"
        f"🧾 Заказ: *#{order['id']}*\n"
        f"👤 User: `{order['user_id']}` (@{order['username'] or '—'})\n"
        f"📦 План: *{order['plan']}*\n"
        f"💰 Сумма: *{order['amount']}₽*\n"
        f"📌 Статус: *{order['status']}*\n"
        f"🕒 Создан: {fmt_ts(order['created_at'])}\n\n"
        "Выбери действие:",
        reply_markup=kb_admin_decision(order_id)
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
        f"🏦 Всего: *{p['total']}₽*",
        reply_markup=kb_admin_menu()
    )
    await call.answer()

@dp.callback_query(F.data == "admin:search")
async def admin_search(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminStates.search_wait)
    await call.message.answer(
        "🔎 *Поиск заказа*\n\n"
        "Отправь сюда:\n"
        "• номер заказа (например `105`)\n"
        "• или user_id (например `123456789`)\n"
        "• или username (например `@sokxyy`)\n\n"
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

    if order["status"] in ("accepted", "rejected", "cancelled"):
        await call.answer("Уже решено", show_alert=True)
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
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
            await bot.send_message(ADMIN_ID, f"⚠️ Не смог отправить пользователю {order['user_id']}. Пусть нажмёт /start.", parse_mode=None)
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

        await call.answer("Выдано ✅")


# ================== FSM INPUTS (АДМИН) ==================
@dp.message(AdminStates.search_wait)
async def admin_search_input(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        await state.clear()
        return

    txt = (m.text or "").strip()
    if txt.lower() == "отмена":
        await state.clear()
        await m.answer("❌ Отменено.", reply_markup=kb_admin_menu())
        return

    rows = db_search_orders(txt, limit=10)
    if not rows:
        await m.answer("Ничего не найдено. Попробуй другой запрос.", reply_markup=kb_admin_menu())
        return

    out = ["🔎 *Результаты поиска:*"]
    for (oid, uid, uname, plan, amount, status, created_at, accepted_at) in rows:
        u = f"@{uname}" if uname else str(uid)
        out.append(
            f"\n🧾 *#{oid}* • {plan} • *{amount}₽*\n"
            f"👤 {u} (`{uid}`)\n"
            f"📌 {status}\n"
            f"🕒 {fmt_ts(created_at)}"
            + (f"\n✅ {fmt_ts(accepted_at)}" if accepted_at else "")
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
    if price < 1 or price > 1000000:
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
    left = db_keys_count(plan)

    await state.clear()
    await m.answer(
        f"✅ Ключи добавлены ({title})\n\n"
        f"➕ Добавлено: *{added}*\n"
        f"⏭ Пропущено (дубли): *{skipped}*\n"
        f"📦 Осталось свободных: *{left}*",
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
