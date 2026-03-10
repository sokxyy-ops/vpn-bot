import asyncio
import os
import time
import sqlite3
from typing import Optional, List, Dict, Callable, Awaitable
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
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
bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ================== DB ==================
def db():
    return sqlite3.connect(DB_PATH)

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

def plan_meta(plan: str):
    price_standard = 200
    price_family = 310
    if plan == "standard":
        return "🟩 Стандарт", "1 пользователь • до 3 устройств", "3", price_standard
    return "🟦 Семейная", "до 8 пользователей • до 3 устройств каждому", "3", price_family

# ================== KEYBOARDS ==================
def kb_agreement(plan: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Соглашение", url=AGREEMENT_URL)],
        [InlineKeyboardButton(text="✅ Согласиться", callback_data=f"agree:{plan}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy")],
    ])

def kb_main(user_id: int):
    rows = [
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy:standard")],
        [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="menu:sub")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ================== CALLBACKS ==================
@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    user_id = call.from_user.id
    active = db_get_active_order(user_id)

    if active:
        await call.message.answer(f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n*❌ Отменить заказ* или *🔁 Переслать админу*.")
        return

    plan = call.data.split(":")[1]
    if plan not in ("standard", "family"):
        await call.answer("Ошибка тарифа", show_alert=True)
        return

    plan_name, conditions, _device_limit, amount = plan_meta(plan)
    await call.message.answer(
        f"📄 *Перед покупкой ознакомься с соглашением.*\n\n📦 Тариф: *{plan_name}*\n{conditions}\n💰 Сумма: *{amount}₽*\n\n"
        "Нажимая *«Согласиться»*, ты подтверждаешь принятие условий соглашения.\n*Возврат средств после активации подписки не производится.*",
        reply_markup=kb_agreement(plan)
    )

@dp.callback_query(F.data.startswith("agree:"))
async def agree_and_create_order(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username
    plan = call.data.split(":")[1]

    if not db_get_active_order(user_id):
        plan_name, conditions, _device_limit, amount = plan_meta(plan)
        order_id = db_create_order(user_id, username, plan, amount)

        msg = await call.message.answer(
            f"🧾 *Заказ #{order_id}*\n\n📦 Тариф: *{plan_name}*\n{conditions}\n💰 Сумма: *{amount}₽*\n\n{PAYMENT_TEXT}\n\n"
            "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст)."
        )
        await call.answer()

# ================== START ==================
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer("Добро пожаловать! Выберите действие:", reply_markup=kb_main(m.from_user.id))

# ================== MAIN ==================
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
