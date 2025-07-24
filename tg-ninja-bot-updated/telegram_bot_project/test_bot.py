#!/usr/bin/env python3
"""
Скрипт для тестирования основных функций бота
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.database import db_manager
from database.models import User, Account, Group, AutoPost, NeuroComment
from services.encryption import EncryptionService
from config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BotTester:
    def __init__(self):
        self.encryption = EncryptionService()
    
    def test_database_connection(self):
        """Тест подключения к базе данных"""
        logger.info("Testing database connection...")
        try:
            from sqlalchemy import text
            db_manager.init_database()
            with db_manager.get_session() as session:
                result = session.execute(text("SELECT 1")).scalar()
                assert result == 1
            logger.info("✅ Database connection test passed")
            return True
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            return False
    
    def test_database_models(self):
        """Тест моделей базы данных"""
        logger.info("Testing database models...")
        try:
            with db_manager.get_session() as session:
                # Создание тестового пользователя
                test_user = User(
                    telegram_id=123456789,
                    username="test_user",
                    first_name="Test User"
                )
                session.add(test_user)
                session.flush()
                
                # Создание тестового аккаунта
                test_account = Account(
                    user_id=test_user.id,
                    phone_number="+1234567890",
                    session_string=self.encryption.encrypt("test_session"),
                    is_active=True
                )
                session.add(test_account)
                session.flush()
                
                # Создание тестовой группы
                test_group = Group(
                    telegram_id="-1001234567890",
                    title="Test Group",
                    username="test_group",
                    member_count=100
                )
                session.add(test_group)
                session.flush()
                
                # Создание тестовой рассылки
                test_broadcast = AutoPost(
                    user_id=test_user.id,
                    account_id=test_account.id,
                    message_text="Test broadcast message",
                    target_groups='[1]',
                    interval_seconds=3600,
                    is_active=True
                )
                session.add(test_broadcast)
                session.flush()
                
                # Создание тестовой настройки нейрокомментирования
                test_neuro = NeuroComment(
                    user_id=test_user.id,
                    account_id=test_account.id,
                    target_channels='["@test_channel"]',
                    comment_template="Test comment {random_emoji}",
                    is_active=True,
                    comments_per_day=10
                )
                session.add(test_neuro)
                session.flush()
                
                # Проверка созданных записей
                assert session.query(User).filter_by(telegram_id=123456789).first() is not None
                assert session.query(Account).filter_by(phone_number="+1234567890").first() is not None
                assert session.query(Group).filter_by(telegram_id="-1001234567890").first() is not None
                assert session.query(AutoPost).filter_by(message_text="Test broadcast message").first() is not None
                assert session.query(NeuroComment).filter_by(comment_template="Test comment {random_emoji}").first() is not None
                
                # Очистка тестовых данных
                session.delete(test_neuro)
                session.delete(test_broadcast)
                session.delete(test_group)
                session.delete(test_account)
                session.delete(test_user)
                session.commit()
                
            logger.info("✅ Database models test passed")
            return True
        except Exception as e:
            logger.error(f"❌ Database models test failed: {e}")
            return False
    
    def test_encryption_service(self):
        """Тест сервиса шифрования"""
        logger.info("Testing encryption service...")
        try:
            test_data = "sensitive_session_string_12345"
            
            # Шифрование
            encrypted = self.encryption.encrypt(test_data)
            assert encrypted != test_data
            assert len(encrypted) > 0
            
            # Расшифровка
            decrypted = self.encryption.decrypt(encrypted)
            assert decrypted == test_data
            
            logger.info("✅ Encryption service test passed")
            return True
        except Exception as e:
            logger.error(f"❌ Encryption service test failed: {e}")
            return False
    
    def test_config_loading(self):
        """Тест загрузки конфигурации"""
        logger.info("Testing configuration loading...")
        try:
            # Проверка обязательных параметров
            required_configs = [
                'DATABASE_URL',
                'SECRET_KEY',
                'API_ID',
                'API_HASH'
            ]
            
            for config_name in required_configs:
                value = getattr(Config, config_name, None)
                if not value:
                    logger.warning(f"⚠️ Config {config_name} is not set")
                else:
                    logger.info(f"✅ Config {config_name} is set")
            
            # Проверка опциональных параметров
            optional_configs = [
                'BOT_TOKEN',
                'OPENAI_API_KEY',
                'OPENAI_API_BASE'
            ]
            
            for config_name in optional_configs:
                value = getattr(Config, config_name, None)
                if not value:
                    logger.info(f"ℹ️ Optional config {config_name} is not set")
                else:
                    logger.info(f"✅ Optional config {config_name} is set")
            
            logger.info("✅ Configuration loading test completed")
            return True
        except Exception as e:
            logger.error(f"❌ Configuration loading test failed: {e}")
            return False
    
    def test_directory_structure(self):
        """Тест структуры директорий"""
        logger.info("Testing directory structure...")
        try:
            required_dirs = [
                'app',
                'database',
                'handlers',
                'services',
                'utils',
                'web'
            ]
            
            for dir_name in required_dirs:
                if os.path.exists(dir_name) and os.path.isdir(dir_name):
                    logger.info(f"✅ Directory {dir_name} exists")
                else:
                    logger.error(f"❌ Directory {dir_name} does not exist")
                    return False
            
            # Проверка важных файлов
            required_files = [
                'main.py',
                'config.py',
                'requirements.txt',
                '.env.example'
            ]
            
            for file_name in required_files:
                if os.path.exists(file_name) and os.path.isfile(file_name):
                    logger.info(f"✅ File {file_name} exists")
                else:
                    logger.error(f"❌ File {file_name} does not exist")
                    return False
            
            logger.info("✅ Directory structure test passed")
            return True
        except Exception as e:
            logger.error(f"❌ Directory structure test failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Запуск всех тестов"""
        logger.info("=" * 50)
        logger.info("Starting TG Ninja Bot Tests")
        logger.info("=" * 50)
        
        tests = [
            ("Directory Structure", self.test_directory_structure),
            ("Configuration Loading", self.test_config_loading),
            ("Database Connection", self.test_database_connection),
            ("Database Models", self.test_database_models),
            ("Encryption Service", self.test_encryption_service)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"\n🧪 Running test: {test_name}")
            try:
                if test_func():
                    passed += 1
                    logger.info(f"✅ {test_name} - PASSED")
                else:
                    logger.error(f"❌ {test_name} - FAILED")
            except Exception as e:
                logger.error(f"❌ {test_name} - ERROR: {e}")
        
        logger.info("\n" + "=" * 50)
        logger.info(f"Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests passed! Bot is ready for deployment.")
        else:
            logger.error(f"⚠️ {total - passed} tests failed. Please fix issues before deployment.")
        
        logger.info("=" * 50)
        
        return passed == total

async def main():
    """Главная функция тестирования"""
    tester = BotTester()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🚀 Bot testing completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Bot testing failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

