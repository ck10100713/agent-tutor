---
translated: true
source: examples/agents_api/sandboxes/aws/README.md
---
# 在 AWS Lambda MicroVMs 上跑 Agents API sandbox

> 原文：[examples/agents_api/sandboxes/aws/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/sandboxes/aws/README.md)

在 AWS Lambda MicroVMs 裡執行 agent 的 tool，支援由應用程式或 webhook 管理的佈建、檔案傳輸，以及 suspend/resume。

## 這篇在做什麼
讓 agent 的 tool 跑在你自己 AWS 帳號的 Lambda MicroVM 裡：OpenAI 跑 agent harness，每個 MicroVM 跑 `codex exec-server` 並保存 session 的 workspace 檔案。你先建一個可重用的 image，再選「應用程式管理」或「webhook 管理」兩種方式來啟動 MicroVM。

## 學完你會
- 建出含 Codex CLI 和 AWS lifecycle hook（ready、run、suspend、resume、terminate 等）的 MicroVM image。
- 用 `RunMicrovm` 直接啟動，或用 API Gateway 加 launcher Lambda 接 `agent.session.action_required` webhook 自動啟動。
- 在 turn 結束時正確終止 MicroVM，並用 suspend/resume 讓 workspace 檔案在多個 turn 之間保留。

## 開跑前
- 有 Lambda MicroVMs 存取權的 AWS 帳號，AWS CLI 要包含 `lambda-microvms`，憑證要能建立 S3 bucket、IAM role、CloudWatch log group 並建置、執行 MicroVM。
- `OPENAI_API_KEY`，加上另一把 environment key（`OPENAI_EXECUTOR_API_KEY`），存在 Secrets Manager。
- 一個只能讀 environment-key secret 的 MicroVM execution role。

使用 [AWS Lambda MicroVMs](https://docs.aws.amazon.com/lambda/latest/dg/microvms-getting-started.html) 在你自己的 AWS 帳號裡執行 agent 的 tool。OpenAI 跑 agent harness；每個 MicroVM 跑 `codex exec-server` 並保存 session 的 workspace 檔案。

先建一個 image，再執行[應用程式管理](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/sandboxes/aws/application_managed/README.md)或 [webhook 管理](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/sandboxes/aws/webhook_managed/README.md)的範例。兩者用同一個 image 和同樣的憑證。

每個範例都會請 agent 寫入 `hello.txt`，然後下載並檢查它。用 `--suspend-resume` 可以驗證檔案在 turn 之間不會消失。

## 運作方式

在 webhook 路徑裡，你的應用程式建立自架 session 並送出 input。session 需要 executor 時，OpenAI 會送出帶有 `environment_connection` action 的 `agent.session.action_required`。[API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api.html) 把 webhook 送到 launcher [Lambda](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)，它會驗證簽章、檢查目前的 session，並啟動 MicroVM。

MicroVM 的 `/run` hook 從 [Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html) 取得 environment key 並啟動 executor。executor 主動向外連到 OpenAI，等待中的 input 就會繼續處理。你的應用程式跟著 session stream、下載輸出檔案，並在最後一個 turn 之後終止 MicroVM。

![The application sends input to Agents API. A connection-required webhook flows through API Gateway and a launcher Lambda to an AWS Lambda MicroVM. The launcher uses a reusable image; the VM reads its environment key from Secrets Manager and connects outbound to OpenAI. The application retrieves output files.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_api/sandboxes/aws/images/aws-microvm-sandboxes.webp)

## 開始之前

- **AWS 存取：** 有 Lambda MicroVMs 存取權的帳號，且 AWS CLI 要包含 `lambda-microvms`。建置腳本會建立 S3 artifact bucket、IAM image build role 和 CloudWatch log group。你的 AWS 憑證需要有建立這些資源以及建置、執行 MicroVM 的權限。背景知識請見 AWS 的[入門指南](https://docs.aws.amazon.com/lambda/latest/dg/microvms-getting-started.html)。
- **Application key：** 用 `OPENAI_API_KEY` 建立 session 和送出 input。
- **Environment key（`OPENAI_EXECUTOR_API_KEY`）：** 另外建立一把 [environment key](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication)，organization、project 和使用者或 service account 的歸屬要一致。把它的值存在 Secrets Manager，例如名為 `codex/agents-api/executor` 的 secret。`/run` hook 會把它當作 `CODEX_API_KEY` 傳給 Codex。
- **MicroVM execution role：** 只允許這個 role 讀取 environment-key 的 secret。如果用客戶自管的 KMS key，要加上解密權限。role 的設定請見 AWS 的[安全與權限](https://docs.aws.amazon.com/lambda/latest/dg/microvms-security.html)。

application key 和 webhook signing secret 要放在 MicroVM 外面。webhook launcher 需要把這些憑證放在它自己的 Secrets Manager secret；VM 只會拿到它的 environment-key secret 的 ARN。

## 準備可重用的 image

建一個 image，裡面有 [Codex CLI](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#prepare-your-environment)、tool 的相依套件、像 `/workspace` 這樣的工作目錄，以及一個處理 AWS lifecycle hook 的 HTTP server。

| Hook                                    | Behavior                                                                                              |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `/aws/lambda-microvms/runtime/v1/ready` | Return HTTP 200 when the server is ready for AWS to snapshot. Leave the executor disconnected.        |
| `/aws/lambda-microvms/runtime/v1/run`   | Read the session connection values and secret ARN, fetch the environment key, and start the executor. |
| `/aws/lambda-microvms/runtime/v1/validate` | Check that Codex runs and the workspace is writable. |
| `/aws/lambda-microvms/runtime/v1/suspend` | Stop the executor and flush writes before AWS snapshots the VM. |
| `/aws/lambda-microvms/runtime/v1/resume` | Fetch the key again and restart the executor for the same environment. |
| `/aws/lambda-microvms/runtime/v1/terminate` | Stop the executor and flush writes before termination. |

把 `Dockerfile` 和 hook server 打包成 S3 artifact，然後用 8 GB 記憶體（4 vCPU 基準）建置 `codex-executor`。建置腳本會在 8080 port 啟用這些 hook。session ID、憑證和即時的 executor 連線不要放進可重用的 image snapshot。建置和 hook 設定請見 AWS 的 [MicroVM images](https://docs.aws.amazon.com/lambda/latest/dg/microvms-images.html)。

啟動時，你的應用程式或 launcher 會把這些值序列化成 JSON，放在 `runHookPayload`：

| Value                            | Purpose                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| `session.environment.id`         | Identifies the environment the executor connects to.               |
| `session.environment.remote_url` | Provides the executor's OpenAI connection URL.                     |
| Environment-key secret ARN       | Lets the hook retrieve the key using the MicroVM's execution role. |

`/run` hook 會解析 payload、取得 key、設定 `CODEX_API_KEY`，並[啟動 executor](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#start-the-executor)。process 一啟動就要回傳，避免 hook timeout。

要允許 executor 需要的[對外連線](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#network-access)和 Secrets Manager 的存取。要存取私有資源或有網路限制，就設定 AWS egress connector。

用 `PUT /upload/<path>` 把檔案寫到 `/workspace` 底下，用 `GET /download/<path>` 讀取。上傳接受最大 64 MiB 的原始 bytes。`upload_file` 和 `download_file` 這兩個 helper 會取得 8080 port 的 AWS 驗證 token。workspace 以外的路徑會被拒絕。

## 啟動 MicroVM

在 turn 結束前，要讓 session 的事件 stream 保持開啟。

### 應用程式管理的佈建

1. [建立自架 session](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#create-or-reuse-a-session)，工作目錄要跟 image 一致，然後[開啟它的事件 stream](https://developers.openai.com/api/docs/guides/agents-api/sessions/events#consume-a-stream)。
2. 呼叫 AWS [RunMicrovm](https://docs.aws.amazon.com/lambda/latest/microvm-api/API_RunMicrovm.html)，帶入 image ARN 和版本、execution role、network connector 和 `runHookPayload`。把回傳的 `microvmId` 和 session ID 一起存起來。
3. [送出 input](https://developers.openai.com/api/docs/guides/agents-api/sessions#send-input)，並追蹤這個 turn 的結果。
4. 取回輸出檔案並[停止 MicroVM](#stop-the-microvm)。

### Webhook 管理的佈建

你的應用程式建立 session、開啟 stream 並送出 input。OpenAI webhook 透過 API Gateway 送到 launcher Lambda。

1. 部署一個呼叫 launcher 的 `POST /webhook` 路由。要給 launcher 權限去讀取它的憑證、檢查、啟動、resume 和終止所選 image 的 MicroVM、傳遞 MicroVM execution role，以及使用設定好的 network connector。
2. 為 `agent.session.action_required` 和 `agent.session.failed` [註冊 endpoint](https://developers.openai.com/api/docs/guides/agents-api/sessions/webhooks#set-up-a-webhook)。把 endpoint 的 signing secret 跟 launcher 的 application key 存在一起。
3. 在存取 session 或啟動運算資源之前，先用原始的 request body 驗證 webhook 簽章。取回目前的 session 並確認 handler 擁有它，例如比對一個專用的已儲存 agent。
4. 如果 `environment_connection` 仍然待處理，而 session 記錄的 VM 是 suspended，就 resume 它。否則，若沒有記錄的 VM 就啟動一個並存下它的 ID；存不起來就終止它。如果 executor 在[連線 timeout](https://developers.openai.com/api/docs/guides/agents-api/sessions/webhooks#environment-connection-events) 之前連上，等待中的 input 會繼續處理，不用重送。
5. 如果 session 仍是 `failed`，就終止它記錄的 MicroVM。忽略已刪除的 session、已解決的 action 和屬於其他 handler 的事件。

範例把 VM ID 存在 session metadata。在那個 ID 被記錄之前，併發的 webhook 送達仍可能多啟動 VM。

## 停止 MicroVM

在 session stream 上，等主 agent（`event.turn.subagent_id` 為 `null`）的 `agent.session.turn.completed`、`agent.session.turn.failed` 或 `agent.session.turn.cancelled`。Subagent 共用 MicroVM，它們的結束事件不能觸發清理。取回需要的檔案，呼叫 `TerminateMicrovm`，並確認 VM 到達 `TERMINATED`。應用程式出錯時也要跑清理。

turn 的結果是 stream 事件，不是 webhook 訂閱。`agent.session.failed` webhook 處理 session 失敗，但沒涵蓋每個失敗的 turn。不要只因為 `agent.session.idle` 就終止：它可能在等待中的 input 開始之前就到了。

萬一清理失敗，要設好 AWS 的限制：

| Setting                                          | Guidance                                                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `maximumDurationInSeconds`                       | Set a ceiling for the workload, such as `900` for a 15-minute test. It can interrupt active work.                       |
| `maxIdleDurationSeconds`                         | Cover the expected workload. AWS measures inbound traffic; the executor's outbound connection doesn't reset this timer. |
| `suspendedDurationSeconds` / `autoResumeEnabled` | The examples use `0` / `false` by default and `300` / `false` with `--suspend-resume`. |

存活時間和閒置控制請見 AWS 的 [Running and using MicroVMs](https://docs.aws.amazon.com/lambda/latest/dg/microvms-launching.html)。

要另外[刪除 session](https://developers.openai.com/api/docs/guides/agents-api/sessions/manage#delete-a-session)；這不會停止 VM，也不會送出刪除 webhook。image 和 environment-key secret 要保留以便重用。後續 turn 的處理請見 [Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)。

## 在 turn 之間 suspend 和 resume

用 AWS 的 [suspend and resume](https://docs.aws.amazon.com/lambda/latest/dg/microvms-launching.html#microvms-launching-suspend-resume) 在 turn 之間保留記憶體和磁碟。要設定非零的 `suspendedDurationSeconds`；suspended 期間會收快照儲存費用。`maximumDurationInSeconds` 把執行加 suspended 的總時間限制在八小時內。

加上 `--suspend-resume` 時，應用程式會在第一個 turn 之後 suspend VM。應用程式管理的範例直接 resume 它；webhook 管理的範例則送另一個 input，讓 webhook 去 resume。下一個 turn 會讀到已存在的 `hello.txt`，應用程式再檢查內容有沒有保留下來。

hook 會在 suspend 前停掉 Codex，並在 resume 時重新載入它的 key。要等 tool 和 subagent 都結束才 suspend。自動 resume 需要有進到 VM 的流量；光是 Agents API 的 input 不會喚醒它。

## 驗證與監控

執行任一個範例，檢查下載的 `hello.txt`、VM 狀態（`TERMINATED`）和 session 已刪除（HTTP 404）。

把 `MICROVM_IMAGE_ARN` 設成你的 image ARN，並使用你部署所在的 AWS region：

```bash
aws logs tail /aws/lambda/codex-agents-api-webhook --since 10m

aws lambda-microvms list-microvms \
  --image-identifier "$MICROVM_IMAGE_ARN" \
  --query 'items[].{id:microvmId,state:state}' --output table
```

把 session ID 和 MicroVM ID 一起寫進 log，方便追蹤一次執行。憑證和原始的 webhook body 不要寫進 log。

## 疑難排解

| Symptom                       | What to check                                                                                                                      |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Webhook signature is rejected | Use the endpoint's signing secret and verify the unmodified request body.                                                          |
| No MicroVM launches           | Check the webhook subscription, session ownership filter, pending `environment_connection` action, and launcher's IAM permissions. |
| Image build fails             | Check the S3 artifact, image build role, and `/ready` hook response.                                                               |
| `/run` fails or times out     | Check secret access and executor startup. Return after starting the process, not after the turn.                                   |
| Executor can't connect        | Check the environment ID, remote URL, key ownership, and outbound network access.                                                  |
| VM stops during a turn        | Check maximum lifetime and idle policy; outbound executor traffic doesn't count as inbound activity.                               |

連線失敗時，檢查 `agent.session.environment.failed` 和 executor 的 log。共用的 executor 規格請見 [Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)。

## 參考資料

- [AWS Lambda MicroVMs guide for Agents API](https://developers.openai.com/api/docs/guides/agents-api/environments/providers/aws)
- [Running and using MicroVMs](https://docs.aws.amazon.com/lambda/latest/dg/microvms-launching.html)
- [Security and permissions](https://docs.aws.amazon.com/lambda/latest/dg/microvms-security.html)

## 重點整理
- OpenAI 跑 agent harness，你的 AWS 帳號裡的 MicroVM 跑 executor 和 workspace，憑證分開放。
- MicroVM 的行為由 lifecycle hook 決定，`/run` 要在 process 啟動後立刻回傳，不要等 turn 結束。
- 應用程式管理和 webhook 管理兩種佈建方式差在「誰呼叫 RunMicrovm」，同一個 image 都能用。
- 清理要看主 agent 的 turn 結束事件，不能只看 `idle` 或 subagent 的事件，並且要設 AWS 時間上限當保險。
- suspend/resume 能保留記憶體和磁碟，但要等 tool 都結束才 suspend，且自動 resume 需要進到 VM 的流量。

## 練習
1. 先跑應用程式管理的範例，把 `hello.txt` 要寫的內容改掉，確認下載後的檢查也跟著改。
2. 用 `--suspend-resume` 跑一次，再把 `suspendedDurationSeconds` 調小，觀察超時後 resume 會發生什麼。
3. 把 `maximumDurationInSeconds` 設成很小的值，讓 turn 被中斷，看你的清理流程能不能確保 VM 仍然到達 `TERMINATED`。
