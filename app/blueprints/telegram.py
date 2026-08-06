"""telegram routes extracted from run_test_v2."""
from __future__ import annotations

from functools import wraps

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)

bp = Blueprint('telegram', __name__)


class _LimiterProxy:
    def limit(self, *limit_args, **limit_kwargs):
        def decorator(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                import run_test_v2 as rt
                return rt.limiter.limit(*limit_args, **limit_kwargs)(f)(*args, **kwargs)
            return wrapped
        return decorator


limiter = _LimiterProxy()


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        import run_test_v2 as rt
        return rt.admin_required(f)(*args, **kwargs)
    return wrapped


def bind_runtime() -> None:
    """Copy shared symbols from run_test_v2 into this module globals."""
    from app.blueprints import bind_module_runtime
    bind_module_runtime(globals())



@bp.route('/api/telegram/settings', methods=['GET'])
@jwt_required()
def get_telegram_settings():
    """Get user's Telegram settings"""
    try:
        user_id = get_jwt_identity()
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        
        if not settings:
            return jsonify({
                'connected': False,
                'settings': None
            }), 200
        
        return jsonify({
            'connected': True,
            'settings': settings.to_dict()
        }), 200
        
    except Exception as e:
        logger.error(f"Get Telegram settings error: {e}")
        return jsonify({'error': 'Failed to get Telegram settings'}), 500

@bp.route('/api/telegram/settings', methods=['POST'])
@jwt_required()
def save_telegram_settings():
    """Save user's Telegram settings"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json()
        
        chat_id = data.get('chat_id', '').strip()
        if not chat_id:
            return jsonify({'error': 'Chat ID is required'}), 400
        
        if not validate_telegram_chat_id(chat_id):
            return jsonify({'error': 'Invalid chat ID format'}), 400
        
        # Get or create settings
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if settings:
            settings.chat_id = chat_id
            settings.is_active = True
            settings.updated_at = datetime.utcnow()
        else:
            settings = TelegramSettings(
                user_id=user_id,
                chat_id=chat_id,
                is_active=True
            )
            db.session.add(settings)
        
        db.session.commit()
        
        logger.info(f"Telegram settings saved for user {user_id}")
        
        return jsonify({
            'message': 'Telegram settings saved successfully',
            'settings': settings.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Save Telegram settings error: {e}")
        return jsonify({'error': 'Failed to save Telegram settings'}), 500

@bp.route('/api/telegram/test', methods=['POST'])
@jwt_required()
def test_telegram_connection():
    """Test Telegram bot connection"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        
        if not settings:
            return jsonify({'error': 'Telegram not configured'}), 400
        
        # Send test message
        test_message = (
            f"🔔 <b>Test Message</b>\n\n"
            f"Hello {user.first_name}! Your Telegram bot is working correctly.\n\n"
            f"You will receive notifications about:\n"
            f"• Campaign completions\n"
            f"• Posting results\n"
            f"• System alerts\n\n"
            f"📱 AIPostX SaaS"
        )
        
        success = send_telegram_message(settings.chat_id, test_message)
        
        # Update settings
        settings.last_test_sent = datetime.utcnow()
        settings.test_successful = success
        db.session.commit()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Test message sent successfully!'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send test message. Please check your chat ID.'
            }), 400
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Test Telegram connection error: {e}")
        return jsonify({'error': 'Failed to test Telegram connection'}), 500

@bp.route('/api/telegram/digest', methods=['POST'])
@jwt_required()
def send_telegram_digest_now():
    """Send today's analytics digest to the current user's Telegram chat."""
    try:
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if not settings or not settings.chat_id:
            return jsonify({'error': 'Telegram not configured'}), 400

        from bot.telegram_reports import build_daily_digest_for_user, send_telegram_html
        label = getattr(user, 'full_name', None) or (user.email if user else '')
        text = build_daily_digest_for_user(user_id, user_label=label or '')
        ok = send_telegram_html(settings.chat_id, text, bot_token=TELEGRAM_BOT_TOKEN)
        if not ok:
            return jsonify({'success': False, 'error': 'Failed to send digest'}), 500
        return jsonify({'success': True, 'message': 'Daily digest sent', 'preview': text}), 200
    except Exception as e:
        logger.error(f"Telegram digest error: {e}")
        return jsonify({'error': 'Failed to send digest'}), 500

