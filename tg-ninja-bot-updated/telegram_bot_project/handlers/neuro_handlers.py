import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import db_manager
from database.models import User, Account, Group, NeuroComment, ActivityLog
from config import Config

logger = logging.getLogger(__name__)

class NeuroHandlers:
    def __init__(self):
        pass
    
    async def neuro_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню нейрокомментинга"""
        user_id = update.effective_user.id
        
        # Получение статистики нейрокомментинга
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            total_neuro = session.query(NeuroComment).filter_by(user_id=user.id).count()
            active_neuro = session.query(NeuroComment).filter_by(
                user_id=user.id, is_active=True
            ).count()
            
            total_comments = session.query(NeuroComment).filter_by(
                user_id=user.id
            ).with_entities(
                session.query(NeuroComment.total_comments).label('sum')
            ).scalar() or 0
        
        text = f"🧠 Нейрокомментирование\n\n"
        text += f"📊 Статистика:\n"
        text += f"• Всего настроек: {total_neuro}\n"
        text += f"• Активных: {active_neuro}\n"
        text += f"• Создано комментариев: {total_comments}\n\n"
        
        text += f"ℹ️ Нейрокомментирование использует OpenAI для генерации\n"
        text += f"умных комментариев к постам в каналах.\n"
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Настроить нейрокомментинг", callback_data="neuro_setup")],
            [InlineKeyboardButton("📋 Список настроек", callback_data="neuro_list")],
            [InlineKeyboardButton("📊 Статистика", callback_data="neuro_stats")],
            [InlineKeyboardButton("⏹ Остановить все", callback_data="neuro_stop_all")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def setup_neuro_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда настройки нейрокомментинга"""
        await self._start_setup_neuro(update, context)
    
    async def _start_setup_neuro(self, update, context):
        """Начало настройки нейрокомментинга"""
        user_id = update.effective_user.id
        
        # Проверка наличия OpenAI API ключа
        if not Config.OPENAI_API_KEY:
            await self._send_message(update, 
                "❌ OpenAI API ключ не настроен.\n"
                "Обратитесь к администратору для настройки."
            )
            return
        
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
                "❌ У вас нет активных аккаунтов для нейрокомментинга.\n"
                "Добавьте аккаунт через /add_account"
            )
            return
        
        text = """
🧠 Настройка нейрокомментинга

Процесс настройки состоит из нескольких шагов:

1️⃣ Указать каналы для комментирования
2️⃣ Настроить шаблон комментариев
3️⃣ Выбрать аккаунт для комментирования
4️⃣ Установить количество комментариев в день
5️⃣ Запустить нейрокомментирование

⚠️ Важно:
• Используйте только для своих каналов или с разрешения
• Не злоупотребляйте комментированием
• Аккаунт должен иметь доступ к каналам
• Соблюдайте правила Telegram

Начнем с указания каналов. Отправьте ссылки на каналы (по одной на строку):
        """
        
        context.user_data['state'] = 'neuro_channels_input'
        
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="neuro_cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_message(update, text, reply_markup)
    
    async def handle_neuro_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода данных для нейрокомментинга"""
        state = context.user_data.get('state')
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if state == 'neuro_channels_input':
            await self._handle_channels_input(update, context, text, user_id)
        elif state == 'neuro_template_input':
            await self._handle_template_input(update, context, text, user_id)
    
    async def _handle_channels_input(self, update, context, channels_text, user_id):
        """Обработка ввода каналов"""
        # Парсинг ссылок на каналы
        channel_links = [link.strip() for link in channels_text.split('\n') if link.strip()]
        
        if not channel_links:
            await update.message.reply_text("❌ Не найдено ссылок на каналы. Попробуйте еще раз:")
            return
        
        # Валидация и сохранение каналов
        valid_channels = []
        for link in channel_links:
            # Простая валидация ссылки
            if 't.me/' in link or link.startswith('@'):
                valid_channels.append(link)
        
        if not valid_channels:
            await update.message.reply_text(
                "❌ Не найдено валидных ссылок на каналы.\n"
                "Используйте формат: https://t.me/channel или @channel"
            )
            return
        
        context.user_data['neuro_channels'] = valid_channels
        context.user_data['state'] = 'neuro_template_input'
        
        text = f"✅ Добавлено каналов: {len(valid_channels)}\n\n"
        text += "Теперь создайте шаблон для комментариев.\n\n"
        text += "Вы можете использовать переменные:\n"
        text += "• {post_text} - текст поста\n"
        text += "• {channel_name} - название канала\n"
        text += "• {random_emoji} - случайный эмодзи\n\n"
        text += "Пример шаблона:\n"
        text += "\"Интересный пост! {random_emoji} Что думаете об этом?\"\n\n"
        text += "Введите ваш шаблон комментария:"
        
        await update.message.reply_text(text)
    
    async def _handle_template_input(self, update, context, template_text, user_id):
        """Обработка ввода шаблона комментариев"""
        if len(template_text) < 10:
            await update.message.reply_text(
                "❌ Шаблон слишком короткий. Минимум 10 символов."
            )
            return
        
        if len(template_text) > 500:
            await update.message.reply_text(
                "❌ Шаблон слишком длинный. Максимум 500 символов."
            )
            return
        
        context.user_data['neuro_template'] = template_text
        
        # Выбор количества комментариев в день
        keyboard = [
            [InlineKeyboardButton("1-3 комментария", callback_data="neuro_count_3")],
            [InlineKeyboardButton("4-6 комментариев", callback_data="neuro_count_6")],
            [InlineKeyboardButton("7-10 комментариев", callback_data="neuro_count_10")],
            [InlineKeyboardButton("11-15 комментариев", callback_data="neuro_count_15")],
            [InlineKeyboardButton("16-20 комментариев", callback_data="neuro_count_20")],
            [InlineKeyboardButton("❌ Отмена", callback_data="neuro_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Шаблон сохранен!\n\n"
            f"Предварительный просмотр:\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{template_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Выберите количество комментариев в день:",
            reply_markup=reply_markup
        )
    
    async def _select_neuro_account(self, update, context, user_id, comments_per_day):
        """Выбор аккаунта для нейрокомментинга"""
        context.user_data['neuro_comments_per_day'] = comments_per_day
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            accounts = session.query(Account).filter_by(
                user_id=user.id,
                is_active=True,
                is_banned=False
            ).all()
        
        if len(accounts) == 1:
            # Если аккаунт один, сразу создаем настройку
            await self._create_neuro_comment(update, context, accounts[0], user_id)
        else:
            # Выбор аккаунта
            keyboard = []
            for account in accounts:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📱 {account.phone_number}",
                        callback_data=f"neuro_account_{account.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="neuro_cancel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = "📱 Выберите аккаунт для нейрокомментинга:"
            await self._send_message(update, text, reply_markup)
    
    async def _create_neuro_comment(self, update, context, account, user_id):
        """Создание настройки нейрокомментинга"""
        try:
            channels = context.user_data.get('neuro_channels', [])
            template = context.user_data.get('neuro_template', '')
            comments_per_day = context.user_data.get('neuro_comments_per_day', 5)
            
            if not all([channels, template, comments_per_day]):
                await self._send_message(update, "❌ Недостаточно данных для создания настройки")
                return
            
            # Создание настройки в базе данных
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                
                neuro_comment = NeuroComment(
                    user_id=user.id,
                    account_id=account.id,
                    target_channels=json.dumps(channels),
                    comment_template=template,
                    is_active=True,
                    comments_per_day=comments_per_day
                )
                session.add(neuro_comment)
                session.flush()
                
                neuro_id = neuro_comment.id
                session.commit()
            
            text = f"✅ Нейрокомментирование настроено!\n\n"
            text += f"🆔 ID настройки: {neuro_id}\n"
            text += f"📱 Аккаунт: {account.phone_number}\n"
            text += f"📺 Каналов: {len(channels)}\n"
            text += f"💬 Комментариев в день: {comments_per_day}\n\n"
            text += f"🤖 Система будет автоматически генерировать и\n"
            text += f"отправлять комментарии к новым постам в каналах.\n\n"
            text += f"Используйте /neuro_status для мониторинга."
            
            await self._send_message(update, text)
            
            # Логирование
            await self._log_activity(
                user_id, account.id, 'neuro_setup',
                f"{len(channels)} channels", 'success',
                f"Created neuro commenting with {comments_per_day} comments per day"
            )
            
            context.user_data.clear()
            
        except Exception as e:
            logger.error(f"Error creating neuro comment: {e}")
            await self._send_message(update, "❌ Ошибка при создании настройки")
    
    async def neuro_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда проверки статуса нейрокомментинга"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            neuro_comments = session.query(NeuroComment).filter_by(user_id=user.id).all()
        
        if not neuro_comments:
            await update.message.reply_text("📝 У вас нет настроек нейрокомментинга")
            return
        
        text = "🧠 Статус нейрокомментинга:\n\n"
        for neuro in neuro_comments:
            status = "🟢 Активно" if neuro.is_active else "🔴 Остановлено"
            
            channels = json.loads(neuro.target_channels)
            
            text += f"🆔 ID: {neuro.id}\n"
            text += f"   {status}\n"
            text += f"   📱 Аккаунт: {neuro.account.phone_number}\n"
            text += f"   📺 Каналов: {len(channels)}\n"
            text += f"   💬 Комментариев в день: {neuro.comments_per_day}\n"
            text += f"   📊 Всего создано: {neuro.total_comments}\n"
            
            if neuro.last_comment_time:
                text += f"   🕐 Последний: {neuro.last_comment_time.strftime('%Y-%m-%d %H:%M')}\n"
            
            text += f"   📝 Шаблон: {neuro.comment_template[:50]}...\n\n"
        
        await update.message.reply_text(text)
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов для нейрокомментинга"""
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        
        if data == "neuro_setup":
            await self._start_setup_neuro(update, context)
        elif data == "neuro_list":
            await self._list_neuro_settings(update, context)
        elif data == "neuro_stats":
            await self._show_neuro_stats(update, context)
        elif data == "neuro_stop_all":
            await self._stop_all_neuro(update, context, user_id)
        elif data == "neuro_cancel":
            context.user_data.clear()
            await query.edit_message_text("❌ Операция отменена")
        elif data.startswith("neuro_count_"):
            comments_per_day = int(data.split("_")[2])
            await self._select_neuro_account(update, context, user_id, comments_per_day)
        elif data.startswith("neuro_account_"):
            account_id = int(data.split("_")[2])
            await self._handle_neuro_account_selection(update, context, account_id, user_id)
        elif data.startswith("neuro_stop_"):
            neuro_id = int(data.split("_")[2])
            await self._stop_single_neuro(update, context, neuro_id, user_id)
    
    async def _handle_neuro_account_selection(self, update, context, account_id, user_id):
        """Обработка выбора аккаунта для нейрокомментинга"""
        with db_manager.get_session() as session:
            account = session.query(Account).filter_by(id=account_id).first()
            if not account:
                await update.callback_query.edit_message_text("❌ Аккаунт не найден")
                return
        
        await self._create_neuro_comment(update, context, account, user_id)
    
    async def _list_neuro_settings(self, update, context):
        """Список настроек нейрокомментинга"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            neuro_comments = session.query(NeuroComment).filter_by(user_id=user.id).all()
        
        if not neuro_comments:
            await update.callback_query.edit_message_text("📝 Нет настроек нейрокомментинга")
            return
        
        text = "📋 Настройки нейрокомментинга:\n\n"
        keyboard = []
        
        for neuro in neuro_comments:
            status_emoji = "🟢" if neuro.is_active else "🔴"
            channels = json.loads(neuro.target_channels)
            
            text += f"{status_emoji} ID: {neuro.id}\n"
            text += f"   📱 {neuro.account.phone_number}\n"
            text += f"   📺 {len(channels)} каналов\n"
            text += f"   💬 {neuro.comments_per_day}/день\n"
            text += f"   📊 Создано: {neuro.total_comments}\n\n"
            
            if neuro.is_active:
                keyboard.append([
                    InlineKeyboardButton(
                        f"⏹ Остановить ID: {neuro.id}",
                        callback_data=f"neuro_stop_{neuro.id}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="neuro_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def _show_neuro_stats(self, update, context):
        """Показать статистику нейрокомментинга"""
        user_id = update.effective_user.id
        
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ Пользователь не найден")
                return
            
            neuro_comments = session.query(NeuroComment).filter_by(user_id=user.id).all()
            
            if not neuro_comments:
                await update.callback_query.edit_message_text("📊 Нет данных для статистики")
                return
            
            total_settings = len(neuro_comments)
            active_settings = len([n for n in neuro_comments if n.is_active])
            total_comments = sum(n.total_comments for n in neuro_comments)
            total_channels = sum(len(json.loads(n.target_channels)) for n in neuro_comments)
            
            # Статистика по аккаунтам
            account_stats = {}
            for neuro in neuro_comments:
                account_phone = neuro.account.phone_number
                if account_phone not in account_stats:
                    account_stats[account_phone] = {'settings': 0, 'comments': 0}
                account_stats[account_phone]['settings'] += 1
                account_stats[account_phone]['comments'] += neuro.total_comments
        
        text = f"📊 Статистика нейрокомментинга\n\n"
        text += f"⚙️ Всего настроек: {total_settings}\n"
        text += f"🟢 Активных: {active_settings}\n"
        text += f"🔴 Остановленных: {total_settings - active_settings}\n"
        text += f"💬 Всего комментариев: {total_comments}\n"
        text += f"📺 Всего каналов: {total_channels}\n\n"
        
        if account_stats:
            text += "📱 По аккаунтам:\n"
            for phone, stats in account_stats.items():
                text += f"• {phone}: {stats['settings']} настроек, {stats['comments']} комментариев\n"
        
        await update.callback_query.edit_message_text(text)
    
    async def _stop_all_neuro(self, update, context, user_id):
        """Остановка всех настроек нейрокомментинга"""
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.callback_query.edit_message_text("❌ Пользователь не найден")
                    return
                
                active_neuro = session.query(NeuroComment).filter_by(
                    user_id=user.id, is_active=True
                ).all()
                
                if not active_neuro:
                    await update.callback_query.edit_message_text("📝 Нет активных настроек")
                    return
                
                # Остановка всех настроек
                for neuro in active_neuro:
                    neuro.is_active = False
                
                session.commit()
                
                count = len(active_neuro)
                await update.callback_query.edit_message_text(
                    f"⏹ Остановлено {count} настроек нейрокомментинга"
                )
                
        except Exception as e:
            logger.error(f"Error stopping all neuro comments: {e}")
            await update.callback_query.edit_message_text("❌ Ошибка при остановке настроек")
    
    async def _stop_single_neuro(self, update, context, neuro_id, user_id):
        """Остановка одной настройки нейрокомментинга"""
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.callback_query.edit_message_text("❌ Пользователь не найден")
                    return
                
                neuro = session.query(NeuroComment).filter_by(
                    id=neuro_id, user_id=user.id
                ).first()
                
                if not neuro:
                    await update.callback_query.edit_message_text("❌ Настройка не найдена")
                    return
                
                if not neuro.is_active:
                    await update.callback_query.edit_message_text("📝 Настройка уже остановлена")
                    return
                
                # Остановка настройки
                neuro.is_active = False
                session.commit()
                
                await update.callback_query.edit_message_text(
                    f"⏹ Настройка ID: {neuro_id} остановлена"
                )
                
        except Exception as e:
            logger.error(f"Error stopping neuro comment {neuro_id}: {e}")
            await update.callback_query.edit_message_text("❌ Ошибка при остановке настройки")
    
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

