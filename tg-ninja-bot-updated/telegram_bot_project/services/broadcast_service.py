import logging
import json
import asyncio
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, ChatWriteForbiddenError, UserBannedInChannelError
from database.database import db_manager
from database.models import AutoPost, Account, Group, ActivityLog
from services.encryption import EncryptionService
from config import Config

logger = logging.getLogger(__name__)

class BroadcastService:
    def __init__(self):
        self.encryption = EncryptionService()
    
    async def execute_auto_post(self, auto_post_id):
        """Выполнение автопоста"""
        try:
            # Получение данных автопоста
            with db_manager.get_session() as session:
                auto_post = session.query(AutoPost).filter_by(id=auto_post_id).first()
                if not auto_post or not auto_post.is_active:
                    logger.info(f"Auto post {auto_post_id} not found or inactive")
                    return
                
                account = auto_post.account
                if not account or not account.is_active or account.is_banned:
                    logger.warning(f"Account for auto post {auto_post_id} is not available")
                    return
                
                target_group_ids = json.loads(auto_post.target_groups)
                target_groups = session.query(Group).filter(
                    Group.id.in_(target_group_ids)
                ).all()
                
                if not target_groups:
                    logger.warning(f"No target groups found for auto post {auto_post_id}")
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
            
            # Отправка сообщений в группы
            sent_count = 0
            failed_count = 0
            
            for group in target_groups:
                try:
                    # Получение сущности группы
                    group_entity = await client.get_entity(int(group.telegram_id))
                    
                    # Отправка сообщения
                    await client.send_message(group_entity, auto_post.message_text)
                    sent_count += 1
                    
                    logger.info(f"Message sent to group {group.title}")
                    
                    # Пауза между отправками
                    await asyncio.sleep(5)
                    
                except ChatWriteForbiddenError:
                    logger.warning(f"No permission to write in group {group.title}")
                    failed_count += 1
                except UserBannedInChannelError:
                    logger.warning(f"Account banned in group {group.title}")
                    failed_count += 1
                except FloodWaitError as e:
                    logger.warning(f"Flood wait for {e.seconds} seconds")
                    await asyncio.sleep(e.seconds)
                    # Повторная попытка после ожидания
                    try:
                        await client.send_message(group_entity, auto_post.message_text)
                        sent_count += 1
                    except Exception as retry_e:
                        logger.error(f"Retry failed for group {group.title}: {retry_e}")
                        failed_count += 1
                except Exception as e:
                    logger.error(f"Error sending to group {group.title}: {e}")
                    failed_count += 1
            
            # Обновление статистики автопоста
            with db_manager.get_session() as session:
                auto_post = session.query(AutoPost).filter_by(id=auto_post_id).first()
                if auto_post:
                    auto_post.total_sent += sent_count
                    auto_post.last_sent = datetime.utcnow()
                    
                    # Планирование следующей отправки
                    auto_post.next_post_time = datetime.utcnow() + timedelta(
                        seconds=auto_post.interval_seconds
                    )
                    
                    session.commit()
            
            # Логирование результата
            await self._log_broadcast_activity(
                auto_post.user_id, account.id, 'auto_post',
                f"{len(target_groups)} groups", 'success',
                f"Sent: {sent_count}, Failed: {failed_count}"
            )
            
            logger.info(f"Auto post {auto_post_id} completed: {sent_count} sent, {failed_count} failed")
            
            await client.disconnect()
            
        except Exception as e:
            logger.error(f"Error executing auto post {auto_post_id}: {e}")
            
            # Логирование ошибки
            try:
                with db_manager.get_session() as session:
                    auto_post = session.query(AutoPost).filter_by(id=auto_post_id).first()
                    if auto_post:
                        await self._log_broadcast_activity(
                            auto_post.user_id, auto_post.account_id, 'auto_post',
                            'error', 'failed', str(e)
                        )
            except:
                pass
    
    async def send_manual_broadcast(self, user_id, account_id, message_text, target_group_ids):
        """Отправка ручной рассылки"""
        try:
            # Получение данных
            with db_manager.get_session() as session:
                account = session.query(Account).filter_by(id=account_id).first()
                if not account or not account.is_active or account.is_banned:
                    raise Exception("Account is not available")
                
                target_groups = session.query(Group).filter(
                    Group.id.in_(target_group_ids)
                ).all()
                
                if not target_groups:
                    raise Exception("No target groups found")
            
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
            
            # Отправка сообщений
            sent_count = 0
            failed_count = 0
            errors = []
            
            for group in target_groups:
                try:
                    group_entity = await client.get_entity(int(group.telegram_id))
                    await client.send_message(group_entity, message_text)
                    sent_count += 1
                    
                    # Пауза между отправками
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    failed_count += 1
                    errors.append(f"{group.title}: {str(e)}")
                    logger.error(f"Error sending to group {group.title}: {e}")
            
            await client.disconnect()
            
            # Логирование результата
            await self._log_broadcast_activity(
                user_id, account_id, 'manual_broadcast',
                f"{len(target_groups)} groups", 'success',
                f"Sent: {sent_count}, Failed: {failed_count}"
            )
            
            return {
                'success': True,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Error in manual broadcast: {e}")
            
            # Логирование ошибки
            await self._log_broadcast_activity(
                user_id, account_id, 'manual_broadcast',
                'error', 'failed', str(e)
            )
            
            return {
                'success': False,
                'error': str(e)
            }
    
    async def test_broadcast_access(self, account_id, group_ids):
        """Тестирование доступа к группам для рассылки"""
        try:
            with db_manager.get_session() as session:
                account = session.query(Account).filter_by(id=account_id).first()
                if not account:
                    raise Exception("Account not found")
                
                groups = session.query(Group).filter(
                    Group.id.in_(group_ids)
                ).all()
            
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
            
            # Проверка доступа к каждой группе
            results = []
            
            for group in groups:
                try:
                    group_entity = await client.get_entity(int(group.telegram_id))
                    
                    # Проверка прав на отправку сообщений
                    permissions = await client.get_permissions(group_entity, 'me')
                    
                    can_send = not permissions.is_banned and (
                        permissions.is_admin or 
                        not getattr(group_entity, 'default_banned_rights', {}).get('send_messages', False)
                    )
                    
                    results.append({
                        'group_id': group.id,
                        'group_title': group.title,
                        'can_send': can_send,
                        'is_member': True,
                        'error': None
                    })
                    
                except Exception as e:
                    results.append({
                        'group_id': group.id,
                        'group_title': group.title,
                        'can_send': False,
                        'is_member': False,
                        'error': str(e)
                    })
            
            await client.disconnect()
            
            return {
                'success': True,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error testing broadcast access: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_broadcast_statistics(self, user_id):
        """Получение статистики рассылок пользователя"""
        try:
            with db_manager.get_session() as session:
                auto_posts = session.query(AutoPost).join(Account).filter(
                    Account.user_id == user_id
                ).all()
                
                if not auto_posts:
                    return {
                        'total_broadcasts': 0,
                        'active_broadcasts': 0,
                        'total_sent': 0,
                        'broadcasts': []
                    }
                
                total_broadcasts = len(auto_posts)
                active_broadcasts = len([ap for ap in auto_posts if ap.is_active])
                total_sent = sum(ap.total_sent for ap in auto_posts)
                
                broadcasts = []
                for auto_post in auto_posts:
                    target_groups = json.loads(auto_post.target_groups)
                    
                    broadcasts.append({
                        'id': auto_post.id,
                        'message_preview': auto_post.message_text[:100],
                        'is_active': auto_post.is_active,
                        'interval_seconds': auto_post.interval_seconds,
                        'target_groups_count': len(target_groups),
                        'total_sent': auto_post.total_sent,
                        'last_sent': auto_post.last_sent.isoformat() if auto_post.last_sent else None,
                        'next_post_time': auto_post.next_post_time.isoformat() if auto_post.next_post_time else None,
                        'created_at': auto_post.created_at.isoformat(),
                        'account_phone': auto_post.account.phone_number
                    })
                
                return {
                    'total_broadcasts': total_broadcasts,
                    'active_broadcasts': active_broadcasts,
                    'total_sent': total_sent,
                    'broadcasts': broadcasts
                }
                
        except Exception as e:
            logger.error(f"Error getting broadcast statistics: {e}")
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
    
    async def _log_broadcast_activity(self, user_id, account_id, action_type, target, status, details):
        """Логирование активности рассылки"""
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
            logger.error(f"Error logging broadcast activity: {e}")
    
    async def pause_broadcast(self, broadcast_id, user_id):
        """Приостановка рассылки"""
        try:
            with db_manager.get_session() as session:
                auto_post = session.query(AutoPost).join(Account).filter(
                    AutoPost.id == broadcast_id,
                    Account.user_id == user_id
                ).first()
                
                if not auto_post:
                    return {'success': False, 'error': 'Broadcast not found'}
                
                auto_post.is_active = False
                session.commit()
                
                return {'success': True, 'message': 'Broadcast paused'}
                
        except Exception as e:
            logger.error(f"Error pausing broadcast {broadcast_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def resume_broadcast(self, broadcast_id, user_id):
        """Возобновление рассылки"""
        try:
            with db_manager.get_session() as session:
                auto_post = session.query(AutoPost).join(Account).filter(
                    AutoPost.id == broadcast_id,
                    Account.user_id == user_id
                ).first()
                
                if not auto_post:
                    return {'success': False, 'error': 'Broadcast not found'}
                
                auto_post.is_active = True
                # Установка времени следующей отправки
                auto_post.next_post_time = datetime.utcnow() + timedelta(
                    seconds=auto_post.interval_seconds
                )
                session.commit()
                
                return {'success': True, 'message': 'Broadcast resumed'}
                
        except Exception as e:
            logger.error(f"Error resuming broadcast {broadcast_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def delete_broadcast(self, broadcast_id, user_id):
        """Удаление рассылки"""
        try:
            with db_manager.get_session() as session:
                auto_post = session.query(AutoPost).join(Account).filter(
                    AutoPost.id == broadcast_id,
                    Account.user_id == user_id
                ).first()
                
                if not auto_post:
                    return {'success': False, 'error': 'Broadcast not found'}
                
                session.delete(auto_post)
                session.commit()
                
                return {'success': True, 'message': 'Broadcast deleted'}
                
        except Exception as e:
            logger.error(f"Error deleting broadcast {broadcast_id}: {e}")
            return {'success': False, 'error': str(e)}

