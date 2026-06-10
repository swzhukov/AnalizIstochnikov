# ROADMAP — что дальше

## v6.2 (через 1-2 недели) — product reshape

| Фича | Зачем | Сложность |
|------|-------|-----------|
| **Eval harness** | Измерять качество дайджестов. 20-видео golden set, ROUGE-L + 5-question factual quiz | Средне |
| **`/cost_estimate` endpoint** | Перед LLM-вызовом сказать "это будет ~2₽". Прозрачно для PM | Легко |
| **Proactive monitoring** | Schedule Trigger + channel registry. Система сама ходит по 5-10 каналам раз в неделю | Средне |
| **Source registry** | `/sources` endpoint + UI. PM добавляет канал, бот автоматически делает weekly digest | Средне |
| **TZ enforcement** | Все cron через n8n Schedule Trigger с `timezone: Europe/Moscow` + `triggerAtRandom: true` | Легко |

## v6.3 (через 1 месяц) — compounding flywheel

| Фича | Зачем | Сложность |
|------|-------|-----------|
| **LLM provider abstraction** | yandexgpt/openai/ollama в config. Свич провайдера = 1 env-var | Легко |
| **`TESTED-BY` / `RAM-COST` / `FALLBACKS` per-pattern** | Эмпирические метрики по каждому паттерну в KB | Средне |
| **KB as standalone product** | LLM payload + human changelog + system prompt template. Продавать другим no-coder'ам на Beget | Тяжело |
| **Cross-source synthesis** | "Что 3+ блогера сказали про X в этом месяце" — тематический дайджест | Тяжело |
| **Credibility scoring** | После 6 мес собрать данные, кто из блогеров был прав. Weighted feed | Тяжело |

## v6.4 (через 3 месяца) — продукт для рынка

- White-label для других no-coder'ов на Beget VPS
- Telegram-канал как источник в дополнение к YouTube
- Распознавание голосовых в Nanogram (Newton → OpenAI Whisper fallback)
- Мобильный UI для просмотра дайджестов

## Не делать (anti-roadmap)

- ❌ Не делать self-hosted embedding модель — 1.9 GB RAM не хватит
- ❌ Не делать multi-user SaaS — security overhead, 1 пользователь
- ❌ Не делать vector DB (Chroma/pgvector) — keyword search в SQLite хватает
- ❌ Не уходить с Beget — дороже, и не нужно
- ❌ Не делать Telegram Premium как зависимость — 449₽/мес лишние расходы
