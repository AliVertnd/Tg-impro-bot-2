#!/usr/bin/env python3
"""
Telegram Bot для парсинга, рассылок и инвайтинга
Основной файл запуска приложения
"""

import asyncio
import logging
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
import time

from config import Config
from database.database import db_manager
from app.bot import TelegramBot
from web.app import create_flask_app
from services.scheduler import SchedulerService

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'{Config.LOGS_DIR}/bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

class Application:
    def __init__(self):
        self.bot = None
        self.flask_app = None
        self.scheduler = None
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def start(self):
        """Запуск всех компонентов приложения"""
        logger.info("Starting Telegram Bot Application...")
        
        try:
            # Инициализация базы данных
            logger.info("Initializing database...")
            db_manager.init_database()
            
            # Создание и запуск бота
            logger.info("Starting Telegram bot...")
            self.bot = TelegramBot()
            
            # Создание Flask приложения
            logger.info("Creating Flask web interface...")
            self.flask_app = create_flask_app()
            
            # Запуск планировщика задач
            logger.info("Starting scheduler service...")
            self.scheduler = SchedulerService()
            self.scheduler.start()
            
            # Запуск Flask в отдельном потоке
            flask_thread = Thread(
                target=self._run_flask,
                daemon=True
            )
            flask_thread.start()
            
            # Запуск бота
            self.running = True
            await self.bot.start()
            
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            await self.stop()
            raise
    
    def _run_flask(self):
        """Запуск Flask приложения в отдельном потоке"""
        try:
            self.flask_app.run(
                host='0.0.0.0',
                port=Config.FLASK_PORT,
                debug=Config.DEBUG,
                use_reloader=False
            )
        except Exception as e:
            logger.error(f"Flask app error: {e}")
    
    async def stop(self):
        """Остановка всех компонентов приложения"""
        logger.info("Stopping Telegram Bot Application...")
        
        self.running = False
        
        # Остановка планировщика
        if self.scheduler:
            self.scheduler.stop()
        
        # Остановка бота
        if self.bot:
            await self.bot.stop()
        
        # Закрытие базы данных
        db_manager.close()
        
        # Закрытие executor
        self.executor.shutdown(wait=True)
        
        logger.info("Application stopped successfully")

# Глобальный экземпляр приложения
app = Application()

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"Received signal {signum}, shutting down...")
    asyncio.create_task(app.stop())

async def main():
    """Главная функция"""
    # Регистрация обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await app.start()
        
        # Ожидание завершения
        while app.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Application error: {e}")
    finally:
        await app.stop()

if __name__ == "__main__":
    # Проверка конфигурации
    if not Config.BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables")
        sys.exit(1)
    
    # Создание необходимых директорий
    import os
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    os.makedirs(Config.LOGS_DIR, exist_ok=True)
    
    # Запуск приложения
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Failed to run application: {e}")
        sys.exit(1)

