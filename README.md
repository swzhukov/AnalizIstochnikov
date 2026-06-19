# Анализ Источников (AnalizIstochnikov)

> **Личный research-агент**: Telegram-бот → YouTube URL / голосовое → авто-сабы через **Piped API** (без бана IP) → суммаризация через **YandexGPT** → HTML-дайджест в Telegram + SQLite-база знаний.

## 🎯 Что это

Самохостящийся ассистент для инвестора (или любого эксперта), который:
- принимает YouTube-ссылку в Telegram
- вытаскивает авто-субтитры через **Piped/Invidious API** (потому что YouTube CDN банит VPS Beget — `googlevideo=000`)
- отправляет субтитры в **YandexGPT** с учётом твоего `user_profile`
- возвращает структурированный **HTML-дайджест** (summary + action items + ключевые тезисы)
- сохраняет всё в **SQLite** для последующего поиска
- **Newton CLI** используется **только** для распознавания голоса (Telegram voice / кружочки), не для YouTube

## 🧱 Стек

| Компонент | Версия | Зачем |
|-----------|--------|-------|
| **n8n** | 2.17.7 (Docker) | Оркестратор workflow, Telegram Trigger |
| **Flask** | 3.x (Python 3.12) | Обёртка над Newton + внешними API |
| **Newton CLI** | 1.0+ | Распознавание голоса |
| **Piped API** | публичные зеркала | Субтитры (auto-gen) |
| **Invidious API** | fallback | Субтитры (другая схема, см. KB §3.8) |
| **YandexGPT** | yandexgpt-lite | LLM для суммаризации |
| **YouTube Data API v3** | v3 | Метаданные, теги, описания |
| **SQLite** | 3 | База знаний |
| **systemd** | — | Управление процессом (НЕ pkill -9) |

**Хост:** Beget VPS, 1 vCPU, 1.9 GB RAM, 0 swap. **Тесно, но работает.**

## 📦 Структура репо

```
AnalizIstochnikov/
├── README.md                          ← ты здесь
├── LICENSE                            ← MIT
├── .gitignore                         ← secrets, __pycache__, runtime/
├── .github/workflows/lint.yml         ← CI: py_compile на каждый push
├── docs/
│   ├── KB.md                          ← полная база знаний v6.1.1
│   ├── QUICKREF.md                    ← шпаргалка v6.1.1
│   ├── CHANGELOG.md                   ← история версий
│   ├── LESSONS.md                     ← процессные уроки (10 грабель, 9 принципов)
│   └── ROADMAP.md                     ← что будет в v6.2 / v6.3
├── research-agent/                    ← Flask-приложение
│   ├── core/app.py                    ← каркас + auth gate + health
│   ├── packages/
│   │   ├── research/                  ← YouTube/Piped/YandexGPT
│   │   ├── kb/                        ← SQLite + render_digest
│   │   └── telegram_bot/              ← /send_message
│   └── deploy/
│       ├── install.sh                 ← бэкап + __pycache__ + systemd + smoke test
│       ├── newton-api.service         ← systemd unit с OOM protection
│       └── env-template.txt           ← .env шаблон
├── workflows/
│   └── research-agent-v1.1.json      ← n8n workflow (импортируется через UI)
└── examples/
    └── user-profile.example.json      ← пример профиля для LLM
```

## 🚀 Quick start

### 1. Клонировать

```bash
git clone git@github.com:swzhukov/AnalizIstochnikov.git
cd AnalizIstochnikov
```

### 2. Заполнить `.env` (на VPS, не в репо)

Скопировать `research-agent/deploy/env-template.txt` в `/opt/beget/n8n/.env`, заполнить:
- `NEWTON_TOKEN`, `TELEGRAM_BOT_TOKEN` — уже есть
- `YOUTUBE_API_KEY` — Google Cloud Console → API Key
- `YANDEX_GPT_API_KEY`, `YANDEX_GPT_FOLDER_ID` — Yandex Cloud
- **`ALLOWED_TELEGRAM_USERS`** — КРИТИЧНО, твой Telegram user_id (через `@userinfobot`)
- `DAILY_BUDGET_RUB=200`

### 3. Запустить install.sh

```bash
bash research-agent/deploy/install.sh
```

Скрипт: бэкапит текущую версию → очищает `__pycache__` (LESSONS §2.6) → устанавливает systemd unit → рестарт → smoke test (§10.7 KB).

### 4. Импортировать workflow в n8n

n8n UI → Workflows → Import from File → `workflows/research-agent-v1.1.json`. Привязать Telegram credential к ноде "Telegram Trigger". Включить (Active).

### 5. Открыть @ZhukovsFirstBot, отправить YouTube URL

Через 15-30 секунд получаешь:
1. HTML-файл дайджеста
2. TL;DR текстом с cost и chunks
3. Запись в SQLite (`/opt/beget/n8n/kb/research.db`)

## 📊 Статус

| Версия | Статус | Что |
|--------|--------|-----|
| **v6.0.7** | ✅ ready | Auth gate, chunking, systemd, split Flask, KB §10.7-10.10 |
| **v6.2** | 📋 planned | Eval harness (20-видео golden set), `/cost_estimate`, proactive monitoring |
| **v6.3** | 📋 planned | LLM provider abstraction, KB as product |

## 🐛 Что уроки капитальского деплоя нас научили

См. `docs/LESSONS.md` — 10 конкретных bash-грабель (heredoc+pipe, `pkill -9`, `__pycache__`, etc.) и 9 процессных принципов. **Без них эта штука сломалась бы в первую же ночь.**

## 🔐 Безопасность

- **Auth gate** через `ALLOWED_TELEGRAM_USERS` — без токена Flask отдаёт 403 на все опасные эндпоинты
- **Daily budget cap** через `DAILY_BUDGET_RUB` — при превышении `/yagpt_summarize` вернёт 429
- **No cookies, no tor, no proxychains** для YouTube — это путь к бану. Только легальные Piped/Invidious
- **systemd MemoryMax=700M** — не даём OOM убить весь VPS

## 📝 Лицензия

MIT. См. `LICENSE`.

## 👤 Автор

Sergei Zhukov ([@swzhukov](https://github.com/swzhukov))
