from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem,
    QLineEdit, QLabel, QProgressBar, QMenuBar,
    QFileDialog, QSystemTrayIcon, QApplication
)
from PyQt6.QtGui import QIcon, QAction
from core.downloader import DownloadManager
from config.settings import config
import logging

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.manager = DownloadManager(max_workers=config.max_parallel_downloads)
        self.tray = self._init_tray()
        self._init_ui()
        self._start_update_timer()

    def _init_tray(self):
        """Инициализация трея"""
        tray = QSystemTrayIcon(QIcon(":/icons/app_icon.png"), self)
        tray_menu = QMenuBar()
        tray_menu.addAction("Открыть", self.show)
        tray_menu.addAction("Выход", QApplication.quit)
        tray.setContextMenu(tray_menu)
        tray.show()
        return tray

    def _init_ui(self):
        self.setWindowTitle("CleanDownloader")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top panel
        top_panel = QHBoxLayout()
        
        self.url_input = QLineEdit(placeholderText="Введите URL...")
        self.add_btn = QPushButton("Добавить")
        self.add_btn.clicked.connect(self.add_download)
        
        self.pause_btn = QPushButton("Пауза")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        
        top_panel.addWidget(self.url_input)
        top_panel.addWidget(self.add_btn)
        top_panel.addWidget(self.pause_btn)

        # Downloads table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Имя файла", "Размер", "Прогресс", "Скорость", "Статус"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Status bar
        self.status = self.statusBar()
        self.status_label = QLabel("Готово")
        self.status.addPermanentWidget(self.status_label)

        layout.addLayout(top_panel)
        layout.addWidget(self.table)

        # Menu
        menu = self.menuBar()
        settings_menu = menu.addMenu("Настройки")
        theme_action = settings_menu.addAction("Тёмная тема")
        theme_action.setCheckable(True)
        theme_action.toggled.connect(self.apply_dark_theme)

    def apply_dark_theme(self, checked):
        if checked:
            self.setStyleSheet("""
                QWidget { background: #2b2b2b; color: #ffffff; }
                QLineEdit { background: #404040; border: 1px solid #606060; }
                QTableWidget { background: #353535; }
                QHeaderView::section { background: #404040; }
            """)
        else:
            self.setStyleSheet("")

    def add_download(self):
        url = self.url_input.text()
        if url:
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить как")
            if path:
                self.download_manager.add_download(url, path)
                self.update_table()

    def toggle_pause(self, checked):
        self.download_manager.toggle_pause(checked)
        self.pause_btn.setText("Возобновить" if checked else "Пауза")

    def update_table(self):
        self.table.setRowCount(len(self.download_manager.downloads))
        for row, download in enumerate(self.download_manager.downloads):
            self.table.setItem(row, 0, QTableWidgetItem(download['name']))
            self.table.setItem(row, 1, QTableWidgetItem(download['size']))
            self.table.setItem(row, 2, QTableWidgetItem(f"{download['progress']}%"))
            self.table.setItem(row, 3, QTableWidgetItem(download['speed']))
            self.table.setItem(row, 4, QTableWidgetItem(download['status']))

    def _create_progress_bar(self) -> QProgressBar:
        """Кастомный прогресс-бар для таблицы"""
        bar = QProgressBar()
        bar.setTextVisible(False)
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
        self.timer.timeout.connect(self._update_ui)
        self.timer.start(1000)  # Обновление каждую секунду

    def _update_ui(self):
        """Обновление таблицы и статистики"""
        for row in range(self.table.rowCount()):
            download = self.manager.downloads[row]
            self.table.item(row, 3).setText(download['speed'])
            self.table.cellWidget(row, 2).setValue(download['progress'])
            
            status_item = self.table.item(row, 4)
            status_item.setText(download['status'])
            status_item.setForeground(
                Qt.GlobalColor.green if "Completed" in download['status'] else 
                Qt.GlobalColor.red if "Error" in download['status'] else 
                Qt.GlobalColor.yellow
            )