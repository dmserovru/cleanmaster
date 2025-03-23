import os
from pathlib import Path
import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QLabel, QToolTip, 
    QMenu, QAction, QToolBar
)
from PyQt5.QtCore import QTimer, Qt, QPoint
from PyQt5.QtGui import QIcon, QColor
from core.sync_downloader import DownloadManager
from plugins.telegram_bot import TelegramBot
from config.settings import settings
from urllib.parse import urlparse
import time

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, download_manager: DownloadManager, telegram_bot: TelegramBot):
        super().__init__()
        self.download_manager = download_manager
        self.telegram_bot = telegram_bot
        self.download_folder = Path.home() / settings.download_folder
        self.download_folder.mkdir(parents=True, exist_ok=True)
        self.init_ui()
        
        # Таймер для обновления информации о загрузках
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_downloads)
        self.update_timer.start(1000)  # Обновление каждую секунду
        
        logger.info("Main window initialized")

    def init_ui(self):
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle("CleanDownloader")
        self.setGeometry(100, 100, 900, 600)

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
        
        # Добавляем кнопки для управления историей загрузок
        self.clear_completed_button = QPushButton("Очистить завершенные")
        self.clear_completed_button.clicked.connect(self.clear_completed_downloads)
        folder_info.addWidget(self.clear_completed_button)
        
        self.clear_all_button = QPushButton("Очистить все")
        self.clear_all_button.clicked.connect(self.clear_all_downloads)
        folder_info.addWidget(self.clear_all_button)
        
        layout.addLayout(folder_info)

        # Создаем таблицу загрузок
        self.downloads_table = QTableWidget()
        self.downloads_table.setColumnCount(7)  # Добавлен столбец для статуса проверки на вирусы
        self.downloads_table.setHorizontalHeaderLabels([
            "Имя файла", "Размер", "Прогресс", "Скорость", "Статус", "Безопасность", "Действия"
        ])
        
        # Настраиваем растяжение колонок
        header = self.downloads_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Имя файла
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Размер
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Прогресс
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Скорость
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Статус
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Безопасность
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Действия
        
        # Добавляем контекстное меню для таблицы
        self.downloads_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.downloads_table.customContextMenuRequested.connect(self.show_context_menu)
        
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
            # Проверяем, является ли URL ссылкой на Microsoft Store
            is_ms_store = "microsoft.com" in url and any(part.upper().startswith('9N') for part in url.split('/'))
            
            if is_ms_store:
                # Предупреждаем пользователя о Microsoft Store
                reply = QMessageBox.question(
                    self, 
                    "Microsoft Store",
                    "Приложения из Microsoft Store нельзя скачать напрямую. Открыть в Microsoft Store?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    # Ищем ID продукта и открываем в Microsoft Store
                    product_id = ""
                    for part in url.split('/'):
                        if '9N' in part.upper():
                            product_id = part.split('?')[0]
                            break
                    
                    if product_id:
                        ms_store_url = f"ms-windows-store://pdp/?productid={product_id}"
                        # Открываем Microsoft Store
                        import webbrowser
                        webbrowser.open(ms_store_url)
                    else:
                        QMessageBox.warning(self, "Ошибка", "Не удалось определить ID продукта Microsoft Store")
                    return
            
            # Корректная обработка имени файла
            filename = os.path.basename(urlparse(url).path).split("?")[0]
            
            # Для Microsoft Store ссылок создаем специальное имя файла
            if "microsoft.com" in url:
                # Пытаемся извлечь ID продукта
                ms_id = ""
                for part in url.split('/'):
                    if '9N' in part.upper():
                        ms_id = part.split('?')[0]
                        break
                
                if ms_id:
                    filename = f"MicrosoftStore_{ms_id}.appx"
                else:
                    filename = f"MicrosoftStore_app_{int(time.time())}.appx"
            
            # Если имя файла пустое, используем дефолтное
            if not filename:
                filename = f"download_{int(time.time())}"
            
            # Создаем полный путь сохранения
            save_path = self.download_folder / filename
            
            # Добавляем загрузку
            self.download_manager.add_download(url, save_path)
            self.url_input.clear()
            logger.info(f"Started download from {url} to {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось начать загрузку: {str(e)}")
            logger.error(f"Error starting download: {e}")

    def update_downloads(self):
        """Обновление информации о загрузках"""
        try:
            downloads = self.download_manager.get_all_downloads()
            
            # Отладочная информация
            for download in downloads:
                logger.debug(f"Download info: {download}")
                for key, value in download.items():
                    logger.debug(f"Key: {key}, Value: {value}, Type: {type(value)}")
            
            # Обновляем количество строк
            self.downloads_table.setRowCount(len(downloads))
            
            for row, download in enumerate(downloads):
                # Имя файла
                self.set_table_item(row, 0, download['name'])
                
                # Размер
                self.set_table_item(row, 1, download['size'])
                
                # Прогресс
                self.set_table_item(row, 2, download['progress'])
                
                # Скорость
                self.set_table_item(row, 3, download['speed'])
                
                # Статус
                self.set_table_item(row, 4, download['status'])
                
                # Безопасность (результаты проверки на вирусы)
                if "virus_scan" in download:
                    scan_result = download["virus_scan"]
                    status = scan_result["status"]
                    
                    # Устанавливаем иконку/эмодзи в зависимости от статуса проверки
                    status_icon = {
                        "safe": "✅",
                        "warning": "⚠️",
                        "danger": "🚨",
                        "error": "❓",
                        "pending": "⏳",
                        "unknown": "❓",
                        "info": "ℹ️",
                        "not_found": "❓"
                    }.get(status, "❓")
                    
                    security_item = self.set_table_item(row, 5, status_icon)
                    
                    # Устанавливаем цвет фона в зависимости от статуса
                    colors = {
                        "safe": QColor(200, 255, 200),  # Светло-зеленый
                        "warning": QColor(255, 255, 200),  # Светло-желтый
                        "danger": QColor(255, 200, 200),  # Светло-красный
                        "pending": QColor(230, 230, 255)  # Светло-синий
                    }
                    
                    if status in colors:
                        security_item.setBackground(colors[status])
                    
                    # Устанавливаем всплывающую подсказку с подробностями
                    tooltip = f"{scan_result['message']}"
                    if "details" in scan_result:
                        details = scan_result["details"]
                        tooltip += f"\n\nДетали: {details}"
                    
                    security_item.setToolTip(tooltip)
                else:
                    # Если нет информации о безопасности
                    self.set_table_item(row, 5, "⏳")
                
                # Кнопки действий
                # Получаем статус загрузки как строку
                download_status = download['status']
                download_id = download['id']
                
                # Создаем виджет для кнопок если его нет, или обновляем существующий
                actions_widget = self.downloads_table.cellWidget(row, 6)
                if not actions_widget:
                    actions_widget = QWidget()
                    actions_layout = QHBoxLayout(actions_widget)
                    actions_layout.setContentsMargins(0, 0, 0, 0)
                    
                    # Кнопка паузы/возобновления
                    pause_button = QPushButton()
                    pause_button.setFixedWidth(30)
                    
                    # Кнопка отмены
                    cancel_button = QPushButton("❌")
                    cancel_button.setFixedWidth(30)
                    
                    actions_layout.addWidget(pause_button)
                    actions_layout.addWidget(cancel_button)
                    self.downloads_table.setCellWidget(row, 6, actions_widget)
                    
                    # Создаем обработчики здесь, но они будут обновляться ниже
                    pause_button.clicked.connect(lambda checked, d_id=download_id: self.toggle_pause_resume(d_id))
                    cancel_button.clicked.connect(lambda checked, d_id=download_id: self.cancel_download(d_id))
                else:
                    # Если виджет уже существует, получаем его компоненты
                    pause_button = actions_widget.layout().itemAt(0).widget()
                    cancel_button = actions_widget.layout().itemAt(1).widget()
                
                # Обновляем текст кнопки в зависимости от статуса
                if download_status == "Загрузка":
                    pause_button.setText("⏸️")
                    pause_button.setEnabled(True)
                    cancel_button.setEnabled(True)
                elif download_status == "Приостановлено":
                    pause_button.setText("▶️")
                    pause_button.setEnabled(True)
                    cancel_button.setEnabled(True)
                elif download_status == "В очереди":
                    pause_button.setText("⏸️")
                    pause_button.setEnabled(True)
                    cancel_button.setEnabled(True)
                else:
                    # Если загрузка не активна или завершена, дизейблим кнопки
                    pause_button.setEnabled(False)
                    cancel_button.setEnabled(download_status not in ["Завершено", "Отменено", "Ошибка", "Ошибка доступа к файлу", "Ошибка сети"])
                    pause_button.setText("⏸️" if download_status != "Приостановлено" else "▶️")

        except Exception as e:
            logger.error(f"Error updating downloads table: {e}")

    def toggle_pause_resume(self, download_id):
        """Переключение состояния паузы/возобновления загрузки"""
        download_info = self.download_manager.get_download_by_id(download_id)
        if download_info:
            status = download_info['status']
            if status == "Загрузка":
                self.download_manager.pause_download(download_id)
            elif status == "Приостановлено":
                self.download_manager.resume_download(download_id)
            elif status == "В очереди":
                self.download_manager.pause_download(download_id)

    def cancel_download(self, download_id):
        """Отмена загрузки"""
        download_info = self.download_manager.get_download_by_id(download_id)
        if download_info:
            # Проверяем, можно ли отменить загрузку
            status = download_info['status']
            if status in ["Загрузка", "Приостановлено", "В очереди"]:
                self.download_manager.cancel_download(download_id)
                
    def clear_completed_downloads(self):
        """Очистка завершенных загрузок"""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите очистить завершенные загрузки?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.download_manager.clear_completed_downloads()
            logger.info("Completed downloads cleared")
            
    def clear_all_downloads(self):
        """Очистка всех загрузок"""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Вы уверены, что хотите очистить все загрузки?\nАктивные загрузки будут отменены.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.download_manager.clear_all_downloads()
            logger.info("All downloads cleared")
            
    def show_context_menu(self, position):
        """Отображение контекстного меню для таблицы загрузок"""
        row = self.downloads_table.rowAt(position.y())
        if row < 0:
            return
            
        menu = QMenu(self)
        
        # Получаем информацию о загрузке
        download_id = self.get_download_id_by_row(row)
        if not download_id:
            return
            
        download_info = self.download_manager.get_download_by_id(download_id)
        if not download_info:
            return
            
        # Действия в зависимости от статуса загрузки
        status = download_info['status']
        
        if status == "Загрузка":
            pause_action = QAction("Приостановить", self)
            pause_action.triggered.connect(lambda: self.toggle_pause_resume(download_id))
            menu.addAction(pause_action)
            
            cancel_action = QAction("Отменить", self)
            cancel_action.triggered.connect(lambda: self.cancel_download(download_id))
            menu.addAction(cancel_action)
        elif status == "Приостановлено":
            resume_action = QAction("Возобновить", self)
            resume_action.triggered.connect(lambda: self.toggle_pause_resume(download_id))
            menu.addAction(resume_action)
            
            cancel_action = QAction("Отменить", self)
            cancel_action.triggered.connect(lambda: self.cancel_download(download_id))
            menu.addAction(cancel_action)
        elif status == "Завершено":
            open_folder_action = QAction("Открыть папку", self)
            open_folder_action.triggered.connect(lambda: self.open_download_folder(download_info))
            menu.addAction(open_folder_action)
            
            if "virus_scan" in download_info and "link" in download_info["virus_scan"]:
                view_report_action = QAction("Подробный отчет безопасности", self)
                view_report_action.triggered.connect(lambda: self.open_virus_report(download_info))
                menu.addAction(view_report_action)
        
        # Общие действия
        menu.addSeparator()
        remove_action = QAction("Удалить из списка", self)
        remove_action.triggered.connect(lambda: self.remove_download_from_list(download_id))
        menu.addAction(remove_action)
        
        menu.exec_(self.downloads_table.viewport().mapToGlobal(position))
        
    def get_download_id_by_row(self, row):
        """Получение ID загрузки по номеру строки в таблице"""
        try:
            downloads = self.download_manager.get_all_downloads()
            if 0 <= row < len(downloads):
                return downloads[row]["id"]
        except Exception as e:
            logger.error(f"Error getting download ID for row {row}: {e}")
        return None
        
    def open_download_folder(self, download_info):
        """Открытие папки с загруженным файлом"""
        try:
            path = download_info["path"]
            folder = os.path.dirname(path)
            os.startfile(folder)
        except Exception as e:
            logger.error(f"Error opening folder: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку: {str(e)}")
            
    def open_virus_report(self, download_info):
        """Открытие отчета о безопасности в браузере"""
        try:
            report_link = download_info["virus_scan"]["link"]
            import webbrowser
            webbrowser.open(report_link)
        except Exception as e:
            logger.error(f"Error opening virus report: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть отчет: {str(e)}")
            
    def remove_download_from_list(self, download_id):
        """Удаление загрузки из списка"""
        # Это просто удаляет запись из интерфейса, но не удаляет файл
        try:
            # Найдем загрузку в списке и удалим её
            for i, download in enumerate(self.download_manager.downloads):
                if download.id == download_id:
                    if download.status in ["Загрузка", "Приостановлено", "В очереди"]:
                        # Сначала отменяем активную загрузку
                        self.download_manager.cancel_download(download_id)
                    
                    # Удаляем запись
                    self.download_manager.downloads.pop(i)
                    break
        except Exception as e:
            logger.error(f"Error removing download from list: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить загрузку: {str(e)}")

    def set_table_item(self, row: int, column: int, text: str):
        """Вспомогательный метод для установки значения в ячейку таблицы"""
        item = self.downloads_table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.downloads_table.setItem(row, column, item)
        item.setText(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # Делаем ячейку нередактируемой
        return item

    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        self.download_manager.shutdown()
        event.accept()