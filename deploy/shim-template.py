#!/usr/bin/env python3
"""
SHIM TEMPLATE для merge-approach: добавление endpoints к существующему Flask-приложению.

Использование:
1. Скопируй этот файл в /opt/beget/<project>/deploy/add_<project>_endpoints.py
2. Реализуй свои endpoints внутри register_<project>_endpoints(app)
3. В основном newton-api.py (или app.py) добавь блок:

    import sys
    sys.path.insert(0, '/opt/beget/<project>')
    try:
        from deploy.add_<project>_endpoints import register_<project>_endpoints
        register_<project>_endpoints(app)
        print(f"[<PROJECT>] endpoints registered OK", flush=True)
    except Exception as e:
        print(f"[<PROJECT>] FAILED: {e}", flush=True)
        import traceback
        traceback.print_exc()

Зачем merge, а не replace:
- На Beget VPS разные проекты могут шарить один Flask process
- Replace ломает другие endpoints (kapital, research, и т.д.)
- Merge добавляет endpoints без удаления существующих

⚠️ Конфликты routes:
- Если у двух проектов одинаковый endpoint (например /health), последний загруженный ПЕРЕЗАПИШЕТ
- Решение: используй уникальные prefix'ы: /kapital/*, /research/*, /<project>/*

⚠️ Lazy import:
- Если модуль не установлен, endpoint вернёт 503 (не 500)
- Это даёт стабильность — новый проект не ломает существующие
"""
from flask import jsonify, request
import logging
import os

logger = logging.getLogger('<project>_api')

# Lazy import: если <project> не установлен, endpoint вернёт 503
try:
    from <project>.<module> import <func1>, <func2>
    PROJECT_AVAILABLE = True
except ImportError as e:
    PROJECT_AVAILABLE = False
    IMPORT_ERROR = str(e)


def register_<project>_endpoints(app):
    """Регистрирует все /<project>/* endpoints в существующем Flask app."""

    @app.route('/<project>/health', methods=['GET'])
    def <project>_health():
        """Health check endpoint."""
        return jsonify({
            'status': 'ok' if PROJECT_AVAILABLE else 'unavailable',
            'service': '<project>-api',
            'version': '1.0.0',
            '<project>_available': PROJECT_AVAILABLE,
            'import_error': IMPORT_ERROR if not PROJECT_AVAILABLE else None,
            'endpoints': [
                '/<project>/health',
                '/<project>/<endpoint1>',
                '/<project>/<endpoint2>',
            ]
        })

    @app.route('/<project>/<endpoint>', methods=['POST'])
    def <project>_<endpoint>():
        """Generic endpoint handler."""
        body = request.get_json(silent=True) or {}
        user_id = str(body.get('user_id', '')).strip()
        if not user_id:
            return jsonify({'ok': False, 'error': 'user_id обязателен'}), 400
        try:
            from <project>.<module> import <func>
            result = <func>(user_id, ...)
            return jsonify({'ok': True, **result})
        except Exception as e:
            logger.exception(f'<project>.<endpoint> failed: {e}')
            return jsonify({'ok': False, 'error': str(e)}), 500

    logger.info(f'<Project> v1.0 endpoints зарегистрированы. PROJECT_AVAILABLE={PROJECT_AVAILABLE}')
    return app
