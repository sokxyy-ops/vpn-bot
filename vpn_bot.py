import asyncio
import os
import time
import sqlite3
import re
from typing import Optional, List, Tuple, Dict, Any

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

# ================== НАСТРОЙКИ (ENV) ==================
# Укажите свои данные здесь или в переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_ТУТ").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) # ВАШ ТЕЛЕГРАМ ID
DB_PATH = "orders.sqlite"

# ================== ССЫЛКИ И ПУТИ ==================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BANNER_PATH = os.path.join(BASE_DIR, "banner.jpg")

TG_CHANNEL = "https://t.me/skywhy_news"  # Обновил название в ссылке (пример)
AGREEMENT_URL = "https://telegra.ph/Soglashenie-SkyWhy-VPN"

HAPP_ANDROID_URL = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_IOS_URL = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"

# Текст оплаты
PAYMENT_TEXT = (
    "💳 *Оплата подписки SkyWhy VPN*\n\n"
    "✅ *Перевод на карту:*\n"
    "`2204320913014587`\n\n"
    "🔁 *Через Ozon (по номеру):*\n"
    "`+79951253391`\n\n"
    "📎 *Инструкция:* После перевода отправьте *чек или скриншот* сюда в чат.\n"
    "Админ подтвердит оплату, и ключ появится в профиле! 🚀"
)

# ================== СОСТОЯНИЯ FSM ==================
class AdminStates(StatesGroup):
    broadcast_wait = State()
    price_wait = State()
    keys_wait = State()
    user_search_wait = State()

class OrderStates(StatesGroup):
    waiting_receipt = State()

# ================== РАБОТА С БАЗОЙ ДАННЫХ ==================
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def db_init():
    with db_conn() as con:
        cur = con.cursor()
        # Таблица заказов
        cur.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan TEXT,
            amount INTEGER,
            status TEXT,
            issued_key TEXT,
            accepted_at INTEGER,
            created_at INTEGER
        )""")
        # Таблица пользователей
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_banned INTEGER DEFAULT 0
        )""")
        # Таблица настроек
        cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # Таблица ключей (ключи хранятся здесь)
        cur.execute("""CREATE TABLE IF NOT EXISTS keys_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan TEXT,
            key TEXT UNIQUE
        )""")
        
        # Начальные цены
        cur.execute("INSERT OR IGNORE INTO settings VALUES ('price_standard', '200')")
        cur.execute("INSERT OR IGNORE INTO settings VALUES ('price_family', '350')")
        con.commit()

def get_setting(key, default="0"):
    with db_conn() as con:
        res = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return res['value'] if res else default

# ================== ЛОГИКА КЛЮЧЕЙ (БЕЗ УДАЛЕНИЯ) ==================
def take_key(plan: str) -> Optional[str]:
    with db_conn() as con:
        # Просто берем первый попавшийся ключ для этого тарифа
        res = con.execute("SELECT key FROM keys_store WHERE plan=? LIMIT 1", (plan,)).fetchone()
        return res['key'] if res else None

# ================== ДИЗАЙН И ТЕКСТЫ ==================
def plan_meta(plan_id):
    if plan_id == "standard":
        return "🟩 Стандарт", get_setting("price_standard")
    return "🟦 Семейная", get_setting("price_family")

def kb_main(user_id):
    buttons = [
        [InlineKeyboardButton(text="💎 Купить подписку", callback_data="buy_menu")],
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="⚙️ Инструкция", callback_data="setup_guide")],
        [InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL)]
    ]
    if user_id == ADMIN_ID:
        buttons.append([InlineKeyboardButton(text="👨‍💻 Админ-панель", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================== ХЕНДЛЕРЫ КЛИЕНТА ==================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def start(msg: Message):
    with db_conn() as con:
        con.execute("INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?,?,?)", 
                    (msg.from_user.id, msg.from_user.username, msg.from_user.first_name))
        con.commit()
    
    welcome_text = (
        "🛡️ *SkyWhy VPN — Твой надежный доступ*\n\n"
        "🚀 Высокая скорость и безлимитный трафик\n"
        "♾ Подписка покупается один раз и навсегда!\n\n"
        "Выберите действие в меню:"
    )
    await msg.answer(welcome_text, reply_markup=kb_main(msg.from_user.id))

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(call: CallbackQuery):
    p1_n, p1_v = plan_meta("standard")
    p2_n, p2_v = plan_meta("family")
    text = (
        "🛒 *Выберите тарифный план:*\n\n"
        f"{p1_n} — {p1_v}₽\n└ Идеально для одного телефона\n\n"
        f"{p2_n} — {p2_v}₽\n└ Можно использовать на 5+ устройствах"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p1_n} ({p1_v}₽)", callback_data="order:standard")],
        [InlineKeyboardButton(text=f"{p2_n} ({p2_v}₽)", callback_data="order:family")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    await call.message.edit_text(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("order:"))
async def create_order(call: CallbackQuery, state: FSMContext):
    plan = call.data.split(":")[1]
    name, price = plan_meta(plan)
    
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("INSERT INTO orders (user_id, plan, amount, status, created_at) VALUES (?,?,?,?,?)",
                    (call.from_user.id, plan, price, "waiting_receipt", int(time.time())))
        con.commit()
        order_id = cur.lastrowid

    await state.update_data(order_id=order_id)
    await state.set_state(OrderStates.waiting_receipt)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]])
    await call.message.edit_text(PAYMENT_TEXT, reply_markup=kb)

@dp.message(OrderStates.waiting_receipt, F.photo | F.document)
async def handle_receipt(msg: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    
    with db_conn() as con:
        con.execute("UPDATE orders SET status='pending_admin' WHERE id=?", (order_id,))
        con.commit()
    
    await msg.answer("✅ *Чек получен!* Ожидайте подтверждения администратором.")
    
    # Уведомление админу
    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_confirm:{order_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"adm_decline:{order_id}")]
    ])
    await bot.send_message(ADMIN_ID, f"🔔 *Новый заказ #{order_id}*\nОт: @{msg.from_user.username}\nID: `{msg.from_user.id}`")
    await msg.copy_to(ADMIN_ID, reply_markup=adm_kb)
    await state.clear()

@dp.callback_query(F.data == "profile")
async def profile(call: CallbackQuery):
    with db_conn() as con:
        orders = con.execute("SELECT * FROM orders WHERE user_id=? AND status='accepted' ORDER BY id DESC", 
                            (call.from_user.id,)).fetchall()
    
    text = f"👤 *Ваш профиль SkyWhy VPN*\nID: `{call.from_user.id}`\n\n"
    if not orders:
        text += "💎 У вас пока нет активных подписок."
    else:
        text += "💎 *Ваши ключи:*\n"
        for o in orders:
            p_name = "Стандарт" if o['plan'] == "standard" else "Семейная"
            text += f"━━━━━━━━━━━━━━\n🔹 Тариф: {p_name}\n🔑 Ключ: `{o['issued_key']}`\n"
    
    await call.message.edit_text(text, reply_markup=kb_main(call.from_user.id))

# ================== АДМИН-ЧАСТЬ ==================
@dp.callback_query(F.data.startswith("adm_confirm:"))
async def adm_confirm(call: CallbackQuery):
    order_id = call.data.split(":")[1]
    with db_conn() as con:
        order = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order: return
        
        key = take_key(order['plan'])
        if not key:
            await call.answer("❌ Нет свободных ключей в базе!", show_alert=True)
            return
        
        con.execute("UPDATE orders SET status='accepted', issued_key=?, accepted_at=? WHERE id=?", 
                    (key, int(time.time()), order_id))
        con.commit()
    
    await bot.send_message(order['user_id'], f"🎉 *Оплата подтверждена!*\n\nВаш ключ SkyWhy VPN: `{key}`\nОн также доступен в разделе 'Мой профиль'.")
    await call.message.edit_caption(caption=f"✅ Заказ #{order_id} одобрен")

@dp.callback_query(F.data == "admin_main")
async def admin_main(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ключи", callback_data="adm_add_keys")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])
    await call.message.edit_text("⚙️ Панель управления", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_keys")
async def adm_add_keys_choice(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Стандарт", callback_data="add_k:standard")],
        [InlineKeyboardButton(text="Семейная", callback_data="add_k:family")]
    ])
    await call.message.edit_text("Выберите тариф для добавления ключей:", reply_markup=kb)

@dp.callback_query(F.data.startswith("add_k:"))
async def adm_add_keys_start(call: CallbackQuery, state: FSMContext):
    plan = call.data.split(":")[1]
    await state.update_data(plan=plan)
    await state.set_state(AdminStates.keys_wait)
    await call.message.answer(f"Пришлите ключи для тарифа {plan} (каждый с новой строки):")

@dp.message(AdminStates.keys_wait)
async def adm_process_keys(msg: Message, state: FSMContext):
    data = await state.get_data()
    plan = data['plan']
    keys = msg.text.split("\n")
    
    with db_conn() as con:
        added = 0
        for k in keys:
            if k.strip():
                try:
                    con.execute("INSERT INTO keys_store (plan, key) VALUES (?,?)", (plan, k.strip()))
                    added += 1
                except: continue
        con.commit()
    
    await msg.answer(f"✅ Успешно добавлено {added} ключей.")
    await state.clear()

# ================== ОБЩИЕ ==================
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("🛡️ *SkyWhy VPN — Твой надежный доступ*", reply_markup=kb_main(call.from_user.id))

async def main():
    db_init()
    print("Бот SkyWhy VPN запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
