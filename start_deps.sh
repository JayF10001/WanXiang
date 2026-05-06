#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ACTION="${1:-start}"

MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27017}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "未找到 docker compose / docker-compose，请先安装 Docker。"
  exit 1
fi

compose() {
  "${COMPOSE[@]}" -f "$ROOT_DIR/$COMPOSE_FILE" "$@"
}

wait_port() {
  local name="$1"
  local host="$2"
  local port="$3"
  local retries="${4:-30}"

  for _ in $(seq 1 "$retries"); do
    if python3 - <<PY >/dev/null 2>&1
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
s.connect(("$host", int("$port")))
s.close()
PY
    then
      echo "$name 就绪: $host:$port"
      return 0
    fi
    sleep 1
  done

  echo "$name 启动超时: $host:$port"
  return 1
}

status_ports() {
  local ok=0
  if python3 - <<PY >/dev/null 2>&1
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
s.connect(("$MONGO_HOST", int("$MONGO_PORT")))
s.close()
PY
  then
    echo "MongoDB 端口可达: $MONGO_HOST:$MONGO_PORT"
  else
    echo "MongoDB 端口不可达: $MONGO_HOST:$MONGO_PORT"
    ok=1
  fi

  if python3 - <<PY >/dev/null 2>&1
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.0)
s.connect(("$REDIS_HOST", int("$REDIS_PORT")))
s.close()
PY
  then
    echo "Redis 端口可达: $REDIS_HOST:$REDIS_PORT"
  else
    echo "Redis 端口不可达: $REDIS_HOST:$REDIS_PORT"
    ok=1
  fi
  return "$ok"
}

case "$ACTION" in
  start)
    compose up -d db redis
    wait_port "MongoDB" "$MONGO_HOST" "$MONGO_PORT"
    wait_port "Redis" "$REDIS_HOST" "$REDIS_PORT"
    ;;
  stop)
    compose stop db redis
    ;;
  restart)
    compose stop db redis || true
    compose up -d db redis
    wait_port "MongoDB" "$MONGO_HOST" "$MONGO_PORT"
    wait_port "Redis" "$REDIS_HOST" "$REDIS_PORT"
    ;;
  status)
    compose ps db redis || true
    status_ports
    ;;
  *)
    echo "用法: ./start_deps.sh [start|stop|restart|status]"
    exit 1
    ;;
esac
