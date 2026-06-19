"""packages/research/utils.py — common utils (v6.0.5: +vtt_to_claims)"""
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


def vtt_to_claims(vtt):
    """Parse VTT -> [{ts_in_video: float, text: str}]. Dedupes 3x auto-transcript repeats."""
    out = []
    prev_text = None
    for block in re.split(r'\n\n+', vtt):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        if lines[0].startswith('WEBVTT') or lines[0].startswith('NOTE'):
            continue
        ts = 0.0
        text_lines = []
        for line in lines:
            if '-->' in line:
                m = re.match(r'(\d+):(\d{2}):(\d{2})[.,](\d+)', line)
                if m:
                    h, mi, s, ms = map(int, m.groups())
                    ts = h * 3600 + mi * 60 + s + ms / 1000
            elif re.match(r'^\d+$', line):
                continue
            else:
                clean = re.sub(r'<[^>]+>', '', line)
                if clean:
                    text_lines.append(clean)
        if not text_lines:
            continue
        text = ' '.join(text_lines).strip()
        if not text:
            continue
        # v6.0.8: strip overlap with previous (cumulative VTT cues)
        if prev_text:
            # find longest suffix of prev_text that is a prefix of text
            overlap = 0
            max_check = min(len(prev_text), len(text))
            for k in range(max_check, 4, -1):
                if prev_text.endswith(text[:k]):
                    overlap = k
                    break
            if overlap > 4:
                text = text[overlap:].strip()
        if not text or len(text) < 3:
            continue
        if prev_text and text == prev_text:
            continue
        if prev_text:
            prev_text = (prev_text + ' ' + text).strip()[-200:]
        else:
            prev_text = text
        out.append({'ts_in_video': ts, 'text': text})
    return out


def vtt_to_timeline(vtt, max_chars=12000):
    """VTT -> '[hh:mm:ss] text' lines for YandexGPT prompt. Dedupes, limits."""
    claims = vtt_to_claims(vtt)
    out = []
    total = 0
    for c in claims:
        if len(c['text']) < 4:
            continue
        h = int(c['ts_in_video'] // 3600)
        m = int((c['ts_in_video'] % 3600) // 60)
        s = int(c['ts_in_video'] % 60)
        line = f'[{h:02d}:{m:02d}:{s:02d}] {c["text"]}'
        if total + len(line) > max_chars:
            out.append('... (truncated)')
            break
        out.append(line)
        total += len(line)
    return '\n'.join(out)


def chunk_text(text, size=18000, overlap=1000):
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end >= len(text):
            chunks.append(text[start:])
            break
        boundary = max(text.rfind('. ', start, end),
                       text.rfind('.', start, end),
                       text.rfind('\n\n', start, end))
        if boundary > start + size // 2:
            end = boundary + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
    return chunks


def safe_get(url, timeout=20, headers=None):
    try:
        r = requests.get(url, timeout=timeout,
                         headers=headers or {'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        return r
    except Exception:
        return None
