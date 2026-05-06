#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.prod.yml"
ACTION="${1:-status}"
DOCKER_COMPOSE=(docker compose -f "$COMPOSE_FILE")

CLASSIC_BUILDER="${WANXIANG_CLASSIC_BUILDER:-${ZHIMO_CLASSIC_BUILDER:-1}}"
DOCKER_ENV=()
if [ "$CLASSIC_BUILDER" = "1" ]; then
  DOCKER_ENV=(DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0)
fi

REQUIRED_VARS=(
  SECRET_KEY
  MONGODB_URI
  CELERY_BROKER_URL
  CELERY_RESULT_BACKEND
  FRONTEND_ORIGIN
  WANXIANG_ALLOWED_ORIGINS
  CHATBACKEND_BASE_URL
  FRONTEND_API_BASE_URL
)
OPTIONAL_WARN_VARS=(
  GOOGLE_API_KEY
  TAVILY_API_KEY
  FEISHU_APP_ID
  FEISHU_APP_SECRET
  QQ_APP_ID
  QQ_APP_SECRET
  ELEVENLABS_API_KEY
  DASHSCOPE_API_KEY
)

FAILED_ITEMS=()
WARN_ITEMS=()
OK_ITEMS=()

print_usage() {
  cat <<'EOF'
Usage:
  scripts/server/wanxiang-server.sh <bootstrap|doctor|build|start|deploy|status>

Commands:
  bootstrap  Install host dependencies, enable Docker, and ensure swap exists
  doctor     Generate/check .env and print deployment readiness issues
  build      Build production images serially: backend -> frontend_api -> nginx
  start      Start services in dependency order and wait for health
  deploy     Run bootstrap -> doctor -> build -> start
  status     Show docker compose status and local probe results
EOF
}

print_line() {
  printf '%s\n' "------------------------------------------------------------"
}

print_step() {
  printf '\n==> %s\n' "$1"
}

record_ok() {
  OK_ITEMS+=("$1")
  printf '[OK] %s\n' "$1"
}

record_warn() {
  WARN_ITEMS+=("$1")
  printf '[WARN] %s\n' "$1"
}

record_fail() {
  FAILED_ITEMS+=("$1")
  printf '[FAIL] %s\n' "$1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run_compose() {
  "${DOCKER_COMPOSE[@]}" "$@"
}

run_compose_build() {
  env "${DOCKER_ENV[@]}" "${DOCKER_COMPOSE[@]}" build "$@"
}

ensure_root_dir() {
  cd "$ROOT_DIR"
}

sudo_cmd() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

ensure_template_env() {
  if [ -f "$ROOT_DIR/.env" ]; then
    return 0
  fi

  local template=""
  for candidate in \
    "$ROOT_DIR/.env.server.recommended.example" \
    "$ROOT_DIR/.env.server.example" \
    "$ROOT_DIR/.env.example"; do
    if [ -f "$candidate" ]; then
      template="$candidate"
      break
    fi
  done

  if [ -z "$template" ]; then
    record_fail "未找到可用环境变量模板（.env.server.recommended.example / .env.server.example / .env.example）"
    return 1
  fi

  cp "$template" "$ROOT_DIR/.env"
  record_warn "未检测到 .env，已基于 $(basename "$template") 自动生成；请补齐真实密钥后重新运行 doctor"
  return 0
}

env_value() {
  local key="$1"
  local legacy_key=""
  local file="$ROOT_DIR/.env"
  if [ ! -f "$file" ]; then
    return 1
  fi
  local value=""
  value="$(grep -E "^${key}=" "$file" | tail -n 1 | cut -d '=' -f 2-)"
  if [ -n "$value" ]; then
    printf '%s\n' "$value"
    return 0
  fi
  case "$key" in
    WANXIANG_*)
      legacy_key="ZHIMO_${key#WANXIANG_}"
      ;;
  esac
  if [ -n "$legacy_key" ]; then
    grep -E "^${legacy_key}=" "$file" | tail -n 1 | cut -d '=' -f 2-
  fi
}

is_placeholder_value() {
  local value="$1"
  if [ -z "$value" ]; then
    return 0
  fi
  case "$value" in
    replace-with-*|your-*|example*|changeme*|todo*|TODO*|"<"*">")
      return 0
      ;;
  esac
  if printf '%s' "$value" | grep -Eq 'replace-with|your-|example\.com|wanxiang\.example\.com|你的真实|一串随机|示例|占位'; then
    return 0
  fi
  return 1
}

check_duplicate_keys() {
  local file="$ROOT_DIR/.env"
  local duplicates=""
  duplicates="$(awk -F= '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    /^[A-Za-z_][A-Za-z0-9_]*=/ { count[$1]++ }
    END {
      for (k in count) {
        if (count[k] > 1) print k ":" count[k]
      }
    }
  ' "$file" | sort)"

  if [ -z "$duplicates" ]; then
    record_ok ".env 未发现重复键"
    return 0
  fi

  while IFS= read -r item; do
    [ -z "$item" ] && continue
    record_fail ".env 存在重复键: $item"
  done <<<"$duplicates"
  return 1
}

check_required_envs() {
  local key value
  for key in "${REQUIRED_VARS[@]}"; do
    value="$(env_value "$key" || true)"
    if is_placeholder_value "$value"; then
      record_fail "$key 缺失或仍是占位值"
    else
      record_ok "$key 已配置"
    fi
  done

  local qwen_key openrouter_key deepseek_key
  qwen_key="$(env_value QWEN_API_KEY || true)"
  openrouter_key="$(env_value OPENROUTER_API_KEY || true)"
  deepseek_key="$(env_value DEEPSEEK_API_KEY || true)"
  if is_placeholder_value "$qwen_key" && is_placeholder_value "$openrouter_key" && is_placeholder_value "$deepseek_key"; then
    record_fail "至少需要配置一组模型 Provider Key，默认建议填写 QWEN_API_KEY"
  else
    record_ok "已检测到至少一组模型 Provider Key"
  fi

  for key in "${OPTIONAL_WARN_VARS[@]}"; do
    value="$(env_value "$key" || true)"
    if is_placeholder_value "$value"; then
      record_warn "$key 未配置（可选能力）"
    else
      record_ok "$key 已配置（可选能力）"
    fi
  done
}

check_host_tools() {
  local missing=0
  if has_cmd docker; then
    record_ok "已检测到 docker"
  else
    record_fail "缺少 docker"
    missing=1
  fi

  if docker compose version >/dev/null 2>&1; then
    record_ok "已检测到 docker compose v2"
  else
    record_fail "缺少 docker compose v2"
    missing=1
  fi

  if has_cmd docker && ! docker info >/dev/null 2>&1; then
    record_fail "Docker daemon 未运行或当前用户无权访问 Docker"
    missing=1
  elif has_cmd docker; then
    record_ok "Docker daemon 运行正常"
  fi

  if has_cmd curl; then
    record_ok "已检测到 curl"
  else
    record_fail "缺少 curl"
    missing=1
  fi

  if has_cmd ss; then
    record_ok "已检测到 ss"
  else
    record_warn "未检测到 ss，端口占用检查会受限"
  fi

  return "$missing"
}

check_system_resources() {
  local available_kb total_kb swap_total_mb disk_avail_mb
  available_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
  total_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
  swap_total_mb="$(free -m | awk '/^Swap:/ {print $2}')"
  disk_avail_mb="$(df -Pm "$ROOT_DIR" | awk 'NR==2 {print $4}')"

  if [ -n "$total_kb" ] && [ "$total_kb" -gt 0 ]; then
    record_ok "内存概览: $(printf '%.1f' "$(awk "BEGIN {print $total_kb/1024/1024}")") GiB 总量"
  fi

  if [ -n "$available_kb" ] && [ "$available_kb" -lt 524288 ]; then
    record_warn "当前可用内存低于 512 MiB，构建镜像时可能明显变慢"
  else
    record_ok "当前可用内存可接受"
  fi

  if [ -n "$swap_total_mb" ] && [ "$swap_total_mb" -ge 4096 ]; then
    record_ok "Swap 已达到推荐值（>= 4 GiB）"
  elif [ -n "$swap_total_mb" ] && [ "$swap_total_mb" -gt 0 ]; then
    record_warn "Swap 已配置但低于推荐值（当前 ${swap_total_mb} MiB，建议 4096 MiB）"
  else
    record_warn "未检测到 swap，2C2G 机器上建议配置 4 GiB"
  fi

  if [ -n "$disk_avail_mb" ] && [ "$disk_avail_mb" -lt 5120 ]; then
    record_warn "磁盘剩余空间不足 5 GiB，镜像构建可能失败"
  else
    record_ok "磁盘剩余空间可接受"
  fi
}

check_port_80() {
  if ! has_cmd ss; then
    return 0
  fi

  local listeners
  listeners="$(ss -ltnp 2>/dev/null | awk '$4 ~ /:80$/ {print}')"
  if [ -z "$listeners" ]; then
    record_ok "宿主机 80 端口当前空闲"
    return 0
  fi

  if printf '%s\n' "$listeners" | grep -q 'nginx'; then
    record_warn "80 端口被系统 nginx 占用，启动容器 nginx 前需先停掉系统 nginx/apache"
  else
    record_warn "80 端口已被其他进程占用，启动容器 nginx 前需先释放端口"
  fi
}

print_security_group_hint() {
  record_warn "安全组需要人工确认已放行 22/TCP 与 80/TCP；脚本无法在服务器内自动检查云控制台配置"
}

print_summary() {
  print_line
  printf '通过项: %s\n' "${#OK_ITEMS[@]}"
  printf '告警项: %s\n' "${#WARN_ITEMS[@]}"
  printf '失败项: %s\n' "${#FAILED_ITEMS[@]}"
  if [ "${#FAILED_ITEMS[@]}" -gt 0 ]; then
    print_line
    printf '需修复的问题:\n'
    local item
    for item in "${FAILED_ITEMS[@]}"; do
      printf '  - %s\n' "$item"
    done
  fi
}

bootstrap() {
  ensure_root_dir
  print_step "安装服务器基础依赖"
  sudo_cmd apt-get update
  sudo_cmd apt-get install -y software-properties-common
  if has_cmd add-apt-repository; then
    sudo_cmd add-apt-repository -y universe
    sudo_cmd apt-get update
  fi
  sudo_cmd apt-get install -y software-properties-common docker.io docker-compose-v2 git curl
  sudo_cmd systemctl enable --now docker
  record_ok "Docker 与 docker compose v2 已安装并启动"

  print_step "检查 swap"
  if swapon --show | grep -q '/swapfile'; then
    record_ok "已检测到 /swapfile swap"
  else
    if [ -f /swapfile ]; then
      sudo_cmd chmod 600 /swapfile
      if ! sudo_cmd swapon /swapfile; then
        sudo_cmd mkswap /swapfile
        sudo_cmd swapon /swapfile
      fi
    else
      if has_cmd fallocate; then
        sudo_cmd fallocate -l 4G /swapfile
      else
        sudo_cmd dd if=/dev/zero of=/swapfile bs=1M count=4096
      fi
      sudo_cmd chmod 600 /swapfile
      sudo_cmd mkswap /swapfile
      sudo_cmd swapon /swapfile
    fi
    if ! grep -q '^/swapfile ' /etc/fstab; then
      echo '/swapfile none swap sw 0 0' | sudo_cmd tee -a /etc/fstab >/dev/null
    fi
    record_ok "已配置 4 GiB swap"
  fi

  print_step "检查 80 端口占用"
  check_port_80
  record_ok "bootstrap 完成"
}

doctor() {
  ensure_root_dir
  FAILED_ITEMS=()
  WARN_ITEMS=()
  OK_ITEMS=()

  print_step "准备 .env"
  if ensure_template_env; then
    record_ok "已找到 .env"
  fi

  print_step "检查宿主机工具"
  check_host_tools || true

  print_step "检查环境变量"
  if [ -f "$ROOT_DIR/.env" ]; then
    check_duplicate_keys || true
    check_required_envs
  fi

  print_step "检查系统资源与端口"
  check_system_resources
  check_port_80
  print_security_group_hint

  print_summary
  if [ "${#FAILED_ITEMS[@]}" -gt 0 ]; then
    return 1
  fi
  return 0
}

build_images() {
  ensure_root_dir
  print_step "串行构建 backend 镜像"
  run_compose_build backend
  print_step "串行构建 frontend_api 镜像"
  run_compose_build frontend_api
  print_step "串行构建 nginx 镜像"
  run_compose_build nginx

  print_step "镜像摘要"
  docker image ls --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' \
    | grep -E 'REPOSITORY|wanxiang-backend|wanxiang-frontend_api|wanxiang-nginx'
}

wait_for_health() {
  local container="$1"
  local timeout_seconds="$2"
  local interval=5
  local elapsed=0
  local status=""

  while [ "$elapsed" -lt "$timeout_seconds" ]; do
    status="$(docker inspect "$container" --format '{{if .State.Health}}{{.State.Health.Status}}{{else if .State.Running}}running{{else}}stopped{{end}}' 2>/dev/null || true)"
    if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
      printf '[OK] %s 状态: %s\n' "$container" "$status"
      return 0
    fi
    if [ "$status" = "unhealthy" ]; then
      printf '[FAIL] %s 状态: unhealthy\n' "$container"
      docker logs --tail=40 "$container" || true
      return 1
    fi
    printf '[WAIT] %s 当前状态: %s (%ss/%ss)\n' "$container" "${status:-missing}" "$elapsed" "$timeout_seconds"
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done

  printf '[FAIL] %s 在 %ss 内未达到可用状态\n' "$container" "$timeout_seconds"
  docker logs --tail=40 "$container" || true
  return 1
}

probe_url() {
  local label="$1"
  local url="$2"
  local require_success="${3:-1}"
  local code

  code="$(curl --noproxy '*' -sS --max-time 25 -o /tmp/wanxiang_probe.out -w '%{http_code}' "$url" || true)"
  if [ "$require_success" = "1" ]; then
    if [ "$code" = "200" ]; then
      printf '[OK] %s -> HTTP %s\n' "$label" "$code"
      return 0
    fi
    printf '[FAIL] %s -> HTTP %s\n' "$label" "${code:-curl-error}"
    cat /tmp/wanxiang_probe.out 2>/dev/null || true
    return 1
  fi

  if [ "$code" = "200" ]; then
    printf '[OK] %s -> HTTP %s\n' "$label" "$code"
  else
    printf '[WARN] %s -> HTTP %s（非阻塞）\n' "$label" "${code:-curl-error}"
  fi
  return 0
}

start_services() {
  ensure_root_dir
  if ! docker image inspect wanxiang-backend:latest >/dev/null 2>&1; then
    printf '[FAIL] 未找到 wanxiang-backend:latest，请先运行 build\n'
    return 1
  fi
  if ! docker image inspect wanxiang-frontend_api:latest >/dev/null 2>&1; then
    printf '[FAIL] 未找到 wanxiang-frontend_api:latest，请先运行 build\n'
    return 1
  fi
  if ! docker image inspect wanxiang-nginx:latest >/dev/null 2>&1; then
    printf '[FAIL] 未找到 wanxiang-nginx:latest，请先运行 build\n'
    return 1
  fi

  print_step "启动 redis 与 db"
  run_compose up -d redis db
  wait_for_health "redis_prod" 60
  wait_for_health "mongodb_prod" 180

  print_step "启动 backend"
  run_compose up -d backend
  wait_for_health "chat_backend_prod" 120

  print_step "启动 frontend_api"
  run_compose up -d frontend_api
  wait_for_health "frontend_api_prod" 120

  print_step "启动 celery worker / beat"
  run_compose up -d celeryworker celerybeat

  print_step "启动 nginx"
  run_compose up -d nginx
  wait_for_health "nginx_prod" 60

  print_step "执行启动后探针"
  probe_url "nginx healthz" "http://127.0.0.1/healthz"
  probe_url "frontend_api health" "http://127.0.0.1/api/health"
  probe_url "backend health" "http://127.0.0.1/backend-api/health"
  probe_url "assistant home" "http://127.0.0.1/api/assistant/home" 0

  print_step "当前容器状态"
  run_compose ps
}

status() {
  ensure_root_dir
  print_step "docker compose 状态"
  run_compose ps || true

  print_step "本机探针"
  probe_url "nginx healthz" "http://127.0.0.1/healthz" 0
  probe_url "frontend_api health" "http://127.0.0.1/api/health" 0
  probe_url "backend health" "http://127.0.0.1/backend-api/health" 0
  probe_url "assistant home" "http://127.0.0.1/api/assistant/home" 0
}

deploy() {
  bootstrap
  doctor
  build_images
  start_services
}

case "$ACTION" in
  bootstrap)
    bootstrap
    ;;
  doctor)
    doctor
    ;;
  build)
    build_images
    ;;
  start)
    start_services
    ;;
  deploy)
    deploy
    ;;
  status)
    status
    ;;
  *)
    print_usage
    exit 1
    ;;
esac
