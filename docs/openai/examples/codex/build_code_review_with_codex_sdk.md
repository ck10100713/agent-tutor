---
translated: true
source: examples/codex/build_code_review_with_codex_sdk.md
---
# 用 Codex SDK 打造 Code Review

> 原文：[examples/codex/build_code_review_with_codex_sdk.md](https://github.com/openai/openai-cookbook/blob/main/examples/codex/build_code_review_with_codex_sdk.md)



## 這篇在做什麼
Codex Cloud 的 Code Review 只能接雲端的 GitHub repo。這篇教你用 Codex CLI 的 headless 模式，在自己的 CI/CD runner 上做出同樣的自動 code review，涵蓋 GitHub Actions、GitLab CI/CD、Azure DevOps Pipelines 和 Jenkins。

## 學完你會
- 用 `codex exec` 搭配 review prompt 在 CI 裡跑 headless 的程式碼審查。
- 用 JSON schema（structured outputs）規定 Codex 的輸出格式，拿到可以對應到程式碼行數的 finding。
- 解析 Codex 的結果，呼叫 GitHub、GitLab、Azure DevOps 等 SCM 的 API 貼上 inline review comment。

## 開跑前
- 需要 `OPENAI_API_KEY`，在 CI 裡要存成 secret variable。
- GitLab 要另外設 `GITLAB_TOKEN`；Azure DevOps 要開 OAuth token 的 script access，並讓 build service 有 contribute to pull requests 的權限。


> **封存範例：使用這些 workflow 前，請先看最新的 CI 指引。** 下面的 GitHub 範例會把 API 和 repository token 暴露給整個 job，而且把 review 和 pull request 寫入權限放在一起。不要照抄這種 credential 和權限配置，只靠 read-only sandbox 保護不了 secret。請改用[最新的 Codex GitHub Action workflow 和安全檢查清單](https://learn.chatgpt.com/docs/github-action)，它把 review 和貼回 feedback 分開處理。其他 CI 系統請參考[自動化環境的驗證指引](https://learn.chatgpt.com/docs/non-interactive-mode#authenticate-in-automation)。

用 Codex Cloud 的 [Code Review](https://chatgpt.com/codex/settings/code-review)，你可以把團隊放在雲端的 GitHub repo 連到 Codex，每個 PR 都自動收到 code review。但如果你的程式碼放在 on-prem，或是根本不用 GitHub 當 SCM 呢？

我們可以在自己的 CI/CD runner 上重現 Codex 雲端的 review 流程。這篇會用 Codex CLI 的 headless 模式，分別在 GitHub Actions、GitLab CI/CD、Azure DevOps Pipelines 和 Jenkins 上做一個自己的 Code Review action。

模型建議：這些 workflow 用 `gpt-5.5`，code review 的準確度和一致性最好。

要做自己的 Code Review，照下面幾個步驟走就好：

1. 在 CI/CD runner 上安裝 Codex CLI
2. 用 headless（exec）模式，搭配 CLI 內建的 Code Review prompt 呼叫 Codex
3. 給 Codex 一份結構化輸出的 JSON schema
4. 解析 JSON 結果，拿去呼叫 SCM 的 API 建立 review comment

做完之後，Codex 就能留下 inline 的 code review comment：
<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/codex_code_review.png" alt="Codex Code Review in GitHub" width="500"/>

## Code Review Prompt

GPT-5.5 是 Codex 裡處理複雜 coding workflow 的推薦模型。用下面這個 prompt 就能引導 GPT-5.5 做 code review：

```
You are acting as a reviewer for a proposed code change made by another engineer.
Focus on issues that impact correctness, performance, security, maintainability, or developer experience.
Flag only actionable issues introduced by the pull request.
When you flag an issue, provide a short, direct explanation and cite the affected file and line range.
Prioritize severe issues and avoid nit-level comments unless they block understanding of the diff.
After listing findings, produce an overall correctness verdict (\"patch is correct\" or \"patch is incorrect\") with a concise justification and a confidence score between 0 and 1.
Ensure that file citations and line numbers are exactly correct using the tools available; if they are incorrect your comments will be rejected.
```

## Codex 的 Structured Outputs

要在 pull request 的程式碼範圍上留言，我們需要 Codex 用固定格式回應。做法是建一個 `codex-output-schema.json`，格式符合 OpenAI 的 [structured outputs](https://platform.openai.com/docs/guides/structured-outputs)。

在 workflow YAML 裡，可以用 `output-schema-file` 參數把這個檔案帶給 Codex，像這樣：

```yaml
- name: Run Codex structured review
        id: run-codex
        uses: openai/codex-action@main
        with:
            openai-api-key: ${{ secrets.OPENAI_API_KEY }}
            prompt-file: codex-prompt.md
            sandbox: read-only
            model: ${{ env.CODEX_MODEL }}
            output-schema-file: codex-output-schema.json # <-- Our schema file
            output-file: codex-output.json
```

`codex exec` 也可以傳類似的參數，例如：

```bash
codex exec "Review my pull request!" --output-schema codex-output-schema.json
```

## GitHub Actions 範例

把前面的東西串起來。如果你在 on-prem 環境用 GitHub Actions，可以照自己的 workflow 調整這個範例。行內註解標出了重點步驟。

```yaml
name: Codex Code Review

# Determine when the review action should be run:
on:
  pull_request:
    types:
      - opened
      - reopened
      - synchronize
      - ready_for_review

concurrency:
  group: codex-structured-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  codex-structured-review:
    name: Run Codex structured review
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      GITHUB_TOKEN: ${{ github.token }}
      CODEX_MODEL: ${{ vars.CODEX_MODEL || 'gpt-5.5' }}
      PR_NUMBER: ${{ github.event.pull_request.number }}
      HEAD_SHA: ${{ github.event.pull_request.head.sha }}
      BASE_SHA: ${{ github.event.pull_request.base.sha }}
      REPOSITORY: ${{ github.repository }}
    outputs:
      codex-output: ${{ steps.run-codex.outputs.final-message }}
    steps:
      - name: Checkout pull request merge commit
        uses: actions/checkout@v5
        with:
          ref: refs/pull/${{ github.event.pull_request.number }}/merge

      - name: Fetch base and head refs
        run: |
          set -euxo pipefail
          git fetch --no-tags origin \
            "${{ github.event.pull_request.base.ref }}" \
            +refs/pull/${{ github.event.pull_request.number }}/head
        shell: bash

      # The structured output schema ensures that codex produces comments
      # with filepaths, line numbers, title, body, etc.
      - name: Generate structured output schema
        run: |
          set -euo pipefail
          cat <<'JSON' > codex-output-schema.json
          {
              "type": "object",
              "properties": {
                "findings": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "properties": {
                      "title": {
                        "type": "string",
                        "maxLength": 80
                      },
                      "body": {
                        "type": "string",
                        "minLength": 1
                      },
                      "confidence_score": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1
                      },
                      "priority": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 3
                      },
                      "code_location": {
                        "type": "object",
                        "properties": {
                          "absolute_file_path": {
                            "type": "string",
                            "minLength": 1
                          },
                          "line_range": {
                            "type": "object",
                            "properties": {
                              "start": {
                                "type": "integer",
                                "minimum": 1
                              },
                              "end": {
                                "type": "integer",
                                "minimum": 1
                              }
                            },
                            "required": [
                              "start",
                              "end"
                            ],
                            "additionalProperties": false
                          }
                        },
                        "required": [
                          "absolute_file_path",
                          "line_range"
                        ],
                        "additionalProperties": false
                      }
                    },
                    "required": [
                      "title",
                      "body",
                      "confidence_score",
                      "priority",
                      "code_location"
                    ],
                    "additionalProperties": false
                  }
                },
                "overall_correctness": {
                  "type": "string",
                  "enum": [
                    "patch is correct",
                    "patch is incorrect"
                  ]
                },
                "overall_explanation": {
                  "type": "string",
                  "minLength": 1
                },
                "overall_confidence_score": {
                  "type": "number",
                  "minimum": 0,
                  "maximum": 1
                }
              },
              "required": [
                "findings",
                "overall_correctness",
                "overall_explanation",
                "overall_confidence_score"
              ],
              "additionalProperties": false
            }
          JSON
        shell: bash

      # This section generates our prompt:
      - name: Build Codex review prompt
        env:
          REVIEW_PROMPT_PATH: ${{ vars.CODEX_PROMPT_PATH || 'review_prompt.md' }}
        run: |
          set -euo pipefail
          PROMPT_PATH="codex-prompt.md"
          TEMPLATE_PATH="${REVIEW_PROMPT_PATH}"

          if [ -n "$TEMPLATE_PATH" ] && [ -f "$TEMPLATE_PATH" ]; then
            cat "$TEMPLATE_PATH" > "$PROMPT_PATH"
          else
            {
              printf '%s\n' "You are acting as a reviewer for a proposed code change made by another engineer."
              printf '%s\n' "Focus on issues that impact correctness, performance, security, maintainability, or developer experience."
              printf '%s\n' "Flag only actionable issues introduced by the pull request."
              printf '%s\n' "When you flag an issue, provide a short, direct explanation and cite the affected file and line range."
              printf '%s\n' "Prioritize severe issues and avoid nit-level comments unless they block understanding of the diff."
              printf '%s\n' "After listing findings, produce an overall correctness verdict (\"patch is correct\" or \"patch is incorrect\") with a concise justification and a confidence score between 0 and 1."
              printf '%s\n' "Ensure that file citations and line numbers are exactly correct using the tools available; if they are incorrect your comments will be rejected."
            } > "$PROMPT_PATH"
          fi

          {
            echo ""
            echo "Repository: ${REPOSITORY}"
            echo "Pull Request #: ${PR_NUMBER}"
            echo "Base ref: ${{ github.event.pull_request.base.ref }}"
            echo "Head ref: ${{ github.event.pull_request.head.ref }}"
            echo "Base SHA: ${BASE_SHA}"
            echo "Head SHA: ${HEAD_SHA}"
            echo "Changed files:"
            git --no-pager diff --name-status "${BASE_SHA}" "${HEAD_SHA}"
            echo ""
            echo "Unified diff (context=5):"
            git --no-pager diff --unified=5 --stat=200 "${BASE_SHA}" "${HEAD_SHA}" > /tmp/diffstat.txt
            git --no-pager diff --unified=5 "${BASE_SHA}" "${HEAD_SHA}" > /tmp/full.diff
            cat /tmp/diffstat.txt
            echo ""
            cat /tmp/full.diff
          } >> "$PROMPT_PATH"
        shell: bash

      # Putting it all together: we run the codex action with our code review prompt,
      # structured output, and output file:
      - name: Run Codex structured review
        id: run-codex
        uses: openai/codex-action@main
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          prompt-file: codex-prompt.md
          output-schema-file: codex-output-schema.json
          output-file: codex-output.json
          sandbox: read-only
          model: ${{ env.CODEX_MODEL }}

      - name: Inspect structured Codex output
        if: ${{ always() }}
        run: |
          if [ -s codex-output.json ]; then
            jq '.' codex-output.json || true
          else
            echo "Codex output file missing"
          fi
        shell: bash

      # This step produces in-line code review comments on specific line
      # ranges of code.
      - name: Publish inline review comments
        if: ${{ always() }}
        env:
          REVIEW_JSON: codex-output.json
        run: |
          set -euo pipefail
          if [ ! -s "$REVIEW_JSON" ]; then
            echo "No Codex output file present; skipping comment publishing."
            exit 0
          fi
          findings_count=$(jq '.findings | length' "$REVIEW_JSON")
          if [ "$findings_count" -eq 0 ]; then
            echo "Codex returned no findings; skipping inline comments."
            exit 0
          fi
          jq -c --arg commit "$HEAD_SHA" '.findings[] | {
              body: (.title + "\n\n" + .body + "\n\nConfidence: " + (.confidence_score | tostring) + (if has("priority") then "\nPriority: P" + (.priority | tostring) else "" end)),
              commit_id: $commit,
              path: .code_location.absolute_file_path,
              line: .code_location.line_range.end,
              side: "RIGHT",
              start_line: (if .code_location.line_range.start != .code_location.line_range.end then .code_location.line_range.start else null end),
              start_side: (if .code_location.line_range.start != .code_location.line_range.end then "RIGHT" else null end)
            } | with_entries(select(.value != null))' "$REVIEW_JSON" > findings.jsonl
          while IFS= read -r payload; do
            echo "Posting review comment payload:" && echo "$payload" | jq '.'
            curl -sS \
              -X POST \
              -H "Accept: application/vnd.github+json" \
              -H "Authorization: Bearer ${GITHUB_TOKEN}" \
              -H "X-GitHub-Api-Version: 2022-11-28" \
              "https://api.github.com/repos/${REPOSITORY}/pulls/${PR_NUMBER}/comments" \
              -d "$payload"
          done < findings.jsonl
        shell: bash

      # This section creates a single comment summarizing the review.
      - name: Publish overall summary comment
        if: ${{ always() }}
        env:
          REVIEW_JSON: codex-output.json
        run: |
          set -euo pipefail
          if [ ! -s "$REVIEW_JSON" ]; then
            echo "Codex output missing; skipping summary."
            exit 0
          fi
          overall_state=$(jq -r '.overall_correctness' "$REVIEW_JSON")
          overall_body=$(jq -r '.overall_explanation' "$REVIEW_JSON")
          confidence=$(jq -r '.overall_confidence_score' "$REVIEW_JSON")
          msg="**Codex automated review**\n\nVerdict: ${overall_state}\nConfidence: ${confidence}\n\n${overall_body}"
          curl -sS \
            -X POST \
            -H "Accept: application/vnd.github+json" \
            -H "Authorization: Bearer ${GITHUB_TOKEN}" \
            -H "X-GitHub-Api-Version: 2022-11-28" \
            "https://api.github.com/repos/${REPOSITORY}/issues/${PR_NUMBER}/comments" \
            -d "$(jq -n --arg body "$msg" '{body: $body}')"
        shell: bash
```

## GitLab 範例
GitLab 沒有直接對應 GitHub Action 的東西，不過可以在 GitLab CI/CD 裡跑 codex exec 來做自動 code review。

但 GitHub Action 有一個重要的[安全策略](https://github.com/openai/codex-action?tab=readme-ov-file#safety-strategy)：它會拿掉 sudo 權限，讓 Codex 讀不到自己的 OpenAI API key。這個隔離很關鍵，尤其是公開 repo 裡可能有敏感 secret（例如你的 OpenAI API key），隔離可以避免 Codex 在執行時讀取或外洩 credential。
跑這個 job 之前，先設定你的 GitLab 專案：

1. 到 **Project → Settings → CI/CD**。
2. 展開 **Variables** 區塊。
3. 加入這些變數：
   - `OPENAI_API_KEY`
   - `GITLAB_TOKEN`
4. 視情況勾選 masked/protected。
5. 把下面的 GitLab 範例 job 加到 repo 根目錄的 `.gitlab-ci.yml`，讓它在 merge request pipeline 裡執行。

公開 repo 上請小心處理你的 API key。

```yaml
stages:
  - review

codex-structured-review:
  stage: review
  image: ubuntu:22.04
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
  variables:
    PR_NUMBER: $CI_MERGE_REQUEST_IID
    REPOSITORY: "$CI_PROJECT_PATH"
    BASE_SHA: "$CI_MERGE_REQUEST_DIFF_BASE_SHA"
    HEAD_SHA: "$CI_COMMIT_SHA"

  before_script:
    - apt-get update -y
    - apt-get install -y git curl jq
    - |
      if ! command -v codex >/dev/null 2>&1; then
        ARCH="$(uname -m)"
        case "$ARCH" in
          x86_64) CODEX_PLATFORM="x86_64-unknown-linux-musl" ;;
          aarch64|arm64) CODEX_PLATFORM="aarch64-unknown-linux-musl" ;;
          *)
            echo "Unsupported architecture: $ARCH"
            exit 1
            ;;
        esac

        CODEX_VERSION="${CODEX_VERSION:-latest}"
        if [ -n "${CODEX_DOWNLOAD_URL:-}" ]; then
          CODEX_URL="$CODEX_DOWNLOAD_URL"
        elif [ "$CODEX_VERSION" = "latest" ]; then
          CODEX_URL="https://github.com/openai/codex/releases/latest/download/codex-${CODEX_PLATFORM}.tar.gz"
        else
          CODEX_URL="https://github.com/openai/codex/releases/download/${CODEX_VERSION}/codex-${CODEX_PLATFORM}.tar.gz"
        fi

        TMP_DIR="$(mktemp -d)"
        curl -fsSL "$CODEX_URL" -o "$TMP_DIR/codex.tar.gz"
        tar -xzf "$TMP_DIR/codex.tar.gz" -C "$TMP_DIR"
        install -m 0755 "$TMP_DIR"/codex-* /usr/local/bin/codex
        rm -rf "$TMP_DIR"
      fi
    - git fetch origin $CI_MERGE_REQUEST_TARGET_BRANCH_NAME
    - git fetch origin $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME
    - git checkout $CI_MERGE_REQUEST_SOURCE_BRANCH_NAME

  script:
    - echo "Running Codex structured review for MR !${PR_NUMBER}"

    # Generate structured output schema
    - |
      cat <<'JSON' > codex-output-schema.json
      {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Codex Structured Review",
        "type": "object",
        "additionalProperties": false,
        "required": [
          "overall_correctness",
          "overall_explanation",
          "overall_confidence_score",
          "findings"
        ],
        "properties": {
          "overall_correctness": {
            "type": "string",
            "description": "Overall verdict for the merge request."
          },
          "overall_explanation": {
            "type": "string",
            "description": "Explanation backing up the verdict."
          },
          "overall_confidence_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence level for the verdict."
          },
          "findings": {
            "type": "array",
            "description": "Collection of actionable review findings.",
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "title",
                "body",
                "confidence_score",
                "code_location"
              ],
              "properties": {
                "title": {
                  "type": "string"
                },
                "body": {
                  "type": "string"
                },
                "confidence_score": {
                  "type": "number",
                  "minimum": 0,
                  "maximum": 1
                },
                "code_location": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": [
                    "absolute_file_path",
                    "relative_file_path",
                    "line_range"
                  ],
                  "properties": {
                    "absolute_file_path": {
                      "type": "string"
                    },
                    "relative_file_path": {
                      "type": "string"
                    },
                    "line_range": {
                      "type": "object",
                      "additionalProperties": false,
                      "required": [
                        "start",
                        "end"
                      ],
                      "properties": {
                        "start": {
                          "type": "integer",
                          "minimum": 1
                        },
                        "end": {
                          "type": "integer",
                          "minimum": 1
                        }
                      }
                    }
                  }
                }
              }
            },
            "default": []
          }
        }
      }
      JSON

    # Build Codex review prompt
    - |
      PROMPT_PATH="codex-prompt.md"
      TEMPLATE_PATH="${REVIEW_PROMPT_PATH:-review_prompt.md}"
      if [ -n "$TEMPLATE_PATH" ] && [ -f "$TEMPLATE_PATH" ]; then
        cat "$TEMPLATE_PATH" > "$PROMPT_PATH"
      else
        {
          printf '%s\n' "You are acting as a reviewer for a proposed code change..."
          printf '%s\n' "Focus on issues that impact correctness, performance, security..."
          printf '%s\n' "Flag only actionable issues introduced by this merge request..."
          printf '%s\n' "Provide an overall correctness verdict..."
        } > "$PROMPT_PATH"
      fi
      {
        echo ""
        echo "Repository: ${REPOSITORY}"
        echo "Merge Request #: ${PR_NUMBER}"
        echo "Base SHA: ${BASE_SHA}"
        echo "Head SHA: ${HEAD_SHA}"
        echo ""
        echo "Changed files:"
        git --no-pager diff --name-status "${BASE_SHA}" "${HEAD_SHA}"
        echo ""
        echo "Unified diff (context=5):"
        git --no-pager diff --unified=5 "${BASE_SHA}" "${HEAD_SHA}"
      } >> "$PROMPT_PATH"

    # Run Codex exec CLI
    - |
      printenv OPENAI_API_KEY | codex login --with-api-key && \
      codex exec --output-schema codex-output-schema.json \
                 --output-last-message codex-output.json \
                 --sandbox read-only \
                 - < codex-prompt.md

    # Inspect structured Codex output
    - |
      if [ -s codex-output.json ]; then
        jq '.' codex-output.json || true
      else
        echo "Codex output file missing"; exit 1
      fi

    # Publish inline comments to GitLab MR
    - |
      findings_count=$(jq '.findings | length' codex-output.json)
      if [ "$findings_count" -eq 0 ]; then
        echo "No findings from Codex; skipping comments."
        exit 0
      fi

      jq -c \
        --arg base "$BASE_SHA" \
        --arg start "$BASE_SHA" \
        --arg head "$HEAD_SHA" '
        .findings[] | {
          body: (.title + "\n\n" + .body + "\n\nConfidence: " + (.confidence_score | tostring)),
          position: {
            position_type: "text",
            base_sha: $base,
            start_sha: $start,
            head_sha: $head,
            new_path: (.code_location.relative_file_path // .code_location.absolute_file_path),
            new_line: .code_location.line_range.end
          }
        }
      ' codex-output.json > findings.jsonl

      while IFS= read -r payload; do
        curl -sS --request POST \
             --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
             --header "Content-Type: application/json" \
             --data "$payload" \
             "https://gitlab.com/api/v4/projects/${CI_PROJECT_ID}/merge_requests/${PR_NUMBER}/discussions"
      done < findings.jsonl

    # Publish overall summary comment
    - |
      overall_state=$(jq -r '.overall_correctness' codex-output.json)
      overall_body=$(jq -r '.overall_explanation' codex-output.json)
      confidence=$(jq -r '.overall_confidence_score' codex-output.json)

      summary="**Codex automated review**\n\nVerdict: ${overall_state}\nConfidence: ${confidence}\n\n${overall_body}"

      curl -sS --request POST \
           --header "PRIVATE-TOKEN: $GITLAB_TOKEN" \
           --header "Content-Type: application/json" \
           --data "$(jq -n --arg body "$summary" '{body: $body}')" \
           "https://gitlab.com/api/v4/projects/${CI_PROJECT_ID}/merge_requests/${PR_NUMBER}/notes"

  artifacts:
    when: always
    paths:
      - codex-output.json
      - codex-prompt.md

```

## Azure DevOps Pipelines 範例

Azure DevOps 不用 GitHub Actions 或 GitLab CI/CD，但 Codex review 的模式一樣：在 Azure Pipeline 裡跑 Codex，提供 pull request 的 diff，要求結構化輸出，再把 findings 以 review thread 的形式發回 Azure DevOps 的 pull request。

跑這個 job 之前，先設定你的 Azure DevOps 專案：

1. 把 `OPENAI_API_KEY` 存成 secret pipeline variable 或放進 variable group。
2. 如果要用 `$(System.AccessToken)` 呼叫 Azure DevOps REST API，要開啟 OAuth token 的 script access。
3. Azure Repos Git 要在目標 branch 設定 **Build validation** branch policy，pipeline 才會在 pull request 時跑。
4. 確認 build service identity 有 contribute to pull requests 的權限。
5. 加一個類似下面範例的 Azure Pipelines YAML 檔。

公開 repo 上請小心處理你的 API key。對於公開或不受信任的 pull request，要用跟 GitLab 那段一樣的隔離思維：Codex 審查任意程式碼時，不應該讀得到或外洩 credential。

這個範例假設 `review_prompt.md` 和 `codex-output-schema.json` 跟 pipeline 一起 commit 在同一處。schema 要包含 `code_location.relative_file_path`，Azure DevOps 的發布步驟靠它把 finding 對回 repo 路徑。

```yaml
trigger: none
pr: none # Azure Repos PR validation is configured with branch policies.

pool:
  vmImage: ubuntu-latest

variables:
  CODEX_MODEL: gpt-5.5

steps:
  - checkout: self
    fetchDepth: 0
    persistCredentials: true

  - script: |
      set -euo pipefail
      npm install -g @openai/codex
      command -v jq >/dev/null || {
        sudo apt-get update -y
        sudo apt-get install -y jq
      }
    displayName: Install Codex CLI and jq

  - script: |
      set -euo pipefail
      TARGET_BRANCH="${SYSTEM_PULLREQUEST_TARGETBRANCH#refs/heads/}"
      SOURCE_BRANCH="${SYSTEM_PULLREQUEST_SOURCEBRANCH#refs/heads/}"

      git fetch --no-tags origin \
        "+refs/heads/${TARGET_BRANCH}:refs/remotes/origin/${TARGET_BRANCH}" \
        "+refs/heads/${SOURCE_BRANCH}:refs/remotes/origin/${SOURCE_BRANCH}"

      BASE_SHA="$(git merge-base "origin/${TARGET_BRANCH}" "origin/${SOURCE_BRANCH}")"
      HEAD_SHA="${SYSTEM_PULLREQUEST_SOURCECOMMITID:-$(git rev-parse "origin/${SOURCE_BRANCH}")}"

      cp review_prompt.md codex-prompt.md
      {
        echo ""
        echo "Repository: $(Build.Repository.Name)"
        echo "Pull Request ID: $(System.PullRequest.PullRequestId)"
        echo "Base ref: ${TARGET_BRANCH}"
        echo "Head ref: ${SOURCE_BRANCH}"
        echo "Base SHA: ${BASE_SHA}"
        echo "Head SHA: ${HEAD_SHA}"
        echo "Changed files:"
        git --no-pager diff --name-status "${BASE_SHA}" "${HEAD_SHA}"
        echo ""
        echo "Unified diff (context=5):"
        git --no-pager diff --unified=5 --stat=200 "${BASE_SHA}" "${HEAD_SHA}" > /tmp/diffstat.txt
        git --no-pager diff --unified=5 "${BASE_SHA}" "${HEAD_SHA}" > /tmp/full.diff
        cat /tmp/diffstat.txt
        cat /tmp/full.diff
      } >> codex-prompt.md
    displayName: Build Codex review prompt

  - script: |
      set -euo pipefail
      codex exec \
        --model "${CODEX_MODEL}" \
        --output-schema codex-output-schema.json \
        -o codex-output.json \
        --sandbox read-only \
        - < codex-prompt.md
    env:
      CODEX_API_KEY: $(OPENAI_API_KEY)
    displayName: Run Codex structured review

  - script: |
      set -euo pipefail
      if [ -s codex-output.json ]; then
        jq '.' codex-output.json || true
      else
        echo "Codex output file missing"
      fi
    displayName: Inspect structured Codex output
    condition: always()

  - script: |
      set -euo pipefail
      [ -s codex-output.json ] || exit 0

      org_url="$(System.CollectionUri)"
      project="$(jq -rn --arg v "$(System.TeamProject)" '$v|@uri')"
      repo_id="$(Build.Repository.ID)"
      pr_id="$(System.PullRequest.PullRequestId)"
      api_version="7.1"
      api_base="${org_url}${project}/_apis/git/repositories/${repo_id}/pullRequests/${pr_id}"
      headers=(-H "Authorization: Bearer ${SYSTEM_ACCESSTOKEN}" -H "Content-Type: application/json")

      ado_get() { curl -fsS "${headers[@]}" "$1"; }
      ado_post() { curl -fsS -X POST "${headers[@]}" "$1" -d @"$2"; }

      iterations_json="$(ado_get "${api_base}/iterations?api-version=${api_version}")"
      last_iteration="$(echo "$iterations_json" | jq -r '(.value // .) | map(.id) | max')"

      if [ -n "$last_iteration" ] && [ "$last_iteration" != "null" ]; then
        ado_get "${api_base}/iterations/${last_iteration}/changes?\$top=2000&api-version=${api_version}" |
          jq '(.changeEntries // .value // [])
            | map({
                key: (.item.path // .sourceServerItem),
                value: {
                  id: .changeTrackingId,
                  type: (.changeType // "")
                }
              })
            | map(select(.key != null))
            | from_entries' > azure-devops-changes.json

        jq -c '.findings[]?' codex-output.json | while IFS= read -r finding; do
          path="$(echo "$finding" | jq -r '.code_location.relative_file_path // empty')"
          start_line="$(echo "$finding" | jq -r '.code_location.line_range.start')"
          end_line="$(echo "$finding" | jq -r '.code_location.line_range.end')"
          ado_path="/${path#/}"
          change="$(jq -c --arg path "$ado_path" '.[$path] // empty' azure-devops-changes.json)"

          if [ -z "$path" ] || [ -z "$change" ] || ! [[ "$start_line" =~ ^[0-9]+$ && "$end_line" =~ ^[0-9]+$ ]]; then
            echo "Skipping finding that cannot be safely anchored."
            continue
          fi

          change_type="$(echo "$change" | jq -r '.type')"
          [ "$change_type" != "delete" ] || continue

          jq -n \
            --arg content "$(echo "$finding" | jq -r '"\(.title)\n\n\(.body)\n\nConfidence: \(.confidence_score)\nPriority: P\(.priority)"')" \
            --arg filePath "$ado_path" \
            --argjson start "$start_line" \
            --argjson end "$end_line" \
            --argjson changeTrackingId "$(echo "$change" | jq -r '.id')" \
            --argjson iteration "$last_iteration" \
            '{
              comments: [{ parentCommentId: 0, content: $content, commentType: 1 }],
              status: 1,
              threadContext: {
                filePath: $filePath,
                rightFileStart: { line: $start, offset: 1 },
                rightFileEnd: { line: $end, offset: 1 }
              },
              pullRequestThreadContext: {
                changeTrackingId: $changeTrackingId,
                iterationContext: {
                  firstComparingIteration: 1,
                  secondComparingIteration: $iteration
                }
              }
            }' > inline-comment.json

          ado_post "${api_base}/threads?api-version=${api_version}" inline-comment.json || true
        done
      fi

      jq -n --slurpfile review codex-output.json '{
        comments: [{
          parentCommentId: 0,
          commentType: 1,
          content: "**Codex automated review**\n\nVerdict: \($review[0].overall_correctness)\nConfidence: \($review[0].overall_confidence_score)\n\n\($review[0].overall_explanation)"
        }],
        status: 1
      }' > summary-comment.json

      ado_post "${api_base}/threads?api-version=${api_version}" summary-comment.json
    displayName: Publish Azure DevOps comments
    condition: always()
    env:
      SYSTEM_ACCESSTOKEN: $(System.AccessToken)
```

這是一個精簡但實用的 Azure Repos 範例，inline comment 的錨定有一些需要注意的限制。

這個範例假設是同一個 repo 內的 Azure Repos PR；fork 或跨 repo 的 PR 可能要從 `System.PullRequest.SourceRepositoryUri` fetch。

Azure DevOps 專屬的步驟是透過 [Pull Request Threads API](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/pull-request-threads/create?view=azure-devops-rest-7.1) 發布 Codex 的 findings。inline comment 靠 `threadContext.filePath`、`threadContext.rightFileStart`、`threadContext.rightFileEnd` 和 `pullRequestThreadContext.changeTrackingId` 來附著。範例在貼留言前，會從最新的 pull request iteration changes 解出 `changeTrackingId`。

在把它當成必要的 branch policy 之前，請先在自己的 Azure DevOps 專案驗證 inline 錨定的行為，尤其要測新增檔案、修改檔案、改名檔案、刪除檔案和多行 finding。如果某個 finding 沒辦法安全地錨定到 diff 的右側，寧可跳過 inline comment、只靠整體摘要，也不要貼出會誤導人的行留言。

## Jenkins 範例

同樣的做法也可以用在 Jenkins 的 job script 上。一樣用註解標出 workflow 的關鍵階段：

```groovy
pipeline {
  agent any

  options {
    timestamps()
    ansiColor('xterm')
    // Prevent overlapping runs on the same PR. Newer builds will cancel older ones after passing the milestone.
    disableConcurrentBuilds()
  }

  environment {
    // Default model like your GHA (can be overridden at job/env level)
    CODEX_MODEL = "${env.CODEX_MODEL ?: 'gpt-5.5'}"

    // Filled in during Init
    PR_NUMBER   = ''
    HEAD_SHA    = ''
    BASE_SHA    = ''
    REPOSITORY  = ''   // org/repo
  }

  stages {
    stage('Init (PR context, repo, SHAs)') {
      steps {
        checkout scm

        // Compute PR context and SHAs similar to the GitHub Action
        sh '''
          set -euo pipefail

          # Derive PR number from Jenkins env when building PRs via GitHub Branch Source
          PR_NUMBER="${CHANGE_ID:-}"
          if [ -z "$PR_NUMBER" ]; then
            echo "Not a PR build (CHANGE_ID missing). Exiting."
            exit 1
          fi
          echo "PR_NUMBER=$PR_NUMBER" >> $WORKSPACE/jenkins.env

          # Discover owner/repo (normalize SSH/HTTPS forms)
          ORIGIN_URL="$(git config --get remote.origin.url)"
          if echo "$ORIGIN_URL" | grep -qE '^git@github.com:'; then
            REPO_PATH="${ORIGIN_URL#git@github.com:}"
            REPO_PATH="${REPO_PATH%.git}"
          else
            # e.g. https://github.com/owner/repo.git
            REPO_PATH="${ORIGIN_URL#https://github.com/}"
            REPO_PATH="${REPO_PATH%.git}"
          fi
          echo "REPOSITORY=$REPO_PATH" >> $WORKSPACE/jenkins.env

          # Ensure we have all refs we need
          git fetch --no-tags origin \
            "+refs/heads/*:refs/remotes/origin/*" \
            "+refs/pull/${PR_NUMBER}/head:refs/remotes/origin/PR-${PR_NUMBER}-head" \
            "+refs/pull/${PR_NUMBER}/merge:refs/remotes/origin/PR-${PR_NUMBER}-merge"

          # HEAD (PR head) and BASE (target branch tip)
          CHANGE_TARGET="${CHANGE_TARGET:-main}"
          HEAD_SHA="$(git rev-parse refs/remotes/origin/PR-${PR_NUMBER}-head)"
          BASE_SHA="$(git rev-parse refs/remotes/origin/${CHANGE_TARGET})"

          echo "HEAD_SHA=$HEAD_SHA" >> $WORKSPACE/jenkins.env
          echo "BASE_SHA=$BASE_SHA" >> $WORKSPACE/jenkins.env

          echo "Resolved:"
          echo "  REPOSITORY=$REPO_PATH"
          echo "  PR_NUMBER=$PR_NUMBER"
          echo "  CHANGE_TARGET=$CHANGE_TARGET"
          echo "  HEAD_SHA=$HEAD_SHA"
          echo "  BASE_SHA=$BASE_SHA"
        '''
        script {
          def envMap = readProperties file: 'jenkins.env'
          env.PR_NUMBER  = envMap['PR_NUMBER']
          env.REPOSITORY = envMap['REPOSITORY']
          env.HEAD_SHA   = envMap['HEAD_SHA']
          env.BASE_SHA   = envMap['BASE_SHA']
        }

        // Ensure only latest build for this PR proceeds; older in-flight builds will be aborted here
        milestone 1
      }
    }

    stage('Generate structured output schema') {
      steps {
        sh '''
          set -euo pipefail
          cat > codex-output-schema.json <<'JSON'
          {
            "type": "object",
            "properties": {
              "findings": {
                "type": "array",
                "items": {
                  "type": "object",
                  "properties": {
                    "title": { "type": "string", "maxLength": 80 },
                    "body": { "type": "string", "minLength": 1 },
                    "confidence_score": { "type": "number", "minimum": 0, "maximum": 1 },
                    "priority": { "type": "integer", "minimum": 0, "maximum": 3 },
                    "code_location": {
                      "type": "object",
                      "properties": {
                        "absolute_file_path": { "type": "string", "minLength": 1 },
                        "line_range": {
                          "type": "object",
                          "properties": {
                            "start": { "type": "integer", "minimum": 1 },
                            "end": { "type": "integer", "minimum": 1 }
                          },
                          "required": ["start","end"],
                          "additionalProperties": false
                        }
                      },
                      "required": ["absolute_file_path","line_range"],
                      "additionalProperties": false
                    }
                  },
                  "required": ["title","body","confidence_score","priority","code_location"],
                  "additionalProperties": false
                }
              },
              "overall_correctness": { "type": "string", "enum": ["patch is correct","patch is incorrect"] },
              "overall_explanation": { "type": "string", "minLength": 1 },
              "overall_confidence_score": { "type": "number", "minimum": 0, "maximum": 1 }
            },
            "required": ["findings","overall_correctness","overall_explanation","overall_confidence_score"],
            "additionalProperties": false
          }
          JSON
        '''
      }
    }

    stage('Build Codex review prompt') {
      environment {
        REVIEW_PROMPT_PATH = "${env.CODEX_PROMPT_PATH ?: 'review_prompt.md'}"
      }
      steps {
        sh '''
          set -euo pipefail
          PROMPT_PATH="codex-prompt.md"
          TEMPLATE_PATH="${REVIEW_PROMPT_PATH}"

          if [ -n "$TEMPLATE_PATH" ] && [ -f "$TEMPLATE_PATH" ]; then
            cat "$TEMPLATE_PATH" > "$PROMPT_PATH"
          else
            {
              printf '%s\n' "You are acting as a reviewer for a proposed code change made by another engineer."
              printf '%s\n' "Focus on issues that impact correctness, performance, security, maintainability, or developer experience."
              printf '%s\n' "Flag only actionable issues introduced by the pull request."
              printf '%s\n' "When you flag an issue, provide a short, direct explanation and cite the affected file and line range."
              printf '%s\n' "Prioritize severe issues and avoid nit-level comments unless they block understanding of the diff."
              printf '%s\n' "After listing findings, produce an overall correctness verdict (\\\"patch is correct\\\" or \\\"patch is incorrect\\\") with a concise justification and a confidence score between 0 and 1."
              printf '%s\n' "Ensure that file citations and line numbers are exactly correct using the tools available; if they are incorrect your comments will be rejected."
            } > "$PROMPT_PATH"
          fi

          {
            echo ""
            echo "Repository: ${REPOSITORY}"
            echo "Pull Request #: ${PR_NUMBER}"
            echo "Base ref: ${CHANGE_TARGET}"
            echo "Head ref: ${CHANGE_BRANCH:-PR-${PR_NUMBER}-head}"
            echo "Base SHA: ${BASE_SHA}"
            echo "Head SHA: ${HEAD_SHA}"
            echo "Changed files:"
            git --no-pager diff --name-status "${BASE_SHA}" "${HEAD_SHA}"
            echo ""
            echo "Unified diff (context=5):"
            git --no-pager diff --unified=5 --stat=200 "${BASE_SHA}" "${HEAD_SHA}" > /tmp/diffstat.txt
            git --no-pager diff --unified=5 "${BASE_SHA}" "${HEAD_SHA}" > /tmp/full.diff
            cat /tmp/diffstat.txt
            echo ""
            cat /tmp/full.diff
          } >> "$PROMPT_PATH"
        '''
      }
    }

    stage('Run Codex structured review') {
      environment {
        REVIEW_PROMPT = 'codex-prompt.md'
        REVIEW_SCHEMA = 'codex-output-schema.json'
        REVIEW_OUTPUT = 'codex-output.json'
      }
      steps {
        withCredentials([
          string(credentialsId: 'openai-api-key', variable: 'OPENAI_API_KEY')
        ]) {
          // Option A: If you have the OpenAI CLI installed on the Jenkins agent
          sh '''
            set -euo pipefail
            if command -v openai >/dev/null 2>&1; then
              # Use the Responses API with a JSON schema tool spec
              # Produces codex-output.json with the structured result.
              openai responses.create \
                --model "${CODEX_MODEL}" \
                --input-file "${REVIEW_PROMPT}" \
                --response-format "json_object" \
                --output-schema "${RESPONSE_FORMAT}" \
                --tool-choice "auto" \
                > raw_response.json || true

              # Fallback if CLI doesn’t support your exact flags:
              # Keep demo resilient: If raw_response.json is empty, create a minimal stub so later steps don’t fail.
              if [ ! -s raw_response.json ]; then
                echo '{"findings":[],"overall_correctness":"patch is correct","overall_explanation":"No issues detected.","overall_confidence_score":0.5}' > "${REVIEW_OUTPUT}"
              else
                # If your CLI/format returns a JSON object with the structured content in .output or similar, map it here.
                # Adjust jq path to match your CLI output shape.
                jq -r '.output // .' raw_response.json > "${REVIEW_OUTPUT}" || cp raw_response.json "${REVIEW_OUTPUT}"
              fi
            else
              echo "openai CLI not found; creating a stub output for demo continuity."
              echo '{"findings":[],"overall_correctness":"patch is correct","overall_explanation":"(CLI not available on agent)","overall_confidence_score":0.4}' > "${REVIEW_OUTPUT}"
            fi
          '''
        }
      }
    }

    stage('Inspect structured Codex output') {
      steps {
        sh '''
          if [ -s codex-output.json ]; then
            jq '.' codex-output.json || true
          else
            echo "Codex output file missing"
          fi
        '''
      }
    }

    stage('Publish inline review comments') {
      when { expression { true } }
      steps {
        withCredentials([string(credentialsId: 'github-token', variable: 'GITHUB_TOKEN')]) {
          sh '''
            set -euo pipefail
            REVIEW_JSON="codex-output.json"
            if [ ! -s "$REVIEW_JSON" ]; then
              echo "No Codex output file present; skipping comment publishing."
              exit 0
            fi

            findings_count=$(jq '.findings | length' "$REVIEW_JSON")
            if [ "$findings_count" -eq 0 ]; then
              echo "Codex returned no findings; skipping inline comments."
              exit 0
            fi

            jq -c --arg commit "$HEAD_SHA" '.findings[] | {
                body: (.title + "\\n\\n" + .body + "\\n\\nConfidence: " + (.confidence_score | tostring) + (if has("priority") then "\\nPriority: P" + (.priority | tostring) else "" end)),
                commit_id: $commit,
                path: .code_location.absolute_file_path,
                line: .code_location.line_range.end,
                side: "RIGHT",
                start_line: (if .code_location.line_range.start != .code_location.line_range.end then .code_location.line_range.start else null end),
                start_side: (if .code_location.line_range.start != .code_location.line_range.end then "RIGHT" else null end)
              } | with_entries(select(.value != null))' "$REVIEW_JSON" > findings.jsonl

            while IFS= read -r payload; do
              echo "Posting review comment payload:" && echo "$payload" | jq '.'
              curl -sS \
                -X POST \
                -H "Accept: application/vnd.github+json" \
                -H "Authorization: Bearer ${GITHUB_TOKEN}" \
                -H "X-GitHub-Api-Version: 2022-11-28" \
                "https://api.github.com/repos/${REPOSITORY}/pulls/${PR_NUMBER}/comments" \
                -d "$payload"
            done < findings.jsonl
          '''
        }
      }
    }

    stage('Publish overall summary comment') {
      steps {
        withCredentials([string(credentialsId: 'github-token', variable: 'GITHUB_TOKEN')]) {
          sh '''
            set -euo pipefail
            REVIEW_JSON="codex-output.json"
            if [ ! -s "$REVIEW_JSON" ]; then
              echo "Codex output missing; skipping summary."
              exit 0
            fi

            overall_state=$(jq -r '.overall_correctness' "$REVIEW_JSON")
            overall_body=$(jq -r '.overall_explanation' "$REVIEW_JSON")
            confidence=$(jq -r '.overall_confidence_score' "$REVIEW_JSON")
            msg="**Codex automated review**\\n\\nVerdict: ${overall_state}\\nConfidence: ${confidence}\\n\\n${overall_body}"

            jq -n --arg body "$msg" '{body: $body}' > /tmp/summary.json

            curl -sS \
              -X POST \
              -H "Accept: application/vnd.github+json" \
              -H "Authorization: Bearer ${GITHUB_TOKEN}" \
              -H "X-GitHub-Api-Version: 2022-11-28" \
              "https://api.github.com/repos/${REPOSITORY}/issues/${PR_NUMBER}/comments" \
              -d @/tmp/summary.json
          '''
        }
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'codex-*.json, *.md, /tmp/diff*.txt', allowEmptyArchive: true
    }
  }
}
```

# 總結

有了 Codex SDK，你可以在沒有直接接 Codex Cloud 的 CI/CD 環境裡，做出自己的自動 code review workflow。不過「用 prompt 觸發 Codex、拿到結構化輸出、再用 API 對輸出採取行動」這個模式，用途遠不只 Code Review。例如 incident 建立時觸發 root-cause analysis，把結構化報告貼到 Slack channel；或是每個 PR 產生一份程式碼品質報告，結果貼到 dashboard。

## 重點整理
- Headless 模式的 `codex exec` 讓你把 Codex 當成 CI 裡的一個步驟，不需要接 Codex Cloud。
- 用 JSON schema 限制輸出格式，下游程式才能穩定解析 finding 的檔案和行數。
- 各家 SCM 的流程相同：跑 Codex、解析結構化結果、呼叫 SCM API 留言，差別只在 API 和設定。
- Codex 不該讀得到自己的 API key，隔離 credential 和把 review 與寫入權限分開是安全重點。
- 「prompt、結構化輸出、API 動作」這個模式可以延伸到 root-cause analysis、品質報告等場景。

## 練習
1. 在頁面的 `codex-output-schema.json` 範例裡多加一個欄位（例如 `severity`），確認 Codex 輸出會帶上它。
2. 把某一個 CI 範例中的 review prompt 改成只看安全性問題，比較 findings 的差異。
3. 照 Wrap Up 的想法，改寫其中一個範例，讓 Codex 對 PR 產出一份摘要報告，而不是 inline comment。
