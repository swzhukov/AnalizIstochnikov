# 🚀 N8N + NEWTON: БАЗА ЗНАНИЙ (v6.1.1)

**Версия:** 6.1.1 · 2026-06-10 (hotfix)
**Среда (подтверждено `bash context_collector.sh`):** Beget VPS, n8n v2.17.7, Newton CLI, Flask на хосте.

> **Для кого этот документ.** Этот KB пишется **прежде всего для LLM-агента**, который генерирует n8n workflow JSON для этого стека. Человек — вторичный читатель. Поэтому:
> - Все строки ошибок — **английский** (как их возвращает n8n/Flask)
> - Все описания — **русский** (как комментарии)
> - Все JSON-фрагменты — **копируемые as-is** в n8n v3 HTTP Request
> - Версия документов и changelog — **часть контракта**, не декорация

---

## 0. Что это и для кого

### 0.1 Миссия (1 строка)
Агент-читаемая база знаний для стека **n8n 2.17.7 + Newton CLI + Flask v5.4** на Beget VPS (1 vCPU, 1.9 GB RAM, 0 swap, RU).

### 0.2 30-секундный pitch
1. **Telegram-бот** (`@ZhukovsFirstBot`) принимает YouTube URL или голосовое.
2. **Flask-обёртка** на хосте вытаскивает субтитры через **Piped API** (а не `googlevideo.com`, который =000 на этом IP) и метаданные через **YouTube Data API v3**.
3. **YandexGPT** (HTTP-вызов) делает суммаризацию → 5 буллетов + 3 action items.
4. **Flask `/send_document`** шлёт HTML/PDF-дайджест обратно в Telegram.
5. **Newton CLI** используется **только** для распознавания голоса (Telegram voice, кружочки) — не для YouTube.

### 0.3 Глоссарий (8 терминов)

| Термин | Что это |
|--------|---------|
| **Newton** | CLI-инструмент распознавания речи от Newton Services. Живёт в `/usr/local/bin/newton`. Токен в `.env`: `NEWTON_TOKEN`. |
| **engine v3** | Параметр `engine` для `/transcribe`. Whisper-large модель Newton. Не путать с версией Newton CLI (тут 1.0+). |
| **KAPITAL_TELEGRAM_BOT_TOKEN** | Токен второго Telegram-бота в `.env`. **Flask его НЕ использует** (читает только `TELEGRAM_BOT_TOKEN`). Зарезервирован под будущий проект. **Не удалять и не использовать**, пока неясно зачем. |
| **Piped** | Open-source frontend для YouTube. `pipedapi.kavin.rocks` (и 3 других зеркала) отдают JSON с метаданными и субтитрами. Не путать с `piped.video` (web-фронт). |
| **Invidious** | Альтернативный open-source YouTube-frontend. `yewtu.be/api/v1/videos/<id>` отдаёт JSON **с другой схемой** (`captions[]` вместо `subtitles[]`). Использовать как fallback #1. |
| **googlevideo=000** | YouTube-стриминговый CDN заблокирован / timeout на Beget IP. Поэтому `newton fetch` для YouTube **не работает**. Субтитры — только Piped/Invidious. |
| **n8n_storage** | Docker-volume, который хранит `/home/node/.n8n` — все workflows, credentials, encryption keys. **Это самое ценное в стеке** (дни на пересборку). Бэкапить обязательно. |
| **Beget** | Российский хостинг-провайдер (RU-ASN). VPS с 1 vCPU/1.9 GB. Cloud-IP, поэтому YouTube CDN банит. |

### 0.4 Что НЕ в этом стеке
- ❌ Нет векторной БД (Chroma, pgvector) — для v1 keyword search хватает
- ❌ Нет embedding-модели — экономит RAM
- ❌ Нет parallel LLM-вызовов — OOM kill на 1 vCPU
- ❌ Нет прокси / tor / cookies для YouTube — бан аккаунта

---

## 1. Инфраструктура (реальная)

### 1.1 Хост
- **Хостнейм:** `wxvwmvycks`
- **ОС:** Ubuntu 24.04.4 LTS (Noble), kernel 6.8.0-124
- **CPU/RAM/Disk:** **1 vCPU, 1.9 GiB RAM, 14 GB диск, 6.6 GB свободно, 0 swap** ⚠️ тесно → **добавить swap обязательно, см. §10.3**
- **Публичный IP:** `217.114.7.5` (RU, Beget, Екатеринбург) → cloud-IP → YouTube-блок по `timedtext`
- **TZ на хосте:** `Etc/UTC` (см. ⚠️ важно про TZ drift в §4.5)

### 1.2 Docker-стек
| Контейнер | Образ | Статус | Порты |
|-----------|-------|--------|-------|
| `n8n-n8n-1` | `docker.n8n.io/n8nio/n8n:2.17.7` | Up 6d (healthy) | 127.0.0.1:5678 |
| `n8n-n8n-worker-1` | то же | Up 6d (healthy) | — |
| `n8n-postgres-1` | `postgres:16` | Up 6d (healthy) | 127.0.0.1:5432 |
| `n8n-redis-1` | `redis:6-alpine` | Up 6d (healthy) | 6379 |
| `n8n-traefik-1` | `traefik:3.6.5` | Up 6d | 80/443 |

- **Сеть:** `n8n_net` (bridge), n8n IP = `172.19.0.6`
- **extra_hosts:** ✅ `host.docker.internal:host-gateway` уже настроен
- **n8n image — minimal:** ⚠️ внутри контейнера **нет `bash`/`curl`/`getent`**. Тестировать руками нельзя — только через ноды.

### 1.3 Критичные пути
| Что | Путь |
|-----|------|
| Beget stack | `/opt/beget/n8n/` |
| Flask | `/opt/beget/n8n/newton-api.py` |
| Хост-тома | `/opt/beget/n8n/{n8n_storage, db_storage, redis_storage, traefik_data, newton-tmp}` |
| Внутри n8n | `/opt/newton-tmp/` (volume `newton_tmp`) |
| Flask лог | `/opt/beget/n8n/api.log` |
| n8n storage | `n8n_storage:/home/node/.n8n` (volume) |

### 1.4 iptables (подтверждено)
```
Chain INPUT:
1  REJECT tcp dports 22 match-set f2b-sshd
2  ACCEPT tcp 172.16.0.0/12 dpt:8080  ← Docker-сеть пускает
```
**Политика ACCEPT по умолчанию.** Никаких DROP-правил на 8080 нет — `host.docker.internal:8080` работает.

### 1.5 Сетевые лимиты (критично для YouTube-парсинга)
| Хост | HTTP | Что значит |
|------|------|-----------|
| `youtube.com` | 200 | Домен жив |
| `youtu.be` | 303 | Редирект ок |
| `googlevideo.com` | **000** | 🚫 Заблокирован/timeout — **видео/аудио с YouTube напрямую НЕ скачать** |
| `yt3.ggpht.com` | 400 | Префиксы CDN |
| `i.ytimg.com` | 404 | Превью |
| `piped.video` | **200** | ✅ Работает — основной путь к auto-subs |
| `yewtu.be` (invidious) | **200** | ✅ Работает — альтернатива |

> **Вывод:** `newton fetch` (через `googlevideo.com`) — **не работает** на этом VPS. Субтитры — только через `piped.video` / `yewtu.be` / YouTube Data API v3.

### 1.6 DNS
- Резолв идёт через **IPv6**: `2a00:1450:400f:802::200e` (youtube), `2001:67c:4e8:f004::9` (telegram)
- ✅ Yandex, Telegram API, Google — резолвятся

---

## 2. Flask Wrapper API v5.4 (полный код учтён)

### 2.1 Эндпоинты
| Метод | Путь | Тело | Ответ | Таймаут |
|-------|------|------|-------|---------|
| GET | `/` | — | healthcheck | — |
| POST | `/transcribe` | `{"file":"…","engine":"v3"}` | `{"text":"…"}` | 300с |
| POST | `/fetch` | `{"url":"…"}` | `{"file_path":"…"}` | 300с ⚠️ НЕ работает (googlevideo=000) |
| POST | `/download` | `{"url":"…"}` | `{"file_path":"…"}` | 120с |
| POST | `/telegram_download` | `{"file_id":"…"}` | `{"file_path":"…","size":N}` | 120с |
| POST | `/upload` | raw binary `?filename=…&ext=…` | `{"file_path":"…","size":N}` | — |
| POST | `/save_text` | `{"text":"…","filename":"…"}` | `{"file_path":"…","size":N}` | — |
| POST | `/send_document` | `{"file_path":"…","chat_id":"…","message_id":N,"caption":"…"}` | `{"status":"sent","message_id":N}` | 30с |

**Версия:** поднята с v5.2 → v5.4:
- Добавлен `?ext=…` в `/upload`
- Добавлен `/send_document` (Telegram sendDocument через Flask — экономит одну HTTP-ноду в n8n)
- `stdin=DEVNULL` в `run_newton` — не висит на пайпе

### 2.2 Переменные `.env` (текущие)
```env
NEWTON_TOKEN=***
TELEGRAM_BOT_TOKEN=***              # @ZhukovsFirstBot
KAPITAL_TELEGRAM_BOT_TOKEN=***      # отдельный бот — НЕ используется Flask по умолчанию
N8N_ENCRYPTION_KEY=***
POSTGRES_USER=root
POSTGRES_PASSWORD=***
POSTGRES_NON_ROOT_USER=user
POSTGRES_NON_ROOT_PASSWORD=***
```

### 2.3 Что нужно добавить (для v6+)
```env
# YandexGPT (основной LLM)
YANDEX_GPT_API_KEY=***
YANDEX_GPT_FOLDER_ID=***

# YouTube Data API v3
YOUTUBE_API_KEY=***

# pip - новые пакеты на хосте (запустить pip3 install)
# flask-cors, requests уже есть
```

---

## 3. Golden Patterns (обновлены под v6.0)

### 3.1 Паттерн А: Классификация (Code v2) — НЕ ИЗМЕНИЛСЯ
*(тот же из v5.2)*

### 3.2 Паттерн Б: Telegram download
*(тот же)*

### 3.3 Паттерн В: Отправка документа в Telegram
**Новый вариант v6.0** — через Flask `/send_document` (1 нода вместо 3):
```json
{
  "method": "POST",
  "url": "http://host.docker.internal:8080/send_document",
  "sendBody": true,
  "specifyBody": "json",
  "jsonBody": "={{ { file_path: '/opt/newton-tmp/txt_' + $('Detect Type').first().json.unique_id + '.txt', chat_id: $('Detect Type').first().json.chat_id, message_id: $('Detect Type').first().json.message_id, caption: 'Распознавание завершено' } }}"
}
```

### 3.4 Паттерн Г: Upload binary в Flask — НЕ ИЗМЕНИЛСЯ

### 3.5 Паттерн Д: Save text в Flask — НЕ ИЗМЕНИЛСЯ

### 3.6 Паттерн Е: IF-узел v2 — НЕ ИЗМЕНИЛСЯ

### 3.7 Паттерн Ж: IF-каскад — НЕ ИЗМЕНИЛСЯ

### 3.8 Паттерн З (НОВЫЙ v6.0): Piped API — субтитры без бана
```javascript
// Code-узел: extract_video_id + build_piped_url
// ВАЖНО: на 429 — backoff (1s→2s→4s→8s), потом rotate instance (см. §4.8)
const url = $input.first().json.url || '';
const m = url.match(/(?:v=|youtu\.be\/|\/shorts\/)([0-9A-Za-z_-]{11})/);
if (!m) return [{ json: { error: 'no video id' } }];
const video_id = m[1];
return [{
  json: {
    video_id,
    piped_subs_url: `https://pipedapi.kavin.rocks/streams/${video_id}`,
    piped_alt_urls: [
      `https://pipedapi.adminforge.de/streams/${video_id}`,
      `https://watchapi.whatever.social/streams/${video_id}`,
      `https://pipedapi.in.projectsegfau.lt/streams/${video_id}`
    ],
    invidious_fallback: `https://yewtu.be/api/v1/videos/${video_id}`,
    // Piped возвращает subtitles:[{url, mimeType, name, code, autoGenerated}]
    // Invidious возвращает captions:[{label, languageCode, url}]
    // — это РАЗНЫЕ схемы, нормализовать в коде!
    schema_note: 'piped:subtitles[] vs invidious:captions[]'
  }
}];
```

### 3.9 Паттерн И (НОВЫЙ v6.0): YandexGPT через HTTP
```json
{
  "method": "POST",
  "url": "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
  "sendHeaders": true,
  "headers": {
    "Authorization": "Bearer ={{ $env.YANDEX_GPT_API_KEY }}",
    "x-folder-id": "={{ $env.YANDEX_GPT_FOLDER_ID }}",
    "Content-Type": "application/json"
  },
  "sendBody": true,
  "specifyBody": "json",
  "jsonBody": "={{ { modelUri: 'gpt://' + $env.YANDEX_GPT_FOLDER_ID + '/yandexgpt-lite', completionOptions: { stream: false, temperature: 0.3, maxTokens: 2000 }, messages: [ { role: 'system', text: $json.system }, { role: 'user', text: $json.user } ] } }}"
}
```
**Альтернатива v6.1 — IAM-токен (рекомендуется для production):**
- Получить: `yc iam create-token` (CLI) → TTL 12 часов
- В env положить `YANDEX_GPT_IAM_TOKEN`, использовать вместо `YANDEX_GPT_API_KEY`
- В n8n добавить cron-ноду раз в 11 часов, которая обновляет токен через `HTTP Request` к Yandex Cloud metadata endpoint или через `subprocess` в Flask
- **Пока работает и API key** (Yandex Cloud ротирует постепенно) — миграция не срочная, но запланировать

### 3.10 Паттерн К (НОВЫЙ v6.0): YouTube Data API v3 — метаданные
```json
{
  "method": "GET",
  "url": "https://www.googleapis.com/youtube/v3/videos",
  "sendQuery": true,
  "queryParameters": {
    "parameters": {
      "key": "={{ $env.YOUTUBE_API_KEY }}",
      "part": "snippet,contentDetails,statistics",
      "id": "={{ $json.video_id }}"
    }
  }
}
```

---

## 4. Жёсткие правила v6.0

### 4.1 Допустимые версии нод (без изменений)
- `telegram: v1`
- `httpRequest: v3`
- `set: v3.3`
- `code: v2`
- `if: v2`
- `readWriteFile: v1` (только чтение)

### 4.2 Запрещено (без изменений + новые)
- ❌ `fileOperations`
- ❌ `readWriteFile` для записи
- ❌ `fs` в Code
- ❌ `process.env` в Code → `$env.VAR`
- ❌ `operation: "download"` в Telegram
- ❌ `localhost`, `127.0.0.1`, `172.17.0.1` → `host.docker.internal`
- ❌ `$credentials` в Set
- ❌ `JSON.stringify(...)` в jsonBody → объект `={{ { key: value } }}`
- ❌ `bash`/`curl` в docker exec n8n — **image минимальный, ничего нет**
- ❌ **Параллельные LLM-вызовы** на 1 vCPU/1.9 GB RAM — OOM kill

### 4.3 Credentials (без изменений)

### 4.4 Уникальные ID (без изменений)

### 4.5 НОВОЕ: Питание и параллелизм
- **1 vCPU, 1.9 GB RAM, 0 swap** — это лимитирующий фактор
- Никаких `SplitInBatches` с concurrency > 1 для LLM/Newton
- Крон-расписание — с **jitter ±15 минут**, иначе LLM-сессии стартуют одновременно и убивают RAM
- Newton-сессия с audio 30+ мин → `transcribe` жрёт ~500 MB RAM. Не запускать 2 параллельно.

### 4.6 НОВОЕ: Никаких cookies / tor / proxychains
YouTube банит за cloud-IP. **Законные пути** (без риска бана):
- ✅ YouTube Data API v3 (твоим ключом) — метаданные, комменты, описания, теги
- ✅ Piped API (`pipedapi.kavin.rocks` и т.п.) — субтитры + метаданные
- ✅ Invidious API (`yewtu.be` и т.п.) — субтитры + метаданные
- ❌ `youtube-transcript-api` напрямую с Beget IP — бан
- ❌ `yt-dlp` + cookies — бан аккаунта
- ❌ `tor`/`proxychains4` — не установлены, рисково

### 4.7 НОВОЕ: TZ drift (критично)
- Хост: `Etc/UTC`
- n8n env: `Europe/Moscow`
- Cron в n8n и Flask стартует по MSK, но jitter считается на хосте
- **Правило:** все cron в n8n-формате `0 9 * * 1` интерпретируются как **MSK**. Если хочется jitter — ставить Schedule Trigger с `timezone: Europe/Moscow` и `triggerAtRandom: true`, **не** полагаться на host crontab.
- В логах — UTC, в Telegram-сообщениях — конвертировать `new Date().toLocaleString('ru-RU', {timeZone: 'Europe/Moscow'})`.

### 4.8 НОВОЕ: Piped 429 + exponential backoff
Piped-инстансы — добровольные, без SLA. Rate-limit неизвестен, но точно есть. **Правило**:
- При 429 — backoff: 1s → 2s → 4s → 8s, макс 4 retry
- Затем — rotate instance (см. §3.8)
- Затем — fall back на Invidious
- Затем — fail с structured error в KB (`source: 'piped_all_429'`)
- **Не долбить** один инстанс — это путь к бану

---

## 5. Известные ошибки и решения (нормализованный формат)

> **Формат:** `EN: "<строка ошибки>" / RU: <описание> / FIX: <паттерн>`. Каждая строка ошибки — **английский**, как её возвращает n8n/Flask. Описание — русский. Это позволяет LLM-агенту делать literal grep.

### 5.1 Telegram
| EN-строка | Описание | FIX |
|-----------|----------|-----|
| `The value 'download' is not supported` | Нода Telegram без правильного `operation` | `resource:"file", operation:"get", download:true` |
| `expects binary file 'data', but none was found` | Не передан бинарь | Добавить `download:true` |
| `404 The resource could not be found` | file_id битый или credential не привязан | `.trim()` к file_id + проверить credential |

### 5.2 Запись файлов
| EN-строка | Описание | FIX |
|-----------|----------|-----|
| `The file ... is not writable` (readWriteFile) | readWriteFile не имеет прав на запись | Использовать `/upload` или `/save_text` |
| `Module 'fs' is disallowed` | Code-нода пытается `require('fs')` | Использовать Flask endpoints |
| `The value in the "JSON Body" field is not valid JSON` | Передали строку вместо объекта | Объект `={{ { key: value } }}` |

### 5.3 Сеть
| EN-строка | Описание | FIX |
|-----------|----------|-----|
| `connection refused` к Flask (127.0.0.1:8080) | Из контейнера нельзя на 127.0.0.1 | Заменить на `http://host.docker.internal:8080` |
| `host.docker.internal` не резолвится | Нет `extra_hosts` в docker-compose | Добавить `"host.docker.internal:host-gateway"` + `docker-compose up -d` |

### 5.4 Flask
| EN-строка | Описание | FIX |
|-----------|----------|-----|
| Flask не стартует | NEWTON_TOKEN/TELEGRAM_BOT_TOKEN не подхвачены | `pkill -9 -f newton-api.py && NEWTON_TOKEN=... TELEGRAM_BOT_TOKEN=... nohup python3 newton-api.py > api.log 2>&1 &` |
| Newton `OllamaError` / `engine` не найден | Движок `v3` не установлен | `newton engines list` + проверить лицензию |

### 5.5 НОВОЕ: docker exec curl/bash не найден
- **EN:** `OCI runtime exec failed: executable file not found in $PATH`
- **RU:** n8n 2.17.7 — minimal image, нет bash/curl
- **FIX:** Не пытаться тестировать из контейнера руками. Всё через workflow-ноды (HTTP Request к `host.docker.internal:8080`).

### 5.6 НОВОЕ: googlevideo.com = 000
- **EN:** `newton fetch` → `error: timed out` или `error: HTTP 000`
- **RU:** Beget блокирует / YouTube не отдаёт на этот IP
- **FIX:** Не использовать `/fetch` для YouTube. Субтитры — Piped (паттерн З). Метаданные — YouTube Data API v3 (паттерн К).

### 5.7 НОВОЕ: psql role "n8n" does not exist
- **EN:** `psql: error: connection to server ... FATAL: role "n8n" does not exist`
- **RU:** В `.env` `POSTGRES_USER=root`, а не `n8n`. Реальный пользователь n8n — `POSTGRES_NON_ROOT_USER=user`.
- **FIX:** `docker exec n8n-postgres-1 psql -U user -d n8n -c "\dt"`

### 5.8 НОВОЕ: YandexGPT auth/format
- **EN:** `401 Unauthorized` (с статическим API key) → Yandex Cloud ротирует auth. **FIX:** использовать IAM-токен `yc iam create-token` (12ч TTL) вместо API key, или мигрировать на новый endpoint.
- **EN:** `400 Bad Request: x-folder-id required` → забыли header. **FIX:** добавить `x-folder-id: <id>` в headers.
- **EN:** `400 Bad Request: modelUri required` → забыли modelUri. **FIX:** `modelUri: 'gpt://' + folderId + '/yandexgpt-lite'`.

---

## 6. Команды управления (без изменений + новые)

```bash
# YandexGPT — добавить в .env (nano /opt/beget/n8n/.env)
YANDEX_GPT_API_KEY=...
YANDEX_GPT_FOLDER_ID=...
YOUTUBE_API_KEY=...

# pip install на хосте (новые пакеты для Flask)
pip3 install --break-system-packages flask-cors  # если нужен CORS

# Postgres — правильный пользователь
docker exec n8n-postgres-1 psql -U user -d n8n -c "\dt"

# Проверить, что piped.video ещё жив
curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 https://pipedapi.kavin.rocks/streams/dQw4w9WgXcQ
```

---

## 7. Архитектурные паттерны v6.0

### 7.1 Источники данных (приоритет — дёшево → дорого)
1. **YouTube Data API v3** (метаданные, теги, описание, комменты) — **бесплатно**, лимит 10 000 units/день
2. **Piped API / Invidious API** (субтитры auto-gen) — бесплатно, чужой сервер, без твоего IP
3. **Newton CLI** (распознавание голоса) — **только для аудио без субтитров** (Telegram voice, кружочки, длинные стримы)
4. **YandexGPT** (суммаризация, action items, реранкер) — **основной LLM**, тарифицируется по токенам

### 7.2 Хранилище
- **SQLite** через Flask-эндпоинты (n8n не умеет писать файлы)
- Файл: `/opt/beget/n8n/newton-tmp/research.db` (или отдельный том)
- Схема v1: `sources`, `claims`, `digests`, `actions`, `user_profile`

### 7.3 Выход дайджеста
- **Markdown → HTML** (через Python) → отправка в Telegram как `sendDocument` с `.html` или `.pdf`
- **Google Sheets** — для action items (когда подключишь gspread в Flask)

---

## 8. Шаблон workflow "Research Agent v1"

```
1. Telegram Trigger ("/fetch <url>")
        ↓
2. Code (extract_video_id)             Паттерн З
        ↓
3. HTTP GET piped_subs_url              Piped API → subtitles + meta
        ↓
4. IF subs.lang exists?
        ├─ true → текст готов
        └─ false → HTTP GET invidious_alt → IF exists → иначе fallback
        ↓
5. Code (build_yagpt_prompt)            system + user для YandexGPT
        ↓
6. HTTP POST llm.api.cloud.yandex.net  Паттерн И
        ↓
7. Code (parse_summary + actions)
        ↓
8. HTTP POST /save_text (digest.json)
        ↓
9. HTTP POST /send_document             файл в Telegram
        ↓
10. Telegram sendMessage (TL;DR)
```

---

## 10. Runbooks (2am-готовность)

### 10.1 Telegram бот не отвечает
1. `docker exec n8n-n8n-1 wget -q -O- http://host.docker.internal:8080/` → должен быть JSON
2. Если не отвечает — `pkill -9 -f newton-api.py && nohup python3 /opt/beget/n8n/newton-api.py > /opt/beget/n8n/api.log 2>&1 &`
3. Проверить: `curl -s http://localhost:8080/`
4. Если бот всё ещё мёртв — проверить токен: `grep TELEGRAM_BOT_TOKEN /opt/beget/n8n/.env | head -c 30`
5. Проверить, что n8n запущен: `docker ps | grep n8n-n8n-1`

### 10.2 Flask не стартует
1. `tail -50 /opt/beget/n8n/api.log` — посмотреть причину
2. Типичные: `ModuleNotFoundError` → `pip3 install --break-system-packages <pkg>`
3. `Permission denied` → `sudo chown -R 1000:1000 /opt/beget/n8n/newton-tmp`
4. `Address already in use` → `pkill -9 -f newton-api.py`
5. После фикса: `pkill -9 -f newton-api.py && nohup python3 newton-api.py > api.log 2>&1 &` + `sleep 2 && curl -s http://localhost:8080/`

### 10.3 OOM kill (создание swap)
**Симптом:** контейнеры умерли, `dmesg | grep -i oom` показывает kill, RAM > 95% в `free -h`.
**FIX (один раз, ~5 минут):**
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # проверить
```
**После создания swap** — снизить вероятность OOM: не запускать > 1 Newton-сессии параллельно (см. §4.5).

### 10.4 Postgres restore (если volume db_storage помер)
1. **Сначала бэкапы.** `crontab -l` должен содержать ежедневный `pg_dump`. Если его нет — см. §11.3.
2. `docker exec n8n-postgres-1 pg_restore -U user -d n8n -c /backups/n8n_<date>.dump`
3. Если volume цел, но Postgres не стартует — `docker logs n8n-postgres-1 | tail -50`
4. Если volume помер — `docker-compose down && rm -rf db_storage && docker-compose up -d` (потеря данных! восстанавливать из бэкапа)

### 10.5 n8n_storage restore (если volume n8n_storage помер)
**Сценарий:** все workflows + credentials потеряны.
**FIX:** restore из бэкапа (см. §11.3):
```bash
sudo tar -xzf /backups/n8n_storage_<date>.tar.gz -C /opt/beget/n8n/
docker-compose restart n8n
```
**Если бэкапа нет** — пересоздавать workflows вручную (дни работы). **Бэкап n8n_storage обязателен.**

### 10.6 pip3 install (новый пакет в Flask)
```bash
pip3 install --break-system-packages <package>
# или для изоляции:
python3 -m venv /opt/beget/n8n/venv
source /opt/beget/n8n/venv/bin/activate
pip install <package>
# и в newton-api.py: добавить /opt/beget/n8n/venv/lib/python3.12/site-packages в sys.path
```

---

### 10.7 Smoke test (PASS/FAIL процедура) — v6.1.1 NEW
После ЛЮБОГО деплоя выполнить:
```bash
# 1. Health check
curl -s http://localhost:8080/health_full | python3 -m json.tool
# Ожидаем: status=ok, version=6.0.1, ram_pct<85, auth_enabled=true

# 2. Auth gate (без X-Telegram-User-Id → 403)
curl -s -X POST http://localhost:8080/youtube_meta \
  -H "Content-Type: application/json" -d '{"url":"https://youtu.be/6Z_hHWStwxw"}' \
  -w "\nHTTP %{http_code}\n"
# Ожидаем: HTTP 403, {"error":"unauthorized"}

# 3. Auth gate (с правильным user_id → 200)
USER_ID=$(grep ALLOWED_TELEGRAM_USERS /opt/beget/n8n/.env | cut -d= -f2 | cut -d, -f1)
curl -s -X POST http://localhost:8080/youtube_meta \
  -H "Content-Type: application/json" \
  -H "X-Telegram-User-Id: $USER_ID" \
  -d '{"url":"https://youtu.be/6Z_hHWStwxw"}' \
  -w "\nHTTP %{http_code}\n" | head -c 500
# Ожидаем: HTTP 200, JSON с title, channel, duration_sec

# 4. Subs endpoint (долго, 5-15 сек)
time curl -s -X POST http://localhost:8080/youtube_subs \
  -H "Content-Type: application/json" \
  -H "X-Telegram-User-Id: $USER_ID" \
  -d '{"url":"https://youtu.be/6Z_hHWStwxw","lang":"ru"}' | head -c 500
# Ожидаем: HTTP 200, JSON с text (subtitles), char_count > 100

# 5. End-to-end через Telegram
# Открыть @ZhukovsFirstBot, отправить:
#   https://youtu.be/6Z_hHWStwxw
# Ожидаем (в течение 30-60 сек):
#   a) HTML-файл дайджеста (.html)
#   b) Текстовое сообщение TL;DR с cost и chunks
#   c) /health_full показывает yagpt_today_rub > 0
```

### 10.8 systemd unit (вместо pkill) — v6.1.1 NEW
**Проблема (LESSONS §2.3):** `pkill -9 -f newton-api.py` ненадёжен. Процесс может иметь другое имя, обёртку, supervisord.

**Решение:** systemd unit + SIGTERM + PID-файл.
Файл `/etc/systemd/system/newton-api.service`:
```ini
[Unit]
Description=Newton API + Research Agent (v6.0.1)
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/beget/n8n/research-agent
EnvironmentFile=/opt/beget/n8n/.env
ExecStart=/usr/bin/python3 core/app.py
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=15
PIDFile=/run/newton-api.pid
StandardOutput=append:/opt/beget/n8n/api.log
StandardError=append:/opt/beget/n8n/api.log
MemoryMax=700M
MemoryHigh=550M

[Install]
WantedBy=multi-user.target
```

**Установка (один раз):**
```bash
sudo cp /opt/beget/n8n/research-agent/deploy/newton-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable newton-api
sudo systemctl start newton-api
```

**Дальше (БЕЗ pkill):**
- `sudo systemctl status newton-api` — статус
- `sudo systemctl restart newton-api` — рестарт
- `sudo journalctl -u newton-api -n 50` — логи

**Fallback (если systemd недоступен) — kill по PID-файлу или по порту:**
```bash
PID=$(cat /run/newton-api.pid 2>/dev/null)
[ -n "$PID" ] && kill -TERM $PID
# или:
PORT_PID=$(ss -tlnp 2>/dev/null | grep ':8080 ' | grep -oP 'pid=\K[0-9]+' | head -1)
[ -n "$PORT_PID" ] && kill -TERM $PORT_PID
```

### 10.9 auth gate — как узнать свой Telegram user_id — v6.1.1 NEW
1. Открыть Telegram, найти бота `@userinfobot` (или `@getmyid_bot`)
2. Написать ему `/start` — он ответит ваш `id` (число)
3. Добавить в `/opt/beget/n8n/.env`:
   ```env
   ALLOWED_TELEGRAM_USERS=ваш_id
   ```
4. `sudo systemctl restart newton-api`
5. Проверить: §10.7 smoke test step 3

**КРИТИЧНО:** Если `ALLOWED_TELEGRAM_USERS` пустой — **ВСЕ** опасные эндпоинты вернут 403. Это by design (защита от unbounded cost и data exfiltration), но если workflow вдруг перестал работать — первое что проверить.

---

### 10.10 Rollback v6.x → v5.4 (если что-то сломалось) — v6.1.1 NEW
```bash
# 1. Смотрим доступные бэкапы
ls -la /opt/beget/n8n/backups/research-agent/

# 2. Достать последний бэкап Flask
TS=$(ls -t /opt/beget/n8n/backups/research-agent/newton-api_*.py | head -1 | grep -oP '\d{8}_\d{6}')
cp /opt/beget/n8n/backups/research-agent/newton-api_$TS.py /opt/beget/n8n/newton-api.py

# 3. Очистить __pycache__
find /opt/beget/n8n/research-agent -type d -name __pycache__ -exec rm -rf {} +

# 4. Рестарт
sudo systemctl restart newton-api && sleep 3 && curl -s http://localhost:8080/
```

---

## 11. Observability и бэкапы

### 11.1 Расширенный /healthcheck
**Проблема:** текущий `/` возвращает только `{status: ok}`. Не видно RAM, in-flight запросов, последней ошибки.
**Предложение v6.2:** расширить Flask `/`:
```python
@app.route('/')
def health():
    import psutil
    return jsonify({
        'status': 'ok',
        'version': '5.4',
        'service': 'newton-api',
        'ram_pct': psutil.virtual_memory().percent,
        'disk_pct': psutil.disk_usage('/opt/beget/n8n').percent,
        'load_1m': psutil.getloadavg()[0],
        'uptime_sec': time.time() - psutil.Process().create_time(),
        'inflight_newton': NEWTON_INFLIGHT,  # см. §11.2
    })
```

### 11.2 Concurrency bound для /transcribe
**Проблема:** Flask dev-server порождает поток на запрос, каждый `newton transcribe` ест ~500 MB. 5 одновременно = OOM.
**Предложение v6.2:** обернуть `run_newton` в `concurrent.futures.ThreadPoolExecutor(max_workers=1)` и отдавать 503 при превышении лимита.

### 11.3 Бэкап (cron на хосте)
```bash
# /etc/cron.d/research_backup
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Каждый день в 04:00 UTC = 07:00 MSK
0 4 * * * root \
  tar -czf /opt/beget/n8n/backups/n8n_storage_$(date +\%Y\%m\%d).tar.gz -C /opt/beget/n8n n8n_storage 2>/dev/null; \
  docker exec n8n-postgres-1 pg_dump -U user n8n | gzip > /opt/beget/n8n/backups/n8n_pg_$(date +\%Y\%m\%d).sql.gz; \
  find /opt/beget/n8n/backups/ -mtime +7 -delete
```
- **Хранить локально 7 дней**, потом удалять.
- **В перспективе** — rsync на отдельный VPS или Yandex Object Storage (бесплатно 5GB).

### 11.4 Log rotation
**Проблема:** `/opt/beget/n8n/api.log` растёт неограниченно. На 6.6 GB свободно это вопрос недель.
**FIX:** `logrotate` или простой cron:
```bash
# /etc/cron.d/logrotate_api
0 0 * * 0 root \
  mv /opt/beget/n8n/api.log /opt/beget/n8n/api.log.$(date +\%Y\%m\%d); \
  pkill -HUP -f newton-api.py; \
  find /opt/beget/n8n/api.log.* -mtime +14 -delete
```

### 11.5 Disk alert
**Предложение v6.2:** в `/` healthcheck добавить `disk_pct` (см. §11.1), n8n cron раз в час делает `HTTP Request` к `/` и шлёт в Telegram при `disk_pct > 80`.

---

## 12. История изменений

**v6.1.1 (2026-06-10, hotfix по итогам council v2 + LESSONS Kapital):**
- 🚨 Auth gate на всех опасных эндпоинтах через `ALLOWED_TELEGRAM_USERS` (Council #2)
- 🚨 Chunking в `/yagpt_summarize` (Council Outsider #8 — silent truncation)
- 🚨 systemd unit `newton-api.service` вместо `pkill -9 -f` (LESSONS §2.3)
- 🐛 `init_kb()` в try/except (LESSONS §2.9)
- 🐛 `__pycache__` cleanup в restart runbook (LESSONS §2.6)
- 🐛 Workflow: `telegramTrigger` v1 + `updates: ['message']` (вместо deprecated `telegram`)
- 💰 Daily budget cap `DAILY_BUDGET_RUB` + cost в `/health_full`
- 🆕 `POST /user_profile` (GET/POST) для персонализации LLM-промпта
- 🆕 systemd unit с `MemoryMax=700M` (OOM protection)
- ➕ §10.7 Smoke test (PASS/FAIL процедура)
- ➕ §10.8 systemd unit инструкция
- ➕ §10.9 auth gate: как узнать Telegram user_id
- ➕ §10.10 Rollback v6.x → v5.4
- 🗑️ Удалена `KAPITAL_TELEGRAM_BOT_TOKEN` поддержка из core/app.py (PM решит: живой или мёртвый)

**v6.1 (2026-06-10):**
- ➕ §0: миссия, 30-сек pitch, глоссарий (для LLM-агента, не для человека)
- ➕ §4.7: TZ drift — host UTC vs n8n MSK, jitter только через n8n Schedule Trigger
- ➕ §4.8: Piped 429 + exponential backoff
- ➕ §5.x нормализован: `EN: "<строка>" / RU: / FIX:` — агенто-грепабельно
- ➕ §10: runbooks (Telegram, Flask, OOM, Postgres, n8n_storage, pip install)
- ➕ §11: observability + бэкапы (/healthcheck, concurrency bound, backup cron, log rotation, disk alert)
- 🐛 §3.8: `schema_note` в Piped-паттерне — про subtitles[] vs captions[]
- 🐛 §5.5–5.11: новые ошибки (docker exec minimal, googlevideo, psql role, YandexGPT auth, Piped 429, NEWTON_TOKEN, Telegram 50MB)
- 🐛 §1.1: упоминание swap=0 и обязательность §10.3

**v6.0 (2026-06-10):**
- 🎯 Реальный контекст VPS Beget вместо вымышленного: 1 vCPU, 1.9 GB RAM, googlevideo=000
- ➕ Паттерн З: Piped API для субтитров
- ➕ Паттерн И: YandexGPT через HTTP
- ➕ Паттерн К: YouTube Data API v3 для метаданных
- ➕ Раздел 4.5: лимиты RAM/CPU
- ➕ Раздел 4.6: запрет cookies/tor/proxychains, легальные пути
- ➕ Раздел 7: архитектурные паттерны v1
- 🐛 v5.4 в Flask: `/send_document` + `?ext=` в `/upload`
- 🐛 psql-пользователь = `user`, не `n8n`
- 🐛 n8n image minimal — не пытаться `docker exec curl`

**v5.2 (2026-06-04):**
- Адаптация под Qwen Projects: инструкция <1000 символов
- Переход на `host.docker.internal`
