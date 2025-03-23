import sys
import os
import logging
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow
from core.sync_downloader import DownloadManager

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cleandownloader.log', mode='w'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    try:
        # Устанавливаем папку для загрузок по умолчанию
        download_folder = Path(os.path.expanduser("~")) / "Downloads"
        logger.info(f"Download folder set to {download_folder}")

        # Создаем приложение Qt
        app = QApplication(sys.argv)
        app.setApplicationName("CleanDownloader")
        logger.info("QApplication created")

        # Создаем менеджер загрузок
        download_manager = DownloadManager(max_workers=5)
        logger.info("Download manager initialized")

        # Создаем и показываем главное окно
        window = MainWindow(download_manager, download_folder)
        window.show()
        logger.info("Main window displayed")

        # Запускаем главный цикл приложения
        sys.exit(app.exec_())

    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()