import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import Config
from handlers.account_handlers import AccountHandlers
from handlers.parsing_handlers import ParsingHandlers
from handlers.invite_handlers import InviteHandlers
from handlers.broadcast_handlers import BroadcastHandlers
from handlers.neuro_handlers import NeuroHandlers
from database.database import db_manager
from database.models import User

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self):
        self.application = None
        self.account_handlers = AccountHandlers()
        self.parsing_handlers = ParsingHandlers()
        self.invite_handlers = InviteHandlers()
        self.broadcast_handlers = BroadcastHandlers()
        self.neuro_handlers = NeuroHandlers()
    
    async def start(self):
        """Запуск бота"""
        try:
            # Создание приложения
            self.application = Application.builder().token(Config.BOT_TOKEN).build()
            
            # Регистрация обработчиков
            self._register_handlers()
            
            # Запуск бота
            logger.info("Starting Telegram bot...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("Bot started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """Остановка бота"""
        if self.application:
            logger.info("Stopping Telegram bot...")
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Bot stopped successfully")
    
    def _register_handlers(self):
        """Регистрация всех обработчиков команд"""
        app = self.application
        
        # Основные команды
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("menu", self.menu_command))
        
        # Обработчики аккаунтов
        app.add_handler(CommandHandler("add_account", self.account_handlers.add_account_command))
        app.add_handler(CommandHandler("list_accounts", self.account_handlers.list_accounts_command))
        app.add_handler(CommandHandler("remove_account", self.account_handlers.remove_account_command))
        
        # Обработчики парсинга
        app.add_handler(CommandHandler("parse_group", self.parsing_handlers.parse_group_command))
        app.add_handler(CommandHandler("parse_status", self.parsing_handlers.parse_status_command))
        
        # Обработчики инвайтинга
        app.add_handler(CommandHandler("invite_users", self.invite_handlers.invite_users_command))
        app.add_handler(CommandHandler("invite_status", self.invite_handlers.invite_status_command))
        
        # Обработчики рассылки
        app.add_handler(CommandHandler("create_broadcast", self.broadcast_handlers.create_broadcast_command))
        app.add_handler(CommandHandler("list_broadcasts", self.broadcast_handlers.list_broadcasts_command))
        app.add_handler(CommandHandler("stop_broadcast", self.broadcast_handlers.stop_broadcast_command))
        
        # Обработчики нейрокомментинга
        app.add_handler(CommandHandler("setup_neuro", self.neuro_handlers.setup_neuro_command))
        app.add_handler(CommandHandler("neuro_status", self.neuro_handlers.neuro_status_command))
        
        # Обработчики callback запросов
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Обработчик файлов
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        
        # Обработчик текстовых сообщений
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start_command(self, update: Update, context):
        """Обработчик команды /start"""
        user = update.effective_user
        
        # Сохранение пользователя в базу данных
        await self._save_user(user)
        
        welcome_text = f"""
🤖 Добро пожаловать в Telegram Bot для парсинга и рассылок!

👋 Привет, {user.first_name}!

Этот бот поможет вам:
• 📱 Управлять аккаунтами для рассылок
• 👥 Парсить пользователей из групп и каналов
• 📨 Создавать автоматические рассылки
• 🎯 Инвайтить пользователей в группы
• 🧠 Настраивать нейрокомментирование

Используйте /menu для просмотра всех доступных функций.
        """
        
        keyboard = [
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context):
        """Обработчик команды /help"""
        help_text = """
📖 Справка по командам:

🔧 Управление аккаунтами:
/add_account - Добавить новый аккаунт
/list_accounts - Список аккаунтов
/remove_account - Удалить аккаунт

👥 Парсинг пользователей:
/parse_group - Парсить группу/канал
/parse_status - Статус парсинга

🎯 Инвайтинг:
/invite_users - Пригласить пользователей
/invite_status - Статус инвайтинга

📨 Рассылки:
/create_broadcast - Создать рассылку
/list_broadcasts - Список рассылок
/stop_broadcast - Остановить рассылку

🧠 Нейрокомментирование:
/setup_neuro - Настроить нейрокомментирование
/neuro_status - Статус нейрокомментирования

📋 Общие команды:
/menu - Главное меню
/help - Эта справка
        """
        
        await update.message.reply_text(help_text)
    
    async def menu_command(self, update: Update, context):
        """Обработчик команды /menu"""
        keyboard = [
            [
                InlineKeyboardButton("📱 Аккаунты", callback_data="accounts_menu"),
                InlineKeyboardButton("👥 Парсинг", callback_data="parsing_menu")
            ],
            [
                InlineKeyboardButton("🎯 Инвайтинг", callback_data="invite_menu"),
                InlineKeyboardButton("📨 Рассылки", callback_data="broadcast_menu")
            ],
            [
                InlineKeyboardButton("🧠 Нейрокомментинг", callback_data="neuro_menu"),
                InlineKeyboardButton("📊 Статистика", callback_data="stats_menu")
            ],
            [
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = "📋 Главное меню\n\nВыберите нужную функцию:"
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def handle_callback(self, update: Update, context):
        """Обработчик callback запросов"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "main_menu":
            await self.menu_command(update, context)
        elif data == "help":
            await self.help_command(update, context)
        elif data == "accounts_menu":
            await self.account_handlers.accounts_menu(update, context)
        elif data == "parsing_menu":
            await self.parsing_handlers.parsing_menu(update, context)
        elif data == "invite_menu":
            await self.invite_handlers.invite_menu(update, context)
        elif data == "broadcast_menu":
            await self.broadcast_handlers.broadcast_menu(update, context)
        elif data == "neuro_menu":
            await self.neuro_handlers.neuro_menu(update, context)
        elif data.startswith("account_"):
            await self.account_handlers.handle_callback(update, context)
        elif data.startswith("parse_"):
            await self.parsing_handlers.handle_callback(update, context)
        elif data.startswith("invite_"):
            await self.invite_handlers.handle_callback(update, context)
        elif data.startswith("broadcast_"):
            await self.broadcast_handlers.handle_callback(update, context)
        elif data.startswith("neuro_"):
            await self.neuro_handlers.handle_callback(update, context)
    
    async def handle_document(self, update: Update, context):
        """Обработчик загруженных файлов"""
        document = update.message.document
        
        if document.file_name.endswith('.txt'):
            # Обработка текстовых файлов со списками пользователей
            await self.parsing_handlers.handle_user_list_file(update, context)
        else:
            await update.message.reply_text(
                "❌ Поддерживаются только текстовые файлы (.txt)"
            )
    
    async def handle_text(self, update: Update, context):
        """Обработчик текстовых сообщений"""
        text = update.message.text
        user_id = update.effective_user.id
        
        # Проверка состояния пользователя для многошаговых операций
        user_state = context.user_data.get('state')
        
        if user_state:
            if user_state.startswith('add_account_'):
                await self.account_handlers.handle_account_input(update, context)
            elif user_state.startswith('parse_'):
                await self.parsing_handlers.handle_parse_input(update, context)
            elif user_state.startswith('invite_'):
                await self.invite_handlers.handle_invite_input(update, context)
            elif user_state.startswith('broadcast_'):
                await self.broadcast_handlers.handle_broadcast_input(update, context)
            elif user_state.startswith('neuro_'):
                await self.neuro_handlers.handle_neuro_input(update, context)
        else:
            # Обычное сообщение без состояния
            await update.message.reply_text(
                "Используйте /menu для просмотра доступных команд."
            )
    
    async def _save_user(self, telegram_user):
        """Сохранение пользователя в базу данных"""
        try:
            with db_manager.get_session() as session:
                # Проверка существования пользователя
                user = session.query(User).filter_by(
                    telegram_id=telegram_user.id
                ).first()
                
                if not user:
                    # Создание нового пользователя
                    user = User(
                        telegram_id=telegram_user.id,
                        username=telegram_user.username,
                        first_name=telegram_user.first_name,
                        last_name=telegram_user.last_name,
                        is_admin=(telegram_user.id == Config.ADMIN_USER_ID)
                    )
                    session.add(user)
                    logger.info(f"New user registered: {telegram_user.id}")
                else:
                    # Обновление данных существующего пользователя
                    user.username = telegram_user.username
                    user.first_name = telegram_user.first_name
                    user.last_name = telegram_user.last_name
                    
                session.commit()
                
        except Exception as e:
            logger.error(f"Failed to save user {telegram_user.id}: {e}")

