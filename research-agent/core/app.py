"""
core/app.py — каркас Flask-приложения, v6.0.1 hotfix
Только конфиг, health, error handlers. Эндпоинты — из пакетов.
"""
import os
import sys
import logging
import traceback
import time
from datetime import datetime, timezone

from flask import Flask, request, jsonify

# ============================================================
# LOGGING (структурированный, чтобы видеть последнюю ошибку)
# ============================================================
logging.basicConfig(
    filename='/opt/beget/n8n/api.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
log = logging.getLogger('newton-api')

LAST_ERROR = {'ts': None, 'endpoint': None, 'msg': None, 'traceback': None}


def record_error(endpoint, msg, tb=None):
    LAST_ERROR['ts'] = datetime.now(timezone.utc).isoformat()
    LAST_ERROR['endpoint'] = endpoint
    LAST_ERROR['msg'] = str(msg)[:500]
    LAST_ERROR['traceback'] = (tb or '')[:2000]


# ============================================================
# FLASK APP
# ============================================================
def create_app():
    app = Flask(__name__)
    app.config['JSON_SORT_KEYS'] = False
    app.config['START_TS'] = time.time()
    return app


app = create_app()


# ============================================================
# AUTH: ALLOWED_TELEGRAM_USERS (v6.0.1 hotfix — критично!)
# ============================================================
def get_allowed_users():
    """Читает ALLOWED_TELEGRAM_USERS из env. CSV. Если пусто — закрыть доступ к опасным."""
    raw = os.environ.get('ALLOWED_TELEGRAM_USERS', '').strip()
    if not raw:
        return set()  # пусто = никому нельзя
    return {int(x.strip()) for x in raw.split(',') if x.strip().isdigit()}


def is_authorized():
    """Проверка для запросов из n8n (X-Telegram-User-Id header)"""
    expected = get_allowed_users()
    if not expected:
        return False  # нет allow-list = закрыто
    provided = request.headers.get('X-Telegram-User-Id', '') or request.args.get('user_id', '')
    try:
        return int(provided) in expected
    except (ValueError, TypeError):
        return False


def unauthorized_response():
    log.warning('AUTH FAIL: user=%s endpoint=%s ip=%s',
                request.headers.get('X-Telegram-User-Id'),
                request.path, request.remote_addr)
    return jsonify({'error': 'unauthorized',
                    'hint': 'add your Telegram user_id to ALLOWED_TELEGRAM_USERS in .env'}), 403


# ============================================================
# HEALTH (v6.0.1 — расширенный)
# ============================================================
@app.route('/')
def index():
    return jsonify({
        'status': 'ok', 'service': 'newton-api', 'version': '6.0.1',
        'endpoints': 'see KB v6.1.1 §2.1',
    })


@app.route('/health_full')
def health_full():
    import shutil
    try:
        du = shutil.disk_usage('/opt/beget/n8n')
        disk_pct = round(100 * du.used / du.total, 1)
    except Exception:
        disk_pct = -1
    try:
        with open('/proc/loadavg') as f:
            load1 = float(f.read().split()[0])
    except Exception:
        load1 = -1
    try:
        with open('/proc/meminfo') as f:
            mem = f.read()
        mem_total = int(__import__('re').search(r'MemTotal:\s+(\d+)', mem).group(1))
        mem_avail = int(__import__('re').search(r'MemAvailable:\s+(\d+)', mem).group(1))
        ram_pct = round(100 * (1 - mem_avail / mem_total), 1)
    except Exception:
        ram_pct = -1

    uptime = time.time() - app.config['START_TS']
    return jsonify({
        'status': 'ok', 'version': '6.0.1',
        'ram_pct': ram_pct,
        'disk_pct': disk_pct,
        'load_1m': load1,
        'uptime_sec': round(uptime, 1),
        'auth_enabled': bool(get_allowed_users()),
        'last_error': LAST_ERROR,
        'ts': datetime.now(timezone.utc).isoformat(),
    })


# ============================================================
# GLOBAL ERROR HANDLERS
# ============================================================
@app.errorhandler(Exception)
def handle_unhandled(e):
    record_error(request.path, e, traceback.format_exc())
    log.exception('UNHANDLED in %s', request.path)
    return jsonify({'error': 'internal server error',
                    'type': type(e).__name__,
                    'msg': str(e)[:300]}), 500


# ============================================================
# PACKAGE LOADER (LESSONS §2.9: external package pattern)
# ============================================================
def load_packages(app):
    """Регистрирует эндпоинты из пакетов. Каждый пакет имеет routes.register(app)"""
    PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if PARENT not in sys.path:
        sys.path.insert(0, PARENT)
    for pkg in ('research', 'telegram_bot', 'kb'):
        try:
            mod = __import__(f'packages.{pkg}.routes', fromlist=['register'])
            mod.register(app)
            log.info('[%s] endpoints registered OK', pkg)
        except Exception as e:
            log.error('[%s] FAILED to register: %s', pkg, e)
            log.error(traceback.format_exc())
            print(f'[{pkg}] FAILED: {e}', file=sys.stderr, flush=True)
            print(traceback.format_exc(), file=sys.stderr, flush=True)
            sys.exit(1)  # LESSONS §2.9: не стартовать молча


load_packages(app)


if __name__ == '__main__':
    log.info('starting newton-api v6.0.1 (modular)')
    app.run(host='0.0.0.0', port=8080)
