---
translated: true
source: examples/agents_api/sandboxes/databricks/README.md
---

# 在 Databricks Sandbox 上執行 OpenAI agents

> 原文：[examples/agents_api/sandboxes/databricks/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/sandboxes/databricks/README.md)

把 agent 的 tool 跑在 Databricks serverless sandbox 裡，由你的應用程式自己管理 sandbox 的建立與清理。

## 這篇在做什麼

示範怎麼讓 OpenAI Agents API 把程式碼和 tool 呼叫丟到 Databricks 的 serverless sandbox 裡執行。OpenAI 負責 agent 的調度，Databricks 提供隔離的運算環境。這篇走的是 application-managed 模式，sandbox 的生命週期全由你的應用程式用 Databricks SDK 控制。

## 學完你會

- 說得出 application-managed 流程每一步：建 session、開 sandbox、啟動 executor、跑 turn、清理。
- 知道 `codex exec-server` 為什麼要在 sandbox 裡持續執行，以及怎麼用 `execute_command_sync` 讓它在背景跑。
- 會處理 IP allowlist、stop/restart 和常見錯誤（401、403 等）的排查。

## 開跑前

- 需要 `OPENAI_API_KEY` 和另一把 `OPENAI_EXECUTOR_API_KEY`。
- 需要 Databricks workspace，且能使用 serverless sandbox。

[Databricks Sandbox](https://docs.databricks.com/aws/en/compute/serverless/sandbox) 現在支援 [OpenAI Agents API](https://developers.openai.com/api/docs/guides/agents-api/overview)，開發者可以在隔離的 serverless 環境執行 AI agent 的程式碼和 tool 呼叫，環境本身有 Databricks 的網路和治理控制。

整合之後，OpenAI 負責 agent 的 orchestration，Databricks Sandbox 提供隨需的運算資源，用來執行程式碼、操作 tool 和企業資源。開發者可以控制網路連線和檔案存取，讓 agent 的執行落在適合企業工作負載的環境裡。

這篇會走過 [application-managed](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle#start-an-environment) 的 sandbox 佈建方式：你的應用程式用 Databricks SDK 管理 sandbox 的整個生命週期，從建立、執行到清理。

## 運作方式

整個 session 由你的應用程式主導。它建立 agent session、佈建 sandbox、啟動 executor、跑 turn，最後全部拆掉，過程全是對外連線（連 OpenAI 和 Databricks SDK）。沒有東西需要接受 inbound 連線，所以應用程式可以跑在任何地方：筆電、Databricks job 或 notebook。

流程如下：

- 用 self-hosted environment 設定建立一個 agent session。
- 佈建 sandbox，輪詢狀態確認它已經在跑。sandbox 內建 codex binary。
- 在 sandbox 裡啟動 `codex exec-server`，它會對外連到 OpenAI，等待 tool 呼叫。
- 送出 input 並 stream 這個 turn，agent 會在 sandbox 裡執行 shell 和檔案 tool。
- 拆掉 session 和 sandbox。

![Application-managed Databricks sandbox sequence](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_api/sandboxes/databricks/images/databricks-sandbox.png)

## 用 Databricks SDK 的使用範例

agent session 用 OpenAI client 建立，`workspace_directory` 指向 sandbox 裡可寫入的路徑。sandbox 的生命週期管理和指令執行，則用 `databricks-sdk`。

`codex exec-server` 必須在整個 agent session 期間持續執行。應用程式可以用 `execute_command_sync` 以 detached 方式啟動這個 process，讓指令執行的 request 先回傳，codex process 繼續留在 sandbox 裡跑。

```python
import os

w = WorkspaceClient(profile="my-workspace")
app_key = os.environ["OPENAI_API_KEY"]                    # application key
executor_api_key = os.environ["OPENAI_EXECUTOR_API_KEY"]  # environment key -> CODEX_API_KEY


async with AsyncOpenAI(api_key=app_key) as client:
    # Create the self-hosted session first; it returns the environment to connect back to.
    session = await client.beta.agents.sessions.create(
        agent={"model": "gpt-5.6-sol"},
        environment={"type": "self_hosted", "workspace_directory": WORK_DIR},
    )

    # Provision the sandbox via databricks-sdk.
    # Sandboxes typically become ready within sub-seconds.
    sandbox = w.sandbox.create_sandbox(
        Sandbox(
            spec=SandboxSpec(
                compute=ComputeSpec(inactivity_timeout=Duration(seconds=900)))
        ),
        sandbox_id="openai-agent-sandbox",
    )
    name = sandbox.name

    # Launch codex exec-server detached, using the session's environment id/URL.
    remote_url = session.environment.remote_url
    environment_id = session.environment.id
    w.sandbox.execute_command_sync(
        name, "/bin/bash",
        args=["-lc", f"CODEX_HOME=$(mktemp -d) setsid nohup codex exec-server "
              f"--remote {remote_url} --environment-id {environment_id} </dev/null >log 2>&1 & echo pid=$!"],
        envs={"CODEX_API_KEY": executor_api_key},
    )

    # Submit input and stream the turn.
    async with client.beta.agents.sessions.stream(session.id, input=task) as events:
        async for event in events:
            ...  # agent runs tools in the sandbox and streams output
```

完整可執行的範例看 [application-managed example](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/sandboxes/databricks/application_managed/README.md)。

## 前置條件與限制

- 一把 OpenAI application key（`OPENAI_API_KEY`），用來建立 session 和送 input。
- 另一把 OpenAI executor key（`OPENAI_EXECUTOR_API_KEY`），organization、project 和使用者或 service account 要跟 session 相同。它會當成 `CODEX_API_KEY` 傳給 sandbox 裡的 codex。
- 如果你的 OpenAI organization 強制使用 IP allowlist，必須把 sandbox 的 egress IP 加進去，否則 Managed Agents 會拒絕未登記 IP 的流量。需要加入 allowlist 的 Databricks IP 清單看 [Databricks Outbound IPs](https://docs.databricks.com/aws/en/resources/ip-domain-region#outbound-ips)。

## 結束一個 turn

當 session stream 回報主 agent 的 turn 已完成、失敗或被取消，這個 turn 就結束了。需要的結果先用 `execute_command_sync` 從 sandbox 讀回來，再清理資源：停掉 executor、刪除 session、刪除 sandbox。

## 在 turn 之間停止與重啟 sandbox

想在 turn 之間省運算資源，可以在 turn 結束後用 `w.sandbox.stop_sandbox(name)` 停掉 sandbox，下一個 turn 前用 `w.sandbox.start_sandbox(name)` 再啟動。

sandbox 的持久 home（`/home/sandbox-agent`）在 stop 和 start 之間會保留，這個目錄下的檔案都不會掉。但 `codex exec-server` process 在 sandbox 停止時會被殺掉，重啟之後要重新啟動它，才能重新連上 agent session。

sandbox 也可以設定閒置超過 `ComputeSpec.inactivity_timeout` 就自動停止。要關掉自動停止，把 `inactivity_timeout` 設成 0 或不設定。

## 網路

sandbox 的 outbound egress 沒有限制，inbound ingress 全部關閉，目前兩者都不能設定。

如果你的 OpenAI organization 強制 IP allowlist，要加入 sandbox 的 outbound egress IP（看 [Databricks Outbound IPs](https://docs.databricks.com/aws/en/resources/ip-domain-region#outbound-ips)）。sandbox 運行期間 egress IP 是穩定的，但經過 stop 再 restart 之後可能會變。

## 監控

executor 會在 sandbox 裡寫 log，可以用 `execute_command_sync` 讀（tail exec-server 的 log），看註冊和連線狀態或錯誤。

要看 sandbox 狀態，用 `w.sandbox.get_sandbox(name).status.state`。

## 疑難排解

| Symptom | What to check |
| --- | --- |
| Executor rejected with `401 ... IP is not authorized` | The sandbox egress IP is not on your OpenAI organization allowlist (if your org enforces one). Add it, then re-check after a restart - the egress IP can change across stop/restart. |
| Executor rejected with `403 missing required scope api.agents.environments.connect` | The executor is using a general API key. Create a dedicated environment key on the OpenAI Agents tab and pass it as `CODEX_API_KEY`. |
| `codex exec-server` exits right after launch | Tail the executor log in the sandbox. Check the environment id, remote URL, key ownership, and outbound network access. |
| Agent reports that shell or filesystem tools are unavailable | `workspace_directory` does not exist or is not writable. Create it (under `/home/sandbox-agent`) before the turn. |

## 相關資源

- [Databricks Sandbox documentation](https://docs.databricks.com/aws/en/compute/serverless/sandbox)
- [Sandbox SDK on databricks-sdk for Python](https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sandbox/sandbox.html)
- [Running commands in sandboxes](https://databricks-sdk-py.readthedocs.io/en/latest/sandbox-command-execution.html)
- [OpenAI Agents API, self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)

## 重點整理

- application-managed 模式下，應用程式全程主導，只有對外連線，不需要接受 inbound。
- OpenAI 管 agent 調度，sandbox 只負責執行 tool，兩邊靠 `codex exec-server` 的外連串起來。
- application key 和 executor key 是兩把不同的 key，executor key 需要專用的 environment scope。
- sandbox 停止後 `/home/sandbox-agent` 的檔案會留著，但 exec-server process 會消失，要重新啟動。
- 有 IP allowlist 的組織要記得 egress IP 在 restart 後可能會變。

## 練習

1. 照流程圖把五個步驟各對應到一段程式碼，寫在註解裡，確認你知道每一步用的是 OpenAI client 還是 Databricks SDK。
2. 在 turn 結束後，用 `execute_command_sync` 讀 `workspace_directory` 底下的檔案內容，並印出來。
3. 在兩個 turn 之間加上 `stop_sandbox` 和 `start_sandbox`，restart 之後重新啟動 `codex exec-server`，驗證 home 目錄的檔案還在。
