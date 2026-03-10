import asyncio
import os
import time
import sqlite3
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "orders.sqlite")

# ================== LINKS ==================
AGREEMENT_URL = "https://telegra.ph/Soglashenie-03-10-3"

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

# ================== BOT ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(storage=MemoryStorage())

# ================== DB ==================
def db():
    return sqlite3.connect(DB_PATH)


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
    con.commit()
    con.close()


def db_create_order(user_id: int, username: Optional[str], plan: str, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders(user_id, username, plan, amount, status, created_at)
        VALUES(?,?,?,?,?,?)
    """, (user_id, username or "", plan, amount, "waiting_receipt", int(time.time())))
    con.commit()
    order_id = cur.lastrowid
    con.close()
    return order_id


def db_get_active_order(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, status, created_at
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
        "created_at": row[4],
    }


def db_get_last_paid_sub(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, status, created_at
        FROM orders
        WHERE user_id=?
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
        "created_at": row[4],
    }


def plan_meta(plan: str):
    price_standard = 200
    price_family = 310

    if plan == "standard":
        return "🟩 Стандарт", "👤 1 пользователь • 📱 до 3 устройств", "3", price_standard

    return "🟦 Семейная", "👥 до 8 пользователей • 📱 до 3 устройств каждому", "3", price_family


# ================== KEYBOARDS ==================
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")],
        [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="menu:sub")],
    ])


def kb_buy():
    std_price = plan_meta("standard")[3]
    fam_price = plan_meta("family")[3]

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🟩 Стандарт — {std_price}₽", callback_data="buy:standard")],
        [InlineKeyboardButton(text=f"🟦 Семейная — {fam_price}₽", callback_data="buy:family")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])


def kb_agreement(plan: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Открыть соглашение", url=AGREEMENT_URL)],
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"agree:{plan}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy")],
    ])


def kb_after_order():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])


# ================== TEXT ==================
def text_main():
    return (
        "Добро пожаловать!\n\n"
        "Выберите действие ниже."
    )


def text_subscription(sub) -> str:
    if not sub:
        return "У тебя пока нет заказов."

    plan_name, conditions, _device_limit, amount = plan_meta(sub["plan"])
    return (
        "🧾 *Твоя подписка / заказ*\n\n"
        f"🆔 Заказ: *#{sub['id']}*\n"
        f"📦 Тариф: *{plan_name}*\n"
        f"{conditions}\n"
        f"💰 Сумма: *{amount}₽*\n"
        f"📌 Статус: *{sub['status']}*"
    )


# ================== START ==================
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(text_main(), reply_markup=kb_main())


# ================== MENU ==================
@dp.callback_query(F.data == "menu:main")
async def menu_main(call: CallbackQuery):
    await call.message.answer(text_main(), reply_markup=kb_main())
    await call.answer()


@dp.callback_query(F.data == "menu:buy")
async def menu_buy(call: CallbackQuery):
    await call.message.answer("🛒 *Выбери тариф:*", reply_markup=kb_buy())
    await call.answer()


@dp.callback_query(F.data == "menu:sub")
async def menu_sub(call: CallbackQuery):
    sub = db_get_last_paid_sub(call.from_user.id)
    await call.message.answer(text_subscription(sub), reply_markup=kb_main())
    await call.answer()


# ================== BUY FLOW ==================
@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    user_id = call.from_user.id
    active = db_get_active_order(user_id)

    if active:
        await call.message.answer(
            f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n\n"
            "Сначала заверши его или дождись проверки."
        )
        await call.answer()
        return

    plan = call.data.split(":")[1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка тарифа", show_alert=True)
        return

    plan_name, conditions, _device_limit, amount = plan_meta(plan)

    await call.message.answer(
        f"📄 *Перед покупкой ознакомься с соглашением.*\n\n"
        f"📦 Тариф: *{plan_name}*\n"
        f"{conditions}\n"
        f"💰 Сумма: *{amount}₽*\n\n"
        "1. Нажми кнопку *Открыть соглашение*\n"
        "2. Ознакомься с условиями\n"
        "3. Нажми *Принять*\n\n"
        reply_markup=kb_agreement(plan)
    )
    await call.answer()


@dp.callback_query(F.data.startswith("agree:"))
async def agree_and_create_order(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username
    plan = call.data.split(":")[1]

    active = db_get_active_order(user_id)
    if active:
        await call.message.answer(
            f"⏳ У тебя уже есть активный заказ *#{active['id']}*."
        )
        await call.answer()
        return

    if plan not in ("standard", "family"):
        await call.answer("Ошибка тарифа", show_alert=True)
        return

    plan_name, conditions, _device_limit, amount = plan_meta(plan)
    order_id = db_create_order(user_id, username, plan, amount)

    await call.message.answer(
        f"🧾 *Заказ #{order_id}*\n\n"
        f"📦 Тариф: *{plan_name}*\n"
        f"{conditions}\n"
        f"💰 Сумма: *{amount}₽*\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст).",
        reply_markup=kb_after_order()
    )
    await call.answer("Условия приняты ✅", show_alert=True)


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
