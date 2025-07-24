import logging
import asyncio
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import ChannelPrivateError, ChatAdminRequiredError, FloodWaitError
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch, InputChannel
from database.database import db_manager
from database.models import User, Account, Group, ParsedUser, ActivityLog
from services.encryption import EncryptionService
from config import Config

logger = logging.getLogger(__name__)

class ParsingHandlers:
    def __init__(self):
        self.encryption = EncryptionService()
        self.active_parsing = {}  # Хранение активных процессов парсинга
    
    async def parsing_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню парсинга"""
        user_id = update.effective_user.id
        
        # Получение статистики парсинга
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            parsed_count = session.query(ParsedUser).join(Group).filter(
                Group.id.in_(
                    session.query(Group.id).join(Account).filter(Account.user_id == user.id)
                )
            ).count()
            
            groups_count = session.query(Group).join(Account).filter(
                Account.user_id == user.id
            ).count()
        
        text = f"👥 Парсинг пользователей\n\n"
        text += f"📊 Статистика:\n"
        text += f"• Спарсено пользователей: {parsed_count}\n"
        text += f"• Обработано групп: {groups_count}\n\n"
        
        # Проверка активного парсинга
        if user_id in self.active_parsing:
            text += "🔄 Активный парсинг в процессе...\n"
        
        keyboard = [
            [InlineKeyboardButton("🔍 Парсить группу", callback_data="parse_start")],
            [InlineKeyboardButton("📋 Список групп", callback_data="parse_list_groups")],
            [InlineKeyboardButton("📊 Статус парсинга", callback_data="parse_status")],
            [InlineKeyboardButton("📁 Экспорт данных", callback_data="parse_export")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def parse_group_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда парсинга группы"""
        await self._start_parse_group(update, context)
    
    async def _start_parse_group(self, update, context):
        """Начало процесса парсинга группы"""
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
                "❌ У вас нет активных аккаунтов для парсинга.\n"
                "Добавьте аккаунт через /add_account"
            )
            return
        
        text = """
🔍 Парсинг пользователей из группы/канала

Отправьте ссылку на группу или канал в одном из форматов:
• https://t.me/channel_name
• @channel_name
• Приватная ссылка (https://t.me/+...)

Можно отправить несколько ссылок, каждую с новой строки.

⚠️ Важно:
• Аккаунт должен быть участником группы/канала
• Для закрытых групп нужны права администратора
• Парсинг может занять время для больших групп
        """
        
        context.user_data['state'] = 'parse_group_input'
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="parse_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def handle_parse_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода данных для парсинга"""
        state = context.user_data.get('state')
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if state == 'parse_group_input':
            await self._handle_group_links_input(update, context, text, user_id)
    
    async def _handle_group_links_input(self, update, context, text, user_id):
        """Обработка ввода ссылок на группы"""
        # Парсинг ссылок
        links = [link.strip() for link in text.split('\n') if link.strip()]
        
        if not links:
            await update.message.reply_text("❌ Не найдено ссылок. Попробуйте еще раз:")
            return
        
        # Выбор аккаунта для парсинга
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            accounts = session.query(Account).filter_by(
                user_id=user.id,
                is_active=True,
                is_banned=False
            ).all()
        
        if len(accounts) == 1:
            # Если аккаунт один, сразу начинаем парсинг
            await self._start_parsing_process(update, context, links, accounts[0], user_id)
        else:
            # Выбор аккаунта
            keyboard = []
            for account in accounts:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📱 {account.phone_number}",
                        callback_data=f"parse_account_{account.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="parse_cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            context.user_data['parse_links'] = links
            context.user_data['state'] = 'parse_account_select'
            
            await update.message.reply_text(
                "📱 Выберите аккаунт для парсинга:",
                reply_markup=reply_markup
            )
    
    async def _start_parsing_process(self, update, context, links, account, user_id):
        """Запуск процесса парсинга"""
        try:
            # Отметка о начале парсинга
            self.active_parsing[user_id] = {
                'status': 'starting',
                'total_links': len(links),
                'processed_links': 0,
                'total_users': 0,
                'start_time': datetime.utcnow()
            }
            
            await self._send_message(update, 
                f"🔄 Начинаю парсинг {len(links)} групп/каналов...\n"
                f"Используется аккаунт: {account.phone_number}"
            )
            
            # Запуск парсинга в фоне
            asyncio.create_task(
                self._parse_groups_background(links, account, user_id)
            )
            
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error starting parsing process: {e}")
            await self._send_message(update, "❌ Ошибка при запуске парсинга")
            if user_id in self.active_parsing:
                del self.active_parsing[user_id]
    
    async def _parse_groups_background(self, links, account, user_id):
        """Фоновый процесс парсинга групп"""
        try:
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
            
            total_parsed = 0
            
            for i, link in enumerate(links):
                try:
                    # Обновление статуса
                    self.active_parsing[user_id]['status'] = 'parsing'
                    self.active_parsing[user_id]['processed_links'] = i + 1
                    self.active_parsing[user_id]['current_link'] = link
                    
                    # Парсинг группы
                    parsed_count = await self._parse_single_group(client, link, account, user_id)
                    total_parsed += parsed_count
                    
                    self.active_parsing[user_id]['total_users'] = total_parsed
                    
                    # Пауза между группами
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Error parsing group {link}: {e}")
                    await self._log_activity(user_id, account.id, 'parse', link, 'failed', str(e))
            
            # Завершение парсинга
            self.active_parsing[user_id]['status'] = 'completed'
            
            # Создание файла с результатами
            file_path = await self._create_export_file(user_id, account.id)
            
            # Уведомление о завершении (здесь нужно будет добавить отправку через бота)
            logger.info(f"Parsing completed for user {user_id}: {total_parsed} users parsed")
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"Background parsing error for user {user_id}: {e}")
            if user_id in self.active_parsing:
                self.active_parsing[user_id]['status'] = 'error'
                self.active_parsing[user_id]['error'] = str(e)
        finally:
            # Очистка через 1 час
            await asyncio.sleep(3600)
            if user_id in self.active_parsing:
                del self.active_parsing[user_id]
    
    async def _parse_single_group(self, client, link, account, user_id):
        """Парсинг одной группы"""
        try:
            # Получение сущности группы
            entity = await client.get_entity(link)
            
            # Сохранение информации о группе
            group = await self._save_group_info(entity, account.id)
            
            # Получение участников
            participants = []
            offset = 0
            limit = 200
            
            while True:
                try:
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        # Для супергрупп
                        result = await client(GetParticipantsRequest(
                            channel=entity,
                            filter=ChannelParticipantsSearch(''),
                            offset=offset,
                            limit=limit,
                            hash=0
                        ))
                    else:
                        # Для каналов
                        result = await client.get_participants(
                            entity,
                            limit=limit,
                            offset=offset
                        )
                    
                    if not result.users:
                        break
                    
                    participants.extend(result.users)
                    offset += limit
                    
                    # Пауза для избежания флуд-лимитов
                    await asyncio.sleep(1)
                    
                    # Ограничение на количество пользователей (для избежания слишком долгого парсинга)
                    if len(participants) >= 10000:
                        break
                        
                except FloodWaitError as e:
                    logger.warning(f"Flood wait for {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"Error getting participants: {e}")
                    break
            
            # Сохранение пользователей
            saved_count = await self._save_parsed_users(participants, group.id)
            
            # Логирование успешного парсинга
            await self._log_activity(
                user_id, account.id, 'parse', link, 'success',
                f"Parsed {saved_count} users"
            )
            
            return saved_count
            
        except ChannelPrivateError:
            raise Exception("Channel is private and account is not a member")
        except ChatAdminRequiredError:
            raise Exception("Admin rights required for this group")
        except Exception as e:
            raise Exception(f"Failed to parse group: {str(e)}")
    
    async def _save_group_info(self, entity, account_id):
        """Сохранение информации о группе"""
        with db_manager.get_session() as session:
            # Проверка существования группы
            group = session.query(Group).filter_by(
                telegram_id=str(entity.id)
            ).first()
            
            if not group:
                group = Group(
                    telegram_id=str(entity.id),
                    title=entity.title,
                    username=getattr(entity, 'username', None),
                    is_channel=not getattr(entity, 'megagroup', False),
                    is_private=getattr(entity, 'access_hash', None) is not None,
                    member_count=getattr(entity, 'participants_count', 0),
                    description=getattr(entity, 'about', None)
                )
                session.add(group)
                session.flush()
            else:
                # Обновление информации
                group.title = entity.title
                group.username = getattr(entity, 'username', None)
                group.member_count = getattr(entity, 'participants_count', 0)
                group.description = getattr(entity, 'about', None)
            
            # Связывание с аккаунтом
            account = session.query(Account).filter_by(id=account_id).first()
            if account and group not in account.groups:
                account.groups.append(group)
            
            session.commit()
            return group
    
    async def _save_parsed_users(self, participants, group_id):
        """Сохранение спарсенных пользователей"""
        saved_count = 0
        
        with db_manager.get_session() as session:
            for user in participants:
                if user.bot:
                    continue  # Пропускаем ботов
                
                # Проверка существования пользователя
                existing_user = session.query(ParsedUser).filter_by(
                    telegram_id=user.id,
                    source_group_id=group_id
                ).first()
                
                if not existing_user:
                    parsed_user = ParsedUser(
                        telegram_id=user.id,
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        phone_number=getattr(user, 'phone', None),
                        source_group_id=group_id,
                        is_bot=user.bot,
                        is_premium=getattr(user, 'premium', False),
                        last_seen=getattr(user, 'status', {}).get('was_online', None) if hasattr(getattr(user, 'status', {}), 'was_online') else None
                    )
                    session.add(parsed_user)
                    saved_count += 1
            
            session.commit()
        
        return saved_count
    
    async def _create_export_file(self, user_id, account_id):
        """Создание файла экспорта с пользователями"""
        try:
            with db_manager.get_session() as session:
                # Получение всех спарсенных пользователей для данного аккаунта
                parsed_users = session.query(ParsedUser).join(Group).join(
                    Account.groups
                ).filter(Account.id == account_id).all()
                
                if not parsed_users:
                    return None
                
                # Создание файла
                filename = f"parsed_users_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                file_path = os.path.join(Config.DATA_DIR, filename)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("# Спарсенные пользователи\n")
                    f.write(f"# Дата создания: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# Всего пользователей: {len(parsed_users)}\n\n")
                    
                    for user in parsed_users:
                        if user.username:
                            f.write(f"@{user.username}\n")
                        elif user.first_name:
                            f.write(f"{user.first_name}")
                            if user.last_name:
                                f.write(f" {user.last_name}")
                            f.write(f" (ID: {user.telegram_id})\n")
                        else:
                            f.write(f"ID: {user.telegram_id}\n")
                
                return file_path
                
        except Exception as e:
            logger.error(f"Error creating export file: {e}")
            return None
    
    async def parse_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда проверки статуса парсинга"""
        user_id = update.effective_user.id
        
        if user_id not in self.active_parsing:
            await update.message.reply_text("📊 Активный парсинг не найден")
            return
        
        status = self.active_parsing[user_id]
        
        text = "📊 Статус парсинга:\n\n"
        text += f"🔄 Статус: {status['status']}\n"
        text += f"📁 Обработано групп: {status['processed_links']}/{status['total_links']}\n"
        text += f"👥 Всего пользователей: {status['total_users']}\n"
        
        if 'current_link' in status:
            text += f"🔍 Текущая группа: {status['current_link']}\n"
        
        elapsed = datetime.utcnow() - status['start_time']
        text += f"⏱ Время работы: {str(elapsed).split('.')[0]}\n"
        
        if status['status'] == 'error':
            text += f"❌ Ошибка: {status.get('error', 'Unknown error')}\n"
        
        await update.message.reply_text(text)
    
    async def handle_user_list_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка загруженного файла со списком пользователей"""
        document = update.message.document
        user_id = update.effective_user.id
        
        try:
            # Скачивание файла
            file = await context.bot.get_file(document.file_id)
            file_path = os.path.join(Config.DATA_DIR, f"upload_{user_id}_{document.file_name}")
            await file.download_to_drive(file_path)
            
            # Чтение файла
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Парсинг пользователей из файла
            usernames = []
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('@'):
                        usernames.append(line[1:])  # Убираем @
                    elif line:
                        usernames.append(line)
            
            if usernames:
                # Сохранение списка для дальнейшего использования
                context.user_data['uploaded_usernames'] = usernames
                
                text = f"📁 Файл обработан успешно!\n\n"
                text += f"👥 Найдено пользователей: {len(usernames)}\n"
                text += f"📝 Примеры:\n"
                
                for i, username in enumerate(usernames[:5]):
                    text += f"• @{username}\n"
                
                if len(usernames) > 5:
                    text += f"... и еще {len(usernames) - 5}\n"
                
                text += "\nИспользуйте эти данные для инвайтинга или других операций."
                
                await update.message.reply_text(text)
            else:
                await update.message.reply_text("❌ В файле не найдено пользователей")
            
            # Удаление временного файла
            os.remove(file_path)
            
        except Exception as e:
            logger.error(f"Error processing user list file: {e}")
            await update.message.reply_text("❌ Ошибка при обработке файла")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов для парсинга"""
        query = update.callback_query
        data = query.data
        
        if data == "parse_start":
            await self._start_parse_group(update, context)
        elif data == "parse_status":
            await self.parse_status_command(update, context)
        elif data == "parse_list_groups":
            await self._list_parsed_groups(update, context)
        elif data == "parse_export":
            await self._export_parsed_data(update, context)
        elif data == "parse_cancel":
            context.user_data.clear()
            await query.edit_message_text("❌ Операция отменена")
        elif data.startswith("parse_account_"):
            account_id = int(data.split("_")[2])
            await self._handle_account_selection(update, context, account_id)
    
    async def _handle_account_selection(self, update, context, account_id):
        """Обработка выбора аккаунта для парсинга"""
        user_id = update.effective_user.id
        links = context.user_data.get('parse_links', [])
        
        if not links:
            await update.callback_query.edit_message_text("❌ Ссылки не найдены")
            return
        
        with db_manager.get_session() as session:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                await update.callback_query.edit_message_text("❌ Аккаунт не найден")
                return
        
        await self._start_parsing_process(update, context, links, account, user_id)
    
    async def _list_parsed_groups(self, update, context):
        """Список спарсенных групп"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            groups = session.query(Group).join(Account).filter(
                Account.user_id == user.id
            ).all()
        
        if not groups:
            await update.callback_query.edit_message_text("📝 Нет спарсенных групп")
            return
        
        text = "📋 Спарсенные группы:\n\n"
        for i, group in enumerate(groups, 1):
            text += f"{i}. {group.title}\n"
            if group.username:
                text += f"   @{group.username}\n"
            text += f"   👥 Участников: {group.member_count}\n"
            text += f"   📊 Спарсено: {len(group.parsed_users)}\n\n"
        
        await update.callback_query.edit_message_text(text)
    
    async def _export_parsed_data(self, update, context):
        """Экспорт спарсенных данных"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            # Получение первого активного аккаунта
            account = session.query(Account).filter_by(
                user_id=user.id,
                is_active=True
            ).first()
            
            if not account:
                await update.callback_query.edit_message_text("❌ Нет активных аккаунтов")
                return
        
        await update.callback_query.edit_message_text("📁 Создание файла экспорта...")
        
        file_path = await self._create_export_file(user_id, account.id)
        
        if file_path and os.path.exists(file_path):
            # Отправка файла пользователю
            with open(file_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=os.path.basename(file_path),
                    caption="📁 Экспорт спарсенных пользователей"
                )
            
            # Удаление временного файла
            os.remove(file_path)
            
            await update.callback_query.edit_message_text("✅ Файл отправлен!")
        else:
            await update.callback_query.edit_message_text("❌ Нет данных для экспорта")
    
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

