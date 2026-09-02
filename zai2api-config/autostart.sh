#!/bin/bash
# zai2api 自动启动 - codespace 重启/重建后自动恢复
# 幂等：用 flock 防重复启动
# 配置：~/.zai2api-config/.env.gpg (gpg 对称加密)
# 密码：从 ~/.zai2api-config/.passphrase 读（600 权限，仅 root/codespace 可读）

LOCK=/tmp/zai2api-start.lock
(
  flock -n 9 || { echo "[zai2api-autostart] 已在运行，跳过"; exit 0; }

  CONFIG_DIR="/home/codespace/.zai2api-config"
  ENV_GPG="$CONFIG_DIR/.env.gpg"
  ENV_PLAIN="/tmp/zai2api-runtime.env"
  PASS_FILE="$CONFIG_DIR/.passphrase"
  IMAGE="zai2api:latest"

  # 0. 密码文件 / 加密配置存在性
  if [ ! -f "$ENV_GPG" ]; then
    echo "[zai2api-autostart] ⚠️ $ENV_GPG 不存在（codespace 重建？）"
    echo "[zai2api-autostart] 需要手动恢复 token，见 ~/.zai2api-config/RESTORE.md"
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/RESTORE.md" <<'EOF'
# 恢复 zai2api

.env.gpg 文件丢了（codespace 重建后 home 目录被清）。

## 步骤：
1. 登录 chat.z.ai → F12 → Application → Local Storage → 复制 JWT
2. 创建明文 ~/.zai2api-config/.env：
   ```
   AUTH_TOKEN=d3vin
   ZAI_TOKEN=eyJ...   ← 你的 JWT
   TOKEN_BATCH=150
   TOKEN_TARGET=750
   TOKEN_LOWWATER=50
   ```
3. 设置密码并加密：
   ```bash
   echo -n '你的密码' > ~/.zai2api-config/.passphrase
   chmod 600 ~/.zai2api-config/.passphrase
   gpg --batch --yes --symmetric --cipher-algo AES256 \
       --passphrase-file ~/.zai2api-config/.passphrase \
       -o ~/.zai2api-config/.env.gpg ~/.zai2api-config/.env
   shred -u ~/.zai2api-config/.env
   ```
4. bash ~/.zai2api-autostart.sh

EOF
    chmod 600 "$CONFIG_DIR/RESTORE.md"
    exit 0
  fi

  if [ ! -f "$PASS_FILE" ]; then
    echo "[zai2api-autostart] ⚠️ $PASS_FILE 不存在"
    echo "[zai2api-autostart] 创建密码文件: echo -n '你的密码' > ~/.zai2api-config/.passphrase && chmod 600 ~/.zai2api-config/.passphrase"
    exit 0
  fi

  # 1. docker 在不在？
  if ! command -v docker >/dev/null 2>&1; then
    echo "[zai2api-autostart] docker 未安装，跳过"
    exit 0
  fi

  # 2. 镜像在不在？
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "[zai2api-autostart] ⚠️ 镜像 $IMAGE 不存在（codespace 重建？）"
    echo "[zai2api-autostart] 需要手动: cd /workspaces/zai2api && docker build -t zai2api:latest ."
    exit 0
  fi

  # 3. 容器已经在跑？
  if docker ps --format '{{.Names}}' | grep -q '^zai2api$'; then
    echo "[zai2api-autostart] 容器已在运行"
    exit 0
  fi

  # 4. 解密 .env.gpg → 运行时临时文件（insecure mode，0600，仅本进程可见）
  echo "[zai2api-autostart] 解密 .env.gpg ..."
  if ! gpg --batch --yes \
    --passphrase-file "$PASS_FILE" \
    -o "$ENV_PLAIN" \
    -d "$ENV_GPG" 2>&1; then
    echo "[zai2api-autostart] ❌ 解密失败"
    exit 1
  fi
  chmod 600 "$ENV_PLAIN"

  # 5. 启动容器
  docker rm -f zai2api >/dev/null 2>&1
  echo "[zai2api-autostart] 启动 zai2api 容器..."
  docker run -d --name zai2api --restart unless-stopped \
    -p 8080:8080 \
    --env-file "$ENV_PLAIN" \
    -v zai2api-data:/data \
    "$IMAGE"

  # 6. 等就绪
  for i in 1 2 3 4 5 6 7 8; do
    sleep 2
    CODE=$(curl -s -m 2 -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer d3vin" \
        http://localhost:8080/v1/models 2>/dev/null)
    if [ "$CODE" = "200" ]; then
      echo "[zai2api-autostart] ✅ zai2api 就绪（耗时 ${i}*2s, HTTP $CODE）"
      echo "[zai2api-autostart] 运行时 env 文件保留在 $ENV_PLAIN，权限 600"
      exit 0
    fi
  done
  echo "[zai2api-autostart] ⚠️ 启动超时，查看 docker logs zai2api --tail 20"
) 9>"$LOCK"