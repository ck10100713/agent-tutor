---
translated: true
source: examples/chatgpt/workspace_agents/workspace-agents-api-trigger.ipynb
---
# 用 API 觸發 Workspace Agent

> 原文：[examples/chatgpt/workspace_agents/workspace-agents-api-trigger.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/workspace_agents/workspace-agents-api-trigger.ipynb)

設定一個 Workspace Agent，加上 API channel，再送出一個真實的 trigger，讓 agent 把結果寫到它設定好的目的地。

## 這篇在做什麼

這篇示範怎麼從外部系統用 HTTP 請求啟動一個存在 ChatGPT 裡的 Workspace Agent。你會送一筆事件、確認 trigger 被接受，再去 agent 的目的地確認結果有寫進去。API 只負責啟動，之後做什麼由 agent 的 instructions、app 權限和核准設定決定。

## 學完你會

- 建立一個 Workspace Agent，加上 API channel，拿到 `agtch_...` 開頭的 trigger ID
- 用 Python 標準函式庫對 trigger endpoint 送 `POST`，帶上 access token、`conversation_key` 和 `Idempotency-Key`
- 看懂 202、401、403、404、409 各代表什麼，並到目的地驗證 agent 真的有寫入

## 開跑前

- 要有啟用 Workspace Agents 的 ChatGPT workspace，並有建立和分享 agent 的權限
- 一個存好的 Workspace Agent，且有一個它能寫入的目的地（channel、文件、email、ticket 都可以）
- 一組帶 Workspace Agents scope 的 access token（不是 OpenAI Platform API key）

Workspace Agents 讓團隊把重複的工作存在 ChatGPT 裡：instructions、連接的 context、app 動作、核准流程和輸出格式。API trigger 則讓另一個系統在 ChatGPT 之外有工作開始時，去啟動這個存好的流程。

這份 notebook 會送出一筆來源事件，確認 trigger 被接受，再到 agent 的目的地確認結果。API 負責啟動 run，接下來發生什麼由 instructions、app 權限和核准設定控制。

*API 觸發的 run 是非同步的。endpoint 只會把 run 排進佇列，不會回傳 agent 完成後的回覆。*


## 你會做出什麼

做完之後，你會有一個存好的 Workspace Agent、一個帶 `agtch_...` trigger ID 的 API channel，還有一段能對你的 agent 真實執行的 Python trigger 呼叫。


## 前置需求

執行真實 trigger 的 cell 之前，你需要：

| 需要什麼 | 參考文件 |
| --- | --- |
| 在支援的 ChatGPT workspace 啟用 Workspace Agents，並有建立與分享 agent 的權限 | [ChatGPT Workspace Agents guide](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business) |
| 一個存好的 Workspace Agent，有一個可寫入的目的地 | [Create and manage Workspace Agents](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business) |
| 該 agent 上的 API channel 和它的 `agtch_...` trigger ID | [Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs) |
| 一組帶 Workspace Agents scope 的 Workspace Agent access token | [Authenticate with Workspace Agent access tokens](https://developers.openai.com/workspace-agents/authentication) |
| 能送 HTTPS `POST` 請求的 notebook 或後端環境 | 這份 notebook 只用 Python 標準函式庫，不需要 OpenAI Platform SDK |

有一個非同步的細節要記得：HTTP 請求會在 agent 做完之前就回來。目的地可以是 agent 能寫入的任何已連接 app 或介面，例如 channel、文件、email 或 ticket。

目前的方案和地區支援請看 Help Center。


## 架構

來源系統決定什麼時候開始工作。Workspace Agent 用它的 instructions、context、app 和核准設定，決定存好的流程怎麼跑。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/business-technical-bridge.svg" alt="Flow from source event to backend, API trigger, Workspace Agent, and output" width="80%" />
</p>

*後端啟動 run，agent 照存好的流程執行並寫出結果。*


## 1. 寫 agent 的 instructions

API trigger 只負責啟動 run。接下來做什麼，要靠 Workspace Agent 的 instructions 告訴它。

| instructions 決定 | app 設定決定 |
| --- | --- |
| 要用哪個目的地 | app 能不能存取那個目的地 |
| 要寫什麼輸出 | 寫入動作是否可用 |
| 要直接做還是先問 | 寫入前是否需要核准 |

這個 demo 的 instructions 要很窄：讀來源事件、對目的地寫一則更新、並附上 request ID 方便你驗證。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent_instructions.png" alt="Workspace Agent builder showing channels, connected apps, files, and instructions" width="80%" />
</p>

*用 instructions 區塊把目的地、寫入行為和核准預期寫清楚。*


```python
agent_builder_prompt = """
Create a Workspace Agent that writes API-triggered updates to the configured destination.

When the agent receives an API-triggered run:
1. Find the request ID, source system, output destination, and update text in the input.
2. Write one short update to that destination if the connected app allows it.
3. Start the update with: Workspace Agent API demo received: <Request ID>
4. Include the source system, submitted timestamp, and update text if present.
5. After the write succeeds, stop.

Use the exact destination named in the input or saved in these instructions.
Do not assume the API-triggered run has a current chat, channel, thread, or document context.
If write approval is required, request approval. If the destination is unavailable, say that the output destination could not be reached.
""".strip()

print(agent_builder_prompt)
```

加 API trigger 之前，先在 Preview 測一次實際行為。貼一段含 request ID、目的地和更新文字的範例訊息。如果 Preview 寫不進目的地，API trigger 也一樣寫不進去。


## 2. 連接一個輸出目的地

選一個風險低、agent 能寫入的目的地：channel、文件、email、ticket 或其他已連接的 app。測試 API trigger 之前，先設定好 app 連線，並決定寫入是否要核准。

低風險的 demo 目的地可以自動核准寫入。風險較高的寫入要維持需要核准。

| 驗證方式 | 適用時機 | 要注意 |
| --- | --- | --- |
| End-user account | 每個執行 agent 的人要用自己的 app 權限 | API 觸發的流程可能要求呼叫者本身有對應的 app 權限 |
| Agent-owned account | 流程需要固定的共用連線，例如團隊 channel、共用文件或共用信箱 | 盡量用 service account，除非清楚風險，不要用個人帳號 |


```python
api_output_instructions = """
When triggered by API, write one short update to the configured destination.
Always include the request ID from the trigger input.

Start the update with: Workspace Agent API demo received: <Request ID>
Include the source system, submitted timestamp, and update text if present.
Use the exact destination named in the input or saved in these instructions.
Do not assume the API-triggered run has a current chat, channel, thread, or document context.
If writes are auto-approved for this destination, write immediately. If approval is required, request approval.
After the write succeeds, stop.
""".strip()

print(api_output_instructions)
```

## 3. 加上 API channel

在 Workspace Agent builder 開啟 agent，加一個 API channel、存檔、複製 trigger ID，並確認 ID 是 `agtch_` 開頭。

把 agent 分享給會拿 access token 來呼叫 API 的使用者。trigger ID 放在 API 路徑裡，它跟 agent 名稱是兩回事。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/api_channel.png" alt="API channel with trigger ID" width="80%" />
</p>

*這個 API channel ID 就是 trigger endpoint 要用的。*


## 4. 設定真實呼叫

你需要兩個值：

| 值 | 從哪來 |
| --- | --- |
| API trigger ID | agent 的 API channel，格式是 `agtch_...` |
| Workspace Agent access token | ChatGPT 的 `Admin > Access tokens`，要帶 Workspace Agents scope |

對 `https://api.chatgpt.com` 要用 Workspace Agent access token，不是 OpenAI Platform API key。token 擁有者必須有權限執行這個被分享的 agent，不然 API 會回 `403 Forbidden`。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/access_token.png" alt="Access token settings with Workspace Agents scope" width="80%" />
</p>

*token 當成 secret 存放，不要貼進 notebook 程式碼。*


要真實執行的話，開 notebook 之前先匯出這些值：

```bash
export WORKSPACE_AGENT_TRIGGER_ID="agtch_..."
export WORKSPACE_AGENT_ACCESS_TOKEN="<workspace-agent-access-token>"
export WORKSPACE_AGENT_OUTPUT_DESTINATION="output-destination"

jupyter notebook  # or jupyter lab
```

`WORKSPACE_AGENT_OUTPUT_DESTINATION` 是選填。它只是在 trigger input 裡標示目的地名稱，實際能不能存取還是看 agent 連接的 app。


```python
import json
import os
import textwrap
import urllib.error
import urllib.request
from datetime import datetime, timezone


def read_env(name: str, default: str = "") -> tuple[str, str]:
    value = os.environ.get(name, "").strip()
    if value:
        return value, "environment"
    return default, "default" if default else "missing"


TRIGGER_ID, trigger_id_source = read_env("WORKSPACE_AGENT_TRIGGER_ID")
ACCESS_TOKEN, access_token_source = read_env("WORKSPACE_AGENT_ACCESS_TOKEN")
OUTPUT_DESTINATION, output_destination_source = read_env(
    "WORKSPACE_AGENT_OUTPUT_DESTINATION",
    "the agent's configured destination",
)
API_BASE = "https://api.chatgpt.com/v1"

print(f"Trigger ID configured: {bool(TRIGGER_ID)} ({trigger_id_source})")
print(f"Access token configured: {bool(ACCESS_TOKEN)} ({access_token_source})")
print(f"Output destination label: {OUTPUT_DESTINATION} ({output_destination_source})")

if ACCESS_TOKEN.startswith("sk-"):
    print("Warning: this looks like an OpenAI Platform API key. Create a ChatGPT Workspace Agent access token from Admin > Access tokens instead.")

if OUTPUT_DESTINATION == "the agent's configured destination":
    print("Tip: set WORKSPACE_AGENT_OUTPUT_DESTINATION when you want the API input to name a specific destination.")
```

## 5. 送出一筆來源事件

第一次的 input 保持簡單：來源系統送一筆事件，Workspace Agent 對目的地寫一則更新。


```python
run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

source_event = {
    "request_id": f"DEMO-{run_stamp}",
    "submitted_at": datetime.now(timezone.utc).isoformat(),
    "source_system": "notebook demo",
    "update_text": "The API trigger reached the Workspace Agent and asked it to write this update.",
    "output_destination": OUTPUT_DESTINATION,
}

source_event
```

呼叫 trigger endpoint 之前，先把來源事件轉成純文字。API 只是把事件傳給 agent，寫入行為由 agent 存好的 instructions、app 權限和核准設定控制。


```python
def build_agent_input(event: dict) -> str:
    return textwrap.dedent(f"""
    Request ID: {event['request_id']}
    Source system: {event['source_system']}
    Submitted at: {event['submitted_at']}
    Output destination: {event['output_destination']}
    Update text: {event['update_text']}

    Please write this update to the configured destination.
    Start with exactly: Workspace Agent API demo received: {event['request_id']}
    """).strip()


agent_input = build_agent_input(source_event)
print(agent_input)
```

如果多筆事件要接續同一段 agent 對話（例如同一個 request 的多次更新），用 `conversation_key`。

要重試的話，送 `Idempotency-Key` header。只有在重試同一筆來源事件時，才重複使用同一個 key。


```python
conversation_key = f"workspace-agent-api-demo-{source_event['request_id']}"
idempotency_key = f"workspace-agent-api-demo-{source_event['request_id']}-v1"

payload = {
    "conversation_key": conversation_key,
    "input": agent_input,
}

print(json.dumps(payload, indent=2))
print("Idempotency-Key:", idempotency_key)
```

## 6. 用 API 觸發 agent

Endpoint：

```http
POST https://api.chatgpt.com/v1/workspace_agents/{id}/trigger
```

必填與建議的請求欄位：

| 位置 | 欄位 | 必填 | 說明 |
| --- | --- | --- | --- |
| Path | `id` | 是 | agent 的 API channel 的 trigger ID，格式 `agtch_...` |
| Header | `Authorization` | 是 | 用 Workspace Agent access token 的 Bearer 憑證 |
| Header | `Content-Type` | 是 | 用 `application/json` |
| Header | `Idempotency-Key` | 建議 | 重試同一筆來源事件用的固定 key |
| Body | `input` | 是 | 當作 trigger input 傳給 agent 的訊息文字 |
| Body | `conversation_key` | 否 | 呼叫端自訂的固定 ID，用來接續同一段 agent 對話 |


```python
def trigger_workspace_agent(trigger_id: str, access_token: str, payload: dict, idempotency_key: str) -> dict:
    url = f"{API_BASE}/workspace_agents/{trigger_id}/trigger"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return {"ok": True, "status": response.status, "error": None}
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed_error = json.loads(error_body).get("error", {})
        except json.JSONDecodeError:
            parsed_error = {"message": error_body}
        return {"ok": False, "status": exc.code, "error": parsed_error}


def print_trigger_error(result: dict) -> None:
    status = result.get("status")
    error = result.get("error") or {}
    message = error.get("message", "Unknown error")
    code = error.get("code")

    print(f"Workspace Agent trigger failed: HTTP {status}")
    print("Message:", message)
    if code:
        print("Code:", code)

    if status == 401:
        print()
        print("Fix: create a fresh ChatGPT Workspace Agent access token from Admin > Access tokens with the Workspace Agents scope.")
        print("Do not use an OpenAI Platform API key from platform.openai.com for this endpoint.")
    elif status == 403:
        print()
        print("Fix: the token is valid, but the token owner cannot trigger this agent. Share the agent with that user or use a token from an allowed owner.")
    elif status == 404:
        print()
        print("Fix: confirm the API channel trigger ID starts with agtch_ and belongs to an agent visible to the token owner.")
    elif status == 409:
        print()
        print("Fix: save/publish the agent and confirm the API channel is active and runnable.")


if not TRIGGER_ID or not ACCESS_TOKEN:
    print("No live request sent.")
    print("Set WORKSPACE_AGENT_TRIGGER_ID and WORKSPACE_AGENT_ACCESS_TOKEN before starting the kernel.")
else:
    result = trigger_workspace_agent(TRIGGER_ID, ACCESS_TOKEN, payload, idempotency_key)
    if not result["ok"]:
        print_trigger_error(result)
    else:
        status = result["status"]
        print("HTTP status:", status)
        assert status == 202, f"Expected 202 Accepted, got {status}"
        print("Trigger accepted. Look in the configured destination for the result.")
        print("Search for request ID:", source_event["request_id"])
        print("Expected output destination:", source_event["output_destination"])
```

`202 Accepted` 代表 trigger 已被接受處理，不代表 agent 已經做完。API 不會回傳 body、公開的 run ID 或 agent 最終輸出。

第一次真實執行時，確認三件事：`HTTP status: 202`、一個唯一的 request ID、以及目的地出現以 `Workspace Agent API demo received:` 開頭的更新。

如果 trigger 成功但什麼都沒寫入，要查的是 agent 設定，不是 HTTP 請求。通常是這幾項缺了一個：目的地的 instructions、app 權限、app 驗證，或預期中的核准設定。

重複測試 notebook 時，request ID 和 idempotency key 都要產生新的。對同一筆來源事件重用同一個 `Idempotency-Key`，可能回傳原本已接受的結果，而不是排入新的 run。


## 7. 改成適合後端 worker 的呼叫

上面的真實呼叫是最小測試。下面的 helper 把同樣的請求包起來，給後端 worker、排程工作或 workflow engine 用。

同一筆來源事件要讓 `conversation_key` 和 `Idempotency-Key` 保持固定，這樣重試才不會排入重複的 run。


```python
def build_backend_trigger_request(event: dict) -> dict:
    """Create the Workspace Agent trigger request from a source-system event."""
    request_id = event["request_id"]
    return {
        "trigger_id": TRIGGER_ID,
        "payload": {
            "conversation_key": f"workspace-agent-api-demo-{request_id}",
            "input": build_agent_input(event),
        },
        "idempotency_key": f"workspace-agent-api-demo-{request_id}-v1",
    }


def handle_source_event(event: dict, *, live: bool = False) -> dict:
    """Preview or send the backend trigger call."""
    trigger_request = build_backend_trigger_request(event)
    result = {
        "request_id": event["request_id"],
        "conversation_key": trigger_request["payload"]["conversation_key"],
        "idempotency_key": trigger_request["idempotency_key"],
        "queued": False,
        "status": None,
    }

    if live:
        if not TRIGGER_ID or not ACCESS_TOKEN:
            raise RuntimeError("Set WORKSPACE_AGENT_TRIGGER_ID and WORKSPACE_AGENT_ACCESS_TOKEN before live=True.")
        trigger_result = trigger_workspace_agent(
            trigger_request["trigger_id"],
            ACCESS_TOKEN,
            trigger_request["payload"],
            trigger_request["idempotency_key"],
        )
        result["status"] = trigger_result["status"]
        result["queued"] = trigger_result["ok"] and trigger_result["status"] == 202
        if not trigger_result["ok"]:
            result["error"] = trigger_result["error"]

    return result


backend_preview = handle_source_event(source_event, live=False)
print(json.dumps(backend_preview, indent=2))
```

正式環境要記錄來源 request ID、trigger ID、idempotency key、時間戳和 HTTP status。不要記錄 access token 或敏感的請求內容。


## 8. 驗證目的地的動作

API 不會回傳完成的回覆，所以要到 agent 的目的地確認動作。檢查 trigger input 裡指定的、或 agent instructions 裡存的那個目的地。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/api-trigger-check.svg" alt="API trigger flow showing accepted request and destination check" width="80%" />
</p>

*HTTP 回應只告訴你 trigger 收到了，實際的工作要去目的地驗證。*


到設定好的目的地搜尋真實 trigger cell 印出來的 request ID。更新應該以這段開頭：

```text
Workspace Agent API demo received: DEMO-20260618010101
```

到這裡，整條路徑都通了：trigger、token、分享、instructions、app 權限和核准行為。

如果 trigger 成功但沒有輸出，先查這些：

| 檢查 | 要確認什麼 |
| --- | --- |
| Preview | 貼上完全一樣的 `agent_input` 文字，確認 agent 會寫入目的地 |
| 目的地 | 啟動 kernel 之前，把 `WORKSPACE_AGENT_OUTPUT_DESTINATION` 設成確切的目的地名稱 |
| 權限 | 確認連接的 app 在 API 觸發的 run 中能寫入該目的地 |
| 核准 | 如果 demo 要自動寫入，確認寫入動作是自動核准 |
| 存取 | 確認 token 擁有者能執行這個 agent，且存好的 API channel 是啟用狀態 |

接下來把 `source_event` 換成任何後端事件即可。API 呼叫不變，agent 擁有者在 ChatGPT 裡更新 instructions、目的地和核准行為。


上線前先跑一個小型測試矩陣：

| 測試 | 預期結果 |
| --- | --- |
| 正常流程 | agent 把 `Workspace Agent API demo received: <request_id>` 寫到設定好的目的地 |
| 缺 request ID | agent 會要求提供 request ID，不會寫出意義不明的更新 |
| 用同一個 idempotency key 重複重試 | API 回傳原本已接受的結果，不會排入第二個 trigger 事件 |
| 未被分享的使用者的 token | API 回 `403 Forbidden` |
| trigger ID 錯誤 | API 回 `404 Not Found` |
| agent 或目的地無法執行 | API 回 `409 Conflict` |


## 錯誤處理

trigger endpoint 可能回傳：

| 狀態 | 意思 | 該怎麼做 |
| --- | --- | --- |
| `202 Accepted` | 請求已接受處理 | 到設定好的目的地驗證結果 |
| `401 Unauthorized` | token 缺少、過期、被撤銷、無效，或憑證類型錯誤 | 從 `Admin > Access tokens` 建立帶 Workspace Agents scope 的 ChatGPT Workspace Agent access token。不要用 OpenAI Platform API key |
| `403 Forbidden` | token 有效，但不能觸發這個 agent | 把 agent 分享給呼叫者，或改用被允許的使用者的 token |
| `404 Not Found` | trigger ID 不存在，或對呼叫者不可見 | 確認 API channel 上的 `agtch_` ID |
| `409 Conflict` | agent 或 API channel 無法執行 | 儲存或發布 agent，並確認 API channel 是啟用狀態 |
| `202 Accepted`，但沒有輸出 | trigger 成功，但 agent 沒有寫入目的地 | 檢查 instructions、app 驗證、目的地權限和寫入核准設定 |

遇到暫時性的網路失敗，用同一個 `Idempotency-Key` 重試同一筆來源事件。如果是不同的來源事件，就產生新的 idempotency key。


## 上線檢查清單

從試行階段擴大之前，先把四件事鎖好：

| 面向 | 檢查 |
| --- | --- |
| Auth | 存放並定期輪換 access token。選一個讓 run 歸屬清楚的 token 擁有者 |
| Access | 只把 agent 分享給允許的使用者或群組，確認連接的 app 能寫入目的地 |
| Behavior | 在 agent instructions 裡明確寫出目的地、輸出格式和核准行為 |
| Operations | 帶上來源事件 ID、監控非 202 的回應、留意缺少輸出的情況 |

只對低風險的寫入使用自動核准。敏感的寫入要維持需要核准，直到流程跟業務負責人一起檢視過。


## 什麼時候用這個模式

當工作應該由業務團隊擁有的 Workspace Agent 來做，但由另一個系統來啟動時，就用 API trigger。

| 適合用這個模式 | 該用別的做法 |
| --- | --- |
| 非技術的負責人要自己維護流程的 instructions | 呼叫端需要在 HTTP 回應裡拿到完成的答案 |
| 工作從表單、ticket、CRM 紀錄、排程工作或後端事件開始 | 來源系統需要低延遲的同步行為 |
| 結果可以寫到已連接的 app、channel、文件或 email | agent 的輸出沒有可長期保存的目的地 |
| instructions 和核准設定足以安全地控制寫入行為 | 流程影響很大，卻缺少審查、稽核或回滾機制 |

這就是分工方式：業務團隊在 ChatGPT 裡調整 agent，工程團隊負責讓來源系統的 trigger 保持穩定。


## 延伸這個模式

當工作從 ChatGPT 之外開始，但要透過可重複使用的 Workspace Agent 執行時，都可以用同樣的模式：

| 流程 | 來源事件 | agent 輸出 |
| --- | --- | --- |
| 會議後續追蹤 | 會議錄影或逐字稿準備好 | 待辦事項和後續追蹤草稿 |
| 依行事曆準備 | 找到 Google Calendar 事件或即將到來的會議行程 | 簡報文件或準備摘要 |
| 進站 lead 篩選 | CRM lead 或表單提交 | 帳戶摘要和業務任務 |
| 客服升級 | 建立高優先度 ticket | 升級摘要和後續步驟 |
| 員工支援 | 開啟 helpdesk ticket | 分流回答或升級路徑 |
| 每週報表 | 排程工作找到新紀錄 | 摘要文件或團隊更新 |

從一個窄的流程、一個明確的來源事件、一個輸出目的地開始。等 agent 的行為穩定了，再加更多目的地、更豐富的 context，或需要核准的動作。


## 延伸閱讀

- [Building workspace agents in ChatGPT to complete repeatable, end-to-end work](https://developers.openai.com/cookbook/articles/chatgpt-agents-sales-meeting-prep)
- [ChatGPT Workspace Agents for Enterprise and Business](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)
- [Trigger workspace agent runs](https://developers.openai.com/workspace-agents/trigger-runs)
- [Authenticate with Workspace Agent access tokens](https://developers.openai.com/workspace-agents/authentication)


## 重點整理

- API trigger 只負責啟動，agent 做什麼取決於 instructions、app 權限和核准設定
- 呼叫是非同步的，202 只代表被接受，結果要去目的地驗證
- 用 `Idempotency-Key` 讓重試安全，用 `conversation_key` 接續同一段對話
- 要用 Workspace Agent access token，不是 Platform API key，而且 token 擁有者要能執行這個 agent
- trigger 成功但沒輸出時，先查 agent 設定，不要先懷疑 HTTP 請求

## 練習

1. 改動 `source_event` 的內容（例如換成一筆假的 ticket 事件），重新產生 request ID 和 idempotency key，確認目的地有寫入新的更新。
2. 故意把 trigger ID 改錯一個字元，或換成沒被分享的使用者的 token，確認你拿到 404 或 403。
3. 在後端 worker 的 helper 裡加上 log（source request ID、trigger ID、idempotency key、timestamp、HTTP status），並確認不會把 access token 印出來。
