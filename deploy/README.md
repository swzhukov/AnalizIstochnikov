# Deploy — newton-api.shim

Содержимое для воспроизводимого деплоя research-agent на Beget VPS.

## Файлы

| Файл | Назначение |
|------|------------|
| `newton-api.full.py` | Backup актуального `/opt/beget/n8n/newton-api.py` (на 17.06.2026, 75 строк) |
| `shim-template.py` | Шаблон для добавления новых endpoints в существующий Flask monolith |

## Паттерн: merge-approach shim

**Почему не replace, а merge:**
- На Beget VPS `newton-api.py` уже обслуживает несколько проектов (kapital, research, и т.д.)
- Replace одного модуля = поломка других
- Merge добавляет endpoints без удаления существующих

**Структура основного newton-api.py (на 17.06.2026):**

```python
# 1. Newton endpoints (legacy, hardcoded)
@app.route('/transcribe', methods=['POST'])
def transcribe(): ...

# 2. KAPITAL shim (auto-patched, lazy import)
import sys
sys.path.insert(0, '/opt/beget/kapital')
from deploy.add_kapital_endpoints import register_kapital_endpoints
register_kapital_endpoints(app)

# 3. RESEARCH-AGENT v6.0.1 shim (auto-patched, lazy import)
RESEARCH_AGENT_DIR = '/opt/beget/n8n/research-agent'
if RESEARCH_AGENT_DIR not in sys.path:
    sys.path.insert(0, RESEARCH_AGENT_DIR)
import core.app as _core_app
for pkg in ('research', 'telegram_bot', 'kb'):
    mod = __import__(f'packages.{pkg}.routes', fromlist=['register'])
    mod.register(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## Установка нового проекта

1. Скопируй `shim-template.py` в `/opt/beget/<new-project>/deploy/add_<new>_endpoints.py`
2. Реализуй endpoints внутри `register_<new>_endpoints(app)`
3. Добавь в `/opt/beget/n8n/newton-api.py` (ПЕРЕД `if __name__ == '__main__':`):

```python
# ===== <NEW-PROJECT> (auto-patched YYYY-MM-DD) =====
import sys
sys.path.insert(0, '/opt/beget/<new-project>')
try:
    from deploy.add_<new>_endpoints import register_<new>_endpoints
    register_<new>_endpoints(app)
    print(f'[<NEW-PROJECT>] endpoints registered OK', flush=True)
except Exception as e:
    print(f'[<NEW-PROJECT>] FAILED: {e}', flush=True)
    import traceback
    traceback.print_exc()
# ===== END <NEW-PROJECT> =====
```

4. Перезапусти Flask:
```bash
pkill -9 -f newton-api.py; sleep 10
cd /opt/beget/n8n
set -a; source .env; set +a
nohup python3 newton-api.py > api.log 2>&1 &
```

5. Проверь health:
```bash
curl -s http://localhost:8080/<new-project>/health
```

## ⚠️ Потенциальные конфликты

1. **Route collision:** если у двух проектов одинаковый endpoint (например `/health`), последний загруженный перезапишет первый.
   - Решение: используй уникальные prefix'ы (`/<project>/*`)

2. **Lazy import failure:** если модуль сломан, endpoint вернёт 503 (не 500).
   - Решение: проверь `import_error` в `/<project>/health`

3. **Двойной запуск:** если Flask запущен дважды (старый PID + новый PID), порт 8080 коллизится.
   - Решение: `pkill -9 -f newton-api.py; sleep 10` перед запуском

4. **Werkzeug auto-reloader:** если Flask запущен с debug=True, любой mtime change триггерит рестарт.
   - Решение: `FLASK_DEBUG=0` в command line

## История изменений

- **2026-06-17:** Backup сделан (75 строк). Содержит 3 shim-блока: kapital, research-agent, telegram_bot, kb.
- **2026-06-10:** Более старые бэкапы в `newton-api.py.bak.20260610_131933` на VPS.
