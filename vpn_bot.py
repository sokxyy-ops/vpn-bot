import asyncio
import os
import time
import sqlite3
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties

# ====== ENV (Railway Variables) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ID приватной группы (chat_id вида -100xxxxxxxxxx)
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID", "0"))

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

# ====== ЗАКАЗЫ (в памяти) ======
orders = {}
order_seq = 1000

# Антиспам: 1 активный заказ + кулдаун
USER_COOLDOWN_SEC = 60
last_order_time = {}        # user_id -> unix time
active_order_by_user = {}   # user_id -> order_id

# Если повторная покупка и юзер не в группе — ждём вступление
pending_join_check = {}     # user_id -> {"plan": str, "order_id": int}

def is_active_status(status: str) -> bool:
    return status in {"wait_receipt", "pending_admin", "await_join"}

# ====== SQLite: покупатели (чтобы помнить "1-я покупка/повтор") ======
DB_PATH = "buyers.sqlite"

def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS buyers (
            user_id INTEGER PRIMARY KEY,
            first_key_issued_at INTEGER NOT NULL
        )
    """)
    con.commit()
    con.close()

def is_repeat_buyer(user_id: int) -> bool:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT 1 FROM buyers WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    con.close()
    return row is not None

def mark_buyer(user_id: int):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO buyers(user_id, first_key_issued_at) VALUES(?, ?)",
        (user_id, int(time.time()))
    )
    con.commit()
    con.close()

# ====== КЛАВИАТУРЫ ======
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

def kb_after_key_with_connect(subscription: str) -> InlineKeyboardMarkup:
    deeplink = "happ://add/" + subscription
    connect_url = "https://vleska.xyz/?url=" + quote(deeplink, safe=":/?=&%")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться (Happ)", url=connect_url)],
        [InlineKeyboardButton(text="🔒 Приватная группа (обязательно)", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
    ])

def kb_join_required() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Вступить в приватную группу", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="✅ Я вступил — проверить", callback_data="check_join")],
    ])

# ====== КЛЮЧИ ИЗ TXT (НЕ УДАЛЯЕМ) ======
def take_key(plan: str) -> str | None:
    filename = "standard_keys.txt" if plan == "standard" else "family_keys.txt"
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = [x.strip() for x in f.read().splitlines() if x.strip()]
    if not lines:
        return None
    return lines[0]  # всегда первый (не удаляем)

# ====== Проверка членства в приватной группе ======
async def is_member_of_private_group(user_id: int) -> bool:
    if PRIVATE_GROUP_ID == 0:
        # если не настроили — считаем что не можем проверить
        return True
    try:
        member = await bot.get_chat_member(PRIVATE_GROUP_ID, user_id)
        # member.status: "creator", "administrator", "member", "left", "kicked"
        return member.status in ("creator", "administrator", "member")
    except Exception:
        # если бот не в группе/нет прав/не тот ID — проверка не сработает
        return False

# ====== БОТ ======
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown"))
dp = Dispatcher()

# ====== /start /myid ======
@dp.message(CommandStart())
async def start(m: Message):
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

# ====== отмена заказа ======
async def cancel_for_user(user_id: int, notify_admin: bool = True) -> str:
    oid = active_order_by_user.get(user_id)
    if not oid or oid not in orders:
        return "У тебя нет активного заказа."

    st = orders[oid].get("status")
    if not is_active_status(st):
        active_order_by_user.pop(user_id, None)
        pending_join_check.pop(user_id, None)
        return "Активный заказ уже завершён."

    orders[oid]["status"] = "cancelled"
    active_order_by_user.pop(user_id, None)
    pending_join_check.pop(user_id, None)

    if notify_admin:
        try:
            await bot.send_message(ADMIN_ID, f"ℹ️ Пользователь `{user_id}` отменил заказ *#{oid}* (было: *{st}*).")
        except Exception:
            pass

    return f"✅ Заказ *#{oid}* отменён."

@dp.callback_query(F.data == "cancel")
async def cancel_btn(call: CallbackQuery):
    text = await cancel_for_user(call.from_user.id, notify_admin=True)
    await call.message.answer(text, reply_markup=kb_main())
    await call.answer()

@dp.message(Command("cancel"))
async def cancel_cmd(m: Message):
    text = await cancel_for_user(m.from_user.id, notify_admin=True)
    await m.answer(text, reply_markup=kb_main())

# ====== навигация ======
@dp.callback_query(F.data == "back")
async def back(call: CallbackQuery):
    await start(call.message)
    await call.answer()

# ====== тарифы ======
@dp.callback_query(F.data.startswith("plan:"))
async def plan_info(call: CallbackQuery):
    plan = call.data.split(":")[1]
    if plan == "standard":
        text = (
            "🟩 *Стандарт — 200₽ (навсегда)*\n"
            "👤 1 пользователь\n"
            "📱 до 3 устройств\n\n"
            "✅ Обходит белые списки и глушилки\n"
            "🔑 Подписка для Happ после оплаты\n\n"
            "📣 Канал: https://t.me/sokxyybc"
        )
    else:
        text = (
            "🟦 *Семейная — 300₽ (навсегда)*\n"
            "👥 до 8 пользователей\n"
            "📱 у каждого до 3 устройств\n\n"
            "✅ Обходит белые списки и глушилки\n"
            "🔑 Подписка для Happ после оплаты\n\n"
            "📣 Канал: https://t.me/sokxyybc"
        )
    await call.message.answer(text, reply_markup=kb_plan(plan))
    await call.answer()

# ====== реквизиты + создание заказа (антиспам) ======
@dp.callback_query(F.data.startswith("pay:"))
async def pay(call: CallbackQuery):
    global order_seq
    user_id = call.from_user.id
    plan = call.data.split(":")[1]
    amount = 200 if plan == "standard" else 300

    existing_id = active_order_by_user.get(user_id)
    if existing_id and existing_id in orders and is_active_status(orders[existing_id]["status"]):
        st = orders[existing_id]["status"]
        if st == "wait_receipt":
            await call.message.answer(
                f"⏳ У тебя уже есть активный заказ *#{existing_id}*.\n"
                f"Сумма: *{orders[existing_id]['amount']}₽*\n\n"
                f"{PAYMENT_TEXT}\n\n"
                "📎 Отправь чек/скрин сюда в чат."
            )
        else:
            await call.message.answer(
                f"⏳ Заказ *#{existing_id}* уже в обработке.\n"
                "Дождись результата или нажми *Отменить заказ*."
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

    order_seq += 1
    orders[order_seq] = {"user_id": user_id, "plan": plan, "amount": amount, "status": "wait_receipt"}
    active_order_by_user[user_id] = order_seq
    last_order_time[user_id] = now

    await call.message.answer(
        f"🧾 *Заказ #{order_seq}*\n"
        f"Сумма: *{amount}₽*\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст)."
    )
    await call.answer()

# ====== приём чека ======
@dp.message(F.content_type.in_({"photo", "document", "text"}))
async def receipt(m: Message):
    user_id = m.from_user.id
    oid = active_order_by_user.get(user_id)
    if not oid or oid not in orders:
        return

    st = orders[oid].get("status")
    if not is_active_status(st):
        return

    if st == "pending_admin":
        await m.answer("⏳ Твой чек уже отправлен админу. Дождись подтверждения.")
        return

    if st == "await_join":
        await m.answer("⏳ Ожидается вступление в приватную группу. Нажми «✅ Я вступил — проверить».")
        return

    orders[oid]["status"] = "pending_admin"
    plan = orders[oid]["plan"]
    amount = orders[oid]["amount"]

    await bot.send_message(
        ADMIN_ID,
        "🔔 *Чек на проверку*\n"
        f"Заказ: *#{oid}*\n"
        f"Пользователь: `{m.from_user.id}` (@{m.from_user.username or '—'})\n"
        f"Сумма: *{amount}₽*\n\n"
        "Принять оплату?",
        reply_markup=kb_admin(oid, plan, m.from_user.id)
    )
    try:
        await m.forward(ADMIN_ID)
    except Exception:
        pass

    await m.answer("✅ Чек отправлен админу. Жди подтверждения.")

# ====== админ решение ======
@dp.callback_query(F.data.startswith("admin:"))
async def admin_decide(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Не админ", show_alert=True)
        return

    _, act, oid, plan, user_id = call.data.split(":")
    oid = int(oid)
    user_id = int(user_id)

    if oid not in orders or orders[oid]["status"] != "pending_admin":
        await call.answer("Заказ уже обработан/отменён", show_alert=True)
        return

    if act == "ok":
        key = take_key(plan)
        if not key:
            await call.answer("Ключи не найдены", show_alert=True)
            await bot.send_message(ADMIN_ID, "⚠️ В файле ключей нет строк. Заполни standard_keys.txt / family_keys.txt.")
            return

        # повторная покупка? тогда проверяем приватную группу
        repeat = is_repeat_buyer(user_id)
        if repeat:
            ok_member = await is_member_of_private_group(user_id)
            if not ok_member:
                orders[oid]["status"] = "await_join"
                pending_join_check[user_id] = {"plan": plan, "order_id": oid}

                await bot.send_message(
                    user_id,
                    "🔒 *Перед выдачей подписки нужно вступить в приватную группу.*\n"
                    "Без вступления обслуживания нет.\n\n"
                    "Вступи и нажми кнопку «✅ Я вступил — проверить».",
                    reply_markup=kb_join_required()
                )

                await call.message.edit_text(call.message.text + "\n\n⏳ Повторная покупка: ждём вступление в группу.")
                await call.answer("Ждём вступление")
                return

        # 1-я покупка или уже состоит в группе -> выдаём
        orders[oid]["status"] = "accepted"
        active_order_by_user.pop(user_id, None)
        pending_join_check.pop(user_id, None)

        # отмечаем, что у пользователя уже была 1-я покупка (после первой выдачи)
        mark_buyer(user_id)

        subscription = key
        await bot.send_message(
            user_id,
            "✅ *Оплата подтверждена!*\n\n"
            "🔑 Твоя подписка:\n"
            f"`{subscription}`\n\n"
            "Нажми кнопку ниже — откроется *Happ* и подписка добавится автоматически.\n\n"
            "🔒 *Важно:* без вступления в приватную группу обслуживания нет.\n"
            "⭐ Буду благодарен за отзыв.",
            reply_markup=kb_after_key_with_connect(subscription)
        )

        await call.message.edit_text(call.message.text + "\n\n✅ Принято. Подписка выдана.")
        await call.answer("Выдано")

    else:
        orders[oid]["status"] = "rejected"
        active_order_by_user.pop(user_id, None)
        pending_join_check.pop(user_id, None)

        await bot.send_message(
            user_id,
            "❌ *Оплата не подтверждена.*\n"
            "Проверь сумму/чек и отправь корректный чек ещё раз."
        )
        await call.message.edit_text(call.message.text + "\n\n❌ Отклонено.")
        await call.answer("Отклонено")

# ====== Проверка вступления (кнопка) ======
@dp.callback_query(F.data == "check_join")
async def check_join(call: CallbackQuery):
    user_id = call.from_user.id
    info = pending_join_check.get(user_id)
    if not info:
        await call.answer("Нет ожидающей проверки", show_alert=True)
        return

    ok_member = await is_member_of_private_group(user_id)
    if not ok_member:
        await call.answer("Ты ещё не в группе", show_alert=True)
        return

    plan = info["plan"]
    oid = info["order_id"]

    key = take_key(plan)
    if not key:
        await call.answer("Ключи не найдены", show_alert=True)
        return

    # выдаём
    orders[oid]["status"] = "accepted"
    active_order_by_user.pop(user_id, None)
    pending_join_check.pop(user_id, None)

    mark_buyer(user_id)

    subscription = key
    await call.message.answer(
        "✅ *Проверка пройдена!*\n\n"
        "🔑 Твоя подписка:\n"
        f"`{subscription}`\n\n"
        "Нажми кнопку ниже — откроется *Happ* и подписка добавится автоматически.\n\n"
        "⭐ Буду благодарен за отзыв.",
        reply_markup=kb_after_key_with_connect(subscription)
    )
    await call.answer("Готово")

# ====== запуск ======
@dp.message(Command("chatid"))
async def chatid(m: Message):
    await m.answer(f"chat_id: {m.chat.id}\nтип: {m.chat.type}")
async def main():
    
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set (Railway Variables -> BOT_TOKEN)")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set (Railway Variables -> ADMIN_ID)")
    db_init()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
