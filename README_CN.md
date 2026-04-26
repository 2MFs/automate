# autoMate

> **AI 的智能 NAS。** 你的仓库:笔记 · 文件 · 提醒 · 记忆 · 30+ 工具。
> 接进任何大模型。我们不做聊天 — 我们做聊天背后的**仓储 + 工具库**。

```
   ┌─ Claude Code ──┐                    ┌─ notes/memory ───── 跨会话生存
   ├─ Cursor / Cline├──── MCP ────┐      ├─ files ──────────── 文件库
   ├─ Kimi K2 / GPT ├──── HTTP ───┤      ├─ reminders ──────── 推到手机
   ├─ Ollama / 网页 ├──── bridge ─┤      ├─ memory ─────────── 长期记忆
   └─ 你的脚本      ┘             │      │
                                  ▼      ▼
                          ┌──────────────────┐    ┌─ shell · script · browser
                          │     autoMate     │ ── ┤  desktop · 31 SaaS APIs
                          │   (你的机器)     │    └─ 你正在用的 Chrome (扩展)
                          └────────┬─────────┘
                                   ▼
                          ~/.automate/  · SQLite + Fernet 加密
```

## 这是什么

每家 AI 厂商都在抢"聊天入口"。大多数也能调工具。**但没有任何一家能把你
所有用过的 AI 串起来 — 跨厂商记忆、本地存大文件、时间到了主动推手机。**

autoMate 是聊天背后的那一层:**你自己拥有的仓库**。一段话粘到你正在用的
AI 里 — 从此**那个 AI** 能往你笔记里写、把文件丢进来、设置提醒、调用真实
工具。明天换一家 AI,数据照样能读出来。

| 你正在用 | autoMate 给那个 AI 的 |
|---|---|
| Kimi 网页版 / ChatGPT | 一个本地 hub 让它去读写工具/笔记/文件 |
| Claude Code | 同上,通过 MCP |
| Cursor / Cline | 同上,通过 MCP |
| 终端里的 Ollama | 一个 bridge 脚本,Ollama 调 shell 就行 |
| 你的手机 (APK / PWA) | 你的数据装在口袋里 — 电脑关机也能用 |

## 两种"运行级别"

| 级别 | 存储位置 | 适合 |
|---|---|---|
| **纯本地**(手机 APK / PWA) | 设备本地 IndexedDB | 临时记笔记,电脑不在身边 |
| **Hub**(电脑 / NAS / Docker) | SQLite + 文件系统 + 30+ 工具 | 完整仓库:工具、文件、推送 |

两者之间的同步是**手动的、可选的**。详见 [docs/sync.md](./docs/sync.md)。

## 安装

| 路径 | 拿什么 | 适合 |
|---|---|---|
| `pip install 'automate-hub[full]'` | Python 包 | 有 Python 想轻量 |
| 独立二进制(Win/Mac/Linux) | [Releases](https://github.com/yuruotong1/autoMate/releases/latest) | 没 Python,双击就跑 |
| Docker | `docker run -p 8765:8765 ghcr.io/yuruotong1/automate:latest` | NAS / 服务器 |
| 浏览器扩展 | [`extension/`](./extension/) | 接管你正在用的 Chrome |
| **Android APK** | [Releases](https://github.com/yuruotong1/autoMate/releases/latest) | 原生手机 app,**纯本地模式可独立用** |
| iOS / 任意手机 | 浏览器打开 hub URL → 添加到主屏幕 | PWA,所有手机都通 |

装完跑 `automate`,浏览器自动开。配模型 + 粘 key,2 分钟搞定。

## 接你常用的那个 AI

打开 **Connect AI** 标签,挑你那家的 snippet 复制。四种模式:

| 模式 | 适合 |
|---|---|
| **MCP** | Claude Code · Cursor · Cline · Kimi K2 · 任意 MCP 客户端 |
| **HTTP** | ChatGPT GPTs · n8n · Make · 你自己的脚本 |
| **Bridge** | 不会调工具的 LLM(基础 Ollama、网页聊天)— 一个 shell 中转脚本 |
| **OpenAPI** | 能读 schema 的 agent (`/openapi.json`) |

之后那个 AI 就拥有 hub 的全部工具目录,当原生 function calls 用。

## 手机端怎么用

手机是个**轻量驱动器**,装本地化数据(笔记/记忆),其余远程接 hub。三种装法:

1. **Android APK** — 从 release 下 `autoMate-android.apk`。**纯本地模式**就能记
   笔记。点黄色横幅可同步到电脑 hub 或中转。
2. **Android PWA** — Chrome 打开 hub URL → 添加到主屏幕。
3. **iOS PWA** — Safari 打开 hub URL → 分享 → 添加到主屏幕。
   (苹果不让侧载,所以 iOS 只有 PWA 这条路。iOS 16.4+ 支持 Web Push。)

详细步骤:[docs/mobile.md](./docs/mobile.md)。

## 仓库里有什么

**个人数据**
- `notes.*` — Markdown 文档,标签、搜索、置顶。本地或 hub 都行。
- `files.*` — 内容寻址文件库,SHA-256 去重,流式上传。仅 hub。
- `reminders.*` — 后台 scheduler + Web Push 推手机。仅 hub。
- `memory.*` — 长期 K/V 事实,任何 AI 都能读写。

**本地执行器**
- `shell.*`、`script.*`(Python/Bash/Node)、`desktop.*`(pyautogui)
- `browser.*`(Playwright,起干净 Chromium)
- `bx.*`(通过 [Chrome 扩展](./extension/README.md) 接管你正在用的浏览器)

**SaaS 集成 — 31 家**:GitHub · GitLab · Gitee · Notion · Slack · Linear ·
Jira · Confluence · Trello · Asana · Monday · HubSpot · Airtable · Stripe ·
Shopify · Telegram · Discord · MS Teams · Zoom · Twitter/X · SendGrid ·
Mailchimp · Twilio · Sentry · 飞书 · 钉钉 · 企业微信 · 微信公众号 · 微博 ·
语雀 · 高德地图。

**LLM 供应商 — 25 家**:OpenAI · Anthropic · Gemini · xAI Grok · Mistral ·
Cohere · OpenRouter · Groq · Together · Fireworks · DeepInfra · DeepSeek ·
Kimi · 通义 · 豆包 · 智谱 GLM · 百川 · Yi · MiniMax · 阶跃 · 混元 · 硅基流动 ·
Ollama · LM Studio · 任意 OpenAI 兼容端点。

## 隐私

- 服务器默认绑 `127.0.0.1`,需要联网访问要 `--host 0.0.0.0`。
- 凭据全部 Fernet 加密,密钥在 `~/.automate/secret.key`(0600)。
- LLM 调用直接从 autoMate 走到你选的厂商,中间没人偷看。
- 手机本地模式:数据在浏览器 IndexedDB,你不点同步就出不去。

## 状态

v4.2.0 — 手机本地存储(笔记 + 记忆走 IndexedDB)、手动 hub 同步、
内置 SPA 的原生 Android APK。iOS 走 PWA。多端发布:pip · 独立二进制 ·
Docker · Chrome 扩展 · Android APK · iOS PWA。

English: [README.md](./README.md)

## License

MIT。
