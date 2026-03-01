import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"

pending_payments = {}

# ---------- КНОПКИ ----------

def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Купить", callback_data="buy")
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.adjust(1)
    return kb.as_markup()

def buy_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Стандарт 200₽", callback_data="pay:200")
    kb.button(text="👨‍👩‍👧 Семейный 300₽", callback_data="pay:300")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1)
    return kb.as_markup()

def paid_kb(price):
    kb = InlineKeyboardBuilder()
    kb.button(text="📨 Я оплатил", callback_data=f"paid:{price}")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1)
    return kb.as_markup()

def admin_kb(user_id, price):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"ok:{user_id}:{price}")
    kb.button(text="❌ Отклонить", callback_data=f"no:{user_id}:{price}")
    kb.adjust(2)
    return kb.as_markup()

# ---------- ХЕНДЛЕРЫ ----------

async def start(message: Message):
    await message.answer("👋 Добро пожаловать", reply_markup=main_kb())

async def back(call: CallbackQuery):
    await call.message.edit_text("👋 Добро пожаловать", reply_markup=main_kb())
    await call.answer()

async def buy(call: CallbackQuery):
    await call.message.edit_text("Выбери тариф:", reply_markup=buy_kb())
    await call.answer()

async def pay(call: CallbackQuery):
    price = call.data.split(":")[1]
    await call.message.edit_text(
        f"💳 Оплати {price}₽ и нажми «Я оплатил»",
        reply_markup=paid_kb(price)
    )
    await call.answer()

async def paid(call: CallbackQuery):
    price = call.data.split(":")[1]

    pending_payments[call.from_user.id] = price

    await call.message.edit_text(
        "📸 Теперь отправь чек одним сообщением."
    )
    await call.answer()

async def handle_message(message: Message, bot: Bot):
    user_id = message.from_user.id

    if user_id not in pending_payments:
        return

    price = pending_payments[user_id]

    await bot.send_message(
        ADMIN_ID,
        f"🧾 Новый чек\n\n"
        f"👤 @{message.from_user.username}\n"
        f"ID: {user_id}\n"
        f"💰 Сумма: {price}₽"
    )

    # отправляем сам чек
    if message.photo:
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id)
    elif message.document:
        await bot.send_document(ADMIN_ID, message.document.file_id)
    elif message.text:
        await bot.send_message(ADMIN_ID, message.text)

    await bot.send_message(
        ADMIN_ID,
        "Подтвердить оплату?",
        reply_markup=admin_kb(user_id, price)
    )

    await message.answer("✅ Чек отправлен админу. Ожидай подтверждение.")

async def admin_ok(call: CallbackQuery, bot: Bot):
    _, user_id, price = call.data.split(":")
    user_id = int(user_id)

    pending_payments.pop(user_id, None)

    await bot.send_message(
        user_id,
        f"✅ Оплата {price}₽ подтверждена!\n\n"
        f"Вот доступ:\n{PRIVATE_GROUP_LINK}"
    )

    await call.message.edit_text("✅ Подтверждено")
    await call.answer()

async def admin_no(call: CallbackQuery, bot: Bot):
    _, user_id, price = call.data.split(":")
    user_id = int(user_id)

    pending_payments.pop(user_id, None)

    await bot.send_message(
        user_id,
        "❌ Оплата отклонена. Свяжись с поддержкой."
    )

    await call.message.edit_text("❌ Отклонено")
    await call.answer()

# ---------- ЗАПУСК ----------

async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.register(start, CommandStart())
    dp.callback_query.register(back, F.data == "back")
    dp.callback_query.register(buy, F.data == "buy")
    dp.callback_query.register(pay, F.data.startswith("pay:"))
    dp.callback_query.register(paid, F.data.startswith("paid:"))
    dp.callback_query.register(admin_ok, F.data.startswith("ok:"))
    dp.callback_query.register(admin_no, F.data.startswith("no:"))
    dp.message.register(handle_message)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
