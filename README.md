# deepseek-qq-bot

基于 **NapCat + Kev-0.8B + DeepSeek** 的 QQ 机器人. 

Kev 是本地运行的小型判断模型, 负责判断: 

1. **该不该回**( `should_reply`) 
2. **有没有风险**( `risk`) 
3. **用什么语气**( `style`) 

## 特性

- **智能触发**: Kev 结合最近聊天记录、是否被 @、是否引用机器人等上下文做语义判断. 
- **风险拦截**: 风险概率超过阈值时, 拒绝回话. 
- **表情包**: 有阅读和使用表情包的能力.
- **上下文记忆**: 各群 / 私聊独立 SQLite 会话, 保留最近若干条消息。
- **命令**: `!help`、`!ping`、`!status`、`!reset`. 

## 前置条件

- Linux
- [uv](https://docs.astral.sh/uv/)(Python 3.13)
- Docker + Docker Compose
- 一个 QQ 小号( **不要用主号**) 
- DeepSeek API Key: <https://platform.deepseek.com/api_keys>
- 可选: NVIDIA 显卡. 

## 快速开始

```bash
cd ~/Playground/deepseek-qq-bot

# 1. 生成 .env、安装 bot 依赖、安装 Kev 依赖
make install

# 2. 编辑 .env, 填入 DeepSeek key
#    同时确认 WEBUI_TOKEN 是随机长串(init_env.sh 已自动生成) 
vim .env

# 3. 启动 NapCat
make up
docker compose logs -f napcat
```

打开 <http://127.0.0.1:6099/webui>, 用 `.env` 里的 `WEBUI_TOKEN` 登录, 然后扫码登录 QQ. 

> NapCat 的 WebUI 和 OneBot WS 都绑定在 `127.0.0.1`, 不要改成公网监听. 扫码建议用小号; NapCat 属于非官方客户端, 存在账号风控风险. 

确认 NapCat 的 OneBot v11 正向 WebSocket 已监听 3001: 

```bash
ss -lntp | grep 3001
```

`compose.yaml` 里的 `MODE=ws` 会在首次启动时生成配置. 如果 WebUI 里没有自动出现, 手动添加: 

- 类型: WebSocket 服务器( 正向 WS) 
- Host: `0.0.0.0`
- Port: `3001`
- 消息格式: `array`
- Token: 可留空; 如果设置, 把同样的值填到 `.env` 的 `NAPCAT_WS_TOKEN`

然后启动 Kev 和机器人: 

```bash
# 终端 1: 前台启动 Kev, 首次会下载 Kev-0.8B 权重
make kev

# 终端 2: 检查三方连通性
make check

# 终端 3: 启动机器人
make bot
```

或者后台一键启动: 

```bash
make start
make status
tail -f data/logs/bot.log
```

停止: 

```bash
make stop          # 停 bot 和 Kev, 保留 NapCat 容器
make down          # 停 bot、Kev, 并删除 NapCat 容器(登录数据仍保留) 
```

## 配置说明

配置需写入 `.env`.  

| 变量 | 默认 | 说明 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 空 | 必填 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | DeepSeek 模型名 |
| `DEEPSEEK_THINKING` | `false` | 是否开启思考模式 |
| `VISION_ENABLED` | `true` | 是否处理图片 |
| `VISION_CAPTION_FOR_KEV` | `true` | 是否先让 DeepSeek 描述图片再交给 Kev |
| `VISION_DETAIL` | `low` | 图片细节级别: `low` / `high` / `original` / `auto` |
| `MAX_IMAGES_PER_MESSAGE` | `3` | 单条消息最多处理几张图 |
| `MAX_IMAGE_BYTES` | `20971520` | 单张图片最大字节数 |
| `MAX_CONTEXT_IMAGES` | `2` | 最终回复时最多带几张历史图片 |
| `STICKER_ENABLED` | `true` | 是否附发表情包 |
| `STICKER_DIR` | `~/Downloads/表情包` | 本地表情包目录 |
| `STICKER_CHANCE` | `0.2` | 每条回复附表情包的概率 |
| `STICKER_BLOCK_WORDS` | 见 `.env.example` | 文件名含这些词的表情包不自动发送 |
| `BOT_NAME` | `小深` | 机器人名字, 也用于日志和回复前缀清理 |
| `BOT_ALIASES` | `小深,deepseek,ds` | 群聊里叫到这些词时, 按"被点名"降低阈值 |
| `ADMIN_QQS` | 空 | 管理员 QQ, 逗号分隔, 才能用 `!status` / `!reset` |
| `GROUP_WHITELIST` | 空 | 只在这些群工作; 留空不限制 |
| `GROUP_BLACKLIST` | 空 | 这些群完全忽略 |
| `PRIVATE_WHITELIST` | 空 | 只和这些 QQ 私聊; 留空不限制 |
| `PRIVATE_BLACKLIST` | 空 | 这些 QQ 私聊完全忽略 |
| `ENABLE_AMBIENT` | `true` | 是否允许群聊里没被 @ 时主动接话 |
| `KEV_ENABLED` | `true` | 关闭后走简单本地规则, 仅用于调试 |
| `KEV_MODEL_REPO` | `jaredpalmer/kev-0.8b` | Kev 权重仓库 |
| `KEV_DEVICE` | `auto` | `auto` / `cuda` / `cpu` |
| `KEV_REPLY_THRESHOLD_AT` | `0.20` | 被 @ / 被叫名字时的回复阈值 |
| `KEV_REPLY_THRESHOLD_PRIVATE` | `0.20` | 私聊回复阈值 |
| `KEV_REPLY_THRESHOLD_GROUP` | `0.72` | 普通群聊主动接话阈值, 越高越安静 |
| `KEV_RISK_THRESHOLD` | `0.60` | 风险概率达到该值就不回 |
| `KEV_FAIL_OPEN` | `false` | Kev 挂掉时是否仍然放行; 默认宁可沉默 |
| `GROUP_COOLDOWN_SECONDS` | `25` | 群聊主动接话冷却 |
| `USER_COOLDOWN_SECONDS` | `90` | 同一用户主动接话冷却 |
| `MAX_REPLIES_PER_MINUTE` | `8` | 全局每分钟最多发送条数 |
| `MAX_BOT_MESSAGES_IN_ROW` | `2` | 机器人连续发言上限 |
| `MAX_CONTEXT_MESSAGES` | `10` | 提供给 Kev / DeepSeek 的最近消息数 |
| `DRY_RUN` | `false` | 只走流程不发消息, 也不调用 DeepSeek; 图片描述同样跳过 |
| `DECISION_LOG` | `true` | 写 `data/decisions.jsonl` |

## 命令

在群里需要 @ 机器人, 私聊直接发: 

| 命令 | 作用 |
|---|---|
| `!help` | 显示帮助 |
| `!ping` | 测试在线, 返回延迟 |
| `!status` | 查看 Kev / DeepSeek / 上下文 / 统计( 管理员)  |
| `!reset` | 清空当前会话记忆( 管理员)  |

管理员在 `.env` 里设置: 

```env
ADMIN_QQS=123456789,987654321
```

## 日志与数据

```
data/
├── bot.sqlite3          # 会话上下文
├── decisions.jsonl      # 每次 Kev 判断
├── logs/
│   ├── bot.log
│   └── kev.log
├── run/                 # PID 文件
└── napcat/              # QQ 登录态、NapCat 配置、插件
```

## 测试

```bash
make test          # 单元测试, 不需要 GPU / 网络
make check         # 检查 .env、Kev /v1/models、DeepSeek 文本 ping、表情包目录
make smoke         # 用 6 条中文样例看 Kev 的概率倾向
```

`make smoke` 输出类似: 

```
[被叫到] 小深, 帮我看看这段 Python 报错是什么意思？
  should_reply=0.94  risk=0.01  style=friendly (0.63)
```

## 自定义人设

编辑 `persona.md`, 重启 bot 生效. 示例: 

```markdown
你是「小深」, 一个待在 QQ 群里的 AI 朋友. 
说话自然、简短, 不刷屏, 不装人类. 
遇到不确定的事就说不知道. 
```

`persona.md` 会作为 DeepSeek 的 system prompt 的一部分; Kev 只收到简短的机器人设定和聊天上下文, 不会收到完整人设. 

## 开发

```bash
uv sync --all-groups     # bot 依赖
uv run pytest -q         # 测试
uv run python -m bot.main --check
uv run python -m bot.main
```

代码结构上, `handler.py` 是唯一把"过滤、Kev、DeepSeek、发送"串起来的地方; `decision.py` 只做纯函数策略, 方便单测. 新增命令在 `handler._handle_command` 里加; 新增 Kev 问题在 `decision.KEV_QUESTIONS` 里加, 并在 `_process` 里读取. 

## 参考

- Kev: <https://github.com/jaredpalmer/kev>
- NapCat: <https://github.com/NapNeko/NapCatQQ>
- NapCat Docker: <https://github.com/NapNeko/NapCat-Docker>
- OneBot v11: <https://github.com/botuniverse/onebot-11>
- DeepSeek API: <https://api-docs.deepseek.com/>

## License

MIT © 2026 AHuangMeow
