"""templates routes extracted from run_test_v2."""
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

bp = Blueprint('templates', __name__)


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



@bp.route('/api/templates/stats')
@jwt_required()
def get_template_stats():
    """Get template system statistics"""
    try:
        runtime_user_id = _template_runtime_user_id()
        records = runtime_store.list_templates(runtime_user_id)
        # Initialize default stats
        stats = {
            'total_templates': len(records),
            'total_variables': 0, 
            'possible_combinations': 0
        }
        
        # Variables are shared application configuration; template content is user-scoped.
        templates_file = 'templates_data/message_templates.json'
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
                variables = data.get('variables', {})
                stats['total_variables'] = len(variables)
                if records and variables:
                    combinations = 1
                    for var_list in variables.values():
                        if var_list:
                            combinations *= len(var_list)
                    stats['possible_combinations'] = combinations * len(records)
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error getting template stats: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/templates/list')
@jwt_required()
def list_templates():
    """Get list of all templates"""
    try:
        import os
        runtime_user_id = _template_runtime_user_id()
        records = runtime_store.list_templates(runtime_user_id)
        templates = [record['content'] for record in records]
        
        return jsonify({
            'success': True,
            'templates': templates,
            'records': records,
            'count': len(templates)
        })
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/api/templates/variables')
@jwt_required()
def get_template_variables():
    """Get available template variables"""
    try:
        import os
        templates_file = 'templates_data/message_templates.json'
        
        # Default variables
        default_variables = {
            'name': ['Alex', 'Maria', 'John', 'Elena', 'Michael'],
            'product': ['amazing product', 'great service', 'unique opportunity'],
            'company': ['our company', 'our team', 'our platform'],
            'benefit': ['save time', 'increase profit', 'grow business']
        }
        
        variables = default_variables.copy()
        
        # Load custom variables if file exists
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
                saved_variables = data.get('variables', {})
                variables.update(saved_variables)
        
        return jsonify(variables)
    except Exception as e:
        logger.error(f"Error getting template variables: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/templates/add', methods=['POST'])
@jwt_required()
def add_template():
    """Add new template"""
    try:
        import os
        import json
        from datetime import datetime
        
        data = request.get_json()
        template_text = data.get('template', '').strip()
        
        if not template_text:
            return jsonify({'success': False, 'error': 'Template text is required'}), 400
        
        runtime_store.sync_templates(_template_runtime_user_id(), [template_text])
        
        logger.info(f"Template added successfully: {template_text[:50]}...")
        return jsonify({'success': True, 'message': 'Template added successfully'})
        
    except Exception as e:
        logger.error(f"Error adding template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/api/templates/delete', methods=['POST'])
@jwt_required()
def delete_template():
    """Delete specific template"""
    try:
        import os
        import json
        
        data = request.get_json()
        template_index = data.get('template_index')
        
        if template_index is None:
            return jsonify({'success': False, 'error': 'Template index is required'}), 400
        
        runtime_user_id = _template_runtime_user_id()
        templates = runtime_store.list_templates(runtime_user_id)
        
        if template_index < 0 or template_index >= len(templates):
            return jsonify({'success': False, 'error': 'Invalid template index'}), 400
        deleted_template = templates[template_index]['content']
        runtime_store.delete_template(runtime_user_id, deleted_template)
        
        logger.info(f"Template deleted: {deleted_template[:50]}...")
        return jsonify({'success': True, 'message': 'Template deleted successfully'})
        
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/api/templates/delete_multiple', methods=['POST'])
@jwt_required()
def delete_multiple_templates():
    """Delete multiple templates by indices (sorted descending to keep indices stable)"""
    try:
        import os, json
        data = request.get_json()
        indices = data.get('template_indices', [])
        if not indices:
            return jsonify({'success': False, 'error': 'No indices provided'}), 400

        runtime_user_id = _template_runtime_user_id()
        templates = runtime_store.list_templates(runtime_user_id)
        for i in sorted(set(indices), reverse=True):
            if 0 <= i < len(templates):
                runtime_store.delete_template(runtime_user_id, templates[i]['content'])

        return jsonify({'success': True, 'message': f'Deleted {len(indices)} template(s)'})
    except Exception as e:
        logger.error(f"Error deleting multiple templates: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/api/templates/metadata', methods=['POST'])
@jwt_required()
def update_template_metadata():
    try:
        data = request.get_json() or {}
        content = data.get('content')
        if not content:
            return jsonify({'success': False, 'error': 'Template content is required'}), 400
        runtime_store.update_template_meta(
            _template_runtime_user_id(),
            content,
            title=(data.get('title') or '').strip() or None,
            folder=(data.get('folder') or '').strip() or None,
            tags=data.get('tags', []),
            is_active=1 if data.get('is_active', True) else 0,
            weight=float(data.get('weight', 1.0) or 1.0),
        )
        return jsonify({'success': True, 'message': 'Template metadata updated'})
    except Exception as e:
        logger.error(f"Error updating template metadata: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/api/templates/generate')
@jwt_required()
def generate_template_message():
    """Generate a message from templates"""
    try:
        import os
        import json
        import random
        
        template_index = request.args.get('template_index', type=int)
        
        templates_file = 'templates_data/message_templates.json'
        templates = [row['content'] for row in runtime_store.list_templates(_template_runtime_user_id())]
        data = {}
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        variables = data.get('variables', {
            'name': ['Alex', 'Maria', 'John'],
            'product': ['amazing product', 'great service'],
            'benefit': ['save time', 'increase profit']
        })
        
        if not templates:
            return jsonify({'error': 'No templates available'}), 404
        
        # Select template
        if template_index is not None and 0 <= template_index < len(templates):
            template = templates[template_index]
            used_index = template_index
        else:
            used_index = random.randint(0, len(templates) - 1)
            template = templates[used_index]
        
        # Generate message with random variables
        message = template
        used_variables = {}
        
        import re
        for var_name, var_values in variables.items():
            patterns = [f'{{{{{var_name}}}}}', f'{{{var_name}}}']
            if any(pattern in message for pattern in patterns) and var_values:
                selected_value = random.choice(var_values)
                for pattern in patterns:
                    message = message.replace(pattern, selected_value)
                used_variables[var_name] = selected_value
        
        return jsonify({
            'message': message,
            'template_index': used_index,
            'variables_used': used_variables,
            'original_template': template
        })
        
    except Exception as e:
        logger.error(f"Error generating template message: {e}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/templates/preview')
@jwt_required()
def preview_templates():
    """Preview multiple templates"""
    try:
        import os
        import json
        import random
        
        count = request.args.get('count', default=5, type=int)
        count = min(count, 20)  # Limit to max 20 previews
        
        templates_file = 'templates_data/message_templates.json'
        templates = [row['content'] for row in runtime_store.list_templates(_template_runtime_user_id())]
        data = {}
        if os.path.exists(templates_file):
            with open(templates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        variables = data.get('variables', {
            'name': ['Alex', 'Maria', 'John'],
            'product': ['amazing product', 'great service'],
            'benefit': ['save time', 'increase profit']
        })
        
        if not templates:
            return jsonify({'previews': [], 'count': 0})
        
        previews = []
        
        # Generate previews
        for i in range(min(count, len(templates))):
            template = templates[i] if i < len(templates) else random.choice(templates)
            
            # Generate message with random variables
            message = template
            used_variables = {}
            
            for var_name, var_values in variables.items():
                patterns = [f'{{{{{var_name}}}}}', f'{{{var_name}}}']
                if any(pattern in message for pattern in patterns) and var_values:
                    selected_value = random.choice(var_values)
                    for pattern in patterns:
                        message = message.replace(pattern, selected_value)
                    used_variables[var_name] = selected_value
            
            previews.append({
                'template_index': i,
                'original_template': template,
                'generated_message': message,
                'variables_used': used_variables
            })
        
        return jsonify({
            'previews': previews,
            'count': len(previews),
            'total_templates': len(templates)
        })
        
    except Exception as e:
        logger.error(f"Error previewing templates: {e}")
        return jsonify({'error': str(e)}), 500

