import asyncio
import os
import time
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ================== LINKS ==================
TG_CHANNEL = "https://t.me/sokxyybc"
PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"
REVIEW_LINK = "https://t.me/sokxyybc/23"

# Клиенты Happ
HAPP_ANDROID_URL = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_IOS_URL = "https://apps.apple.com/app/happ-proxy-utility/id6504287215"
HAPP_WINDOWS_URL = "https://happ.su/"

# ================== PAYMENT ==================
PAYMENT_TEXT = (
    "💳 *Реквизиты для оплаты*\n\n"
    "✅ *Основной способ (карта):*\n"
    "Номер карты: `2204320913014587`\n\n"
    "🔁 *Если есть комиссия — переводи через Ozon по номеру:*\n"
    "Номер: `+79951253391`\n\n"
    "📎 После оплаты отправь сюда *чек/скрин*.\n"
    "Я проверю — бот выдаст ключ."
)

# ================== KEY FILES ==================
STANDARD_KEYS_FILE = "standard_keys.txt"
FAMILY_KEYS_FILE = "family_keys.txt"

# ================== DB ==================
# Если хочешь чтобы база не слетала на Railway:
# добавь Volume /data и поставь переменную DB_PATH=/data/orders.sqlite
DB_PATH = os.getenv("DB_PATH", "orders.sqlite")

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
            status TEXT NOT NULL,         -- waiting_receipt / pending_admin / accepted / rejected
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    con.commit()
    con.close()

def db_get_active_order(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, status FROM orders
        WHERE user_id=? AND status IN ('waiting_receipt','pending_admin')
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "plan": row[1], "amount": row[2], "status": row[3]}

def db_create_order(user_id: int, username: str | None, plan: str, amount: int):
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

def db_set_status(order_id: int, status: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    con.commit()
    con.close()

def db_get_order(order_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, user_id, username, plan, amount, status FROM orders WHERE id=?", (order_id,))
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
    }

# ================== KEYS (НЕ УДАЛЯЕМ) ==================
def take_key(plan: str) -> str | None:
    filename = STANDARD_KEYS_FILE if plan == "standard" else FAMILY_KEYS_FILE
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = [x.strip() for x in f.read().splitlines() if x.strip()]
    if not lines:
        return None
    return lines[0]  # всегда первая строка, НЕ удаляем

# ================== KEYBOARDS ==================
def kb_start():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟩 Стандарт — 200₽", callback_data="buy:standard")],
        [InlineKeyboardButton(text="🟦 Семейная — 300₽", callback_data="buy:family")],
        [InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL)],
    ])

def kb_admin(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:ok:{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}")
        ]
    ])

def kb_after_issue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Скачать Happ (Android)", url=HAPP_ANDROID_URL)],
        [InlineKeyboardButton(text="🍎 Скачать Happ (iOS)", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Скачать Happ (Windows)", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
    ])

# ================== BOT ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "⚡ *Sokxyy Обход — VPN навсегда*\n\n"
        "✅ Доступ навсегда\n"
        "🔑 После оплаты выдаётся ключ для *Happ*\n\n"
        "Выбери тариф 👇",
        reply_markup=kb_start()
    )

@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username

    # 1 активный заказ — чтобы не заспамили
    active = db_get_active_order(user_id)
    if active:
        await call.message.answer(
            f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n"
            "Просто отправь сюда чек/скрин оплаты."
        )
        await call.answer()
        return

    plan = call.data.split(":")[1]
    amount = 200 if plan == "standard" else 300
    plan_name = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"

    order_id = db_create_order(user_id, username, plan, amount)

    await call.message.answer(
        f"🧾 *Заказ #{order_id}*\n"
        f"Тариф: *{plan_name}*\n"
        f"Сумма: *{amount}₽*\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст)."
    )
    await call.answer()

@dp.message(F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    user_id = m.from_user.id
    username = m.from_user.username

    active = db_get_active_order(user_id)
    if not active:
        await m.answer("⚠️ Нет активного заказа. Нажми /start и выбери тариф.")
        return

    if active["status"] == "pending_admin":
        await m.answer("⏳ Чек уже отправлен админу. Жди подтверждения.")
        return

    db_set_status(active["id"], "pending_admin")

    await bot.send_message(
        ADMIN_ID,
        "🔔 *Чек на проверку*\n"
        f"Заказ: *#{active['id']}*\n"
        f"Пользователь: `{user_id}` (@{username or '—'})\n"
        f"Тариф: *{active['plan']}*\n"
        f"Сумма: *{active['amount']}₽*\n\n"
        "Принять оплату?",
        reply_markup=kb_admin(active["id"])
    )

    try:
        await m.copy_to(ADMIN_ID)
    except Exception:
        pass

    await m.answer("✅ Чек отправлен админу. Жди подтверждения.")

async def send_key_to_user(user_id: int, plan: str, key: str):
    plan_name = "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"
    await bot.send_message(
        user_id,
        "✅ *Оплата подтверждена!*\n\n"
        f"Тариф: *{plan_name}* (навсегда)\n\n"
        "🔑 *Твой ключ:*\n"
        f"`{key}`\n\n"
        "📲 *Как подключиться (Happ):*\n"
        "1) Скачай Happ (кнопки ниже)\n"
        "2) Открой приложение\n"
        "3) Нажми «Добавить / Import / Подписка»\n"
        "4) Вставь туда *ключ* (который выше)\n\n"
        "🌍 После добавления появятся сервера — выбирай любой и подключайся.\n\n"
        "🔒 Вступи в приватную группу (обязательно для обслуживания).\n"
        "⭐ Оставь отзыв — буду благодарен.",
        reply_markup=kb_after_issue()
    )

@dp.callback_query(F.data.startswith("admin:"))
async def admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return

    _, action, order_id_str = call.data.split(":")
    order_id = int(order_id_str)

    order = db_get_order(order_id)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if action == "no":
        db_set_status(order_id, "rejected")
        try:
            await bot.send_message(order["user_id"], "❌ Оплата отклонена. Отправь корректный чек ещё раз.")
        except Exception:
            pass
        await call.answer("Отклонено")
        return

    if action == "ok":
        if order["status"] == "accepted":
            await call.answer("Уже выдано", show_alert=True)
            return

        key = take_key(order["plan"])
        if not key:
            await call.answer("Ключей нет", show_alert=True)
            await bot.send_message(ADMIN_ID, "⚠️ В файлах ключей пусто. Заполни standard_keys.txt / family_keys.txt.")
            return

        # Сначала пытаемся отправить пользователю
        try:
            await send_key_to_user(order["user_id"], order["plan"], key)
        except TelegramForbiddenError:
            await call.answer("Не могу написать юзеру", show_alert=True)
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ Не смог отправить пользователю `{order['user_id']}`.\n"
                "Пусть он откроет бота и нажмёт /start, затем попробуй снова."
            )
            return
        except TelegramBadRequest as e:
            await call.answer("TelegramBadRequest", show_alert=True)
            await bot.send_message(ADMIN_ID, f"⚠️ TelegramBadRequest при выдаче: `{e}`")
            return
        except Exception as e:
            await call.answer("Ошибка", show_alert=True)
            await bot.send_message(ADMIN_ID, f"⚠️ Ошибка при выдаче: `{type(e).__name__}`")
            return

        # Только после успешной отправки
        db_set_status(order_id, "accepted")
        await call.answer("Выдано ✅")
        return

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set (Railway Variables)")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set (Railway Variables)")

    db_init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
