"""packages/research/routes.py — эндпоинты YouTube/Piped/YandexGPT.

v6.0.1 hotfix:
- /transcribe, /fetch, /download требуют X-Telegram-User-Id из ALLOWED_TELEGRAM_USERS
- chunking для длинных субтитров
- cost tracking в /health_full
- YandexGPT прокидывает truncated-флаг в KB
"""
import os
import re
import time
import json
import logging
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from flask import request, jsonify

from packages.research import config as cfg
from packages.research.utils import extract_video_id, vtt_to_text, chunk_text, safe_get

log = logging.getLogger('newton-api.research')

# Concurrency bound (v6.0.1 — действительно работает, в отличие от v6.0)
NEWTON_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix='newton')
NEWTON_INFLIGHT = 0
NEWTON_LOCK = threading.Lock()
YAGPT_TODAY_RUB = 0.0
YAGPT_TODAY_DATE = None  # для сброса в полночь MSK
COST_LOCK = threading.Lock()


def track_inflight(delta):
    global NEWTON_INFLIGHT
    with NEWTON_LOCK:
        NEWTON_INFLIGHT = max(0, NEWTON_INFLIGHT + delta)


def track_cost(rub):
    """YandexGPT cost tracking. Сбрасывается в 00:00 MSK."""
    global YAGPT_TODAY_RUB, YAGPT_TODAY_DATE
    today = (datetime.now(timezone.utc) + timedelta(hours=3)).date().isoformat()
    with COST_LOCK:
        if YAGPT_TODAY_DATE != today:
            YAGPT_TODAY_RUB = 0.0
            YAGPT_TODAY_DATE = today
        YAGPT_TODAY_RUB += rub


def get_today_cost():
    with COST_LOCK:
        return round(YAGPT_TODAY_RUB, 2)


def budget_exceeded():
    return cfg.DAILY_BUDGET_RUB > 0 and get_today_cost() >= cfg.DAILY_BUDGET_RUB


# ============================================================
# NEWTON CLI wrapper
# ============================================================
def run_newton(args, timeout=300):
    env = os.environ.copy()
    env['NEWTON_TOKEN'] = os.environ.get('NEWTON_TOKEN', '')
    import subprocess
    return subprocess.run(args, env=env, capture_output=True, text=True,
                          timeout=timeout, stdin=subprocess.DEVNULL)


# ============================================================
# ROUTES
# ============================================================
def register(app):
    @app.route('/transcribe', methods=['POST'])
    def transcribe():
        # v6.0.1: auth gate
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        file_path = data.get('file')
        engine = data.get('engine', 'v3')
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'File not found', 'path': file_path}), 400
        # v6.0.1: concurrency bound ДЕЙСТВИТЕЛЬНО работает
        with NEWTON_LOCK:
            if NEWTON_INFLIGHT >= 1:
                return jsonify({'error': 'transcribe busy', 'hint': '1 newton session at a time'}), 503
            nonlocal_marker = True
        track_inflight(+1)
        out_path = f"/opt/beget/n8n/newton-tmp/out_{os.getpid()}_{int(time.time())}.txt"
        cmd = ['newton', 'transcribe', file_path, '-e', engine, '-o', out_path]
        try:
            res = run_newton(cmd)
        except Exception as e:
            track_inflight(-1)
            return jsonify({'error': str(e)}), 500
        track_inflight(-1)
        if res.returncode != 0:
            return jsonify({'error': res.stderr or 'Newton CLI failed', 'engine': engine}), 500
        try:
            with open(out_path, encoding='utf-8') as f:
                text = f.read()
            os.remove(out_path)
            return jsonify({'text': text})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/fetch', methods=['POST'])
    def fetch_youtube():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        url = (request.json or {}).get('url')
        if not url:
            return jsonify({'error': 'URL required'}), 400
        out_path = f"/opt/beget/n8n/newton-tmp/yt_{os.getpid()}_{int(time.time())}.mp3"
        cmd = ['newton', 'fetch', url, '-o', out_path, '--wait']
        res = run_newton(cmd, timeout=300)
        if res.returncode != 0:
            return jsonify({
                'error': res.stderr,
                'note': 'googlevideo=000 — НЕ работает для YouTube. Используйте /youtube_subs',
            }), 500
        return jsonify({'file_path': out_path})

    @app.route('/download', methods=['POST'])
    def download_url():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        url = (request.json or {}).get('url')
        if not url:
            return jsonify({'error': 'URL required'}), 400
        out_path = f"/opt/beget/n8n/newton-tmp/url_{os.getpid()}_{int(time.time())}.bin"
        try:
            r = requests.get(url, timeout=120, stream=True)
            r.raise_for_status()
            with open(out_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return jsonify({'file_path': out_path})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/telegram_download', methods=['POST'])
    def telegram_download():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        file_id = (request.json or {}).get('file_id')
        if not file_id:
            return jsonify({'error': 'file_id required'}), 400
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            return jsonify({'error': 'TELEGRAM_BOT_TOKEN not set'}), 500
        try:
            info = requests.get(f'https://api.telegram.org/bot{bot_token}/getFile',
                                params={'file_id': file_id}, timeout=30).json()
            if not info.get('ok'):
                return jsonify({'error': f"Telegram API error: {info.get('description')}"}), 400
            remote = info['result']['file_path']
            ext = os.path.splitext(remote)[1] or '.bin'
            out_path = f"/opt/beget/n8n/newton-tmp/tg_{os.getpid()}_{int(time.time())}{ext}"
            file_url = f'https://api.telegram.org/file/bot{bot_token}/{remote}'
            r = requests.get(file_url, timeout=120, stream=True)
            r.raise_for_status()
            with open(out_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return jsonify({'file_path': out_path, 'size': os.path.getsize(out_path)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/upload', methods=['POST'])
    def upload_file():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        filename = request.args.get('filename', f'upload_{int(time.time())}.bin')
        ext = request.args.get('ext', '')
        if ext and not filename.endswith(ext):
            filename = f"{os.path.splitext(filename)[0]}.{ext}"
        file_path = os.path.join('/opt/beget/n8n/newton-tmp', filename)
        try:
            with open(file_path, 'wb') as f:
                f.write(request.data)
            return jsonify({'file_path': file_path, 'size': len(request.data)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/save_text', methods=['POST'])
    def save_text():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        text = data.get('text', '')
        filename = data.get('filename', f'out_{int(time.time())}.txt')
        file_path = os.path.join('/opt/beget/n8n/newton-tmp', filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(text)
            return jsonify({'file_path': file_path, 'size': len(text)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/send_document', methods=['POST'])
    def send_document():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        file_path = data.get('file_path')
        chat_id = data.get('chat_id')
        message_id = data.get('message_id')
        caption = data.get('caption', '✅ Готово')
        if not file_path or not os.path.exists(file_path):
            return jsonify({'error': 'File not found', 'path': file_path}), 400
        if not chat_id:
            return jsonify({'error': 'chat_id required'}), 400
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            return jsonify({'error': 'TELEGRAM_BOT_TOKEN not set'}), 500
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                payload = {'chat_id': chat_id, 'caption': caption}
                if message_id:
                    payload['reply_to_message_id'] = message_id
                r = requests.post(f'https://api.telegram.org/bot{bot_token}/sendDocument',
                                  files=files, data=payload, timeout=30)
                result = r.json()
                if not result.get('ok'):
                    return jsonify({'error': f"Telegram API error: {result.get('description')}",
                                    'details': result}), 400
                return jsonify({'status': 'sent',
                                'message_id': result.get('result', {}).get('message_id')})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ============================================================
    # /youtube_meta — YouTube Data API v3
    # ============================================================
    @app.route('/youtube_meta', methods=['POST'])
    def youtube_meta():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        video_id = data.get('video_id') or extract_video_id(data.get('url', ''))
        if not video_id:
            return jsonify({'error': 'video_id or url required'}), 400
        api_key = os.environ.get('YOUTUBE_API_KEY', '')
        if not api_key:
            return jsonify({'error': 'YOUTUBE_API_KEY not set'}), 500
        try:
            r = requests.get(cfg.YOUTUBE_API_URL,
                             params={'key': api_key, 'part': 'snippet,contentDetails,statistics',
                                     'id': video_id}, timeout=15)
            r.raise_for_status()
            j = r.json()
            if not j.get('items'):
                return jsonify({'error': 'video not found', 'video_id': video_id}), 404
            item = j['items'][0]
            sn = item['snippet']
            dur_iso = item['contentDetails'].get('duration', 'PT0S')
            m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur_iso)
            h = int(m.group(1) or 0) if m else 0
            mi = int(m.group(2) or 0) if m else 0
            s = int(m.group(3) or 0) if m else 0
            return jsonify({
                'video_id': video_id,
                'title': sn.get('title', ''),
                'channel': sn.get('channelTitle', ''),
                'channel_id': sn.get('channelId', ''),
                'published': sn.get('publishedAt', '')[:10],
                'description': sn.get('description', ''),
                'tags': sn.get('tags', []),
                'duration_sec': h * 3600 + mi * 60 + s,
                'views': int(item.get('statistics', {}).get('viewCount', 0)),
                'likes': int(item.get('statistics', {}).get('likeCount', 0)),
                'thumb': sn.get('thumbnails', {}).get('high', {}).get('url', ''),
                'url': f'https://youtu.be/{video_id}',
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # ============================================================
    # /youtube_subs — Piped primary + Invidious fallback + backoff
    # v6.0.1: возврат text + truncation flag
    # ============================================================
    @app.route('/youtube_subs', methods=['POST'])
    def youtube_subs():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        video_id = data.get('video_id') or extract_video_id(data.get('url', ''))
        prefer_lang = (data.get('lang') or 'ru').lower()
        if not video_id:
            return jsonify({'error': 'video_id or url required'}), 400

        # v6.0.3: только yt-dlp (Piped/Invidious мертвы с 12.06.2026)
        try:
            import subprocess
            _proc = subprocess.run(
                ['yt-dlp', '--skip-download', '--dump-single-json',
                 '--no-warnings', '--no-progress',
                 '-o', '/dev/null', f'https://youtu.be/{video_id}'],
                capture_output=True, text=True, timeout=20
            )
            if _proc.returncode != 0 or not _proc.stdout.strip():
                return jsonify({
                    'error': 'yt-dlp failed',
                    'stderr': _proc.stderr[:300],
                    'hint': 'video unavailable or yt-dlp broken',
                }), 500
            _meta = json.loads(_proc.stdout)
            _sub_url = None
            _sub = (_meta.get('requested_subtitles') or {}).get(prefer_lang)
            if _sub and _sub.get('url'):
                _sub_url = _sub['url']
            else:
                for _cand in _meta.get('automatic_captions', {}).get(prefer_lang, []):
                    if _cand.get('url') and _cand.get('ext') == 'vtt':
                        _sub_url = _cand['url']; break
            if not _sub_url:
                return jsonify({
                    'error': 'no_subs',
                    'hint': f'no {prefer_lang} subtitles available',
                }), 404
            _sub_r = requests.get(_sub_url, timeout=20,
                                   headers={'User-Agent': 'Mozilla/5.0'})
            _sub_r.raise_for_status()
            raw = _sub_r.text
            text = vtt_to_text(raw)
            return jsonify({
                'video_id': video_id,
                'source': 'yt-dlp',
                'lang': prefer_lang,
                'auto_generated': True,
                'text': text,
                'truncated': False,
                'char_count': len(text),
                'meta': {
                    'title': _meta.get('title', ''),
                    'uploader': _meta.get('uploader') or _meta.get('channel', ''),
                    'duration': _meta.get('duration', 0),
                    'uploadDate': _meta.get('upload_date', ''),
                    'description': (_meta.get('description') or '')[:2000],
                }
            })
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'yt-dlp_timeout', 'hint': 'yt-dlp took >20s'}), 504
        except Exception as _e:
            return jsonify({'error': 'yt-dlp_error', 'msg': f'{type(_e).__name__}: {_e}'}), 500


    # ============================================================
    # /yagpt_summarize — v6.0.1: chunking + cost tracking + structured errors
    # ============================================================
    @app.route('/yagpt_summarize', methods=['POST'])
    def yagpt_summarize():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        # budget check
        if budget_exceeded():
            return jsonify({
                'error': 'daily_budget_exceeded',
                'spent_rub': get_today_cost(),
                'cap_rub': cfg.DAILY_BUDGET_RUB,
                'hint': 'wait until 00:00 MSK or raise DAILY_BUDGET_RUB',
            }), 429
        data = request.json or {}
        text = data.get('text', '')
        system = data.get('system', '')
        model = data.get('model', cfg.YANDEX_GPT_DEFAULT_MODEL)
        max_tokens = int(data.get('max_tokens', 2000))
        temperature = float(data.get('temperature', 0.3))
        if not text:
            return jsonify({'error': 'text required'}), 400
        api_key = os.environ.get('YANDEX_GPT_API_KEY', '')
        folder_id = os.environ.get('YANDEX_GPT_FOLDER_ID', '')
        if not api_key or not folder_id:
            return jsonify({'error': 'YANDEX_GPT_API_KEY or YANDEX_GPT_FOLDER_ID not set'}), 500
        if not system:
            system = ('Ты — персональный аналитик инвестора. Тебе дают транскрипт видео на русском. '
                      'Сделай: 1) summary 5 буллетов, 2) 3 action items. '
                      'Вывод строго в JSON: {"summary": [...], "actions": [{"text", "subject", "trigger", "confidence"}]}.')
        # v6.0.1: chunking — для длинных видео разбиваем и summarize по частям
        chunks = chunk_text(text, size=cfg.CHUNK_SIZE_CHARS, overlap=cfg.CHUNK_OVERLAP_CHARS)
        truncated = len(text) > cfg.YANDEX_GPT_MAX_INPUT_CHARS
        if truncated and len(chunks) == 1:
            chunks = chunk_text(text, size=cfg.CHUNK_SIZE_CHARS, overlap=cfg.CHUNK_OVERLAP_CHARS)
        if len(chunks) > 1:
            log.info('yagpt: chunking %d chars into %d chunks', len(text), len(chunks))
            # Per-chunk summary
            chunk_summaries = []
            total_in = 0
            total_out = 0
            for i, ch in enumerate(chunks):
                res = _yagpt_call(api_key, folder_id, model, system, ch,
                                  max_tokens=min(800, max_tokens), temperature=temperature)
                if not res['ok']:
                    return jsonify({
                        'error': 'yagpt chunk failed',
                        'chunk_index': i,
                        'chunks_total': len(chunks),
                        'details': res,
                    }), 502
                chunk_summaries.append(res['text'])
                total_in += res['usage_in']
                total_out += res['usage_out']
            # Meta-summarize: объединяем summary чанков
            meta_text = '\n\n'.join(f'[Часть {i+1}/{len(chunks)}]\n{s}'
                                     for i, s in enumerate(chunk_summaries))
            meta_res = _yagpt_call(api_key, folder_id, model,
                                    'Сделай ОБЩИЙ summary из нескольких частей одного видео. '
                                    'Объедини в 5 буллетов и 3 action items. '
                                    'Верни JSON: {"summary":[...], "actions":[...]}',
                                    meta_text, max_tokens=max_tokens, temperature=temperature)
            if not meta_res['ok']:
                return jsonify({
                    'error': 'yagpt meta-summarize failed',
                    'details': meta_res,
                }), 502
            total_in += meta_res['usage_in']
            total_out += meta_res['usage_out']
            # cost
            cost_in = total_in / 1000 * cfg.COST_PER_1K_TOKENS_RUB.get(model, {}).get('input', 0.4)
            cost_out = total_out / 1000 * cfg.COST_PER_1K_TOKENS_RUB.get(model, {}).get('output', 1.2)
            total_cost = cost_in + cost_out
            track_cost(total_cost)
            return jsonify({
                'raw': meta_res['text'],
                'parsed': _parse_json_safe(meta_res['text']),
                'usage': {'input_tokens': total_in, 'output_tokens': total_out, 'rub': round(total_cost, 4)},
                'chunks': len(chunks),
                'truncated': truncated,
                'budget_spent_today_rub': get_today_cost(),
            })
        # single chunk
        res = _yagpt_call(api_key, folder_id, model, system, text,
                          max_tokens=max_tokens, temperature=temperature)
        if not res['ok']:
            return jsonify({'error': 'yagpt http error', 'details': res}), 502
        cost_in = res['usage_in'] / 1000 * cfg.COST_PER_1K_TOKENS_RUB.get(model, {}).get('input', 0.4)
        cost_out = res['usage_out'] / 1000 * cfg.COST_PER_1K_TOKENS_RUB.get(model, {}).get('output', 1.2)
        track_cost(cost_in + cost_out)
        return jsonify({
            'raw': res['text'],
            'parsed': _parse_json_safe(res['text']),
            'usage': {'input_tokens': res['usage_in'], 'output_tokens': res['usage_out'],
                       'rub': round(cost_in + cost_out, 4)},
            'chunks': 1,
            'truncated': False,
            'budget_spent_today_rub': get_today_cost(),
        })


def _yagpt_call(api_key, folder_id, model, system, user_text, max_tokens, temperature):
    body = {
        'modelUri': f'gpt://{folder_id}/{model}',
        'completionOptions': {'stream': False, 'temperature': temperature,
                              'maxTokens': str(max_tokens)},
        'messages': [{'role': 'system', 'text': system}, {'role': 'user', 'text': user_text}],
    }
    try:
        r = requests.post(cfg.YANDEX_GPT_URL,
                          headers={'Authorization': f'Bearer {api_key}',
                                   'x-folder-id': folder_id, 'Content-Type': 'application/json'},
                          json=body, timeout=cfg.CHUNK_TIMEOUT_S)
        if r.status_code != 200:
            return {'ok': False, 'status': r.status_code, 'body': r.text[:500]}
        j = r.json()
        text = j['result']['alternatives'][0]['message']['text']
        usage = j['result'].get('usage', {})
        return {'ok': True, 'text': text,
                'usage_in': int(usage.get('inputTextTokens', 0)),
                'usage_out': int(usage.get('completionTokens', 0))}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _parse_json_safe(s):
    """Попробовать распарсить JSON из ответа LLM, обрезав лишнее"""
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r'\{[\s\S]*\}', s)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
