# zai2api — Hermes Agent 定制版

基于 [Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent) 的定制部署，包含：

1. **zai2api 容器** — Z.AI GLM 模型的 OpenAI 兼容代理网关
2. **三联屏视频管线** — AI 自动生成封面文案 + 渲染三联屏短视频
3. **Hermes fallback 配置** — 完整的多层模型回退链路

---

## 目录结构

```
zai2api/
├── assets/                  # 视频管线脚本
│   ├── triptych_full.py     # 主入口：渲染 → 上传 → Telegram
│   ├── auto_triptych.py     # 视频渲染引擎 v4
│   ├── generate_copy.py     # AI 封面文案生成器
│   ├── make_series_cover.py # 1280x720 封面图生成
│   ├── pipeline_paths.py    # 路径常量共享
│   ├── spare_titles.py      # 199 个备用中文标题
│   └── bgm/                 # BGM 音乐文件
├── zai2api-config/          # zai2api 容器配置与启动脚本
│   ├── autostart.sh         # 自动启动脚本（含自动拉取镜像）
│   ├── profile.sh           # /etc/profile.d/ hook
│   └── setup.sh             # codespace 重建恢复脚本
├── .persistedshare/         # Codespace 持久化数据
│   └── zai2api-config/      # 加密配置 + 密码文件
└── README.md                # 本文档
```

---

## 快速开始

### 1. 启动 zai2api 容器

```bash
# 首次设置
bash zai2api-config/setup.sh

# 日常使用 — 容器会自动启动（重启/重建后）
bash ~/.zai2api-autostart.sh
```

容器配置：
- 端口：`localhost:8080`
- 认证：`Authorization: Bearer <AUTH_TOKEN>`（默认 `d3vin`）
- Token 池：750 个 deviceToken（自动采集 + 补采）

### 2. 测试 API

```bash
# 健康检查
curl http://localhost:8080/healthz

# 模型列表
curl http://localhost:8080/v1/models \
  -H "Authorization: Bearer d3vin"

# 对话测试
curl -N http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer d3vin" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-5.2","messages":[{"role":"user","content":"hi"}]}'
```

### 3. 生成视频

```bash
# 基本用法（手动指定文案）
python3 assets/triptych_full.py <视频文件> \
  --title 流光 \
  --en RADIANCE \
  --theme cool

# AI 自动生成文案（需要 ZAI_API_KEY）
python3 assets/triptych_full.py <视频文件> \
  --auto-copy \
  --no-upload \
  --no-notify

# 完整选项
python3 assets/triptych_full.py <视频> \
  --title 标题 --en ENGLISH \
  --kicker "COOL · DARK VIBES" \
  --tag "中文 tagline" \
  --foot "for you" \
  --theme cool \
  --hero-at 0.0 \
  --yoff -0.02 \
  --intro 3.0 \
  --fade-in 1.0 \
  --fade-out 1.5 \
  --afade-in 2.0 \
  --afade-out 3.0 \
  --upload \
  --no-notify
```

---

## 支持的模型

| 模型 | 需要通过 zai2api | 说明 |
|------|-----------------|------|
| `glm-4.7` | ✅ | guest 模式可用 |
| `GLM-5-Turbo` | ✅ | 需要 ZAI_TOKEN |
| `GLM-5v-Turbo` | ✅ | 需要 ZAI_TOKEN |
| `GLM-5.1` | ✅ | 需要 ZAI_TOKEN |
| `glm-5.2` | ✅ | 需要 ZAI_TOKEN |

---

## Hermes Fallback 配置

`~/.hermes/config.yaml` 中的 fallback 顺序（从高到低）：

```yaml
fallback_providers:
  - name: zai2api-52          # glm-5.2（最先进）
    provider: openai-compatible
    base_url: http://localhost:8080/v1
    model: glm-5.2
    key_env: ZAI2API_AUTH_TOKEN

  - name: zai2api-turbo       # GLM-5-Turbo
    provider: openai-compatible
    base_url: http://localhost:8080/v1
    model: GLM-5-Turbo
    key_env: ZAI2API_AUTH_TOKEN

  - name: zai                 # glm-4.5-flash（Z.AI 官方 API）
    provider: zai
    base_url: https://api.z.ai/api/paas/v4
    model: glm-4.5-flash
    key_env: ZAI_API_KEY

  - name: zai2api-47          # glm-4.7（兜底）
    provider: openai-compatible
    base_url: http://localhost:8080/v1
    model: glm-4.7
    key_env: ZAI2API_AUTH_TOKEN
```

环境变量（`~/.hermes/.env`）：
```bash
ZAI2API_AUTH_TOKEN=d3vin     # zai2api 认证
ZAI_API_KEY=...              # Z.AI 官方 API（fallback 用）
```

---

## zai2api 容器管理

### 查看状态
```bash
docker ps | grep zai2api
docker logs zai2api --tail 20
curl http://localhost:8080/status | python3 -m json.tool
```

### 重启容器
```bash
docker restart zai2api
```

### Token 池状态
```bash
curl -s http://localhost:8080/status | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'用户: {d[\"userName\"]}')
print(f'Token 池: {d[\"tokenCount\"]} / 750')
print(f'连接状态: {\"✅\" if d[\"connected\"] else \"❌\"}')
"
```

---

## 视频管线详解

### 工作流程

```
源视频 → hero 帧 → 封面 PNG → 片头卡 → 三联主体 → 拼接 + 淡入淡出 → BGM → 上传
```

### 各脚本职责

| 脚本 | 功能 |
|------|------|
| `triptych_full.py` | 主入口：编排全流程 |
| `auto_triptych.py` | 渲染引擎：封面 → 片头 → 三联 → 拼接 → BGM |
| `generate_copy.py` | AI 文案生成：抽帧 → 描述 → 生成标题/副标/tagline |
| `make_series_cover.py` | 封面图生成：1280x720，双色主题（cool/warm） |
| `pipeline_paths.py` | 路径常量共享 |
| `spare_titles.py` | 199 个备用中文标题 |

### 封面文案格式

AI 生成的文案包含：
- `title` — 中文大标题（2字最佳）
- `en` — 英文副标（全大写，3-6词）
- `kicker` — 风格标签（如 "COOL · DARK VIBES"）
- `tag` — 中文 tagline（10-20字）
- `foot` — 英文页脚（2-4词）

### 视频参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--intro` | 3.0s | 片头封面时长 |
| `--fade-in` | 1.0s | 视频淡入 |
| `--fade-out` | 1.5s | 视频淡出 |
| `--afade-in` | 2.0s | 音频淡入 |
| `--afade-out` | 3.0s | 音频淡出 |
| `--theme` | warm | cool（冰蓝）/ warm（暖褐） |
| `--hero-at` | 0.0s | 抽帧时间点 |
| `--yoff` | -0.02 | 竖向裁切偏移 |

---

## Codespace 恢复

### 正常重启
容器 `--restart unless-stopped` 自动恢复，无需操作。

### Codespace 重建后
重建会清掉 `/etc/profile.d/` 和 `~/.zai2api-autostart.sh`，但持久化数据保留：

```bash
# 运行恢复脚本
bash /workspaces/zai2api/zai2api-config/setup.sh
```

脚本会自动：
1. 重建 `~/.zai2api-config/` 软链到持久化目录
2. 复制 autostart 脚本到 `~/.zai2api-autostart.sh`
3. 恢复 `/etc/profile.d/zai2api-autostart.sh`
4. 启动容器（自动拉取最新镜像）

---

## 故障排查

### 容器无法启动
```bash
# 检查镜像
docker image inspect zai2api:latest || docker pull ghcr.io/pingmike2/zai2api:latest

# 检查 token 池
curl -s http://localhost:8080/healthz

# 查看日志
docker logs zai2api --tail 50
```

### zai2api 返回 401
确认 `ZAI2API_AUTH_TOKEN` 与容器内 `AUTH_TOKEN` 一致。

### GLM-5 模型不可用
确认 `ZAI_TOKEN` 已配置（检查 `docker exec zai2api env | grep ZAI_TOKEN`）。

### 视频渲染失败
确认已安装 ffmpeg：
```bash
apt-get install -y ffmpeg
```

---

## 相关链接

- [Hermes Agent 官方文档](https://hermes-agent.nousresearch.com/docs/)
- [zai2api 上游仓库](https://github.com/pingmike2/zai2api)
- [GLM-ZAI-2API 原版](https://github.com/D3-vin/GLM-ZAI-2API)

---

## License

MIT — 继承自 [Nous Research Hermes Agent](https://github.com/NousResearch/hermes-agent)。
