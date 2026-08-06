"""scheduler routes extracted from run_test_v2."""
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

bp = Blueprint('scheduler', __name__)


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



@bp.route('/api/scheduler/jobs', methods=['GET'])
@jwt_required()
def get_scheduled_jobs():
    """Get user's scheduled jobs"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        jobs = ScheduledJob.query.filter_by(user_id=user_id).order_by(ScheduledJob.created_at.desc()).all()
        
        return jsonify({
            'jobs': [job.to_dict() for job in jobs]
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': 'Failed to get scheduled jobs',
            'message': str(e),
            'code': 'GET_JOBS_ERROR'
        }), 500

@bp.route('/api/scheduler/jobs', methods=['POST'])
@jwt_required()
@limiter.limit("50 per 15 minutes")  # Limit job creation
def create_scheduled_job():
    """Create a new scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'cron_expression', 'campaign_data']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields',
                'missing_fields': missing_fields,
                'code': 'MISSING_FIELDS'
            }), 400
        
        # Validate cron expression
        try:
            from apscheduler.triggers.cron import CronTrigger

            CronTrigger.from_crontab(data['cron_expression'])
        except Exception as e:
            return jsonify({
                'error': 'Invalid cron expression',
                'message': str(e),
                'code': 'INVALID_CRON'
            }), 400
        
        # Create scheduled job
        job = ScheduledJob(
            user_id=user_id,
            name=data['name'],
            cron_expression=data['cron_expression'],
            campaign_data=json.dumps(data['campaign_data']),
            status='active'
        )
        
        db.session.add(job)
        db.session.commit()
        
        # Add job to scheduler
        global job_scheduler
        job_data = {
            'name': job.name,
            'message': data['campaign_data'].get('message', ''),
            'target_groups': data['campaign_data'].get('target_groups', []),
            'max_groups': data['campaign_data'].get('max_groups', 10),
            'min_delay': data['campaign_data'].get('min_delay', 10),
            'max_delay': data['campaign_data'].get('max_delay', 60)
        }
        
        success = job_scheduler.schedule_job(job.id, user_id, job_data)
        
        if not success:
            # Delete the job if scheduling failed
            db.session.delete(job)
            db.session.commit()
            return jsonify({
                'error': 'Failed to schedule job',
                'code': 'SCHEDULE_ERROR'
            }), 500
        
        # Notify via WebSocket
        socketio.emit('job_scheduled', {
            'job_id': job.id,
            'user_id': user_id,
            'name': job.name,
            'message': f'Job "{job.name}" scheduled successfully'
        }, room=f'user_{user_id}')
        
        return jsonify({
            'message': 'Job scheduled successfully',
            'job': job.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to create scheduled job',
            'message': str(e),
            'code': 'CREATE_JOB_ERROR'
        }), 500

@bp.route('/api/scheduler/jobs/<int:job_id>', methods=['PUT'])
@jwt_required()
def update_scheduled_job(job_id):
    """Update a scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        data = request.get_json()
        
        # Update job fields
        if 'name' in data:
            job.name = data['name']
        if 'cron_expression' in data:
            # Validate cron expression
            try:
                from apscheduler.triggers.cron import CronTrigger

                CronTrigger.from_crontab(data['cron_expression'])
                job.cron_expression = data['cron_expression']
            except Exception as e:
                return jsonify({
                    'error': 'Invalid cron expression',
                    'message': str(e),
                    'code': 'INVALID_CRON'
                }), 400
        if 'campaign_data' in data:
            job.campaign_data = json.dumps(data['campaign_data'])
        if 'status' in data:
            job.status = data['status']
        
        job.updated_at = datetime.utcnow()
        db.session.commit()
        
        # Update job in scheduler
        global job_scheduler
        job_data = {
            'name': job.name,
            'cron_expression': job.cron_expression,
            'campaign_data': json.loads(job.campaign_data)
        }
        
        job_scheduler.schedule_job(job.id, user_id, job_data)
        
        return jsonify({
            'message': 'Job updated successfully',
            'job': job.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to update job',
            'message': str(e),
            'code': 'UPDATE_JOB_ERROR'
        }), 500

@bp.route('/api/scheduler/jobs/<int:job_id>', methods=['DELETE'])
@jwt_required()
def delete_scheduled_job(job_id):
    """Delete a scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        # Remove from scheduler
        global job_scheduler
        job_scheduler.delete_job(job.id)
        
        # Delete from database
        db.session.delete(job)
        db.session.commit()
        
        return jsonify({
            'message': 'Job deleted successfully'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to delete job',
            'message': str(e),
            'code': 'DELETE_JOB_ERROR'
        }), 500

@bp.route('/api/scheduler/jobs/<int:job_id>/pause', methods=['POST'])
@jwt_required()
def pause_scheduled_job(job_id):
    """Pause a scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        # Pause in scheduler
        global job_scheduler
        success = job_scheduler.pause_job(job.id)
        
        if success:
            job.status = 'paused'
            job.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'message': 'Job paused successfully',
                'job': job.to_dict()
            }), 200
        else:
            return jsonify({
                'error': 'Failed to pause job',
                'code': 'PAUSE_ERROR'
            }), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to pause job',
            'message': str(e),
            'code': 'PAUSE_JOB_ERROR'
        }), 500

@bp.route('/api/scheduler/jobs/<int:job_id>/resume', methods=['POST'])
@jwt_required()
def resume_scheduled_job(job_id):
    """Resume a paused scheduled job"""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        
        job = ScheduledJob.query.filter_by(id=job_id, user_id=user_id).first()
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'code': 'JOB_NOT_FOUND'
            }), 404
        
        # Resume in scheduler
        global job_scheduler
        success = job_scheduler.resume_job(job.id)
        
        if success:
            job.status = 'active'
            job.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'message': 'Job resumed successfully',
                'job': job.to_dict()
            }), 200
        else:
            return jsonify({
                'error': 'Failed to resume job',
                'code': 'RESUME_ERROR'
            }), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to resume job',
            'message': str(e),
            'code': 'RESUME_JOB_ERROR'
        }), 500

