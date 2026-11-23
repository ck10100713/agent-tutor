---
translated: true
source: examples/partners/AWS/openai_models_with_amazon_bedrock.ipynb
---
# 在 Amazon Bedrock 上開始使用 OpenAI 模型

> 原文：[examples/partners/AWS/openai_models_with_amazon_bedrock.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/openai_models_with_amazon_bedrock.ipynb)

學會用 OpenAI Python SDK 呼叫相容 OpenAI 的 Amazon Bedrock endpoint，也有對應的 cURL 範例，並用上 Bedrock 提供的 Responses API 功能。

## 這篇在做什麼

OpenAI 模型在 Amazon Bedrock 上提供相容的 Responses API，可以拿來做文字生成、結構化輸出、應用程式 tool、直接送檔案、回應狀態管理、prompt caching 和背景任務。這篇用一個虛構零售商 BrightCart 的客服助理情境，處理延遲和損毀訂單的換貨需求，把每個功能都跑一遍。

一般呼叫用 OpenAI Python SDK，想看實際 request body 時用一個簡單的原始 HTTPS helper。流程從設定和最小的預檢開始，接著是回應生命週期、模型參數、結構化 JSON、tool、檔案輸入、狀態管理、caching、背景處理、context 壓縮、營運檢查，最後清理。

## 學完你會

1. 用 Bedrock 專屬的環境變數設定 Bedrock 上的 OpenAI 模型，並驗證 Responses endpoint、檢查 response schema、usage 和統一格式的錯誤。
2. 用原始 HTTPS 和 OpenAI SDK 送文字請求，產生符合 schema 的 JSON，也會用比較寬鬆的 JSON mode。
3. 寫出 function tool、平行 tool call 和 custom text tool 的呼叫迴圈，送 PDF 當輸入，並用 `previous_response_id` 或自己重組歷史來延續對話，再搭配 prompt caching 和背景模式。

## 開跑前

- 需要 Bedrock 上 OpenAI 模型的 bearer token（環境變數 `AWS_BEARER_TOKEN_BEDROCK`）、Python 3.9 以上，以及能連到 Bedrock OpenAI 相容 endpoint 的網路。
- 這些呼叫會用到 Bedrock 的付費資源。

預設跑 `us-west-2` 的 `openai.gpt-5.4`。要換別的組合，執行設定 cell 之前，把 `AWS_REGION`、`BEDROCK_MODEL`、`BEDROCK_BASE_URL` 一起改掉。

| AWS Region | Supported model IDs |
| --- | --- |
| `us-west-2` | `openai.gpt-5.4` |
| `us-east-2` | `openai.gpt-5.5`, `openai.gpt-5.4` |


## 1. 設定 Amazon Bedrock

這一節準備執行環境：安裝需要的 Python 套件、讀取 Bedrock 專用的環境變數、建立原始 HTTPS session 和 OpenAI SDK client、endpoint 有提供時就查詢模型資訊，並定義後面都會用到的 helper。

先設好這些環境變數，預設組合是 `us-west-2` 配 `openai.gpt-5.4`。

```bash
export AWS_BEARER_TOKEN_BEDROCK="YOUR_BEDROCK_BEARER_TOKEN"
export AWS_REGION="us-west-2"
export BEDROCK_MODEL="openai.gpt-5.4"
export BEDROCK_BASE_URL="https://bedrock-mantle.${AWS_REGION}.api.aws/openai/v1"
```

bearer token 從 `AWS_BEARER_TOKEN_BEDROCK` 讀取。沒設的話，設定 cell 會用密碼輸入的方式問你，而且不會把它印出來。


### 1.1 安裝依賴套件

安裝會用到的套件。OpenAI SDK 用在應用範例，`requests` 用來對 Responses endpoint 發原始 HTTPS 請求，`pandas` 和 IPython 的顯示 helper 讓 request 和 response 的摘要比較好讀。看輸出只要確認套件裝好了或已經存在就行。


```python
%pip install -U "openai>=2.28.0" requests pandas ipython --quiet
print("Dependencies installed or already available: openai, requests, pandas, ipython")
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 24.0 -> 26.1.1
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    Dependencies installed or already available: openai, requests, pandas, ipython
    ```

### 1.2 匯入函式庫和預設值

匯入全篇會用到的標準函式庫、SDK、HTTP client 和顯示工具。這個 cell 也設定了環境變數沒設時的預設 Bedrock region 和模型。看印出來的預設值，確認沒有覆蓋的話會從 `us-west-2` 和 `openai.gpt-5.4` 開始。


```python
from __future__ import annotations

import base64
import builtins
import html
import json
import os
import shlex
import textwrap
import time
from datetime import date, timedelta
from getpass import getpass
from typing import Any, Callable, Iterable

import pandas as pd
import requests
from IPython.display import HTML, Markdown, display
from openai import OpenAI

DEFAULT_REGION = "us-west-2"
DEFAULT_MODEL = "openai.gpt-5.4"
PREFERRED_MODELS = [DEFAULT_MODEL]


def gpt_version_tuple(model_id: str) -> tuple[int, int] | None:
    normalized = model_id.lower().removeprefix("openai.")
    if not normalized.startswith("gpt-"):
        return None
    version = normalized.removeprefix("gpt-").split("-")[0]
    parts = version.split(".")
    try:
        major = builtins.int(parts[0])
        minor = builtins.int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None
    return major, minor


def prompt_cache_retention_for_model(model_id: str) -> str:
    version = gpt_version_tuple(model_id)
    if version and version >= (5, 5):
        return "24h"
    return "in_memory"

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", 200)
pd.set_option("display.max_colwidth", None)
pd.set_option("display.width", 160)


def display_wrapped_table(df: pd.DataFrame, *, max_col_width_px: int = 520, index: bool = False) -> None:
    if df.empty:
        display(Markdown("_No rows to display._"))
        return
    table_html = df.to_html(index=index, escape=True, border=0)
    table_html = table_html.replace('<table border="0" class="dataframe">', '<table class="dataframe wrapped-output-table">')
    display(HTML(f"""
    <style>
      .wrapped-output-table {{
        border-collapse: collapse;
        width: 100%;
        table-layout: auto;
        font-size: 13px;
      }}
      .wrapped-output-table th,
      .wrapped-output-table td {{
        border: 1px solid #d0d7de;
        padding: 6px 8px;
        text-align: left;
        vertical-align: top;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        word-break: break-word;
        max-width: {max_col_width_px}px;
      }}
      .wrapped-output-table th {{
        background: #f6f8fa;
        font-weight: 600;
      }}
    </style>
    {table_html}
    """))

print("Imports loaded.")
print("Default region:", DEFAULT_REGION)
print("Default model:", DEFAULT_MODEL)
```

??? note "輸出"

    ```text
    Imports loaded.
    Default region: us-west-2
    Default model: openai.gpt-5.4
    ```

### 1.3 設定 Bedrock 憑證和 client

從環境變數讀取 Bedrock 設定並建立 client。`BEDROCK_BASE_URL` 會先正規化一次，原始的 `requests.Session` 把 bearer token 放進 headers，OpenAI SDK client 則明確帶入同一組 token 和 base URL。正式呼叫之前，看一下表格，確認選到的 region、模型、endpoint、SDK client 設定，以及儲存回應的清理行為。


```python
from __future__ import annotations


def env_value(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def env_flag(name: str, default: bool = False) -> bool:
    value = env_value(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.endswith("/responses"):
        return url[: -len("/responses")]
    return url


def endpoint(path: str) -> str:
    return f"{BEDROCK_BASE_URL}/{path.lstrip('/')}"


def responses_url(base_url: str) -> str:
    return f"{normalize_base_url(base_url)}/responses"


API_TIMEOUT_SECONDS = float(env_value("BEDROCK_REQUEST_TIMEOUT_SECONDS") or "60")
MAX_RETRIES = builtins.int(env_value("BEDROCK_MAX_RETRIES") or "0")
CLEAN_UP_STORED_RESPONSES = env_flag("BEDROCK_CLEANUP_STORED_RESPONSES", True)
FAIL_ON_CHECK_FAILURE = env_flag("BEDROCK_FAIL_ON_CHECK_FAILURE", False)
RUN_RESPONSIVENESS_CHECK = env_flag("BEDROCK_RESPONSIVENESS_CHECK", True)
TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}

AWS_REGION = (env_value("AWS_REGION") or DEFAULT_REGION).strip() or DEFAULT_REGION
BEDROCK_MODEL = (env_value("BEDROCK_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
BEDROCK_BASE_URL = normalize_base_url(
    env_value("BEDROCK_BASE_URL") or f"https://bedrock-mantle.{AWS_REGION}.api.aws/openai/v1"
)
RESPONSES_URL = responses_url(BEDROCK_BASE_URL)
AWS_BEARER_TOKEN_BEDROCK = env_value("AWS_BEARER_TOKEN_BEDROCK")

if not AWS_BEARER_TOKEN_BEDROCK:
    AWS_BEARER_TOKEN_BEDROCK = getpass("Paste your AWS Bedrock bearer token for this kernel session: ").strip()
    if AWS_BEARER_TOKEN_BEDROCK:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = AWS_BEARER_TOKEN_BEDROCK

if not AWS_BEARER_TOKEN_BEDROCK:
    raise RuntimeError("AWS_BEARER_TOKEN_BEDROCK is required to run the live examples.")

http = requests.Session()
http.headers.update({
    "Authorization": f"Bearer {AWS_BEARER_TOKEN_BEDROCK}",
    "Content-Type": "application/json",
})

client = OpenAI(api_key=AWS_BEARER_TOKEN_BEDROCK, base_url=BEDROCK_BASE_URL, max_retries=0)
BASE_URL = BEDROCK_BASE_URL

config_rows = [
    {"setting": "AWS_REGION", "value": AWS_REGION},
    {"setting": "BEDROCK_MODEL", "value": BEDROCK_MODEL},
    {"setting": "BEDROCK_BASE_URL", "value": BEDROCK_BASE_URL},
    {"setting": "SDK client", "value": "OpenAI(api_key=AWS_BEARER_TOKEN_BEDROCK, base_url=BEDROCK_BASE_URL)"},
    {"setting": "cleanup stored responses", "value": CLEAN_UP_STORED_RESPONSES},
]
display_wrapped_table(pd.DataFrame(config_rows), max_col_width_px=680)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

### 1.4 查詢可用模型

endpoint 有提供模型列表時就去查，然後選定後面要用的模型。有設 `BEDROCK_MODEL` 就用它，沒有的話優先選 `openai.gpt-5.4`。查模型列表是選用的，因為有些相容 endpoint 就算查不到模型資訊也能做推論。看一下選到的模型和回傳的目錄資料。


```python
from __future__ import annotations


def list_openai_models(client: OpenAI) -> list[str]:
    return sorted(model.id for model in client.models.list(timeout=API_TIMEOUT_SECONDS).data)


def resolve_model_id(client: OpenAI | None) -> tuple[str, list[str], str | None]:
    configured_model = env_value("BEDROCK_MODEL")
    available_models: list[str] = []
    model_discovery_note: str | None = None

    if client is not None:
        try:
            available_models = list_openai_models(client)
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code == 404:
                model_discovery_note = "This endpoint did not expose model-list metadata. The guide will continue with the configured model."
            else:
                model_discovery_note = f"Model-list metadata could not be listed. The guide will continue with the configured model. Details: {builtins.str(exc)[:240]}"

    if configured_model:
        return configured_model, available_models, model_discovery_note

    for candidate in PREFERRED_MODELS:
        if candidate in available_models:
            return candidate, available_models, model_discovery_note

    for candidate in available_models:
        if candidate.startswith("openai."):
            return candidate, available_models, model_discovery_note

    if available_models:
        return available_models[0], available_models, model_discovery_note

    return PREFERRED_MODELS[0], available_models, model_discovery_note


EXPLICIT_MODEL = env_value("BEDROCK_MODEL")
MODEL_ID, AVAILABLE_MODELS, MODEL_DISCOVERY_NOTE = resolve_model_id(client)
os.environ["BEDROCK_MODEL"] = MODEL_ID
PROMPT_CACHE_RETENTION = prompt_cache_retention_for_model(MODEL_ID)
PROMPT_CACHE_RETENTION_NOTE = (
    "GPT-5.5 and later use 24h extended prompt caching; earlier GPT-5 models can use in_memory."
)

config_rows = [{
    "selected_model": MODEL_ID,
    "model_was_explicit": bool(EXPLICIT_MODEL),
    "model_catalog_status": "listed" if AVAILABLE_MODELS else "using configured model",
    "discovered_model_count": len(AVAILABLE_MODELS),
    "prompt_cache_retention": PROMPT_CACHE_RETENTION,
    "prompt_cache_retention_note": PROMPT_CACHE_RETENTION_NOTE,
    "note": MODEL_DISCOVERY_NOTE or "Model selection is ready.",
}]
display_wrapped_table(pd.DataFrame(config_rows), max_col_width_px=620)

if AVAILABLE_MODELS:
    display_wrapped_table(pd.DataFrame({"available_models": AVAILABLE_MODELS[:25]}), max_col_width_px=520)
else:
    print("Continuing with:", MODEL_ID)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Continuing with: openai.gpt-5.4
    ```

### 1.5 設定 helper 函式

定義整個流程共用的 helper：顯示 request 的樣子、統一 API 錯誤格式、發原始 HTTPS 請求、包裝 SDK 呼叫（可選擇重試）、取出 `output_text`、整理 token 用量、記錄儲存下來的 response ID，以及顯示精簡表格。後面的範例就能專心講各個 API 概念，重複的雜事交給 helper。想知道回應文字、用量、錯誤和清理怎麼處理，就看這個 cell。


```python
from __future__ import annotations

RESULTS_SUMMARY: list[dict[str, Any]] = []
EXAMPLE_RESPONSES: list[dict[str, str]] = []
STORED_RESPONSE_IDS: list[str] = []
OUTPUT_WIDTH = 100
MAX_DISPLAY_TEXT_CHARS = builtins.int(env_value("BEDROCK_MAX_DISPLAY_CHARS") or "1200")


def truncate_display_text(text: Any, *, limit: int = MAX_DISPLAY_TEXT_CHARS) -> str:
    rendered = builtins.str(text).strip()
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit].rstrip() + "\n[Display truncated for readability. Inspect the Python variable for the full value.]"


def compact_text(text: Any, limit: int = 220) -> str:
    rendered = " ".join(builtins.str(text).split())
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit].rstrip() + "..."


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def warn_or_raise(condition: bool, message: str) -> bool:
    if condition:
        return True
    display(HTML(f"<div style=\"border-left:4px solid #d29922; padding:6px 10px;\"><strong>Warning:</strong> {html.escape(message)}</div>"))
    if FAIL_ON_CHECK_FAILURE:
        raise AssertionError(message)
    return False


def display_text_block(label: str, text: Any, *, limit: int = MAX_DISPLAY_TEXT_CHARS) -> None:
    safe_label = html.escape(label)
    safe_text = html.escape(truncate_display_text(text, limit=limit))
    display(HTML(f"""
    <div style="border:1px solid #d0d7de; border-radius:6px; margin:8px 0; overflow:hidden; font-size:13px;">
      <div style="padding:6px 8px; font-weight:600;">{safe_label}</div>
      <div style="padding:8px; white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.45;">{safe_text}</div>
    </div>
    """))


def print_wrapped(text: Any, *, width: int = OUTPUT_WIDTH) -> None:
    print(textwrap.fill(builtins.str(text), width=width, break_long_words=True, break_on_hyphens=False))


def print_json(value: Any, *, width: int = OUTPUT_WIDTH) -> None:
    display_json_block("JSON", value)


def print_label(label: str) -> None:
    display(HTML(f"<div style=\"font-weight:600; margin:8px 0 4px;\">{html.escape(label)}</div>"))


def print_labeled_text(label: str, text: Any) -> None:
    display_text_block(label, text)


def print_labeled_json(label: str, value: Any) -> None:
    display_json_block(label, value)


def display_json_block(label: str, value: Any, *, limit: int = MAX_DISPLAY_TEXT_CHARS) -> None:
    rendered = json.dumps(value, indent=2, default=builtins.str)
    display_text_block(label, rendered, limit=limit)


def summarize_content(content: Any) -> str:
    if isinstance(content, builtins.str):
        return compact_text(content)
    if isinstance(content, builtins.list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, builtins.dict):
                parts.append(compact_text(item, 80))
                continue
            item_type = item.get("type", "item")
            if item_type == "input_text":
                parts.append(f"input_text: {compact_text(item.get('text', ''), 120)}")
            elif item_type == "input_file":
                parts.append(f"input_file: {item.get('filename', '<inline file>')}")
            else:
                parts.append(item_type)
        return "; ".join(parts)
    return compact_text(content)


def summarize_input(input_value: Any) -> str:
    if isinstance(input_value, builtins.str):
        return compact_text(input_value, 260)
    if isinstance(input_value, builtins.list):
        messages: list[str] = []
        for item in input_value[:4]:
            if isinstance(item, builtins.dict):
                role = item.get("role", item.get("type", "item"))
                messages.append(f"{role}: {summarize_content(item.get('content', item))}")
            else:
                messages.append(compact_text(item, 120))
        suffix = f"; +{len(input_value) - 4} more" if len(input_value) > 4 else ""
        return f"{len(input_value)} item(s): " + "; ".join(messages) + suffix
    return compact_text(input_value, 260)


def summarize_text_format(text_config: Any) -> str:
    if not isinstance(text_config, builtins.dict):
        return compact_text(text_config)
    fmt = text_config.get("format")
    if isinstance(fmt, builtins.dict):
        fmt_type = fmt.get("type")
        if fmt_type == "json_schema":
            schema = fmt.get("schema") or {}
            required = schema.get("required") or []
            return f"json_schema: {fmt.get('name')} strict={fmt.get('strict')} required={len(required)} fields"
        if fmt_type:
            return builtins.str(fmt_type)
    return compact_text(text_config)


def request_summary_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    ordered_keys = [
        "model", "max_output_tokens", "store", "background", "service_tier", "previous_response_id",
        "parallel_tool_calls", "prompt_cache_key", "prompt_cache_retention",
    ]
    for key in ordered_keys:
        if key in payload:
            rows.append({"field": key, "value": compact_text(payload[key], 180)})
    if "reasoning" in payload:
        rows.append({"field": "reasoning", "value": compact_text(payload["reasoning"], 180)})
    if "text" in payload:
        rows.append({"field": "text format", "value": summarize_text_format(payload["text"])})
    if "include" in payload:
        rows.append({"field": "include", "value": compact_text(payload["include"], 180)})
    if "tools" in payload:
        tool_names = [tool.get("name", tool.get("type", "tool")) for tool in payload.get("tools", [])]
        rows.append({"field": "tools", "value": ", ".join(tool_names)})
    if "tool_choice" in payload:
        rows.append({"field": "tool_choice", "value": compact_text(payload["tool_choice"], 180)})
    if "input" in payload:
        rows.append({"field": "input", "value": summarize_input(payload["input"])})
    return rows


def print_request_shape(payload: dict[str, Any]) -> None:
    rows = request_summary_rows(redact_payload(payload))
    print_label("Request shape")
    display_wrapped_table(pd.DataFrame(rows), max_col_width_px=520)


def print_response_summary(response_or_summary: Any) -> None:
    summary = response_or_summary if isinstance(response_or_summary, builtins.dict) and "output" not in response_or_summary else summarize_response(response_or_summary)
    preferred = [
        "id", "model", "status", "output_item_types", "input_tokens", "cached_input_tokens",
        "output_tokens", "total_tokens", "reasoning_output_tokens", "service_tier",
    ]
    rows = [{"field": key, "value": compact_text(summary.get(key), 220)} for key in preferred if key in summary]
    print_label("Response summary")
    display_wrapped_table(pd.DataFrame(rows), max_col_width_px=420)


def print_key_takeaway(text: str) -> None:
    display(HTML(f"<div style=\"border-left:4px solid #1f6feb; padding:6px 10px; margin:8px 0;\"><strong>Key takeaway:</strong> {html.escape(text)}</div>"))


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def redact(value: Any) -> Any:
        if isinstance(value, builtins.dict):
            return {
                key: ("<inline file data redacted for display>" if key == "file_data" else redact(item))
                for key, item in value.items()
            }
        if isinstance(value, builtins.list):
            return [redact(item) for item in value]
        return value

    return json.loads(json.dumps(redact(payload), default=builtins.str))


def compact_detail(detail: Any) -> str:
    if isinstance(detail, (builtins.dict, builtins.list)):
        return compact_text(json.dumps(detail, default=builtins.str), 500)
    return compact_text(detail, 500)


def record_check(name: str, status: str, detail: Any = "") -> None:
    RESULTS_SUMMARY.append({"name": name, "status": status, "detail": compact_detail(detail)})


def record_response(example: str, response_type: str, content: Any, limit: int = 900) -> None:
    if isinstance(content, pd.DataFrame):
        rendered = content.to_json(orient="records", indent=2)
    elif isinstance(content, (builtins.dict, builtins.list)):
        rendered = json.dumps(content, indent=2, default=builtins.str)
    else:
        rendered = builtins.str(content)
    rendered = rendered.strip()
    if len(rendered) > limit:
        rendered = rendered[:limit].rstrip() + chr(10) + "..."
    EXAMPLE_RESPONSES.append({
        "example": example,
        "response_type": response_type,
        "response": rendered,
    })


def print_response_gallery() -> pd.DataFrame:
    gallery = pd.DataFrame(EXAMPLE_RESPONSES)
    if gallery.empty:
        gallery = pd.DataFrame(columns=["example", "response_type", "response"])
    display_wrapped_table(gallery, max_col_width_px=620)
    return gallery


def normalize_error(response: requests.Response, body: Any) -> dict[str, Any]:
    return {
        "exception_class": "HTTPError",
        "status_code": response.status_code,
        "retryable": response.status_code in TRANSIENT_STATUS_CODES,
        "request_id": response.headers.get("x-request-id"),
        "body": body,
    }


def describe_api_error(exc: Exception) -> dict[str, Any]:
    try:
        parsed = json.loads(builtins.str(exc))
        if isinstance(parsed, builtins.dict) and "status_code" in parsed:
            return {
                "exception_class": type(exc).__name__,
                "status_code": parsed.get("status_code"),
                "retryable": parsed.get("retryable"),
                "request_id": parsed.get("request_id"),
                "message": compact_text(parsed.get("body", parsed), 500),
            }
    except Exception:
        pass

    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    request_id = None
    if response is not None:
        headers = getattr(response, "headers", {})
        request_id = headers.get("x-request-id") if hasattr(headers, "get") else None
    return {
        "exception_class": type(exc).__name__,
        "status_code": status_code,
        "retryable": status_code in TRANSIENT_STATUS_CODES,
        "request_id": request_id,
        "message": builtins.str(exc)[:500],
    }


def request_json(method: str, path: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    response = http.request(
        method,
        endpoint(path),
        json=payload,
        timeout=API_TIMEOUT_SECONDS,
    )
    try:
        body = response.json() if response.text else {}
    except json.JSONDecodeError:
        body = {"raw_text": response.text}
    if response.status_code >= 400:
        raise RuntimeError(json.dumps(normalize_error(response, body), indent=2, default=builtins.str))
    return body


def to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, builtins.list):
        return [to_dict(item) for item in value]
    if isinstance(value, builtins.dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


def output_text(response: Any) -> str:
    direct = getattr(response, "output_text", None)
    if direct:
        return direct
    data = to_dict(response)
    pieces: list[str] = []
    for item in data.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                pieces.append(content.get("text", ""))
    return "".join(pieces)


def response_items(response: Any) -> list[dict[str, Any]]:
    data = to_dict(response)
    return builtins.list(data.get("output", []) or [])


def first_output_item(response: Any, item_type: str) -> dict[str, Any] | None:
    for item in response_items(response):
        if item.get("type") == item_type:
            return item
    return None


def summarize_response(response: Any) -> dict[str, Any]:
    data = to_dict(response)
    usage = data.get("usage") or {}
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    return {
        "id": data.get("id"),
        "model": data.get("model"),
        "status": data.get("status"),
        "output_item_types": [item.get("type") for item in data.get("output", []) or []],
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": input_details.get("cached_tokens"),
        "reasoning_output_tokens": output_details.get("reasoning_tokens"),
        "service_tier": data.get("service_tier"),
    }


def call_with_retries(label: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    kwargs.setdefault("timeout", API_TIMEOUT_SECONDS)
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            error = describe_api_error(exc)
            should_retry = bool(error["retryable"] and attempt <= MAX_RETRIES)
            if not should_retry:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))
    raise RuntimeError(f"{label} failed after retries") from last_exc


def create_response(**kwargs: Any) -> Any:
    kwargs.setdefault("model", MODEL_ID)
    return call_with_retries("responses.create", client.responses.create, **kwargs)


def retrieve_response(response_id: str) -> Any:
    return call_with_retries("responses.retrieve", client.responses.retrieve, response_id)


def delete_response(response_id: str) -> Any:
    return call_with_retries("responses.delete", client.responses.delete, response_id)


def remember_stored_response(response: Any) -> None:
    response_id = getattr(response, "id", None) or to_dict(response).get("id")
    if response_id:
        STORED_RESPONSE_IDS.append(response_id)


def handle_example_error(features: str | list[str], exc: Exception) -> None:
    feature_list = [features] if isinstance(features, builtins.str) else features
    error = describe_api_error(exc)
    for feature in feature_list:
        record_check(feature, "warn", error)
    print_labeled_text("Result", "This live call did not complete in this environment.")
    print_labeled_json("Response summary", error)


def build_curl_command(payload: dict[str, Any]) -> str:
    body = json.dumps(payload)
    return " ".join([
        "curl", "-sS", shlex.quote(RESPONSES_URL),
        "-H", shlex.quote("Content-Type: application/json"),
        "-H", shlex.quote("Authorization: Bearer $AWS_BEARER_TOKEN_BEDROCK"),
        "-d", shlex.quote(body),
    ])


def run_raw_http_request(payload: dict[str, Any]) -> dict[str, Any]:
    return request_json("POST", "/responses", payload=payload)

print("Helpers ready.")
```

??? note "輸出"

    ```text
    Helpers ready.
    ```

### 1.6 驗證 endpoint

第一次實際呼叫刻意做得很小。它送出一個最小的 Responses 請求，帶 `store=false` 和一句簡短的文字指示，讓你在跑複雜範例前先抓出設定問題。看 request 的樣子、回傳文字、status、model、output item 類型和 token 用量。




```python
from __future__ import annotations
preflight_payload = {
    "model": MODEL_ID,
    "input": "Reply with exactly: ok",
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(preflight_payload)
try:
    preflight_response = create_response(**preflight_payload)
    require(output_text(preflight_response).strip(), "Preflight response did not return output text.")
    record_check("Endpoint shape", "pass", RESPONSES_URL)
    model_selection_detail = f"{len(AVAILABLE_MODELS)} models discovered" if AVAILABLE_MODELS else "Using configured model; model-list metadata is not required for requests."
    record_check("Model selection", "pass", model_selection_detail)
    preflight_text = output_text(preflight_response).strip()
    record_response("Endpoint verification", "text", preflight_text)
    print_labeled_text("Result", preflight_text)
    print_response_summary(preflight_response)
    print_key_takeaway('A tiny response confirms that the endpoint, key, model, and request shape are working.')
except Exception as exc:
    handle_example_error(["Endpoint shape", "Model selection"], exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 1.7 統一 API 錯誤格式

正式環境的整合需要一致的錯誤紀錄，包含 status code、要不要重試、request ID 和 response body。這個 cell 說明這篇使用的統一錯誤格式，不會故意發出失敗的請求。後面的 cell 在呼叫失敗或回傳非 2xx 時，都用同一種格式。


```python
from __future__ import annotations
error_taxonomy_example = {
    "normalized_fields": ["exception_class", "status_code", "retryable", "request_id", "message"],
    "retryable_status_codes": sorted(TRANSIENT_STATUS_CODES),
    "notes": "call_with_retries(...) uses this taxonomy for transient retry handling.",
}
record_check("Error handling", "pass", error_taxonomy_example)
print_json(error_taxonomy_example)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 2. 送出第一批 Responses 請求

這一節從兩個角度看 Responses 的請求。先檢視並執行一個原始 HTTPS 請求，讓 endpoint、headers 和 JSON body 都看得到。再用 OpenAI SDK 做同類型的應用流程，設定正確之後，正式程式碼多半該走這條路。


### 2.1 檢視原始 HTTPS 請求的格式

為 BrightCart 客服助理的回覆組一個最小的 Responses payload，並產生可以直接複製貼上的 `curl` 指令。指令裡用 `$AWS_BEARER_TOKEN_BEDROCK`，不會把 token 寫死，notebook 也不會執行把 bearer token 放在 process 參數裡的 shell 指令。看一下 `model`、`input`、`max_output_tokens` 和 `store` 這幾個欄位。


```python
from __future__ import annotations
basic_curl_payload = {
    "model": MODEL_ID,
    "input": "BrightCart customer Maya asks why replacement order ORDER-8831 is delayed. Write two labeled plain-text lines for the support agent. Do not use leading hyphens or bold text.",
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(basic_curl_payload)
print_labeled_text("Result", build_curl_command(basic_curl_payload))
print_key_takeaway('The curl command shows the raw HTTPS shape behind the SDK call.')
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 2.2 送出原始 HTTPS 請求

用原始 HTTPS helper 送出同一個請求。這個 cell 示範底層的 `POST /responses` 路徑，並且走訪 output item 從 response body 取出文字。看回傳的 response ID、model、status 和文字輸出，了解你的應用會收到什麼 schema。


```python
from __future__ import annotations

print_request_shape(basic_curl_payload)
try:
    basic_http_response = run_raw_http_request(basic_curl_payload)
    record_check("Text generation", "pass", basic_http_response.get("id"))
    response_text_parts = []
    for item in basic_http_response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                response_text_parts.append(content.get("text", ""))
    raw_http_output = "".join(response_text_parts).strip()
    record_response("First raw HTTPS request", "text", raw_http_output)
    print_labeled_text("Result", raw_http_output)
    print_labeled_json("Response summary", {
        "id": basic_http_response.get("id"),
        "model": basic_http_response.get("model"),
        "status": basic_http_response.get("status"),
    })
    print_key_takeaway("The response body contains message output that application code can extract as text.")
except Exception as exc:
    handle_example_error("Text generation", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 2.3 使用 OpenAI SDK

只要明確傳入 Bedrock 的 bearer token 和 base URL，OpenAI SDK 就能呼叫相容 OpenAI 的 API。這個 cell 透過 `client.responses.create` 送文字生成請求，把 `reasoning.effort` 設成 `low`，並印出精簡的回應摘要。看輸出文字、token 數、output item 類型，還有 endpoint 回傳的 reasoning token 資訊。

官方文件：[Reasoning models](https://developers.openai.com/api/docs/guides/reasoning) 說明了在 Responses API 裡怎麼用 reasoning effort。


```python
from __future__ import annotations
sdk_text_payload = {
    "model": MODEL_ID,
    "input": "Write a three-sentence overview for a developer building a BrightCart support assistant with the Responses API.",
    "reasoning": {"effort": "low"},
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(sdk_text_payload)
try:
    text_response = create_response(**sdk_text_payload)
    sdk_text = output_text(text_response).strip()
    require(sdk_text, "SDK text response did not return output text.")
    record_check("Text generation", "pass", summarize_response(text_response))
    record_check("Reasoning effort", "pass", summarize_response(text_response))
    record_response("SDK text generation", "text", sdk_text)
    print_labeled_text("Result", sdk_text)
    print_response_summary(text_response)
    print_key_takeaway('The SDK returns a response object with text, status, token usage, and output item metadata.')
except Exception as exc:
    handle_example_error(["Text generation", "Reasoning effort"], exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 2.4 建立並取回 response

Responses API 可以把回應存起來，之後用 ID 取回。這個做法適合稽核紀錄、除錯，以及引用之前 context 的後續回合。這個 cell 建立一個會儲存的 response，記下 ID 以便之後清理，再把它取回來，比對取回的文字和 usage 資訊。




```python
from __future__ import annotations
lifecycle_payload = {
    "model": MODEL_ID,
    "input": (
        "BrightCart is building a support assistant for delayed replacement orders. "
        "Return exactly three labeled plain-text lines: goal, data needed, and human-review rule. Do not use leading hyphens or bold text."
    ),
    "max_output_tokens": 1024,
    "store": True,
}

print_request_shape(lifecycle_payload)
try:
    lifecycle_response = create_response(**lifecycle_payload)
    remember_stored_response(lifecycle_response)
    retrieved_response = retrieve_response(lifecycle_response.id)
    retrieved_summary = summarize_response(retrieved_response)
    retrieved_text = output_text(retrieved_response).strip()
    require(retrieved_text, "Retrieved response did not contain text output.")

    lifecycle_status = "pass" if retrieved_summary.get("status") in {None, "completed"} else "warn"
    record_check("Responses lifecycle", lifecycle_status, retrieved_response.id)
    record_check("Response schema", "pass", retrieved_summary)
    record_check("Usage metadata", "pass" if retrieved_summary.get("total_tokens") is not None else "warn", retrieved_summary)
    record_response("Create and retrieve response", "text", retrieved_text)

    print_labeled_text("Result", retrieved_text)
    print_labeled_json("Created response summary", summarize_response(lifecycle_response))
    print_response_summary(retrieved_summary)
    print_key_takeaway('store=True lets an application retrieve the response later by ID with usage metadata intact.')
except Exception as exc:
    handle_example_error(["Responses lifecycle", "Response schema", "Usage metadata"], exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 2.5 加上 reasoning effort、service tier 和 prompt cache 參數

模型控制參數跟一般 input 一起送出。這個請求同時帶了 `reasoning.effort`、`service_tier`、`prompt_cache_key` 和 `prompt_cache_retention`，你可以看到這些營運控制和 prompt cache 資訊，跟一般文字輸出出現在同一個 response schema 裡。看一下 `service_tier`、`cached_input_tokens`、reasoning token 資訊和總 token 用量。

注意：這份 notebook 用 `PROMPT_CACHE_RETENTION`，不直接寫死 `prompt_cache_retention`。`openai.gpt-5.4` 的值是 `in_memory`，`openai.gpt-5.5` 之後的模型是 `24h`，因為那些模型要求使用延長版的 prompt caching。


```python
from __future__ import annotations
control_payload = {
    "model": MODEL_ID,
    "input": (
        "For the BrightCart support assistant, explain prompt caching in exactly two labeled plain-text lines: "
        "one latency benefit and one consistency benefit."
    ),
    "reasoning": {"effort": "low"},
    "prompt_cache_key": "brightcart-support-policy-guide",
    "prompt_cache_retention": PROMPT_CACHE_RETENTION,
    "service_tier": "auto",
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(control_payload)
try:
    control_response = create_response(**control_payload)
    control_summary = summarize_response(control_response)
    control_text = output_text(control_response).strip()
    require(control_text, "Control response did not return text.")
    status = "pass" if control_summary.get("status") in {None, "completed"} else "warn"
    record_check("Prompt caching", "pass" if control_summary.get("cached_input_tokens") is not None else "warn", control_summary)
    record_check("Service tier", "pass" if control_summary.get("service_tier") is not None else "warn", control_summary)
    record_check("Reasoning effort", status, control_summary)
    record_response("Service tier and prompt cache request", "text", control_text)
    print_labeled_text("Result", control_text)
    print_response_summary(control_summary)
    print_key_takeaway('Model controls travel with the same request as normal input, while returned metadata can vary by endpoint.')
except Exception as exc:
    handle_example_error(["Prompt caching", "Service tier", "Reasoning effort"], exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 3. 產生結構化 JSON

結構化 JSON 讓模型輸出變成應用程式能解析、驗證和分流的資料。這一節比較嚴格受 schema 約束的輸出和比較寬鬆的 JSON mode。應用需要明確的格式約定時用 Structured Outputs，只要是合法 JSON、schema 可以彈性一點時用 JSON mode。




### 3.1 定義結構化輸出的 schema

定義下一個實際請求會用的客服工單 schema。schema 列出應用預期的欄位，包含類別、優先級、情緒、摘要、需要的動作和是否升級處理。看 request 的樣子，了解 `text.format.type="json_schema"`、`strict=true` 和 JSON Schema 怎麼附加到一般的 Responses 請求上。


```python
from __future__ import annotations
support_triage_schema = {
    "type": "object",
    "properties": {
        "ticket_id": {"type": "string"},
        "category": {"type": "string", "enum": ["delivery_delay", "return_exchange", "damaged_item", "billing", "account"]},
        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
        "customer_sentiment": {"type": "string"},
        "summary": {"type": "string"},
        "required_actions": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        "escalation_needed": {"type": "boolean"},
    },
    "required": ["ticket_id", "category", "priority", "customer_sentiment", "summary", "required_actions", "escalation_needed"],
    "additionalProperties": False,
}

structured_payload = {
    "model": MODEL_ID,
    "input": (
        "Support ticket TICKET-7429: Maya Chen says ORDER-8831 is a replacement for a damaged standing desk. "
        "The replacement is two days late, the carrier scan has not moved, and she needs the desk before Monday. "
        "She asks for a supervisor callback and refund options. Triage this ticket for the next support agent."
    ),
    "text": {"format": {"type": "json_schema", "name": "support_ticket_triage", "strict": True, "schema": support_triage_schema}},
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(structured_payload)
print_key_takeaway('The schema is part of the request and defines the fields the next cell validates.')
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 3.2 驗證受 schema 約束的輸出

用上一個 cell 的 schema 呼叫模型，把回傳文字解析成 JSON，並在 Python 裡驗證重要欄位。API 請求要求模型遵守 schema，但應用端還是要檢查回傳的物件適不適合往下游分流。看解析後的物件和 response 摘要。


```python
from __future__ import annotations


def validate_support_triage(payload: dict[str, Any]) -> dict[str, Any]:
    require("ticket_id" in payload, "Missing key: ticket_id")
    require(payload.get("ticket_id") == "TICKET-7429", "Ticket ID did not match expected value.")
    require("required_actions" in payload, "Missing key: required_actions")
    require(isinstance(payload.get("required_actions"), builtins.list), "required_actions must be a list.")
    require(len(payload["required_actions"]) >= 2, "required_actions should contain at least two actions.")
    return payload

print_request_shape(structured_payload)
try:
    structured_response = create_response(**structured_payload)
    raw_structured_text = output_text(structured_response).strip()
    try:
        structured_payload_result = validate_support_triage(json.loads(raw_structured_text))
        record_check("Structured Outputs", "pass", structured_payload_result)
        record_response("Structured ticket triage", "json", structured_payload_result)
        print_labeled_json("Result", structured_payload_result)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")
    except Exception as parse_exc:
        record_check("Structured Outputs", "warn", {"message": "Response did not match the expected schema shape.", "text_sample": raw_structured_text[:600], "error": builtins.str(parse_exc)})
        print_labeled_text("Result", "The request completed, but the returned text did not match the expected schema shape.")
        print_wrapped(raw_structured_text[:1200])
    print_response_summary(structured_response)
    print_key_takeaway('Schema-constrained output gives application code a predictable JSON object to parse and validate.')
except Exception as exc:
    handle_example_error("Structured Outputs", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 3.3 使用 JSON mode

JSON mode 只要求模型回傳合法的 JSON 物件，不強制嚴格的 schema。適合輕量的交接，你還是要可解析的輸出，但格式約定可以鬆一點。這個 cell 請求一個客服交接物件、解析它，並檢查預期的 key 在不在。


```python
from __future__ import annotations
json_mode_payload = {
    "model": MODEL_ID,
    "input": (
        "Return JSON for a support chat handoff with keys customer_name, order_id, issue_summary, next_step, "
        "and metrics_to_watch. Context: Maya Chen asks about delayed replacement order ORDER-8831; the carrier scan is stale. "
        "metrics_to_watch should be an array."
    ),
    "text": {"format": {"type": "json_object"}},
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(json_mode_payload)
try:
    json_mode_response = create_response(**json_mode_payload)
    payload = json.loads(output_text(json_mode_response).strip())
    require({"customer_name", "order_id", "issue_summary", "next_step", "metrics_to_watch"}.issubset(payload), "JSON mode response missed required keys.")
    record_check("JSON mode", "pass", payload)
    record_response("JSON support handoff", "json", payload)
    print_labeled_json("Result", payload)
    print_response_summary(json_mode_response)
    print_key_takeaway('JSON mode is useful when valid JSON is enough and a strict schema is not required.')
except Exception as exc:
    handle_example_error("JSON mode", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 3.4 用 verbosity 控制輸出的詳細程度

verbosity 控制產生文字的長短和風格，reasoning effort 則控制模型回答前花多少推理功夫。前面的 SDK 和模型控制 cell 已經示範過 `reasoning.effort`，這個 cell 專門看 `text.verbosity`，對同一個政策主題分別送出精簡版和詳細版。並排看文字和 token 摘要，比較風格和用量。


```python
from __future__ import annotations
verbosity_prompt = "Explain BrightCart's delayed-replacement policy to a new support agent."
compact_payload = {
    "model": MODEL_ID,
    "input": verbosity_prompt + " Reply in one sentence under 35 words.",
    "text": {"verbosity": "low"},
    "max_output_tokens": 1024,
    "store": False,
}
detailed_payload = {
    "model": MODEL_ID,
    "input": verbosity_prompt + " Reply in exactly three numbered plain-text lines, each under 18 words. Do not use leading hyphens or bold text.",
    "text": {"verbosity": "high"},
    "max_output_tokens": 1024,
    "store": False,
}

print_labeled_json("Request shape", {
    "compact": redact_payload(compact_payload),
    "detailed": redact_payload(detailed_payload),
})
try:
    compact_response = create_response(**compact_payload)
    detailed_response = create_response(**detailed_payload)
    compact_guidance_text = output_text(compact_response).strip()
    detailed_guidance_text = output_text(detailed_response).strip()
    require(compact_guidance_text and detailed_guidance_text, "Verbosity responses did not return text.")
    compact_summary = summarize_response(compact_response)
    detailed_summary = summarize_response(detailed_response)
    status = "pass" if compact_summary.get("status") in {None, "completed"} and detailed_summary.get("status") in {None, "completed"} else "warn"
    record_check("Verbosity", status, {"compact_chars": len(compact_guidance_text), "detailed_chars": len(detailed_guidance_text)})
    record_response("Compact policy guidance", "text", compact_guidance_text)
    record_response("Detailed policy guidance", "text", detailed_guidance_text)
    print_labeled_text("Result: compact guidance", compact_guidance_text)
    print_labeled_text("Result: detailed guidance", detailed_guidance_text)
    verbosity_summary = pd.DataFrame([
        {"request": "compact", **compact_summary},
        {"request": "detailed", **detailed_summary},
    ])
    print_label("Response summary")
    display_wrapped_table(verbosity_summary, max_col_width_px=420)
    print_key_takeaway('Verbosity controls tune the answer style while the prompt still bounds the output.')
except Exception as exc:
    handle_example_error("Verbosity", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 4. 加入由應用程式管理的 tool

Function calling 讓模型向你的應用要資料或要求執行動作，但實際執行 tool 和回傳結果的是你的程式。這一節先定義本地的 BrightCart tool，再依序走過單一 function call、多個獨立的呼叫，以及 custom text tool。範例的 tool 輸出是固定的，這樣請求迴圈比較好看清楚。




### 4.1 定義本地 tool 的 schema 和函式

定義查訂單狀態和客戶資料的本地範例 tool。tool schema 描述名稱、說明、參數格式、必填欄位和是否 strict，模型就靠這些決定要呼叫什麼。Python 函式則代表訂單管理、CRM 或政策服務這類應用系統。


```python
from __future__ import annotations
function_tools = [
    {
        "type": "function",
        "name": "get_order_status",
        "description": "Look up a sample BrightCart order status.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "An order ID such as ORDER-8831."}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_customer_profile",
        "description": "Look up sample customer context for a BrightCart support interaction.",
        "parameters": {
            "type": "object",
            "properties": {"customer_id": {"type": "string", "description": "A customer ID such as CUST-1042."}},
            "required": ["customer_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def get_order_status(order_id: str) -> dict[str, Any]:
    orders = {
        "ORDER-8831": {
            "order_id": "ORDER-8831",
            "customer_id": "CUST-1042",
            "item": "standing desk replacement",
            "status": "delayed",
            "carrier_scan": "No movement for 36 hours at Denver sort center",
            "promised_delivery": (date.today() + timedelta(days=2)).isoformat(),
            "recommended_policy": "If delay exceeds 48 hours, offer expedited replacement or 15% concession with agent approval.",
        },
        "ORDER-2044": {
            "order_id": "ORDER-2044",
            "customer_id": "CUST-1042",
            "item": "ergonomic chair",
            "status": "delivered",
            "carrier_scan": "Delivered yesterday at front desk",
            "promised_delivery": (date.today() - timedelta(days=1)).isoformat(),
            "recommended_policy": "Confirm delivery details before opening a replacement request.",
        },
    }
    return orders.get(order_id, {"order_id": order_id, "status": "unknown", "customer_id": None})


def get_customer_profile(customer_id: str) -> dict[str, Any]:
    profiles = {
        "CUST-1042": {
            "customer_id": "CUST-1042",
            "name": "Maya Chen",
            "loyalty_tier": "Gold",
            "region": "California",
            "recent_issue": "Damaged standing desk replacement",
            "contact_preference": "email with SMS updates for shipping changes",
        }
    }
    return profiles.get(customer_id, {"customer_id": customer_id, "loyalty_tier": "unknown"})


def dispatch_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    name = call["name"]
    args = json.loads(call["arguments"])
    if name == "get_order_status":
        output = get_order_status(**args)
    elif name == "get_customer_profile":
        output = get_customer_profile(**args)
    else:
        raise ValueError(f"Unsupported tool: {name}")
    return {"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(output)}

print("Sample function tools:")
print_json([tool["name"] for tool in function_tools])
print("\nSample order lookup:")
print_json(get_order_status("ORDER-8831"))
```

??? note "輸出"

    ```text
    Sample function tools:
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text

    Sample order lookup:
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 4.2 呼叫 function tool
這個 cell 跑基本的 function calling 迴圈。第一個請求給模型一個查訂單狀態的 tool，讓它自己挑參數。應用解析回傳的 `function_call`，執行本地 Python 函式，送回一個 `function_call_output` item，再要求模型給出有根據的最終回答。看 tool 參數、本地 tool 輸出、最終模型文字和 response 資訊。


```python
from __future__ import annotations
function_input = [{"role": "user", "content": "Use get_order_status for ORDER-8831, then explain the next best action for the support agent in two labeled plain-text lines. Do not use leading hyphens or bold text."}]
order_status_tool = [tool for tool in function_tools if tool["name"] == "get_order_status"]
function_request = {
    "model": MODEL_ID,
    "input": function_input,
    "tools": order_status_tool,
    "tool_choice": "required",
    "max_output_tokens": 1024,
    "store": False,
}


def create_tool_plan_with_auto_fallback(request: dict[str, Any]) -> tuple[Any, str]:
    try:
        return create_response(**request), builtins.str(request.get("tool_choice"))
    except Exception as first_exc:
        fallback_request = {**request, "tool_choice": "auto"}
        try:
            return create_response(**fallback_request), "auto"
        except Exception:
            raise first_exc


print_request_shape(function_request)
try:
    function_plan, tool_choice_used = create_tool_plan_with_auto_fallback(function_request)
    function_calls = [item for item in response_items(function_plan) if item.get("type") == "function_call"]

    if function_calls:
        function_call = function_calls[0]
        function_args = json.loads(function_call["arguments"])
        require(function_args.get("order_id") == "ORDER-8831", f"Unexpected function arguments: {function_args}")
        tool_output = dispatch_tool_call(function_call)
        final_response = create_response(
            model=MODEL_ID,
            input=function_input + response_items(function_plan) + [tool_output],
            tools=order_status_tool,
            max_output_tokens=1024,
            store=False,
        )
        final_answer = output_text(final_response).strip()
        tool_output_payload = json.loads(tool_output["output"])
        record_check("Function calling", "pass", {"tool_choice_used": tool_choice_used, "arguments": function_args})
        record_response("Order-status tool answer", "text", final_answer)
        print_labeled_json("Result: tool arguments", function_args)
        print_labeled_json("Result: tool output", tool_output_payload)
        print_labeled_text("Result: final model answer", final_answer)
        print_response_summary(final_response)
        print_key_takeaway('Function calling separates model-selected arguments from application-executed business logic.')
    else:
        fallback_order = get_order_status("ORDER-8831")
        fallback_prompt = (
            "The model response did not include a function_call item. Use this application lookup result "
            "to answer in two labeled plain-text lines without leading hyphens or bold text: " + json.dumps(fallback_order)
        )
        final_response = create_response(
            model=MODEL_ID,
            input=function_input + [{"role": "user", "content": fallback_prompt}],
            max_output_tokens=1024,
            store=False,
        )
        final_answer = output_text(final_response).strip()
        returned_item_types = [item.get("type") for item in response_items(function_plan)]
        record_check("Function calling", "warn", {"tool_choice_used": tool_choice_used, "returned_item_types": returned_item_types})
        record_response("Order-status local fallback answer", "text", final_answer)
        print_labeled_json("Result: returned output item types", returned_item_types)
        print_labeled_json("Result: local tool output", fallback_order)
        print_labeled_text("Result: final model answer", final_answer)
        print_response_summary(final_response)
        print_key_takeaway('The local lookup keeps the function-calling pattern understandable even when the model returns text.')
except Exception as exc:
    handle_example_error("Function calling", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 4.3 處理多個 tool call

平行 tool call 讓模型在同一個回合要求多個彼此獨立的查詢。這個 cell 允許兩筆訂單狀態查詢，執行每個本地 function call，把兩份輸出都送回去，再請模型比較目前的出貨問題。看回傳的訂單 ID 和最終回答，確認回答是根據應用資料，不是靠模型記憶。


```python
from __future__ import annotations
parallel_input = [{"role": "user", "content": "Use get_order_status for ORDER-8831 and ORDER-2044, then summarize whether Maya has one shipping problem or multiple active shipping problems in two labeled plain-text lines. Do not use leading hyphens or bold text."}]
parallel_request = {
    "model": MODEL_ID,
    "input": parallel_input,
    "tools": function_tools,
    "tool_choice": "auto",
    "parallel_tool_calls": True,
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(parallel_request)
try:
    parallel_plan = create_response(**parallel_request)
    parallel_calls = [item for item in response_items(parallel_plan) if item.get("type") == "function_call"]
    parallel_outputs = [dispatch_tool_call(call) for call in parallel_calls]
    parallel_order_ids = [json.loads(call["arguments"]).get("order_id") for call in parallel_calls if call.get("name") == "get_order_status"]
    expected_order_ids = ["ORDER-8831", "ORDER-2044"]
    missing_order_ids = [order_id for order_id in expected_order_ids if order_id not in builtins.set(parallel_order_ids)]

    if not missing_order_ids:
        parallel_final = create_response(
            model=MODEL_ID,
            input=parallel_input + response_items(parallel_plan) + parallel_outputs,
            tools=function_tools,
            max_output_tokens=1024,
            store=False,
        )
        parallel_answer = output_text(parallel_final).strip()
        record_check("Parallel tool calls", "pass", {"tool_call_count": len(parallel_calls), "order_ids": parallel_order_ids})
        record_response("Parallel order lookup answer", "text", parallel_answer)
        print_labeled_json("Result: tool calls", {"tool_call_count": len(parallel_calls), "order_ids": parallel_order_ids})
        print_labeled_text("Result: final model answer", parallel_answer)
        print_response_summary(parallel_final)
        print_key_takeaway('Parallel tool calls let the model request multiple lookups, while the application still controls execution.')
    else:
        fallback_orders = [get_order_status(order_id) for order_id in expected_order_ids]
        fallback_prompt = (
            "The model did not request every expected order lookup. Use these application lookup results "
            "to answer in two labeled plain-text lines without leading hyphens or bold text: " + json.dumps(fallback_orders)
        )
        parallel_final = create_response(
            model=MODEL_ID,
            input=parallel_input + [{"role": "user", "content": fallback_prompt}],
            max_output_tokens=1024,
            store=False,
        )
        parallel_answer = output_text(parallel_final).strip()
        record_check("Parallel tool calls", "warn", {"returned_order_ids": parallel_order_ids, "missing_order_ids": missing_order_ids})
        record_response("Parallel order lookup fallback answer", "text", parallel_answer)
        print_labeled_json("Result: returned tool calls", {"tool_call_count": len(parallel_calls), "order_ids": parallel_order_ids})
        print_labeled_json("Result: local tool outputs", fallback_orders)
        print_labeled_text("Result: final model answer", parallel_answer)
        print_response_summary(parallel_final)
        print_key_takeaway('Local lookup outputs keep the parallel-tool pattern understandable if not every call is returned.')
except Exception as exc:
    handle_example_error("Parallel tool calls", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 4.4 使用 custom text tool

Custom tool 把自由格式的文字交給應用自己的邏輯，不需要結構化的 JSON 參數物件。這個 cell 定義一個客服備註正規化 tool，請求一次 custom tool call，並且在 endpoint 只回一般文字、沒有 custom call 時，有本地的 fallback。看 output item 的類型和正規化後的備註。


```python
from __future__ import annotations
custom_tools = [
    {
        "type": "custom",
        "name": "normalize_support_note",
        "description": "Normalize a freeform support note written by an agent. Input is plain text.",
        "format": {"type": "text"},
    }
]


def normalize_support_note_text(note: str) -> str:
    fields = [part.strip().upper() for part in note.split("|")]
    labels = ["ORDER_ID", "CUSTOMER_ID", "ISSUE", "CUSTOMER_REQUEST", "POLICY_OPTION"]
    return "\n".join(
        f"{label}: {value}"
        for label, value in zip(labels, fields)
        if value
    )


support_note = "order-8831 | cust-1042 | replacement delayed | customer wants supervisor | offer expedited replacement or 15% concession"
custom_input = [{
    "role": "user",
    "content": (
        "Call normalize_support_note with this exact note. Do not answer directly; "
        f"send the note to the custom tool: {support_note}"
    ),
}]
custom_request = {
    "model": MODEL_ID,
    "input": custom_input,
    "tools": custom_tools,
    "tool_choice": {"type": "custom", "name": "normalize_support_note"},
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(custom_request)
print_labeled_text("Result: local fallback normalization", normalize_support_note_text(support_note))
try:
    custom_plan = create_response(**custom_request)
    returned_item_types = [item.get("type") for item in response_items(custom_plan)]
    try:
        custom_call = first_output_item(custom_plan, "custom_tool_call")
        if custom_call is None:
            raise LookupError("No custom_tool_call item returned.")
        tool_input = custom_call.get("input", "").strip()
        normalized_note = normalize_support_note_text(tool_input)
        record_check("Custom tools", "pass", {"output_item_types": returned_item_types, "normalized_note": normalized_note})
        record_response("Normalized support note", "text", normalized_note)
        print_labeled_json("Result: returned output item types", returned_item_types)
        print_labeled_text("Result: custom tool input", tool_input)
        print_labeled_text("Result: application-owned normalized output", normalized_note)
    except LookupError:
        fallback_text = output_text(custom_plan).strip() or "No text content was returned."
        normalized_note = normalize_support_note_text(support_note)
        record_check("Custom tools", "warn", {
            "expected": "custom_tool_call item named normalize_support_note",
            "actual_output_item_types": returned_item_types,
            "meaning": "The model response did not include a custom-tool invocation, so the application fallback normalization is shown for teaching.",
        })
        record_response("Custom tool text fallback", "text", fallback_text)
        record_response("Application-owned normalization fallback", "text", normalized_note)
        print_labeled_json("Result: returned output item types", returned_item_types or ["no typed output items returned"])
        print_labeled_text("Result: model text response", fallback_text)
        print_labeled_text("Result: application-owned normalization", normalized_note)
    print_response_summary(custom_plan)
    print_key_takeaway('Custom tools are useful when the application owns a freeform parsing or execution step.')
except Exception as exc:
    handle_example_error("Custom tools", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 5. 直接送檔案當輸入

直接送檔案跟應用管理的 tool 是兩回事。檔案可以用 `input_file` item 跟文字指示一起放進這次的 Responses 請求，適合模型只需要在這一回合讀檔、不想另外建檢索索引的情況。

### 5.1 把 PDF 當 `input_file` 附上

這個 cell 在記憶體裡產生一個小 PDF 逐字稿，用 base64 檔案資料附上，並要求從文件裡取出精確的 JSON 欄位。看 PDF 預覽、預期欄位、解析後的回應和用量摘要。




```python
from __future__ import annotations
def make_simple_pdf(lines: list[str]) -> bytes:
    def pdf_escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    stream_lines = ["BT", "/F1 11 Tf", "72 740 Td", "15 TL"]
    for idx, line in enumerate(lines):
        if idx:
            stream_lines.append("T*")
        stream_lines.append(f"({pdf_escape(line)}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + builtins.str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{idx} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
    xref_offset = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    return pdf


file_lines = [
    "BrightCart support transcript",
    "Ticket: TICKET-7429",
    "Customer: Maya Chen",
    "Order: ORDER-8831",
    "Product: Standing desk replacement",
    "Issue: Replacement for a damaged item is delayed and carrier scan has not moved",
    "Customer request: Supervisor callback and refund options",
    "Policy options: expedited replacement or 15% concession with agent approval after 48-hour delay",
]
file_text = "\n".join(file_lines)
pdf_data = base64.b64encode(make_simple_pdf(file_lines)).decode("utf-8")

expected_direct_file_fields = {
    "ticket_id": "TICKET-7429",
    "customer": "Maya Chen",
    "order_id": "ORDER-8831",
    "product": "Standing desk replacement",
}

direct_file_request = {
    "model": MODEL_ID,
    "input": [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_file",
                    "filename": "brightcart-support-transcript.pdf",
                    "file_data": f"data:application/pdf;base64,{pdf_data}",
                },
                {
                    "type": "input_text",
                    "text": (
                        "Read the attached PDF support transcript and return JSON with keys "
                        "ticket_id, customer, order_id, product, issue, requested_resolution, and policy_options. "
                        "Use exact values from the file. Do not return null for fields that are present in the file."
                    ),
                },
            ],
        }
    ],
    "text": {"format": {"type": "json_object"}},
    "max_output_tokens": 1024,
    "store": False,
}

print_labeled_text("Result: PDF transcript preview", file_text)
print_request_shape(direct_file_request)
print_labeled_json("Result: expected fields", expected_direct_file_fields)
try:
    direct_file_response = create_response(**direct_file_request)
    raw_direct_file_output = output_text(direct_file_response).strip()
    try:
        direct_file_payload = json.loads(raw_direct_file_output)
        missing_or_empty = [
            key for key, expected in expected_direct_file_fields.items()
            if builtins.str(direct_file_payload.get(key, "")).strip().lower() != expected.lower()
        ]
        null_fields = [key for key, value in direct_file_payload.items() if value in {None, "", []}]
        if missing_or_empty or null_fields:
            record_check("Direct file inputs", "warn", {
                "message": "The request completed, but the model did not extract the expected values from the attached PDF.",
                "missing_or_unexpected_fields": missing_or_empty,
                "empty_fields": null_fields,
                "payload": direct_file_payload,
            })
            record_response("Support transcript extraction returned by model", "json", direct_file_payload)
            print_labeled_text("Result", "The request completed, but the model did not extract the expected values from the attached PDF.")
            print_labeled_json("Result: returned JSON", direct_file_payload)
        else:
            record_check("Direct file inputs", "pass", direct_file_payload)
            record_response("Support transcript extraction", "json", direct_file_payload)
            print_labeled_json("Result", direct_file_payload)
    except Exception as parse_exc:
        record_check("Direct file inputs", "warn", {
            "message": "The request completed, but the response was not valid JSON.",
            "text_sample": raw_direct_file_output[:600],
            "error": builtins.str(parse_exc),
        })
        record_response("Support transcript extraction text", "text", raw_direct_file_output[:1200])
        print_labeled_text("Result", raw_direct_file_output[:1200])
    print_response_summary(direct_file_response)
    print_key_takeaway('Direct file input is useful when the file should be read in the current request context.')
except Exception as exc:
    handle_example_error("Direct file inputs", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 6. 管理對話狀態

對話狀態決定後續回合怎麼拿到之前的 context。Responses API 支援用 `previous_response_id` 延續已儲存的回應，應用也可以自己管理狀態，每次重送相關的輸入歷史。這一節比較這兩種做法，再示範在支援的情況下帶著加密的 reasoning context。



### 6.1 用 `previous_response_id` 延續對話

用 `previous_response_id` 從已儲存的回應繼續，不用重送之前整段 prompt。第一個請求儲存 BrightCart 的案件細節，第二個請求只帶新的追問指示加上前一個 response ID。看追問有沒有保留訂單、客戶、問題和下一步動作。


```python
from __future__ import annotations
promised_delivery = (date.today() + timedelta(days=2)).isoformat()
stateful_seed_input = (
    f"Customer Maya Chen opened ticket TICKET-4812 about order ORDER-8831. "
    "The item is a standing desk replacement for a damaged delivery. "
    f"The promised delivery date is {promised_delivery}, but the carrier scan has not moved in 36 hours. "
    "Customer sentiment is frustrated because this is the second attempt. "
    "Support policy says to offer expedited replacement or a 15% concession if the delay exceeds 48 hours. "
    "Escalation owner is Tier 2 Returns."
)
stateful_followup_input = "Return five labeled lines: ticket ID, order ID, customer name, issue, and next best action."
stateful_request_shape = {
    "model": MODEL_ID,
    "input": stateful_followup_input,
    "previous_response_id": "<response-id-from-prior-stored-turn>",
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(stateful_request_shape)
try:
    stateful_turn_1 = create_response(model=MODEL_ID, input=stateful_seed_input, max_output_tokens=1024, store=True)
    remember_stored_response(stateful_turn_1)
    stateful_turn_2 = create_response(model=MODEL_ID, input=stateful_followup_input, previous_response_id=stateful_turn_1.id, max_output_tokens=1024, store=False)
    text = output_text(stateful_turn_2).strip()
    require("order-8831" in text.lower() or "maya" in text.lower(), "Stateful continuation response missed expected support context.")
    record_check("Stateful continuation", "pass", stateful_turn_1.id)
    record_response("Stateful support handoff", "text", text)
    print_labeled_text("Result", text)
    print_response_summary(stateful_turn_2)
    print_key_takeaway('previous_response_id lets a follow-up use stored context without resending the full prior turn.')
except Exception as exc:
    handle_example_error("Stateful continuation", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 6.2 重建無狀態的 context

無狀態延續的意思是應用每次請求都送出相關歷史。如果你的產品本來就負責對話儲存、保存政策或稽核需求，這個做法很合適。這個 cell 送一小段聊天歷史加上新的交接指示，並檢查摘要和 token 用量。


```python
from __future__ import annotations
stateless_history = [
    {"role": "user", "content": "Support chat TICKET-3920: Customer Jordan Lee says ORDER-7718 arrived with a cracked monitor stand."},
    {"role": "assistant", "content": "Captured damaged-item issue for ORDER-7718 and asked for preferred resolution."},
    {"role": "user", "content": "Jordan wants a replacement shipped this week and asks whether the damaged item must be returned first."},
]
stateless_payload = {
    "model": MODEL_ID,
    "input": stateless_history + [{"role": "user", "content": "Summarize this support chat for the next agent in five labeled plain-text lines. Do not use leading hyphens or bold text."}],
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(stateless_payload)
try:
    stateless_response = create_response(**stateless_payload)
    stateless_text = output_text(stateless_response).strip()
    require(stateless_text, "Stateless continuation response did not return text.")
    record_check("Stateless continuation", "pass", summarize_response(stateless_response))
    record_response("Stateless support handoff", "text", stateless_text)
    print_labeled_text("Result", stateless_text)
    print_response_summary(stateless_response)
    print_key_takeaway('Stateless continuation sends the relevant history with each request when the application owns conversation storage.')
except Exception as exc:
    handle_example_error("Stateless continuation", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 6.3 帶著加密的 reasoning context

支援 reasoning 的模型在要求時，可以回傳 reasoning item 和加密的 reasoning 內容。這個 cell 要求加密的 reasoning 資料，把之前的 response item 帶進後續請求，並檢查有沒有回傳加密內容。隱藏的 reasoning 文字不會被看到，應用只是在支援的情況下把這份不透明的 context 往後帶。

官方文件：[Reasoning models](https://developers.openai.com/api/docs/guides/reasoning) 說明了 Responses 流程裡的 reasoning 模型和 reasoning effort。


```python
from __future__ import annotations
encrypted_history = [
    {"role": "user", "content": "For a customer-support assistant handling names, order IDs, and refund context, compare stateful and stateless continuation in two sentences."}
]
encrypted_turn_payload = {
    "model": MODEL_ID,
    "input": encrypted_history,
    "reasoning": {"effort": "medium"},
    "include": ["reasoning.encrypted_content"],
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(encrypted_turn_payload)
try:
    encrypted_turn_1 = create_response(**encrypted_turn_payload)
    encrypted_turn_2 = create_response(
        model=MODEL_ID,
        input=encrypted_history + response_items(encrypted_turn_1) + [
            {"role": "user", "content": "Based on the prior reasoning context, recommend one approach for a regulated support workflow in two labeled plain-text lines. Do not use leading hyphens or bold text."}
        ],
        max_output_tokens=1024,
        store=False,
    )
    reasoning_items = [item for item in response_items(encrypted_turn_1) if item.get("type") == "reasoning"]
    has_encrypted_content = any(item.get("encrypted_content") for item in reasoning_items)
    record_check("Encrypted reasoning", "pass", {"encrypted_content_returned": has_encrypted_content, "reasoning_item_count": len(reasoning_items)})
    encrypted_answer = output_text(encrypted_turn_2).strip()
    record_response("State strategy recommendation", "text", encrypted_answer)
    print_labeled_json("Result: reasoning metadata", {
        "returned_item_types": [item.get("type") for item in response_items(encrypted_turn_1)],
        "encrypted_reasoning_content_returned": has_encrypted_content,
    })
    print_labeled_text("Result: follow-up answer", encrypted_answer)
    print_response_summary(encrypted_turn_2)
    print_key_takeaway('Encrypted reasoning content can be carried forward where supported without exposing hidden reasoning text.')
except Exception as exc:
    handle_example_error("Encrypted reasoning", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 7. 使用 prompt caching

請求共用完全相同的靜態前綴時，prompt caching 可以降低延遲和成本。

### 7.1 比較兩個帶 cache key 的請求

這個 cell 把固定不變的 BrightCart 政策文字放在 input 最前面，用同一個 `prompt_cache_key` 把同一個請求送兩次，並比較 token 資訊。endpoint 有回傳 cache 細節的話，看第二個 response 的 `cached_input_tokens`。

注意：`PROMPT_CACHE_RETENTION` 是依目前的 `MODEL_ID` 選的。`openai.gpt-5.5` 之後的模型用 `24h`，`openai.gpt-5.4` 用 `in_memory`。


```python
from __future__ import annotations
base_support_policy = [
    "BrightCart support policy:",
    "1. Be empathetic, concise, and specific about the customer's order.",
    "2. Do not promise refunds, credits, or delivery dates unless the policy context supports it.",
    "3. For damaged-item replacements, check replacement status before offering concessions.",
    "4. If a replacement delay exceeds 48 hours, offer expedited replacement or a 15% concession subject to agent approval.",
]
policy_reference_paragraph = (
    "Expanded cacheable policy context: BrightCart agents should identify the customer, order ID, replacement status, "
    "carrier scan age, promised delivery window, item category, prior concessions, and supervisor approval needs before "
    "drafting a customer-facing answer. The assistant should preserve a calm tone, avoid unsupported promises, separate "
    "confirmed facts from assumptions, recommend one clear next action, and document why any escalation, expedited "
    "replacement, or concession is appropriate. Repeated policy context like this is intentionally stable across many "
    "requests so prompt caching can reuse the prefix when the same cache key is supplied."
)
expanded_policy_context = "\n".join(
    f"Policy reference paragraph {idx + 1}: {policy_reference_paragraph}"
    for idx in range(32)
)
stable_support_policy = "\n".join(base_support_policy + [expanded_policy_context])
cache_input = [
    {"role": "system", "content": stable_support_policy},
    {"role": "user", "content": "Draft a two-sentence agent reply for Maya Chen about delayed replacement order ORDER-8831."},
]
estimated_cache_input_words = len(json.dumps(cache_input).split())
require(estimated_cache_input_words > 2048, f"Prompt-cache input should be over 2048 words; found {estimated_cache_input_words}.")
cache_payload = {
    "model": MODEL_ID,
    "input": cache_input,
    "prompt_cache_key": "brightcart-support-policy-v1",
    "prompt_cache_retention": PROMPT_CACHE_RETENTION,
    "max_output_tokens": 1024,
    "store": False,
}

print_request_shape(cache_payload)
print_labeled_json("Prompt-cache input size", {"estimated_input_words": estimated_cache_input_words, "target_minimum_tokens": 2048})
try:
    cache_response_1 = create_response(**cache_payload)
    cache_response_2 = create_response(**cache_payload)
    cache_summary_1 = summarize_response(cache_response_1)
    cache_summary_2 = summarize_response(cache_response_2)
    cache_comparison = pd.DataFrame([
        {
            "request": "first",
            "input_tokens": cache_summary_1.get("input_tokens"),
            "cached_input_tokens": cache_summary_1.get("cached_input_tokens"),
            "output_tokens": cache_summary_1.get("output_tokens"),
            "total_tokens": cache_summary_1.get("total_tokens"),
        },
        {
            "request": "second",
            "input_tokens": cache_summary_2.get("input_tokens"),
            "cached_input_tokens": cache_summary_2.get("cached_input_tokens"),
            "output_tokens": cache_summary_2.get("output_tokens"),
            "total_tokens": cache_summary_2.get("total_tokens"),
        },
    ])
    record_check("Prompt caching", "pass" if cache_summary_2.get("cached_input_tokens") is not None else "warn", {"first": cache_summary_1, "second": cache_summary_2})
    cache_reply = output_text(cache_response_2).strip()
    record_response("Prompt-cache token comparison", "table", cache_comparison)
    record_response("Cached support-policy reply", "text", cache_reply)

    print_labeled_text("Result", cache_reply)
    print_labeled_json("First request summary", cache_summary_1)
    print_labeled_json("Second request summary", cache_summary_2)
    print_label("Response summary")
    display_wrapped_table(cache_comparison, max_col_width_px=260)
    print_key_takeaway('cached_input_tokens is the metadata field to inspect for prompt-cache reuse.')
except Exception as exc:
    handle_example_error("Prompt caching", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 8. 執行背景任務

背景模式會非同步啟動一個 response，讓應用輪詢直到它進入終止狀態。

### 8.1 送出並輪詢背景 response

這個 cell 送出 `background=true` 的請求，儲存 response ID，在 status 是 queued 或 in progress 時持續輪詢，最後印出主管摘要。看 status 的變化歷程、最終 status、response ID 和 token 摘要。




```python
from __future__ import annotations
backlog = """
Same-day BrightCart support backlog:
1. 18 delayed-order contacts, mostly from the West Coast distribution lane.
2. 7 damaged-item replacement contacts; 3 mention replacement delays.
3. 5 return-window exception requests after holiday promotions.
""".strip()
background_payload = {
    "model": MODEL_ID,
    "input": f"Return exactly three labeled plain-text lines for a support-manager summary: theme, risk, next action. Keep each line under 12 words. Do not use leading hyphens or bold text.\n\n{backlog}",
    "background": True,
    "max_output_tokens": 1024,
    "store": True,
}

print_request_shape(background_payload)
try:
    background_response = create_response(**background_payload)
    remember_stored_response(background_response)
    status_history = [getattr(background_response, "status", None)]
    for _ in range(15):
        if getattr(background_response, "status", None) not in {"queued", "in_progress"}:
            break
        time.sleep(2)
        background_response = retrieve_response(background_response.id)
        status_history.append(getattr(background_response, "status", None))
    background_summary = summarize_response(background_response)
    manager_summary = output_text(background_response).strip()
    require(manager_summary, "Background response did not return text.")
    status = "pass" if background_summary.get("status") in {None, "completed"} else "warn"
    record_check("Background mode", status, {"status_history": status_history, "id": getattr(background_response, "id", None), "final_status": background_summary.get("status")})
    record_response("Background manager summary", "text", manager_summary)
    print_labeled_json("Result: status history", status_history)
    print_labeled_text("Result: manager summary", manager_summary)
    print_response_summary(background_summary)
    print_key_takeaway('Background mode starts work asynchronously and lets the application poll by response ID.')
except Exception as exc:
    handle_example_error("Background mode", exc)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 9. 壓縮長時間運行的 context

壓縮（compaction）把很長的對話狀態濃縮成長期有用的事實、未解問題、限制條件和下一步動作。這個 cell 用一個小 JSON 物件說明應用端的壓縮做法，不另外增加實際的功能路徑，把概念講清楚就好。看下一回合之前，哪些事實被留下、哪些細節被省略。




```python
from __future__ import annotations
compaction_note = {
    "feature": "Compaction",
    "how_to_apply": "Summarize older support turns into durable facts, open questions, policy constraints, and next actions before continuing the workflow.",
    "brightcart_example": {
        "durable_facts": ["Customer Maya Chen", "ORDER-8831", "replacement delayed", "carrier scan stale"],
        "policy_constraints": ["Do not promise refund without eligibility", "Offer expedited replacement or 15% concession after 48-hour delay with approval"],
        "next_action": "Check latest carrier scan and supervisor callback status.",
    },
}
record_check("Compaction", "documented", compaction_note)
record_response("Compacted support context", "json", compaction_note)
print_json(compaction_note)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 10. 執行營運冒煙檢查

營運冒煙檢查只是輕量的設定檢查，不是壓力測試，也不是服務水準量測。這個 cell 送三個簡短請求，量測本地經過的時間，彙整成功率和 token 用量，並從設定的 Bedrock base URL 推斷 region。看延遲、完成狀態、範例輸出和 token 總量。


```python
from __future__ import annotations
def infer_region_from_base_url(base_url: str) -> str | None:
    host = normalize_base_url(base_url).replace("https://", "").split("/")[0]
    for part in host.split("."):
        if part.count("-") >= 2 and any(char.isdigit() for char in part):
            return part
    return None


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return round(ordered[index], 3)


operations_features = ["Latency runtime example", "Throughput runtime example", "Reliability runtime example", "Region check"]
operations_payload = {"model": MODEL_ID, "input": "Reply with one short customer-support sentence.", "service_tier": "auto", "max_output_tokens": 1024, "store": False}

print_request_shape(operations_payload)
if not RUN_RESPONSIVENESS_CHECK:
    record_check("Endpoint responsiveness", "skipped", "BEDROCK_RESPONSIVENESS_CHECK is disabled.")
    print_labeled_text("Result", "Responsiveness check disabled.")
else:
    prompts = [
        "Reply in one short sentence: apologize for a delayed replacement order.",
        "Reply with one metric name for support-assistant quality.",
        "Reply in one short sentence: hand off a return exception to a supervisor.",
    ]
    samples = []
    for idx, prompt in enumerate(prompts):
        started = time.perf_counter()
        try:
            response = create_response(model=MODEL_ID, input=prompt, service_tier="auto", max_output_tokens=1024, store=False)
            elapsed = time.perf_counter() - started
            summary = summarize_response(response)
            text = output_text(response).strip()
            samples.append({
                "ok": bool(text),
                "latency_seconds": round(elapsed, 3),
                "output_tokens": summary.get("output_tokens") or 0,
                "total_tokens": summary.get("total_tokens") or 0,
                "status": summary.get("status"),
                "sample_output": text[:140],
            })
        except Exception as exc:
            elapsed = time.perf_counter() - started
            samples.append({"ok": False, "latency_seconds": round(elapsed, 3), "error": describe_api_error(exc)})

    successes = [sample for sample in samples if sample["ok"]]
    completed = [sample for sample in successes if sample.get("status") in {None, "completed"}]
    latencies = [sample["latency_seconds"] for sample in successes]
    responsiveness_summary = {
        "region_hint": infer_region_from_base_url(BASE_URL),
        "base_url_host": normalize_base_url(BASE_URL).replace("https://", "").split("/")[0],
        "sample_count": len(samples),
        "success_rate": len(successes) / len(samples) if samples else 0,
        "completed_rate": len(completed) / len(samples) if samples else 0,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "p50_latency_seconds": percentile(latencies, 50),
        "p90_latency_seconds": percentile(latencies, 90),
        "total_output_tokens": sum(sample.get("output_tokens", 0) for sample in samples),
        "total_tokens": sum(sample.get("total_tokens", 0) for sample in samples),
    }
    status = "pass" if len(successes) == len(samples) and len(completed) == len(samples) else "warn"
    for feature in operations_features:
        record_check(feature, status, responsiveness_summary)
    record_response("Endpoint responsiveness summary", "json", {**responsiveness_summary, "samples": samples})
    print_labeled_json("Result", responsiveness_summary)
    print_label("Response summary")
    display_wrapped_table(pd.DataFrame(samples), max_col_width_px=360)
    print_key_takeaway('Responsiveness samples are setup checks, not a load test or service-level measurement.')
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 11. 清理並檢視結果

生命週期、有狀態延續和背景範例所建立的已儲存 response，都記錄在 `STORED_RESPONSE_IDS`。最後這個 cell 在啟用清理時嘗試刪除這些儲存的 response，然後印出執行摘要和範例 response 的圖庫。先看警告，通常能指出是 endpoint 設定、模型可用性，還是功能支援上的差異。


```python
from __future__ import annotations

cleanup_rows = []
tracked_ids = list(dict.fromkeys(STORED_RESPONSE_IDS))

if not tracked_ids:
    cleanup_rows.append({"response_id": "none", "status": "no stored responses tracked", "detail": ""})
elif not CLEAN_UP_STORED_RESPONSES:
    for stored_id in tracked_ids:
        cleanup_rows.append({"response_id": stored_id, "status": "skipped", "detail": "BEDROCK_CLEANUP_STORED_RESPONSES is disabled"})
    record_check("Stored response cleanup", "skipped", cleanup_rows)
else:
    for stored_id in tracked_ids:
        try:
            delete_result = delete_response(stored_id)
            cleanup_rows.append({"response_id": stored_id, "status": "deleted", "detail": compact_text(to_dict(delete_result), 240)})
        except Exception as exc:
            cleanup_rows.append({"response_id": stored_id, "status": "warn", "detail": describe_api_error(exc)})
    cleanup_status = "pass" if all(row["status"] == "deleted" for row in cleanup_rows) else "warn"
    record_check("Stored response cleanup", cleanup_status, cleanup_rows)

print_label("Stored response cleanup")
display_wrapped_table(pd.DataFrame(cleanup_rows), max_col_width_px=520)

summary_df = pd.DataFrame(RESULTS_SUMMARY)
print_label("Run summary")
display_wrapped_table(summary_df, max_col_width_px=620)

print_label("Example responses")
print_response_gallery()
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
                                      example response_type  \
    0                   Endpoint verification          text   
    1                 First raw HTTPS request          text   
    2                     SDK text generation          text   
    3            Create and retrieve response          text   
    4   Service tier and prompt cache request          text   
    5                Structured ticket triage          json   
    6                    JSON support handoff          json   
    7                 Compact policy guidance          text   
    8                Detailed policy guidance          text   
    9                Order-status tool answer          text   
    10  Parallel order lookup fallback answer          text   
    11                Normalized support note          text   
    12     Support transcript extraction text          text   
    13               Stateful support handoff          text   
    14              Stateless support handoff          text   
    15          State strategy recommendation          text   
    16          Prompt-cache token comparison         table   
    17            Cached support-policy reply          text   
    18             Background manager summary          text   
    19              Compacted support context          json   
    20        Endpoint responsiveness summary          json   

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           response  
    0                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            ok  
    1                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  Empathy: I’m sorry, Maya — your replacement order ORDER-8831 is delayed because the carrier reported a temporary transit hold at the regional sorting facility.\nAction: We’re monitoring the shipment closely and will send you an updated delivery estimate within 24 hours; if there’s no movement by then, we’ll review the next replacement or refund options with you.  
    2                                                                                                                                                                                                                                                                                                                                    Use the Responses API to build a BrightCart support assistant that can answer customer questions, summarize policies, and guide users through common workflows like order tracking, refunds, and account updates. Ground the assistant in BrightCart documentation and connect it to relevant backend tools or APIs so it can retrieve live order data, check account status, and provide accurate, context-aware support responses. Design the experience around clear system instructions, structured tool calling, and conversation state management so the assistant stays on-brand, reliable, and safe when handling customer issues.  
    3                                                                                                                                                                                                                                                                                                                                                                                                            goal: Help support agents explain delayed replacement orders, set expectations, and suggest next steps.\ndata needed: Order ID, replacement order status, shipment/tracking events, delay reason, estimated ship/delivery date, customer contact history, inventory/backorder status, and applicable refund or reship policy.\nhuman-review rule: Escalate to a human if the delay exceeds policy thresholds, tracking is inconsistent or missing, the order appears lost, the customer is high-risk or highly upset, or any refund/reship exception is requested.  
    4                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                Latency benefit: Prompt caching lets the BrightCart support assistant reuse previously processed context, reducing response time for repeated or similar requests.\nConsistency benefit: Prompt caching helps the BrightCart support assistant return more uniform answers by reusing the same established prompt context across interactions.  
    5                          {\n  "ticket_id": "TICKET-7429",\n  "category": "delivery_delay",\n  "priority": "urgent",\n  "customer_sentiment": "frustrated and time-sensitive",\n  "summary": "Customer Maya Chen reports that ORDER-8831 is a replacement shipment for a previously damaged standing desk. The replacement is now 2 days late, carrier tracking has not updated, and she needs the desk delivered before Monday. She is requesting a supervisor callback and wants to know refund options if the replacement cannot arrive in time.",\n  "required_actions": [\n    "Review ORDER-8831 shipment status and confirm last carrier scan/update.",\n    "Contact carrier or open a trace/escalation for stalled tracking.",\n    "Check expedited reshipment or alternative fulfillment options to meet the before-Monday deadline.",\n    "Arrange supervisor callback per customer request.",\n    "Review and communicate refund options, including refund\n...  
    6                                                                                                                                                                                                                                                                                                                                                                                                                                                {\n  "customer_name": "Maya Chen",\n  "order_id": "ORDER-8831",\n  "issue_summary": "Customer is asking about a delayed replacement order. The carrier tracking scan is stale and has not updated.",\n  "next_step": "Handoff to support to investigate the carrier delay, verify shipment status, and provide Maya Chen with an update or resolution.",\n  "metrics_to_watch": [\n    "tracking_scan_recency",\n    "carrier_exception_status",\n    "replacement_order_delivery_eta",\n    "customer_follow_up_time"\n  ]\n}  
    7                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        BrightCart’s delayed-replacement policy lets customers keep using the original item until the replacement arrives, then return the defective product within the allowed return window.  
    8                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                1. BrightCart sends replacements after customers return the original item and warehouse receipt is confirmed.\n2. This delay prevents duplicate shipments, verifies eligibility, and reduces fraud or inventory errors.\n3. Agents should explain timelines clearly, offer return instructions, and reassure customers once receipt is logged.  
    9                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   Status: ORDER-8831 is delayed; carrier shows no movement for 36 hours at the Denver sort center, with promised delivery on 2026-06-01.\nNext best action: Monitor until the 48-hour threshold; if no movement then, contact the customer and offer either an expedited replacement or a 15% concession with agent approval.  
    10                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  Order statuses: ORDER-8831 is delayed and ORDER-2044 was delivered yesterday.\nShipping problems: Maya has one active shipping problem, because only ORDER-8831 is currently delayed while ORDER-2044 is already delivered.  
    11                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          ORDER_ID: ORDER-8831\nCUSTOMER_ID: CUST-1042\nISSUE: REPLACEMENT DELAYED\nCUSTOMER_REQUEST: CUSTOMER WANTS SUPERVISOR\nPOLICY_OPTION: OFFER EXPEDITED REPLACEMENT OR 15% CONCESSION  
    12                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       {"ticket_id":"TICKET-7429","customer":"Maya Chen","order_id":"ORDER-8831","product":"Standing desk replacement","issue":"Replacement for a damaged item is delayed and carrier scan has not moved","requested_resolution":"Supervisor callback and refund options","policy_options":"expedited replacement or 15% concession with agent approval after 48-hour delay"}  
    13                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           Ticket ID: TICKET-4812\nOrder ID: ORDER-8831\nCustomer Name: Maya Chen\nIssue: Replacement standing desk shipment for damaged delivery has had no carrier movement for 36 hours; customer is frustrated because this is the second attempt\nNext Best Action: Monitor until 48 hours without movement, then offer expedited replacement or 15% concession and escalate to Tier 2 Returns if needed  
    14                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        Customer: Jordan Lee reported ORDER-7718 arrived with a cracked monitor stand.\nIssue: Damaged item; monitor stand is cracked on arrival.\nRequested Resolution: Customer wants a replacement shipped this week.\nOpen Question: Jordan asked whether the damaged item must be returned before replacement is sent.\nStatus: Damage claim captured and awaiting next-agent confirmation on replacement timing and return requirement.  
    15                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       Recommendation: Stateless continuation\nReason: In a regulated support workflow, requiring names, order IDs, and refund context to be explicitly provided each turn improves controllability, auditability, and data-minimization, reducing the risk of unintended retention or cross-session leakage.  
    ... (省略 5 行)
    ```

## 重點整理

- 同一組 Responses 請求可以走原始 HTTPS，也可以走 OpenAI SDK，Bedrock 只是換了 base URL 和 bearer token。
- 需要固定格式用 `json_schema` 加 `strict=true`，只要合法 JSON 就用 JSON mode，兩者都該在應用端再驗證一次。
- Function calling 的迴圈是模型提出 call、你的程式執行、再用 `function_call_output` 送回，答案才會有根據。
- 對話狀態有兩種管法，用 `previous_response_id` 讓服務端記，或自己每次重送歷史，選哪個看你的儲存和稽核需求。
- prompt caching 要靠穩定的前綴和 `prompt_cache_key`，長任務可用背景模式輪詢，歷史太長時可以做應用端壓縮。

## 練習

1. 把 3.4 的 `text.verbosity` 改成別的值，或把 2.3 的 `reasoning.effort` 從 `low` 改成 `high`，比較輸出長短和 token 用量的差異。
2. 在 3.1 的 schema 裡多加一個欄位（例如 `order_id`），並在 3.2 的驗證邏輯裡檢查它，看模型有沒有照 schema 回。
3. 在 4.1 新增第三個本地 tool（例如查退貨政策），用 4.3 的寫法讓模型一次平行呼叫三個 tool，確認三份輸出都有送回去。
