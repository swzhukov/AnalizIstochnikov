"""packages/research/utils.py — общие утилиты"""
import re
import time
import requests

VIDEO_ID_RE = re.compile(r'(?:v=|youtu\.be/|/shorts/|embed/)([0-9A-Za-z_-]{11})')


def extract_video_id(url):
    if not url:
        return None
    m = VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def vtt_to_text(vtt):
    """Удаляем заголовки WEBVTT, таймкоды и пустые строки, склеиваем в plain text.
    НЕ СОДЕРЖИТ timestamps — для рендера HTML они не нужны.
    """
    out = []
    for line in vtt.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('WEBVTT') or line.startswith('NOTE'):
            continue
        if '-->' in line:
            continue
        if re.match(r'^\d+$', line):
            continue
        line = re.sub(r'<[^>]+>', '', line)
        out.append(line)
    return '\n'.join(out)


def chunk_text(text, size=18000, overlap=1000):
    """Разбить текст на чанки с overlap. Возвращает list[str].
    Используется для длинных видео, чтобы yandexgpt-lite не silent-truncate."""
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            chunks.append(text[start:])
            break
        # пытаемся разбить по предложению/абзацу, не посередине слова
        boundary = max(text.rfind('. ', start, end),
                       text.rfind('。', start, end),
                       text.rfind('\n\n', start, end))
        if boundary > start + size // 2:
            end = boundary + 1
        chunks.append(text[start:end].strip())
        start = end - overlap  # overlap для связности
    return chunks


def safe_get(url, timeout=20, headers=None):
    """GET с обработкой ошибок. Возвращает requests.Response или None."""
    try:
        r = requests.get(url, timeout=timeout,
                         headers=headers or {'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        return r
    except Exception:
        return None
