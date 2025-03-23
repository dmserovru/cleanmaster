from telegram import Update, Bot
from telegram.ext import (
    CommandHandler, MessageHandler, 
    filters, ApplicationBuilder
)
from core.downloader import DownloadManager
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token: str, download_manager: DownloadManager):
        self.bot = Bot(token)
        self.manager = download_manager
        self.app = ApplicationBuilder().token(token).build()
        
        # Регистрация обработчиков
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(MessageHandler(filters.TEXT, self.handle_url))

    async def start(self, update: Update, context):
        await update.message.reply_text(
            "🚀 Отправьте мне ссылку для загрузки файла!"
        )

    async def handle_url(self, update: Update, context):
        url = update.message.text
        try:
            path = Path.home() / "Downloads" / url.split("/")[-1]
            self.manager.add_download(url, path)
            await update.message.reply_text(f"✅ Добавлено в загрузки: {url}")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
            logger.error(f"Telegram error: {e}")

    def run(self):
        self.app.run_polling()