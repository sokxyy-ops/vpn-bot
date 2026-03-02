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
    "💳 *Оплата*\n\n"
    "✅ *Карта:*\n"
    "Номер: `2204320913014587`\n\n"
    "🔁 *Если есть комиссия — переводи через Ozon по номеру:*\n"
    "Номер: `+79951253391`\n\n"
    "📎 *После оплаты отправь сюда чек/скрин.*\n"
    "Я проверю — бот выдаст ключ."
)

# ================== KEY FILES ==================
STANDARD_KEYS_FILE = "standard_keys.txt"
FAMILY_KEYS_FILE = "family_keys.txt"

# ================== DB ==================
DB_PATH = os.getenv("DB_PATH", "orders.sqlite")

def db():
    # check_same_thread=False чтобы sqlite не душил в редких случаях
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def _ensure_column(cur: sqlite3.Cursor, table: str, col: str, col_def: str):
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}  # row[1] = name
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")

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
    # миграции (если база старая)
    _ensure_column(cur, "orders", "order_msg_chat_id", "INTEGER DEFAULT NULL")
    _ensure_column(cur, "orders", "order_msg_id", "INTEGER DEFAULT NULL")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status)")
    con.commit()
    con.close()

def db_create_order(user_id: int, username: str | None, plan: str, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders(user_id, username, plan, amount, status, created_at, order_msg_chat_id, order_msg_id)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (user_id, username or "", plan, amount, "waiting_receipt", int(time.time()), None, None))
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

def db_set_order_message(order_id: int, chat_id: int, msg_id: int):
    con = db()
    cur = con.cursor()
    # если колонок вдруг нет — не падаем
    try:
        cur.execute(
            "UPDATE orders SET order_msg_chat_id=?, order_msg_id=? WHERE id=?",
            (chat_id, msg_id, order_id),
        )
        con.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        con.close()

def db_get_active_order(user_id: int):
    con = db()
    cur = con.cursor()

    # Пытаемся новой схемой (с message_id)
    try:
        cur.execute("""
            SELECT id, plan, amount, status, order_msg_chat_id, order_msg_id FROM orders
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
            "order_msg_chat_id": row[4],
            "order_msg_id": row[5],
        }
    except sqlite3.OperationalError:
        # Старая база (без колонок order_msg_*)
        cur.execute("""
            SELECT id, plan, amount, status FROM orders
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
            "order_msg_chat_id": None,
            "order_msg_id": None,
        }

def db_get_order(order_id: int):
    con = db()
    cur = con.cursor()

    try:
        cur.execute("""
            SELECT id, user_id, username, plan, amount, status, order_msg_chat_id, order_msg_id
            FROM orders WHERE id=?
        """, (order_id,))
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
            "order_msg_chat_id": row[6],
            "order_msg_id": row[7],
        }
    except sqlite3.OperationalError:
        # Старая база
        cur.execute("""
            SELECT id, user_id, username, plan, amount, status
            FROM orders WHERE id=?
        """, (order_id,))
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
            "order_msg_chat_id": None,
            "order_msg_id": None,
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

# ================== HELPERS ==================
def plan_name(plan: str) -> str:
    return "🟩 Стандарт" if plan == "standard" else "🟦 Семейная"

def admin_url() -> str:
    return f"tg://user?id={ADMIN_ID}"

# ================== KEYBOARDS ==================
def kb_start():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟩 Стандарт — 200₽", callback_data="buy:standard")],
        [InlineKeyboardButton(text="🟦 Семейная — 300₽", callback_data="buy:family")],
        [
            InlineKeyboardButton(text="✍️ Написать админу", url=admin_url()),
            InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL),
        ],
    ])

def kb_order_controls(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{order_id}"),
            InlineKeyboardButton(text="✍️ Написать админу", url=admin_url()),
        ],
        [InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL)],
    ])

def kb_admin(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:ok:{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}")
        ]
    ])

def kb_admin_resolved(status: str):
    if status == "accepted":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принято", callback_data="noop:accepted")]
        ])
    if status == "rejected":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отклонено", callback_data="noop:rejected")]
        ])
    if status == "cancelled":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Отменено пользователем", callback_data="noop:cancelled")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Обработано", callback_data="noop:done")]
    ])

def kb_after_issue():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Happ (Android)", url=HAPP_ANDROID_URL)],
        [InlineKeyboardButton(text="🍎 Happ (iOS)", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Happ (Windows)", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [
            InlineKeyboardButton(text="✍️ Поддержка (админ)", url=admin_url()),
            InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK),
        ],
    ])

# ================== BOT ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "⚡ *Sokxyy Обход — VPN навсегда*\n\n"
        "🛡️ *Обходит глушилки / блокировки*\n"
        "🌐 Есть *обычный VPN* и *режим обхода*\n"
        "♾️ *Выдаётся навсегда* (без ежемесячных платежей)\n"
        "🔑 После оплаты выдаю *ключ для Happ*\n\n"
        "Выбери тариф 👇",
        reply_markup=kb_start()
    )

@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery):
    user_id = call.from_user.id
    username = call.from_user.username

    active = db_get_active_order(user_id)
    if active:
        await call.message.answer(
            f"⏳ У тебя уже есть активный заказ *#{active['id']}*.\n"
            "📎 Просто отправь сюда *чек/скрин* оплаты.\n\n"
            "Если передумал — можешь отменить заказ кнопкой ниже.",
            reply_markup=kb_order_controls(active["id"])
        )
        await call.answer()
        return

    plan = call.data.split(":")[1]
    amount = 200 if plan == "standard" else 300

    order_id = db_create_order(user_id, username, plan, amount)

    sent = await call.message.answer(
        f"🧾 *Заказ #{order_id}*\n"
        f"📦 Тариф: *{plan_name(plan)}*\n"
        f"💰 Сумма: *{amount}₽*\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "📌 *Отправь чек/скрин сюда в чат* (фото/файл/текст).\n"
        "После проверки бот выдаст ключ ✅",
        reply_markup=kb_order_controls(order_id)
    )

    # Запоминаем ID сообщения с реквизитами (если база старая — просто пропустится)
    db_set_order_message(order_id, sent.chat.id, sent.message_id)

    await call.answer()

@dp.callback_query(F.data.startswith("cancel:"))
async def cancel_order(call: CallbackQuery):
    user_id = call.from_user.id
    order_id = int(call.data.split(":")[1])

    order = db_get_order(order_id)
    if not order or order["user_id"] != user_id:
        await call.answer("Заказ не найден", show_alert=True)
        return

    if order["status"] in ("accepted", "rejected", "cancelled"):
        await call.answer("Этот заказ уже закрыт", show_alert=True)
        return

    prev_status = order["status"]
    db_set_status(order_id, "cancelled")

    # Удаляем сообщение с реквизитами (ботовское), если оно сохранено
    if order.get("order_msg_chat_id") and order.get("order_msg_id"):
        try:
            await bot.delete_message(order["order_msg_chat_id"], order["order_msg_id"])
        except Exception:
            pass

    # Уведомим админа
    try:
        await bot.send_message(
            ADMIN_ID,
            "🚫 *Заказ отменён пользователем*\n"
            f"Заказ: *#{order_id}*\n"
            f"Пользователь: `{order['user_id']}` (@{order['username'] or '—'})\n"
            f"Тариф: *{order['plan']}* / {plan_name(order['plan'])}\n"
            f"Сумма: *{order['amount']}₽*\n"
            f"Статус был: *{prev_status}*"
        )
    except Exception:
        pass

    await call.message.answer(
        f"✅ Заказ *#{order_id}* отменён.\n\n"
        "Если захочешь снова — нажми /start и выбери тариф."
    )
    await call.answer("Отменено ✅")

@dp.message(F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    user_id = m.from_user.id
    username = m.from_user.username

    active = db_get_active_order(user_id)
    if not active:
        await m.answer("⚠️ Нет активного заказа. Нажми /start и выбери тариф.")
        return

    if active["status"] == "pending_admin":
        await m.answer(
            "⏳ Чек уже отправлен админу. Жди подтверждения.\n"
            "Если нужно — можешь написать админу или отменить заказ.",
            reply_markup=kb_order_controls(active["id"])
        )
        return

    db_set_status(active["id"], "pending_admin")

    await bot.send_message(
        ADMIN_ID,
        "🔔 *Чек на проверку*\n"
        f"Заказ: *#{active['id']}*\n"
        f"Пользователь: `{user_id}` (@{username or '—'})\n"
        f"Тариф: *{active['plan']}* / {plan_name(active['plan'])}\n"
        f"Сумма: *{active['amount']}₽*\n\n"
        "Принять оплату?",
        reply_markup=kb_admin(active["id"])
    )

    try:
        await m.copy_to(ADMIN_ID)
    except Exception:
        pass

    await m.answer(
        "✅ Чек отправлен админу.\n"
        "⏳ Жди подтверждения.\n\n"
        "Если нужно — можешь написать админу или отменить заказ.",
        reply_markup=kb_order_controls(active["id"])
    )

async def send_key_to_user(user_id: int, plan: str, key: str):
    await bot.send_message(
        user_id,
        "✅ *Оплата подтверждена!*\n\n"
        f"📦 Тариф: *{plan_name(plan)}* (навсегда)\n\n"
        "🔑 *Твой ключ:*\n"
        f"`{key}`\n\n"
        "📲 *Как подключиться (Happ):*\n"
        "1) Скачай Happ (кнопки ниже)\n"
        "2) Открой приложение\n"
        "3) Нажми «Добавить / Import / Подписка»\n"
        "4) Вставь *ключ* и сохрани\n\n"
        "🌍 Дальше выбирай сервер и подключайся.\n\n"
        "🔒 Вступи в приватную группу (для обслуживания).\n"
        "⭐ Оставь отзыв — буду благодарен.",
        reply_markup=kb_after_issue()
    )

@dp.callback_query(F.data.startswith("noop:"))
async def noop(call: CallbackQuery):
    await call.answer("Этот заказ уже обработан.", show_alert=True)

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

    # Если отменён — блокируем и меняем кнопки
    if order["status"] == "cancelled":
        try:
            await call.message.edit_reply_markup(reply_markup=kb_admin_resolved("cancelled"))
        except Exception:
            pass
        await call.answer("Заказ отменён пользователем", show_alert=True)
        return

    if action == "no":
        db_set_status(order_id, "rejected")

        try:
            await call.message.edit_reply_markup(reply_markup=kb_admin_resolved("rejected"))
        except Exception:
            pass

        try:
            await bot.send_message(
                order["user_id"],
                "❌ Оплата отклонена.\n"
                "Отправь корректный чек ещё раз (в этот чат), либо нажми /start и создай новый заказ."
            )
        except Exception:
            pass

        await call.answer("Отклонено")
        return

    if action == "ok":
        if order["status"] == "accepted":
            try:
                await call.message.edit_reply_markup(reply_markup=kb_admin_resolved("accepted"))
            except Exception:
                pass
            await call.answer("Уже выдано", show_alert=True)
            return

        key = take_key(order["plan"])
        if not key:
            await call.answer("Ключей нет", show_alert=True)
            await bot.send_message(
                ADMIN_ID,
                "⚠️ В файлах ключей пусто.\n"
                "Заполни standard_keys.txt / family_keys.txt."
            )
            return

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

        db_set_status(order_id, "accepted")

        try:
            await call.message.edit_reply_markup(reply_markup=kb_admin_resolved("accepted"))
        except Exception:
            pass

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
