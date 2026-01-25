import asyncio

from bot import PaymentBot
from config import Config

async def main():
    config = Config()
    bot = PaymentBot(config)
    try:
        await bot.start()
    except Exception as e:
        print(f"Error starting bot: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")