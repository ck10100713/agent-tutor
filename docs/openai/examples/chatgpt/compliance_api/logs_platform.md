---
translated: true
source: examples/chatgpt/compliance_api/logs_platform.ipynb
---

# OpenAI Compliance Logs Platform 快速上手

> 原文：[examples/chatgpt/compliance_api/logs_platform.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/compliance_api/logs_platform.ipynb)



## 這篇在做什麼
這篇帶你開始使用 OpenAI Compliance Logs Platform，重點是下載 log 檔，方便匯入你的 SIEM 或 data lake。
提供 Unix 和 Windows 兩個功能相同的 script，會列出可用的 log 檔、翻頁、下載，並把內容輸出到 stdout。

- [Help Center 說明](https://help.openai.com/en/articles/9261474-compliance-api-for-chatgpt-enterprise-edu-and-chatgpt-for-teachers)
- [API Reference](https://chatgpt.com/admin/api-reference#tag/Compliance-API-Logs-Platform)

## 學完你會
- 知道用哪些參數（workspace 或 org ID、event type、limit、after）向 Compliance API 取得指定事件和時間範圍的 log。
- 在 Unix 或 Windows 上跑下載 script，把 log 輸出給後續處理。
- 看懂 script 怎麼列出 log 檔並分頁下載，之後能改寫成自己的整合。

## 開跑前
- 需要 Enterprise Compliance API key，並匯出成環境變數 `COMPLIANCE_API_KEY`。
- 需要要查的 principal 的 ChatGPT account ID 或 API Platform Org ID。
- 依你的環境另有其他需求。

## Quickstart Scripts

下面有兩個功能相同的 script，一個給 Unix 系統，一個給 Windows。
它們示範怎麼用 Compliance API 取得指定事件類型和時間範圍的 log 資料並處理。
script 會列出可用的 log 檔、翻頁並下載，輸出到 stdout。

範例用法寫在 script 的說明區塊裡，不帶參數執行就能看到。

## 方案一：Unix 系統

事前準備：
- 把 script 存成 `download_compliance_files.sh`，並設成可執行
- 確認 `bash`、`curl`、`sed`、`date` 都是新版
- 把你要取得「`after` 之後」所有 log 的時間，寫成含時區的 ISO 8601 字串

執行方式類似 `./download_compliance_files.sh <workspace_or_org_id> <event_type> <limit> <after>`

```bash
#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <workspace_or_org_id> <event_type> <limit> <after>" >&2
  echo >&2
  echo 'Examples: ' >&2
  echo 'COMPLIANCE_API_KEY=<KEY> ./download_compliance_files.sh f7f33107-5fb9-4ee1-8922-3eae76b5b5a0 AUTH_LOG 100 "$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ)" > output.jsonl' >&2
  echo 'COMPLIANCE_API_KEY=<KEY> ./download_compliance_files.sh org-p13k3klgno5cqxbf0q8hpgrk AUTH_LOG 100 "$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ)" > output.jsonl' >&2
}

if [[ $# -ne 4 ]]; then
  usage
  exit 2
fi

PRINCIPAL_ID="$1"
EVENT_TYPE="$2"
LIMIT="$3"
INITIAL_AFTER="$4"

# Require COMPLIANCE_API_KEY to be present and non-empty before using it
if [[ -z "${COMPLIANCE_API_KEY:-}" ]]; then
  echo "COMPLIANCE_API_KEY environment variable is required. e.g.:" >&2
  echo "COMPLIANCE_API_KEY=<KEY> $0 <workspace_or_org_id> <event_type> <limit> <after>" >&2
  exit 2
fi

API_BASE="https://api.chatgpt.com/v1/compliance"
AUTH_HEADER=("-H" "Authorization: Bearer ${COMPLIANCE_API_KEY}")

# Determine whether the first arg is a workspace ID or an org ID.
# If it starts with "org-" treat it as an organization ID and switch the path segment accordingly.
SCOPE_SEGMENT="workspaces"
if [[ "${PRINCIPAL_ID}" == org-* ]]; then
  SCOPE_SEGMENT="organizations"
fi

# Perform a curl request and fail fast on HTTP errors, logging context to stderr.
# Usage: perform_curl "description of action" <curl args...>
perform_curl() {
  local description="$1"
  shift
  # Capture body and HTTP status code, keeping body on stdout-like var
  # We append a newline before the status to reliably split even if body has no trailing newline.
  local combined
  if ! combined=$(curl -sS -w "\n%{http_code}" "$@"); then
    echo "Network/transport error while ${description}" >&2
    exit 1
  fi
  local http_code
  http_code="${combined##*$'\n'}"
  local body
  body="${combined%$'\n'*}"

  if [[ ! "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
    echo "HTTP error ${http_code} while ${description}:" >&2
    if [[ -n "${body}" ]]; then
      # Print the body to stderr so it doesn't corrupt stdout stream
      echo "${body}" | jq . >&2
    fi
    exit 1
  fi

  # On success, emit body to stdout for callers to consume
  echo "${body}"
}

list_logs() {
  local after="$1"
  perform_curl "listing logs (after=${after}, event_type=${EVENT_TYPE}, limit=${LIMIT})" \
    -G \
    "${API_BASE}/${SCOPE_SEGMENT}/${PRINCIPAL_ID}/logs" \
    "${AUTH_HEADER[@]}" \
    --data-urlencode "limit=${LIMIT}" \
    --data-urlencode "event_type=${EVENT_TYPE}" \
    --data-urlencode "after=${after}"
}

download_log() {
  local id="$1"
  echo "Fetching logs for ID: ${id}" >&2
  perform_curl "downloading log id=${id}" \
    -G -L \
    "${API_BASE}/${SCOPE_SEGMENT}/${PRINCIPAL_ID}/logs/${id}" \
    "${AUTH_HEADER[@]}"
}

to_local_human() {
  local iso="$1"
  if [[ -z "${iso}" || "${iso}" == "null" ]]; then
    echo ""
    return 0
  fi

  local iso_norm
  iso_norm=$(echo -n "${iso}" \
    | sed -E 's/\.[0-9]+(Z|[+-][0-9:]+)$/\1/' \
    | sed -E 's/([+-]00:00)$/Z/')

  # macOS/BSD date: parse UTC to epoch then format in local timezone
  local epoch
  epoch=$(date -j -u -f "%Y-%m-%dT%H:%M:%SZ" "${iso_norm}" +%s 2>/dev/null) || true
  if [[ -n "${epoch}" ]]; then
    date -r "${epoch}" "+%Y-%m-%d %H:%M:%S %Z" 2>/dev/null && return 0
  fi

  # Fallback to original if parsing failed
  echo "${iso}"
}

current_after="${INITIAL_AFTER}"
page=1
total_downloaded=0
while true; do
  echo "Fetching page ${page} with after='${current_after}' (local: $(to_local_human "${current_after}"))" >&2
  response_json="$(list_logs "${current_after}")"

  # Count and download each ID from the current page (if any)
  page_count="$(echo "${response_json}" | jq '.data | length')"
  if [[ "${page_count}" -gt 0 ]]; then
    echo "${response_json}" | jq -r '.data[].id' | while read -r id; do
      download_log "${id}"
    done
    total_downloaded=$((total_downloaded + page_count))
  fi

  has_more="$(echo "${response_json}" | jq -r '.has_more')"
  current_after="$(echo "${response_json}" | jq -r '.last_end_time')"
  if [[ "${has_more}" == "true" ]]; then
    page=$((page + 1))
  else
    break
  fi
done

if [[ "${total_downloaded}" -eq 0 && ( -z "${current_after}" || "${current_after}" == "null" ) ]]; then
  echo "No results found for event_type ${EVENT_TYPE} after ${INITIAL_AFTER}" >&2
else
  echo "Completed downloading ${total_downloaded} log files up to ${current_after} (local: $(to_local_human "${current_after}"))" >&2
fi
```

## 方案二：Windows

事前準備：
- 把 script 存成 `download_compliance_files.ps1`
- 開啟 PowerShell（5.1 版以上），切到 script 所在的目錄

執行方式類似 `.\download_compliance_files.ps1 <workspace_or_org_id> <event_type> <limit> <after>`

```ps
#!/usr/bin/env pwsh
#Requires -Version 5.1

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Web

function Show-Usage {
    [Console]::Error.WriteLine(@"
Usage: .\download_compliance_files.ps1 <workspace_or_org_id> <event_type> <limit> <after>

Example:
  `$env:COMPLIANCE_API_KEY = '<KEY>'
  .\download_compliance_files.ps1 f7f33107-5fb9-4ee1-8922-3eae76b5b5a0 AUTH_LOG 100 (Get-Date -AsUTC).AddDays(-1).ToString('yyyy-MM-ddTHH:mm:ssZ') |
    Out-File -Encoding utf8 output.jsonl

Example (org id):
  `$env:COMPLIANCE_API_KEY = '<KEY>'
  .\download_compliance_files.ps1 org-p13k3klgno5cqxbf0q8hpgrk AUTH_LOG 100 (Get-Date -AsUTC).AddDays(-1).ToString('yyyy-MM-ddTHH:mm:ssZ') |
    Out-File -Encoding utf8 output.jsonl
"@)
}

if ($args.Count -ne 4) {
    Show-Usage
    exit 2
}

if (-not $env:COMPLIANCE_API_KEY) {
    [Console]::Error.WriteLine('COMPLIANCE_API_KEY environment variable must be set.')
    exit 2
}

$PrincipalId = $args[0]
$EventType = $args[1]
$Limit = $args[2]
$InitialAfter = $args[3]

$ApiBase = 'https://api.chatgpt.com/v1/compliance'

if ($PrincipalId.StartsWith('org-')) {
    $ScopeSegment = 'organizations'
} else {
    $ScopeSegment = 'workspaces'
}

$handler = [System.Net.Http.HttpClientHandler]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $env:COMPLIANCE_API_KEY)

function Invoke-ComplianceRequest {
    param(
        [Parameter(Mandatory = $true)] [string] $Description,
        [Parameter(Mandatory = $true)] [string] $Path,
        [hashtable] $Query = @{}
    )

    $builder = [System.UriBuilder]::new("$ApiBase/$ScopeSegment/$PrincipalId/$Path")
    $queryString = [System.Web.HttpUtility]::ParseQueryString($builder.Query)
    foreach ($key in $Query.Keys) {
        $queryString[$key] = $Query[$key]
    }
    $builder.Query = $queryString.ToString()

    try {
        $response = $client.GetAsync($builder.Uri).GetAwaiter().GetResult()
    } catch {
        [Console]::Error.WriteLine("Network/transport error while $Description")
        exit 1
    }

    $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $response.IsSuccessStatusCode) {
        [Console]::Error.WriteLine("HTTP error $($response.StatusCode.value__) while ${Description}:")
        if ($body) {
            try {
                $parsed = $body | ConvertFrom-Json
                $parsed | ConvertTo-Json -Depth 10 | Write-Error
            } catch {
                [Console]::Error.WriteLine($body)
            }
        }
        exit 1
    }

    Write-Output $body
}

function List-Logs {
    param(
        [Parameter(Mandatory = $true)] [string] $After
    )

    Invoke-ComplianceRequest -Description "listing logs (after=$After, event_type=$EventType, limit=$Limit)" -Path 'logs' -Query @{
        limit      = $Limit
        event_type = $EventType
        after      = $After
    }
}

function Download-Log {
    param(
        [Parameter(Mandatory = $true)] [string] $Id
    )

    [Console]::Error.WriteLine("Fetching logs for ID: $Id")
    Invoke-ComplianceRequest -Description "downloading log id=$Id" -Path "logs/$Id"
}

function ConvertTo-LocalHuman {
    param(
        [string] $Iso
    )

    if (-not $Iso -or $Iso -eq 'null') {
        return ''
    }

    try {
        $dt = [datetimeoffset]::Parse($Iso)
        return $dt.ToLocalTime().ToString('yyyy-MM-dd HH:mm:ss zzz')
    } catch {
        return $Iso
    }
}

$currentAfter = $InitialAfter
$page = 1
$totalDownloaded = 0
while ($true) {
    [Console]::Error.WriteLine("Fetching page $page with after='$currentAfter' (local: $(ConvertTo-LocalHuman -Iso $currentAfter))")
    $responseJson = List-Logs -After $currentAfter
    $responseObj = $responseJson | ConvertFrom-Json

    $pageCount = $responseObj.data.Count
    if ($pageCount -gt 0) {
        foreach ($entry in $responseObj.data) {
            Download-Log -Id $entry.id
        }
        $totalDownloaded += $pageCount
    }

    $hasMore = $false
    if ($null -ne $responseObj.has_more) {
        $hasMore = [System.Convert]::ToBoolean($responseObj.has_more)
    }

    $currentAfter = $responseObj.last_end_time
    if ($hasMore) {
        $page += 1
    } else {
        break
    }
}

if ($totalDownloaded -eq 0 -and ([string]::IsNullOrEmpty($currentAfter) -or $currentAfter -eq 'null')) {
    [Console]::Error.WriteLine("No results found for event_type $EventType after $InitialAfter")
} else {
    [Console]::Error.WriteLine("Completed downloading $totalDownloaded log files up to $currentAfter (local: $(ConvertTo-LocalHuman -Iso $currentAfter))")
}

$client.Dispose()
$handler.Dispose()
```

## 重點整理
- Compliance Logs Platform 提供 log 檔下載，適合接到 SIEM 或 data lake 做稽核和分析。
- 查詢由 principal ID、event type、數量上限和起始時間決定。
- log 檔要先列出再分頁下載，所以 script 的重點是處理翻頁。
- 兩個平台的 script 邏輯一致，只是 shell 不同，挑環境對應的那份即可。

## 練習
1. 不帶參數執行 script，讀說明區塊，列出它支援的 event type。
2. 把 `<after>` 改成不同的 ISO 8601 時間，比較下載到的 log 檔數量。
3. 把 `<limit>` 調小，觀察 script 翻頁的次數怎麼變，並把輸出導向檔案存起來。
