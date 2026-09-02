# codespace 启动时自动恢复 zai2api 容器
# 任何用户登录（包括 codespace 后台 spawn 的 shell）都会触发
if [ -x "/home/codespace/.zai2api-autostart.sh" ]; then
  /home/codespace/.zai2api-autostart.sh 2>/dev/null || true
fi