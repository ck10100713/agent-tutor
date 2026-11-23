---
translated: true
source: examples/codex/secure_quality_gitlab.md
---
# 用 Codex CLI 在 GitLab 自動化程式碼品質與資安修復

> 原文：[examples/codex/secure_quality_gitlab.md](https://github.com/openai/openai-cookbook/blob/main/examples/codex/secure_quality_gitlab.md)



## 這篇在做什麼
把 Codex CLI 塞進 GitLab CI/CD pipeline，讓它在 merge 前幫你做兩件事：產出 GitLab 看得懂的 code quality 報告，以及把既有 SAST 掃描結果整理成有優先順序的修復建議和 patch。重點是 prompt、JSON marker 抽取、schema 驗證這套做法，讓 LLM 的輸出能穩定被程式吃進去。

## 學完你會
- 寫出一個 GitLab CI job，用 Codex CLI 產出符合 CodeClimate JSON 格式的報告，直接顯示在 merge request。
- 讓 Codex 讀 `gl-sast-report.json`，去重、依可利用性排序，輸出 `security_priority.md`。
- 讓 Codex 對 High/Critical 問題產生 `git diff` patch，並用 `git apply --check` 驗證。

## 開跑前
- GitLab 帳號和專案，runner 要能連外（`api.openai.com`）。
- `OPENAI_API_KEY`，設在 Settings → CI/CD → Variables。

> **更新說明：使用這些範例前請先看最新的官方說明。** 下面用到的 `--full-auto` 旗標已經棄用。Codex 執行失敗或輸出無效時，不要當成「沒有發現問題」。一般的 Codex 自動化請看 [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)。專門的 Codex Security 掃描與修復，請用維護中的 [GitLab CI/CD 指南](https://learn.chatgpt.com/docs/security/cli/ci/gitlab)。那套流程跟本文的程式碼品質分析、解讀既有 SAST 結果不同，下面的範例還沒遷移過去。

## 簡介

正式環境的程式碼上線前，大部分團隊靠 CI/CD pipeline 在 merge 前把關。reviewer 通常看單元測試結果、弱點掃描和 code quality 報告。這些傳統上都是規則引擎產出的，抓得到已知問題，但常漏掉需要上下文才看得出的問題，結果又吵又難排優先順序。

有了 LLM，你可以多加一層：讓它判斷程式碼品質、解讀資安發現。在 GitLab pipeline 裡加上 **OpenAI 的 Codex CLI**，可以拿到靜態規則給不了的東西：

* **Code Quality** → 產出符合 GitLab 規格的 CodeClimate JSON 報告，把有上下文的問題直接顯示在 merge request。

* **Security** → 對既有 SAST 結果做後處理，合併重複項目、依可利用性排序，並給出清楚、可執行的修復步驟。

這篇會示範怎麼把 Codex CLI 接進 GitLab pipeline 處理這兩種情境，同時產出機器可讀的結構化報告和人看得懂的修復指引。

## Codex CLI 是什麼？

Codex CLI 是開源的命令列工具，讓你把 OpenAI 的 reasoning 模型帶進開發流程。安裝、用法和完整文件請看官方 repo：[github.com/openai/codex](https://github.com/openai/codex?utm_source=chatgpt.com)。

這篇會在臨時的 GitLab runner 上用 **Full Auto mode** 產出符合標準的 JSON 報告。

### 前置需求

要跟著做，你需要：

* GitLab 帳號和專案  
* 有**網路連線**的 GitLab runner（我們測試的是 2 vCPU、8GB 記憶體、30GB 儲存的 Linux runner）  
* Runner 必須能連到 `api.openai.com`  
* **OpenAI API key**（`OPENAI_API_KEY`）  
* 在 **Settings → CI/CD → Variables** 設好 GitLab CI/CD 變數

## 範例 #1：用 Codex CLI 產生 Code Quality 報告

### 背景

這個 repo 是一個刻意留有漏洞的 Node.js Express demo app，基於 [GitLab 的 node express 範本](https://gitlab.com/gitlab-org/project-templates/express/-/tree/main)，用來展示 GitLab CI/CD 的靜態應用程式安全測試（SAST）和 code quality 掃描。

程式裡有常見的坑，像 command injection、path traversal、不安全的 `eval`、regex DoS、弱加密（MD5）、寫死的 secret。用它來驗證 Codex 驅動的分析器能不能產出 GitLab 原生報告（Code Quality 和 SAST），並直接顯示在 merge request。

CI 跑在 GitLab SaaS runner 上，用 `node:24` image，再加幾個工具（`jq`、`curl`、`ca-certificates`、`ajv-cli`）。Job 用 `set -euo pipefail`、schema 驗證和嚴格的 JSON marker 做防護，這樣就算 Codex 輸出有變化，解析還是穩的。

這套模式（prompt、JSON marker 抽取、schema 驗證）也能套到其他技術棧，只是 prompt 措辭和 schema 規則可能要微調。因為 Codex 跑在 sandbox 裡，有些系統指令（像 `awk` 或 `nl`）可能被限制。

你的團隊希望 merge 前**自動跑 code quality 檢查**。要讓發現直接顯示在 GitLab 的 merge request widget，報告必須符合 **CodeClimate JSON 格式**。[參考：GitLab 文件](https://docs.gitlab.com/ci/testing/code_quality/#import-code-quality-results-from-a-cicd-job)

### Code Quality CI/CD Job 範例

這是一個可以直接放進去的 GitLab CI job，用 **Codex CLI** 產出合規的 JSON 檔：
```yaml
stages: [codex]

default:
  image: node:24
  variables:
    CODEX_QA_PATH: "gl-code-quality-report.json"
    CODEX_RAW_LOG: "artifacts/codex-raw.log"
    # Strict prompt: must output a single JSON array (or []), no prose/markdown/placeholders.
    CODEX_PROMPT: |
      Review this repository and output a GitLab Code Quality report in CodeClimate JSON format.
      RULES (must follow exactly):
      - OUTPUT MUST BE A SINGLE JSON ARRAY. Example: [] or [ {...}, {...} ].
      - If you find no issues, OUTPUT EXACTLY: []
      - DO NOT print any prose, backticks, code fences, markdown, or placeholders.
      - DO NOT write any files. PRINT ONLY between these two lines:
        === BEGIN_CODE_QUALITY_JSON ===
        <JSON ARRAY HERE>
        === END_CODE_QUALITY_JSON ===
      Each issue object MUST include these fields:
        "description": String,
        "check_name": String (short rule name),
        "fingerprint": String (stable across runs for same issue),
        "severity": "info"|"minor"|"major"|"critical"|"blocker",
        "location": { "path": "<repo-relative-file>", "lines": { "begin": <line> } }
      Requirements:
      - Use repo-relative paths from the current checkout (no "./", no absolute paths).
      - Use only files that actually exist in this repo.
      - No trailing commas. No comments. No BOM.
      - Prefer concrete, de-duplicated findings. If uncertain, omit the finding.

codex_review:
  stage: codex
  # Skip on forked MRs (no secrets available). Run only if OPENAI_API_KEY exists.
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID != $CI_PROJECT_ID'
      when: never
    - if: '$OPENAI_API_KEY'
      when: on_success
    - when: never

  script:
    - set -euo pipefail
    - echo "PWD=$(pwd)  CI_PROJECT_DIR=${CI_PROJECT_DIR}"
    # Ensure artifacts always exist so upload never warns, even on early failure
    - mkdir -p artifacts
    - ': > ${CODEX_RAW_LOG}'
    - ': > ${CODEX_QA_PATH}'
    # Minimal deps + Codex CLI
    - apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git lsb-release
    - npm -g i @openai/codex@latest
    - codex --version && git --version
    # Build a real-file allowlist to guide Codex to valid paths/lines
    - FILE_LIST="$(git ls-files | sed 's/^/- /')"
    - |
      export CODEX_PROMPT="${CODEX_PROMPT}
      Only report issues in the following existing files (exactly as listed):
      ${FILE_LIST}"
    # Run Codex; allow non-zero exit but capture output for extraction
    - |
      set +o pipefail
      script -q -c 'codex exec --full-auto "$CODEX_PROMPT"' | tee "${CODEX_RAW_LOG}" >/dev/null
      CODEX_RC=${PIPESTATUS[0]}
      set -o pipefail
      echo "Codex exit code: ${CODEX_RC}"
    # Strip ANSI + \r, extract JSON between markers to a temp file; validate or fallback to []
    - |
      TMP_OUT="$(mktemp)"
      sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g' "${CODEX_RAW_LOG}" \
        | tr -d '\r' \
        | awk '
            /^\s*=== BEGIN_CODE_QUALITY_JSON ===\s*$/ {grab=1; next}
            /^\s*=== END_CODE_QUALITY_JSON ===\s*$/   {grab=0}
            grab
          ' > "${TMP_OUT}"
      # If extracted content is empty/invalid or still contains placeholders, replace with []
      if ! node -e 'const f=process.argv[1]; const s=require("fs").readFileSync(f,"utf8").trim(); if(!s || /(<JSON ARRAY HERE>|BEGIN_CODE_QUALITY_JSON|END_CODE_QUALITY_JSON)/.test(s)) process.exit(2); JSON.parse(s);' "${TMP_OUT}"; then
        echo "WARNING: Extracted content empty/invalid; writing empty [] report."
        echo "[]" > "${TMP_OUT}"
      fi
      mv -f "${TMP_OUT}" "${CODEX_QA_PATH}"
      # Soft warning if Codex returned non-zero but we still produced a report
      if [ "${CODEX_RC}" -ne 0 ]; then
        echo "WARNING: Codex exited with code ${CODEX_RC}. Proceeding with extracted report." >&2
      fi

  artifacts:
    when: always
    reports:
      codequality: gl-code-quality-report.json
    paths:
      - artifacts/codex-raw.log
    expire_in: 14 days
```

1. 安裝 Codex CLI（`npm -g i @openai/codex@latest`）  
2. 用 `git ls-files` 建立檔案 allowlist  
3. 用嚴格的「只輸出 JSON」prompt 以 full-auto mode 跑 Codex  
4. 抽出 marker 之間的合法 JSON、驗證，無效就退回 `[]`  
5. 把 artifact 發佈到 GitLab，結果會直接顯示在 merge request

產出的 artifact 可以從 pipeline 頁面下載

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gitlab-pipelines-success.png" alt="GitLab Pipelines" width="700"/>

如果是從 feature branch merge 到 master，則會顯示在這裡，

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gitlab-mr-widget.png" alt="GitLab Merge Request Widget" width="700"/>

把 Codex CLI 嵌進 GitLab CI/CD pipeline，你可以**讓 code quality 檢查超越靜態規則**。不再只抓語法錯誤或風格違規，而是做基於推理的分析，把潛在問題連同上下文一起指出來。

這種做法有幾個好處：

* **一致性**：每個 merge request 都經過同一套推理流程審查  
* **理解上下文**：LLM 可以標出規則型掃描器漏掉的細微問題  
* **賦能開發者**：回饋即時、看得到、可以直接動手

團隊採用這個流程後，LLM 驅動的品質檢查可以補強傳統的 lint 和弱點掃描，讓上線的程式碼既穩健又好維護。

## 範例 #2：用 Codex CLI 做資安修復

### 背景

這個範例我們用 [OWASP Juice Shop](https://github.com/juice-shop/juice-shop?utm_source=chatgpt.com) 測試，它是刻意留有漏洞的 Node.js Express app，包含 injection、不安全的 `eval`、弱加密、寫死的 secret 等常見缺陷，很適合驗證 Codex 的分析能力。

你的團隊希望每次有程式碼變更，pipeline 都會在 merge 前自動檢查資安漏洞。這件事靜態分析器和各語言的掃描器已經在做，它們會產出 GitLab SAST JSON schema 格式的報告。不過原始輸出往往死板、雜訊多，reviewer 看完還是不知道下一步該做什麼。

把 Codex CLI 加進 pipeline，你可以把 [GitLab SAST 掃描器](https://docs.gitlab.com/user/application_security/sast/)（或其他掃描器）的結果變成**可執行的修復指引**，甚至產出**可直接套用的 git patch**：

### 步驟 1：產生建議

* Codex 讀取 `gl-sast-report.json`。  
* 合併重複的發現。  
* 依可利用性排序（例如使用者輸入 → 危險的 sink）。  
* 產出簡潔的 `security_priority.md`，包含前 5 大行動和詳細修復說明。

#### 資安建議 CI/CD Job 範例

**前提**：這個 job 預期上游的 SAST job 已經產生 `gl-sast-report.json`。Codex 讀取它，產出給 reviewer 看的 `security_priority.md`。

```yaml
stages:
 - codex
 - remediation

default:
 image: node:24

variables:
 CODEX_SAST_PATH: "gl-sast-report.json"
 CODEX_SECURITY_MD: "security_priority.md"
 CODEX_RAW_LOG: "artifacts/codex-sast-raw.log"

 # --- Recommendations prompt (reads SAST → writes Markdown) ---
 CODEX_PROMPT: |
   You are a security triage assistant analyzing GitLab SAST output.
   The SAST JSON is located at: ${CODEX_SAST_PATH}

   GOAL:
   - Read and parse ${CODEX_SAST_PATH}.
   - Consolidate duplicate or overlapping findings (e.g., same CWE + same sink/function, same file/line ranges, or same data flow root cause).
   - Rank findings by realistic exploitability and business risk, not just library presence.
     * Prioritize issues that:
       - Are reachable from exposed entry points (HTTP handlers, controllers, public APIs, CLI args).
       - Involve user-controlled inputs reaching dangerous sinks (e.g., SQL exec, OS exec, eval, path/file ops, deserialization, SSRF).
       - Occur in authentication/authorization boundaries or around secrets/keys/tokens.
       - Have clear call stacks/evidence strings pointing to concrete methods that run.
       - Affect internet-facing or privileged components.
     * De-prioritize purely theoretical findings with no reachable path or dead code.

   CONSOLIDATION RULES:
   - Aggregate by (CWE, primary sink/function, file[:line], framework route/handler) when applicable.
   - Merge repeated instances across files if they share the same source-sink pattern and remediation is the same.
   - Keep a single representative entry with a count of affected locations; list notable examples.

   OUTPUT FORMAT (MARKDOWN ONLY, BETWEEN MARKERS BELOW):
   - Start with a title and short summary of total findings and how many were consolidated.
   - A table of TOP PRIORITIES sorted by exploitability (highest first) with columns:
     Rank | CWE | Title | Affected Locations | Likely Exploit Path | Risk | Rationale (1–2 lines)
   - "Top 5 Immediate Actions" list with concrete next steps.
   - "Deduplicated Findings (Full Details)" with risk, 0–100 exploitability score, evidence (file:line + methods), remediation, owners, references.
   - If ${CODEX_SAST_PATH} is missing or invalid JSON, output a brief note stating no parsable SAST findings.

   RULES (must follow exactly):
   - PRINT ONLY between these two lines:
     === BEGIN_SECURITY_MD ===
     <MARKDOWN CONTENT HERE>
     === END_SECURITY_MD ===
   - No prose, backticks, code fences, or anything outside the markers.
   - Be concise but specific. Cite only evidence present in the SAST report.

# ---------------------------
# Stage: codex → Job 1 (Recommendations)
# ---------------------------
codex_recommendations:
 stage: codex
 rules:
   - if: '$CI_PIPELINE_SOURCE == "merge_request_event" && $CI_MERGE_REQUEST_SOURCE_PROJECT_ID != $CI_PROJECT_ID'
     when: never
   - if: '$OPENAI_API_KEY'
     when: on_success
   - when: never
 script:
   - set -euo pipefail
   - mkdir -p artifacts
   - ": > ${CODEX_RAW_LOG}"
   - ": > ${CODEX_SECURITY_MD}"

   - apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git lsb-release
   - npm -g i @openai/codex@latest
   - codex --version && git --version

   - |
     if [ ! -s "${CODEX_SAST_PATH}" ]; then
       echo "WARNING: ${CODEX_SAST_PATH} not found or empty. Codex will emit a 'no parsable findings' note."
     fi

   - FILE_LIST="$(git ls-files | sed 's/^/- /')"
   - |
     export CODEX_PROMPT="${CODEX_PROMPT}

     Existing repository files (for reference only; use paths exactly as listed in SAST evidence):
     ${FILE_LIST}"

   # Run Codex and capture raw output (preserve Codex's exit code via PIPESTATUS)
   - |
     set +o pipefail
     codex exec --full-auto "$CODEX_PROMPT" | tee "${CODEX_RAW_LOG}" >/dev/null
     CODEX_RC=${PIPESTATUS[0]}
     set -o pipefail
     echo "Codex exit code: ${CODEX_RC}"

   # Extract markdown between markers; fallback to a minimal note
   - |
     TMP_OUT="$(mktemp)"
     sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g' "${CODEX_RAW_LOG}" | tr -d '\r' | awk '
       /^\s*=== BEGIN_SECURITY_MD ===\s*$/ {grab=1; next}
       /^\s*=== END_SECURITY_MD ===\s*$/   {grab=0}
       grab
     ' > "${TMP_OUT}"
     if ! [ -s "${TMP_OUT}" ]; then
       cat > "${TMP_OUT}" <<'EOF' # Security Findings Priority
       No parsable SAST findings detected in `gl-sast-report.json`._
     EOF
       echo "WARNING: No content extracted; wrote minimal placeholder."
     fi
     mv -f "${TMP_OUT}" "${CODEX_SECURITY_MD}"
     if [ "${CODEX_RC}" -ne 0 ]; then
       echo "WARNING: Codex exited with code ${CODEX_RC}. Proceeding with extracted report." >&2
     fi
 artifacts:
   when: always
   paths:
     - artifacts/codex-sast-raw.log
     - security_priority.md
   expire_in: 14 days
```
下面是我們拿到的輸出範例：

### 輸出範例：合併後的 SAST 發現

Parsed `gl-sast-report.json` and merged overlapping issues.  
**Total raw findings:** 5 → **Consolidated into:** 4 representative entries  
(duplicated SQL injection patterns across endpoints were merged).

#### Summary Table

| Rank | CWE      | Title                                | Affected Locations | Likely Exploit Path                  | Risk     | Rationale (1–2 lines)                                                                                 |
|------|----------|--------------------------------------|-------------------|--------------------------------------|----------|--------------------------------------------------------------------------------------------------------|
| 1    | CWE-798  | Hardcoded JWT private key            | 1                 | Auth token issuance / verification   | Critical | Repo leak enables minting valid admin JWTs; trivial exploitation, internet-facing.                     |
| 2    | CWE-89   | SQL injection in login and search    | 2                 | Login endpoint; product search       | Critical | Raw SQL concatenation; direct login bypass and data exfiltration via public HTTP handlers.             |
| 3    | CWE-94   | Server-side code injection via eval  | 1                 | User profile update handler          | High     | `eval()` on user input allows RCE; conditionally enabled but still high-impact when reachable.          |
| 4    | — (SSRF) | SSRF via arbitrary image URL fetch   | 1                 | Image URL fetch/write flow           | High     | Outbound fetch of unvalidated URLs enables internal service / metadata access (e.g., AWS metadata).     |

#### Top 5 Immediate Actions
1. Replace hardcoded JWT signing key in `lib/insecurity.ts:23`; load from secret storage, rotate keys, and invalidate existing tokens.  
2. Update `routes/login.ts:34` to use parameterized queries; remove raw concatenation; validate and escape inputs.  
3. Fix `routes/search.ts:23` by using ORM bind parameters or escaped `LIKE` helpers instead of string concatenation.  
4. Refactor `routes/userProfile.ts:55–66`; replace `eval()` with safe templating or a whitelisted evaluator.  
5. Harden image import logic: allowlist schemes/hosts, block link-local/metadata IPs, apply timeouts and size limits.  

##### Deduplicated Findings (Full Details)

##### 1. CWE-798 — Hardcoded JWT private key
- Risk: Critical — Exploitability 98/100  
- Evidence:  
  - File: `lib/insecurity.ts:23`  
  - Message: RSA private key embedded in source enables forged admin tokens  
- Suggested Remediation: Remove key from source, load via env/secret manager, rotate keys, enforce short TTLs  
- Owners/Teams: Backend/Core (lib)  
- References: CWE-798; OWASP ASVS 2.1.1, 2.3.1  
---
##### 2. CWE-89 — SQL injection (login & search)
- Risk: Critical — Exploitability 95/100  
- Evidence:  
  - `routes/login.ts:34` — classic login bypass via `' OR 1=1--`  
  - `routes/search.ts:23` — UNION-based extraction via `%25' UNION SELECT ...`  
- Suggested Remediation: Use parameterized queries/ORM, validate inputs, add WAF/error suppression  
- Owners/Teams: Backend/API (routes)  
- References: CWE-89; OWASP Top 10 A03:2021; ASVS 5.3  
---
##### 3. CWE-94 — Server-side code injection (`eval`)
- Risk: High — Exploitability 72/100  
- Evidence:  
  - `routes/userProfile.ts:55–66` — `eval()` used for dynamic username patterns  
- Suggested Remediation: Remove `eval()`, or sandbox with strict whitelist; validate/encode inputs  
- Owners/Teams: Backend/API (routes)  
- References: CWE-94; OWASP Top 10 A03:2021  
---
##### 4. SSRF — Arbitrary image URL fetch
- Risk: High — Exploitability 80/100  
- Evidence:  
  - Image import fetches arbitrary `imageUrl` → can hit internal services (`169.254.169.254`)  
- Suggested Remediation: Enforce HTTPS + DNS/IP allowlist, block RFC1918/link-local, validate post-resolution, no redirects  
- Owners/Teams: Backend/API (routes)  
- References: OWASP SSRF Prevention; OWASP Top 10 A10:2021  
---
### 步驟 2：根據建議修復資安問題
- Codex 同時讀取 SAST JSON 和 repo 目錄結構。  
- 對每個 High/Critical 問題：  
  - 建立結構化 prompt → 輸出統一格式的 `git diff`。  
  - diff 會先用 `git apply --check` 驗證，才存成 `.patch`。  

#### 修復 CI/CD Job 範例

**前提**：這個 job 依賴前一個 stage 產出的 `security_priority.md`，把它當輸入來產生 patch 檔，之後拿去建立 MR：
```yaml
 stages:
  - remediation

default:
  image: node:24

variables:
  # Inputs/outputs
  SAST_REPORT_PATH: "gl-sast-report.json"
  PATCH_DIR: "codex_patches"
  CODEX_DIFF_RAW: "artifacts/codex-diff-raw.log"

  # --- Resolution prompt (produces unified git diffs only) ---
  CODEX_DIFF_PROMPT: |
    You are a secure code remediation assistant.
    You will receive:
    - The repository working tree (read-only)
    - One vulnerability (JSON from a GitLab SAST report)
    - Allowed files list

    GOAL:
    - Create the minimal, safe fix for the vulnerability.
    - Output a unified git diff that applies cleanly with `git apply -p0` (or -p1 for a/ b/ paths).
    - Prefer surgical changes: input validation, safe APIs, parameterized queries, permission checks.
    - Do NOT refactor broadly or change unrelated code.

    RULES (must follow exactly):
    - PRINT ONLY the diff between the markers below.
    - Use repo-relative paths; `diff --git a/path b/path` headers are accepted.
    - No binary file changes. No prose/explanations outside the markers.

    MARKERS:
    === BEGIN_UNIFIED_DIFF ===
    <unified diff here>
    === END_UNIFIED_DIFF ===

    If no safe fix is possible without deeper changes, output an empty diff between the markers.

# ---------------------------
# Stage: remediation → Generate unified diffs/patches
# ---------------------------
codex_resolution:
  stage: remediation
  rules:
    - if: '$OPENAI_API_KEY'
      when: on_success
    - when: never
  script:
    - set -euo pipefail
    - mkdir -p "$PATCH_DIR" artifacts

    # Deps
    - apt-get update && apt-get install -y --no-install-recommends bash git jq curl ca-certificates
    - npm -g i @openai/codex@latest
    - git --version && codex --version || true

    # Require SAST report; no-op if missing
    - |
      if [ ! -s "${SAST_REPORT_PATH}" ]; then
        echo "No SAST report found; remediation will no-op."
        printf "CODEX_CREATED_PATCHES=false\n" > codex.env
        exit 0
      fi

    # Pull High/Critical items
    - jq -c '.vulnerabilities[]? | select((.severity|ascii_downcase)=="high" or (.severity|ascii_downcase)=="critical")' "$SAST_REPORT_PATH" \
        | nl -ba > /tmp/hicrit.txt || true
    - |
      if [ ! -s /tmp/hicrit.txt ]; then
        echo "No High/Critical vulnerabilities found. Nothing to fix."
        printf "CODEX_CREATED_PATCHES=false\n" > codex.env
        exit 0
      fi

    # Ground Codex to actual repo files
    - FILE_LIST="$(git ls-files | sed 's/^/- /')"

    # Identity for any local patch ops
    - git config user.name "CI Codex Bot"
    - git config user.email "codex-bot@example.com"

    - created=0

    # Loop: build prompt (robust temp-file), run Codex, extract diff, validate
    - |
      while IFS=$'\t' read -r idx vuln_json; do
        echo "Processing vulnerability #$idx"
        echo "$vuln_json" > "/tmp/vuln-$idx.json"

        PROMPT_FILE="$(mktemp)"
        {
          printf "%s\n\n" "$CODEX_DIFF_PROMPT"
          printf "VULNERABILITY_JSON:\n<<JSON\n"
          cat "/tmp/vuln-$idx.json"
          printf "\nJSON\n\n"
          printf "EXISTING_REPOSITORY_FILES (exact list):\n"
          printf "%s\n" "$FILE_LIST"
        } > "$PROMPT_FILE"

        PER_FINDING_PROMPT="$(tr -d '\r' < "$PROMPT_FILE")"
        rm -f "$PROMPT_FILE"

        : > "$CODEX_DIFF_RAW"
        set +o pipefail
        codex exec --full-auto "$PER_FINDING_PROMPT" | tee -a "$CODEX_DIFF_RAW" >/dev/null
        RC=${PIPESTATUS[0]}
        set -o pipefail
        echo "Codex (diff) exit code: ${RC}"

        OUT_PATCH="$PATCH_DIR/fix-$idx.patch"
        sed -E 's/\x1B\[[0-9;]*[A-Za-z]//g' "$CODEX_DIFF_RAW" \
          | tr -d '\r' \
          | awk '
              /^\s*=== BEGIN_UNIFIED_DIFF ===\s*$/ {grab=1; next}
              /^\s*=== END_UNIFIED_DIFF ===\s*$/   {grab=0}
              grab
            ' > "$OUT_PATCH"

        if ! [ -s "$OUT_PATCH" ] || ! grep -qE '^\s*diff --git ' "$OUT_PATCH"; then
          echo "  No usable diff produced for #$idx; skipping."
          rm -f "$OUT_PATCH"
          continue
        fi

        # Validate: accept -p0 (repo-relative) or -p1 (a/ b/ prefixes)
        if git apply --check -p0 "$OUT_PATCH" || git apply --check -p1 "$OUT_PATCH"; then
          echo "  Patch validated → $OUT_PATCH"
          created=$((created+1))
        else
          echo "  Patch failed to apply cleanly; removing."
          rm -f "$OUT_PATCH"
        fi
      done < /tmp/hicrit.txt

      if [ "$created" -gt 0 ]; then
        printf "CODEX_CREATED_PATCHES=true\nPATCH_DIR=%s\n" "$PATCH_DIR" > codex.env
      else
        printf "CODEX_CREATED_PATCHES=false\n" > codex.env
      fi
  artifacts:
    when: always
    paths:
      - codex_patches/
      - artifacts/codex-diff-raw.log
    reports:
      dotenv: codex.env
    expire_in: 14 days
```

跑完這個用 Codex CLI 的 CI/CD job，我們拿到一個 Git patch，修掉了原本掃描器找到的問題：

```patch
<unified diff here>
diff --git a/routes/profileImageUrlUpload.ts b/routes/profileImageUrlUpload.ts
index 9b4a62d..c7f1a7e 100644
--- a/routes/profileImageUrlUpload.ts
+++ b/routes/profileImageUrlUpload.ts
@@ -5,17 +5,12 @@
 * SPDX-License-Identifier: MIT
 */
-import fs from 'node:fs'
-import { Readable } from 'node:stream'
-import { finished } from 'node:stream/promises'
import { type Request, type Response, type NextFunction } from 'express'
import * as security from '../lib/insecurity'
import { UserModel } from '../models/user'
-import * as utils from '../lib/utils'
-import logger from '../lib/logger'
export function profileImageUrlUpload () {
  return async (req: Request, res: Response, next: NextFunction) => {
    if (req.body.imageUrl !== undefined) {
      const url = req.body.imageUrl
      if (url.match(/(.)*solve\\/challenges\\/server-side(.)*/) !== null) req.app.locals.abused_ssrf_bug = true
      const loggedInUser = security.authenticatedUsers.get(req.cookies.token)
      if (loggedInUser) {
-        try {
-          const response = await fetch(url)
-          if (!response.ok || !response.body) {
-            throw new Error('url returned a non-OK status code or an empty body')
-          }
-          const ext = ['jpg', 'jpeg', 'png', 'svg', 'gif'].includes(url.split('.').slice(-1)[0].toLowerCase()) ? url.split('.').slice(-1)[0].toLowerCase() : 'jpg'
-          const fileStream = fs.createWriteStream(`frontend/dist/frontend/assets/public/images/uploads/${loggedInUser.data.id}.${ext}`, { flags: 'w' })
-          await finished(Readable.fromWeb(response.body as any).pipe(fileStream))
-          await UserModel.findByPk(loggedInUser.data.id).then(async (user: UserModel | null) => { return await user?.update({ profileImage: `/assets/public/images/uploads/${loggedInUser.data.id}.${ext}` }) }).catch((error: Error) => { next(error) })
-        } catch (error) {
-          try {
-            const user = await UserModel.findByPk(loggedInUser.data.id)
-            await user?.update({ profileImage: url })
-            logger.warn(`Error retrieving user profile image: ${utils.getErrorMessage(error)}; using image link directly`)
-          } catch (error) {
-            next(error)
-            return
-          }
-        }
+        try {
+          const user = await UserModel.findByPk(loggedInUser.data.id)
+          await user?.update({ profileImage: url })
+        } catch (error) {
+          next(error)
+          return
+        }
      } else {
        next(new Error('Blocked illegal activity by ' + req.socket.remoteAddress))
        return
```

## 主要好處
在 GitLab CI/CD 裡用 Codex CLI，可以補強現有的 review 流程，讓團隊出貨更快。

* **互補**：Codex 不取代掃描器，它解讀掃描器的發現並加速修復。 
* **可執行**：reviewer 看到的不只是漏洞，還有排好優先順序的修復步驟。  
* **自動化**：patch 直接在 CI 裡產生，可以拿去 `git apply` 或開修復 branch。  

---

## 總結

這篇示範了怎麼把 **Codex CLI** 嵌進 GitLab CI/CD pipeline，讓軟體交付更安全、更好維護：

* **Code Quality 報告**：產出符合 GitLab 規格的 CodeClimate JSON，讓推理型的發現跟 lint、單元測試、風格檢查一起顯示。

* **漏洞解讀**：拿 SAST 和其他掃描器的原始輸出（`gl-sast-report.json`），轉成有優先順序、人看得懂的計畫（`security_priority.md`），包含去重、可利用性排序和具體下一步。

* **自動修復**：延伸流程，讓 Codex 產生統一格式的 git diff 存成 `.patch`。這些 patch 會先驗證（`git apply --check`），之後可以自動套用到新 branch。

整體來看，LLM 驅動的分析是補強傳統規則型工具，而不是取代。偵測仍以掃描器為準，Codex 補上上下文理解、優先順序、開發者指引，甚至能透過 MR 提出具體修法。GitLab 的 schema 和 API 提供結構，讓這些輸出可預期、可執行，也能完整融入開發流程。

最關鍵的心得是，要有好結果需要**清楚的 prompt、schema 驗證和護欄**。JSON marker、severity 白名單、schema 強制檢查和 diff 驗證，才能讓輸出真的可用。

接下來，這個模式可以延伸成用同一條 Codex 修復流程整合所有主要掃描類型：

* **Dependency Scans** → 彙整各 lockfile 的 CVE，建議升級版本，並自動產生升級有漏洞套件的 diff。  
* **Container/Image Scans** → 標出過時的 base image，建議 Dockerfile 的修改。  
* **DAST 結果** → 找出可被利用的 endpoint，並修補 routing/middleware 加上驗證或存取控制。  

把這些合併成單一個 Codex 驅動的後處理加修復 pipeline，團隊就能在所有資安領域得到一致的**可執行指引和驗證過的 patch**。

**更大的結論：**搭配 prompt engineering、schema 驗證，以及整合進 GitLab 原生的 MR 流程，LLM 會從「顧問」變成**一等公民的 CI/CD agent**，幫團隊交付的程式碼不只能用，還安全、好維護，而且盡可能自動修好。

## 重點整理
- 規則型掃描器負責偵測，LLM 負責解讀、排序和提修法，兩者互補。
- 讓 LLM 輸出可被程式消化的關鍵是 JSON marker、schema 驗證，以及失敗時退回安全預設值。
- 報告格式要對齊 GitLab 的 schema（CodeClimate、SAST），才能直接顯示在 merge request。
- patch 要先 `git apply --check` 驗證才存檔，避免產出壞掉的 diff。
- 這份範例用的 `--full-auto` 已棄用，實際使用前要對照最新官方指南。

## 練習
1. 把 Code Quality job 的 prompt 改成只回報某一類問題（例如只看 `eval` 和 command injection），看輸出的 JSON 有什麼變化。
2. 在 `security_priority.md` 的 prompt 裡把「前 5 大行動」改成前 3 大，或加上「Owners/Teams」以外的欄位，確認輸出還能通過你的驗證。
3. 修改修復 job，讓它只處理 Critical 等級的問題，並在 `git apply --check` 失敗時讓 job 明確失敗，而不是默默產出空 patch。
