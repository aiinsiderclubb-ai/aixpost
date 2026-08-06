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
                'settings': None,
                'bot_token': '',
                'chat_id': '',
            }), 200

        payload = settings.to_dict()
        return jsonify({
            'connected': True,
            'settings': payload,
            # Keep form fields filled for chat; never return full token.
            'bot_token': '',
            'bot_token_masked': payload.get('bot_token_masked') or '',
            'bot_token_set': payload.get('bot_token_set'),
            'chat_id': settings.chat_id,
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
        data = request.get_json() or {}
        
        chat_id = (data.get('chat_id') or '').strip()
        bot_token = (data.get('bot_token') or '').strip()
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
            if bot_token:
                settings.bot_token = bot_token
        else:
            if not bot_token:
                return jsonify({
                    'error': 'Bot Token is required for the first connection (or set TELEGRAM_BOT_TOKEN on the server)',
                }), 400
            settings = TelegramSettings(
                user_id=user_id,
                chat_id=chat_id,
                bot_token=bot_token,
                is_active=True
            )
            db.session.add(settings)
        
        db.session.commit()

        inbound = {}
        try:
            from bot.telegram_bot import activate_inbound_bot
            inbound = activate_inbound_bot(prefer_token=(settings.bot_token or None))
        except Exception as activate_err:
            logger.warning("Telegram inbound activate failed: %s", activate_err)
            inbound = {'ok': False, 'error': str(activate_err)}
        
        logger.info(f"Telegram settings saved for user {user_id}")
        
        return jsonify({
            'message': 'Telegram settings saved successfully',
            'settings': settings.to_dict(),
            'inbound': inbound,
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
            f"• System alerts\n"
            f"• Schedule commands (/schedule, /jobs)\n\n"
            f"📱 AIPostX"
        )

        from bot.telegram_reports import send_telegram_html, resolve_bot_token
        token = resolve_bot_token(getattr(settings, 'bot_token', None))
        success = send_telegram_html(settings.chat_id, test_message, bot_token=token)
        
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
                'message': 'Failed to send test message. Check Bot Token + Chat ID.'
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

        from bot.telegram_reports import build_daily_digest_for_user, send_telegram_html, resolve_bot_token
        label = getattr(user, 'full_name', None) or (user.email if user else '')
        text = build_daily_digest_for_user(user_id, user_label=label or '')
        token = resolve_bot_token(getattr(settings, 'bot_token', None))
        ok = send_telegram_html(settings.chat_id, text, bot_token=token)
        if not ok:
            return jsonify({'success': False, 'error': 'Failed to send digest'}), 500
        return jsonify({'success': True, 'message': 'Daily digest sent', 'preview': text}), 200
    except Exception as e:
        logger.error(f"Telegram digest error: {e}")
        return jsonify({'error': 'Failed to send digest'}), 500


@bp.route('/api/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Inbound Telegram updates (set via setWebhook). No JWT — verified by shared secret header optional."""
    try:
        from bot.telegram_bot import handle_update_payload, webhook_secret_ok

        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') or request.args.get('secret') or ''
        if not webhook_secret_ok(secret):
            # Still accept when secret not configured yet (first boot), but log.
            from bot.telegram_bot import expected_webhook_secret
            if expected_webhook_secret():
                return jsonify({'ok': False}), 403

        payload = request.get_json(silent=True) or {}
        handle_update_payload(payload)
        return jsonify({'ok': True}), 200
    except Exception as e:
        logger.error("Telegram webhook error: %s", e)
        return jsonify({'ok': False}), 200  # always 200 to avoid Telegram retries storms
