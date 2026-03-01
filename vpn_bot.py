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
    raise RuntimeError("BOT_TOKEN env is empty")
if ADMIN_ID == 0:
    raise RuntimeError("ADMIN_ID env is empty/0")

# ================== BRAND / LINKS ==================
VPN_NAME = "SOKXYYBC VPN"
PRIVATE_GROUP_LINK = "https://t.me/+T7CkE9me-ohkYWNi"  # доступ навсегда (после подтверждения)

# ================== PAYMENT ==================
# ВСТАВЬ СВОИ РЕКВИЗИТЫ СЮДА:
PAYMENT_DETAILS = (
    "💳 <b>Реквизиты для оплаты</b>\n\n"
    "Перевод: <b>СБП / Карта</b>\n"
    "Номер/телефон: <b>+7 XXX XXX-XX-XX</b>\n"
    "Банк: <b>Тинькофф</b>\n\n"
    "📝 Комментарий к переводу: <b>без комментариев</b>\n"
)

# ================== SUBSCRIPTIONS ==================
# (Как ты написал)
PLANS = {
    "standard": {
        "title": "Стандарт",
        "price": "200",
        "users": "1 пользователь",
        "devices": "по 3 устройства",
        "note": "Доступ навсегда",
    },
    "family": {
        "title": "Семейная",
        "price": "300",
        "users": "8 пользователей",
        "devices": "по 3 устройства",
        "note": "Доступ навсегда",
    },
}

# ================== STATE (simple memory) ==================
# user_id -> {"plan": "...", "price": "..."}
waiting_check = {}

# ================== TEXTS ==================
START_TEXT = (
    f"🔥 <b>{VPN_NAME}</b>\n\n"
    "🚀 <b>VPN с обходом глушилок</b> — когда режут скорость/душат интернет или мешают подключению.\n"
    "🛡 Также работает как <b>обычный VPN</b>: приватность + доступ к сайтам.\n\n"
    "✅ <b>Выдача навсегда</b> после подтверждения оплаты.\n\n"
    "Выбери действие:"
)

SUPPORT_TEXT = (
    "🆘 <b>Поддержка</b>\n\n"
    "Напиши сюда сообщение — я перешлю админу."
)

def plan_text(plan_key: str) -> str:
    p = PLANS[plan_key]
    return (
        f"📦 <b>{p['title']}</b>\n"
        f"👥 {p['users']} / {p['devices']}\n"
        f"♾ {p['note']}\n"
        f"💰 <b>{p['price']}₽</b>"
    )

def payment_text(plan_key: str) -> str:
    p = PLANS[plan_key]
    return (
        f"💳 <b>Оплата: {p['title']}</b>\n\n"
        f"{plan_text(plan_key)}\n\n"
        f"{PAYMENT_DETAILS}\n"
        "📸 <b>После оплаты</b> нажми «Я оплатил(а)» и <b>скинь чек</b> одним сообщением."
    )

# ================== KEYBOARDS ==================
def main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Купить", callback_data="buy")
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.adjust(1, 1)
    return kb.as_markup()

def back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1)
    return kb.as_markup()

def buy_kb():
    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"✅ {PLANS['standard']['title']} — {PLANS['standard']['price']}₽",
        callback_data="choose:standard"
    )
    kb.button(
        text=f"👨‍👩‍👧‍👦 {PLANS['family']['title']} — {PLANS['family']['price']}₽",
        callback_data="choose:family"
    )
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def paid_kb(plan_key: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="📨 Я оплатил(а)", callback_data=f"paid:{plan_key}")
    kb.button(text="⬅️ Назад", callback_data="back")
    kb.adjust(1, 1)
    return kb.as_markup()

def admin_decision_kb(user_id: int, plan_key: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"admin_ok:{user_id}:{plan_key}")
    kb.button(text="❌ Отклонить", callback_data=f"admin_no:{user_id}:{plan_key}")
    kb.adjust(2)
    return kb.as_markup()

# ================== HELPERS ==================
def user_tag(u) -> str:
    if u.username:
        return f"@{u.username}"
    return u.full_name

# ================== USER FLOW ==================
async def cmd_start(message: Message):
    await message.answer(START_TEXT, reply_markup=main_kb())

async def cb_back(call: CallbackQuery):
    await call.message.edit_text(START_TEXT, reply_markup=main_kb())
    await call.answer()

async def cb_support(call: CallbackQuery):
    await call.message.edit_text(SUPPORT_TEXT, reply_markup=back_kb())
    await call.answer()

async def cb_buy(call: CallbackQuery):
    text = (
        "🛒 <b>Выбор подписки</b>\n\n"
        f"• {plan_text('standard')}\n\n"
        f"• {plan_text('family')}\n\n"
        "Выбери вариант:"
    )
    await call.message.edit_text(text, reply_markup=buy_kb())
    await call.answer()

async def cb_choose(call: CallbackQuery):
    # choose:plan
    _, plan_key = call.data.split(":", 1)
    await call.message.edit_text(payment_text(plan_key), reply_markup=paid_kb(plan_key))
    await call.answer()

async def cb_paid(call: CallbackQuery):
    # paid:plan
    _, plan_key = call.data.split(":", 1)
    waiting_check[call.from_user.id] = {"plan": plan_key, "price": PLANS[plan_key]["price"]}

    await call.message.edit_text(
        "📸 Ок, теперь отправь <b>чек</b> (фото/скрин/файл/текст) одним сообщением.\n\n"
        "После этого админ подтвердит оплату.",
        reply_markup=back_kb()
    )
    await call.answer()

# ================== MESSAGES: чек / поддержка ==================
async def handle_any_message(message: Message, bot: Bot):
    uid = message.from_user.id

    # 1) Если ждём чек — это чек
    if uid in waiting_check:
        data = waiting_check[uid]
        plan_key = data["plan"]
        p = PLANS[plan_key]

        header = (
            "🧾 <b>Новый чек</b>\n"
            f"👤 Пользователь: <b>{user_tag(message.from_user)}</b>\n"
            f"🆔 ID: <code>{uid}</code>\n"
            f"📦 Подписка: <b>{p['title']}</b> ({p['users']} / {p['devices']})\n"
            f"♾ Доступ: <b>навсегда</b>\n"
            f"💰 Сумма: <b>{p['price']}₽</b>\n\n"
            "Выбери действие:"
        )

        kb = admin_decision_kb(uid, plan_key)

        try:
            # ЧЕК + КНОПКИ В ОДНОМ СООБЩЕНИИ (чтобы не пропадали)
            if message.photo:
                await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=header, reply_markup=kb)
            elif message.document:
                await bot.send_document(ADMIN_ID, message.document.file_id, caption=header, reply_markup=kb)
            elif message.video:
                await bot.send_video(ADMIN_ID, message.video.file_id, caption=header, reply_markup=kb)
            elif message.text:
                await bot.send_message(
                    ADMIN_ID,
                    f"{header}\n\n📝 Текст чека:\n<blockquote>{message.text}</blockquote>",
                    reply_markup=kb
                )
            else:
                await bot.send_message(ADMIN_ID, header + "\n\n(чек неизвестного типа)", reply_markup=kb)

            await message.answer("✅ Чек отправлен админу. Ожидай подтверждение.")
            return
        except Exception:
            await message.answer("❗ Не получилось отправить админу. Попробуй ещё раз.")
            return

    # 2) Иначе — поддержка: пересылаем админу
    try:
        await bot.send_message(
            ADMIN_ID,
            "🆘 <b>Поддержка</b>\n"
            f"От: <b>{user_tag(message.from_user)}</b>\n"
            f"ID: <code>{uid}</code>"
        )

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

        await message.answer("✅ Передал админу. Ответят скоро.")
    except Exception:
        await message.answer("❗ Не смог переслать админу. Попробуй позже.")

# ================== ADMIN ACTIONS ==================
async def admin_ok(call: CallbackQuery, bot: Bot):
    # admin_ok:user_id:plan
    _, user_id_s, plan_key = call.data.split(":", 2)
    user_id = int(user_id_s)
    p = PLANS[plan_key]

    waiting_check.pop(user_id, None)

    # выдаём "навсегда"
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"🔥 <b>{VPN_NAME}</b>\n"
            f"📦 Подписка: <b>{p['title']}</b> ({p['users']} / {p['devices']})\n"
            f"♾ Доступ: <b>навсегда</b>\n\n"
            f"🔗 <b>Твой доступ:</b>\n{PRIVATE_GROUP_LINK}\n\n"
            "Если ссылка не открывается — напиши в поддержку."
        )

        # пометка для админа (и для фото/дока caption, и для текстового)
        if call.message.caption is not None:
            await call.message.edit_caption((call.message.caption or "") + "\n\n✅ <b>ПРИНЯТО</b>")
        else:
            await call.message.edit_text("✅ ПРИНЯТО")
    except Exception:
        try:
            await call.message.edit_text("✅ Принято, но не смог написать пользователю (возможно, он не запускал бота).")
        except Exception:
            pass

    await call.answer("OK")

async def admin_no(call: CallbackQuery, bot: Bot):
    # admin_no:user_id:plan
    _, user_id_s, plan_key = call.data.split(":", 2)
    user_id = int(user_id_s)

    waiting_check.pop(user_id, None)

    try:
        await bot.send_message(
            user_id,
            "❌ <b>Оплата отклонена</b>\n\n"
            "Чек не читается или оплата не пришла.\n"
            "Отправь чек ещё раз или напиши в поддержку."
        )

        if call.message.caption is not None:
            await call.message.edit_caption((call.message.caption or "") + "\n\n❌ <b>ОТКЛОНЕНО</b>")
        else:
            await call.message.edit_text("❌ ОТКЛОНЕНО")
    except Exception:
        try:
            await call.message.edit_text("❌ Отклонено (не смог написать пользователю).")
        except Exception:
            pass

    await call.answer("NO")

# ================== RUN ==================
async def main():
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.message.register(cmd_start, CommandStart())

    dp.callback_query.register(cb_back, F.data == "back")
    dp.callback_query.register(cb_buy, F.data == "buy")
    dp.callback_query.register(cb_support, F.data == "support")
    dp.callback_query.register(cb_choose, F.data.startswith("choose:"))
    dp.callback_query.register(cb_paid, F.data.startswith("paid:"))

    dp.callback_query.register(admin_ok, F.data.startswith("admin_ok:"))
    dp.callback_query.register(admin_no, F.data.startswith("admin_no:"))

    dp.message.register(handle_any_message)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
