import sys
import os
import logging
import threading
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow
from core.sync_downloader import DownloadManager
from plugins.telegram_bot import TelegramBot
from plugins.browser_monitor import BrowserMonitor
from config.settings import settings

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    try:
        # Устанавливаем папку для загрузок
        download_folder = Path.home() / settings.download_folder
        download_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Download folder set to {download_folder}")

        # Создаем приложение Qt
        app = QApplication(sys.argv)
        logger.info("QApplication created")

        # Инициализируем менеджер загрузок
        download_manager = DownloadManager(max_workers=settings.max_workers)
        logger.info("Download manager initialized")

        # Инициализируем Telegram бота
        telegram_bot = TelegramBot(download_manager)
        logger.info("Telegram bot initialized")

        # Инициализируем монитор браузера
        def handle_browser_download(url: str, filename: str):
            """Обработчик скачиваний из браузера"""
            try:
                # Создаем путь для загрузки
                download_path = download_folder / filename
                # Добавляем загрузку
                download_manager.add_download(url, download_path)
                logger.info(f"Added download from browser: {url}")
            except Exception as e:
                logger.error(f"Error handling browser download: {e}")

        browser_monitor = BrowserMonitor(handle_browser_download)
        browser_monitor.start()
        logger.info("Browser monitor started")

        # Создаем и показываем главное окно
        window = MainWindow(download_manager, telegram_bot)
        window.show()
        logger.info("Main window displayed")

        # Запускаем Telegram бота в отдельном потоке
        bot_thread = threading.Thread(target=telegram_bot.run, daemon=True)
        bot_thread.start()
        logger.info("Telegram bot started in background thread")

        # Запускаем главный цикл приложения
        sys.exit(app.exec_())

    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()