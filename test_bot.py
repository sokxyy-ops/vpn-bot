import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "ТВОЙ_ТОКЕН_СЮДА"

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Напиши /etest")

@dp.message(Command("etest"))
async def etest(m: Message):
    await m.answer(
        '<tg-emoji emoji-id="5359596642506925824">🌐</tg-emoji> КАСТОМ ЭМОДЗИ ТЕСТ'
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
