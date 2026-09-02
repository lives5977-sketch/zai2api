#!/bin/bash
# zai2api codespace 恢复脚本
# 场景：codespace 重建后 /etc/profile.d/ 和 ~/.zai2api-config/ 都被清
#        但 /workspaces/.codespaces/.persistedshare/zai2api-config/ 还在
#        token / 加密 env / zai2api 镜像 也都还在
# 跑一次这个脚本 = codespace 回到完整工作状态

set -e

CONFIG_DIR="$HOME/.zai2api-config"
PERSIST_DIR="/workspaces/.codespaces/.persistedshare/zai2api-config"
PROFILE_D="/etc/profile.d/zai2api-autostart.sh"
AUTOSTART="$HOME/.zai2api-autostart.sh"
REPO_PROFILE="/workspaces/zai2api/zai2api-config/profile.sh"
REPO_AUTOSTART="/workspaces/zai2api/zai2api-config/autostart.sh"

echo "[setup] 恢复 zai2api codespace 配置..."

# 1. 软链配置目录（codespace 清了 home，但持久化目录还在）
if [ ! -e "$CONFIG_DIR" ]; then
  if [ -d "$PERSIST_DIR" ]; then
    ln -s "$PERSIST_DIR" "$CONFIG_DIR"
    echo "[setup] ✅ 软链 $CONFIG_DIR -> $PERSIST_DIR"
  else
    echo "[setup] ❌ $PERSIST_DIR 不存在 — 需要重新填 token"
    echo "[setup]    1. 登录 chat.z.ai -> F12 -> Application -> Local Storage -> 复制 JWT"
    echo "[setup]    2. 编辑 $PERSIST_DIR/.env（AUTH_TOKEN=d3vin / ZAI_TOKEN=<JWT>）"
    echo "[setup]    3. 编辑 $PERSIST_DIR/.passphrase（一行密码）"
    mkdir -p "$PERSIST_DIR"
    exit 1
  fi
else
  echo "[setup] ✓ $CONFIG_DIR 已存在"
fi

# 2. 恢复 autostart 脚本到 home
if [ ! -f "$AUTOSTART" ] && [ -f "$REPO_AUTOSTART" ]; then
  cp "$REPO_AUTOSTART" "$AUTOSTART"
  chmod +x "$AUTOSTART"
  echo "[setup] ✅ 恢复 $AUTOSTART"
fi

# 3. 恢复 /etc/profile.d/ hook（codespace 重建会清）
if [ ! -f "$PROFILE_D" ] && [ -f "$REPO_PROFILE" ]; then
  sudo cp "$REPO_PROFILE" "$PROFILE_D"
  sudo chmod +x "$PROFILE_D"
  echo "[setup] ✅ 恢复 $PROFILE_D (sudo)"
fi

# 4. 起容器（如果没在跑）
if ! docker ps --format '{{.Names}}' | grep -q '^zai2api$'; then
  echo "[setup] 启动 zai2api 容器..."
  bash "$AUTOSTART"
else
  echo "[setup] ✓ zai2api 容器已在跑"
fi

# 5. 验证
echo
echo "[setup] === 验证 ==="
docker ps --format '{{.Names}}\t{{.Status}}' | grep zai2api || echo "❌ 容器未在跑"
echo -n "  /v1/models: "
curl -s -m 3 -o /dev/null -w "%{http_code}" -H "Authorization: Bearer d3vin" http://localhost:8080/v1/models
echo
echo "[setup] 完成。Hermes fallback 链路就绪。"