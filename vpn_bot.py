import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANNER_PATH = os.path.join(BASE_DIR, "banner.jpg")

DB_PATH = "orders.sqlite"

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

# ================= DATABASE =================

def db():
    return sqlite3.connect(DB_PATH)

def db_init():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        issued_key TEXT,
        status TEXT
    )
    """)

    con.commit()
    con.close()

def db_get_last_accepted(user_id):
    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT plan, issued_key
    FROM orders
    WHERE user_id=? AND status='accepted'
    ORDER BY id DESC LIMIT 1
    """, (user_id,))

    row = cur.fetchone()
    con.close()

    if not row:
        return None

    return {
        "plan": row[0],
        "issued_key": row[1]
    }

# ================= PLANS =================

def plan_meta(plan):
    if plan == "standard":
        return "🟩 Стандарт", "1 пользователь • до 3 устройств", "3", 200

    return "🟦 Семейная", "до 8 пользователей • до 3 устройств каждому", "24", 300


# ================= KEYBOARDS =================

def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="mysub")],
        [InlineKeyboardButton(text="📣 Канал", url="https://t.me/sokxyybc")]
    ])

def kb_copy_key():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ключ", callback_data="copy_key")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")]
    ])

def kb_reply():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Меню"), KeyboardButton(text="🧾 Моя подписка")]
        ],
        resize_keyboard=True
    )

# ================= TEXT =================

def text_menu():
    return (
        "⚡ *Sokxyy Обход — VPN*\n\n"
        "🛡 Обычный VPN + режим обхода блокировок\n"
        "♾ Доступ навсегда\n"
        "🔑 Выдача ключа для Happ после оплаты\n\n"
        "👇 Выбери действие ниже"
    )


def text_subscription_card(user, sub):

    name = user.from_user.first_name
    uid = user.from_user.id

    if not sub:
        return (
            "👤 *Профиль:*\n"
            f"> Имя: {name}\n"
            f"> ID: {uid}\n\n"
            "🔗 *Ваша подписка:*\n"
            "> Нет активной подписки"
        )

    plan_name, conditions, device_limit, _ = plan_meta(sub["plan"])
    key = sub["issued_key"]

    return (
        "👤 *Профиль:*\n"
        f"> Имя: {name}\n"
        f"> ID: {uid}\n\n"
        "🔗 *Ваш ключ:*\n"
        f"> {key}\n\n"
        "📄 *Информация о тарифе:*\n"
        f"> Тариф: {plan_name} • ♾ Навсегда\n"
        f"> {conditions}\n"
        f"> Лимит устройств: {device_limit}"
    )


# ================= BANNER =================

async def send_banner(chat_id, text, keyboard=None):

    if os.path.exists(BANNER_PATH):

        await bot.send_photo(
            chat_id,
            FSInputFile(BANNER_PATH),
            caption=text,
            reply_markup=keyboard
        )

    else:
        await bot.send_message(
            chat_id,
            text,
            reply_markup=keyboard
        )


# ================= START =================

@dp.message(CommandStart())
async def start(m: Message):

    await send_banner(
        m.chat.id,
        text_menu(),
        kb_main()
    )

    await m.answer(reply_markup=kb_reply())


# ================= MENU BUTTON =================

@dp.message(F.text == "📋 Меню")
async def menu_btn(m: Message):

    await send_banner(
        m.chat.id,
        text_menu(),
        kb_main()
    )


# ================= SUB BUTTON =================

@dp.message(F.text == "🧾 Моя подписка")
async def sub_btn(m: Message):

    sub = db_get_last_accepted(m.from_user.id)

    await m.answer(
        text_subscription_card(m, sub),
        reply_markup=kb_copy_key() if sub else kb_main()
    )


# ================= CALLBACK =================

@dp.callback_query(F.data == "menu")
async def menu(call: CallbackQuery):

    await send_banner(
        call.message.chat.id,
        text_menu(),
        kb_main()
    )


@dp.callback_query(F.data == "mysub")
async def mysub(call: CallbackQuery):

    sub = db_get_last_accepted(call.from_user.id)

    await call.message.answer(
        text_subscription_card(call, sub),
        reply_markup=kb_copy_key() if sub else kb_main()
    )


# ================= COPY KEY =================

@dp.callback_query(F.data == "copy_key")
async def copy_key(call: CallbackQuery):

    sub = db_get_last_accepted(call.from_user.id)

    if not sub:
        await call.answer("Ключ не найден", show_alert=True)
        return

    await call.message.answer(
        f"📋 Скопируй ключ:\n\n`{sub['issued_key']}`"
    )

    await call.answer("Ключ отправлен")


# ================= MAIN =================

async def main():

    db_init()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
