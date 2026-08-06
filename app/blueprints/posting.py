"""posting routes extracted from run_test_v2."""
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

bp = Blueprint('posting', __name__)


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



@bp.route('/api/post_to_groups', methods=['POST'])
@jwt_required()
def api_post_to_groups():
    global poster_instance
    try:
        data = request.get_json() or {}
        message = data.get('message', '').strip()
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        username = (data.get('username') or user.facebook_username or '').strip()
        password = (data.get('password') or (decrypt_password(user.facebook_password) if user.facebook_password else '')).strip()
        group_urls = data.get('group_urls', [])
        headless = bool(data.get('headless', True))
        max_groups = int(data.get('max_groups', 20))
        use_templates = bool(data.get('use_templates', False))
        template_mode = data.get('template_mode', 'random')
        account_id = data.get('account_id')
        campaign_name = (data.get('campaign_name') or '').strip()
        auto_rotate = bool(data.get('auto_rotate', True))

        if not use_templates and not message:
            return jsonify({'error': 'Message is required'}), 400
        if not group_urls:
            return jsonify({'error': 'No groups selected'}), 400

        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        selected_account, pick_reason = orch.pick_account(
            user_id,
            preferred_account_id=int(account_id) if account_id else None,
            require_trusted=True,
        )
        if not selected_account:
            # Allow legacy form credentials only if no saved accounts exist
            if runtime_store.list_accounts(user_id):
                return jsonify({
                    'error': pick_reason or 'No trusted account available. Prepare an account first.',
                    'code': 'SESSION_NOT_TRUSTED',
                    'hint': '/accounts',
                }), 403
        else:
            account_id = int(selected_account['id'])
            username, password = _account_credentials(selected_account, user)

        if not username or not password:
            return jsonify({'error': 'Facebook credentials required'}), 400

        # Persist credentials encrypted (never log)
        user.facebook_username = username
        user.facebook_password = encrypt_password(password)
        db.session.commit()
        _ensure_release_runtime_user_state(user)
        tg_settings = TelegramSettings.query.filter_by(user_id=user_id).first()
        if tg_settings and tg_settings.is_active:
            send_telegram_message(
                tg_settings.chat_id,
                f"Campaign started\nGroups: {len(group_urls[:max_groups])}\nMode: {template_mode}\nHeadless: {'yes' if headless else 'no'}\nAccount: {account_id or 'legacy'}",
            )

        task = _start_local_posting_thread(
            user_id=int(user_id),
            username=username,
            password=password,
            message=message,
            group_urls=group_urls,
            headless=headless,
            use_templates=use_templates,
            template_mode=template_mode,
            max_groups=max_groups,
            account_id=int(account_id) if account_id else None,
            campaign_name=campaign_name,
        )
        return jsonify({
            'message': 'Posting started',
            'task': task,
            'task_id': task.get('id'),
            'mode': task.get('queue_mode', 'local_persistent'),
            'account_id': account_id,
            'auto_rotate': auto_rotate,
        }), 202
    except Exception as e:
        logger.error(f"api_post_to_groups error: {e}")
        return jsonify({'error': str(e) or 'Failed to start posting'}), 500

@bp.route('/api/posting_status')
@jwt_required()
def api_posting_status():
    user_id = int(get_jwt_identity())
    task_id = request.args.get('task_id', type=int)
    task = runtime_store.get_task_for_user(task_id, user_id) if task_id else runtime_store.get_latest_task(user_id, 'posting')
    if task_id and not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(_task_snapshot_from_poster(user_id, task, None))

@bp.route('/api/stop_posting', methods=['POST'])
@jwt_required()
def api_stop_posting():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json(silent=True) or {}
        task_id = data.get('task_id')
        task = runtime_store.get_task_for_user(int(task_id), user_id) if task_id else runtime_store.get_active_task(user_id, 'posting')
        if task and runtime_store.request_stop(task['id'], user_id):
            return jsonify({'message': 'Stop requested', 'status': 'stopping', 'task_id': task['id']}), 202
        return jsonify({'error': 'No posting in progress'}), 400
    except Exception as e:
        logger.error(f"stop_posting error: {e}")
        return jsonify({'error': 'Failed to stop'}), 500

@bp.route('/api/pause_posting', methods=['POST'])
@jwt_required()
def api_pause_posting():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    task = runtime_store.get_task_for_user(int(task_id), user_id) if task_id else runtime_store.get_active_task(user_id, 'posting')
    if task and runtime_store.request_pause(task['id'], user_id):
        return jsonify({'message': 'Posting pause requested', 'task_id': task['id']}), 202
    return jsonify({'error': 'No posting in progress'}), 400

@bp.route('/api/resume_posting', methods=['POST'])
@jwt_required()
def api_resume_posting():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    task_id = data.get('task_id')
    task = runtime_store.get_task_for_user(int(task_id), user_id) if task_id else runtime_store.get_active_task(user_id, 'posting')
    if task and task.get('task_type') == 'posting' and runtime_store.request_resume(task['id'], user_id):
        return jsonify({'message': 'Posting resume requested', 'task_id': task['id']}), 202
    return jsonify({'error': 'No paused posting found'}), 400

@bp.route('/api/tasks', methods=['GET'])
@jwt_required()
def api_list_tasks():
    user_id = int(get_jwt_identity())
    task_type = request.args.get('task_type')
    limit = min(int(request.args.get('limit', 25) or 25), 100)
    return jsonify({'tasks': runtime_store.list_tasks(user_id, task_type=task_type, limit=limit)})

@bp.route('/api/tasks/<int:task_id>', methods=['GET'])
@jwt_required()
def api_get_task(task_id):
    task = runtime_store.get_task_for_user(task_id, int(get_jwt_identity()))
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)

@bp.route('/api/tasks/<int:task_id>/stop', methods=['POST'])
@jwt_required()
def api_stop_task(task_id):
    user_id = int(get_jwt_identity())
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    if not runtime_store.request_stop(task_id, user_id):
        return jsonify({'error': 'Task is not active'}), 409
    return jsonify({'message': 'Stop requested', 'task_id': task_id, 'status': 'stopping'}), 202

@bp.route('/api/tasks/<int:task_id>/pause', methods=['POST'])
@jwt_required()
def api_pause_task(task_id):
    user_id = int(get_jwt_identity())
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    if task.get('task_type') != 'posting':
        return jsonify({
            'error': f"Pause is not supported for {task.get('task_type')} tasks",
            'supported_actions': ['stop'],
        }), 409
    if not runtime_store.request_pause(task_id, user_id):
        return jsonify({'error': 'Task is not active'}), 409
    return jsonify({'message': 'Pause requested', 'task_id': task_id}), 202

@bp.route('/api/tasks/<int:task_id>/resume', methods=['POST'])
@jwt_required()
def api_resume_task(task_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not user or not task:
        return jsonify({'error': 'Task not found'}), 404
    if task.get('task_type') != 'posting':
        return jsonify({
            'error': f"Resume is not supported for {task.get('task_type')} tasks",
            'supported_actions': ['stop'],
        }), 409
    if task.get('status') in ('queued', 'running', 'paused', 'waiting_manual', 'stopping'):
        if runtime_store.request_resume(task_id, user_id):
            return jsonify({'message': 'Resume requested', 'task_id': task_id}), 202
        return jsonify({'error': 'Task is not active'}), 409
    payload = task.get('payload') or {}
    groups = runtime_store.get_resumable_groups(task_id)
    if not groups:
        return jsonify({'error': 'No groups left to resume'}), 400
    password = decrypt_password(user.facebook_password) if user.facebook_password else ''
    if payload.get('account_id'):
        account = runtime_store.get_account(int(payload['account_id']))
        if account and account.get('encrypted_password'):
            password = decrypt_password(account['encrypted_password'])
    resume_task = _start_local_posting_thread(
        user_id=user_id,
        username=user.facebook_username or payload.get('username', ''),
        password=password,
        message=payload.get('message', ''),
        group_urls=groups,
        headless=bool(payload.get('headless', True)),
        use_templates=bool(payload.get('use_templates', False)),
        template_mode=payload.get('template_mode', 'random'),
        max_groups=len(groups),
        account_id=payload.get('account_id'),
        campaign_name=(payload.get('campaign_name') or f'Resume task #{task_id}'),
        skip_success_urls=runtime_store.get_success_group_urls(task_id),
        resumed_from_task_id=task_id,
    )
    return jsonify({'message': 'Resume started', 'task': resume_task, 'groups_remaining': len(groups)}), 202

@bp.route('/api/tasks/<int:task_id>/retry_failed', methods=['POST'])
@jwt_required()
def api_retry_failed_task_groups(task_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    task = runtime_store.get_task_for_user(task_id, user_id)
    if not user or not task:
        return jsonify({'error': 'Task not found'}), 404
    failed_groups = runtime_store.get_failed_groups(task_id)
    if not failed_groups:
        return jsonify({'error': 'No failed groups to retry'}), 400
    payload = task.get('payload', {})
    password = decrypt_password(user.facebook_password) if user.facebook_password else ''
    retry_task = _start_local_posting_thread(
        user_id=user_id,
        username=user.facebook_username or payload.get('username', ''),
        password=password,
        message=payload.get('message', ''),
        group_urls=failed_groups,
        headless=bool(payload.get('headless', True)),
        use_templates=bool(payload.get('use_templates', False)),
        template_mode=payload.get('template_mode', 'random'),
        max_groups=len(failed_groups),
        account_id=payload.get('account_id'),
        campaign_name=(payload.get('campaign_name') or 'Retry failed groups'),
    )
    return jsonify({'message': 'Retry started', 'task': retry_task}), 202

@bp.route('/api/validate_message', methods=['POST'])
@jwt_required()
def api_validate_message():
    try:
        data = request.get_json() or {}
        msg = data.get('message', '')
        if not msg.strip():
            return jsonify({'valid': False, 'error': 'Message cannot be empty'})
        links = msg.count('http://') + msg.count('https://')
        words = len(msg.split())
        return jsonify({'valid': True, 'stats': {'length': len(msg), 'words': words, 'links': links, 'emojis': 0}})
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)})

