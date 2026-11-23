---
translated: true
source: agents/README.md
---

# Agents

> 原文：[agents/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/agents/README.md)



## 這篇在做什麼

介紹一個用 Claude API 實作 LLM agent 的極簡教學版本，核心邏輯不到 300 行，重點展示「LLM 在迴圈裡使用 tool」這個基礎。

## 學完你會

- 知道這個參考實作由 `agent.py`、`tools/`、`utils/` 三塊組成
- 理解 agent 的核心就是 LLM 在迴圈裡使用 tool
- 知道跑起來需要哪些環境和套件

## 開跑前

需要 Python 3.10+、設好 `ANTHROPIC_API_KEY` 環境變數的 Claude API key，以及 `anthropic` 和 `mcp` 兩個 Python 套件（2.0 以上）。

一個用 Claude API 實作 LLM agent 的極簡教學版本。

> **注意：**這不是 SDK，而是關鍵概念的參考實作

## 概覽與核心元件

這個 repo 示範怎麼用 Claude API [打造有效的 agent](https://www.anthropic.com/engineering/building-effective-agents)。它展示了複雜的 AI 行為，可以從一個簡單的基礎長出來：LLM 在迴圈裡使用 tool。這個實作沒有任何強制要求，核心邏輯不到 300 行，而且刻意不含 production 才有的功能。你可以把這些 pattern 翻成你用的語言和 production 技術堆疊（[Claude Code](https://docs.claude.com/en/docs/agents-and-tools/claude-code/overview) 可以幫忙！）

它包含三個元件：

- `agent.py`：管理 Claude API 互動和 tool 執行
- `tools/`：tool 實作（包含原生 tool 和 MCP tool）
- `utils/`：訊息歷史和 MCP server 連線的工具

## 使用方式

```python
from agents.agent import Agent
from agents.tools.think import ThinkTool

# Create an agent with both local tools and MCP server tools
agent = Agent(
    name="MyAgent",
    system="You are a helpful assistant.",
    tools=[ThinkTool()],  # Local tools
    mcp_servers=[
        {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "mcp_server"],
        },
    ]
)

# Run the agent
response = agent.run("What should I consider when buying a new laptop?")
```

在這個基礎上，你可以加領域專用的 tool、最佳化效能，或實作自訂的回應處理。我們刻意保持中立，這個骨架只是讓你從基本功開始。

## 需求

- Python 3.10+
- Claude API key（設為 `ANTHROPIC_API_KEY` 環境變數）
- `anthropic` Python 套件，2.0 以上
- `mcp` Python 套件，2.0 以上

```bash
pip install "anthropic>=2.0.0,<3" "mcp>=2.0"
```

## 重點整理

- agent 的核心就是 LLM 在迴圈裡使用 tool，不需要複雜的框架。
- 三個元件分工：agent 迴圈、tool 實作、訊息歷史和 MCP 連線。
- 這個實作是教學用的參考，不含 production 功能，要自己補。
- tool 可以是原生 tool，也可以是 MCP server 提供的 tool。

## 練習

1. 照 README 的指令跑起來，觀察一次 tool 呼叫的完整訊息流程。
2. 在 `tools/` 加一個自己的小 tool（例如回傳現在時間）。
3. 修改 agent 迴圈，加上最大迭代次數的保護。
