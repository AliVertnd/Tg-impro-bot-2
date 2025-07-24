import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.database import db_manager
from database.models import User
from handlers.account_handlers import AccountHandlers
from handlers.parsing_handlers import ParsingHandlers
from handlers.invite_handlers import InviteHandlers
from handlers.broadcast_handlers import BroadcastHandlers
from handlers.neuro_handlers import NeuroHandlers

logger = logging.getLogger(__name__)

class MainHandlers:
    def __init__(self):
        self.account_handlers = AccountHandlers()
        self.parsing_handlers = ParsingHandlers()
        self.invite_handlers = InviteHandlers()
        self.broadcast_handlers = BroadcastHandlers()
        self.neuro_handlers = NeuroHandlers()
    
    def set_scheduler(self, scheduler):
        """Установка планировщика для обработчиков"""
        self.broadcast_handlers.set_scheduler(scheduler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        first_name = update.effective_user.first_name or "User"
        
        # Создание или обновление пользователя
        with db_manager.get_session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                user = User(
                    telegram_id=user_id,
                    username=username,
                    first_name=first_name
                )
                session.add(user)
                session.commit()
                
                welcome_text = f"""
🎉 Добро пожаловать в TG Ninja Bot, {first_name}!

🤖 Этот бот предоставляет мощные инструменты для работы с Telegram:

📱 Управление аккаунтами
• Добавление и настройка аккаунтов
• Мониторинг статуса и активности

👥 Парсинг пользователей
• Извлечение списков из групп и каналов
• Экспорт в удобные форматы

📨 Авто-рассылки
• Создание автоматических рассылок
• Настройка периодичности и целевых групп

🧠 Нейрокомментирование
• ИИ-комментарии к постам в каналах
• Умная генерация контента

⚡ Инвайтинг в группы
• Массовое добавление пользователей
• Управление приглашениями

Используйте меню ниже для навигации:
                """
            else:
                welcome_text = f"""
👋 С возвращением, {first_name}!

Выберите нужную функцию из меню:
                """
        
        keyboard = [
            [
                InlineKeyboardButton("📱 Аккаунты", callback_data="accounts_menu"),
                InlineKeyboardButton("👥 Парсинг", callback_data="parsing_menu")
            ],
            [
                InlineKeyboardButton("📨 Рассылки", callback_data="broadcast_menu"),
                InlineKeyboardButton("🧠 Нейро", callback_data="neuro_menu")
            ],
            [
                InlineKeyboardButton("⚡ Инвайтинг", callback_data="invite_menu"),
                InlineKeyboardButton("📊 Статистика", callback_data="stats_menu")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu"),
                InlineKeyboardButton("ℹ️ Помощь", callback_data="help_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
📖 Справка по TG Ninja Bot

🔧 Основные команды:
/start - Главное меню
/help - Эта справка
/add_account - Добавить аккаунт
/list_accounts - Список аккаунтов
/create_broadcast - Создать рассылку
/list_broadcasts - Список рассылок
/setup_neuro - Настроить нейрокомментирование
/neuro_status - Статус нейрокомментирования

📱 Управление аккаунтами:
• Добавляйте Telegram аккаунты через номер телефона
• Подтверждайте через код из SMS
• Управляйте статусом и активностью

👥 Парсинг пользователей:
• Указывайте ссылки на группы и каналы
• Получайте списки участников в txt файлах
• Работает с открытыми и закрытыми группами

📨 Авто-рассылки:
• Создавайте сообщения для рассылки
• Настраивайте интервалы отправки
• Выбирайте целевые группы и аккаунты

🧠 Нейрокомментирование:
• Используйте ИИ для генерации комментариев
• Настраивайте шаблоны и частоту
• Автоматическое комментирование постов

⚡ Инвайтинг:
• Массовое добавление пользователей в группы
• Управление списками для приглашения
• Контроль лимитов и безопасности

⚠️ Важные правила:
• Соблюдайте правила Telegram
• Не злоупотребляйте функциями
• Используйте разумные интервалы
• Следите за лимитами аккаунтов

🌐 Веб-интерфейс:
Доступна удобная веб-панель для управления всеми функциями бота.

По вопросам обращайтесь к администратору.
        """
        
        keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(help_text, reply_markup=reply_markup)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда статистики"""
        user_id = update.effective_user.id
        
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    await update.message.reply_text("❌ Пользователь не найден")
                    return
                
                # Получение статистики
                from database.models import Account, AutoPost, NeuroComment, ActivityLog
                
                total_accounts = session.query(Account).filter_by(user_id=user.id).count()
                active_accounts = session.query(Account).filter_by(
                    user_id=user.id, is_active=True, is_banned=False
                ).count()
                
                total_broadcasts = session.query(AutoPost).filter_by(user_id=user.id).count()
                active_broadcasts = session.query(AutoPost).filter_by(
                    user_id=user.id, is_active=True
                ).count()
                
                total_neuro = session.query(NeuroComment).filter_by(user_id=user.id).count()
                active_neuro = session.query(NeuroComment).filter_by(
                    user_id=user.id, is_active=True
                ).count()
                
                # Подсчет отправленных сообщений
                total_sent = session.query(AutoPost).filter_by(user_id=user.id).with_entities(
                    session.query(AutoPost.total_sent).label('sum')
                ).scalar() or 0
                
                # Подсчет нейрокомментариев
                total_comments = session.query(NeuroComment).filter_by(user_id=user.id).with_entities(
                    session.query(NeuroComment.total_comments).label('sum')
                ).scalar() or 0
                
                # Последняя активность
                last_activity = session.query(ActivityLog).filter_by(user_id=user.id).order_by(
                    ActivityLog.created_at.desc()
                ).first()
            
            stats_text = f"""
📊 Ваша статистика

👤 Пользователь: {user.first_name}
📅 Регистрация: {user.created_at.strftime('%Y-%m-%d')}

📱 Аккаунты:
• Всего: {total_accounts}
• Активных: {active_accounts}
• Заблокированных: {total_accounts - active_accounts}

📨 Рассылки:
• Всего: {total_broadcasts}
• Активных: {active_broadcasts}
• Отправлено сообщений: {total_sent}

🧠 Нейрокомментирование:
• Настроек: {total_neuro}
• Активных: {active_neuro}
• Создано комментариев: {total_comments}

🕐 Последняя активность:
{last_activity.created_at.strftime('%Y-%m-%d %H:%M') if last_activity else 'Нет данных'}
{last_activity.action_type if last_activity else ''}
            """
            
            keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(stats_text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            await update.message.reply_text("❌ Ошибка при получении статистики")
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик callback запросов"""
        query = update.callback_query
        data = query.data
        
        try:
            await query.answer()
            
            # Главное меню
            if data == "main_menu":
                await self.show_main_menu(update, context)
            
            # Меню аккаунтов
            elif data == "accounts_menu":
                await self.account_handlers.accounts_menu(update, context)
            elif data.startswith("account_"):
                await self.account_handlers.handle_callback(update, context)
            
            # Меню парсинга
            elif data == "parsing_menu":
                await self.parsing_handlers.parsing_menu(update, context)
            elif data.startswith("parsing_"):
                await self.parsing_handlers.handle_callback(update, context)
            
            # Меню инвайтинга
            elif data == "invite_menu":
                await self.invite_handlers.invite_menu(update, context)
            elif data.startswith("invite_"):
                await self.invite_handlers.handle_callback(update, context)
            
            # Меню рассылок
            elif data == "broadcast_menu":
                await self.broadcast_handlers.broadcast_menu(update, context)
            elif data.startswith("broadcast_"):
                await self.broadcast_handlers.handle_callback(update, context)
            
            # Меню нейрокомментирования
            elif data == "neuro_menu":
                await self.neuro_handlers.neuro_menu(update, context)
            elif data.startswith("neuro_"):
                await self.neuro_handlers.handle_callback(update, context)
            
            # Статистика
            elif data == "stats_menu":
                await self.stats_command(update, context)
            
            # Помощь
            elif data == "help_menu":
                await self.help_command(update, context)
            
            # Настройки
            elif data == "settings_menu":
                await self.show_settings_menu(update, context)
            
        except Exception as e:
            logger.error(f"Error handling callback query {data}: {e}")
            await query.edit_message_text("❌ Произошла ошибка. Попробуйте еще раз.")
    
    async def show_main_menu(self, update, context):
        """Показать главное меню"""
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        
        text = f"""
🎯 Главное меню - {first_name}

Выберите нужную функцию:
        """
        
        keyboard = [
            [
                InlineKeyboardButton("📱 Аккаунты", callback_data="accounts_menu"),
                InlineKeyboardButton("👥 Парсинг", callback_data="parsing_menu")
            ],
            [
                InlineKeyboardButton("📨 Рассылки", callback_data="broadcast_menu"),
                InlineKeyboardButton("🧠 Нейро", callback_data="neuro_menu")
            ],
            [
                InlineKeyboardButton("⚡ Инвайтинг", callback_data="invite_menu"),
                InlineKeyboardButton("📊 Статистика", callback_data="stats_menu")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu"),
                InlineKeyboardButton("ℹ️ Помощь", callback_data="help_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def show_settings_menu(self, update, context):
        """Показать меню настроек"""
        text = """
⚙️ Настройки системы

Основные параметры и конфигурация:
        """
        
        keyboard = [
            [InlineKeyboardButton("🔑 API настройки", callback_data="settings_api")],
            [InlineKeyboardButton("🛡️ Безопасность", callback_data="settings_security")],
            [InlineKeyboardButton("📊 Лимиты", callback_data="settings_limits")],
            [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстового ввода"""
        state = context.user_data.get('state')
        
        if not state:
            # Если нет активного состояния, показываем помощь
            await update.message.reply_text(
                "ℹ️ Используйте /start для открытия главного меню или /help для справки."
            )
            return
        
        # Перенаправление к соответствующим обработчикам
        if state.startswith('account_'):
            await self.account_handlers.handle_account_input(update, context)
        elif state.startswith('parsing_'):
            await self.parsing_handlers.handle_parsing_input(update, context)
        elif state.startswith('invite_'):
            await self.invite_handlers.handle_invite_input(update, context)
        elif state.startswith('broadcast_'):
            await self.broadcast_handlers.handle_broadcast_input(update, context)
        elif state.startswith('neuro_'):
            await self.neuro_handlers.handle_neuro_input(update, context)
        else:
            await update.message.reply_text(
                "❌ Неизвестное состояние. Используйте /start для сброса."
            )
            context.user_data.clear()
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик документов"""
        state = context.user_data.get('state')
        
        if state and state.startswith('parsing_'):
            await self.parsing_handlers.handle_document(update, context)
        elif state and state.startswith('invite_'):
            await self.invite_handlers.handle_document(update, context)
        else:
            await update.message.reply_text(
                "ℹ️ Отправьте документ в контексте соответствующей операции."
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка. Попробуйте еще раз или обратитесь к администратору."
            )

