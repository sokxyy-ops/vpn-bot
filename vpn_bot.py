import asyncio
import os
import time
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties

# ====== ENV ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ====== LINKS ======
TG_CHANNEL = "https://t.me/sokxyybc"
ADMIN_USERNAME = "whyshawello"

PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"
REVIEW_LINK = "https://t.me/sokxyybc/23"

PAYMENT_TEXT = (
    "💳 *Реквизиты для оплаты*\n\n"
    "Карта: `2204320913014587`\n"
    "Если комиссия — Ozon: `+79951253391`\n\n"
    "📎 После оплаты отправь чек."
)

# ====== DB (заказы) ======
DB_PATH = "orders.sqlite"

def db():
    return sqlite3.connect(DB_PATH)

def db_init():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            plan TEXT,
            amount INTEGER,
            status TEXT
        )
    """)
    con.commit()
    con.close()

def create_order(order_id, user_id, plan, amount):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO orders VALUES(?,?,?,?,?)",
        (order_id, user_id, plan, amount, "wait_receipt")
    )
    con.commit()
    con.close()

def get_active_order(user_id):
    con = db()
    cur = con.cursor()
    cur.execute(
        "SELECT order_id, plan, amount, status FROM orders "
        "WHERE user_id=? AND status IN ('wait_receipt','pending_admin') "
        "ORDER BY order_id DESC LIMIT 1",
        (user_id,)
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "order_id": row[0],
        "plan": row[1],
        "amount": row[2],
        "status": row[3]
    }

def get_order(order_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT order_id, user_id, plan, amount, status FROM orders WHERE order_id=?", (order_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {
        "order_id": row[0],
        "user_id": row[1],
        "plan": row[2],
        "amount": row[3],
        "status": row[4]
    }

def set_status(order_id, status):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET status=? WHERE order_id=?", (status, order_id))
    con.commit()
    con.close()

# ====== КЛЮЧИ ======
def take_key(plan):
    filename = "standard_keys.txt" if plan == "standard" else "family_keys.txt"
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = [x.strip() for x in f.readlines() if x.strip()]
    return lines[0] if lines else None  # не удаляем

# ====== КЛАВИАТУРЫ ======
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟩 Стандарт — 200₽", callback_data="plan:standard")],
        [InlineKeyboardButton(text="🟦 Семейная — 300₽", callback_data="plan:family")],
        [InlineKeyboardButton(text="📣 TG канал", url=TG_CHANNEL)],
    ])

def kb_plan(plan):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Получить реквизиты", callback_data=f"pay:{plan}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

def kb_admin(order_id, plan, user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:ok:{order_id}:{plan}:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}:{plan}:{user_id}")
        ]
    ])

# 🔥 ЧИСТЫЙ HAPP (без vleska)
def kb_after_key(subscription):
    connect_url = f"happ://add/{subscription}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться (Happ)", url=connect_url)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
    ])

# ====== БОТ ======
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Выбери тариф:", reply_markup=kb_main())

@dp.callback_query(F.data.startswith("plan:"))
async def plan_info(call: CallbackQuery):
    plan = call.data.split(":")[1]
    await call.message.answer(
        f"Тариф: *{plan}*\n\n{PAYMENT_TEXT}",
        reply_markup=kb_plan(plan)
    )
    await call.answer()

@dp.callback_query(F.data.startswith("pay:"))
async def pay(call: CallbackQuery):
    user_id = call.from_user.id
    plan = call.data.split(":")[1]
    amount = 200 if plan == "standard" else 300

    active = get_active_order(user_id)
    if active:
        await call.message.answer("У тебя уже есть активный заказ.")
        await call.answer()
        return

    order_id = int(time.time() * 1000)
    create_order(order_id, user_id, plan, amount)

    await call.message.answer(
        f"🧾 Заказ #{order_id}\nСумма: {amount}₽\n\nОтправь чек."
    )
    await call.answer()

@dp.message(F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    user_id = m.from_user.id
    active = get_active_order(user_id)

    order_id = active["order_id"] if active else "UNKNOWN"
    plan = active["plan"] if active else "UNKNOWN"

    if active:
        set_status(order_id, "pending_admin")

    await bot.send_message(
        ADMIN_ID,
        f"Новый чек\nЗаказ: {order_id}\nПользователь: {user_id}",
        reply_markup=kb_admin(order_id, plan, user_id) if active else None
    )

    try:
        await m.copy_to(ADMIN_ID)
    except:
        pass

    await m.answer("Чек отправлен админу.")

@dp.callback_query(F.data.startswith("admin:"))
async def admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    _, action, order_id, plan, user_id = call.data.split(":")
    order_id = int(order_id)
    user_id = int(user_id)

    if action == "ok":
        key = take_key(plan)
        if not key:
            await call.answer("Нет ключей", show_alert=True)
            return

        set_status(order_id, "accepted")

        await bot.send_message(
            user_id,
            f"✅ Оплата подтверждена!\n\n`{key}`",
            reply_markup=kb_after_key(key)
        )

        await call.answer("Выдано")

    else:
        set_status(order_id, "rejected")
        await bot.send_message(user_id, "❌ Оплата отклонена.")
        await call.answer("Отклонено")

async def main():
    db_init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
