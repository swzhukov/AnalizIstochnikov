#!/usr/bin/env bash
# install.sh — установка/обновление newton-api v6.0.1
# Использование: bash install.sh
#
# Безопасно перезапускает Flask. Бэкапит текущую версию.
# Очищает __pycache__ (LESSONS §2.6).
# Использует PID-файл + SIGTERM (LESSONS §2.3), НЕ pkill -9 -f.

set -euo pipefail

APP_DIR="/opt/beget/n8n/research-agent"
DEPLOY_DIR="$APP_DIR/deploy"
SERVICE_NAME="newton-api"
PID_FILE="/run/${SERVICE_NAME}.pid"

cd "$(dirname "$0")/.."

# ============================================================
# 1. Проверки (pre-flight)
# ============================================================
echo "=== 1. PRE-FLIGHT ==="
for cmd in python3 systemctl ss; do
  command -v $cmd >/dev/null || { echo "❌ $cmd не найден"; exit 1; }
done
[ -d "$APP_DIR" ] || { echo "❌ $APP_DIR не существует"; exit 1; }
[ -f "$APP_DIR/core/app.py" ] || { echo "❌ core/app.py не найден — структура сломана"; exit 1; }

ENV_FILE="/opt/beget/n8n/.env"
[ -f "$ENV_FILE" ] || { echo "❌ $ENV_FILE не найден"; exit 1; }

# Проверка обязательных переменных (без них Flask стартанёт, но эндпоинты вернут 500)
required_vars="NEWTON_TOKEN TELEGRAM_BOT_TOKEN YOUTUBE_API_KEY YANDEX_GPT_API_KEY YANDEX_GPT_FOLDER_ID ALLOWED_TELEGRAM_USERS"
missing=()
for v in $required_vars; do
  if ! grep -qE "^${v}=" "$ENV_FILE"; then
    missing+=("$v")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "⚠️  ВНИМАНИЕ: в $ENV_FILE отсутствуют переменные: ${missing[*]}"
  echo "   Без них часть эндпоинтов вернёт 500. Продолжить? (y/n)"
  read -r ans
  [ "$ans" = "y" ] || exit 1
fi
echo "✅ pre-flight OK"

# ============================================================
# 2. Бэкап текущей версии
# ============================================================
echo "=== 2. BACKUP ==="
BACKUP_DIR="/opt/beget/n8n/backups/research-agent"
mkdir -p "$BACKUP_DIR"
TS=$(date +%Y%m%d_%H%M%S)
if [ -f "/opt/beget/n8n/newton-api.py" ]; then
  cp /opt/beget/n8n/newton-api.py "$BACKUP_DIR/newton-api_$TS.py"
  echo "✅ бэкап: $BACKUP_DIR/newton-api_$TS.py"
fi
if [ -d "$APP_DIR" ]; then
  tar -czf "$BACKUP_DIR/research-agent_$TS.tar.gz" -C "$(dirname $APP_DIR)" "$(basename $APP_DIR)" 2>/dev/null
  echo "✅ бэкап: $BACKUP_DIR/research-agent_$TS.tar.gz"
fi
# keep last 5 backups
ls -t $BACKUP_DIR/newton-api_*.py 2>/dev/null | tail -n +6 | xargs -r rm -f
ls -t $BACKUP_DIR/research-agent_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm -f

# ============================================================
# 3. Очистка __pycache__ (LESSONS §2.6)
# ============================================================
echo "=== 3. CLEAR __pycache__ ==="
find "$APP_DIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find "$APP_DIR" -name "*.pyc" -delete 2>/dev/null
echo "✅ __pycache__ очищен"

# ============================================================
# 4. Остановка текущего процесса (по PID-файлу, не pkill -f)
# ============================================================
echo "=== 4. STOP OLD ==="
if systemctl is-active --quiet $SERVICE_NAME 2>/dev/null; then
  echo "  останавливаю systemd unit..."
  sudo systemctl stop $SERVICE_NAME
  sleep 2
fi
# Fallback: kill по PID-файлу
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE" 2>/dev/null || echo "")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "  посылаю SIGTERM PID=$OLD_PID"
    kill -TERM "$OLD_PID" 2>/dev/null
    for i in 1 2 3 4 5; do
      sleep 1
      kill -0 "$OLD_PID" 2>/dev/null || break
    done
    if kill -0 "$OLD_PID" 2>/dev/null; then
      echo "  SIGTERM не помог → SIGKILL"
      kill -KILL "$OLD_PID" 2>/dev/null
    fi
  fi
  rm -f "$PID_FILE"
fi
# Last resort: kill by port 8080
PORT_PID=$(ss -tlnp 2>/dev/null | grep ':8080 ' | grep -oP 'pid=\K[0-9]+' | head -1)
if [ -n "$PORT_PID" ]; then
  echo "  порт 8080 занят PID=$PORT_PID, убиваю"
  kill -TERM "$PORT_PID" 2>/dev/null
  sleep 2
  kill -0 "$PORT_PID" 2>/dev/null && kill -KILL "$PORT_PID" 2>/dev/null
fi
sleep 1
# Verify port is free
if ss -tln | grep -q ':8080 '; then
  echo "❌ порт 8080 всё ещё занят:"
  ss -tlnp | grep ':8080'
  exit 1
fi
echo "✅ старый процесс остановлен, порт 8080 свободен"

# ============================================================
# 5. Установка systemd unit
# ============================================================
echo "=== 5. SYSTEMD UNIT ==="
if [ -f "$DEPLOY_DIR/newton-api.service" ]; then
  sudo cp "$DEPLOY_DIR/newton-api.service" /etc/systemd/system/${SERVICE_NAME}.service
  sudo systemctl daemon-reload
  sudo systemctl enable $SERVICE_NAME
  echo "✅ systemd unit установлен"
else
  echo "  systemd unit не найден, запускаем напрямую"
  USE_SYSTEMD=0
fi

# ============================================================
# 6. Запуск
# ============================================================
echo "=== 6. START ==="
if [ -f /etc/systemd/system/${SERVICE_NAME}.service ]; then
  sudo systemctl start $SERVICE_NAME
  sleep 3
  if systemctl is-active --quiet $SERVICE_NAME; then
    echo "✅ запущен через systemd"
  else
    echo "❌ systemd start не удался, логи:"
    sudo journalctl -u $SERVICE_NAME -n 20 --no-pager
    exit 1
  fi
else
  # Fallback: nohup
  cd "$APP_DIR"
  nohup python3 core/app.py > /opt/beget/n8n/api.log 2>&1 &
  echo $! > "$PID_FILE"
  sleep 3
  if kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
    echo "✅ запущен через nohup, PID=$(cat $PID_FILE)"
  else
    echo "❌ nohup start не удался, логи:"
    tail -30 /opt/beget/n8n/api.log
    exit 1
  fi
fi

# ============================================================
# 7. Smoke test
# ============================================================
echo "=== 7. SMOKE TEST ==="
sleep 1
HEALTH=$(curl -s --max-time 5 http://localhost:8080/health_full)
if [ -z "$HEALTH" ]; then
  echo "❌ /health_full не отвечает"
  tail -30 /opt/beget/n8n/api.log
  exit 1
fi
echo "✅ /health_full: $HEALTH" | head -c 500
echo
echo
echo "=== INSTALL COMPLETE ==="
echo "Следующие шаги:"
echo "  1. Найди свой Telegram user_id: напиши @userinfobot"
echo "  2. Добавь в /opt/beget/n8n/.env: ALLOWED_TELEGRAM_USERS=<твой_id>"
echo "  3. Перезапусти: sudo systemctl restart $SERVICE_NAME"
echo "  4. Импортируй workflow v1.1 в n8n"
echo "  5. Отправь боту YouTube URL"
