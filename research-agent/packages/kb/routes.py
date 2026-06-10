"""packages/kb/routes.py — kb_save, kb_query, render_digest"""
import os
import re
import json
import time
import sqlite3
import logging
from datetime import datetime, timezone, timedelta

from flask import request, jsonify

from packages.kb.schema import KB_DB, init_kb

log = logging.getLogger('newton-api.kb.routes')

TMP_DIR = '/opt/beget/n8n/newton-tmp'


def _esc(s):
    if s is None:
        return ''
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
                  .replace('>', '&gt;').replace('"', '&quot;'))


def register(app):
    @app.route('/kb_save', methods=['POST'])
    def kb_save():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        kind = data.get('kind', 'youtube_video')
        if kind not in ('youtube_video', 'youtube_channel', 'telegram_channel'):
            return jsonify({'error': f'unsupported kind: {kind}'}), 400
        url = data.get('url', '').strip()
        title = data.get('title', '')
        external_id = data.get('external_id', '')
        if not url:
            return jsonify({'error': 'url required'}), 400
        try:
            con = sqlite3.connect(KB_DB)
            cur = con.cursor()
            cur.execute('''INSERT INTO sources (url, kind, external_id, title, added_at, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(url) DO UPDATE SET
                             last_seen = excluded.last_seen,
                             title = COALESCE(NULLIF(excluded.title, ''), sources.title)''',
                        (url, kind, external_id, title,
                         datetime.now(timezone.utc).isoformat(),
                         datetime.now(timezone.utc).isoformat()))
            cur.execute('SELECT id FROM sources WHERE url = ?', (url,))
            source_id = cur.fetchone()[0]
            claims_saved = 0
            for c in data.get('claims', []):
                try:
                    cur.execute('''INSERT OR IGNORE INTO claims
                                   (source_id, ts_in_video, text, lang, url, claim_type, created_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                (source_id, c.get('ts_in_video'), c.get('text', ''),
                                 c.get('lang', 'ru'), c.get('url', ''),
                                 c.get('claim_type', 'fact'),
                                 datetime.now(timezone.utc).isoformat()))
                    if cur.rowcount > 0:
                        claims_saved += 1
                except Exception as e:
                    log.warning('claim insert skipped: %s', e)
            con.commit()
            con.close()
            return jsonify({'source_id': source_id, 'claims_saved': claims_saved})
        except Exception as e:
            log.exception('kb_save failed')
            return jsonify({'error': str(e)}), 500

    @app.route('/kb_query', methods=['GET'])
    def kb_query():
        source_id = request.args.get('source_id')
        since = request.args.get('since')
        limit = int(request.args.get('limit', 50))
        try:
            con = sqlite3.connect(KB_DB)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            if source_id:
                cur.execute('''SELECT * FROM claims WHERE source_id = ?
                               AND (? IS NULL OR created_at >= ?)
                               ORDER BY created_at DESC LIMIT ?''',
                            (source_id, since, since, limit))
            else:
                cur.execute('''SELECT * FROM claims
                               WHERE (? IS NULL OR created_at >= ?)
                               ORDER BY created_at DESC LIMIT ?''',
                            (since, since, limit))
            rows = [dict(r) for r in cur.fetchall()]
            con.close()
            return jsonify({'claims': rows, 'count': len(rows)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/user_profile', methods=['GET', 'POST'])
    def user_profile():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        try:
            con = sqlite3.connect(KB_DB)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            if request.method == 'GET':
                cur.execute('SELECT key, value, updated_at FROM user_profile')
                rows = {r['key']: {'value': r['value'], 'updated_at': r['updated_at']} for r in cur.fetchall()}
                con.close()
                return jsonify({'profile': rows})
            # POST: merge
            data = request.json or {}
            for k, v in data.items():
                cur.execute('''INSERT INTO user_profile (key, value, updated_at)
                               VALUES (?, ?, ?)
                               ON CONFLICT(key) DO UPDATE SET
                                 value = excluded.value,
                                 updated_at = excluded.updated_at''',
                            (k, str(v), datetime.now(timezone.utc).isoformat()))
            con.commit()
            con.close()
            return jsonify({'status': 'ok', 'updated': list(data.keys())})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/render_digest', methods=['POST'])
    def render_digest():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        title = data.get('title', 'Дайджест')
        summary = data.get('summary', [])
        actions = data.get('actions', [])
        meta = data.get('meta', {})
        claims = data.get('claims', [])
        digest_id = data.get('digest_id', f'd_{int(time.time())}')
        html_path = os.path.join(TMP_DIR, f'digest_{digest_id}.html')
        html = _render_html(title, summary, actions, meta, claims)
        try:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            return jsonify({'file_path': html_path, 'size': len(html)})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


def _render_html(title, summary, actions, meta, claims):
    now_msk = (datetime.now(timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M MSK')
    summary_html = ''.join(f'<li>{_esc(s)}</li>' for s in summary) if summary else '<li><em>(пусто)</em></li>'
    actions_html = ''
    for a in (actions or []):
        if isinstance(a, str):
            text = a; subj = ''; trig = ''; conf = ''
        else:
            text = a.get('text', ''); subj = a.get('subject', '')
            trig = a.get('trigger', ''); conf = a.get('confidence', '')
        actions_html += f'<div class="action"><div class="at">{_esc(text)}</div>'
        if subj: actions_html += f'<div class="am">📌 {_esc(subj)}</div>'
        if trig: actions_html += f'<div class="am">⏰ {_esc(trig)}</div>'
        if conf != '' and conf is not None: actions_html += f'<div class="am">📊 уверенность: {conf}</div>'
        actions_html += '</div>'
    claims_html = ''
    for c in (claims or [])[:30]:
        text = c.get('text', '') if isinstance(c, dict) else str(c)
        ts = c.get('ts_in_video', '') if isinstance(c, dict) else ''
        claims_html += f'<div class="claim"><span class="ts">{_esc(str(ts))}s</span> {_esc(text)}</div>'
    meta_html = ''
    for k, v in (meta or {}).items():
        meta_html += f'<div class="meta-row"><b>{_esc(k)}:</b> {_esc(str(v)[:300])}</div>'
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{_esc(title)}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  max-width:780px;margin:30px auto;padding:0 20px;color:#222;line-height:1.55;background:#fafafa}}
h1{{color:#1a1a1a;border-bottom:2px solid #4a90e2;padding-bottom:8px}}
h2{{color:#4a90e2;margin-top:30px}}
.meta{{background:#fff;padding:12px 16px;border-radius:8px;border:1px solid #eee;margin:16px 0}}
.meta-row{{margin:4px 0;font-size:14px}}
.summary{{background:#fff;padding:16px 16px 16px 36px;border-radius:8px;border:1px solid #eee}}
.action{{background:#fff8e1;padding:12px 16px;border-radius:8px;margin:10px 0;border-left:4px solid #f5a623}}
.at{{font-weight:600;margin-bottom:4px}}
.am{{font-size:13px;color:#666;margin-top:2px}}
.claim{{background:#fff;padding:8px 12px;border-radius:6px;margin:6px 0;font-size:14px;border:1px solid #eee}}
.ts{{background:#4a90e2;color:#fff;padding:1px 6px;border-radius:3px;font-size:12px;margin-right:6px}}
.footer{{margin-top:30px;padding-top:12px;border-top:1px solid #ddd;font-size:12px;color:#999}}
</style></head><body>
<h1>{_esc(title)}</h1>
<div class="footer">Сгенерировано: {now_msk} · Research Agent v6.0.1</div>
<div class="meta">{meta_html}</div>
<h2>📋 Краткое содержание</h2>
<div class="summary"><ol>{summary_html}</ol></div>
<h2>🎯 Action items</h2>
{actions_html or '<p><em>Нет рекомендаций</em></p>'}
<h2>💬 Ключевые тезисы (до 30)</h2>
{claims_html or '<p><em>Нет данных</em></p>'}
</body></html>'''
