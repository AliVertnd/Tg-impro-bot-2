import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import PhoneNumberInvalidError, PhoneCodeInvalidError, PasswordHashInvalidError
from database.database import db_manager
from database.models import User, Account
from config import Config
from services.encryption import EncryptionService

logger = logging.getLogger(__name__)

class AccountHandlers:
    def __init__(self):
        self.encryption = EncryptionService()
        self.active_sessions = {}  # Хранение активных сессий для авторизации
    
    async def accounts_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню управления аккаунтами"""
        user_id = update.effective_user.id
        
        # Получение списка аккаунтов пользователя
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            accounts = session.query(Account).filter_by(user_id=user.id).all()
        
        text = f"📱 Управление аккаунтами\n\n"
        text += f"Всего аккаунтов: {len(accounts)}\n"
        text += f"Активных: {len([a for a in accounts if a.is_active])}\n\n"
        
        if accounts:
            text += "📋 Ваши аккаунты:\n"
            for i, account in enumerate(accounts, 1):
                status = "✅" if account.is_active else "❌"
                banned = "🚫" if account.is_banned else ""
                text += f"{i}. {status} {account.phone_number} {banned}\n"
        else:
            text += "📝 У вас пока нет добавленных аккаунтов"
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить аккаунт", callback_data="account_add")],
            [InlineKeyboardButton("📋 Список аккаунтов", callback_data="account_list")],
            [InlineKeyboardButton("🗑 Удалить аккаунт", callback_data="account_remove")],
            [InlineKeyboardButton("🔄 Обновить статус", callback_data="account_refresh")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def add_account_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда добавления аккаунта"""
        await self._start_add_account(update, context)
    
    async def _start_add_account(self, update, context):
        """Начало процесса добавления аккаунта"""
        text = """
📱 Добавление нового аккаунта

Для добавления аккаунта потребуется:
1. Номер телефона (в формате +7XXXXXXXXXX)
2. Код подтверждения из SMS
3. Пароль двухфакторной аутентификации (если включен)

⚠️ Важно:
• Аккаунт должен быть зарегистрирован в Telegram
• Убедитесь, что у вас есть доступ к номеру телефона
• Данные будут зашифрованы и сохранены безопасно

Введите номер телефона в формате +7XXXXXXXXXX:
        """
        
        context.user_data['state'] = 'add_account_phone'
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="account_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def handle_account_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода данных для добавления аккаунта"""
        state = context.user_data.get('state')
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if state == 'add_account_phone':
            await self._handle_phone_input(update, context, text, user_id)
        elif state == 'add_account_code':
            await self._handle_code_input(update, context, text, user_id)
        elif state == 'add_account_password':
            await self._handle_password_input(update, context, text, user_id)
    
    async def _handle_phone_input(self, update, context, phone, user_id):
        """Обработка ввода номера телефона"""
        # Валидация номера телефона
        if not phone.startswith('+') or len(phone) < 10:
            await update.message.reply_text(
                "❌ Неверный формат номера. Используйте формат +7XXXXXXXXXX"
            )
            return
        
        try:
            # Создание клиента Telegram
            client = TelegramClient(
                StringSession(),
                Config.API_ID,
                Config.API_HASH
            )
            
            await client.connect()
            
            # Отправка кода подтверждения
            result = await client.send_code_request(phone)
            
            # Сохранение данных сессии
            session_key = f"{user_id}_{phone}"
            self.active_sessions[session_key] = {
                'client': client,
                'phone': phone,
                'phone_code_hash': result.phone_code_hash
            }
            
            context.user_data['state'] = 'add_account_code'
            context.user_data['session_key'] = session_key
            
            await update.message.reply_text(
                f"📱 Код подтверждения отправлен на номер {phone}\n\n"
                "Введите полученный код:"
            )
            
        except PhoneNumberInvalidError:
            await update.message.reply_text(
                "❌ Неверный номер телефона. Проверьте правильность ввода."
            )
        except Exception as e:
            logger.error(f"Error sending code to {phone}: {e}")
            await update.message.reply_text(
                "❌ Ошибка при отправке кода. Попробуйте позже."
            )
    
    async def _handle_code_input(self, update, context, code, user_id):
        """Обработка ввода кода подтверждения"""
        session_key = context.user_data.get('session_key')
        if not session_key or session_key not in self.active_sessions:
            await update.message.reply_text("❌ Сессия истекла. Начните заново.")
            context.user_data.clear()
            return
        
        session_data = self.active_sessions[session_key]
        client = session_data['client']
        phone = session_data['phone']
        phone_code_hash = session_data['phone_code_hash']
        
        try:
            # Попытка авторизации с кодом
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            # Успешная авторизация
            await self._save_account(client, phone, user_id)
            await update.message.reply_text(
                f"✅ Аккаунт {phone} успешно добавлен!"
            )
            
            # Очистка данных
            await client.disconnect()
            del self.active_sessions[session_key]
            context.user_data.clear()
            
        except PhoneCodeInvalidError:
            await update.message.reply_text(
                "❌ Неверный код. Попробуйте еще раз:"
            )
        except Exception as e:
            if "Two-step verification is enabled" in str(e):
                context.user_data['state'] = 'add_account_password'
                await update.message.reply_text(
                    "🔐 Требуется пароль двухфакторной аутентификации.\n\n"
                    "Введите ваш пароль:"
                )
            else:
                logger.error(f"Error signing in with code for {phone}: {e}")
                await update.message.reply_text(
                    "❌ Ошибка авторизации. Проверьте код и попробуйте снова."
                )
    
    async def _handle_password_input(self, update, context, password, user_id):
        """Обработка ввода пароля двухфакторной аутентификации"""
        session_key = context.user_data.get('session_key')
        if not session_key or session_key not in self.active_sessions:
            await update.message.reply_text("❌ Сессия истекла. Начните заново.")
            context.user_data.clear()
            return
        
        session_data = self.active_sessions[session_key]
        client = session_data['client']
        phone = session_data['phone']
        
        try:
            # Авторизация с паролем
            await client.sign_in(password=password)
            
            # Успешная авторизация
            await self._save_account(client, phone, user_id)
            await update.message.reply_text(
                f"✅ Аккаунт {phone} успешно добавлен!"
            )
            
            # Очистка данных
            await client.disconnect()
            del self.active_sessions[session_key]
            context.user_data.clear()
            
        except PasswordHashInvalidError:
            await update.message.reply_text(
                "❌ Неверный пароль. Попробуйте еще раз:"
            )
        except Exception as e:
            logger.error(f"Error signing in with password for {phone}: {e}")
            await update.message.reply_text(
                "❌ Ошибка авторизации. Проверьте пароль и попробуйте снова."
            )
    
    async def _save_account(self, client, phone, user_id):
        """Сохранение аккаунта в базу данных"""
        try:
            # Получение информации о пользователе
            me = await client.get_me()
            
            # Получение строки сессии
            session_string = client.session.save()
            
            # Шифрование сессии
            encrypted_session = self.encryption.encrypt(session_string)
            
            with db_manager.get_session() as session:
                # Получение пользователя
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    raise Exception("User not found")
                
                # Проверка существования аккаунта
                existing_account = session.query(Account).filter_by(
                    phone_number=phone
                ).first()
                
                if existing_account:
                    # Обновление существующего аккаунта
                    existing_account.session_string = encrypted_session
                    existing_account.username = me.username
                    existing_account.first_name = me.first_name
                    existing_account.last_name = me.last_name
                    existing_account.is_active = True
                    existing_account.is_banned = False
                else:
                    # Создание нового аккаунта
                    account = Account(
                        user_id=user.id,
                        phone_number=phone,
                        username=me.username,
                        first_name=me.first_name,
                        last_name=me.last_name,
                        session_string=encrypted_session,
                        is_active=True
                    )
                    session.add(account)
                
                session.commit()
                logger.info(f"Account {phone} saved for user {user_id}")
                
        except Exception as e:
            logger.error(f"Failed to save account {phone}: {e}")
            raise
    
    async def list_accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра списка аккаунтов"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            accounts = session.query(Account).filter_by(user_id=user.id).all()
        
        if not accounts:
            await update.message.reply_text("📝 У вас нет добавленных аккаунтов")
            return
        
        text = "📱 Ваши аккаунты:\n\n"
        for i, account in enumerate(accounts, 1):
            status = "✅ Активен" if account.is_active else "❌ Неактивен"
            banned = " 🚫 Заблокирован" if account.is_banned else ""
            
            text += f"{i}. {account.phone_number}\n"
            text += f"   👤 {account.first_name or 'Не указано'}"
            if account.username:
                text += f" (@{account.username})"
            text += f"\n   {status}{banned}\n\n"
        
        await update.message.reply_text(text)
    
    async def remove_account_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда удаления аккаунта"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            accounts = session.query(Account).filter_by(user_id=user.id).all()
        
        if not accounts:
            await update.message.reply_text("📝 У вас нет аккаунтов для удаления")
            return
        
        keyboard = []
        for account in accounts:
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {account.phone_number}",
                    callback_data=f"account_delete_{account.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="account_cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "🗑 Выберите аккаунт для удаления:"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов для аккаунтов"""
        query = update.callback_query
        data = query.data
        
        if data == "account_add":
            await self._start_add_account(update, context)
        elif data == "account_list":
            await self.list_accounts_command(update, context)
        elif data == "account_remove":
            await self.remove_account_command(update, context)
        elif data == "account_refresh":
            await self._refresh_accounts_status(update, context)
        elif data == "account_cancel":
            context.user_data.clear()
            await query.edit_message_text("❌ Операция отменена")
        elif data.startswith("account_delete_"):
            account_id = int(data.split("_")[2])
            await self._delete_account(update, context, account_id)
    
    async def _refresh_accounts_status(self, update, context):
        """Обновление статуса аккаунтов"""
        user_id = update.effective_user.id
        
        await update.callback_query.edit_message_text("🔄 Обновление статуса аккаунтов...")
        
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.callback_query.edit_message_text("❌ Пользователь не найден")
                    return
                
                accounts = session.query(Account).filter_by(user_id=user.id).all()
                
                updated_count = 0
                for account in accounts:
                    try:
                        # Проверка статуса аккаунта
                        session_string = self.encryption.decrypt(account.session_string)
                        client = TelegramClient(
                            StringSession(session_string),
                            Config.API_ID,
                            Config.API_HASH
                        )
                        
                        await client.connect()
                        
                        if await client.is_user_authorized():
                            account.is_active = True
                            account.is_banned = False
                            updated_count += 1
                        else:
                            account.is_active = False
                        
                        await client.disconnect()
                        
                    except Exception as e:
                        logger.error(f"Error checking account {account.phone_number}: {e}")
                        account.is_active = False
                        if "banned" in str(e).lower():
                            account.is_banned = True
                
                session.commit()
            
            await update.callback_query.edit_message_text(
                f"✅ Статус обновлен для {updated_count} аккаунтов"
            )
            
        except Exception as e:
            logger.error(f"Error refreshing accounts status: {e}")
            await update.callback_query.edit_message_text(
                "❌ Ошибка при обновлении статуса аккаунтов"
            )
    
    async def _delete_account(self, update, context, account_id):
        """Удаление аккаунта"""
        user_id = update.effective_user.id
        
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.callback_query.edit_message_text("❌ Пользователь не найден")
                    return
                
                account = session.query(Account).filter_by(
                    id=account_id,
                    user_id=user.id
                ).first()
                
                if not account:
                    await update.callback_query.edit_message_text("❌ Аккаунт не найден")
                    return
                
                phone = account.phone_number
                session.delete(account)
                session.commit()
            
            await update.callback_query.edit_message_text(
                f"✅ Аккаунт {phone} успешно удален"
            )
            
        except Exception as e:
            logger.error(f"Error deleting account {account_id}: {e}")
            await update.callback_query.edit_message_text(
                "❌ Ошибка при удалении аккаунта"
            )

