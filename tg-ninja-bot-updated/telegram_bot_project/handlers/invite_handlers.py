import logging
import asyncio
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    PeerFloodError, UserPrivacyRestrictedError, UserNotMutualContactError,
    UserChannelsTooMuchError, FloodWaitError, ChatAdminRequiredError,
    UserAlreadyParticipantError, UserBannedInChannelError
)
from database.database import db_manager
from database.models import User, Account, Group, InviteTask, ActivityLog
from services.encryption import EncryptionService
from config import Config

logger = logging.getLogger(__name__)

class InviteHandlers:
    def __init__(self):
        self.encryption = EncryptionService()
        self.active_invites = {}  # Хранение активных процессов инвайтинга
    
    async def invite_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню инвайтинга"""
        user_id = update.effective_user.id
        
        # Получение статистики инвайтинга
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            total_tasks = session.query(InviteTask).filter_by(user_id=user.id).count()
            completed_tasks = session.query(InviteTask).filter_by(
                user_id=user.id, status='completed'
            ).count()
            
            total_invited = session.query(InviteTask).filter_by(
                user_id=user.id
            ).with_entities(
                session.query(InviteTask.invited_count).label('sum')
            ).scalar() or 0
        
        text = f"🎯 Инвайтинг пользователей\n\n"
        text += f"📊 Статистика:\n"
        text += f"• Всего задач: {total_tasks}\n"
        text += f"• Завершено: {completed_tasks}\n"
        text += f"• Приглашено пользователей: {total_invited}\n\n"
        
        # Проверка активного инвайтинга
        if user_id in self.active_invites:
            text += "🔄 Активный инвайтинг в процессе...\n"
        
        keyboard = [
            [InlineKeyboardButton("🎯 Пригласить пользователей", callback_data="invite_start")],
            [InlineKeyboardButton("📋 Список задач", callback_data="invite_list_tasks")],
            [InlineKeyboardButton("📊 Статус инвайтинга", callback_data="invite_status")],
            [InlineKeyboardButton("⏹ Остановить инвайтинг", callback_data="invite_stop")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def invite_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда инвайтинга пользователей"""
        await self._start_invite_process(update, context)
    
    async def _start_invite_process(self, update, context):
        """Начало процесса инвайтинга"""
        user_id = update.effective_user.id
        
        # Проверка наличия аккаунтов
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await self._send_message(update, "❌ Пользователь не найден")
                return
            
            accounts = session.query(Account).filter_by(
                user_id=user.id,
                is_active=True,
                is_banned=False
            ).all()
        
        if not accounts:
            await self._send_message(update, 
                "❌ У вас нет активных аккаунтов для инвайтинга.\n"
                "Добавьте аккаунт через /add_account"
            )
            return
        
        text = """
🎯 Инвайтинг пользователей в группу

Процесс инвайтинга состоит из нескольких шагов:

1️⃣ Добавьте бота в целевую группу как администратора
2️⃣ Отправьте ссылку на группу
3️⃣ Загрузите список пользователей (файл .txt или введите вручную)
4️⃣ Выберите аккаунт для инвайтинга
5️⃣ Запустите процесс

⚠️ Важно:
• Бот должен быть администратором в целевой группе
• Аккаунт должен иметь права на добавление участников
• Соблюдайте лимиты Telegram (не более 50 инвайтов в час)

Начнем с добавления ссылки на группу:
        """
        
        context.user_data['state'] = 'invite_group_input'
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="invite_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def handle_invite_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода данных для инвайтинга"""
        state = context.user_data.get('state')
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if state == 'invite_group_input':
            await self._handle_group_input(update, context, text, user_id)
        elif state == 'invite_users_input':
            await self._handle_users_input(update, context, text, user_id)
    
    async def _handle_group_input(self, update, context, group_link, user_id):
        """Обработка ввода ссылки на группу"""
        try:
            # Проверка и сохранение группы
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                account = session.query(Account).filter_by(
                    user_id=user.id,
                    is_active=True,
                    is_banned=False
                ).first()
                
                if not account:
                    await update.message.reply_text("❌ Нет активных аккаунтов")
                    return
                
                # Проверка доступа к группе
                session_string = self.encryption.decrypt(account.session_string)
                client = TelegramClient(
                    StringSession(session_string),
                    Config.API_ID,
                    Config.API_HASH
                )
                
                await client.connect()
                
                try:
                    entity = await client.get_entity(group_link)
                    
                    # Проверка прав администратора
                    permissions = await client.get_permissions(entity, 'me')
                    if not permissions.is_admin:
                        await update.message.reply_text(
                            "❌ Аккаунт должен быть администратором в этой группе"
                        )
                        await client.disconnect()
                        return
                    
                    # Сохранение информации о группе
                    group = session.query(Group).filter_by(
                        telegram_id=str(entity.id)
                    ).first()
                    
                    if not group:
                        group = Group(
                            telegram_id=str(entity.id),
                            title=entity.title,
                            username=getattr(entity, 'username', None),
                            is_channel=not getattr(entity, 'megagroup', False),
                            member_count=getattr(entity, 'participants_count', 0)
                        )
                        session.add(group)
                        session.flush()
                    
                    context.user_data['target_group_id'] = group.id
                    context.user_data['state'] = 'invite_users_input'
                    
                    await update.message.reply_text(
                        f"✅ Группа '{entity.title}' подтверждена!\n\n"
                        "Теперь отправьте список пользователей для инвайтинга:\n"
                        "• Можно отправить файл .txt со списком\n"
                        "• Или введите usernames через запятую или с новой строки\n"
                        "• Формат: @username или просто username"
                    )
                    
                    session.commit()
                    
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Ошибка доступа к группе: {str(e)}"
                    )
                finally:
                    await client.disconnect()
                    
        except Exception as e:
            logger.error(f"Error handling group input: {e}")
            await update.message.reply_text("❌ Ошибка при обработке группы")
    
    async def _handle_users_input(self, update, context, text, user_id):
        """Обработка ввода списка пользователей"""
        # Парсинг пользователей
        usernames = []
        
        # Проверка на загруженный файл
        if 'uploaded_usernames' in context.user_data:
            usernames = context.user_data['uploaded_usernames']
            del context.user_data['uploaded_usernames']
        else:
            # Парсинг из текста
            for line in text.replace(',', '\n').split('\n'):
                username = line.strip()
                if username:
                    if username.startswith('@'):
                        username = username[1:]
                    if username:
                        usernames.append(username)
        
        if not usernames:
            await update.message.reply_text(
                "❌ Не найдено пользователей. Попробуйте еще раз:"
            )
            return
        
        # Выбор аккаунта для инвайтинга
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            accounts = session.query(Account).filter_by(
                user_id=user.id,
                is_active=True,
                is_banned=False
            ).all()
        
        context.user_data['invite_usernames'] = usernames
        
        if len(accounts) == 1:
            # Если аккаунт один, сразу начинаем инвайтинг
            await self._start_invite_task(update, context, accounts[0], user_id)
        else:
            # Выбор аккаунта
            keyboard = []
            for account in accounts:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📱 {account.phone_number}",
                        callback_data=f"invite_account_{account.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="invite_cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            context.user_data['state'] = 'invite_account_select'
            
            await update.message.reply_text(
                f"📱 Выберите аккаунт для инвайтинга {len(usernames)} пользователей:",
                reply_markup=reply_markup
            )
    
    async def _start_invite_task(self, update, context, account, user_id):
        """Запуск задачи инвайтинга"""
        try:
            target_group_id = context.user_data.get('target_group_id')
            usernames = context.user_data.get('invite_usernames', [])
            
            if not target_group_id or not usernames:
                await self._send_message(update, "❌ Недостаточно данных для инвайтинга")
                return
            
            # Создание задачи в базе данных
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                
                invite_task = InviteTask(
                    user_id=user.id,
                    account_id=account.id,
                    target_group_id=target_group_id,
                    user_list=json.dumps(usernames),
                    status='pending'
                )
                session.add(invite_task)
                session.flush()
                
                task_id = invite_task.id
                session.commit()
            
            # Отметка о начале инвайтинга
            self.active_invites[user_id] = {
                'task_id': task_id,
                'status': 'starting',
                'total_users': len(usernames),
                'processed_users': 0,
                'invited_count': 0,
                'failed_count': 0,
                'start_time': datetime.utcnow()
            }
            
            await self._send_message(update, 
                f"🔄 Начинаю инвайтинг {len(usernames)} пользователей...\n"
                f"Используется аккаунт: {account.phone_number}\n\n"
                f"⚠️ Процесс может занять время из-за лимитов Telegram"
            )
            
            # Запуск инвайтинга в фоне
            asyncio.create_task(
                self._invite_users_background(task_id, account, user_id)
            )
            
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error starting invite task: {e}")
            await self._send_message(update, "❌ Ошибка при запуске инвайтинга")
            if user_id in self.active_invites:
                del self.active_invites[user_id]
    
    async def _invite_users_background(self, task_id, account, user_id):
        """Фоновый процесс инвайтинга пользователей"""
        try:
            # Получение данных задачи
            with db_manager.get_session() as session:
                task = session.query(InviteTask).filter_by(id=task_id).first()
                if not task:
                    raise Exception("Task not found")
                
                usernames = json.loads(task.user_list)
                target_group = session.query(Group).filter_by(id=task.target_group_id).first()
                
                if not target_group:
                    raise Exception("Target group not found")
            
            # Создание клиента
            session_string = self.encryption.decrypt(account.session_string)
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                raise Exception("Account is not authorized")
            
            # Получение сущности группы
            group_entity = await client.get_entity(int(target_group.telegram_id))
            
            invited_count = 0
            failed_count = 0
            
            # Обновление статуса задачи
            with db_manager.get_session() as session:
                task = session.query(InviteTask).filter_by(id=task_id).first()
                task.status = 'in_progress'
                session.commit()
            
            for i, username in enumerate(usernames):
                try:
                    # Обновление статуса
                    if user_id in self.active_invites:
                        self.active_invites[user_id]['status'] = 'inviting'
                        self.active_invites[user_id]['processed_users'] = i + 1
                        self.active_invites[user_id]['current_user'] = username
                    
                    # Попытка инвайтинга
                    try:
                        user_entity = await client.get_entity(username)
                        await client.invite_to_chat(group_entity, user_entity)
                        invited_count += 1
                        
                        # Обновление статистики
                        if user_id in self.active_invites:
                            self.active_invites[user_id]['invited_count'] = invited_count
                        
                        logger.info(f"Successfully invited {username} to group")
                        
                    except UserAlreadyParticipantError:
                        logger.info(f"User {username} is already in the group")
                        continue
                    except UserPrivacyRestrictedError:
                        logger.warning(f"User {username} has privacy restrictions")
                        failed_count += 1
                    except UserNotMutualContactError:
                        logger.warning(f"User {username} is not a mutual contact")
                        failed_count += 1
                    except UserChannelsTooMuchError:
                        logger.warning(f"User {username} is in too many channels")
                        failed_count += 1
                    except UserBannedInChannelError:
                        logger.warning(f"User {username} is banned in the channel")
                        failed_count += 1
                    except PeerFloodError:
                        logger.error("Peer flood error - too many requests")
                        # Увеличиваем паузу при флуд-ошибке
                        await asyncio.sleep(300)  # 5 минут
                        failed_count += 1
                    except FloodWaitError as e:
                        logger.warning(f"Flood wait for {e.seconds} seconds")
                        await asyncio.sleep(e.seconds)
                        # Повторная попытка после ожидания
                        try:
                            await client.invite_to_chat(group_entity, user_entity)
                            invited_count += 1
                        except:
                            failed_count += 1
                    except Exception as e:
                        logger.error(f"Error inviting {username}: {e}")
                        failed_count += 1
                    
                    # Обновление статистики в активных инвайтах
                    if user_id in self.active_invites:
                        self.active_invites[user_id]['failed_count'] = failed_count
                    
                    # Пауза между инвайтами (важно для избежания блокировок)
                    await asyncio.sleep(30)  # 30 секунд между инвайтами
                    
                    # Проверка лимитов (не более 50 в час)
                    if invited_count >= Config.MAX_INVITES_PER_HOUR:
                        logger.info("Hourly invite limit reached, pausing...")
                        await asyncio.sleep(3600)  # Ждем час
                        invited_count = 0  # Сброс счетчика для следующего часа
                    
                except Exception as e:
                    logger.error(f"Error processing user {username}: {e}")
                    failed_count += 1
            
            # Завершение задачи
            with db_manager.get_session() as session:
                task = session.query(InviteTask).filter_by(id=task_id).first()
                task.status = 'completed'
                task.invited_count = invited_count
                task.failed_count = failed_count
                session.commit()
            
            # Обновление статуса
            if user_id in self.active_invites:
                self.active_invites[user_id]['status'] = 'completed'
            
            # Логирование завершения
            await self._log_activity(
                user_id, account.id, 'invite', target_group.title,
                'success', f"Invited {invited_count} users, failed {failed_count}"
            )
            
            logger.info(f"Invite task {task_id} completed: {invited_count} invited, {failed_count} failed")
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"Background invite error for task {task_id}: {e}")
            
            # Обновление статуса ошибки
            with db_manager.get_session() as session:
                task = session.query(InviteTask).filter_by(id=task_id).first()
                if task:
                    task.status = 'failed'
                    task.error_message = str(e)
                    session.commit()
            
            if user_id in self.active_invites:
                self.active_invites[user_id]['status'] = 'error'
                self.active_invites[user_id]['error'] = str(e)
        finally:
            # Очистка через 1 час
            await asyncio.sleep(3600)
            if user_id in self.active_invites:
                del self.active_invites[user_id]
    
    async def invite_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда проверки статуса инвайтинга"""
        user_id = update.effective_user.id
        
        if user_id not in self.active_invites:
            # Проверка последних задач в базе данных
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.message.reply_text("❌ Пользователь не найден")
                    return
                
                recent_tasks = session.query(InviteTask).filter_by(
                    user_id=user.id
                ).order_by(InviteTask.created_at.desc()).limit(5).all()
                
                if not recent_tasks:
                    await update.message.reply_text("📊 Нет задач инвайтинга")
                    return
                
                text = "📊 Последние задачи инвайтинга:\n\n"
                for task in recent_tasks:
                    status_emoji = {
                        'pending': '⏳',
                        'in_progress': '🔄',
                        'completed': '✅',
                        'failed': '❌'
                    }.get(task.status, '❓')
                    
                    text += f"{status_emoji} ID: {task.id}\n"
                    text += f"   Статус: {task.status}\n"
                    text += f"   Приглашено: {task.invited_count}\n"
                    text += f"   Ошибок: {task.failed_count}\n"
                    text += f"   Дата: {task.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                
                await update.message.reply_text(text)
                return
        
        status = self.active_invites[user_id]
        
        text = "📊 Статус инвайтинга:\n\n"
        text += f"🔄 Статус: {status['status']}\n"
        text += f"👥 Обработано: {status['processed_users']}/{status['total_users']}\n"
        text += f"✅ Приглашено: {status['invited_count']}\n"
        text += f"❌ Ошибок: {status['failed_count']}\n"
        
        if 'current_user' in status:
            text += f"👤 Текущий пользователь: @{status['current_user']}\n"
        
        elapsed = datetime.utcnow() - status['start_time']
        text += f"⏱ Время работы: {str(elapsed).split('.')[0]}\n"
        
        if status['status'] == 'error':
            text += f"❌ Ошибка: {status.get('error', 'Unknown error')}\n"
        
        await update.message.reply_text(text)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов для инвайтинга"""
        query = update.callback_query
        data = query.data
        
        if data == "invite_start":
            await self._start_invite_process(update, context)
        elif data == "invite_status":
            await self.invite_status_command(update, context)
        elif data == "invite_list_tasks":
            await self._list_invite_tasks(update, context)
        elif data == "invite_stop":
            await self._stop_invite_process(update, context)
        elif data == "invite_cancel":
            context.user_data.clear()
            await query.edit_message_text("❌ Операция отменена")
        elif data.startswith("invite_account_"):
            account_id = int(data.split("_")[2])
            await self._handle_account_selection(update, context, account_id)
    
    async def _handle_account_selection(self, update, context, account_id):
        """Обработка выбора аккаунта для инвайтинга"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                await update.callback_query.edit_message_text("❌ Аккаунт не найден")
                return
        
        await self._start_invite_task(update, context, account, user_id)
    
    async def _list_invite_tasks(self, update, context):
        """Список задач инвайтинга"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            tasks = session.query(InviteTask).filter_by(
                user_id=user.id
            ).order_by(InviteTask.created_at.desc()).limit(10).all()
        
        if not tasks:
            await update.callback_query.edit_message_text("📝 Нет задач инвайтинга")
            return
        
        text = "📋 Задачи инвайтинга:\n\n"
        for task in tasks:
            status_emoji = {
                'pending': '⏳',
                'in_progress': '🔄',
                'completed': '✅',
                'failed': '❌'
            }.get(task.status, '❓')
            
            text += f"{status_emoji} ID: {task.id}\n"
            text += f"   Группа: {task.target_group.title}\n"
            text += f"   Аккаунт: {task.account.phone_number}\n"
            text += f"   Приглашено: {task.invited_count}\n"
            text += f"   Ошибок: {task.failed_count}\n"
            text += f"   Дата: {task.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        
        await update.callback_query.edit_message_text(text)
    
    async def _stop_invite_process(self, update, context):
        """Остановка процесса инвайтинга"""
        user_id = update.effective_user.id
        
        if user_id not in self.active_invites:
            await update.callback_query.edit_message_text("📊 Нет активного инвайтинга")
            return
        
        # Отметка об остановке
        self.active_invites[user_id]['status'] = 'stopped'
        
        # Обновление статуса задачи в базе данных
        task_id = self.active_invites[user_id]['task_id']
        with db_manager.get_session() as session:
            task = session.query(InviteTask).filter_by(id=task_id).first()
            if task:
                task.status = 'failed'
                task.error_message = 'Stopped by user'
                session.commit()
        
        await update.callback_query.edit_message_text("⏹ Инвайтинг остановлен")
        
        # Удаление из активных процессов
        del self.active_invites[user_id]
    
    async def _log_activity(self, user_id, account_id, action_type, target, status, details):
        """Логирование активности"""
        try:
            with db_manager.get_session() as session:
                log = ActivityLog(
                    user_id=session.query(User).filter_by(telegram_id=user_id).first().id,
                    account_id=account_id,
                    action_type=action_type,
                    target=target,
                    status=status,
                    details=details
                )
                session.add(log)
                session.commit()
        except Exception as e:
            logger.error(f"Error logging activity: {e}")
    
    async def _send_message(self, update, text, reply_markup=None):
        """Универсальная отправка сообщения"""
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)

