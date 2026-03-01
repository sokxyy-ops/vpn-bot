import asyncio
import os
import time
import sqlite3

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties

# ====== ENV (Railway Variables) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ====== LINKS / SETTINGS ======
TG_CHANNEL = "https://t.me/sokxyybc"
ADMIN_USERNAME = "whyshawello"  # без @

PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"
REVIEW_LINK = "https://t.me/sokxyybc/23"

PAYMENT_TEXT = (
    "💳 *Реквизиты для оплаты*\n\n"
    "✅ *Основной способ (карта):*\n"
    "Номер карты: `2204320913014587`\n\n"
    "🔁 *Если есть комиссия — переводи через Ozon по номеру:*\n"
    "Номер: `+79951253391`\n\n"
    "📎 После оплаты отправь сюда *чек/скрин*.\n"
    "Админ подтвердит — бот выдаст ключ."
)

# ====== Антиспам ======
USER_COOLDOWN_SEC = 60
last_order_time = {}  # user_id -> unix time

# ====== SQLite (заказы) ======
DB_PATH = "orders.sqlite"

def db():
    return sqlite3.connect(DB_PATH)

def db_init():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    con.commit()
    con.close()

def db_create_order(order_id: int, user_id: int, plan: str, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO orders(order_id, user_id, plan, amount, status, created_at) VALUES(?,?,?,?,?,?)",
        (order_id, user_id, plan, amount, "wait_receipt", int(time.time()))
    )
    con.commit()
    con.close()

def db_get_active_order(user_id: int):
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
    return {"order_id": row[0], "plan": row[1], "amount": row[2], "status": row[3]}

def db_get_order(order_id: int):
    con = db()
    cur = con.cursor()
    cur.execute(
        "SELECT order_id, user_id, plan, amount, status FROM orders WHERE order_id=?",
        (order_id,)
    )
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {"order_id": row[0], "user_id": row[1], "plan": row[2], "amount": row[3], "status": row[4]}

def db_set_status(order_id: int, status: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE orders SET status=? WHERE order_id=?", (status, order_id))
    con.commit()
    con.close()

# ====== Keys (НЕ удаляем) ======
def take_key(plan: str) -> str | None:
    filename = "standard_keys.txt" if plan == "standard" else "family_keys.txt"
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = [x.strip() for x in f.read().splitlines() if x.strip()]
    if not lines:
        return None
    return lines[0]  # всегда первая строка (не удаляем)

# ====== Keyboards ======
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟩 Стандарт — 200₽", callback_data="plan:standard")],
        [InlineKeyboardButton(text="🟦 Семейная — 300₽", callback_data="plan:family")],
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel")],
        [InlineKeyboardButton(text="📣 TG канал", url=TG_CHANNEL)],
    ])

def kb_plan(plan: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Получить реквизиты", callback_data=f"pay:{plan}")],
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel")],
        [InlineKeyboardButton(text="✉️ Написать админу", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ])

def kb_admin(order_id: int, plan: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять (выдать ключ)", callback_data=f"admin:ok:{order_id}:{plan}:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}:{plan}:{user_id}"),
        ]
    ])

def kb_after_key(subscription: str) -> InlineKeyboardMarkup:
    # ✅ БЕЗ vleska: прямой deep-link
    connect_url = f"happ://add/{subscription}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться (Happ)", url=connect_url)],
        [InlineKeyboardButton(text="🔒 Вступить в приватную группу (обязательно)", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
    ])

# ====== Bot ======
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

# ====== Commands ======
@dp.message(CommandStart())
async def start_cmd(m: Message):
    await m.answer(
        "⚡ *Sokxyy Обход — VPN навсегда*\n\n"
        "✅ *Обе подписки:* обходят белые списки, глушилки\n"
        "🔑 После покупки выдаётся подписка для *Happ*\n\n"
        "Выбери подписку 👇",
        reply_markup=kb_main()
    )

@dp.message(Command("myid"))
async def myid(m: Message):
    await m.answer(f"Твой ID: `{m.from_user.id}`")

# ====== Navigation ======
@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    await start_cmd(call.message)
    await call.answer()

# ====== Cancel ======
@dp.callback_query(F.data == "cancel")
async def cancel_btn(call: CallbackQuery):
    active = db_get_active_order(call.from_user.id)
    if not active:
        await call.message.answer("У тебя нет активного заказа.", reply_markup=kb_main())
        await call.answer()
        return

    db_set_status(active["order_id"], "cancelled")

    try:
        await bot.send_message(
            ADMIN_ID,
            f"ℹ️ Пользователь `{call.from_user.id}` отменил заказ *#{active['order_id']}* (было: *{active['status']}*)."
        )
    except Exception:
        pass

    await call.message.answer(f"✅ Заказ *#{active['order_id']}* отменён.", reply_markup=kb_main())
    await call.answer()

@dp.message(Command("cancel"))
async def cancel_cmd(m: Message):
    active = db_get_active_order(m.from_user.id)
    if not active:
        await m.answer("У тебя нет активного заказа.", reply_markup=kb_main())
        return
    db_set_status(active["order_id"], "cancelled")
    await m.answer(f"✅ Заказ *#{active['order_id']}* отменён.", reply_markup=kb_main())

# ====== Plans ======
@dp.callback_query(F.data.startswith("plan:"))
async def plan_info(call: CallbackQuery):
    plan = call.data.split(":")[1]
    if plan == "standard":
        text = (
            "🟩 *Стандарт — 200₽ (навсегда)*\n"
            "👤 1 пользователь\n"
            "📱 до 3 устройств\n\n"
            "✅ Обходит белые списки и глушилки\n"
            "🔑 Подписка для Happ после оплаты\n"
        )
    else:
        text = (
            "🟦 *Семейная — 300₽ (навсегда)*\n"
            "👥 до 8 пользователей\n"
            "📱 у каждого до 3 устройств\n\n"
            "✅ Обходит белые списки и глушилки\n"
            "🔑 Подписка для Happ после оплаты\n"
        )
    await call.message.answer(text + "\n" + f"📣 Канал: {TG_CHANNEL}", reply_markup=kb_plan(plan))
    await call.answer()

# ====== Create order ======
@dp.callback_query(F.data.startswith("pay:"))
async def pay(call: CallbackQuery):
    user_id = call.from_user.id
    plan = call.data.split(":")[1]
    amount = 200 if plan == "standard" else 300

    active = db_get_active_order(user_id)
    if active:
        if active["status"] == "wait_receipt":
            await call.message.answer(
                f"⏳ У тебя уже есть активный заказ *#{active['order_id']}*.\n"
                f"Сумма: *{active['amount']}₽*\n\n"
                f"{PAYMENT_TEXT}\n\n"
                "📎 Отправь чек/скрин сюда в чат."
            )
        else:
            await call.message.answer(
                f"⏳ Заказ *#{active['order_id']}* уже отправлен админу на проверку.\n"
                "Дождись подтверждения."
            )
        await call.answer()
        return

    now = int(time.time())
    last = last_order_time.get(user_id, 0)
    left = USER_COOLDOWN_SEC - (now - last)
    if left > 0:
        await call.message.answer(f"⛔ Подожди *{left} сек* и попробуй снова.")
        await call.answer()
        return

    # order_id по времени (не зависит от RAM)
    order_id = int(time.time() * 1000)
    db_create_order(order_id, user_id, plan, amount)
    last_order_time[user_id] = now

    await call.message.answer(
        f"🧾 *Заказ #{order_id}*\n"
        f"Сумма: *{amount}₽*\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст)."
    )
    await call.answer()

# ====== Receipt (admin receives always) ======
@dp.message(F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    user_id = m.from_user.id
    active = db_get_active_order(user_id)

    if active and active["status"] == "pending_admin":
        await m.answer("⏳ Твой чек уже отправлен админу. Дождись подтверждения.")
        return

    # если нашли заказ — ставим pending_admin
    if active:
        db_set_status(active["order_id"], "pending_admin")

    order_id = active["order_id"] if active else None
    plan = active["plan"] if active else None
    amount = active["amount"] if active else None

    # 1) текст админу всегда
    if active:
        await bot.send_message(
            ADMIN_ID,
            "🔔 *Чек на проверку*\n"
            f"Заказ: *#{order_id}*\n"
            f"Пользователь: `{user_id}` (@{m.from_user.username or '—'})\n"
            f"Сумма: *{amount}₽*\n\n"
            "Принять оплату?",
            reply_markup=kb_admin(order_id, plan, user_id)
        )
    else:
        await bot.send_message(
            ADMIN_ID,
            "⚠️ *Чек без активного заказа*\n"
            f"Пользователь: `{user_id}` (@{m.from_user.username or '—'})\n\n"
            "Это бывает после деплоя/сброса базы.\n"
            "Попроси у пользователя тариф и сумму — и прими вручную."
        )

    # 2) копия чека админу (надежнее, чем forward)
    try:
        await m.copy_to(ADMIN_ID)
    except Exception as e:
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ Не смог скопировать чек: `{type(e).__name__}`")
        except Exception:
            pass

    await m.answer("✅ Чек отправлен админу. Жди подтверждения.")

# ====== Admin decision (fixed) ======
@dp.callback_query(F.data.startswith("admin:"))
async def admin_decide(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Не админ", show_alert=True)
        return

    try:
        _, act, order_id, plan, user_id = call.data.split(":")
        order_id = int(order_id)
        user_id = int(user_id)
    except Exception:
        await call.answer("Ошибка данных заказа", show_alert=True)
        return

    order = db_get_order(order_id)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order["status"] != "pending_admin":
        await call.answer("Заказ уже обработан/отменён", show_alert=True)
        return

    if act == "ok":
        key = take_key(plan)
        if not key:
            await call.answer("Ключи не найдены", show_alert=True)
            try:
                await bot.send_message(ADMIN_ID, "⚠️ В файле ключей нет строк. Заполни standard_keys.txt / family_keys.txt.")
            except Exception:
                pass
            return

        db_set_status(order_id, "accepted")

        await bot.send_message(
            user_id,
            "✅ *Оплата подтверждена!*\n\n"
            "🔑 Твоя подписка:\n"
            f"`{key}`\n\n"
            "Нажми кнопку ниже — откроется *Happ* и подписка добавится.\n\n"
            "🔒 *Важно:* без вступления в приватную группу обслуживания нет.\n"
            "⭐ Буду благодарен за отзыв.",
            reply_markup=kb_after_key(key)
        )

        await call.message.edit_text(call.message.text + "\n\n✅ Принято. Подписка выдана.")
        await call.answer("Выдано")

    elif act == "no":
        db_set_status(order_id, "rejected")
        await bot.send_message(user_id, "❌ *Оплата не подтверждена.* Отправь корректный чек ещё раз.")
        await call.message.edit_text(call.message.text + "\n\n❌ Отклонено.")
        await call.answer("Отклонено")

# ====== Run ======
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set (Railway Variables -> BOT_TOKEN)")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set (Railway Variables -> ADMIN_ID)")

    db_init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
