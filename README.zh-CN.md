# Chat Deck

> 一个面向 Claude Code 和 Codex 的 chat-first 多 agent 控制台，基于 Python、Textual 和 tmux 构建。

Chat Deck 让你可以在一个终端 UI 中统一管理多个 Claude Code 和 Codex agent。每个 agent 都运行在自己独立的 tmux 会话里，也可以工作在完全不同的目录。你不需要一直盯着原始终端日志，而是可以在聊天式主面板中与当前选中的 agent 对话，并在任务完成后直接收到结构化总结。

![Chat Deck 界面截图](./assets/chat-deck-screenshot.png)

> 当前状态：alpha / experimental
>
> 当前包名和 CLI 名称是：`chat-deck`

[English README](./README.md)

---

## 为什么做 Chat Deck？

同时跑多个 Claude Code 或 Codex 会话其实不难，难的是让这些会话始终可见、可切换，并且保持“以对话为中心”的体验。

tmux 和终端 tab 很擅长管理终端本身。Chat Deck 位于它们之上，提供的是 chat-first 的控制层：统一入口、agent 状态可见、直接点名某个 agent，以及结构化完成总结。

---

## Chat Deck 能做什么

- 在一个控制台 UI 里管理多个 agent
- 当前支持的真实 worker：
  - Claude Code
  - Codex
- 每个 agent 跑在独立的 tmux session 中
- 通过常驻侧边栏持续显示会话状态
- 在主面板中以聊天方式和当前选中的 agent 交互
- agent 完成任务后，直接把总结回传到面板，而不是每次都要 attach 到 tmux 才能看结果
- 支持结构化完成协议：

```xml
<TASK_DONE>{"summary":"...","result":"...","next":"..."}</TASK_DONE>
```

- 通过临时注入的方式接入 Claude hooks 和 Codex notify，不改你的全局 `~/.claude` 或 `~/.codex`
- 大段粘贴内容会在 UI 中折叠，发送时再恢复原文
- 在侧边栏和当前聊天视图里都显示 loading 状态
- 支持用鼠标拖动调整侧边栏宽度

---

## 当前功能

### 多 agent 聊天控制台

- 单一主界面统一管理多个 agent 会话
- 左侧侧边栏始终显示所有 session 卡片
- 卡片中会显示：
  - 名称
  - client
  - 工作目录
  - 状态

### Chat-first 交互

- 主内容区是当前选中 agent 的聊天视图
- 原始执行日志不是主视图
- agent 完成任务后，会把总结直接回到聊天区

### 基于 tmux 的真实 worker

- 每个 agent 都运行在独立的 tmux session 中
- 不同 agent 可以运行在完全不同的目录
- 需要时仍然可以进入原生 CLI 界面

### 结构化完成回传

- Claude 和 Codex 都可以把任务完成总结回传到面板
- 当前完成判定主要依赖 `<TASK_DONE>...</TASK_DONE>` 协议

### 输入体验和可用性

- 内容区支持鼠标选中文本
- `Ctrl+C` 复制
- `Ctrl+V` 粘贴
- 大段粘贴内容会折叠显示，发送时恢复原文
- 输入 `/` 时会显示命令联想
- `Tab` 可以自动补全当前命令建议

---

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Chat Deck 依赖 `tmux` 来运行真实的 Claude Code 和 Codex worker，所以正常启动前需要单独安装：

```bash
brew install tmux
```

如果你准备使用真实 worker，也请确保这些命令都在 `PATH` 中：

```bash
which tmux
which claude
which codex
```

---

## 运行

```bash
chat-deck
```

没有安装 `tmux` 时，仍然可以先跑 demo：

```bash
chat-deck --demo
```

---

## 命令

### 创建 agent

```bash
/new codex <name> <cwd>
/new claude <name> <cwd>
```

也可以在工作目录后面直接追加 client 的启动参数：

```bash
/new codex worker /path/to/project --model gpt-5 --profile fast
/new claude reviewer /path/to/project --dangerously-skip-permissions
```

即使你加了自定义参数，Chat Deck 仍然会继续注入它自己的 notify / settings 回调。

### 会话管理

- `/agents`：列出当前 agent
- `/attach [agent-name]`：进入当前选中或指定 agent 的原生 tmux 会话
- `/close`：关闭当前 active agent
- `/close <agent-name>`：关闭指定 agent，并销毁对应 tmux session

### 消息路由

- `@agent-name ...`：直接给指定 agent 发消息

---

## 快捷键

- `Ctrl+1..9`：选中 agent
- `Ctrl+T`：进入当前 agent 的原生 tmux 会话
- `Ctrl+X`：关闭当前 active agent，并杀掉它背后的 tmux session
- `Ctrl+B`：隐藏 / 显示侧边栏
- `Esc`：回到 controller

---

## 工作方式

Chat Deck 可以理解为两层结构。

### 1. Controller UI

Controller 层基于 Python + Textual 构建。

它负责：

- 展示 agent 状态
- 路由消息
- 展示总结
- 管理当前 active 的聊天视图

### 2. 真实 worker 会话

Claude Code 和 Codex 以真实 CLI worker 的形式运行在 tmux 中。

Chat Deck 不会替代这些 CLI。它做的是管理、通信和总结。

当你确实需要原生界面时，再通过 `Ctrl+T` attach 到对应 worker 的 tmux session。

---

## 为什么不直接用 tmux 或终端标签页？

tmux 管理的是终端。

Chat Deck 管理的是 agent 对话。

这意味着：

- 你不需要反复找 pane 才能知道哪个 session 在跑
- 你可以直接在 controller 里和 agent 对话
- 你能直接收到任务完成总结
- 只有在确实需要的时候，才进入原生 CLI

---

## 当前限制

- Controller 目前还没有接完整的 LLM orchestration 层
- Codex 的更细粒度语义状态还没有接到完整 app-server 路径
- 完成总结目前仍然依赖 worker 正确输出 `TASK_DONE` 协议
- 当前主 UI 是 chat-first，不是嵌入式的原生 Claude / Codex 终端

---

## Roadmap

- 增加更聪明的 controller agent
- 改进 Codex 的语义状态集成
- 让完成总结比当前纯协议检测更稳
- 增加更丰富的会话历史和总结浏览
- 后续再探索嵌入式终端能力，但不会把它作为核心体验

---

## 设计原则

- Chat first, terminal second
- 总结优先于原始日志
- 只在必要时进入原生 CLI
- 不污染全局配置
- 一个 controller，多条长期运行的 worker

---

## 适合谁？

Chat Deck 适合这些开发者：

- 同时运行多个 Claude Code 或 Codex 会话
- 希望在一个地方看到所有 session 状态
- 更喜欢“对话 + 总结”而不是一直盯着终端输出
- 仍然希望在需要时保留原生 tmux-backed CLI 会话能力

---

## 项目状态

Chat Deck 目前聚焦在本地优先工作流：

- Python + Textual 负责 controller
- tmux 负责长期运行的 worker session
- Claude Code 和 Codex 是第一批支持的 worker

打包、安装和更广泛的分发方式还在继续演进。

---

## 许可证

[MIT](./LICENSE)
