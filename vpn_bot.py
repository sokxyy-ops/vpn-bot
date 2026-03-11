import asyncio
import os
import time
import sqlite3
from typing import Optional, List, Tuple, Dict, Any, Callable, Awaitable
import re

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

# ================== BOT ИНИЦИАЛИЗАЦИЯ ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(storage=MemoryStorage())

# ================== MIDDLEWARE ДЛЯ БАНА ==================
class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and db_is_banned(user.id):
            if isinstance(event, Message):
                await event.answer("🚫 Вы заблокированы в этом боте.")
            return 
        return await handler(event, data)

dp.message.outer_middleware(BanMiddleware())
dp.callback_query.outer_middleware(BanMiddleware())

# ================== FSM ==================
class AdminStates(StatesGroup):
    broadcast_wait = State()
    message_user_wait = State()
    user_search_wait = State()
    # Другие состояния (цены, ключи и т.д.)

# ================== DB ФУНКЦИИ (ОБНОВЛЕННЫЕ) ==================
def db():
    return sqlite3.connect(DB_PATH)

def db_init():
    con = db()
    cur = con.cursor()
    # Таблица пользователей с полем бана
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_seen INTEGER NOT NULL,
            is_blocked INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    """)
    # Таблица заказов и ключей (упрощенно для примера, используй свои изначальные DDL)
    con.commit()
    con.close()

def db_is_banned(user_id: int) -> bool:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    con.close()
    return bool(res and res[0] == 1)

def db_toggle_ban(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET is_banned = 1 - is_banned WHERE user_id = ?", (user_id,))
    cur.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    new_status = cur.fetchone()[0]
    con.commit()
    con.close()
    return new_status

def db_get_all_users(offset=0, limit=10):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id, username, is_banned FROM users LIMIT ? OFFSET ?", (limit, offset))
    rows = cur.fetchall()
    con.close()
    return rows

# ================== АДМИНКА: ПОЛЬЗОВАТЕЛИ ==================

@dp.callback_query(F.data.startswith("admin:users:"))
async def admin_users_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    offset = int(call.data.split(":")[2])
    users = db_get_all_users(offset=offset)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for uid, uname, banned in users:
        status_icon = "🔴" if banned else "🟢"
        ban_text = "Разбанить" if banned else "Забанить"
        name = f"@{uname}" if uname else f"ID:{uid}"
        
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status_icon} {name}", callback_data=f"admin:user_info:{uid}"),
            InlineKeyboardButton(text="✉️", callback_data=f"msguser:{uid}"),
            InlineKeyboardButton(text=f"🚫 {ban_text}", callback_data=f"admin:ban:{uid}:{offset}")
        ])
    
    # Кнопки навигации (упрощенно)
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:home")])
    await call.message.edit_text("👥 *Управление пользователями:*\n🟢 - Активен, 🔴 - Забанен", reply_markup=kb)

@dp.callback_query(F.data.startswith("admin:ban:"))
async def admin_ban_toggle(call: CallbackQuery):
    parts = call.data.split(":")
    uid, offset = int(parts[2]), int(parts[3])
    if uid == ADMIN_ID: return await call.answer("Нельзя забанить себя")
    
    new_status = db_toggle_ban(uid)
    await call.answer("Статус изменен" if new_status else "Пользователь разбанен")
    # Возвращаемся в список на ту же страницу
    await admin_users_list(call)

# ================== АДМИНКА: НАПИСАТЬ ЮЗЕРУ ==================

@dp.callback_query(F.data.startswith("msguser:"))
async def admin_msg_user_start(call: CallbackQuery, state: FSMContext):
    target_id = int(call.data.split(":")[1])
    await state.update_data(target_user=target_id)
    await state.set_state(AdminStates.message_user_wait)
    await call.message.answer(f"✉️ Введите сообщение для пользователя `{target_id}`:\n(или напишите 'отмена')")
    await call.answer()

@dp.message(AdminStates.message_user_wait)
async def admin_msg_user_send(message: Message, state: FSMContext):
    if message.text.lower() == "отмена":
        await state.clear()
        return await message.answer("❌ Отменено")

    data = await state.get_data()
    uid = data.get("target_user")
    
    try:
        await bot.send_message(uid, f"🔔 *Сообщение от администрации SOKXYY VPN:*\n\n{message.text}")
        await message.answer(f"✅ Сообщение отправлено пользователю `{uid}`")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()

# ================== ОСТАЛЬНАЯ ЛОГИКА (START, MAIN и т.д.) ==================
# ... (используй свои функции cmd_start и main из исходного файла)

async def main():
    db_init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
