import asyncio
import os
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
# ====== ENV (Railway Variables) ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
# ====== LINKS / SETTINGS ======
TG_CHANNEL = "https://t.me/sokxyybc"
ADMIN_USERNAME = "whyshawello" # без @
PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"
REVIEW_LINK = "https://t.me/sokxyybc/23"
PAYMENT_TEXT = (
    "💳 *Реквизиты для оплаты*\n\n"
    "✅ *Основной способ (карта):*\n"
    "Номер карты: 2204320913014587\n\n"
    "🔁 *Если есть комиссия — переводи на Ozon по номеру:*\n"
    "Номер: +79951253391\n\n"
    "📎 После оплаты отправь сюда *чек/скрин*.\n"
    "Админ подтвердит — бот выдаст ключ."
)
# ====== ЗАКАЗЫ (в памяти) ======
orders = {}
order_seq = 1000
# Антиспам: 1 активный заказ + кулдаун
USER_COOLDOWN_SEC = 60
last_order_time = {} # user_id -> unix time
active_order_by_user = {} # user_id -> order_id
def is_active_status(status: str) -> bool:
    return status in {"wait_receipt", "pending_admin"}
# ====== КЛАВИАТУРЫ ======
def kb_after_key() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Вступить в приватную группу", url=PRIVATE_GROUP_LINK)],
        [InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_LINK)],
    ])
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
# ====== КЛЮЧИ ИЗ TXT (НЕ УДАЛЯЕМ) ======
def take_key(plan: str) -> str | None:
    filename = "standard_keys.txt" if plan == "standard" else "family_keys.txt"
    if not os.path.exists(filename):
        return None
    with open(filename, "r", encoding="utf-8") as f:
        lines = [x.strip() for x in f.read().splitlines() if x.strip()]
    if not lines:
        return None
    # ✅ не удаляем, всегда выдаём первый ключ
    return lines[0]
# ====== БОТ ======
bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher()
# ====== /start /myid ======
@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "⚡ *Sokxyy Обход — VPN навсегда*\n\n"
        "✅ *Обе подписки:* обходят белые списки, глушилки, обычные vpn\n"
        "🔑 После покупки выдаётся ключ для *Happ* клиента\n\n"
        "Выбери подписку 👇",
        reply_markup=kb_main()
    )
@dp.message(Command("myid"))
async def myid(m: Message):
    await m.answer(f"Твой ID: {m.from_user.id}")
# ====== отмена заказа (кнопка + /cancel) ======
async def cancel_for_user(user_id: int, notify_admin: bool = True) -> str:
    oid = active_order_by_user.get(user_id)
    if not oid or oid not in orders:
        return "У тебя нет активного заказа."
    st = orders[oid].get("status")
    if not is_active_status(st):
        active_order_by_user.pop(user_id, None)
        return "Активный заказ уже завершён."
    orders[oid]["status"] = "cancelled"
    active_order_by_user.pop(user_id, None)
    if notify_admin:
        try:
            await bot.send_message(ADMIN_ID, f"ℹ️ Пользователь {user_id} отменил заказ *#{oid}* (было: *{st}*).")
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
            "✅ Обходит глушилки,+ vpn\n"
            "🔑 Ключ для Happ после подтверждения оплаты\n\n"
            "📣 Канал: https://t.me/sokxyybc"
        )
    else:
        text = (
            "🟦 *Семейная — 300₽ (навсегда)*\n"
            "👥 до 8 пользователей\n"
            "📱 у каждого до 3 устройств\n\n"
            "✅ Обходит глушилки,+vpn\n"
            "🔑 Ключ для Happ после подтверждения оплаты\n\n"
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
    # 1) если уже есть активный заказ — не создаём новый
    existing_id = active_order_by_user.get(user_id)
    if existing_id and existing_id in orders and is_active_status(orders[existing_id]["status"]):
        st = orders[existing_id]["status"]
        if st == "wait_receipt":
            await call.message.answer(
                f"⏳ У тебя уже есть активный заказ *#{existing_id}*.\n"
                f"Сумма: *{orders[existing_id]['amount']}₽*\n\n"
                f"{PAYMENT_TEXT}\n\n"
                "📎 Отправь чек/скрин сюда в чат.\n"
                "Если передумал — нажми *Отменить заказ*."
            )
        else:
            await call.message.answer(
                f"⏳ Заказ *#{existing_id}* уже отправлен админу на проверку.\n"
                "Дождись подтверждения.\n"
                "Если передумал — нажми *Отменить заказ*."
            )
        await call.answer()
        return
    # 2) кулдаун
    now = int(time.time())
    last = last_order_time.get(user_id, 0)
    left = USER_COOLDOWN_SEC - (now - last)
    if left > 0:
        await call.message.answer(f"⛔ Подожди *{left} сек* и попробуй снова.")
        await call.answer()
        return
    # 3) создаём заказ
    order_seq += 1
    orders[order_seq] = {"user_id": user_id, "plan": plan, "amount": amount, "status": "wait_receipt"}
    active_order_by_user[user_id] = order_seq
    last_order_time[user_id] = now
    await call.message.answer(
        f"🧾 *Заказ #{order_seq}*\n"
        f"Сумма: *{amount}₽*\n\n"
        f"{PAYMENT_TEXT}\n\n"
        "📎 *Отправь чек/скрин сюда в чат* (фото/файл/текст).\n"
        "Если передумал — нажми *Отменить заказ*."
    )
    await call.answer()
# ====== приём чека (без дублей админу) ======
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
    orders[oid]["status"] = "pending_admin"
    plan = orders[oid]["plan"]
    amount = orders[oid]["amount"]
    await bot.send_message(
        ADMIN_ID,
        "🔔 *Чек на проверку*\n"
        f"Заказ: *#{oid}*\n"
        f"Пользователь: {m.from_user.id} (@{m.from_user.username or '—'})\n"
        f"Сумма: *{amount}₽*\n\n"
        "Принять оплату?",
        reply_markup=kb_admin(oid, plan, m.from_user.id)
    )
    try:
        await m.forward(ADMIN_ID)
    except Exception:
        pass
    await m.answer("✅ Чек отправлен админу. Жди подтверждения.")
# ====== решение админа ======
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
            await bot.send_message(ADMIN_ID, "⚠️ В файле ключей нет строк. Добавь ключи в standard_keys.txt / family_keys.txt")
            return
        orders[oid]["status"] = "accepted"
        active_order_by_user.pop(user_id, None)
        await bot.send_message(
            user_id,
            "✅ *Оплата подтверждена!*\n"
            "Твой ключ:\n"
            f"{key}\n\n"
            "📌 *Happ:* Add/Import → вставь ключ → Connect\n\n"
            "🔒 *Обязательно:* вступи в приватную группу — без неё обслуживания нет.\n"
            "⭐ Буду благодарен за отзыв.",
            reply_markup=kb_after_key()
        )
        await call.message.edit_text(call.message.text + "\n\n✅ Принято. Ключ выдан.")
        await call.answer("Выдано")
    else:
        orders[oid]["status"] = "rejected"
        active_order_by_user.pop(user_id, None)
        await bot.send_message(
            user_id,
            "❌ *Оплата не подтверждена.*\n"
            "Проверь сумму/чек и отправь корректный чек ещё раз."
        )
        await call.message.edit_text(call.message.text + "\n\n❌ Отклонено.")
        await call.answer("Отклонено")
# ====== запуск ======
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set (Railway Variables -> BOT_TOKEN)")
    if ADMIN_ID == 0:
        raise RuntimeError("ADMIN_ID is not set (Railway Variables -> ADMIN_ID)")
    await dp.start_polling(bot)
if **name** == "**main**":
    asyncio.run(main())
