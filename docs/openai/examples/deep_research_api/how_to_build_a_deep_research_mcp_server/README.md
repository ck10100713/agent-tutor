---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/deep_research_api/how_to_build_a_deep_research_mcp_server/README.md
---

# 建一個 Deep Research MCP Server

> 原文：[examples/deep_research_api/how_to_build_a_deep_research_mcp_server/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/README.md)



## 這篇在做什麼
這是一個最小版的 Deep Research 風格 MCP server，可以搜尋並取回 OpenAI 檔案儲存服務裡的檔案。
Deep Research agent 專門依賴 Search 和 Fetch 兩個 tool：Search 要在你的物件儲存裡找出一組特定的 top-k ID，Fetch 則接收 objectId 當參數，把對應的資源取回來。

想知道怎麼用 Responses API 搭配 Deep Research 呼叫這個服務，看[這篇 cookbook](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api)。想知道怎麼用 Agents SDK 呼叫這個 MCP server，看[這篇 cookbook](https://cookbook.openai.com/examples/deep_research_api/how_to_use_deep_research_API_agents)。

## 學完你會
- 把內部檔案放進 OpenAI Vector Storage，並架一個提供 search 和 fetch 的 MCP server。
- 用 SSE transport 在本機啟動 server，必要時用 ngrok 對外開放。
- 看懂一次 Deep Research 呼叫 MCP server 的請求長什麼樣子。

## 開跑前
- 需要 OpenAI API key，以及 OpenAI Vector Storage 裡已存好的檔案。
- 要讓公網的 client 連到本機 server，需要 ngrok 或類似工具。

## 安裝與執行

把你的內部檔案存到 [OpenAI Vector Storage](https://platform.openai.com/storage/vector_stores/)。

Python 環境設定：

```shell
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

啟動 server：

```shell
python main.py
```

server 會用 SSE transport 在 `http://0.0.0.0:8000/sse/` 啟動。如果想從公開網路連到這個 server，有很多做法，包括用 ngrok：

```shell
brew install ngrok 
ngrok config add-authtoken <your_token>
ngrok http 8000
```

這樣你的 client 就能連到本機的 server 了。

## 檔案

- `main.py`：[server 主程式](https://github.com/openai/openai-cookbook/blob/main/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/main.py)

## MCP Server 範例流程圖

![../../../images/mcp_dr.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/mcp_dr.png)

## 請求範例

```python
# system_message includes reference to internal file lookups for MCP.
system_message = """
You are a professional researcher preparing a structured, data-driven report on behalf of a global health economics team. Your task is to analyze the health question the user poses.

Do:
- Focus on data-rich insights: include specific figures, trends, statistics, and measurable outcomes (e.g., reduction in hospitalization costs, market size, pricing trends, payer adoption).
- When appropriate, summarize data in a way that could be turned into charts or tables, and call this out in the response (e.g., "this would work well as a bar chart comparing per-patient costs across regions").
- Prioritize reliable, up-to-date sources: peer-reviewed research, health organizations (e.g., WHO, CDC), regulatory agencies, or pharmaceutical earnings reports.
- Include an internal file lookup tool to retrieve information from our own internal data sources. If you've already retrieved a file, do not call fetch again for that same file. Prioritize inclusion of that data.
- Include inline citations and return all source metadata.

Be analytical, avoid generalities, and ensure that each section supports data-backed reasoning that could inform healthcare policy or financial modeling.
"""

user_query = "Research the economic impact of semaglutide on global healthcare systems."

response = client.responses.create(
  model="o3-deep-research-2025-06-26",
  input=[
    {
      "role": "developer",
      "content": [
        {
          "type": "input_text",
          "text": system_message,
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": user_query,
        }
      ]
    }
  ],
  reasoning={
    "summary": "auto"
  },
  tools=[
    {
      "type": "web_search_preview"
    },
    { # ADD MCP TOOL SUPPORT
      "type": "mcp",
      "server_label": "internal_file_lookup",
      "server_url": "http://0.0.0.0:8000/sse/", # Update to the location of *your* MCP server
      "require_approval": "never"
    }
  ]
)

```

## 重點整理
- Deep Research 只需要兩個 tool：search 負責找出候選 ID，fetch 負責依 ID 取回內容。
- MCP server 是 agent 跟你的私有資料之間的標準介面，資料不用搬出原本的儲存。
- SSE transport 的 server 要讓遠端 client 連到，就得有公開網址。
- 把「找」和「讀」拆成兩個 tool，讓模型能先縮小範圍再讀全文。

## 練習
1. 啟動 server 後，用瀏覽器或 curl 連 `http://0.0.0.0:8000/sse/`，確認它在回應。
2. 在 `main.py` 裡改 search 回傳的 top-k 數量，用範例請求測試結果變化。
3. 用 ngrok 開出公開網址，把它填進請求範例的 MCP server 位址，實際讓 Deep Research 呼叫一次。
