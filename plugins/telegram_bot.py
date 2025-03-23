import os
import logging
import requests
import asyncio
import nest_asyncio
import time
from telegram import Update, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from core.sync_downloader import DownloadManager
from pathlib import Path
from config.settings import settings
from urllib.parse import urlparse

# Применяем патч для вложенных event loops
nest_asyncio.apply()

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, download_manager: DownloadManager):
        self.download_manager = download_manager
        self.application = None
        self.bot_token = settings.telegram_bot_token
        self.virustotal_api_key = settings.virustotal_api_key
        self.download_folder = Path.home() / settings.download_folder
        self.download_tasks = {}  # Словарь для отслеживания задач обновления статуса
        self.tracked_downloads = set()  # Список для отслеживания ID загрузок
        self.chat_ids = set()  # Множество ID чатов с пользователями
        self.monitor_task = None  # Задача для мониторинга загрузок
        self._running = False
        self._initialize_bot()
        
    def _initialize_bot(self):
        """Инициализация бота"""
        try:
            # Создаем приложение
            self.application = Application.builder().token(self.bot_token).build()
            
            # Добавляем обработчики команд
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(CommandHandler("help", self.help))
            self.application.add_handler(CommandHandler("check", self.check_file))
            self.application.add_handler(CommandHandler("download", self.start_download))
            self.application.add_handler(CommandHandler("status", self.show_downloads_status))
            
            # Добавляем обработчик URL
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_url))
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации бота: {e}")
            raise
            
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        # Сохраняем ID чата для отправки уведомлений
        chat_id = update.effective_chat.id
        self.chat_ids.add(chat_id)
        
        await update.message.reply_text(
            "Привет! Я бот для проверки безопасности файлов. Отправь мне ссылку на файл, и я проверю его на вирусы перед загрузкой."
        )
        
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
Доступные команды:
/start - Начать работу с ботом
/help - Показать это сообщение
/check <url> - Проверить файл по ссылке на безопасность
/download <url> - Загрузить файл
/status - Показать статус текущих загрузок

Просто отправьте ссылку на файл, и я проверю его на безопасность.
        """
        await update.message.reply_text(help_text)
        
    async def show_downloads_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус текущих загрузок"""
        chat_id = update.effective_chat.id
        self.chat_ids.add(chat_id)
        
        downloads = self.download_manager.get_all_downloads()
        if not downloads:
            await update.message.reply_text("В данный момент нет активных загрузок.")
            return
            
        # Формируем сообщение со статусами всех загрузок
        status_message = "Статус загрузок:\n\n"
        for download in downloads:
            # Добавляем загрузку в отслеживаемые
            self.tracked_downloads.add(download["id"])
            
            # Форматируем информацию о загрузке
            status_message += f"📁 {download['name']}\n"
            status_message += f"Статус: {download['status']}\n"
            if download['status'] == "Загрузка":
                status_message += f"Прогресс: {download['progress']}\n"
                status_message += f"Скорость: {download['speed']}\n"
            status_message += f"Размер: {download['size']}\n"
            
            # Добавляем информацию о проверке на вирусы, если она есть
            if "virus_scan" in download:
                scan_result = download["virus_scan"]
                status_emoji = {
                    "safe": "✅",
                    "warning": "⚠️",
                    "danger": "🚨",
                    "error": "❓",
                    "pending": "⏳",
                    "unknown": "❓",
                    "info": "ℹ️"
                }.get(scan_result["status"], "❓")
                
                status_message += f"Безопасность: {status_emoji} {scan_result['message']}\n"
            
            status_message += "\n"
            
        await update.message.reply_text(status_message)
        
        # Запускаем мониторинг загрузок, если он еще не запущен
        if not self.monitor_task or self.monitor_task.done():
            self.monitor_task = asyncio.create_task(self._monitor_downloads())
        
    async def check_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /check"""
        if not context.args:
            await update.message.reply_text("Пожалуйста, укажите ссылку на файл для проверки.")
            return
            
        url = context.args[0]
        if not url.startswith(('http://', 'https://')):
            await update.message.reply_text("Пожалуйста, отправьте корректную ссылку на файл.")
            return
            
        try:
            # Отправляем сообщение о начале проверки
            status_message = await update.message.reply_text("🔍 Начинаю проверку файла...")
            
            # Получаем информацию о файле
            response = requests.head(url)
            content_type = response.headers.get('content-type', '')
            content_length = response.headers.get('content-length', '0')
            
            # Проверяем, является ли файл исполняемым
            is_executable = any(ext in url.lower() for ext in ['.exe', '.dll', '.msi', '.bat', '.cmd', '.ps1'])
            
            # Формируем предварительный отчет
            report = f"📊 Информация о файле:\n\n"
            report += f"📦 Тип файла: {content_type}\n"
            report += f"📈 Размер: {int(content_length) / 1024 / 1024:.2f} MB\n"
            report += f"⚠️ Исполняемый файл: {'Да' if is_executable else 'Нет'}\n\n"
            
            # Проверяем файл через VirusTotal
            if is_executable:
                report += "🔍 Проверка через VirusTotal...\n"
                
                # Получаем URL для загрузки
                upload_url = "https://www.virustotal.com/vtapi/v2/url/scan"
                params = {"apikey": self.virustotal_api_key, "url": url}
                
                response = requests.post(upload_url, data=params)
                response.raise_for_status()
                result = response.json()
                
                if "resource" in result:
                    # Получаем результаты проверки
                    report_url = "https://www.virustotal.com/vtapi/v2/url/report"
                    params = {
                        "apikey": self.virustotal_api_key,
                        "resource": result["resource"]
                    }
                    
                    response = requests.get(report_url, params=params)
                    response.raise_for_status()
                    report_data = response.json()
                    
                    if report_data.get("response_code") == 1:
                        positives = report_data.get("positives", 0)
                        total = report_data.get("total", 0)
                        
                        report += f"\n📊 Результаты проверки:\n"
                        report += f"✅ Безопасность: {positives} из {total} антивирусов обнаружили угрозы\n\n"
                        
                        if positives > 0:
                            report += "⚠️ Обнаруженные угрозы:\n"
                            for scanner, result in report_data.get("scans", {}).items():
                                if result.get("detected"):
                                    report += f"- {scanner}: {result.get('result', 'N/A')}\n"
                        else:
                            report += "✅ Угроз не обнаружено.\n"
                    else:
                        report += "⚠️ Проверка все еще выполняется. Попробуйте позже.\n"
                else:
                    report += "❌ Ошибка при проверке файла.\n"
            else:
                report += "ℹ️ Файл не является исполняемым, проверка через VirusTotal не требуется.\n"
            
            # Обновляем сообщение с результатами
            await status_message.edit_text(report)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке файла: {e}")
            await update.message.reply_text(f"❌ Произошла ошибка при проверке файла: {str(e)}")
            
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик URL-сообщений"""
        url = update.message.text
        if not url.startswith(('http://', 'https://')):
            await update.message.reply_text("Пожалуйста, отправьте корректную ссылку на файл.")
            return
            
        # Используем команду check для проверки файла
        context.args = [url]
        await self.check_file(update, context)
            
    async def start_download(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /download для запуска загрузки файла"""
        args = context.args
        if not args:
            await update.message.reply_text("Пожалуйста, укажите URL для загрузки\nПример: /download https://example.com/file.zip")
            return
            
        url = args[0]
        download_path = Path(self.download_folder)
        
        try:
            # Валидация URL
            if not url.startswith(('http://', 'https://')):
                await update.message.reply_text("Некорректный URL. URL должен начинаться с http:// или https://")
                return
                
            # Проверяем, что папка загрузки существует
            download_path.mkdir(parents=True, exist_ok=True)
            
            # Создаем путь для сохранения файла
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            
            if not filename:
                filename = "download"
                
            file_path = download_path / filename
            
            # Сообщаем пользователю о начале загрузки
            message = await update.message.reply_text(f"Начинаю загрузку файла {filename}...\nСохраняю в {file_path}")
            
            # Добавляем задачу в менеджер загрузок
            self.download_manager.add_download(url, file_path)
            
            # Ждем некоторое время, чтобы загрузка началась
            await asyncio.sleep(3)
            
            # Получаем обновленную информацию о загрузке
            downloads = self.download_manager.get_all_downloads()
            for download in downloads:
                if download["url"] == url:
                    download_id = download["id"]
                    
                    # Запускаем задачу по обновлению статуса загрузки
                    self.download_tasks[download_id] = asyncio.create_task(
                        self._update_download_status(message, download_id)
                    )
                    return
            
            await message.edit_text(f"Не удалось начать загрузку файла {filename}. Попробуйте еще раз.")
        except Exception as e:
            await update.message.reply_text(f"Ошибка при запуске загрузки: {str(e)}")

    async def _update_download_status(self, message: Message, download_id: str) -> None:
        """Обновляет статус загрузки в сообщении"""
        try:
            prev_status = None
            is_completed = False
            
            while not is_completed:
                download_info = self.download_manager.get_download_by_id(download_id)
                
                if not download_info:
                    await message.edit_text("Загрузка отменена или не найдена.")
                    return
                    
                status = download_info["status"]
                
                # Проверяем, изменился ли статус
                if status != prev_status:
                    if status == "Загрузка":
                        await message.edit_text(
                            f"Загрузка: {download_info['name']}\n"
                            f"Статус: {status}\n"
                            f"Прогресс: {download_info['progress']}\n"
                            f"Скорость: {download_info['speed']}\n"
                            f"Размер: {download_info['size']}"
                        )
                    elif status == "Завершено":
                        # Проверяем, есть ли информация о проверке на вирусы
                        virus_info = ""
                        if "virus_scan" in download_info:
                            scan_result = download_info["virus_scan"]
                            status_emoji = {
                                "safe": "✅",
                                "warning": "⚠️",
                                "danger": "🚨",
                                "error": "❓",
                                "pending": "⏳",
                                "unknown": "❓",
                                "info": "ℹ️"
                            }.get(scan_result["status"], "❓")
                            
                            virus_info = f"\n\nПроверка на вирусы: {status_emoji} {scan_result['message']}"
                            
                            # Добавляем ссылку на отчет, если она есть
                            if "link" in scan_result:
                                virus_info += f"\n[Подробный отчет]({scan_result['link']})"
                        
                        await message.edit_text(
                            f"Загрузка завершена ✅\n"
                            f"Файл: {download_info['name']}\n"
                            f"Размер: {download_info['size']}\n"
                            f"Путь: {download_info['path']}\n"
                            f"MD5: `{download_info['md5']}`\n"
                            f"SHA1: `{download_info['sha1']}`"
                            f"{virus_info}",
                            parse_mode="Markdown"
                        )
                        is_completed = True
                    elif status in ["Отменено", "Ошибка", "Ошибка доступа к файлу", "Ошибка сети"]:
                        await message.edit_text(
                            f"Загрузка не удалась ❌\n"
                            f"Файл: {download_info['name']}\n"
                            f"Статус: {status}\n"
                            f"URL: {download_info['url']}"
                        )
                        is_completed = True
                    elif status == "Проверка файла...":
                        await message.edit_text(
                            f"Проверка файла 🔍\n"
                            f"Файл: {download_info['name']}\n"
                            f"Размер: {download_info['size']}\n"
                            f"Вычисление контрольных сумм и проверка на вирусы..."
                        )
                    elif status == "Приостановлено":
                        await message.edit_text(
                            f"Загрузка приостановлена ⏸\n"
                            f"Файл: {download_info['name']}\n"
                            f"Прогресс: {download_info['progress']}\n"
                            f"Размер: {download_info['size']}"
                        )
                    elif status == "В очереди":
                        await message.edit_text(
                            f"Файл в очереди на загрузку ⏳\n"
                            f"Файл: {download_info['name']}\n"
                            f"URL: {download_info['url']}"
                        )
                # Сохраняем текущий статус для следующей проверки
                prev_status = status
                
                # Если загрузка все еще выполняется, ждем перед следующим обновлением
                if not is_completed:
                    if status == "Загрузка":
                        # Обновляем прогресс каждые 3 секунды
                        await message.edit_text(
                            f"Загрузка: {download_info['name']}\n"
                            f"Статус: {status}\n"
                            f"Прогресс: {download_info['progress']}\n"
                            f"Скорость: {download_info['speed']}\n"
                            f"Размер: {download_info['size']}"
                        )
                    await asyncio.sleep(3)
                    
        except Exception as e:
            logger.error(f"Error updating download status in Telegram: {e}")
            try:
                await message.edit_text(f"Ошибка при обновлении статуса загрузки: {str(e)}")
            except:
                pass  # Игнорируем ошибки при отправке сообщения об ошибке
            
    def run(self):
        """Запуск бота в отдельном потоке"""
        try:
            # Запускаем бота
            self._running = True
            # Запускаем мониторинг загрузок
            asyncio.run_coroutine_threadsafe(self._monitor_downloads(), asyncio.get_event_loop())
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            raise
            
    async def _monitor_downloads(self):
        """Отслеживает все загрузки и отправляет уведомления об изменении их статуса"""
        logger.info("Starting download monitor task")
        
        prev_statuses = {}  # Словарь для хранения предыдущих статусов загрузок
        
        while self._running:
            try:
                # Получаем все загрузки
                downloads = self.download_manager.get_all_downloads()
                
                for download in downloads:
                    download_id = download["id"]
                    current_status = download["status"]
                    
                    # Проверяем, изменился ли статус загрузки
                    if download_id in prev_statuses and prev_statuses[download_id] != current_status:
                        # Статус изменился, отправляем уведомление всем активным чатам
                        for chat_id in self.chat_ids:
                            await self._send_status_notification(chat_id, download)
                    
                    # Добавляем новую загрузку в отслеживаемые
                    if download_id not in prev_statuses:
                        for chat_id in self.chat_ids:
                            await self._send_new_download_notification(chat_id, download)
                    
                    # Обновляем предыдущий статус
                    prev_statuses[download_id] = current_status
                
                # Удаляем из словаря загрузки, которых больше нет
                download_ids = {d["id"] for d in downloads}
                for download_id in list(prev_statuses.keys()):
                    if download_id not in download_ids:
                        del prev_statuses[download_id]
                
                # Ждем перед следующей проверкой
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"Error in download monitor: {e}")
                await asyncio.sleep(5)  # В случае ошибки делаем более длинную паузу
        
        logger.info("Download monitor task stopped")
    
    async def _send_status_notification(self, chat_id, download):
        """Отправляет уведомление о новом статусе загрузки"""
        try:
            status = download["status"]
            
            if status == "Завершено":
                # Проверяем, есть ли информация о проверке на вирусы
                virus_info = ""
                if "virus_scan" in download:
                    scan_result = download["virus_scan"]
                    status_emoji = {
                        "safe": "✅",
                        "warning": "⚠️",
                        "danger": "🚨",
                        "error": "❓",
                        "pending": "⏳",
                        "unknown": "❓",
                        "info": "ℹ️"
                    }.get(scan_result["status"], "❓")
                    
                    virus_info = f"\n\nПроверка на вирусы: {status_emoji} {scan_result['message']}"
                    
                    # Добавляем ссылку на отчет, если она есть
                    if "link" in scan_result:
                        virus_info += f"\n[Подробный отчет]({scan_result['link']})"
                
                message = (
                    f"Загрузка завершена ✅\n"
                    f"Файл: {download['name']}\n"
                    f"Размер: {download['size']}\n"
                    f"Путь: {download['path']}\n"
                    f"MD5: `{download['md5']}`\n"
                    f"SHA1: `{download['sha1']}`"
                    f"{virus_info}"
                )
                
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown"
                )
            
            elif status in ["Отменено", "Ошибка", "Ошибка доступа к файлу", "Ошибка сети"]:
                message = (
                    f"Загрузка не удалась ❌\n"
                    f"Файл: {download['name']}\n"
                    f"Статус: {status}\n"
                    f"URL: {download['url']}"
                )
                
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
                
            elif status == "Проверка файла...":
                message = (
                    f"Проверка файла 🔍\n"
                    f"Файл: {download['name']}\n"
                    f"Размер: {download['size']}\n"
                    f"Вычисление контрольных сумм и проверка на вирусы..."
                )
                
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message
                )
        
        except Exception as e:
            logger.error(f"Error sending status notification: {e}")
    
    async def _send_new_download_notification(self, chat_id, download):
        """Отправляет уведомление о новой загрузке"""
        try:
            message = (
                f"Новая загрузка добавлена 📥\n"
                f"Файл: {download['name']}\n"
                f"URL: {download['url']}\n"
                f"Статус: {download['status']}"
            )
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message
            )
            
        except Exception as e:
            logger.error(f"Error sending new download notification: {e}")
            
    def stop(self):
        """Остановка бота"""
        if self.application and self._running:
            try:
                self._running = False
                if self.monitor_task:
                    self.monitor_task.cancel()
                self.application.stop()
            except Exception as e:
                logger.error(f"Ошибка при остановке бота: {e}")
                raise