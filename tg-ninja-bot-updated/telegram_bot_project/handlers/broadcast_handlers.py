import logging
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import db_manager
from database.models import User, Account, Group, AutoPost, ActivityLog
from services.scheduler import SchedulerService
from config import Config

logger = logging.getLogger(__name__)

class BroadcastHandlers:
    def __init__(self):
        self.scheduler = None
    
    def set_scheduler(self, scheduler: SchedulerService):
        """Установка планировщика"""
        self.scheduler = scheduler
    
    async def broadcast_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню рассылок"""
        user_id = update.effective_user.id
        
        # Получение статистики рассылок
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            total_broadcasts = session.query(AutoPost).filter_by(user_id=user.id).count()
            active_broadcasts = session.query(AutoPost).filter_by(
                user_id=user.id, is_active=True
            ).count()
            
            total_sent = session.query(AutoPost).filter_by(
                user_id=user.id
            ).with_entities(
                session.query(AutoPost.total_sent).label('sum')
            ).scalar() or 0
        
        text = f"📨 Авто-рассылки\n\n"
        text += f"📊 Статистика:\n"
        text += f"• Всего рассылок: {total_broadcasts}\n"
        text += f"• Активных: {active_broadcasts}\n"
        text += f"• Отправлено сообщений: {total_sent}\n\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать рассылку", callback_data="broadcast_create")],
            [InlineKeyboardButton("📋 Список рассылок", callback_data="broadcast_list")],
            [InlineKeyboardButton("📊 Статистика", callback_data="broadcast_stats")],
            [InlineKeyboardButton("⏹ Остановить все", callback_data="broadcast_stop_all")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def create_broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда создания рассылки"""
        await self._start_create_broadcast(update, context)
    
    async def _start_create_broadcast(self, update, context):
        """Начало создания рассылки"""
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
                "❌ У вас нет активных аккаунтов для рассылки.\n"
                "Добавьте аккаунт через /add_account"
            )
            return
        
        text = """
📨 Создание авто-рассылки

Процесс создания состоит из нескольких шагов:

1️⃣ Написать текст сообщения для рассылки
2️⃣ Выбрать периодичность отправки
3️⃣ Выбрать аккаунт для рассылки
4️⃣ Выбрать группы для рассылки
5️⃣ Запустить рассылку

⚠️ Важно:
• Соблюдайте правила Telegram
• Не отправляйте спам
• Рекомендуемый интервал: не менее 1 часа
• Аккаунт должен быть участником групп

Начнем с текста сообщения. Напишите сообщение для рассылки:
        """
        
        context.user_data['state'] = 'broadcast_message_input'
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def handle_broadcast_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода данных для рассылки"""
        state = context.user_data.get('state')
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if state == 'broadcast_message_input':
            await self._handle_message_input(update, context, text, user_id)
        elif state == 'broadcast_interval_input':
            await self._handle_interval_input(update, context, text, user_id)
    
    async def _handle_message_input(self, update, context, message_text, user_id):
        """Обработка ввода текста сообщения"""
        if len(message_text) < 10:
            await update.message.reply_text(
                "❌ Сообщение слишком короткое. Минимум 10 символов."
            )
            return
        
        if len(message_text) > 4000:
            await update.message.reply_text(
                "❌ Сообщение слишком длинное. Максимум 4000 символов."
            )
            return
        
        context.user_data['broadcast_message'] = message_text
        
        # Выбор периодичности
        keyboard = [
            [InlineKeyboardButton("⏰ 1 час", callback_data="broadcast_interval_3600")],
            [InlineKeyboardButton("⏰ 3 часа", callback_data="broadcast_interval_10800")],
            [InlineKeyboardButton("⏰ 6 часов", callback_data="broadcast_interval_21600")],
            [InlineKeyboardButton("⏰ 12 часов", callback_data="broadcast_interval_43200")],
            [InlineKeyboardButton("⏰ 24 часа", callback_data="broadcast_interval_86400")],
            [InlineKeyboardButton("⚙️ Свой интервал", callback_data="broadcast_interval_custom")],
            [InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Сообщение сохранено!\n\n"
            f"Предварительный просмотр:\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{message_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Теперь выберите периодичность отправки:",
            reply_markup=reply_markup
        )
    
    async def _handle_interval_input(self, update, context, interval_text, user_id):
        """Обработка ввода пользовательского интервала"""
        try:
            # Парсинг интервала
            if interval_text.endswith('м'):
                interval_seconds = int(interval_text[:-1]) * 60
            elif interval_text.endswith('ч'):
                interval_seconds = int(interval_text[:-1]) * 3600
            elif interval_text.endswith('д'):
                interval_seconds = int(interval_text[:-1]) * 86400
            else:
                interval_seconds = int(interval_text) * 60  # По умолчанию в минутах
            
            # Проверка лимитов
            if interval_seconds < Config.MIN_AUTO_POST_INTERVAL:
                await update.message.reply_text(
                    f"❌ Минимальный интервал: {Config.MIN_AUTO_POST_INTERVAL // 60} минут"
                )
                return
            
            if interval_seconds > Config.MAX_AUTO_POST_INTERVAL:
                await update.message.reply_text(
                    f"❌ Максимальный интервал: {Config.MAX_AUTO_POST_INTERVAL // 3600} часов"
                )
                return
            
            context.user_data['broadcast_interval'] = interval_seconds
            await self._select_account(update, context, user_id)
            
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат интервала.\n"
                "Примеры: 30м, 2ч, 1д или просто число в минутах"
            )
    
    async def _select_account(self, update, context, user_id):
        """Выбор аккаунта для рассылки"""
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            accounts = session.query(Account).filter_by(
                user_id=user.id,
                is_active=True,
                is_banned=False
            ).all()
        
        if len(accounts) == 1:
            # Если аккаунт один, сразу переходим к выбору групп
            context.user_data['broadcast_account_id'] = accounts[0].id
            await self._select_groups(update, context, user_id)
        else:
            # Выбор аккаунта
            keyboard = []
            for account in accounts:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📱 {account.phone_number}",
                        callback_data=f"broadcast_account_{account.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = "📱 Выберите аккаунт для рассылки:"
            await self._send_message(update, text, reply_markup)
    
    async def _select_groups(self, update, context, user_id):
        """Выбор групп для рассылки"""
        account_id = context.user_data.get('broadcast_account_id')
        
        with db_manager.get_session() as session:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                await self._send_message(update, "❌ Аккаунт не найден")
                return
            
            # Получение групп, связанных с аккаунтом
            groups = account.groups
        
        if not groups:
            await self._send_message(update, 
                "❌ У выбранного аккаунта нет связанных групп.\n"
                "Сначала выполните парсинг групп."
            )
            return
        
        # Сохранение списка групп для выбора
        context.user_data['available_groups'] = [
            {'id': group.id, 'title': group.title, 'selected': False}
            for group in groups
        ]
        
        await self._show_groups_selection(update, context)
    
    async def _show_groups_selection(self, update, context):
        """Отображение списка групп для выбора"""
        groups = context.user_data.get('available_groups', [])
        
        text = "📋 Выберите группы для рассылки:\n\n"
        
        keyboard = []
        for i, group in enumerate(groups):
            status = "✅" if group['selected'] else "☐"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {group['title'][:30]}",
                    callback_data=f"broadcast_group_toggle_{i}"
                )
            ])
        
        selected_count = sum(1 for g in groups if g['selected'])
        
        if selected_count > 0:
            text += f"Выбрано групп: {selected_count}\n"
            keyboard.append([
                InlineKeyboardButton("✅ Создать рассылку", callback_data="broadcast_create_final")
            ])
        else:
            text += "Выберите хотя бы одну группу\n"
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def _create_final_broadcast(self, update, context, user_id):
        """Финальное создание рассылки"""
        try:
            message_text = context.user_data.get('broadcast_message')
            interval_seconds = context.user_data.get('broadcast_interval')
            account_id = context.user_data.get('broadcast_account_id')
            groups = context.user_data.get('available_groups', [])
            
            selected_groups = [g for g in groups if g['selected']]
            
            if not all([message_text, interval_seconds, account_id, selected_groups]):
                await self._send_message(update, "❌ Недостаточно данных для создания рассылки")
                return
            
            # Создание рассылки в базе данных
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                
                target_group_ids = [g['id'] for g in selected_groups]
                
                auto_post = AutoPost(
                    user_id=user.id,
                    account_id=account_id,
                    message_text=message_text,
                    target_groups=json.dumps(target_group_ids),
                    interval_seconds=interval_seconds,
                    is_active=True,
                    next_post_time=datetime.utcnow() + timedelta(seconds=interval_seconds)
                )
                session.add(auto_post)
                session.flush()
                
                broadcast_id = auto_post.id
                session.commit()
            
            # Планирование первой отправки
            if self.scheduler:
                self.scheduler.schedule_auto_post(
                    broadcast_id,
                    datetime.utcnow() + timedelta(seconds=interval_seconds)
                )
            
            # Форматирование интервала для отображения
            if interval_seconds >= 86400:
                interval_text = f"{interval_seconds // 86400} дн."
            elif interval_seconds >= 3600:
                interval_text = f"{interval_seconds // 3600} ч."
            else:
                interval_text = f"{interval_seconds // 60} мин."
            
            text = f"✅ Рассылка создана успешно!\n\n"
            text += f"📨 ID рассылки: {broadcast_id}\n"
            text += f"⏰ Интервал: {interval_text}\n"
            text += f"📋 Групп: {len(selected_groups)}\n"
            text += f"🚀 Первая отправка через: {interval_text}\n\n"
            text += f"Используйте /list_broadcasts для управления рассылками."
            
            await self._send_message(update, text)
            
            # Логирование
            await self._log_activity(
                user_id, account_id, 'broadcast_create',
                f"{len(selected_groups)} groups", 'success',
                f"Created broadcast with {interval_text} interval"
            )
            
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error creating broadcast: {e}")
            await self._send_message(update, "❌ Ошибка при создании рассылки")
    
    async def list_broadcasts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда просмотра списка рассылок"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            broadcasts = session.query(AutoPost).filter_by(user_id=user.id).all()
        
        if not broadcasts:
            await update.message.reply_text("📝 У вас нет созданных рассылок")
            return
        
        text = "📨 Ваши рассылки:\n\n"
        for broadcast in broadcasts:
            status = "🟢 Активна" if broadcast.is_active else "🔴 Остановлена"
            
            # Форматирование интервала
            if broadcast.interval_seconds >= 86400:
                interval_text = f"{broadcast.interval_seconds // 86400} дн."
            elif broadcast.interval_seconds >= 3600:
                interval_text = f"{broadcast.interval_seconds // 3600} ч."
            else:
                interval_text = f"{broadcast.interval_seconds // 60} мин."
            
            target_groups = json.loads(broadcast.target_groups)
            
            text += f"📨 ID: {broadcast.id}\n"
            text += f"   {status}\n"
            text += f"   ⏰ Интервал: {interval_text}\n"
            text += f"   📋 Групп: {len(target_groups)}\n"
            text += f"   📊 Отправлено: {broadcast.total_sent}\n"
            
            if broadcast.last_sent:
                text += f"   🕐 Последняя: {broadcast.last_sent.strftime('%Y-%m-%d %H:%M')}\n"
            
            if broadcast.is_active and broadcast.next_post_time:
                text += f"   ⏭ Следующая: {broadcast.next_post_time.strftime('%Y-%m-%d %H:%M')}\n"
            
            text += f"   💬 Сообщение: {broadcast.message_text[:50]}...\n\n"
        
        await update.message.reply_text(text)
    
    async def stop_broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда остановки рассылки"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            active_broadcasts = session.query(AutoPost).filter_by(
                user_id=user.id, is_active=True
            ).all()
        
        if not active_broadcasts:
            await update.message.reply_text("📝 У вас нет активных рассылок")
            return
        
        keyboard = []
        for broadcast in active_broadcasts:
            keyboard.append([
                InlineKeyboardButton(
                    f"⏹ ID: {broadcast.id} ({broadcast.message_text[:20]}...)",
                    callback_data=f"broadcast_stop_{broadcast.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="broadcast_cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "⏹ Выберите рассылку для остановки:"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов для рассылок"""
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        
        if data == "broadcast_create":
            await self._start_create_broadcast(update, context)
        elif data == "broadcast_list":
            await self.list_broadcasts_command(update, context)
        elif data == "broadcast_stats":
            await self._show_broadcast_stats(update, context)
        elif data == "broadcast_stop_all":
            await self._stop_all_broadcasts(update, context, user_id)
        elif data == "broadcast_cancel":
            context.user_data.clear()
            await query.edit_message_text("❌ Операция отменена")
        elif data.startswith("broadcast_interval_"):
            if data == "broadcast_interval_custom":
                context.user_data['state'] = 'broadcast_interval_input'
                await query.edit_message_text(
                    "⚙️ Введите свой интервал:\n\n"
                    "Примеры:\n"
                    "• 30м - 30 минут\n"
                    "• 2ч - 2 часа\n"
                    "• 1д - 1 день\n"
                    "• 90 - 90 минут"
                )
            else:
                interval_seconds = int(data.split("_")[2])
                context.user_data['broadcast_interval'] = interval_seconds
                await self._select_account(update, context, user_id)
        elif data.startswith("broadcast_account_"):
            account_id = int(data.split("_")[2])
            context.user_data['broadcast_account_id'] = account_id
            await self._select_groups(update, context, user_id)
        elif data.startswith("broadcast_group_toggle_"):
            group_index = int(data.split("_")[3])
            groups = context.user_data.get('available_groups', [])
            if 0 <= group_index < len(groups):
                groups[group_index]['selected'] = not groups[group_index]['selected']
                context.user_data['available_groups'] = groups
            await self._show_groups_selection(update, context)
        elif data == "broadcast_create_final":
            await self._create_final_broadcast(update, context, user_id)
        elif data.startswith("broadcast_stop_"):
            broadcast_id = int(data.split("_")[2])
            await self._stop_single_broadcast(update, context, broadcast_id, user_id)
    
    async def _show_broadcast_stats(self, update, context):
        """Показать статистику рассылок"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            broadcasts = session.query(AutoPost).filter_by(user_id=user.id).all()
            
            if not broadcasts:
                await update.callback_query.edit_message_text("📊 Нет данных для статистики")
                return
            
            total_broadcasts = len(broadcasts)
            active_broadcasts = len([b for b in broadcasts if b.is_active])
            total_sent = sum(b.total_sent for b in broadcasts)
            
            # Статистика по аккаунтам
            account_stats = {}
            for broadcast in broadcasts:
                account_phone = broadcast.account.phone_number
                if account_phone not in account_stats:
                    account_stats[account_phone] = {'broadcasts': 0, 'sent': 0}
                account_stats[account_phone]['broadcasts'] += 1
                account_stats[account_phone]['sent'] += broadcast.total_sent
        
        text = f"📊 Статистика рассылок\n\n"
        text += f"📨 Всего рассылок: {total_broadcasts}\n"
        text += f"🟢 Активных: {active_broadcasts}\n"
        text += f"🔴 Остановленных: {total_broadcasts - active_broadcasts}\n"
        text += f"📤 Всего отправлено: {total_sent}\n\n"
        
        if account_stats:
            text += "📱 По аккаунтам:\n"
            for phone, stats in account_stats.items():
                text += f"• {phone}: {stats['broadcasts']} рассылок, {stats['sent']} сообщений\n"
        
        await update.callback_query.edit_message_text(text)
    
    async def _stop_all_broadcasts(self, update, context, user_id):
        """Остановка всех рассылок"""
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.callback_query.edit_message_text("❌ Пользователь не найден")
                    return
                
                active_broadcasts = session.query(AutoPost).filter_by(
                    user_id=user.id, is_active=True
                ).all()
                
                if not active_broadcasts:
                    await update.callback_query.edit_message_text("📝 Нет активных рассылок")
                    return
                
                # Остановка всех рассылок
                for broadcast in active_broadcasts:
                    broadcast.is_active = False
                    
                    # Отмена в планировщике
                    if self.scheduler:
                        self.scheduler.cancel_auto_post(broadcast.id)
                
                session.commit()
                
                count = len(active_broadcasts)
                await update.callback_query.edit_message_text(
                    f"⏹ Остановлено {count} рассылок"
                )
                
        except Exception as e:
            logger.error(f"Error stopping all broadcasts: {e}")
            await update.callback_query.edit_message_text("❌ Ошибка при остановке рассылок")
    
    async def _stop_single_broadcast(self, update, context, broadcast_id, user_id):
        """Остановка одной рассылки"""
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.callback_query.edit_message_text("❌ Пользователь не найден")
                    return
                
                broadcast = session.query(AutoPost).filter_by(
                    id=broadcast_id, user_id=user.id
                ).first()
                
                if not broadcast:
                    await update.callback_query.edit_message_text("❌ Рассылка не найдена")
                    return
                
                if not broadcast.is_active:
                    await update.callback_query.edit_message_text("📝 Рассылка уже остановлена")
                    return
                
                # Остановка рассылки
                broadcast.is_active = False
                session.commit()
                
                # Отмена в планировщике
                if self.scheduler:
                    self.scheduler.cancel_auto_post(broadcast_id)
                
                await update.callback_query.edit_message_text(
                    f"⏹ Рассылка ID: {broadcast_id} остановлена"
                )
                
        except Exception as e:
            logger.error(f"Error stopping broadcast {broadcast_id}: {e}")
            await update.callback_query.edit_message_text("❌ Ошибка при остановке рассылки")
    
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

