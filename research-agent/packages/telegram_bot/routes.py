"""packages/telegram_bot/routes.py — /send_message (text Telegram reply)"""
import os
import requests
import logging
from flask import request, jsonify

log = logging.getLogger('newton-api.telegram')


def register(app):
    @app.route('/send_message', methods=['POST'])
    def send_message():
        from core.app import is_authorized, unauthorized_response
        if not is_authorized():
            return unauthorized_response()
        data = request.json or {}
        chat_id = data.get('chat_id')
        text = data.get('text', '')
        message_id = data.get('message_id')
        parse_mode = data.get('parse_mode', 'HTML')
        if not chat_id or not text:
            return jsonify({'error': 'chat_id and text required'}), 400
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        if not bot_token:
            return jsonify({'error': 'TELEGRAM_BOT_TOKEN not set'}), 500
        try:
            payload = {'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode,
                       'disable_web_page_preview': True}
            if message_id:
                payload['reply_to_message_id'] = message_id
            r = requests.post(f'https://api.telegram.org/bot{bot_token}/sendMessage',
                              json=payload, timeout=15)
            j = r.json()
            if not j.get('ok'):
                return jsonify({'error': f"Telegram API error: {j.get('description')}"}), 400
            return jsonify({'status': 'sent', 'message_id': j['result']['message_id']})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
