"""accounts routes extracted from run_test_v2."""
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

bp = Blueprint('accounts', __name__)


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



@bp.route('/api/accounts', methods=['GET', 'POST'])
@jwt_required()
def api_accounts():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    if request.method == 'GET':
        _ensure_release_runtime_user_state(user)
        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        enriched = orch.list_account_trust(user_id)
        for row in enriched:
            row['credentials_ok'] = _credentials_ok(row, user)
            if not row['credentials_ok']:
                row['trust_reason'] = (row.get('trust_reason') or '') + ' — re-save password'
        prepare_summary = runtime_store.get_user_task_summary(user_id, 'prepare_account')
        prepare_task = prepare_summary.get('task')
        prepare_progress = prepare_summary.get('progress') or {}
        return jsonify({
            'accounts': enriched,
            'session': runtime_store.get_latest_session(user_id),
            'prepare_status': {
                'task_id': prepare_task.get('id') if prepare_task else None,
                'status': prepare_task.get('status', 'idle') if prepare_task else 'idle',
                'step': prepare_progress.get('step', ''),
                'message': prepare_progress.get('message', ''),
                'progress': prepare_progress.get('progress', 0),
                'error': prepare_progress.get('error') or (
                    prepare_task.get('error_message') if prepare_task else None
                ),
            },
        })

    data = request.get_json() or {}
    login_email = (data.get('login_email') or '').strip()
    password = (data.get('password') or '').strip()
    if not login_email:
        return jsonify({'error': 'login_email is required'}), 400
    # Preserve existing ciphertext when password field left blank (update metadata only)
    encrypted_password = encrypt_password(password) if password else None
    profile_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        'user_data', 'profiles', f"profile_user_{user_id}_{login_email.split('@')[0]}",
    )
    existing = next(
        (a for a in runtime_store.list_accounts(user_id) if (a.get('login_email') or '').lower() == login_email.lower()),
        None,
    )
    if encrypted_password is None and existing and existing.get('encrypted_password'):
        encrypted_password = existing['encrypted_password']
    elif encrypted_password is None:
        encrypted_password = ''
    from app.services.account_orchestrator import AccountOrchestrator
    from app.core.config import AppConfig

    hourly, daily = AccountOrchestrator.normalize_new_account_limits(
        int(data.get('hourly_limit', 0) or 0),
        int(data.get('daily_limit', 0) or 0),
        is_new=existing is None,
    )
    account_id = runtime_store.upsert_account(
        user_id=user_id,
        login_email=login_email,
        encrypted_password=encrypted_password,
        label=(data.get('label') or (existing or {}).get('label') or login_email).strip(),
        is_primary=bool(data.get('is_primary')),
        is_active=bool(data.get('is_active', True)),
        priority=int(data.get('priority', 0) or 0),
        hourly_limit=hourly,
        daily_limit=daily,
        notes=data.get('notes'),
        profile_dir=data.get('profile_dir') or (existing or {}).get('profile_dir') or profile_dir,
    )
    # Keep primary User credentials in sync when password was provided
    if password:
        user.facebook_username = login_email
        user.facebook_password = encrypted_password
        db.session.commit()
    return jsonify({
        'message': 'Account saved',
        'account_id': account_id,
        'hourly_limit': hourly,
        'daily_limit': daily,
        'hard_max_hourly': AppConfig.HARD_MAX_HOURLY_POST_LIMIT,
        'hard_max_daily': AppConfig.HARD_MAX_DAILY_POST_LIMIT,
        'warmup_days': AppConfig.ACCOUNT_WARMUP_DAYS,
    }), 201

@bp.route('/api/account/status', methods=['GET'])
@jwt_required()
def api_account_status():
    user_id = int(get_jwt_identity())
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    return jsonify({
        'accounts': orch.list_account_trust(user_id),
        'session': runtime_store.get_latest_session(user_id),
        'current_task': runtime_store.get_latest_task(user_id, 'posting'),
        'prepare_task': runtime_store.get_latest_task(user_id, 'prepare_account'),
    })

@bp.route('/accounts')
@jwt_required()
def accounts_page():
    user_id = int(get_jwt_identity())
    current_user = User.query.get(user_id)
    if not current_user:
        return jsonify({'error': 'User not found'}), 404
    _ensure_release_runtime_user_state(current_user)
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    accounts = orch.list_account_trust(user_id)
    return render_template(
        'accounts.html',
        current_user=current_user,
        accounts=accounts,
    )

@bp.route('/api/accounts/<int:account_id>/trust', methods=['GET'])
@jwt_required()
def api_account_trust(account_id: int):
    user_id = int(get_jwt_identity())
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404
    trust = runtime_store.get_account_trust(account_id)
    return jsonify(trust), 200

@bp.route('/api/accounts/<int:account_id>/prepare', methods=['POST'])
@jwt_required()
def api_account_prepare(account_id: int):
    """Start Prepare Account (visible Chrome + CAPTCHA wait)."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404

    active = runtime_store.get_latest_task(user_id, 'prepare_account')
    if active and active.get('status') in ('queued', 'running', 'waiting_manual'):
        return jsonify({'error': 'Prepare already in progress', 'task': active}), 400

    username, password = _account_credentials(account, user)
    if not username or not password:
        return jsonify({
            'error': 'Account credentials missing or undecryptable — re-save password on /accounts',
            'code': 'CREDENTIALS_MISSING',
            'hint': '/accounts',
        }), 400

    from bot.account_preparer import AccountPreparer
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)

    def _runner(task_id: int) -> dict:
        from app.services.task_control import CooperativeTaskControl, DurableControlMonitor, TaskStopped
        tracker = reset_progress_tracker(user_id)
        tracker.start()
        runtime_store.append_task_event(task_id, 'Prepare account started', event_type='system')

        def _progress(payload: dict):
            control.checkpoint(on_stop=preparer.signal_resume_manual, allow_pause=False)
            tracker.update(**payload)
            status = payload.get('status')
            if status == 'waiting_manual':
                runtime_store.update_task(task_id, status='waiting_manual', heartbeat_at=datetime.utcnow().isoformat())
                orch.mark_needs_verify(user_id, account_id, payload.get('message') or 'Manual verification required')
            runtime_store.append_task_event(
                task_id,
                payload.get('message') or payload.get('step') or 'prepare-progress',
                event_type='progress',
                metadata=payload,
            )
            broadcast_to_user(user_id, 'prepare_progress', {**payload, 'account_id': account_id, 'task_id': task_id})

        preparer = AccountPreparer(
            user_id=user_id,
            account_id=account_id,
            username=username,
            password=password,
            profile_dir=account.get('profile_dir'),
            progress_callback=_progress,
        )
        control = CooperativeTaskControl(runtime_store, task_id, user_id)
        try:
            control.checkpoint(allow_pause=False)
            with DurableControlMonitor(control, preparer.stop):
                result = preparer.prepare()
            state = runtime_store.get_control_state(task_id, user_id)
            if state and state.get('acknowledged_state') == 'stopping':
                return {'status': 'cancelled', 'error_message': 'Stopped by user'}
        except TaskStopped:
            return {'status': 'cancelled', 'error_message': 'Stopped by user'}
        if result.get('trusted'):
            orch.mark_trusted(user_id, account_id, profile_dir=result.get('profile_dir'))
            tracker.update(status='completed', progress=100, message='Trusted')
            tracker.finish(success=True)
            result = {**result, 'status': 'completed'}
        else:
            task_status = 'waiting_manual' if result.get('needs_manual') or result.get('status') == 'needs_verify' else 'failed'
            tracker.update(status=task_status, error=result.get('error'), progress=tracker.progress)
            tracker.finish(success=False)
            result = {**result, 'status': task_status, 'error_message': result.get('error')}
        return result

    task = task_manager.start_task(
        user_id=user_id,
        task_type='prepare_account',
        title=f"Prepare account #{account_id}",
        payload={'account_id': account_id},
        runner=_runner,
        task_key=f'prepare:{user_id}:{account_id}',
    )
    return jsonify({'message': 'Prepare started', 'task': task, 'task_id': task.get('id')}), 202

@bp.route('/api/accounts/<int:account_id>/validate', methods=['POST'])
@jwt_required()
def api_account_validate(account_id: int):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404
    username, password = _account_credentials(account, user)
    if not username:
        return jsonify({'error': 'Account login missing'}), 400

    from bot.account_preparer import AccountPreparer
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    preparer = AccountPreparer(
        user_id=user_id,
        account_id=account_id,
        username=username,
        password=password or 'x',
        profile_dir=account.get('profile_dir'),
    )
    result = preparer.validate_only()
    if result.get('trusted'):
        orch.mark_trusted(user_id, account_id, profile_dir=result.get('profile_dir'))
    else:
        orch.mark_needs_verify(user_id, account_id, result.get('error') or 'Session invalid')
    return jsonify(result), 200

@bp.route('/api/accounts/<int:account_id>/resume-manual', methods=['POST'])
@jwt_required()
def api_account_resume_manual(account_id: int):
    """Signal that user completed CAPTCHA/2FA in the open Chrome window."""
    user_id = int(get_jwt_identity())
    account = runtime_store.get_account(account_id)
    if not account or int(account.get('user_id') or 0) != user_id:
        return jsonify({'error': 'Account not found'}), 404

    from bot.account_preparer import get_active_preparer
    preparer = get_active_preparer(account_id)
    signaled = False
    if preparer:
        signaled = preparer.signal_resume_manual()

    # Also nudge active fetcher/poster if they share the challenge.
    global fetcher_instance, poster_instance
    if fetcher_instance and getattr(fetcher_instance, 'manual_verification_needed', False):
        setattr(fetcher_instance, 'manual_resume_requested', True)
        signaled = True
    if poster_instance and getattr(poster_instance, 'manual_verification_needed', False):
        setattr(poster_instance, 'manual_resume_requested', True)
        signaled = True

    if not signaled:
        # No live browser — validate saved profile as fallback
        user = User.query.get(user_id)
        username, password = _account_credentials(account, user)
        from bot.account_preparer import AccountPreparer
        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        preparer = AccountPreparer(
            user_id=user_id,
            account_id=account_id,
            username=username or account.get('login_email') or '',
            password=password or 'x',
            profile_dir=account.get('profile_dir'),
        )
        result = preparer.validate_only()
        if result.get('trusted'):
            orch.mark_trusted(user_id, account_id, profile_dir=result.get('profile_dir'))
        else:
            orch.mark_needs_verify(user_id, account_id, result.get('error') or 'Session invalid')
        return jsonify({'message': 'No live browser — validated profile', **result}), 200

    get_progress_tracker(user_id).update(
        status='waiting_manual',
        step='manual_resume',
        message='Проверяем после ручной верификации...',
        progress=25,
    )
    return jsonify({'message': 'Resume signal sent', 'signaled': True}), 200

@bp.route('/api/accounts/pick', methods=['POST'])
@jwt_required()
def api_accounts_pick():
    """Pick best trusted account for automation (rotation)."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    from app.services.account_orchestrator import AccountOrchestrator
    orch = AccountOrchestrator(runtime_store)
    preferred = data.get('account_id')
    exclude = set(int(x) for x in (data.get('exclude_ids') or []) if str(x).isdigit())
    account, reason = orch.pick_account(
        user_id,
        preferred_account_id=int(preferred) if preferred else None,
        require_trusted=bool(data.get('require_trusted', True)),
        exclude_ids=exclude,
    )
    if not account:
        return jsonify({'error': reason or 'No account available', 'code': 'NO_ACCOUNT'}), 409
    return jsonify({'account': account}), 200


@bp.route('/api/accounts/<int:account_id>/clear-cooldown', methods=['POST'])
@jwt_required()
def api_account_clear_cooldown(account_id: int):
    """Manually clear account cooldown after verification / false positive."""
    user_id = int(get_jwt_identity())
    from app.services.account_orchestrator import AccountOrchestrator
    ok, message = AccountOrchestrator(runtime_store).clear_cooldown(user_id, account_id)
    if not ok:
        return jsonify({'error': message}), 404
    return jsonify({'message': message}), 200


@bp.route('/api/accounts/safety-defaults', methods=['GET'])
@jwt_required()
def api_account_safety_defaults():
    """Expose safe defaults / hard caps for the Accounts UI."""
    from app.core.config import AppConfig
    from bot.account_safety import safe_default_limits

    hourly, daily = safe_default_limits()
    return jsonify({
        'default_hourly': hourly,
        'default_daily': daily,
        'hard_max_hourly': AppConfig.HARD_MAX_HOURLY_POST_LIMIT,
        'hard_max_daily': AppConfig.HARD_MAX_DAILY_POST_LIMIT,
        'cooldown_minutes': AppConfig.ACCOUNT_COOLDOWN_MINUTES,
        'warmup_days': AppConfig.ACCOUNT_WARMUP_DAYS,
        'warmup_hourly': AppConfig.WARMUP_HOURLY_POST_LIMIT,
        'warmup_daily': AppConfig.WARMUP_DAILY_POST_LIMIT,
        'auto_stop_on_verification': AppConfig.AUTO_STOP_ON_VERIFICATION,
        'max_consecutive_failures': AppConfig.MAX_CONSECUTIVE_FAILURES,
    }), 200

