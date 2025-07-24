from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import logging
from database.database import db_manager
from database.models import User, Account, AutoPost, NeuroComment, ActivityLog
from services.broadcast_service import BroadcastService
from services.neuro_service import NeuroService
from config import Config

logger = logging.getLogger(__name__)

def create_flask_app():
    """Создание Flask приложения"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = Config.SECRET_KEY
    
    # Включение CORS для всех доменов
    CORS(app, origins="*")
    
    # Инициализация сервисов
    broadcast_service = BroadcastService()
    neuro_service = NeuroService()
    
    @app.route('/')
    def index():
        """Главная страница"""
        return jsonify({
            'status': 'ok',
            'message': 'TG Ninja Bot API',
            'version': '1.0.0'
        })
    
    @app.route('/api/stats')
    def get_stats():
        """Получение общей статистики"""
        try:
            with db_manager.get_session() as session:
                total_users = session.query(User).count()
                total_accounts = session.query(Account).count()
                active_accounts = session.query(Account).filter_by(is_active=True).count()
                total_broadcasts = session.query(AutoPost).count()
                active_broadcasts = session.query(AutoPost).filter_by(is_active=True).count()
                total_neuro = session.query(NeuroComment).count()
                active_neuro = session.query(NeuroComment).filter_by(is_active=True).count()
                
                return jsonify({
                    'total_users': total_users,
                    'total_accounts': total_accounts,
                    'active_accounts': active_accounts,
                    'total_broadcasts': total_broadcasts,
                    'active_broadcasts': active_broadcasts,
                    'total_neuro': total_neuro,
                    'active_neuro': active_neuro
                })
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/users/<int:user_id>/accounts')
    def get_user_accounts(user_id):
        """Получение аккаунтов пользователя"""
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                accounts = session.query(Account).filter_by(user_id=user.id).all()
                
                return jsonify([{
                    'id': account.id,
                    'phone_number': account.phone_number,
                    'is_active': account.is_active,
                    'is_banned': account.is_banned,
                    'created_at': account.created_at.isoformat()
                } for account in accounts])
        except Exception as e:
            logger.error(f"Error getting user accounts: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/users/<int:user_id>/broadcasts')
    def get_user_broadcasts(user_id):
        """Получение рассылок пользователя"""
        try:
            result = await broadcast_service.get_broadcast_statistics(user_id)
            if 'error' in result:
                return jsonify({'error': result['error']}), 500
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error getting user broadcasts: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/users/<int:user_id>/neuro')
    def get_user_neuro(user_id):
        """Получение настроек нейрокомментирования пользователя"""
        try:
            result = await neuro_service.get_neuro_statistics(user_id)
            if 'error' in result:
                return jsonify({'error': result['error']}), 500
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error getting user neuro settings: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/broadcasts/<int:broadcast_id>/pause', methods=['POST'])
    def pause_broadcast(broadcast_id):
        """Приостановка рассылки"""
        try:
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({'error': 'user_id required'}), 400
            
            result = await broadcast_service.pause_broadcast(broadcast_id, user_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error pausing broadcast: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/broadcasts/<int:broadcast_id>/resume', methods=['POST'])
    def resume_broadcast(broadcast_id):
        """Возобновление рассылки"""
        try:
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({'error': 'user_id required'}), 400
            
            result = await broadcast_service.resume_broadcast(broadcast_id, user_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error resuming broadcast: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/broadcasts/<int:broadcast_id>', methods=['DELETE'])
    def delete_broadcast(broadcast_id):
        """Удаление рассылки"""
        try:
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({'error': 'user_id required'}), 400
            
            result = await broadcast_service.delete_broadcast(broadcast_id, user_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error deleting broadcast: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/neuro/<int:neuro_id>/pause', methods=['POST'])
    def pause_neuro(neuro_id):
        """Приостановка нейрокомментирования"""
        try:
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({'error': 'user_id required'}), 400
            
            result = await neuro_service.pause_neuro_comment(neuro_id, user_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error pausing neuro comment: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/neuro/<int:neuro_id>/resume', methods=['POST'])
    def resume_neuro(neuro_id):
        """Возобновление нейрокомментирования"""
        try:
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({'error': 'user_id required'}), 400
            
            result = await neuro_service.resume_neuro_comment(neuro_id, user_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error resuming neuro comment: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/neuro/<int:neuro_id>', methods=['DELETE'])
    def delete_neuro(neuro_id):
        """Удаление настройки нейрокомментирования"""
        try:
            user_id = request.json.get('user_id')
            if not user_id:
                return jsonify({'error': 'user_id required'}), 400
            
            result = await neuro_service.delete_neuro_comment(neuro_id, user_id)
            return jsonify(result)
        except Exception as e:
            logger.error(f"Error deleting neuro comment: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/activity/<int:user_id>')
    def get_user_activity(user_id):
        """Получение активности пользователя"""
        try:
            with db_manager.get_session() as session:
                user = session.query(User).filter_by(telegram_id=user_id).first()
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                activities = session.query(ActivityLog).filter_by(user_id=user.id).order_by(
                    ActivityLog.created_at.desc()
                ).limit(50).all()
                
                return jsonify([{
                    'id': activity.id,
                    'action_type': activity.action_type,
                    'target': activity.target,
                    'status': activity.status,
                    'details': activity.details,
                    'created_at': activity.created_at.isoformat()
                } for activity in activities])
        except Exception as e:
            logger.error(f"Error getting user activity: {e}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/health')
    def health_check():
        """Проверка состояния приложения"""
        try:
            # Проверка подключения к базе данных
            with db_manager.get_session() as session:
                session.execute("SELECT 1")
            
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'timestamp': Config.get_current_time().isoformat()
            })
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 500
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500
    
    return app

