"""groups routes extracted from run_test_v2."""
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

bp = Blueprint('groups', __name__)


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



@bp.route('/export/groups/<format>')
@jwt_required()
def export_groups(format):
    """Export fetched groups in JSON, CSV, Excel, or ZIP formats."""
    try:
        user_id = int(get_jwt_identity())
        groups = get_fetched_groups(user_id)
        export_format = (format or 'json').lower()

        if not groups:
            return jsonify({'error': 'No groups available to export'}), 404

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        base_name = f"facebook_groups_{user_id}_{timestamp}"

        if export_format == 'json':
            payload = json.dumps(groups, ensure_ascii=False, indent=2).encode('utf-8')
            return send_file(
                io.BytesIO(payload),
                mimetype='application/json',
                as_attachment=True,
                download_name=f'{base_name}.json'
            )

        columns, rows = _prepare_groups_export_rows(groups)

        def build_csv_bytes() -> bytes:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=columns or ['value'])
            writer.writeheader()
            if rows:
                writer.writerows(rows)
            return output.getvalue().encode('utf-8-sig')

        if export_format == 'csv':
            return send_file(
                io.BytesIO(build_csv_bytes()),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'{base_name}.csv'
            )

        if export_format == 'excel':
            try:
                import pandas as pd
            except ImportError:
                return jsonify({'error': 'Excel export is unavailable because pandas is not installed'}), 501

            excel_buffer = io.BytesIO()
            pd.DataFrame(rows or [{'value': ''}], columns=columns or ['value']).to_excel(excel_buffer, index=False)
            excel_buffer.seek(0)
            return send_file(
                excel_buffer,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'{base_name}.xlsx'
            )

        if export_format == 'all':
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(f'{base_name}.json', json.dumps(groups, ensure_ascii=False, indent=2))
                archive.writestr(f'{base_name}.csv', build_csv_bytes())
                try:
                    import pandas as pd
                    excel_buffer = io.BytesIO()
                    pd.DataFrame(rows or [{'value': ''}], columns=columns or ['value']).to_excel(excel_buffer, index=False)
                    archive.writestr(f'{base_name}.xlsx', excel_buffer.getvalue())
                except ImportError:
                    pass
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'{base_name}.zip'
            )

        return jsonify({'error': 'Unsupported export format'}), 400
    except Exception as e:
        logger.error(f"Export groups error: {e}")
        return jsonify({'error': f'Failed to export groups: {str(e)}'}), 500

@bp.route('/api/start_fetch', methods=['POST'])
@jwt_required()
def start_fetch():
    """Start fetching Facebook groups using Selenium fetcher"""
    global fetcher_instance
    try:
        data = request.get_json() or {}
        user_id = int(get_jwt_identity())
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Gate on fetch task only — prepare/post use the same progress_tracker
        active_fetch = runtime_store.get_latest_task(user_id, 'fetch')
        if active_fetch and active_fetch.get('status') in ('queued', 'running', 'waiting_manual', 'paused'):
            return jsonify({'error': 'Fetch task already in progress', 'task': active_fetch}), 400

        username = (data.get('username') or user.facebook_username or '').strip()
        password = (data.get('password') or (decrypt_password(user.facebook_password) if user.facebook_password else '')).strip()
        headless = bool(data.get('headless', False))
        use_session = bool(data.get('use_session', True))
        account_id = data.get('account_id')
        auto_rotate = bool(data.get('auto_rotate', True))

        from app.services.account_orchestrator import AccountOrchestrator
        orch = AccountOrchestrator(runtime_store)
        selected_account = None
        has_saved_accounts = bool(runtime_store.list_accounts(user_id))
        if account_id or auto_rotate or has_saved_accounts:
            selected_account, pick_reason = orch.pick_account(
                user_id,
                preferred_account_id=int(account_id) if account_id else None,
                require_trusted=True,
            )
            if not selected_account and (account_id or has_saved_accounts):
                return jsonify({
                    'error': pick_reason or 'Session not trusted. Prepare account first.',
                    'code': 'SESSION_NOT_TRUSTED',
                    'hint': '/accounts',
                }), 403
            if selected_account:
                account_id = int(selected_account['id'])
                username, password = _account_credentials(selected_account, user)

        if not username or not password:
            return jsonify({
                'error': 'Facebook credentials required — re-save password on /accounts',
                'hint': '/accounts',
            }), 400

        # Persist credentials encrypted (never log)
        user.facebook_username = username
        user.facebook_password = encrypt_password(password)
        db.session.commit()
        _ensure_release_runtime_user_state(user)

        def _runner(task_id: int) -> dict:
            global fetcher_instance
            from app.services.task_control import CooperativeTaskControl, DurableControlMonitor, TaskStopped
            if not _load_facebook_automation():
                raise RuntimeError('Facebook group fetcher is unavailable')
            tracker = reset_progress_tracker(user_id)
            tracker.start()
            runtime_store.append_task_event(task_id, 'Fetch task started', event_type='system')

            def _fetch_progress(payload: dict):
                control.checkpoint(
                    on_stop=lambda: (
                        setattr(fetcher, 'is_fetching', False),
                        fetcher.cleanup(),
                    ),
                    allow_pause=False,
                )
                tracker.update(**payload)
                if payload.get('status') == 'waiting_manual' and account_id:
                    runtime_store.update_task(task_id, status='waiting_manual')
                    orch.mark_needs_verify(
                        user_id, int(account_id),
                        payload.get('message') or 'Manual verification required',
                    )
                runtime_store.append_task_event(
                    task_id,
                    payload.get('step') or 'fetch-progress',
                    event_type='progress',
                    metadata=payload,
                )
                broadcast_to_user(user_id, 'fetch_progress', payload)

            fetcher = FacebookGroupFetcher(
                username=username,
                password=password,
                headless=headless,
                use_session=use_session,
                user_id=user_id,
                progress_callback=_fetch_progress,
            )
            control = CooperativeTaskControl(runtime_store, task_id, user_id)
            if account_id and selected_account and selected_account.get('profile_dir'):
                fetcher.profile_dir = selected_account['profile_dir']
            fetcher_instance = fetcher
            try:
                control.checkpoint(on_stop=fetcher.cleanup, allow_pause=False)
                with DurableControlMonitor(control, fetcher.cleanup):
                    groups = fetcher.fetch_groups()
                state = runtime_store.get_control_state(task_id, user_id)
                if state and state.get('acknowledged_state') == 'stopping':
                    return {'status': 'cancelled', 'error_message': 'Stopped by user'}
            except TaskStopped:
                return {'status': 'cancelled', 'error_message': 'Stopped by user'}
            if groups is None:
                err = fetcher.error or 'Fetch failed'
                if account_id and getattr(fetcher, 'manual_verification_needed', False):
                    orch.mark_needs_verify(user_id, int(account_id), err, checkpoint=True)
                tracker.update(status='failed', error=err)
                tracker.finish(success=False)
                raise RuntimeError(err)

            if account_id:
                orch.mark_trusted(user_id, int(account_id), profile_dir=fetcher.profile_dir)
            save_fetched_groups(user_id, groups)
            tracker.update(status='completed', total_groups=len(groups), progress=100)
            tracker.finish(success=True)
            runtime_store.append_task_event(task_id, f'Fetched {len(groups)} groups', event_type='result')
            return {'status': 'completed', 'groups_found': len(groups), 'account_id': account_id}

        task = task_dispatcher.start_fetch(
            user_id=user_id,
            title='Fetch Facebook groups',
            payload={'headless': headless, 'use_session': use_session, 'account_id': account_id},
            local_runner=_runner,
        )
        return jsonify({
            'message': 'Fetching started',
            'task': task,
            'task_id': task.get('id'),
            'mode': task.get('queue_mode', 'local_persistent'),
            'account_id': account_id,
        }), 202

    except Exception as e:
        logger.error(f"Start fetch error: {e}")
        return jsonify({'error': str(e) or 'Failed to start fetching'}), 500

@bp.route('/api/progress', methods=['GET'])
@jwt_required()
def get_progress():
    user_id = int(get_jwt_identity())
    task_id = request.args.get('task_id', type=int)
    task = runtime_store.get_task_for_user(task_id, user_id) if task_id else None
    if task_id and not task:
        return jsonify({'error': 'Task not found'}), 404
    summary = runtime_store.get_user_task_summary(user_id)
    task = task or summary.get('task')
    progress = {}
    if task:
        progress = next(
            ((event.get('metadata') or {}) for event in reversed(task.get('events') or [])
             if event.get('event_type') == 'progress'),
            {},
        )
    return jsonify({
        'task_id': task.get('id') if task else None,
        'status': task.get('status', 'idle') if task else 'idle',
        'step': progress.get('step', ''),
        'progress': progress.get('progress', 0),
        'total_groups': progress.get('total_groups', 0),
        'current_scroll': progress.get('current_scroll', 0),
        'max_scroll': progress.get('max_scroll', 0),
        'error': progress.get('error') or (task.get('error_message') if task else None),
        'message': progress.get('message', ''),
        'elapsed_time': progress.get('elapsed_time', 0),
        'task': task,
    })

@bp.route('/api/groups', methods=['GET'])
@jwt_required()
def get_groups_api():
    try:
        user_id = get_jwt_identity()
        groups = get_fetched_groups(user_id)
        try:
            from bot.language_classifier import LanguageClassifier
            groups = LanguageClassifier.classify_groups_batch(groups)
        except Exception:
            pass
        try:
            from bot.geo_classifier import GeoClassifier
            groups = GeoClassifier.classify_groups_batch(groups)
        except Exception:
            pass
        workspace_map = runtime_store.get_group_workspace_map(int(user_id))
        for group in groups:
            meta = workspace_map.get(group.get('url', '')) or {}
            if meta:
                group['workspace'] = meta
        return jsonify({'groups': groups, 'total': len(groups)})
    except Exception as e:
        logger.error(f"Get groups error: {e}")
        return jsonify({'error': 'Failed to get groups'}), 500

@bp.route('/api/groups/workspace', methods=['GET', 'POST'])
@jwt_required()
def api_groups_workspace():
    user_id = int(get_jwt_identity())
    if request.method == 'GET':
        return jsonify({'workspace': list(runtime_store.get_group_workspace_map(user_id).values())})

    data = request.get_json() or {}
    group_url = data.get('group_url')
    if not group_url:
        return jsonify({'error': 'group_url is required'}), 400
    runtime_store.upsert_group_workspace(
        user_id,
        group_url,
        group_name=data.get('group_name'),
        is_blacklisted=bool(data.get('is_blacklisted')),
        is_whitelisted=bool(data.get('is_whitelisted')),
        tags=data.get('tags', []),
        notes=data.get('notes'),
        last_posted_at=data.get('last_posted_at'),
        last_post_status=data.get('last_post_status'),
        last_campaign_name=data.get('last_campaign_name'),
    )
    return jsonify({'message': 'Workspace updated'})

@bp.route('/api/groups/filters', methods=['GET', 'POST'])
@jwt_required()
def api_group_filters():
    user_id = int(get_jwt_identity())
    if request.method == 'GET':
        return jsonify({'filters': runtime_store.list_filters(user_id)})

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    config = data.get('config') or {}
    if not name:
        return jsonify({'error': 'Filter name is required'}), 400
    filter_id = runtime_store.save_filter(user_id, name, config, is_default=bool(data.get('is_default')))
    return jsonify({'message': 'Filter saved', 'filter_id': filter_id}), 201

