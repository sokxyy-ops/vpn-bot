import asyncio
import os
import time
import sqlite3
from typing import Optional

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

# ================== KEY FILES ==================
STANDARD_KEYS_FILE = os.path.join(BASE_DIR, "standard_keys.txt")
FAMILY_KEYS_FILE = os.path.join(BASE_DIR, "family_keys.txt")

# ================== RESEND LIMITS ==================
RESEND_COOLDOWN_SEC = 10 * 60   # 10 минут
RESEND_MAX = 3                 # максимум 3 пересылки на заказ

# ================== BOT ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

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
            status TEXT NOT NULL,         -- waiting_receipt / pending_admin / accepted / rejected / cancelled
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    con.commit()

    # миграции
    _add_column_if_missing(con, "orders", "payment_msg_id", "ALTER TABLE orders ADD COLUMN payment_msg_id INTEGER")
    _add_column_if_missing(con, "orders", "issued_key", "ALTER TABLE orders ADD COLUMN issued_key TEXT")
    _add_column_if_missing(con, "orders", "accepted_at", "ALTER TABLE orders ADD COLUMN accepted_at INTEGER")
    _add_column_if_missing(con, "orders", "admin_msg_id", "ALTER TABLE orders ADD COLUMN admin_msg_id INTEGER")

    # антиспам пересылки
    _add_column_if_missing(con, "orders", "resend_count", "ALTER TABLE orders ADD COLUMN resend_count INTEGER DEFAULT 0")
    _add_column_if_missing(con, "orders", "last_resend_at", "ALTER TABLE orders ADD COLUMN last_resend_at INTEGER DEFAULT 0")

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
               resend_count, last_resend_at
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
    """
    returns: (ok: bool, reason: str)
    """
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

# ================== PLANS ==================
def plan_meta(plan: str):
    if plan == "standard":
        return "🟩 Стандарт", "👤 1 пользователь • 📱 до 3 устройств", "3", 200
    return "🟦 Семейная", "👥 до 8 пользователей • 📱 до 3 устройств каждому", "3", 310

# ================== KEYS ==================
def take_key(plan: str) -> Optional[str]:
    filename = STANDARD_KEYS_FILE if plan == "standard" else FAMILY_KEYS_FILE
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = [x.strip() for x in f.read().splitlines() if x.strip()]
    if not lines:
        return None
    return lines[0]  # НЕ удаляем

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
    return (
        "🛒 *Покупка подписки*\n\n"
        "🟩 *Стандарт* — 1 пользователь • до 3 устройств\n"
        "🟦 *Семейная* — до 8 пользователей • до 3 устройств каждому\n\n"
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

    # ✅ ключ в цитате и моноширный (Markdown `...`)
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟩 Стандарт — 200₽ (1 пользователь • до 3 устройств)", callback_data="buy:standard")],
        [InlineKeyboardButton(text="🟦 Семейная — 310₽ (до 8 пользователей • до 3 устройств)", callback_data="buy:family")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])

def kb_payment(order_id: int):
    # ✅ resend есть, но ограничен кулдауном/лимитом (антиспам в обработчике)
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
    # ✅ убрали "Скопировать ключ"
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

# админка
def kb_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Заказы на проверке", callback_data="admin:list")],
    ])

def kb_admin_list(rows):
    keyboard = []
    for oid, uid, uname, plan, amount, created_at in rows[:20]:
        u = f"@{uname}" if uname else str(uid)
        keyboard.append([InlineKeyboardButton(
            text=f"🧾 #{oid} • {plan} • {amount}₽ • {u}",
            callback_data=f"admin:view:{oid}"
        )])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:list")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ================== BANNER SEND ==================
async def send_banner_or_text(chat_id: int, text: str, reply_markup=None):
    try:
        if os.path.exists(BANNER_PATH):
            await bot.send_photo(chat_id, FSInputFile(BANNER_PATH), caption=text, reply_markup=reply_markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)

# ================== HELPERS ==================
async def send_check_to_admin(order_id: int, user_id: int, username: Optional[str], plan: str, amount: int):
    safe_username = username or "—"
    msg = await bot.send_message(
        ADMIN_ID,
        "🔔 Чек на проверку\n\n"
        f"🧾 Заказ: #{order_id}\n"
        f"👤 Пользователь: {user_id} (@{safe_username})\n"
        f"📦 Тариф: {plan}\n"
        f"💰 Сумма: {amount}₽\n\n"
        "Принять оплату?",
        reply_markup=kb_admin_decision(order_id),
        parse_mode=None,
    )
    db_set_admin_msg(order_id, msg.message_id)
    return msg

# ================== START / MENU ==================
@dp.message(CommandStart())
async def start(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())
    # нижнее меню без текста
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
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer("🛠 Админ-панель", reply_markup=kb_admin_menu())

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

        # удаляем сообщение с оплатой если можем
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

        # помечаем попытку
        db_mark_resend(order_id)

        # если был waiting_receipt — ставим pending_admin
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
    user_id = m.from_user.id
    username = m.from_user.username

    active = db_get_active_order(user_id)
    if not active:
        await m.answer("⚠️ Нет активного заказа. Открой /start и выбери тариф.")
        return

    if active["status"] == "pending_admin":
        await m.answer(
            "⏳ Чек уже был отправлен админу.\n"
            "Если админ не отвечает — можно *❌ Отменить заказ* или *🔁 Переслать админу* (ограничено).",
            reply_markup=kb_payment(active["id"])
        )
        return

    # waiting_receipt -> отправляем админу
    try:
        await send_check_to_admin(active["id"], user_id, username, active["plan"], active["amount"])
    except Exception as e:
        print("ADMIN SEND ERROR:", repr(e))
        await m.answer("⚠️ Не смог отправить админу. Попробуй ещё раз через минуту.")
        return

    db_set_status(active["id"], "pending_admin")

    # копия чека админу (не критично)
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

# ================== ADMIN PANEL CALLBACKS ==================
@dp.callback_query(F.data == "admin:list")
async def admin_list(call: CallbackQuery):
    try:
        if call.from_user.id != ADMIN_ID:
            await call.answer("Нет доступа", show_alert=True)
            return
        rows = db_list_pending(limit=20)
        if not rows:
            await call.message.answer("✅ Нет заказов на проверке.")
            return
        await call.message.answer("📦 Заказы на проверке:", reply_markup=kb_admin_list(rows))
    finally:
        try:
            await call.answer()
        except Exception:
            pass

@dp.callback_query(F.data.startswith("admin:view:"))
async def admin_view(call: CallbackQuery):
    try:
        if call.from_user.id != ADMIN_ID:
            await call.answer("Нет доступа", show_alert=True)
            return

        order_id = int(call.data.split(":")[-1])
        order = db_get_order(order_id)
        if not order:
            await call.answer("Заказ не найден", show_alert=True)
            return

        await call.message.answer(
            "🧾 Заказ для решения\n\n"
            f"Заказ: #{order['id']}\n"
            f"User: {order['user_id']} (@{order['username'] or '—'})\n"
            f"План: {order['plan']}\n"
            f"Сумма: {order['amount']}₽\n"
            f"Статус: {order['status']}\n\n"
            "Выбери действие:",
            reply_markup=kb_admin_decision(order_id)
        )
    finally:
        try:
            await call.answer()
        except Exception:
            pass

@dp.callback_query(F.data.startswith("admin:"))
async def admin_decision(call: CallbackQuery):
    try:
        if call.from_user.id != ADMIN_ID:
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
            key = take_key(order["plan"])
            if not key:
                await call.answer("Ключей нет", show_alert=True)
                await bot.send_message(ADMIN_ID, "⚠️ В файлах ключей пусто. Заполни standard_keys.txt / family_keys.txt.", parse_mode=None)
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
            return
    finally:
        try:
            await call.answer()
        except Exception:
            pass

# ================== MAIN ==================
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set")

    db_init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


