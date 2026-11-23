---
translated: true
source: examples/agents_sdk/deployment_manager/README.md
---

# Agents SDK Deployment Manager

> 原文：[examples/agents_sdk/deployment_manager/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/deployment_manager/README.md)

在瀏覽器介面的 deployment manager 裡，執行、檢查並追蹤本機的 Agents SDK demo 應用。

## 這篇在做什麼
介紹一個本機的 control-plane 應用，用來執行並觀察 Agents SDK demo 專案。它能匯入專案、用 Docker 啟停應用，並把 trace 收回來顯示在 UI 上。

## 學完你會
- 啟動 deployment manager，匯入本機的 Agents SDK 專案並以 Docker container 部署
- 知道一個應用要符合哪些條件（`pyproject.toml`、`main.py`、`PORT`、`/health`）才能被這個 manager 部署
- 了解本機 trace 擷取怎麼運作：用 `add_trace_processor()` 多加一個本機目的地，不影響原本送到 OpenAI Platform 的 trace

## 開跑前
需要安裝 `uv`、`npm`，用預設的 `local-docker` 目標時還要有 Docker。

本機的 control-plane 應用，用來執行並觀察 Agents SDK demo 專案。

## 前置條件

- `uv`
- `npm`
- Docker（使用預設的 `local-docker` 目標時）

## 執行

```bash
make run
```

開啟：

```text
http://127.0.0.1:8732
```

Vite 會把 `frontend/` 裡的 React UI 建置到 `dist/`，Flask 後端則提供 `dist/` 和 `/api/*`。

## 截圖

### Deployments

![Deployments](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_sdk/deployment_manager/docs/screenshots/deployments.png)

### App details

![App details](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_sdk/deployment_manager/docs/screenshots/app-details.png)

### Traces

![Traces](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_sdk/deployment_manager/docs/screenshots/traces.png)

## 範圍

- 匯入本機的 Agents SDK 專案。
- 檢查 entrypoint、相依套件、環境變數和 sandbox 的使用情況。
- 建立本機的 deployment 記錄。
- 預設以有標籤的 Docker container 啟動和停止應用或 orchestrator。
- 產生或重用應用層級的 Dockerfile，做容器化部署。
- 顯示 deployment 的 log、trace、應用事件和 Docker container 的活動。
- 用 `agents-sdk.*` metadata 為 sandbox container 加標籤，讓 manager 能把 Docker container 對應回它的 deployment 和 run。

對 Docker 部署來說，預設目標會建置應用的 Dockerfile，並用下面的方式執行 orchestrator：

```bash
docker run -p 127.0.0.1:<app-port>:<app-port> -v /var/run/docker.sock:/var/run/docker.sock ...
```

掛載 Docker socket 是為了讓 `SandboxAgent` 能透過 Docker 建立 sandbox container。

manager 會在應用 process 上設定 `AGENTS_SDK_MANAGER`、`AGENTS_SDK_PROJECT`、`AGENTS_SDK_DEPLOYMENT_DATA_DIR` 和 `AGENTS_SDK_MANAGER_TRACE_ENDPOINT`。擷取到的 trace 會回傳給 manager，存進 manager 自己的 SQLite 資料庫。

## 可部署應用的規範

透過這個 manager 部署的應用應該具備：

- `pyproject.toml`，且 dependencies 裡有 `openai-agents`。
- 以 `main.py` 當應用 entrypoint。
- 本機啟動時支援 `PORT`。
- 設了 `PORT` 時，`uv run python main.py` 會啟動 HTTP 服務。
- 一個 `/health` readiness endpoint。

只能在 CLI 執行的 smoke 行為，要放在明確的參數後面或沒有 `PORT` 的路徑，這樣產生的 Dockerfile 才能穩定啟動服務。

## Tracing

trace 透過 manager 的 HTTP ingestion endpoint 在本機擷取，同時 Agents SDK 仍然透過預設的 processor 把 trace 串流到 OpenAI Platform。

manager 啟動應用時，會把 `runtime/trace_capture` 加進 `PYTHONPATH`，並設定：

```text
AGENTS_SDK_MANAGER_TRACE_ENDPOINT=http://<manager-host>:8732/api/traces/ingest
AGENTS_SDK_DEPLOYMENT_ID=<deployment-id>
AGENTS_SDK_PROJECT_ID=<project-id>
```

本機 process 部署時，`<manager-host>` 是 `127.0.0.1`。Docker 部署時則是 `host.docker.internal`，讓 container 能連到跑在 host 上的 manager。

這個 runtime 套件用 `sitecustomize.py`，在應用 process 裡用 `add_trace_processor()` 安裝一個輕量的 Agents SDK trace processor。這會多加第二個本機目的地，而不會取代 SDK 預設的 OpenAI Platform exporter。本機 processor 會把匯出的 trace 記錄 post 給 manager：

- `trace_start`
- `trace_end`
- `span_start`
- `span_end`

manager 把 trace 存在 `state/traces.sqlite3`。後端在 `app/timeline.py` 讀取這個 SQLite 儲存，按 `trace_id` 把記錄分組，並從 trace metadata（`expense_id`、`run_id` 或 `session_id`）推導出 run key，找不到就退回用 `group_id`，最後才用 `trace_id`。UI 用這些重建出來的記錄來顯示 Traces 檢視、巢狀的 span 清單、事件詳細面板、透過 `?trace_id=...` 的 trace 深層連結，以及 JSON 匯出。

這代表本機 tracing 不需要把 trace 檔案 bind-mount 進應用 container，也不需要從 OpenAI Platform dashboard API 抓 span。

## Make 目標

```bash
make start
make health
make deploy PROJECT_PATH=/path/to/agents-sdk-app APP_PORT=8421 SANDBOX_BACKEND=docker
make deploy PROJECT_PATH=/path/to/agents-sdk-app APP_PORT=8421 TARGET=local-process
make stop
```

## 重點整理
- deployment manager 是本機 control-plane，負責匯入、部署、觀察 Agents SDK 專案。
- 預設用帶標籤的 Docker container 跑應用，並掛載 Docker socket 讓 `SandboxAgent` 能建立 sandbox container。
- 可部署的應用有固定契約：`openai-agents` 相依、`main.py`、`PORT`、`/health`。
- tracing 靠 `add_trace_processor()` 多加本機 processor，trace 回傳給 manager 存進 SQLite，原本送往 OpenAI Platform 的 exporter 不受影響。

## 練習
1. 照前置條件啟動 manager，匯入一個符合契約的範例應用，確認 `/health` 有回應。
2. 在自己的應用裡加上 `PORT` 的支援，並讓沒有 `PORT` 時走 CLI 的 smoke 路徑。
3. 在應用裡跑一次 agent，到 Traces 檢視用 `?trace_id=...` 開啟那筆 trace，並匯出成 JSON 看裡面的 span 結構。
