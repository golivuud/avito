import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database import init_db
from handlers import router
from mail import mail_worker

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()

    session = None
    if settings.PROXY_URL:
        session = AiohttpSession(proxy=settings.PROXY_URL)

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Фоновая задача на чтение почты
    asyncio.create_task(mail_worker(bot))

    print("🚀 Bot running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
