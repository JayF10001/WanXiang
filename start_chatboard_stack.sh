#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env environment variables
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi
if [ -f "$ROOT_DIR/.env.local" ]; then
  set -a
  source "$ROOT_DIR/.env.local"
  set +a
fi
RUNTIME_DIR="$ROOT_DIR/.runtime"
BACKEND_PID_FILE="$RUNTIME_DIR/chatbackend.pid"
WORKER_PID_FILE="$RUNTIME_DIR/chatworker.pid"
FRONTEND_API_PID_FILE="$RUNTIME_DIR/frontend_api.pid"
FEISHU_ADAPTER_PID_FILE="$RUNTIME_DIR/feishu_adapter.pid"
BACKEND_LOG="$RUNTIME_DIR/chatbackend.log"
WORKER_LOG="$RUNTIME_DIR/chatworker.log"
FRONTEND_API_LOG="$RUNTIME_DIR/frontend_api.log"
FEISHU_ADAPTER_LOG="$RUNTIME_DIR/feishu_adapter.log"

mkdir -p "$RUNTIME_DIR"
cd "$ROOT_DIR"

ACTION="${1:-start}"

if [ ! -x "venv/bin/python" ]; then
  echo "未找到仓库根目录 venv，请先创建并安装 Python 依赖。"
  exit 1
fi

source venv/bin/activate
export PYTHONPATH="$ROOT_DIR"
export FLASK_DEBUG=0
export WANXIANG_BACKEND_DEBUG="${WANXIANG_BACKEND_DEBUG:-${ZHIMO_BACKEND_DEBUG:-0}}"
export WANXIANG_ALLOWED_ORIGINS="${WANXIANG_ALLOWED_ORIGINS:-${ZHIMO_ALLOWED_ORIGINS:-}}"
LOCAL_BACKEND_HOST="${LOCAL_BACKEND_HOST:-127.0.0.1}"
LOCAL_BACKEND_PORT="${LOCAL_BACKEND_PORT:-5000}"
LOCAL_FRONTEND_HOST="${LOCAL_FRONTEND_HOST:-127.0.0.1}"
LOCAL_FRONTEND_PORT="${LOCAL_FRONTEND_PORT:-3000}"
LOCAL_FRONTEND_API_HOST="${LOCAL_FRONTEND_API_HOST:-127.0.0.1}"
LOCAL_FRONTEND_API_PORT="${LOCAL_FRONTEND_API_PORT:-8001}"
LOCAL_FEISHU_ADAPTER_HOST="${LOCAL_FEISHU_ADAPTER_HOST:-127.0.0.1}"
LOCAL_FEISHU_ADAPTER_PORT="${LOCAL_FEISHU_ADAPTER_PORT:-8100}"
LOCAL_FRONTEND_API_BASE_URL="${LOCAL_FRONTEND_API_BASE_URL:-http://$LOCAL_FRONTEND_API_HOST:$LOCAL_FRONTEND_API_PORT/api}"
LOCAL_ALLOWED_ORIGINS="${LOCAL_ALLOWED_ORIGINS:-http://$LOCAL_FRONTEND_HOST:$LOCAL_FRONTEND_PORT,http://localhost:$LOCAL_FRONTEND_PORT,http://127.0.0.1:$LOCAL_FRONTEND_PORT}"

wait_for_death() {
  local name="$1"
  local pid="$2"
  local max_wait=5
  local waited=0

  while kill -0 "$pid" >/dev/null 2>&1; do
    if [ "$waited" -ge "$max_wait" ]; then
      return 1
    fi
    sleep 0.5
    waited=$((waited + 1))
  done
  return 0
}

stop_by_pid_file() {
  local name="$1"
  local pid_file="$2"

  if [ ! -f "$pid_file" ]; then
    echo "[停止] $name — 无 PID 记录"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "[停止] $name — PID=$pid 已不存在，清理记录"
    rm -f "$pid_file"
    return 0
  fi

  echo "[停止] $name — 发送 SIGTERM 到 PID=$pid ..."
  kill "$pid" >/dev/null 2>&1 || true

  if wait_for_death "$name" "$pid"; then
    echo "[停止] $name — PID=$pid 已终止（graceful）"
  else
    echo "[停止] $name — PID=$pid 未响应 SIGTERM，发送 SIGKILL ..."
    kill -9 "$pid" >/dev/null 2>&1 || true
    sleep 0.5
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "[停止] $name — 警告：PID=$pid 仍存在，请手动检查"
    else
      echo "[停止] $name — PID=$pid 已强制终止（SIGKILL）"
    fi
  fi

  rm -f "$pid_file"
}

free_port_if_needed() {
  local port="$1"
  local label="$2"
  local pids
  pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    echo "[端口] $label (:$port) — 空闲"
    return 0
  fi

  echo "[端口] $label (:$port) — 被占用 PIDs: $pids，发送 SIGTERM ..."
  for pid in $pids; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  sleep 1

  local remaining
  remaining="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [ -n "$remaining" ]; then
    echo "[端口] $label (:$port) — SIGTERM 无效，发送 SIGKILL 到: $remaining ..."
    for pid in $remaining; do
      kill -9 "$pid" >/dev/null 2>&1 || true
    done
    sleep 0.5
  fi

  remaining="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
  if [ -n "$remaining" ]; then
    echo "[端口] ⚠️ $label (:$port) — 仍有进程残留: $remaining，请手动检查"
  else
    echo "[端口] $label (:$port) — 已释放"
  fi
}

cleanup_celery_remnants() {
  local app_pids
  app_pids="$(ps aux | grep "celery.*ChatBackend.celery_app.*worker" | grep -v grep | awk '{print $2}' || true)"
  if [ -z "$app_pids" ]; then
    echo "[清理] Celery — 无残留进程"
    return 0
  fi

  echo "[清理] Celery — 发现残留进程: $app_pids，发送 SIGTERM ..."
  for pid in $app_pids; do
    kill "$pid" >/dev/null 2>&1 || true
  done
  sleep 1

  local remaining
  remaining="$(ps aux | grep "celery.*ChatBackend.celery_app.*worker" | grep -v grep | awk '{print $2}' || true)"
  if [ -n "$remaining" ]; then
    echo "[清理] Celery — SIGTERM 无效，发送 SIGKILL 到: $remaining ..."
    for pid in $remaining; do
      kill -9 "$pid" >/dev/null 2>&1 || true
    done
    sleep 0.5
  fi

  remaining="$(ps aux | grep "celery.*ChatBackend.celery_app.*worker" | grep -v grep | awk '{print $2}' || true)"
  if [ -n "$remaining" ]; then
    echo "[清理] ⚠️ Celery — 仍有残留: $remaining，请手动检查"
  else
    echo "[清理] Celery — 残留进程已清除"
  fi
}

print_status() {
  local services=(
    "Flask backend|$BACKEND_PID_FILE|5000"
    "Celery worker|$WORKER_PID_FILE|"
    "frontend_api|$FRONTEND_API_PID_FILE|8001"
    "feishu_adapter|$FEISHU_ADAPTER_PID_FILE|8100"
  )

  for entry in "${services[@]}"; do
    IFS='|' read -r name pid_file port <<<"$entry"
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
      echo "$name 运行中，PID=$(cat "$pid_file")${port:+，端口:$port}"
    else
      echo "$name 未运行${port:+，端口:$port}"
    fi
  done
}

start_if_needed() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  shift 3

  if [ -f "$pid_file" ]; then
    local existing_pid
    existing_pid="$(cat "$pid_file")"
    if kill -0 "$existing_pid" >/dev/null 2>&1; then
      echo "$name 已在运行，PID=$existing_pid"
      return 0
    fi
    rm -f "$pid_file"
  fi

  nohup "$@" >>"$log_file" 2>&1 &
  local new_pid=$!
  echo "$new_pid" >"$pid_file"
  echo "已启动 $name，PID=$new_pid，日志: $log_file"
}

case "$ACTION" in
  start)
    echo ""
    echo "========== 启动服务（不杀旧进程） =========="
    echo "提示：若需重启请用 restart 命令"
    echo ""
    start_if_needed \
      "Flask backend (:5000)" \
      "$BACKEND_PID_FILE" \
      "$BACKEND_LOG" \
      env FLASK_DEBUG=0 WANXIANG_BACKEND_DEBUG=0 PYTHONPATH="$ROOT_DIR" venv/bin/python -u ChatBackend/wsgi.py

    start_if_needed \
      "Celery worker" \
      "$WORKER_PID_FILE" \
      "$WORKER_LOG" \
      env PYTHONPATH="$ROOT_DIR" venv/bin/celery -A ChatBackend.celery_app worker --loglevel=info

    start_if_needed \
      "frontend_api (:8001)" \
      "$FRONTEND_API_PID_FILE" \
      "$FRONTEND_API_LOG" \
      env CHATBACKEND_BASE_URL="${CHATBACKEND_BASE_URL:-http://$LOCAL_BACKEND_HOST:$LOCAL_BACKEND_PORT}" FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-http://$LOCAL_FRONTEND_HOST:$LOCAL_FRONTEND_PORT}" WANXIANG_ALLOWED_ORIGINS="${WANXIANG_ALLOWED_ORIGINS:-$LOCAL_ALLOWED_ORIGINS}" FRONTEND_API_HOST="${FRONTEND_API_HOST:-$LOCAL_FRONTEND_API_HOST}" FRONTEND_API_PORT="${FRONTEND_API_PORT:-$LOCAL_FRONTEND_API_PORT}" venv/bin/uvicorn frontend_api.main:app --host "${FRONTEND_API_HOST:-$LOCAL_FRONTEND_API_HOST}" --port "${FRONTEND_API_PORT:-$LOCAL_FRONTEND_API_PORT}"

    start_if_needed \
      "feishu_adapter (:8100)" \
      "$FEISHU_ADAPTER_PID_FILE" \
      "$FEISHU_ADAPTER_LOG" \
      env FRONTEND_API_BASE_URL="${FRONTEND_API_BASE_URL:-$LOCAL_FRONTEND_API_BASE_URL}" FEISHU_FRONTEND_API_BASE_URL="${FEISHU_FRONTEND_API_BASE_URL:-${FRONTEND_API_BASE_URL:-$LOCAL_FRONTEND_API_BASE_URL}}" FEISHU_ADAPTER_HOST="${FEISHU_ADAPTER_HOST:-$LOCAL_FEISHU_ADAPTER_HOST}" FEISHU_ADAPTER_PORT="${FEISHU_ADAPTER_PORT:-$LOCAL_FEISHU_ADAPTER_PORT}" venv/bin/uvicorn feishu_adapter.main:app --host "${FEISHU_ADAPTER_HOST:-$LOCAL_FEISHU_ADAPTER_HOST}" --port "${FEISHU_ADAPTER_PORT:-$LOCAL_FEISHU_ADAPTER_PORT}"
    ;;
  stop)
    echo ""
    echo "========== 停止服务 =========="
    stop_by_pid_file "feishu_adapter" "$FEISHU_ADAPTER_PID_FILE"
    stop_by_pid_file "frontend_api" "$FRONTEND_API_PID_FILE"
    stop_by_pid_file "Celery worker" "$WORKER_PID_FILE"
    stop_by_pid_file "Flask backend" "$BACKEND_PID_FILE"

    echo ""
    echo "========== 清理残留 =========="
    cleanup_celery_remnants
    free_port_if_needed 8100 "feishu_adapter"
    free_port_if_needed 8001 "frontend_api"
    free_port_if_needed 5000 "Flask backend"
    exit 0
    ;;
  restart)
    echo ""
    echo "========== 停止旧进程 =========="
    stop_by_pid_file "feishu_adapter" "$FEISHU_ADAPTER_PID_FILE"
    stop_by_pid_file "frontend_api" "$FRONTEND_API_PID_FILE"
    stop_by_pid_file "Celery worker" "$WORKER_PID_FILE"
    stop_by_pid_file "Flask backend" "$BACKEND_PID_FILE"

    echo ""
    echo "========== 清理残留 =========="
    cleanup_celery_remnants
    free_port_if_needed 8100 "feishu_adapter"
    free_port_if_needed 8001 "frontend_api"
    free_port_if_needed 5000 "Flask backend"

    echo ""
    echo "========== 验证停止结果 =========="
    all_dead=true
    if ps aux | grep -v grep | grep -q "ChatBackend/wsgi.py"; then
      echo "[验证] ⚠️ Flask backend 仍在运行"
      all_dead=false
    else
      echo "[验证] ✓ Flask backend 已停止"
    fi
    if ps aux | grep -v grep | grep -q "celery.*ChatBackend.celery_app.*worker"; then
      echo "[验证] ⚠️ Celery worker 仍有残留"
      all_dead=false
    else
      echo "[验证] ✓ Celery worker 已停止"
    fi
    if lsof -ti tcp:8001 >/dev/null 2>&1; then
      echo "[验证] ⚠️ frontend_api 端口 8001 仍被占用"
      all_dead=false
    else
      echo "[验证] ✓ frontend_api 端口 8001 已释放"
    fi
    if lsof -ti tcp:8100 >/dev/null 2>&1; then
      echo "[验证] ⚠️ feishu_adapter 端口 8100 仍被占用"
      all_dead=false
    else
      echo "[验证] ✓ feishu_adapter 端口 8100 已释放"
    fi
    if lsof -ti tcp:5000 >/dev/null 2>&1; then
      echo "[验证] ⚠️ Flask backend 端口 5000 仍被占用"
      all_dead=false
    else
      echo "[验证] ✓ Flask backend 端口 5000 已释放"
    fi

    if [ "$all_dead" = false ]; then
      echo ""
      echo "⚠️ 部分进程未完全停止，继续启动可能会失败，建议先手动清理"
    fi

    echo ""
    echo "========== 启动新进程 =========="
    start_if_needed \
      "Flask backend (:5000)" \
      "$BACKEND_PID_FILE" \
      "$BACKEND_LOG" \
      env FLASK_DEBUG=0 WANXIANG_BACKEND_DEBUG=0 PYTHONPATH="$ROOT_DIR" venv/bin/python -u ChatBackend/wsgi.py

    start_if_needed \
      "Celery worker" \
      "$WORKER_PID_FILE" \
      "$WORKER_LOG" \
      env PYTHONPATH="$ROOT_DIR" venv/bin/celery -A ChatBackend.celery_app worker --loglevel=info

    start_if_needed \
      "frontend_api (:8001)" \
      "$FRONTEND_API_PID_FILE" \
      "$FRONTEND_API_LOG" \
      env CHATBACKEND_BASE_URL="${CHATBACKEND_BASE_URL:-http://$LOCAL_BACKEND_HOST:$LOCAL_BACKEND_PORT}" FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-http://$LOCAL_FRONTEND_HOST:$LOCAL_FRONTEND_PORT}" WANXIANG_ALLOWED_ORIGINS="${WANXIANG_ALLOWED_ORIGINS:-$LOCAL_ALLOWED_ORIGINS}" FRONTEND_API_HOST="${FRONTEND_API_HOST:-$LOCAL_FRONTEND_API_HOST}" FRONTEND_API_PORT="${FRONTEND_API_PORT:-$LOCAL_FRONTEND_API_PORT}" venv/bin/uvicorn frontend_api.main:app --host "${FRONTEND_API_HOST:-$LOCAL_FRONTEND_API_HOST}" --port "${FRONTEND_API_PORT:-$LOCAL_FRONTEND_API_PORT}"

    start_if_needed \
      "feishu_adapter (:8100)" \
      "$FEISHU_ADAPTER_PID_FILE" \
      "$FEISHU_ADAPTER_LOG" \
      env FRONTEND_API_BASE_URL="${FRONTEND_API_BASE_URL:-$LOCAL_FRONTEND_API_BASE_URL}" FEISHU_FRONTEND_API_BASE_URL="${FEISHU_FRONTEND_API_BASE_URL:-${FRONTEND_API_BASE_URL:-$LOCAL_FRONTEND_API_BASE_URL}}" FEISHU_ADAPTER_HOST="${FEISHU_ADAPTER_HOST:-$LOCAL_FEISHU_ADAPTER_HOST}" FEISHU_ADAPTER_PORT="${FEISHU_ADAPTER_PORT:-$LOCAL_FEISHU_ADAPTER_PORT}" venv/bin/uvicorn feishu_adapter.main:app --host "${FEISHU_ADAPTER_HOST:-$LOCAL_FEISHU_ADAPTER_HOST}" --port "${FEISHU_ADAPTER_PORT:-$LOCAL_FEISHU_ADAPTER_PORT}"
    ;;
  status)
    print_status
    exit 0
    ;;
  *)
    echo "用法: ./start_chatboard_stack.sh [start|stop|restart|status]"
    exit 1
    ;;
esac

echo
echo "旧 chatboard 完整依赖已显式启动："
echo "- Flask backend: http://${LOCAL_BACKEND_HOST}:${LOCAL_BACKEND_PORT}"
echo "- Celery worker: strategy/report async tasks"
echo "- frontend_api: http://${LOCAL_FRONTEND_API_HOST}:${LOCAL_FRONTEND_API_PORT}"
echo "- feishu_adapter: http://${LOCAL_FEISHU_ADAPTER_HOST}:${LOCAL_FEISHU_ADAPTER_PORT}"
echo
echo "查看日志："
echo "- tail -f $BACKEND_LOG"
echo "- tail -f $WORKER_LOG"
echo "- tail -f $FRONTEND_API_LOG"
echo "- tail -f $FEISHU_ADAPTER_LOG"
