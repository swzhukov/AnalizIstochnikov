"""packages/research/config.py — конфигурация и константы"""
import os

# Piped mirrors — ОБНОВЛЕНО 11.06.2026 после live-проверки из sandbox.
# Старые 4 mirror'а ВСЕ мертвы (kavin 526, adminforge пустой, whatever пустой, projectsegfau spam-block).
# Новый primary: api.piped.private.coffee (alive 11.06.2026, HTTP 200, 22 КБ).
# Fallback — dynamic fetch из piped-instances.kavin.rocks (community-maintained list).
PIPED_INSTANCES = [
    'https://api.piped.private.coffee',         # primary (verified 11.06.2026)
    'https://pipedapi.kavin.rocks',             # secondary (может подняться)
    'https://pipedapi.adminforge.de',           # tertiary
    'https://watchapi.whatever.social',         # quaternary
]
INVIDIOUS_INSTANCES = [
    'https://yewtu.be',                          # вторичный fallback
    'https://invidious.fdn.fr',                  # tertiary
    'https://invidious.protokolla.fi',           # последний resort (может быть captcha)
]

# Dynamic Piped instances list (community API, опционально fetch при старте)
PIPED_INSTANCES_API = 'https://piped-instances.kavin.rocks/'  # JSON list of alive instances

# YandexGPT конфиг
YANDEX_GPT_URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
YANDEX_GPT_DEFAULT_MODEL = 'yandexgpt-lite'
YANDEX_GPT_MAX_INPUT_CHARS = 24000

# Chunking — для длинных видео (v6.0.1 hotfix: иначе silent truncation)
CHUNK_SIZE_CHARS = 18000
CHUNK_OVERLAP_CHARS = 1000
CHUNK_TIMEOUT_S = 60

# Cost guard
COST_PER_1K_TOKENS_RUB = {
    'yandexgpt-lite': {'input': 0.20, 'output': 0.60},
    'yandexgpt':      {'input': 0.40, 'output': 1.20},
    'yandexgpt-pro':  {'input': 0.80, 'output': 2.40},
}

DAILY_BUDGET_RUB = float(os.environ.get('DAILY_BUDGET_RUB', '200'))

# Youtube Data API
YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3/videos'
