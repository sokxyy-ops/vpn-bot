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
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@")  # опционально
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

    con.close()


def db_get_active_order(user_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, plan, amount, status, payment_msg_id
        FROM orders
        WHERE user_id=? AND status IN ('waiting_receipt','pending_admin')
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "plan": row[1], "amount": row[2], "status": row[3], "payment_msg_id": row[4]}


def db_create_order(user_id: int, username: Optional[str], plan: str, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders(user_id, username, plan, amount, status, created_at, payment_msg_id, issued_key, accepted_at)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (user_id, username or "", plan, amount, "waiting_receipt", int(time.time()), None, None, None))
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
        SELECT id, user_id, username, plan, amount, status, payment_msg_id, issued_key, accepted_at
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
        "payment_msg_id": row[6],
        "issued_key": row[7],
        "accepted_at": row[8],
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
    return {
        "id": row[0],
        "plan": row[1],
        "amount": row[2],
        "issued_key": row[3],
        "accepted_at": row[4],
    }


# ================== PLANS ==================
def plan_meta(plan: str):
    # returns (plan_name, conditions, device_limit_text, amount)
    if plan == "standard":
        return "🟩 Стандарт", "👤 1 пользователь • 📱 до 3 устройств", "3", 200
    return "🟦 Семейная", "👥 до 8 пользователей • 📱 до 3 устройств каждому", "24", 300


# ================== KEYS (НЕ УДАЛЯЕМ) ==================
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
        "⚡ *Sokxyy Обход — VPN*\n\n"
        "🛡 Обычный VPN + режим обхода блокировок\n"
        "♾ Доступ *навсегда*\n"
        "🔑 Выдача ключа для *Happ* после оплаты\n\n"
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

    return (
        "👤 *Профиль:*\n"
        f"> Имя: {name}\n"
        f"> ID: {uid}\n\n"
        "🔗 *Ваш ключ:*\n"
        f"> {key}\n\n"
        "📄 *Информация о тарифе:*\n"
        f"> Тариф: {plan_name} • ♾ Навсегда\n"
        f"> {conditions}\n"
        f"> Лимит устройств: {device_limit}\n\n"
        "👇 Используй кнопки ниже"
    )


# ================== KEYBOARDS ==================
def kb_reply_menu():
    rows = [[KeyboardButton(text="📋 Меню"), KeyboardButton(text="🧾 Моя подписка")]]
    if ADMIN_USERNAME:
        rows.append([KeyboardButton(text="🆘 Поддержка")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")],
        [InlineKeyboardButton(text="🧾 Моя подписка", callback_data="menu:sub")],
        [InlineKeyboardButton(text="📣 Канал", url=TG_CHANNEL)],
    ])


def kb_buy():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🟩 Стандарт — 200₽ (1 пользователь • до 3 устройств)",
            callback_data="buy:standard"
        )],
        [InlineKeyboardButton(
            text="🟦 Семейная — 300₽ (до 8 пользователей • до 3 устройств каждому)",
            callback_data="buy:family"
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main")],
    ])


def kb_payment(order_id: int):
    rows = [
        [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{order_id}")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ]
    if ADMIN_USERNAME:
        rows.insert(0, [InlineKeyboardButton(text="🆘 Поддержка", url=f"https://t.me/{ADMIN_USERNAME}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"admin:ok:{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:no:{order_id}")
        ]
    ])


def kb_after_issue(key: str):
    rows = []

    # ⚡ Подключить Happ — просто ссылка на ключ (если начинается с happ://)
    if key and isinstance(key, str) and key.startswith("happ://"):
        rows.append([InlineKeyboardButton(text="⚡ Подключить Happ", url=key)])

    rows += [
        [InlineKeyboardButton(text="📋 Скопировать ключ", callback_data="sub:copy")],
        [InlineKeyboardButton(text="📱 Happ (Android)", url=HAPP_ANDROID_URL)],
        [InlineKeyboardButton(text="🍎 Happ (iOS)", url=HAPP_IOS_URL)],
        [InlineKeyboardButton(text="💻 Happ (Windows)", url=HAPP_WINDOWS_URL)],
        [InlineKeyboardButton(text="🔒 Приватная группа", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ]
    if ADMIN_USERNAME:
        rows.insert(0, [InlineKeyboardButton(text="🆘 Поддержка", url=f"https://t.me/{ADMIN_USERNAME}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_sub_no_sub():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="menu:buy")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")],
    ])


# ================== BANNER SEND ==================
async def send_banner_or_text(chat_id: int, text: str, reply_markup=None):
    try:
        if os.path.exists(BANNER_PATH):
            await bot.send_photo(
                chat_id,
                FSInputFile(BANNER_PATH),
                caption=text,
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except Exception:
        # запасной вариант
        await bot.send_message(chat_id, text, reply_markup=reply_markup)


# ================== START / MENU ==================
@dp.message(CommandStart())
async def start(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())
    # просто ставим нижнюю клаву, без сообщения
    try:
        await bot.send_message(m.chat.id, " ", reply_markup=kb_reply_menu())
    except Exception:
        # если не нравится пробел — можно убрать совсем
        pass


@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())


@dp.message(F.text == "📋 Меню")
async def menu_btn(m: Message):
    await send_banner_or_text(m.chat.id, text_menu(), reply_markup=kb_main())


@dp.message(F.text == "🆘 Поддержка")
async def support_btn(m: Message):
    if ADMIN_USERNAME:
        await m.answer(f"🆘 Поддержка: https://t.me/{ADMIN_USERNAME}")
    else:
        await m.answer("🆘 Поддержка недоступна (ADMIN_USERNAME не задан).")


@dp.message(F.text == "🧾 Моя подписка")
async def mysub_btn(m: Message):
    sub = db_get_last_accepted(m.from_user.id)
    if not sub:
        await m.answer(text_subscription_card(m.from_user, None), reply_markup=kb_sub_no_sub())
        return

    key = sub.get("issued_key") or ""
    await m.answer(
        text_subscription_card(m.from_user, sub),
        reply_markup=kb_after_issue(key)
    )


# ================== CALLBACK ROUTER ==================
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
                await call.message.answer(
                    text_subscription_card(call.from_user, None),
                    reply_markup=kb_sub_no_sub()
                )
                return

            key = sub.get("issued_key") or ""
            await call.message.answer(
                text_subscription_card(call.from_user, sub),
                reply_markup=kb_after_issue(key)
            )
            return
    finally:
        # ✅ ВСЕГДА гасим "загрузку"
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
                "Просто отправь сюда чек/скрин оплаты 📎"
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
    except Exception as e:
        print("BUY ERROR:", repr(e))
        try:
            await call.message.answer("⚠️ Ошибка при создании заказа. Попробуй ещё раз.")
        except Exception:
            pass
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

        # удаляем сообщение с реквизитами (или хотя бы убираем кнопки)
        try:
            msg_id = order.get("payment_msg_id") or call.message.message_id
            await bot.delete_message(chat_id=user_id, message_id=msg_id)
        except Exception:
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass

        await bot.send_message(user_id, "✅ Заказ отменён. Если нужно — оформи заново через меню.")
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
        await m.answer("⏳ Чек уже отправлен админу. Жди подтверждения.")
        return

    safe_username = username or "—"

    # сначала отправляем админу кнопки (если не отправится — статус не трогаем)
    try:
        await bot.send_message(
            ADMIN_ID,
            "🔔 Чек на проверку\n\n"
            f"🧾 Заказ: #{active['id']}\n"
            f"👤 Пользователь: {user_id} (@{safe_username})\n"
            f"📦 Тариф: {active['plan']}\n"
            f"💰 Сумма: {active['amount']}₽\n\n"
            "Принять оплату?",
            reply_markup=kb_admin(active["id"]),
            parse_mode=None,
        )
    except Exception as e:
        print("ADMIN SEND ERROR:", repr(e))
        await m.answer("⚠️ Не смог отправить чек админу. Попробуй ещё раз через минуту.")
        return

    db_set_status(active["id"], "pending_admin")

    # копия чека админу
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
        f"> {key}\n\n"
        "📲 *Как подключиться (Happ):*\n"
        "1) Скачай Happ\n"
        "2) Открой приложение\n"
        "3) Нажми «Добавить / Import / Подписка»\n"
        "4) Вставь ключ\n\n"
        "Нажми кнопки ниже 👇",
        reply_markup=kb_after_issue(key)
    )


@dp.callback_query(F.data.startswith("admin:"))
async def admin(call: CallbackQuery):
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

        # если уже решён — не даём нажимать повторно
        if order["status"] in ("accepted", "rejected", "cancelled"):
            await call.answer("Уже решено", show_alert=True)
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        # ✅ скрываем кнопки у админа
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        if action == "no":
            db_set_status(order_id, "rejected")
            try:
                await bot.send_message(order["user_id"], "❌ Оплата отклонена. Отправь корректный чек ещё раз.")
            except Exception:
                pass
            await call.answer("Отклонено")
            return

        if action == "ok":
            key = take_key(order["plan"])
            if not key:
                await call.answer("Ключей нет", show_alert=True)
                await bot.send_message(
                    ADMIN_ID,
                    "⚠️ В файлах ключей пусто. Заполни standard_keys.txt / family_keys.txt.",
                    parse_mode=None
                )
                return

            try:
                await send_key_to_user(order["user_id"], order["plan"], key)
            except TelegramForbiddenError:
                await call.answer("Не могу написать юзеру", show_alert=True)
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ Не смог отправить пользователю {order['user_id']}.\n"
                    "Пусть он откроет бота и нажмёт /start, затем попробуй снова.",
                    parse_mode=None
                )
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
            await call.answer("Выдано ✅")
            return
    finally:
        # на всякий — гасим спиннер
        try:
            await call.answer()
        except Exception:
            pass


# ================== COPY KEY BUTTON ==================
@dp.callback_query(F.data == "sub:copy")
async def sub_copy(call: CallbackQuery):
    try:
        sub = db_get_last_accepted(call.from_user.id)
        if not sub or not sub.get("issued_key"):
            await call.answer("Ключ не найден", show_alert=True)
            return

        key = sub["issued_key"]
        # отдельным сообщением, чтобы удобно копировать (в Telegram можно тапнуть и скопировать)
        await call.message.answer(f"📋 Скопируй ключ:\n`{key}`")
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
