import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database import init_db
from handlers import router
from mail import mail_worker

logging.basicConfig(level=logging.INFO)


async def main():
    await init_db()

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Фоновая задача на чтение почты
    asyncio.create_task(mail_worker(bot))

    print("🚀 Bot running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
