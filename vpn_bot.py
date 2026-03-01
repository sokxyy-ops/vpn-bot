import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================== ENV ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is empty. Set BOT_TOKEN env var.")
if ADMIN_ID == 0:
    raise RuntimeError("ADMIN_ID is empty/0. Set ADMIN_ID env var.")

# ================== SETTINGS ==================
# Канал для проверки подписки (через @username)
CHANNEL_USERNAME = "@sokxyybc"  # <- канал (публичный)

# Ссылки
TG_CHANNEL_LINK = "https://t.me/sokxyybc"
PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"  # просто выдаём после подтверждения оплаты
REVIEW_LINK = "https://t.me/sokxyybc/23"

ADMIN_USERNAME = "whyshawello"  # без @

# Текст оплаты
PAYMENT_TEXT = (
    "💳 *Реквизиты для оплаты*\n\n"
    "• Сумма: *200₽* (стандарт) / *300₽* (семейный)\n"
    "• После оплаты нажми кнопку *«Я оплатил(а)»* и отправь чек/скрин.\n\n"
    "✅ После подтверждения админом ты получишь доступ."
)

# ================== MEMORY (простая) ==================
# В проде лучше БД (sqlite/postgres), но тут "с нуля" — сделаем минимально.
pending_payments = {}  # user_id -> {"tier": "standard/family", "username": "@name"}


# ================== KEYBOARDS ==================
def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Купить", callback_data="buy")
    kb.button(text="📌 Канал", url=TG_CHANNEL_LINK)
    kb.button(text="⭐ Отзывы", url=REVIEW_LINK)
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.adjust(2, 2)
    return kb.as_markup()


def buy_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Стандарт 200₽", callback_data="pay:standard")
    kb.button(text="👨‍👩‍👧‍👦 Семейный 300₽", callback_data="pay:family")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def payment_kb(tier: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="📨 Я оплатил(а)", callback_data=f"paid:{tier}")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1, 1)
    return kb.as_markup()


def need_sub_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📌 Подписаться на канал", url=TG_CHANNEL_LINK)
    kb.button(text="🔄 Проверить подписку", callback_data="check_sub")
    kb.adjust(1, 1)
    return kb.as_markup()


def admin_pay_kb(user_id: int, tier: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"admin_ok:{user_id}:{tier}")
    kb.button(text="❌ Отклонить", callback_data=f"admin_no:{user_id}:{tier}")
    kb.adjust(2)
    return kb.as_markup()


# ================== HELPERS ==================
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """
    Проверяем подписку пользователя на канал.
    Важно: бот должен быть админом в канале, чтобы стабильнее видеть статус.
    """
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        # member.status: "creator", "administrator", "member", "restricted", "left", "kicked"
        return member.status in ("creator", "administrator", "member")
    except Exception:
        # если бот не админ / канал недоступен / юзер скрыт и т.п.
        return False


async def send_main(message: Message):
    text = (
        "👋 *Привет!*\n\n"
        "Здесь можно купить доступ.\n"
        "Чтобы продолжить — выбери действие ниже."
    )
    await message.answer(text, reply_markup=main_kb())


async def send_main_edit(call: CallbackQuery):
    text = (
        "👋 *Привет!*\n\n"
        "Здесь можно купить доступ.\n"
        "Чтобы продолжить — выбери действие ниже."
    )
    await call.message.edit_text(text, reply_markup=main_kb())
    await call.answer()


# ================== HANDLERS ==================
async def start_handler(message: Message):
    await send_main(message)


async def menu_handler(call: CallbackQuery):
    await send_main_edit(call)


async def buy_handler(call: CallbackQuery):
    text = (
        "🛒 *Выбери тариф*\n\n"
        "• Стандарт — *200₽*\n"
        "• Семейный — *300₽*"
    )
    await call.message.edit_text(text, reply_markup=buy_kb())
    await call.answer()


async def pay_handler(call: CallbackQuery):
    _, tier = call.data.split(":", 1)
    tier_name = "Стандарт 200₽" if tier == "standard" else "Семейный 300₽"

    text = f"💰 *Оплата — {tier_name}*\n\n{PAYMENT_TEXT}"
    await call.message.edit_text(text, reply_markup=payment_kb(tier))
    await call.answer()


async def support_handler(call: CallbackQuery, bot: Bot):
    text = (
        "🆘 *Поддержка*\n\n"
        f"Напиши админу: @{ADMIN_USERNAME}\n\n"
        "Или просто отправь сюда сообщение — я перешлю админу."
    )
    await call.message.edit_text(text, reply_markup=InlineKeyboardBuilder()
                                .add(InlineKeyboardBuilder().button(text="⬅️ Назад", callback_data="back").buttons[0])
                                .as_markup())
    await call.answer()


async def paid_handler(call: CallbackQuery, bot: Bot):
    _, tier = call.data.split(":", 1)

    # 1) Проверяем подписку на канал
    ok = await is_subscribed(bot, call.from_user.id)
    if not ok:
        await call.message.edit_text(
            "❗ Чтобы продолжить, подпишись на канал и нажми *«Проверить подписку»*.",
            reply_markup=need_sub_kb()
        )
        await call.answer()
        return

    # 2) Просим отправить чек/скрин (следующее сообщение)
    pending_payments[call.from_user.id] = {
        "tier": tier,
        "username": f"@{call.from_user.username}" if call.from_user.username else "(без username)"
    }

    tier_name = "Стандарт 200₽" if tier == "standard" else "Семейный 300₽"

    await call.message.edit_text(
        "✅ Подписка на канал подтверждена.\n\n"
        f"Теперь отправь *чек/скрин оплаты* сюда одним сообщением.\n"
        f"Тариф: *{tier_name}*",
        reply_markup=InlineKeyboardBuilder()
            .button(text="⬅️ Назад", callback_data="back")
            .as_markup()
    )
    await call.answer()


async def check_sub_handler(call: CallbackQuery, bot: Bot):
    ok = await is_subscribed(bot, call.from_user.id)
    if ok:
        await call.message.edit_text(
            "✅ Подписка найдена! Теперь вернись к оплате и нажми *«Я оплатил(а)»*.",
            reply_markup=InlineKeyboardBuilder()
                .button(text="🛒 Купить", callback_data="buy")
                .button(text="⬅️ Назад", callback_data="back")
                .adjust(1, 1)
                .as_markup()
        )
    else:
        await call.answer("Подписка пока не найдена. Проверь, что ты подписался(лась) 🙂", show_alert=True)


async def any_message_handler(message: Message, bot: Bot):
    """
    1) Если юзер в процессе "поддержки" — пересылаем админу.
    2) Если юзер нажал "Я оплатил" и мы ждём чек — принимаем чек и кидаем админу на подтверждение.
    """
    user_id = message.from_user.id

    # Если ждём чек
    if user_id in pending_payments:
        data = pending_payments[user_id]
        tier = data["tier"]
        tier_name = "Стандарт 200₽" if tier == "standard" else "Семейный 300₽"

        caption = (
            "🧾 *Новая заявка на подтверждение оплаты*\n\n"
            f"👤 Пользователь: {data['username']} (id: `{user_id}`)\n"
            f"📦 Тариф: *{tier_name}*\n"
        )

        # Отправляем админу: пересылаем сам контент (фото/видео/док/текст)
        try:
            # Сначала отправим описание
            await bot.send_message(ADMIN_ID, caption)

            # Затем сам чек
            if message.photo:
                await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption="(чек)")
            elif message.document:
                await bot.send_document(ADMIN_ID, message.document.file_id, caption="(чек)")
            elif message.video:
                await bot.send_video(ADMIN_ID, message.video.file_id, caption="(чек)")
            elif message.text:
                await bot.send_message(ADMIN_ID, f"(чек текстом)\n\n{message.text}")
            else:
                await bot.send_message(ADMIN_ID, "(пользователь отправил чек неизвестным типом сообщения)")

            # Кнопки админского решения
            await bot.send_message(
                ADMIN_ID,
                "Подтвердить оплату?",
                reply_markup=admin_pay_kb(user_id, tier)
            )

            await message.answer(
                "✅ Чек отправлен админу. Ожидай подтверждение.\n"
                "Как только админ подтвердит — я пришлю доступ."
            )
        except Exception as e:
            await message.answer("❗ Не смог отправить админу. Попробуй ещё раз чуть позже.")
        return

    # Иначе — просто поддержка: пересылаем админу всё, что написали
    try:
        username = f"@{message.from_user.username}" if message.from_user.username else "(без username)"
        header = f"🆘 Сообщение в поддержку от {username} (id: {user_id})"
        await bot.send_message(ADMIN_ID, header)

        if message.photo:
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption="(вложение)")
        elif message.document:
            await bot.send_document(ADMIN_ID, message.document.file_id, caption="(вложение)")
        elif message.video:
            await bot.send_video(ADMIN_ID, message.video.file_id, caption="(вложение)")
        elif message.text:
            await bot.send_message(ADMIN_ID, message.text)
        else:
            await bot.send_message(ADMIN_ID, "(сообщение неизвестного типа)")

        await message.answer("✅ Передал админу. Ответят в ближайшее время.")
    except Exception:
        await message.answer("❗ Не смог отправить админу. Попробуй позже.")


async def admin_ok_handler(call: CallbackQuery, bot: Bot):
    # admin_ok:user_id:tier
    _, user_id_str, tier = call.data.split(":", 2)
    user_id = int(user_id_str)

    # убираем из ожидания, если там есть
    pending_payments.pop(user_id, None)

    tier_name = "Стандарт 200₽" if tier == "standard" else "Семейный 300₽"

    # выдача доступа (просто ссылка)
    try:
        await bot.send_message(
            user_id,
            "✅ *Оплата подтверждена!*\n\n"
            f"Тариф: *{tier_name}*\n\n"
            f"🔗 Вот ссылка на доступ:\n{PRIVATE_GROUP_LINK}\n\n"
            "Если ссылка не открывается — напиши в поддержку."
        )
        await call.message.edit_text("✅ Подтверждено. Пользователю отправлен доступ.")
    except Exception:
        await call.message.edit_text("❗ Не смог отправить пользователю сообщение (возможно, он не писал боту).")
    await call.answer()


async def admin_no_handler(call: CallbackQuery, bot: Bot):
    _, user_id_str, tier = call.data.split(":", 2)
    user_id = int(user_id_str)

    pending_payments.pop(user_id, None)

    try:
        await bot.send_message(
            user_id,
            "❌ *Оплата отклонена.*\n\n"
            "Возможно, чек не читается или оплата не пришла.\n"
            "Попробуй отправить чек ещё раз или напиши в поддержку."
        )
        await call.message.edit_text("❌ Отклонено. Пользователю отправлено уведомление.")
    except Exception:
        await call.message.edit_text("❗ Не смог отправить пользователю сообщение.")
    await call.answer()


# ================== MAIN ==================
async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher()

    dp.message.register(start_handler, CommandStart())

    dp.callback_query.register(menu_handler, F.data == "back")
    dp.callback_query.register(buy_handler, F.data == "buy")
    dp.callback_query.register(pay_handler, F.data.startswith("pay:"))
    dp.callback_query.register(paid_handler, F.data.startswith("paid:"))
    dp.callback_query.register(support_handler, F.data == "support")
    dp.callback_query.register(check_sub_handler, F.data == "check_sub")

    dp.callback_query.register(admin_ok_handler, F.data.startswith("admin_ok:"))
    dp.callback_query.register(admin_no_handler, F.data.startswith("admin_no:"))

    # Любые сообщения: чек или поддержка
    dp.message.register(any_message_handler)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
