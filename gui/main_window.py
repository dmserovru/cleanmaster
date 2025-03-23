from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QProgressBar, QMenuBar,
    QFileDialog, QSystemTrayIcon, QApplication,
    QMenu, QHeaderView, QMessageBox, QInputDialog
)
from PyQt6.QtGui import QIcon, QAction, QCursor
from core.downloader import DownloadManager
from config.settings import config
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.manager = DownloadManager(max_workers=config.max_parallel_downloads)
        self.tray = self._init_tray()
        self._init_ui()
        self._start_update_timer()
        
        logger.info("CleanDownloader запущен")

    def _init_tray(self):
        """Инициализация трея"""
        # Проверяем наличие иконки в папке ресурсов
        icon_path = os.path.join("resources", "app_icon.png")
        if not os.path.exists(icon_path):
            icon_path = None
            
        tray = QSystemTrayIcon(QIcon(icon_path) if icon_path else QIcon(), self)
        tray_menu = QMenu()
        tray_menu.addAction("Открыть", self.show)
        tray_menu.addAction("Выход", QApplication.instance().quit)
        tray.setContextMenu(tray_menu)
        tray.show()
        return tray

    def _init_ui(self):
        self.setWindowTitle(f"{config.app_name} {config.app_version}")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top panel
        top_panel = QHBoxLayout()
        
        self.url_input = QLineEdit(placeholderText="Введите URL...")
        self.url_input.returnPressed.connect(self.add_download)
        
        self.add_btn = QPushButton("Добавить")
        self.add_btn.clicked.connect(self.add_download)
        
        self.pause_all_btn = QPushButton("Пауза всех")
        self.pause_all_btn.setCheckable(True)
        self.pause_all_btn.clicked.connect(self.toggle_pause_all)
        
        top_panel.addWidget(self.url_input)
        top_panel.addWidget(self.add_btn)
        top_panel.addWidget(self.pause_all_btn)

        # Downloads table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Имя файла", "Размер", "Прогресс", "Скорость", "Статус", "MD5/SHA1"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        # Status bar
        self.status = self.statusBar()
        self.status_label = QLabel("Готово")
        self.status.addPermanentWidget(self.status_label)

        layout.addLayout(top_panel)
        layout.addWidget(self.table)

        # Menu
        menu = self.menuBar()
        file_menu = menu.addMenu("Файл")
        file_menu.addAction("Добавить URL", self.add_download)
        file_menu.addAction("Выход", self.close_app)
        
        download_menu = menu.addMenu("Загрузки")
        download_menu.addAction("Приостановить все", self.pause_all_downloads)
        download_menu.addAction("Возобновить все", self.resume_all_downloads)
        download_menu.addAction("Проверить MD5", self.check_md5_sum)
        download_menu.addAction("Проверить SHA1", self.check_sha1_sum)
        
        settings_menu = menu.addMenu("Настройки")
        theme_action = settings_menu.addAction("Тёмная тема")
        theme_action.setCheckable(True)
        theme_action.toggled.connect(self.apply_dark_theme)
        
        help_menu = menu.addMenu("Справка")
        help_menu.addAction("О программе", self.show_about)

    def apply_dark_theme(self, checked):
        if checked:
            self.setStyleSheet("""
                QWidget { background: #2b2b2b; color: #ffffff; }
                QLineEdit { background: #404040; border: 1px solid #606060; }
                QTableWidget { background: #353535; }
                QHeaderView::section { background: #404040; }
                QPushButton { 
                    background: #404040; 
                    border: 1px solid #606060;
                    padding: 5px;
                    border-radius: 2px;
                }
                QPushButton:hover { background: #505050; }
                QPushButton:pressed { background: #606060; }
                QPushButton:checked { background: #606060; }
            """)
        else:
            self.setStyleSheet("")

    def add_download(self):
        url = self.url_input.text().strip()
        if url:
            try:
                file_name = os.path.basename(url.split("?")[0]) or "noname.file"
                path, _ = QFileDialog.getSaveFileName(
                    self, 
                    "Сохранить как", 
                    str(config.download_folder / file_name)
                )
            if path:
                    self.manager.add_download(url, Path(path))
                    self.url_input.clear()
                    self.status_label.setText(f"Добавлена загрузка: {file_name}")
                    logger.info(f"Добавлена загрузка: {url} -> {path}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось добавить загрузку: {str(e)}")
                logger.error(f"Ошибка добавления загрузки: {str(e)}")

    def toggle_pause_all(self, checked):
        try:
            if checked:
                self.manager.pause_all()
                self.pause_all_btn.setText("Возобновить все")
                self.status_label.setText("Все загрузки приостановлены")
            else:
                self.manager.resume_all()
                self.pause_all_btn.setText("Пауза всех")
                self.status_label.setText("Все загрузки возобновлены")
        except Exception as e:
            logger.error(f"Ошибка при переключении паузы: {str(e)}")

    def pause_all_downloads(self):
        self.pause_all_btn.setChecked(True)
        self.toggle_pause_all(True)

    def resume_all_downloads(self):
        self.pause_all_btn.setChecked(False)
        self.toggle_pause_all(False)

    def show_context_menu(self, position):
        """Показать контекстное меню для загрузок"""
        row = self.table.rowAt(position.y())
        if row < 0:
            return

        # Получаем информацию о загрузке
        download = self.manager.get_download_info(row)
        if not download:
            return

        menu = QMenu()
        
        if "Приостановлено" in download["status"]:
            menu.addAction("Возобновить", lambda: self.resume_download(download["id"]))
        elif "Загрузка" in download["status"]:
            menu.addAction("Приостановить", lambda: self.pause_download(download["id"]))
        
        menu.addAction("Отмена", lambda: self.cancel_download(download["id"]))
        menu.addAction("Копировать URL", lambda: self.copy_url(download["url"]))
        menu.addAction("Копировать MD5", lambda: self.copy_hash(download["md5"]))
        menu.addAction("Копировать SHA1", lambda: self.copy_hash(download["sha1"]))
        menu.addAction("Открыть папку", lambda: self.open_folder(download["path"]))
        
        menu.exec(QCursor.pos())

    def pause_download(self, download_id):
        """Приостановить загрузку"""
        try:
            self.manager.pause_download(download_id)
            self.status_label.setText("Загрузка приостановлена")
        except Exception as e:
            logger.error(f"Ошибка при приостановке загрузки: {str(e)}")

    def resume_download(self, download_id):
        """Возобновить загрузку"""
        try:
            self.manager.resume_download(download_id)
            self.status_label.setText("Загрузка возобновлена")
        except Exception as e:
            logger.error(f"Ошибка при возобновлении загрузки: {str(e)}")

    def cancel_download(self, download_id):
        """Отмена загрузки"""
        if QMessageBox.question(
            self, 
            "Подтверждение", 
            "Вы уверены, что хотите отменить загрузку?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            try:
                self.manager.cancel_download(download_id)
                self.status_label.setText("Загрузка отменена")
            except Exception as e:
                logger.error(f"Ошибка при отмене загрузки: {str(e)}")

    def copy_url(self, url):
        """Копировать URL в буфер обмена"""
        QApplication.clipboard().setText(url)
        self.status_label.setText("URL скопирован в буфер обмена")

    def copy_hash(self, hash_value):
        """Копировать хеш в буфер обмена"""
        if hash_value:
            QApplication.clipboard().setText(hash_value)
            self.status_label.setText("Хеш скопирован в буфер обмена")
        else:
            self.status_label.setText("Хеш недоступен")

    def open_folder(self, file_path):
        """Открыть папку с файлом"""
        try:
            path = Path(file_path)
            os.startfile(str(path.parent))
        except Exception as e:
            logger.error(f"Ошибка при открытии папки: {str(e)}")
            self.status_label.setText("Не удалось открыть папку")

    def check_md5_sum(self):
        """Проверка MD5 суммы выбранной загрузки"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Информация", "Выберите загрузку для проверки")
            return

        download = self.manager.get_download_info(row)
        if not download:
            return

        expected_md5, ok = QInputDialog.getText(
            self, 
            "Проверка MD5", 
            "Введите ожидаемую MD5 сумму:"
        )
        
        if ok and expected_md5:
            if self.manager.check_md5(download["id"], expected_md5):
                QMessageBox.information(self, "Проверка MD5", "MD5 суммы совпадают!")
            else:
                QMessageBox.warning(self, "Проверка MD5", "MD5 суммы не совпадают!")

    def check_sha1_sum(self):
        """Проверка SHA1 суммы выбранной загрузки"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Информация", "Выберите загрузку для проверки")
            return

        download = self.manager.get_download_info(row)
        if not download:
            return

        expected_sha1, ok = QInputDialog.getText(
            self, 
            "Проверка SHA1", 
            "Введите ожидаемую SHA1 сумму:"
        )
        
        if ok and expected_sha1:
            if self.manager.check_sha1(download["id"], expected_sha1):
                QMessageBox.information(self, "Проверка SHA1", "SHA1 суммы совпадают!")
            else:
                QMessageBox.warning(self, "Проверка SHA1", "SHA1 суммы не совпадают!")

    def update_table(self):
        """Обновление таблицы загрузок"""
        try:
            all_downloads = self.manager.get_all_downloads()
            current_row_count = self.table.rowCount()
            downloads_count = len(all_downloads)
            
            # Добавляем новые строки, если нужно
            if current_row_count < downloads_count:
                self.table.setRowCount(downloads_count)
                for row in range(current_row_count, downloads_count):
                    download = all_downloads[row]
                    
                    self.table.setItem(row, 0, QTableWidgetItem(download.get('name', 'Неизвестно')))
                    self.table.setItem(row, 1, QTableWidgetItem(download.get('size', '0 B')))
                    
                    progress_bar = self._create_progress_bar()
                    progress_bar.setValue(download.get('progress', 0))
                    self.table.setCellWidget(row, 2, progress_bar)
                    
                    self.table.setItem(row, 3, QTableWidgetItem(download.get('speed', '0 B/s')))
                    self.table.setItem(row, 4, QTableWidgetItem(download.get('status', 'В очереди')))
                    
                    # MD5/SHA1 колонка
                    hash_info = ""
                    if download.get('md5'):
                        hash_info = f"MD5: {download['md5'][:8]}..."
                    if download.get('sha1'):
                        if hash_info:
                            hash_info += "\n"
                        hash_info += f"SHA1: {download['sha1'][:8]}..."
                        
                    self.table.setItem(row, 5, QTableWidgetItem(hash_info))
            
            # Обновляем существующие строки
            for row in range(min(current_row_count, downloads_count)):
                download = all_downloads[row]
                
                # Обновляем скорость и статус
                self.table.item(row, 3).setText(download.get('speed', '0 B/s'))
                
                status = download.get('status', '')
                status_item = self.table.item(row, 4)
                status_item.setText(status)
                
                # Обновляем цвет статуса
                if "Завершено" in status:
                    status_item.setForeground(Qt.GlobalColor.green)
                elif "Ошибка" in status or "Отменено" in status:
                    status_item.setForeground(Qt.GlobalColor.red)
                elif "Приостановлено" in status:
                    status_item.setForeground(Qt.GlobalColor.yellow)
                else:
                    status_item.setForeground(Qt.GlobalColor.white 
                        if "dark" in self.styleSheet() else Qt.GlobalColor.black)
                
                # Обновляем прогресс
                progress_bar = self.table.cellWidget(row, 2)
                if progress_bar:
                    progress_bar.setValue(download.get('progress', 0))
                
                # Обновляем хеши
                hash_info = ""
                if download.get('md5'):
                    hash_info = f"MD5: {download['md5'][:8]}..."
                if download.get('sha1'):
                    if hash_info:
                        hash_info += "\n"
                    hash_info += f"SHA1: {download['sha1'][:8]}..."
                    
                hash_item = self.table.item(row, 5)
                if hash_item:
                    hash_item.setText(hash_info)
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении таблицы: {str(e)}")

    def _create_progress_bar(self) -> QProgressBar:
        """Кастомный прогресс-бар для таблицы"""
        bar = QProgressBar()
        bar.setTextVisible(True)
        bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar.setFormat("%p%")
        bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #2ecc71;
            }
        """)
        return bar

    def _start_update_timer(self):
        """Таймер для обновления GUI"""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_table)
        self.timer.start(1000)  # Обновление каждую секунду

    def show_about(self):
        QMessageBox.about(
            self,
            "О программе",
            f"""<b>{config.app_name}</b> v{config.app_version}
            <p>Современный менеджер загрузок с открытым исходным кодом.</p>
            <p>Функции:</p>
            <ul>
                <li>Многопоточная загрузка</li>
                <li>Возобновление загрузок</li>
                <li>Проверка на вирусы через VirusTotal</li>
                <li>Интеграция с Telegram</li>
                <li>Проверка MD5/SHA1 хешей</li>
            </ul>
            """
        )

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        active_downloads = any(
            "Загрузка" in download.get('status', '') 
            for download in self.manager.get_all_downloads()
        )
        
        if active_downloads:
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Есть активные загрузки. Вы действительно хотите выйти?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.shutdown_app()
                event.accept()
            elif reply == QMessageBox.StandardButton.No:
                # Сворачиваем в трей
                event.ignore()
                self.hide()
                self.tray.showMessage(
                    config.app_name,
                    "Программа продолжает работать в фоне. Кликните по иконке, чтобы открыть.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )
            else:  # Cancel
                event.ignore()
        else:
            # Нет активных загрузок
            reply = QMessageBox.question(
                self,
                "Подтверждение",
                "Вы действительно хотите выйти из программы?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.shutdown_app()
                event.accept()
            else:
                event.ignore()

    def close_app(self):
        """Обработка закрытия через меню"""
        self.close()

    def shutdown_app(self):
        """Корректное завершение приложения"""
        try:
            # Останавливаем таймер обновления GUI
            if hasattr(self, 'timer'):
                self.timer.stop()
                
            # Останавливаем менеджер загрузок
            self.manager.shutdown()
            logger.info("Приложение завершено корректно")
        except Exception as e:
            logger.error(f"Ошибка при завершении приложения: {str(e)}")