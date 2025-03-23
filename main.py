import sys
import logging
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow
from config.settings import config
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("cleandownloader.log"),
        logging.StreamHandler()
    ]
)

if __name__ == "__main__":
    # Создаем папку для загрузок, если она не существует
    config.download_folder.mkdir(exist_ok=True, parents=True)
    
    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setOrganizationName("CleanDownloader")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())