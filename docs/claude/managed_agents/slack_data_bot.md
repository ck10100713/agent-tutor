---
translated: true
source: managed_agents/slack_data_bot.ipynb
---

# 用 Claude Managed Agents 做 Slack 資料分析 bot

> 原文：[managed_agents/slack_data_bot.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/slack_data_bot.ipynb)

在 Slack 提及 bot 並附上 CSV，就能在 thread 裡拿到分析報告，並可在同一個 session 繼續多輪追問。

## 這篇在做什麼

把 `data_analyst_agent.ipynb` 裡做好的 agent 包進一個用 Bolt for Python 寫的 Slack bot。使用者在 Slack 提及 bot 並附上 CSV，bot 會把分析過程和報告貼回 thread，後續回覆會延續同一個 session。

## 學完你會

- 從 Slack mention 觸發一次 agent 執行。
- 把 agent 的進度以 thread 更新的形式顯示出來。
- 把完成的報告和 agent 產生的檔案貼回 thread。
- 讓 thread 裡的後續回覆接續同一個 session。

## 開跑前

需要先建立 Slack app（用 manifest，取得 `xoxb-` bot token 和 `xapp-` app-level token）、一個 Slack workspace，並先跑過 `data_analyst_agent.ipynb`，讓 `ANALYST_ENV_ID`、`ANALYST_AGENT_ID`、`ANALYST_AGENT_VERSION` 存進 `.env`。還需要 Anthropic API key。

## 簡介

你會把 [`data_analyst_agent.ipynb`](data_analyst_agent.md) 裡的 agent 包進一個用 [Bolt for Python](https://docs.slack.dev/tools/bolt-python/)（Slack 官方的 app 開發框架）寫的 Slack bot。在 Slack 提及 bot，附上問題和 CSV，就會在 thread 收到一份敘述性的報告。後續訊息會接續同一個 session。

```text
user: @databot what's driving Q1 revenue?  [sales.csv]
    │
    ▼
bot uploads the CSV and starts an agent session
    │
    ▼
bot streams the agent's progress back to the thread
    │
    ▼
bot posts the finished report to the thread
```

### 你會學到

- 從 Slack mention 啟動 agent 執行
- 把 agent 的進度顯示成 thread 更新
- 把完成的報告貼回 thread
- 用後續回覆讓對話繼續

### 前置作業

1. 執行下面的安裝 cell。

2. 建立 [Slack app](https://api.slack.com/apps)：選 **Create New App → From a manifest**，貼上 [`slack_app_manifest.yaml`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/example_data/slack_data_bot/slack_app_manifest.yaml)，並安裝到你的 workspace。這個 manifest 會啟用 Socket Mode（Slack 透過 WebSocket 傳送事件，所以不需要公開 URL）和所需的 scope。然後取得兩個 token：

   - **OAuth & Permissions** → 複製 Bot User OAuth Token（`xoxb-...`）
   - **Basic Information → App-Level Tokens** → 產生一個 scope 為 `connections:write` 的 token（`xapp-...`）

   在你想放 bot 的 channel 執行 `/invite @databot`。

3. 執行 [`data_analyst_agent.ipynb`](data_analyst_agent.md)，它會把 `ANALYST_ENV_ID`、`ANALYST_AGENT_ID` 和 `ANALYST_AGENT_VERSION` 存到 `.env`。

下面的設定 cell 會提示你輸入 Slack token 並存進 `.env`，重啟時就不用重新輸入（也可以事先把它們加進 `.env` 來略過提示）。`.env` 已經在 `.gitignore` 裡，千萬不要 commit 進版本控制。如果手邊沒有 Slack workspace，你還是可以讀程式碼，每個段落都有說明它在做什麼，但要實際跑 bot 就需要一個。

```python
%%capture
%pip install -q "anthropic>=2.0.0" python-dotenv slack_bolt requests markdown-to-mrkdwn
```

```python
import io
import os
import threading
from getpass import getpass

import requests
from anthropic import Anthropic
from dotenv import load_dotenv, set_key
from markdown_to_mrkdwn import SlackMarkdownConverter
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv(override=True)

# Prompt for Slack tokens on first run and save them to .env.
for key in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
    if not os.environ.get(key):
        os.environ[key] = getpass(f"{key}: ")
        set_key(".env", key, os.environ[key])

client = Anthropic()
app = App(token=os.environ["SLACK_BOT_TOKEN"])

for key in ("ANALYST_ENV_ID", "ANALYST_AGENT_ID", "ANALYST_AGENT_VERSION"):
    if not os.environ.get(key):
        raise RuntimeError(f"{key} not set. Run data_analyst_agent.ipynb first.")

# Set these from the IDs saved by the data analyst notebook. Reusing
# the agent and environment avoids re-provisioning on every bot restart.
ANALYST_AGENT = {
    "id": os.environ["ANALYST_AGENT_ID"],
    "version": int(os.environ["ANALYST_AGENT_VERSION"]),
}
ANALYST_ENV_ID = os.environ["ANALYST_ENV_ID"]

# thread_ts -> session_id, so follow-ups land in the same session.
# Sessions stay open for replies. In production, persist this and
# archive sessions when threads go stale.
thread_sessions: dict[str, str] = {}

mrkdwn = SlackMarkdownConverter()
```

## 1. bot 被提及時啟動 session

Bolt 會把 `ack` callback 傳進每個 handler，呼叫它就是告訴 Slack 事件已收到。沒有確認的事件，Slack 會在[三秒後](https://docs.slack.dev/apis/events-api/#responding)重試，所以 `on_mention` 會立刻呼叫 `ack()`，並把耗時的工作（上傳檔案、建立 session、串流）交給背景 thread 裡的 `start_analysis`。

每次 mention 都會建立一個 session，你可以在 [Console](https://platform.claude.com/) 的 **Sessions** 底下打開它，看完整的 trace。

```python
@app.event("app_mention")
def on_mention(event, say, ack):
    ack()
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    # Mention text arrives as "<@BOTID> question"; drop the mention prefix.
    question = event["text"].split(">", 1)[-1].strip()
    slack_file = (event.get("files") or [None])[0]

    say(text="On it. Analyzing now.", thread_ts=thread_ts)
    # Run the slow work in a background thread so this handler
    # returns within Slack's 3s limit.
    threading.Thread(target=start_analysis, args=(channel, thread_ts, question, slack_file)).start()


def start_analysis(channel: str, thread_ts: str, question: str, slack_file: dict | None) -> None:
    try:
        # If the mention had a file attached, pull it from Slack and
        # re-upload to the Anthropic Files API so the session can mount it.
        resources = []
        if slack_file:
            resp = requests.get(
                slack_file["url_private"],
                headers={"Authorization": f"Bearer {app.client.token}"},
                timeout=30,
            )
            resp.raise_for_status()
            mime = slack_file.get("mimetype", "text/csv")
            uploaded = client.beta.files.upload(
                file=(slack_file["name"], io.BytesIO(resp.content), mime)
            )
            mount = "/mnt/session/uploads/data.csv"
            resources.append({"type": "file", "file_id": uploaded.id, "mount_path": mount})
            question += f"\n\nThe data is mounted at {mount}."

        # One session per Slack thread. Store the thread coordinates in
        # metadata so anyone reading the event stream knows where to reply.
        session = client.beta.sessions.create(
            environment_id=ANALYST_ENV_ID,
            agent={"type": "agent", **ANALYST_AGENT},
            resources=resources,
            # Titles are capped at 80 chars and can't contain Unicode
            # control/format characters (Slack sometimes inserts them).
            title="".join(c for c in question if c.isprintable())[:80],
            metadata={"slack_channel": channel, "slack_thread_ts": thread_ts},
        )
        thread_sessions[thread_ts] = session.id

        # Send the question as a user.message event. The agent starts
        # working immediately; relay_stream posts its progress to the thread.
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": question}]}],
        )
        relay_stream(session.id, channel, thread_ts)
    except Exception as e:
        app.client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=f"Analysis failed: {type(e).__name__}: {e}"
        )
```

## 2. 把進度和結果轉發到 thread

下面定義的 `relay_stream` 函式是兩邊 API 之間的橋梁：它讀取 Anthropic session 的事件 stream，並貼到 Slack。它會一直迴圈到 agent 進入 idle，然後貼出最後的摘要，並上傳 agent 寫出的所有檔案。

`files.list(scope_id=...)` 會回傳 session 裡的所有檔案，包括我們上傳的 CSV 和 agent 寫出的任何東西。我們過濾 `downloadable == True`，這樣只有 agent 產生的輸出（報告、圖表）會貼回 Slack，使用者自己的輸入不會。

```python
def relay_stream(session_id: str, channel: str, thread_ts: str) -> None:
    summary = ""
    posted_progress = False
    for ev in client.beta.sessions.events.stream(session_id):
        t = ev.type
        if t == "agent.message":
            # Keep the latest text block; it becomes the final summary.
            for b in ev.content:
                if b.type == "text" and b.text.strip():
                    summary = b.text
        elif t == "agent.tool_use" and not posted_progress:
            # Post a one-time progress update when the agent starts
            # running commands.
            app.client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text="Running analysis..."
            )
            posted_progress = True
        elif t == "session.status_idle":
            break
        elif t == "session.status_terminated":
            trace = f"https://platform.claude.com/sessions/{session_id}"
            app.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Session terminated unexpectedly. Trace: {trace}",
            )
            return

    # Turn is done. Post the summary, then upload any generated files.
    if summary:
        text = mrkdwn.convert(summary)
        if len(text) > 3900:  # Slack text limit ~4000 chars
            text = text[:3900] + "\n_(truncated)_"
        app.client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=text)
    outputs = client.beta.files.list(scope_id=session_id, betas=["managed-agents-2026-04-01"])
    for f in outputs.data:
        if not f.downloadable:
            continue
        content = client.beta.files.download(f.id).read()
        app.client.files_upload_v2(
            channel=channel, thread_ts=thread_ts, filename=f.filename, content=content
        )
```

## 3. 在同一個 session 處理後續回覆

在 thread 裡回覆會變成現有 session 的另一個回合，不需要再次 `@mention` bot。Container 的檔案系統和對話歷史會跨回合保留。

```python
def continue_session(session_id: str, channel: str, thread_ts: str, text: str) -> None:
    try:
        client.beta.sessions.events.send(
            session_id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": text}]}],
        )
        relay_stream(session_id, channel, thread_ts)
    except Exception as e:
        app.client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=f"Analysis failed: {type(e).__name__}: {e}"
        )


@app.event("message")
def on_thread_reply(event, ack):
    ack()
    thread_ts = event.get("thread_ts")
    # Only handle human replies in a thread where we already started
    # a session. Skip edits/deletes and other message subtypes.
    if event.get("subtype"):
        return
    if not thread_ts or event.get("bot_id") or thread_ts not in thread_sessions:
        return
    threading.Thread(
        target=continue_session,
        args=(thread_sessions[thread_ts], event["channel"], thread_ts, event["text"]),
    ).start()
```

## 4. 執行 bot

下面的 cell 會連上 Slack 並開始監聽。它在 bot 執行時會一直阻塞，做完後用 ■ 中斷按鈕停止。

在 bot 所在的任何 channel 提及它並附上 CSV。它會貼出進度，然後在 thread 裡貼出摘要和 `report.html`：

<img src="https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/managed_agents/example_data/slack_data_bot/slack_thread.png" alt="Slack thread showing the bot's analysis" width="600" />

在 thread 裡回覆，就能針對同一份資料深入追問。

```python
SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
```

## 下一步

你已經把分析 agent 包進 Slack bot：mention 會啟動 session，事件 stream 把進度轉發到 thread，輸出被上傳，回覆則延續同一段對話。

- 到 [`data_analyst_agent.ipynb`](data_analyst_agent.md) 換掉 agent 的 system prompt，就能改變它的分析風格。重跑那份 notebook 會建立新的 agent，並把它的 ID 存到 `.env` 讓 bot 讀取。
- 把 `thread_sessions` 存進資料庫，讓對話在 bot 重啟後仍然保留。
- 把 bot 搬出 notebook：把程式碼複製到 `.py` 檔，部署到任何能維持長時間 WebSocket 連線的地方。

## 重點整理
- Slack 事件要在三秒內 `ack`，耗時工作丟到背景 thread。
- `relay_stream` 是兩個 API 之間的橋：讀 Anthropic 的事件 stream，再貼到 Slack。
- 用 `downloadable == True` 過濾，只把 agent 產生的檔案貼回去。
- Thread 對應 session，所以後續回覆自然接續同一段對話和檔案系統。
- 想在重啟後保留對話，要把 thread 到 session 的對應存進資料庫。

## 練習
1. 在 `.env` 預先填好 token，重啟 bot 確認不再提示輸入。
2. 修改 `relay_stream` 的過濾條件，讓它只上傳 `report.html`，不貼圖表。
3. 把 `thread_sessions` 改成存到 SQLite 或 JSON 檔，重啟 bot 後驗證追問仍接續原 session。
