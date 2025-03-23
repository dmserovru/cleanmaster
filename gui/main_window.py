import os
from pathlib import Path
import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QLabel
)
from PyQt5.QtCore import QTimer, Qt
from core.sync_downloader import DownloadManager
from config.settings import config

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, download_manager: DownloadManager, download_folder: Path):
        super().__init__()
        self.download_manager = download_manager
        self.download_folder = download_folder
        self.init_ui()
        
        # Таймер для обновления информации о загрузках
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_downloads)
        self.update_timer.start(1000)  # Обновление каждую секунду
        
        logger.info("Main window initialized")

    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle("CleanDownloader")
        self.setGeometry(100, 100, 800, 600)

        # Создаем центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Создаем главный layout
        layout = QVBoxLayout(central_widget)

        # Создаем верхнюю панель
        top_panel = QHBoxLayout()
        
        # URL поле
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Введите URL для загрузки")
        top_panel.addWidget(self.url_input)

        # Кнопка выбора папки
        self.folder_button = QPushButton("Папка")
        self.folder_button.clicked.connect(self.select_folder)
        top_panel.addWidget(self.folder_button)

        # Кнопка загрузки
        self.download_button = QPushButton("Загрузить")
        self.download_button.clicked.connect(self.start_download)
        top_panel.addWidget(self.download_button)

        layout.addLayout(top_panel)

        # Создаем панель с информацией о папке загрузки
        folder_info = QHBoxLayout()
        folder_label = QLabel("Папка загрузки:")
        self.folder_path_label = QLabel(str(self.download_folder))
        folder_info.addWidget(folder_label)
        folder_info.addWidget(self.folder_path_label)
        folder_info.addStretch()
        layout.addLayout(folder_info)

        # Создаем таблицу загрузок
        self.downloads_table = QTableWidget()
        self.downloads_table.setColumnCount(6)
        self.downloads_table.setHorizontalHeaderLabels([
            "Имя файла", "Размер", "Прогресс", "Скорость", "Статус", "Действия"
        ])
        
        # Настраиваем растяжение колонок
        header = self.downloads_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Имя файла
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Размер
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Прогресс
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Скорость
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Статус
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Действия
        
        layout.addWidget(self.downloads_table)

        logger.info("UI elements initialized")

    def select_folder(self):
        """Выбор папки для загрузки"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для загрузки",
            str(self.download_folder)
        )
        if folder:
            self.download_folder = Path(folder)
            self.folder_path_label.setText(str(self.download_folder))
            logger.info(f"Download folder changed to {self.download_folder}")

    def start_download(self):
        """Начало загрузки файла"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите URL для загрузки")
            return

        try:
            # Добавляем загрузку
            self.download_manager.add_download(url, self.download_folder / os.path.basename(url))
            self.url_input.clear()
            logger.info(f"Started download from {url}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось начать загрузку: {str(e)}")
            logger.error(f"Error starting download: {e}")

    def update_downloads(self):
        """Обновление информации о загрузках"""
        try:
            downloads = self.download_manager.get_all_downloads()
            
            # Обновляем количество строк
            self.downloads_table.setRowCount(len(downloads))
            
            for row, download in enumerate(downloads):
                # Имя файла
                self.set_table_item(row, 0, download['name'])
                
                # Размер
                self.set_table_item(row, 1, download['size'])
                
                # Прогресс
                self.set_table_item(row, 2, f"{download['progress']}%")
                
                # Скорость
                self.set_table_item(row, 3, download['speed'])
                
                # Статус
                self.set_table_item(row, 4, download['status'])
                
                # Кнопки действий
                if not self.downloads_table.cellWidget(row, 5):
                    actions_widget = QWidget()
                    actions_layout = QHBoxLayout(actions_widget)
                    actions_layout.setContentsMargins(0, 0, 0, 0)
                    
                    # Кнопка паузы/возобновления
                    pause_button = QPushButton("⏸️" if download['status'] == "Загрузка" else "▶️")
                    pause_button.setFixedWidth(30)
                    pause_button.clicked.connect(
                        lambda checked, d_id=download['id']:
                        self.download_manager.pause_download(d_id)
                        if download['status'] == "Загрузка"
                        else self.download_manager.resume_download(d_id)
                    )
                    
                    # Кнопка отмены
                    cancel_button = QPushButton("❌")
                    cancel_button.setFixedWidth(30)
                    cancel_button.clicked.connect(
                        lambda checked, d_id=download['id']:
                        self.download_manager.cancel_download(d_id)
                    )
                    
                    actions_layout.addWidget(pause_button)
                    actions_layout.addWidget(cancel_button)
                    self.downloads_table.setCellWidget(row, 5, actions_widget)

        except Exception as e:
            logger.error(f"Error updating downloads table: {e}")

    def set_table_item(self, row: int, column: int, text: str):
        """Вспомогательный метод для установки значения в ячейку таблицы"""
        item = self.downloads_table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.downloads_table.setItem(row, column, item)
        item.setText(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # Делаем ячейку нередактируемой

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.download_manager.shutdown()
        event.accept()