#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
FRONTEND_DIR="$ROOT_DIR/frontend_new"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend_new.pid"
FRONTEND_LOG="$RUNTIME_DIR/frontend_new.log"
BACKEND_PID_FILE="$RUNTIME_DIR/chatbackend.pid"
WORKER_PID_FILE="$RUNTIME_DIR/chatworker.pid"
FRONTEND_API_PID_FILE="$RUNTIME_DIR/frontend_api.pid"
FEISHU_ADAPTER_PID_FILE="$RUNTIME_DIR/feishu_adapter.pid"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
MONGO_HOST="${MONGO_HOST:-127.0.0.1}"
MONGO_PORT="${MONGO_PORT:-27017}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
AUTO_START_DEPS="${AUTO_START_DEPS:-1}"
LOCAL_FRONTEND_API_BASE="${LOCAL_FRONTEND_API_BASE:-/api}"

ACTION="${1:-start}"

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

export WANXIANG_ALLOWED_ORIGINS="${WANXIANG_ALLOWED_ORIGINS:-${ZHIMO_ALLOWED_ORIGINS:-}}"
export WANXIANG_BACKEND_DEBUG="${WANXIANG_BACKEND_DEBUG:-${ZHIMO_BACKEND_DEBUG:-}}"

mkdir -p "$RUNTIME_DIR"
cd "$ROOT_DIR"

print_check() {
  local level="$1"
  local message="$2"
  case "$level" in
    ok)
      echo "[OK] $message"
      ;;
    warn)
      echo "[WARN] $message"
      ;;
    fail)
      echo "[FAIL] $message"
      ;;
    *)
      echo "$message"
      ;;
  esac
}

check_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    print_check ok "已找到命令: $name"
    return 0
  fi
  print_check fail "缺少命令: $name"
  return 1
}

check_env_var() {
  local name="$1"
  local value="${!name:-}"
  if [ -n "$value" ]; then
    print_check ok "$name 已配置"
    return 0
  fi
  print_check fail "$name 未配置"
  return 1
}

doctor() {
  local failed=0

  echo "========== WanXiang 环境检查 =========="
  if [ -f "$ROOT_DIR/.env.local" ]; then
    print_check ok "检测到 .env.local"
  elif [ -f "$ROOT_DIR/.env" ]; then
    print_check ok "检测到 .env"
  else
    print_check fail "未找到 .env.local 或 .env，请先从 .env.example 复制"
    failed=1
  fi

  check_command python3 || failed=1
  check_command node || failed=1
  check_command npm || failed=1

  if [ -x "$ROOT_DIR/venv/bin/python" ]; then
    print_check ok "检测到仓库根目录 venv"
  else
    print_check warn "未检测到仓库根目录 venv，首次启动时 ./start.sh 会自动创建"
  fi

  echo
  echo "========== 必填环境变量 =========="
  check_env_var SECRET_KEY || failed=1
  if [ -n "${MONGODB_URI:-${MONGO_URI:-}}" ]; then
    print_check ok "MONGODB_URI/MONGO_URI 已配置"
  else
    print_check fail "MONGODB_URI 未配置"
    failed=1
  fi
  check_env_var CELERY_BROKER_URL || failed=1
  check_env_var CELERY_RESULT_BACKEND || failed=1
  check_env_var CHATBACKEND_BASE_URL || failed=1
  check_env_var FRONTEND_API_BASE_URL || failed=1
  check_env_var FRONTEND_ORIGIN || failed=1
  check_env_var WANXIANG_ALLOWED_ORIGINS || failed=1

  if [ -n "${QWEN_API_KEY:-}" ] || [ -n "${OPENROUTER_API_KEY:-}" ] || [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    print_check ok "至少检测到一组模型 Provider Key"
  else
    print_check warn "未检测到模型 Provider Key，聊天主链路大概率不可用"
  fi

  if [ "${VITE_FRONTEND_API_BASE:-/api}" = "/api" ]; then
    print_check ok "VITE_FRONTEND_API_BASE 使用同源 /api"
  else
    print_check warn "VITE_FRONTEND_API_BASE 当前不是 /api，本地开发时可能引发登录态/cookie 问题"
  fi

  echo
  echo "========== 本地依赖端口检查 =========="
  preflight_backend_dependencies || failed=1

  echo
  if [ "$failed" -ne 0 ]; then
    print_check fail "环境检查未通过。请补齐环境变量、本地依赖和 Python/Node 运行环境后重试。"
    return 1
  fi

  print_check ok "环境检查通过。下一步可执行: ./start.sh start"
  return 0
}

ensure_venv() {
  if [ -x "$ROOT_DIR/venv/bin/python" ]; then
    return 0
  fi

  echo "未检测到 venv，开始创建并安装 Python 依赖..."
  python3 -m venv "$ROOT_DIR/venv"
  "$ROOT_DIR/venv/bin/pip" install --upgrade pip setuptools wheel
  "$ROOT_DIR/venv/bin/pip" install \
    -r "$ROOT_DIR/ChatBackend/requirements.txt" \
    -r "$ROOT_DIR/frontend_api/requirements.txt" \
    -r "$ROOT_DIR/feishu_adapter/requirements.txt" \
    -r "$ROOT_DIR/wanxiang_mcp/requirements.txt"
}

ensure_nvm_node() {
  if [ -f "$HOME/.nvm/nvm.sh" ]; then
    local had_u=0
    case "$-" in
      *u*) had_u=1 ;;
    esac
    if [ "$had_u" -eq 1 ]; then
      set +u
    fi
    # shellcheck disable=SC1090
    source "$HOME/.nvm/nvm.sh"
    if [ -f "$FRONTEND_DIR/.nvmrc" ]; then
      (cd "$FRONTEND_DIR" && nvm use >/dev/null 2>&1) || true
    fi
    if [ "$had_u" -eq 1 ]; then
      set -u
    fi
  fi
}

check_local_dependency() {
  local name="$1"
  local host="$2"
  local port="$3"
  if python3 - <<PY >/dev/null 2>&1
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1.5)
s.connect(("$host", int("$port")))
s.close()
PY
  then
    echo "$name 就绪: $host:$port"
    return 0
  fi

  echo "$name 未就绪: $host:$port"
  return 1
}

preflight_backend_dependencies() {
  local failed=0
  check_local_dependency "MongoDB" "$MONGO_HOST" "$MONGO_PORT" || failed=1
  check_local_dependency "Redis" "$REDIS_HOST" "$REDIS_PORT" || failed=1
  if [ "$failed" -ne 0 ]; then
    echo "后端依赖未就绪，请先启动 MongoDB/Redis，再执行 ./start.sh start"
    return 1
  fi
  return 0
}

ensure_backend_dependencies() {
  if preflight_backend_dependencies; then
    return 0
  fi

  if [ "$AUTO_START_DEPS" != "1" ]; then
    return 1
  fi

  if [ ! -x "$ROOT_DIR/start_deps.sh" ]; then
    echo "未找到可执行的 ./start_deps.sh，无法自动拉起 MongoDB/Redis。"
    return 1
  fi

  echo "尝试自动启动 MongoDB/Redis..."
  "$ROOT_DIR/start_deps.sh" start
  sleep 2
  preflight_backend_dependencies
}

start_frontend() {
  if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat "$FRONTEND_PID_FILE")" >/dev/null 2>&1; then
    echo "frontend_new 已在运行，PID=$(cat "$FRONTEND_PID_FILE")"
    return 0
  fi

  rm -f "$FRONTEND_PID_FILE"
  ensure_nvm_node

  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "安装 frontend_new 依赖..."
    (
      cd "$FRONTEND_DIR"
      npm install --legacy-peer-deps
    )
  fi

  echo "启动 frontend_new..."
  nohup bash -lc "
    set -eo pipefail
    cd \"$FRONTEND_DIR\"
    unset npm_config_prefix
    if [ -f \"\$HOME/.nvm/nvm.sh\" ]; then
      set +u
      source \"\$HOME/.nvm/nvm.sh\"
      nvm use >/dev/null 2>&1 || true
      set -u
    fi
    export VITE_FRONTEND_API_BASE=\"${VITE_FRONTEND_API_BASE:-$LOCAL_FRONTEND_API_BASE}\"
    npm run dev -- --host=\"$FRONTEND_HOST\" --port=\"$FRONTEND_PORT\"
  " >>"$FRONTEND_LOG" 2>&1 &
  echo $! >"$FRONTEND_PID_FILE"

  sleep 2
  if kill -0 "$(cat "$FRONTEND_PID_FILE")" >/dev/null 2>&1; then
    echo "frontend_new 已启动，PID=$(cat "$FRONTEND_PID_FILE")，日志: $FRONTEND_LOG"
    return 0
  fi

  echo "frontend_new 启动失败，最近日志："
  tail -n 80 "$FRONTEND_LOG" || true
  rm -f "$FRONTEND_PID_FILE"
  return 1
}

stop_frontend() {
  if [ ! -f "$FRONTEND_PID_FILE" ]; then
    echo "frontend_new 未记录 PID"
    return 0
  fi

  local pid
  pid="$(cat "$FRONTEND_PID_FILE")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    echo "frontend_new 已停止，PID=$pid"
  else
    echo "frontend_new PID 无效，已清理记录"
  fi
  rm -f "$FRONTEND_PID_FILE"
}

status_frontend() {
  if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat "$FRONTEND_PID_FILE")" >/dev/null 2>&1; then
    echo "frontend_new 运行中，PID=$(cat "$FRONTEND_PID_FILE")，端口:$FRONTEND_PORT"
  else
    echo "frontend_new 未运行，端口:$FRONTEND_PORT"
  fi
}

pid_matches() {
  local pid_file="$1"
  local expected="$2"

  if [ ! -f "$pid_file" ]; then
    return 1
  fi

  local pid
  pid="$(cat "$pid_file")"
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return 1
  fi

  local cmdline
  cmdline="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  if [ -z "$cmdline" ]; then
    return 1
  fi
  if ! printf '%s' "$cmdline" | grep -Fq "$expected"; then
    return 1
  fi

  return 0
}

verify_backend_after_start() {
  sleep 6
  local failed=0

  if ! pid_matches "$BACKEND_PID_FILE" "ChatBackend/wsgi.py"; then
    echo "Flask backend 启动失败（:5000）"
    tail -n 80 "$RUNTIME_DIR/chatbackend.log" || true
    failed=1
  fi
  if ! pid_matches "$FRONTEND_API_PID_FILE" "frontend_api.main:app"; then
    echo "frontend_api 启动失败（:8001）"
    tail -n 80 "$RUNTIME_DIR/frontend_api.log" || true
    failed=1
  fi
  if ! pid_matches "$WORKER_PID_FILE" "ChatBackend.celery_app"; then
    echo "Celery worker 未就绪"
    tail -n 60 "$RUNTIME_DIR/chatworker.log" || true
  fi
  if ! pid_matches "$FEISHU_ADAPTER_PID_FILE" "feishu_adapter.main:app"; then
    echo "feishu_adapter 未就绪（:8100）"
    tail -n 60 "$RUNTIME_DIR/feishu_adapter.log" || true
  fi

  if [ "$failed" -ne 0 ]; then
    return 1
  fi
  return 0
}

case "$ACTION" in
  doctor)
    doctor
    ;;
  start)
    ensure_venv
    ensure_backend_dependencies
    ./start_chatboard_stack.sh start
    verify_backend_after_start
    start_frontend
    ;;
  stop)
    stop_frontend
    ./start_chatboard_stack.sh stop
    ;;
  restart)
    stop_frontend
    ensure_backend_dependencies
    ./start_chatboard_stack.sh restart
    verify_backend_after_start
    start_frontend
    ;;
  status)
    ./start_chatboard_stack.sh status
    status_frontend
    ;;
  *)
    echo "用法: ./start.sh [doctor|start|stop|restart|status]"
    echo "可选环境变量: AUTO_START_DEPS=1|0 (默认 1)"
    exit 1
    ;;
esac

if [ "$ACTION" = "start" ] || [ "$ACTION" = "restart" ]; then
  echo
  echo "服务入口："
  echo "- frontend_new: http://$FRONTEND_HOST:$FRONTEND_PORT"
  echo "- Flask backend: http://${LOCAL_BACKEND_HOST:-127.0.0.1}:${LOCAL_BACKEND_PORT:-5000}"
  echo "- frontend_api: ${VITE_FRONTEND_API_BASE:-$LOCAL_FRONTEND_API_BASE}"
  echo "- feishu_adapter: http://${FEISHU_ADAPTER_HOST:-127.0.0.1}:${FEISHU_ADAPTER_PORT:-8100}"
fi
