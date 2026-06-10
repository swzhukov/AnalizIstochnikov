"""packages/research/config.py — конфигурация и константы"""
import os

# Piped mirrors (4 основных) + Invidious fallback (3)
PIPED_INSTANCES = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.adminforge.de',
    'https://watchapi.whatever.social',
    'https://pipedapi.in.projectsegfau.lt',
]
INVIDIOUS_INSTANCES = [
    'https://yewtu.be',
    'https://invidious.fdn.fr',
    'https://invidious.protokolla.fi',
]

# YandexGPT конфиг
YANDEX_GPT_URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
YANDEX_GPT_DEFAULT_MODEL = 'yandexgpt-lite'
YANDEX_GPT_MAX_INPUT_CHARS = 24000  # лимит ~32k токенов, берём с запасом

# Chunking — для длинных видео (v6.0.1 hotfix: иначе silent truncation)
CHUNK_SIZE_CHARS = 18000      # ~6k токенов, помещается в yandexgpt-lite 8k context с запасом
CHUNK_OVERLAP_CHARS = 1000    # overlap чтобы не терять границы мыслей
CHUNK_TIMEOUT_S = 60

# Cost guard (YandexGPT-lite, ₽/1k токенов — ОБНОВЛЯТЬ при смене тарифа)
# Источник: https://yandex.cloud/ru/services/ai (YandexGPT Pricing). Заменить на реальные.
COST_PER_1K_TOKENS_RUB = {
    'yandexgpt-lite': {'input': 0.20, 'output': 0.60},  # оценка ±50% (LESSONS §4.5)
    'yandexgpt':      {'input': 0.40, 'output': 1.20},
    'yandexgpt-pro':  {'input': 0.80, 'output': 2.40},
}

# Daily budget cap (₽). 0 = unlimited. Рекомендую 200₽/день для 1 пользователя.
DAILY_BUDGET_RUB = float(os.environ.get('DAILY_BUDGET_RUB', '200'))


# Youtube Data API
YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3/videos'
