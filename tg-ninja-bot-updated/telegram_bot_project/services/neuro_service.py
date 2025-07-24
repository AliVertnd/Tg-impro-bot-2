import logging
import json
import random
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, MessageNotModifiedError
from telethon.tl.types import Message
import openai
from database.database import db_manager
from database.models import NeuroComment, Account, ActivityLog
from services.encryption import EncryptionService
from config import Config

logger = logging.getLogger(__name__)

class NeuroService:
    def __init__(self):
        self.encryption = EncryptionService()
        self.openai_client = openai.OpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.OPENAI_API_BASE
        ) if Config.OPENAI_API_KEY else None
        
        # Список эмодзи для случайного выбора
        self.random_emojis = [
            "😊", "👍", "🔥", "💯", "✨", "🎯", "💪", "🚀", "⭐", "👏",
            "🤔", "💭", "📝", "🎉", "🌟", "💡", "🔔", "📢", "🎊", "🙌"
        ]
    
    async def execute_neuro_comment(self, neuro_comment_id):
        """Выполнение нейрокомментирования"""
        try:
            if not self.openai_client:
                logger.error("OpenAI client not initialized")
                return
            
            # Получение данных настройки
            with db_manager.get_session() as session:
                neuro_comment = session.query(NeuroComment).filter_by(
                    id=neuro_comment_id
                ).first()
                
                if not neuro_comment or not neuro_comment.is_active:
                    logger.info(f"Neuro comment {neuro_comment_id} not found or inactive")
                    return
                
                account = neuro_comment.account
                if not account or not account.is_active or account.is_banned:
                    logger.warning(f"Account for neuro comment {neuro_comment_id} is not available")
                    return
                
                target_channels = json.loads(neuro_comment.target_channels)
                
                if not target_channels:
                    logger.warning(f"No target channels for neuro comment {neuro_comment_id}")
                    return
            
            # Создание клиента
            session_string = self.encryption.decrypt(account.session_string)
            client = TelegramClient(
                StringSession(session_string),
                Config.API_ID,
                Config.API_HASH
            )
            
            await client.connect()
            
            if not await client.is_user_authorized():
                logger.error(f"Account {account.phone_number} is not authorized")
                await self._mark_account_inactive(account.id)
                return
            
            # Поиск новых постов в каналах для комментирования
            commented_count = 0
            
            for channel_link in target_channels:
                try:
                    # Получение сущности канала
                    channel_entity = await client.get_entity(channel_link)
                    
                    # Получение последних сообщений
                    messages = await client.get_messages(channel_entity, limit=5)
                    
                    for message in messages:
                        if isinstance(message, Message) and message.text:
                            # Проверка, нужно ли комментировать этот пост
                            if await self._should_comment_post(message, neuro_comment):
                                # Генерация комментария
                                comment_text = await self._generate_comment(
                                    message.text,
                                    channel_entity.title,
                                    neuro_comment.comment_template
                                )
                                
                                if comment_text:
                                    try:
                                        # Отправка комментария
                                        await client.send_message(
                                            channel_entity,
                                            comment_text,
                                            reply_to=message.id
                                        )
                                        
                                        commented_count += 1
                                        logger.info(f"Comment sent to {channel_entity.title}")
                                        
                                        # Пауза между комментариями
                                        await asyncio.sleep(random.randint(30, 60))
                                        
                                        # Ограничение на количество комментариев за раз
                                        if commented_count >= 3:
                                            break
                                        
                                    except ChatWriteForbiddenError:
                                        logger.warning(f"No permission to comment in {channel_entity.title}")
                                    except FloodWaitError as e:
                                        logger.warning(f"Flood wait for {e.seconds} seconds")
                                        await asyncio.sleep(e.seconds)
                                    except Exception as e:
                                        logger.error(f"Error sending comment to {channel_entity.title}: {e}")
                    
                    # Пауза между каналами
                    await asyncio.sleep(random.randint(10, 30))
                    
                except Exception as e:
                    logger.error(f"Error processing channel {channel_link}: {e}")
                    continue
            
            # Обновление статистики
            if commented_count > 0:
                with db_manager.get_session() as session:
                    neuro_comment = session.query(NeuroComment).filter_by(
                        id=neuro_comment_id
                    ).first()
                    
                    if neuro_comment:
                        neuro_comment.total_comments += commented_count
                        neuro_comment.last_comment_time = datetime.utcnow()
                        session.commit()
                
                # Логирование результата
                await self._log_neuro_activity(
                    neuro_comment.user_id, account.id, 'neuro_comment',
                    f"{len(target_channels)} channels", 'success',
                    f"Created {commented_count} comments"
                )
            
            logger.info(f"Neuro comment {neuro_comment_id} completed: {commented_count} comments created")
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"Error executing neuro comment {neuro_comment_id}: {e}")
            
            # Логирование ошибки
            try:
                with db_manager.get_session() as session:
                    neuro_comment = session.query(NeuroComment).filter_by(
                        id=neuro_comment_id
                    ).first()
                    
                    if neuro_comment:
                        await self._log_neuro_activity(
                            neuro_comment.user_id, neuro_comment.account_id,
                            'neuro_comment', 'error', 'failed', str(e)
                        )
            except:
                pass
    
    async def _should_comment_post(self, message, neuro_comment):
        """Проверка, нужно ли комментировать пост"""
        try:
            # Проверка возраста поста (не комментируем старые посты)
            if message.date < datetime.utcnow() - timedelta(hours=24):
                return False
            
            # Проверка длины поста (не комментируем слишком короткие)
            if len(message.text) < 50:
                return False
            
            # Случайность (не комментируем все подряд)
            if random.random() > 0.3:  # 30% вероятность комментирования
                return False
            
            # Проверка на спам-слова (избегаем комментирования рекламы)
            spam_words = ['реклама', 'скидка', 'купить', 'заказать', 'промокод']
            text_lower = message.text.lower()
            if any(word in text_lower for word in spam_words):
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking if should comment post: {e}")
            return False
    
    async def _generate_comment(self, post_text, channel_name, template):
        """Генерация комментария с помощью OpenAI"""
        try:
            # Подготовка переменных для шаблона
            random_emoji = random.choice(self.random_emojis)
            
            # Замена переменных в шаблоне
            comment_base = template.format(
                post_text=post_text[:100] + "..." if len(post_text) > 100 else post_text,
                channel_name=channel_name,
                random_emoji=random_emoji
            )
            
            # Создание промпта для OpenAI
            prompt = f"""
Создай естественный комментарий к посту в Telegram канале.

Пост: "{post_text[:200]}..."
Канал: {channel_name}
Базовый шаблон: {comment_base}

Требования:
- Комментарий должен быть естественным и релевантным
- Длина: 20-100 символов
- Используй дружелюбный тон
- Можешь добавить эмодзи
- Не используй спам-слова
- Комментарий должен добавлять ценность к обсуждению

Создай только текст комментария, без дополнительных объяснений.
"""
            
            # Запрос к OpenAI
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты помощник для создания естественных комментариев в Telegram."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.8
            )
            
            generated_comment = response.choices[0].message.content.strip()
            
            # Валидация сгенерированного комментария
            if len(generated_comment) < 10 or len(generated_comment) > 200:
                # Если комментарий не подходит, используем базовый шаблон
                return comment_base
            
            return generated_comment
            
        except Exception as e:
            logger.error(f"Error generating comment with OpenAI: {e}")
            
            # В случае ошибки возвращаем базовый шаблон
            random_emoji = random.choice(self.random_emojis)
            return template.format(
                post_text=post_text[:50] + "..." if len(post_text) > 50 else post_text,
                channel_name=channel_name,
                random_emoji=random_emoji
            )
    
    async def test_neuro_comment_access(self, account_id, channel_links):
        """Тестирование доступа к каналам для комментирования"""
        try:
            with db_manager.get_session() as session:
                account = session.query(Account).filter_by(id=account_id).first()
                if not account:
                    raise Exception("Account not found")
            
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
            
            # Проверка доступа к каждому каналу
            results = []
            
            for channel_link in channel_links:
                try:
                    channel_entity = await client.get_entity(channel_link)
                    
                    # Проверка прав на комментирование
                    permissions = await client.get_permissions(channel_entity, 'me')
                    
                    can_comment = not permissions.is_banned and (
                        permissions.is_admin or 
                        not getattr(channel_entity, 'default_banned_rights', {}).get('send_messages', False)
                    )
                    
                    results.append({
                        'channel_link': channel_link,
                        'channel_title': channel_entity.title,
                        'can_comment': can_comment,
                        'is_member': True,
                        'error': None
                    })
                    
                except Exception as e:
                    results.append({
                        'channel_link': channel_link,
                        'channel_title': 'Unknown',
                        'can_comment': False,
                        'is_member': False,
                        'error': str(e)
                    })
            
            await client.disconnect()
            
            return {
                'success': True,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error testing neuro comment access: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_neuro_statistics(self, user_id):
        """Получение статистики нейрокомментирования пользователя"""
        try:
            with db_manager.get_session() as session:
                neuro_comments = session.query(NeuroComment).join(Account).filter(
                    Account.user_id == user_id
                ).all()
                
                if not neuro_comments:
                    return {
                        'total_settings': 0,
                        'active_settings': 0,
                        'total_comments': 0,
                        'settings': []
                    }
                
                total_settings = len(neuro_comments)
                active_settings = len([nc for nc in neuro_comments if nc.is_active])
                total_comments = sum(nc.total_comments for nc in neuro_comments)
                
                settings = []
                for neuro_comment in neuro_comments:
                    target_channels = json.loads(neuro_comment.target_channels)
                    
                    settings.append({
                        'id': neuro_comment.id,
                        'is_active': neuro_comment.is_active,
                        'target_channels_count': len(target_channels),
                        'target_channels': target_channels,
                        'comment_template': neuro_comment.comment_template,
                        'comments_per_day': neuro_comment.comments_per_day,
                        'total_comments': neuro_comment.total_comments,
                        'last_comment_time': neuro_comment.last_comment_time.isoformat() if neuro_comment.last_comment_time else None,
                        'created_at': neuro_comment.created_at.isoformat(),
                        'account_phone': neuro_comment.account.phone_number
                    })
                
                return {
                    'total_settings': total_settings,
                    'active_settings': active_settings,
                    'total_comments': total_comments,
                    'settings': settings
                }
                
        except Exception as e:
            logger.error(f"Error getting neuro statistics: {e}")
            return {
                'error': str(e)
            }
    
    async def _mark_account_inactive(self, account_id):
        """Отметка аккаунта как неактивного"""
        try:
            with db_manager.get_session() as session:
                account = session.query(Account).filter_by(id=account_id).first()
                if account:
                    account.is_active = False
                    session.commit()
                    logger.info(f"Account {account.phone_number} marked as inactive")
        except Exception as e:
            logger.error(f"Error marking account {account_id} as inactive: {e}")
    
    async def _log_neuro_activity(self, user_id, account_id, action_type, target, status, details):
        """Логирование активности нейрокомментирования"""
        try:
            with db_manager.get_session() as session:
                log = ActivityLog(
                    user_id=user_id,
                    account_id=account_id,
                    action_type=action_type,
                    target=target,
                    status=status,
                    details=details
                )
                session.add(log)
                session.commit()
        except Exception as e:
            logger.error(f"Error logging neuro activity: {e}")
    
    async def pause_neuro_comment(self, neuro_comment_id, user_id):
        """Приостановка нейрокомментирования"""
        try:
            with db_manager.get_session() as session:
                neuro_comment = session.query(NeuroComment).join(Account).filter(
                    NeuroComment.id == neuro_comment_id,
                    Account.user_id == user_id
                ).first()
                
                if not neuro_comment:
                    return {'success': False, 'error': 'Neuro comment setting not found'}
                
                neuro_comment.is_active = False
                session.commit()
                
                return {'success': True, 'message': 'Neuro commenting paused'}
                
        except Exception as e:
            logger.error(f"Error pausing neuro comment {neuro_comment_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def resume_neuro_comment(self, neuro_comment_id, user_id):
        """Возобновление нейрокомментирования"""
        try:
            with db_manager.get_session() as session:
                neuro_comment = session.query(NeuroComment).join(Account).filter(
                    NeuroComment.id == neuro_comment_id,
                    Account.user_id == user_id
                ).first()
                
                if not neuro_comment:
                    return {'success': False, 'error': 'Neuro comment setting not found'}
                
                neuro_comment.is_active = True
                session.commit()
                
                return {'success': True, 'message': 'Neuro commenting resumed'}
                
        except Exception as e:
            logger.error(f"Error resuming neuro comment {neuro_comment_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def delete_neuro_comment(self, neuro_comment_id, user_id):
        """Удаление настройки нейрокомментирования"""
        try:
            with db_manager.get_session() as session:
                neuro_comment = session.query(NeuroComment).join(Account).filter(
                    NeuroComment.id == neuro_comment_id,
                    Account.user_id == user_id
                ).first()
                
                if not neuro_comment:
                    return {'success': False, 'error': 'Neuro comment setting not found'}
                
                session.delete(neuro_comment)
                session.commit()
                
                return {'success': True, 'message': 'Neuro comment setting deleted'}
                
        except Exception as e:
            logger.error(f"Error deleting neuro comment {neuro_comment_id}: {e}")
            return {'success': False, 'error': str(e)}

