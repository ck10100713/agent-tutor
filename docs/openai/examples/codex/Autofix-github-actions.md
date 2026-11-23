---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/codex/Autofix-github-actions.ipynb
---

# 用 Codex CLI 自動修復 CI 失敗

> 原文：[examples/codex/Autofix-github-actions.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/codex/Autofix-github-actions.ipynb)



## 這篇在做什麼
示範把 Codex CLI 放進 CI/CD，當 GitHub Actions 的 build 或測試失敗時，自動讓 Codex 產生修正並開 PR。範例是一個 Node 專案。

## 學完你會
- 寫一個在 CI 失敗後觸發的 GitHub Actions workflow，安裝 Codex 並用 `codex exec` 修程式
- 讓 workflow 自動在 `codex/auto-fix` 分支開 PR 供人 review
- 理解這個範例的安全疑慮，以及為什麼要改用最新的官方做法

## 開跑前
- 一個有 Actions workflow 的 GitHub repo
- 在 GitHub 的 repo 或 org 層級設定 `OPENAI_API_KEY` secret
- 在 repo 與 organization 設定中允許 Actions 建立 PR
- 本機環境需要 python（`codex login` 需要）

> **這是封存的範例，請改看最新的 CI 做法。** 下面的 workflow 會把 API key 暴露給整個 job，並且把由 repository 控制的執行內容跟 repository 寫入權限放在一起。請不要照抄那樣的憑證與權限配置。請使用[最新的 autofix workflow](https://learn.chatgpt.com/docs/non-interactive-mode#example-autofix-ci-failures-in-github-actions)，它把產生 patch 和發布 pull request 分開；也請參考 [Codex GitHub Action 安全檢查清單](https://learn.chatgpt.com/docs/github-action#security-checklist)。

## 這份 cookbook 的目的

這份 cookbook 說明如何把 OpenAI Codex CLI 嵌入你的 CI/CD pipeline，這樣當 build 或測試失敗時，codex 會自動產生並提出修正。下面是一個 Node 專案的例子，CI 跑在 GitHub Actions 上。 

## 端到端流程

下面是我們要實作的 pipeline 流程：


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/ci-codex-workflow.png"  width="700"/>

## 前置條件

- 一個有 Actions workflow 的 GitHub Repo

- 你需要在 GitHub 設定中，把 `OPENAI_API_KEY` 建立成環境變數，位置在 https://github.com/{org-name}/{repo-name}/settings/secrets/actions。你也可以設在 org 層級（讓多個 repo 共用 secret） 

- Codex 需要 python 才能使用 `codex login`

- 你需要確認設定已啟用 Actions 在你的 repo 建立 PR，organization 也要設定：


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/github-pr-settings.png" width="700"/>



## 步驟 1：把 GitHub Action 加到你的 CI Pipeline

下面的 YAML 是一個 GitHub action，會在 CI 失敗時自動觸發、安裝 Codex、使用 codex exec，然後在失敗的分支上開一個帶有修正的 PR。請把 "CI" 換成你想監控的 workflow 名稱。 

```yaml
name: Codex Auto-Fix on Failure

on:
  workflow_run:
    # Trigger this job after any run of the primary CI workflow completes
    workflows: ["CI"]
    types: [completed]

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-fix:
    # Only run when the referenced workflow concluded with a failure
    if: ${{ github.event.workflow_run.conclusion == 'failure' }}
    runs-on: ubuntu-latest
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      FAILED_WORKFLOW_NAME: ${{ github.event.workflow_run.name }}
      FAILED_RUN_URL: ${{ github.event.workflow_run.html_url }}
      FAILED_HEAD_BRANCH: ${{ github.event.workflow_run.head_branch }}
      FAILED_HEAD_SHA: ${{ github.event.workflow_run.head_sha }}
    steps:
      - name: Check OpenAI API Key Set
        run: |
          if [ -z "$OPENAI_API_KEY" ]; then
            echo "OPENAI_API_KEY secret is not set. Skipping auto-fix." >&2
            exit 1
          fi
      - name: Checkout Failing Ref
        uses: actions/checkout@v4
        with:
          ref: ${{ env.FAILED_HEAD_SHA }}
          fetch-depth: 0

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: |
          if [ -f package-lock.json ]; then npm ci; else npm i; fi
      - name: Run Codex
        uses: openai/codex-action@main
        id: codex
        with:
          openai_api_key: ${{ secrets.OPENAI_API_KEY }}
          prompt: "You are working in a Node.js monorepo with Jest tests and GitHub Actions. Read the repository, run the test suite, identify the minimal change needed to make all tests pass, implement only that change, and stop. Do not refactor unrelated code or files. Keep changes small and surgical."
          codex_args: '["--config","sandbox_mode=\"workspace-write\""]'

      - name: Verify tests
        run: npm test --silent

      - name: Create pull request with fixes
        if: success()
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "fix(ci): auto-fix failing tests via Codex"
          branch: codex/auto-fix-${{ github.event.workflow_run.run_id }}
          base: ${{ env.FAILED_HEAD_BRANCH }}
          title: "Auto-fix failing CI via Codex"
          body: |
            Codex automatically generated this PR in response to a CI failure on workflow `${{ env.FAILED_WORKFLOW_NAME }}`.
            Failed run: ${{ env.FAILED_RUN_URL }}
            Head branch: `${{ env.FAILED_HEAD_BRANCH }}`
            This PR contains minimal changes intended solely to make the CI pass.
```


## 步驟 2：Actions workflow 被觸發

你可以到 Repo 下的 Actions 分頁，查看 Actions workflow 中失敗的 job。 

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/failing-workflow.png" width="700"/>


失敗的 workflow 完成後，Codex workflow 就會被觸發。 


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/codex-workflow.png" width="700"/>



## 步驟 3：確認 Codex 建立了供 review 的 PR
Codex workflow 執行完成後，它應該會從 feature 分支 codex/auto-fix 開一個 pull request。檢查一切是否正常，然後合併。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/codex-pr.png" width="700"/>



## 結論

這個自動化把 OpenAI Codex CLI 和 GitHub Actions 順暢地整合起來，自動為失敗的 CI 提出修正。

善用 Codex，你可以減少人工介入、加快 code review，並讓 main 分支保持健康。這個 workflow 能讓測試失敗被快速有效地處理，讓開發者專心做更有價值的事。更多 codex-cli 的功能請看[這裡](https://github.com/openai/codex/)。

## 重點整理
- 把 Codex 掛在 CI 失敗事件上，就能自動產生修正並以 PR 交給人審核。
- 修正一律走 PR，由人把關後再合併，不要讓 AI 直接改 main。
- 這個範例的權限配置有風險：API key 暴露給整個 job，又有 repo 寫入權限。
- 正式使用請把「產生 patch」與「發布 PR」拆開，最小化各階段的權限。

## 練習
1. 把 workflow 監控的名稱 "CI" 換成你自己專案的 workflow 名稱。
2. 修改 workflow，讓 PR 分支名稱帶上觸發失敗的 run id，避免多次失敗時互相覆蓋。
3. 參考官方最新的 autofix workflow，把這個範例拆成兩個 job：一個只負責產生 patch（不給 API key 以外的寫入權限），另一個負責開 PR。
