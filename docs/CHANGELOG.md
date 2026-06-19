

## v6.0.7 (2026-06-19) — Sprint 8: prompt + claims + rendering fix

### 🎯 PM feedback
PM прислал реальный дайджест через @ZhukovsFirstBot и нашёл 2 бага:
1. Action items с фейковым профилем ("долгосрочный портфельный инвестор" — placeholder, не реальный PM)
2. "Ключевые тезисы" — мусор из 30 строк "Коллеги, всем добрый день" повторённых 3 раза, без таймкодов

### ✨ Что изменилось

**`packages/research/utils.py`:**
- +`vtt_to_claims(vtt)` — парсит VTT → `[{ts_in_video, text}]`, dedup identical
- +`vtt_to_timeline(vtt)` — формат `[hh:mm:ss] text` для YandexGPT input
- +v6.0.8 cumulative overlap strip (sliding window 200 chars)

**`packages/research/routes.py`:**
- `/youtube_subs` возвращает `claims` (массив) + `timeline` (строка) — раньше только `text`
- `/yagpt_summarize` принимает `user_profile` и вызывает server-side `_build_investor_prompt()`
- +`_build_investor_prompt(profile)` — жёсткий prompt с ПРОФИЛЕМ PM (watchlist, ОФЗ, ИИС, налоги)
  - Confidence 0.8-1.0 для инвестиционных видео
  - Confidence 0.4-0.6 для непрофильных (но actions всё равно привязаны к watchlist)

**`packages/kb/routes.py`:**
- `_render_html` v6.0.7: smart claims merge
  - merge consecutive cues within 3 sec gap
  - filter `len(text) >= 40` chars (real phrases, not fragments)
  - dedupe by normalized text
  - format ts as `mm:ss` или `hh:mm:ss`
  - top 30 by ts order
- Version: `Research Agent v6.0.7` (footer)

### 📊 Метрики (Sprint 8 test, то же видео https://youtu.be/6Z_hHWStwxw)
- /youtube_subs: 641 unique claims (из 1272 cues), timeline 12K chars
- /yagpt_summarize: 4181 input + 447 output tokens, 1.05₽
- /render_digest: 30 осмысленных claims с таймкодами (vs 30 строк мусора в v6.0.1)
- HTML size: 21KB (vs 8.7KB в v6.0.1 — больше данных, меньше мусора)

### 🎯 Качество дайджеста (Sprint 8)
- ✅ Action items про watchlist PM (OFZ-26248, OFZ-26238, PIK, LSR, X5, MGN)
- ✅ Confidence корректный (0.6 для неинвестиционного видео)
- ✅ Relevance объясняет, почему это важно для PM
- ✅ Ключевые тезисы с таймкодами mm:ss (навигация по видео)
- ✅ Summary 5 буллетов, по существу видео

### 📚 Lessons (MISTAKES §3.30-3.33)
- **§3.30** Hardcoded user_profile в n8n Code-ноде → server-side builder в Flask
- **§3.31** VTT auto-transcript cumulative cues → strip overlap (sliding window 200 chars)
- **§3.32** NoneType guard при `prev_text + ' ' + text`
- **§3.33** `FLASK_DEBUG=0` всё равно кэширует модули — `rm -rf __pycache__` обязателен

### 🔄 Migration
- Никаких breaking changes. n8n workflow `FRsjN6Ab1FBGAMoM` остаётся активным.
- Code — Build YandexGPT payload теперь передаёт `user_profile: {...}` в `/yagpt_summarize`.
# Changelog

## v6.0.1 (2026-06-10) — hotfix после council v2

### 🚨 Критично (security & correctness)
- **Auth gate** на всех опасных эндпоинтах через `ALLOWED_TELEGRAM_USERS`
  - Без токена — 403
  - Без этого любой Telegram-юзер мог дёрнуть `/transcribe` и сжечь всю RAM
- **Chunking в `/yagpt_summarize`**
  - YandexGPT-lite 8k context **тихо обрезал** длинные видео и выдавал summary **середины**
  - Теперь: разбивка на чанки 18k chars + overlap 1k + meta-summarize
  - Возвращается `truncated: true/false` для аудита
- **Workflow node type fix**
  - `n8n-nodes-base.telegram` v1 (deprecated) → `n8n-nodes-base.telegramTrigger` v1 + `updates: ['message']`

### 🔧 Операционка (по LESSONS)
- **systemd unit** `newton-api.service` вместо `pkill -9 -f` (LESSONS §2.3)
  - `KillSignal=SIGTERM` + `TimeoutStopSec=15` + `PIDFile=/run/newton-api.pid`
  - `MemoryMax=700M` + `MemoryHigh=550M` (OOM protection на 1.9 GB)
- **Split Flask** на 7 файлов вместо 852-строчного монолита (LESSONS §2.9)
  - `core/app.py` (162 строк) — каркас
  - `packages/research/` (663 строк) — YouTube/Piped/YandexGPT
  - `packages/kb/` (286 строк) — SQLite + render_digest
  - `packages/telegram_bot/` (38 строк) — /send_message
- **`init_kb()` в try/except** — не стартует молча при сломанной БД (LESSONS §2.9)
- **`__pycache__` cleanup** в `install.sh` step 3 (LESSONS §2.6)

### 🆕 Новое в API
- `POST /user_profile` (GET/POST) — персонализация LLM-промпта из KB
- `DAILY_BUDGET_RUB` env — дневной cap расходов на YandexGPT
- `/health_full` показывает: `yagpt_today_rub`, `chunks` за сегодня, `last_error`
- `cost` в ответе `/yagpt_summarize` — прозрачно для PM

### 📚 Документация
- KB §10.7: 5-step smoke test (PASS/FAIL)
- KB §10.8: systemd unit инструкция
- KB §10.9: как узнать Telegram user_id
- KB §10.10: rollback v6.x → v5.4

---

## v6.0 (2026-06-10)

### 🎯 Реальный контекст
- Вместо вымышленного — снят `bash context_collector.sh` с реального VPS
- 1 vCPU, 1.9 GB RAM, 0 swap, `googlevideo=000` — Beget IP заблокирован YouTube CDN

### ➕ Новые паттерны
- **Паттерн З**: Piped API для субтитров (без бана IP)
- **Паттерн И**: YandexGPT через HTTP
- **Паттерн К**: YouTube Data API v3 для метаданных
- **§4.5**: лимиты RAM/CPU (никаких параллельных LLM-вызовов)
- **§4.6**: запрет cookies/tor/proxychains, легальные пути
- **§7**: архитектурные паттерны v1

### 🐛 Фиксы
- v5.4 Flask: `/send_document` + `?ext=` в `/upload`
- psql-пользователь = `user`, не `n8n`
- n8n image minimal — не пытаться `docker exec curl`

---

## v6.1 (2026-06-10) — документация v6.0 улучшена

### ➕ Добавлено
- §0: миссия, 30-сек pitch, глоссарий (для LLM-агента, не для человека)
- §4.7: TZ drift — host UTC vs n8n MSK, jitter только через n8n Schedule Trigger
- §4.8: Piped 429 + exponential backoff
- §5.x нормализован: `EN: "<строка>" / RU: / FIX:` — агенто-грепабельно
- §10: runbooks (Telegram, Flask, OOM, Postgres, n8n_storage, pip install)
- §11: observability + бэкапы

---

## v5.2 → v5.4 (2026-06-04)

- Адаптация под Qwen Projects: инструкция <1000 символов
- Переход на `host.docker.internal`
- Добавлен `/send_document` в Flask v5.4
