#!/usr/bin/env python3
import os
import subprocess
import time
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
TOKEN = os.environ.get('NEWTON_TOKEN', '')
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TMP_DIR = '/opt/beget/n8n/newton-tmp'

def run_newton(args, timeout=300):
    env = os.environ.copy()
    env['NEWTON_TOKEN'] = TOKEN
    return subprocess.run(
        args,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        stdin=subprocess.DEVNULL
    )

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'service': 'newton-api',
        'version': '5.4',
        'endpoints': ['/transcribe', '/fetch', '/download', '/telegram_download', '/upload', '/save_text', '/send_document']
    })





# ===== KAPITAL ENDPOINTS (auto-patched v2) =====
import sys
sys.path.insert(0, '/opt/beget/kapital')
try:
    from deploy.add_kapital_endpoints import register_kapital_endpoints
    register_kapital_endpoints(app)
    print("[KAPITAL] endpoints registered OK", flush=True)
except Exception as e:
    print(f"[KAPITAL] FAILED to register endpoints: {e}", flush=True)
    import traceback
    traceback.print_exc()
# ===== END KAPITAL =====


# ===== RESEARCH-AGENT v6.0.1 (auto-patched 11.06.2026) =====
import sys
RESEARCH_AGENT_DIR = '/opt/beget/n8n/research-agent'
if RESEARCH_AGENT_DIR not in sys.path:
    sys.path.insert(0, RESEARCH_AGENT_DIR)
try:
    import core.app as _core_app
    for pkg in ('research', 'telegram_bot', 'kb'):
        try:
            mod = __import__(f'packages.{pkg}.routes', fromlist=['register'])
            mod.register(app)
            print(f"[{pkg}] endpoints registered OK", flush=True)
        except Exception as pkg_e:
            print(f"[{pkg}] FAILED: {pkg_e}", flush=True)
            import traceback as _tb
            _tb.print_exc()
except Exception as _e:
    print(f"[RESEARCH-AGENT] FAILED: {_e}", flush=True)
    import traceback as _tb
    _tb.print_exc()
# ===== END RESEARCH-AGENT =====

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
