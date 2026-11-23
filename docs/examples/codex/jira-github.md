---
translated: true
source: examples/codex/jira-github.ipynb
---

# 用 Codex 自動化 Jira ↔ GitHub

> 原文：[examples/codex/jira-github.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/codex/jira-github.ipynb)



## 這篇在做什麼
在 Jira issue 上貼一個標籤，就會自動觸發 GitHub Action，由 `codex-cli` 實作需求、開出 pull request，再把 Jira 的狀態和留言更新回去。整個流程不用人手介入。

## 學完你會
- 建一條 Jira Automation rule，在標籤出現時呼叫 GitHub 的 `workflow_dispatch`。
- 寫一個在 GitHub Action 裡非互動式跑 `codex-cli` 的 workflow，並自動開 PR。
- 讓 workflow 用 Jira REST API 把 ticket 轉到 In Review 並留下 PR 連結。

## 開跑前
- Jira 專案管理員權限，且能建立 automation rule。
- GitHub 要有寫入權限、能新增 repository secrets，而且 `main` 是受保護分支。
- 需要 OpenAI API key 和 Jira API token（見下方 Prerequisites 的 secrets）。

## 這份教學的目的

這份教學一步一步帶你把 Jira 和 GitHub 之間的流程自動化。你在 Jira issue 上貼標籤，就會觸發一整套流程：建立 **GitHub pull request**、同步更新兩邊的系統、讓 code review 更順，全程幾乎不用人工操作。自動化的核心是跑在 GitHub Action 裡的 [`codex-cli`](https://github.com/openai/openai-codex) agent。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/codex_action.png" alt="Full data-flow diagram" width="500"/>


流程如下：

1. 在 Jira issue 上貼標籤
2. Jira Automation 呼叫 GitHub Action
3. Action 啟動 `codex-cli` 去實作修改
4. 開出 PR
5. Jira 狀態轉換並加註，形成零點擊的循環。包括改 ticket 狀態、貼上 PR 連結，以及在 ticket 留言回報進度。

## 前置條件

* Jira：專案管理員權限，且能建立 automation rule  
* GitHub：寫入權限、能新增 repository secrets，而且 `main` 是受保護分支  
* API key 和 secrets 要放在 repository secrets：
  * `OPENAI_API_KEY`：給 `codex-cli` 用的 OpenAI key  
  * `JIRA_BASE_URL`、`JIRA_EMAIL`、`JIRA_API_TOKEN`：給 action 呼叫 REST API 用  
* 本機要裝 `codex-cli`（`pnpm add -g @openai/codex`），方便臨時測試  
* 有一個含 `.github/workflows/` 資料夾的 repository


## 建立 Jira Automation Rule

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jira_rule.png" alt="Automation Rule" width="500"/>

這條 rule 的第一步是監聽 issue 標籤的變動，這樣只有標籤被新增或修改時才會觸發，不用處理 issue 的每一次更新。

接著檢查更新後的標籤是否包含特定關鍵字，我們的例子用 `aswe`。它是一個過濾條件，只有明確貼了標籤的 issue 才會繼續，避免不相關的更新造成雜訊。

條件成立後，我們對 GitHub 的 `workflow_dispatch` 端點送一個 `POST` request，帶著 issue 的相關資訊啟動 GitHub Actions workflow。傳進去的有 issue key、summary，以及整理過的 description（把引號和換行跳脫掉，這樣 payload 在 YAML/JSON 裡才解析得動）。Jira 還有[更多欄位](https://support.atlassian.com/cloud-automation/docs/jira-smart-values-issues/)可以當變數用，讓 codex agent 執行時拿到更多脈絡。

這樣的設計讓團隊能精準控制哪些 Jira issue 會觸發自動化，也讓 GitHub 收到結構乾淨的 metadata。你也可以設多個標籤，各自觸發不同的 GitHub Action，例如一個標籤跑快速修 bug 的流程，另一個標籤開始做重構或產生 API stub。


## 加入 GitHub Action

GitHub Actions 讓你用 YAML 檔定義 repository 裡的 workflow，裡面描述一連串 job 和 step。不管是手動觸發還是透過 POST request 觸發，GitHub 都會自動準備環境並執行 workflow。

要處理 Jira 送來的 `POST` request，我們在 repository 的 `.github/workflows/` 目錄建一個 GitHub Action，YAML 如下：


```yaml
name: Codex Automated PR
on:
  workflow_dispatch:
    inputs:
      issue_key:
        description: 'JIRA issue key (e.g., PROJ-123)'
        required: true
      issue_summary:
        description: 'Brief summary of the issue'
        required: true
      issue_description:
        description: 'Detailed issue description'
        required: true

permissions:
  contents: write           # allow the action to push code & open the PR
  pull-requests: write      # allow the action to create and update PRs

jobs:
  codex_auto_pr:
    runs-on: ubuntu-latest

    steps:
    # 0 – Checkout repository
    - uses: actions/checkout@v4
      with:
        fetch-depth: 0       # full history → lets Codex run tests / git blame if needed

    # 1 – Set up Node.js and Codex
    - uses: actions/setup-node@v4
      with:
        node-version: 22
    - run: pnpm add -g @openai/codex

    # 2 – Export / clean inputs (available via $GITHUB_ENV)
    - id: vars
      run: |
        echo "ISSUE_KEY=${{ github.event.inputs.issue_key }}"        >> $GITHUB_ENV
        echo "TITLE=${{ github.event.inputs.issue_summary }}"        >> $GITHUB_ENV
        echo "RAW_DESC=${{ github.event.inputs.issue_description }}" >> $GITHUB_ENV
        DESC_CLEANED=$(echo "${{ github.event.inputs.issue_description }}" | tr '\n' ' ' | sed 's/"/'\''/g')
        echo "DESC=$DESC_CLEANED"                                    >> $GITHUB_ENV
        echo "BRANCH=codex/${{ github.event.inputs.issue_key }}"     >> $GITHUB_ENV

    # 3 – Transition Jira issue to "In Progress"
    - name: Jira – Transition to In Progress
      env:
        ISSUE_KEY:      ${{ env.ISSUE_KEY }}
        JIRA_BASE_URL:  ${{ secrets.JIRA_BASE_URL }}
        JIRA_EMAIL:     ${{ secrets.JIRA_EMAIL }}
        JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
      run: |
        curl -sS -X POST \
          --url   "$JIRA_BASE_URL/rest/api/3/issue/$ISSUE_KEY/transitions" \
          --user  "$JIRA_EMAIL:$JIRA_API_TOKEN" \
          --header 'Content-Type: application/json' \
          --data  '{"transition":{"id":"21"}}'
          # 21 is the transition ID for changing the ticket status to In Progress. Learn more here: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-get

    # 4 – Set Git author for CI commits
    - run: |
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git config user.name  "github-actions[bot]"

    # 5 – Let Codex implement & commit (no push yet)
    - name: Codex implement & commit
      env:
        CODEX_API_KEY:  ${{ secrets.OPENAI_API_KEY }}
      run: |
        set -e
        codex exec --sandbox workspace-write \
              "Implement JIRA ticket $ISSUE_KEY: $TITLE. $DESC"

        git add -A
        git commit -m "feat($ISSUE_KEY): $TITLE"

    # 6 – Open (and push) the PR in one go
    - id: cpr
      uses: peter-evans/create-pull-request@v6
      with:
        token:  ${{ secrets.GITHUB_TOKEN }}
        base:   main
        branch: ${{ env.BRANCH }}
        title:  "${{ env.TITLE }} (${{ env.ISSUE_KEY }})"
        body: |
          Auto-generated by Codex for JIRA **${{ env.ISSUE_KEY }}**.
          ---
          ${{ env.DESC }}

    # 7 – Transition Jira to "In Review" & drop the PR link
    - name: Jira – Transition to In Review & Comment PR link
      env:
        ISSUE_KEY:      ${{ env.ISSUE_KEY }}
        JIRA_BASE_URL:  ${{ secrets.JIRA_BASE_URL }}
        JIRA_EMAIL:     ${{ secrets.JIRA_EMAIL }}
        JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        PR_URL:         ${{ steps.cpr.outputs.pull-request-url }}
      run: |
        # Status transition
        curl -sS -X POST \
          --url   "$JIRA_BASE_URL/rest/api/3/issue/$ISSUE_KEY/transitions" \
          --user  "$JIRA_EMAIL:$JIRA_API_TOKEN" \
          --header 'Content-Type: application/json' \
          --data  '{"transition":{"id":"31"}}'
          # 31 is the Transition ID for changing the ticket status to In Review. Learn more here: https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/#api-rest-api-3-issue-issueidorkey-transitions-get

        # Comment with PR link
        curl -sS -X POST \
          --url   "$JIRA_BASE_URL/rest/api/3/issue/$ISSUE_KEY/comment" \
          --user  "$JIRA_EMAIL:$JIRA_API_TOKEN" \
          --header 'Content-Type: application/json' \
          --data  "{\"body\":{\"type\":\"doc\",\"version\":1,\"content\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"PR created: $PR_URL\"}]}]}}"
```


## Workflow 的關鍵步驟

1. **Codex 實作與 commit**（Step 5）
   - 用 OpenAI API 實作 JIRA ticket 的需求
   - 以非互動模式執行 Codex CLI，並給予 workspace 寫入權限
   - 用統一格式的 commit message 提交所有修改

2. **建立 Pull Request**（Step 6） 
   - 使用 peter-evans/create-pull-request action
   - 對 main 分支建立 PR
   - 用 JIRA ticket 的資訊設定 PR 標題和說明
   - 回傳 PR URL 供後面使用

3. **更新 JIRA**（Step 7）
   - 透過 JIRA API 把 ticket 轉到 "In Review" 狀態
   - 在 JIRA ticket 上留言貼 PR URL
   - 用 curl 指令呼叫 JIRA REST API


## 幫 Issue 貼標籤

在任何 bug 或 feature ticket 上貼特殊的 `aswe` 標籤：

1. **建立時**：在按 *Create* 之前，先在 "Labels" 欄位加上  
2. **已存在的 issue**：滑到標籤區 → 點鉛筆圖示 → 輸入 `aswe`

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/add_label.png" alt="Adding a label" width="500"/>


## 端到端流程

1. Jira 加上標籤 → Automation 觸發
2. `workflow_dispatch` 送出，action 在 GitHub 上啟動
3. `codex-cli` 修改程式碼並 commit
4. 在產生的分支上開 PR
5. Jira 移到 **In Review**，並留言貼上 PR URL
6. Reviewer 依你原本的 branch protection 設定收到通知

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jira_comment.png" alt="Jira comment with PR link" width="300"/>
<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jira_status_change.png" alt="Jira status transition to In Review" width="300"/>


## Review 並 Merge PR

打開 JIRA ticket 上的 PR 連結，確認沒問題就可以 merge。如果有開 branch protection 和 Smart Commits 整合，PR merge 後 Jira ticket 會自動關閉。

## 結論

這套自動化把 Jira 和 GitHub 無縫串起來，讓開發流程更順：

* **自動追蹤狀態**：ticket 不用手動更新就會依流程前進
* **更好的開發體驗**：把心力放在 review 程式品質，不用寫樣板程式碼
* **減少交接摩擦**：ticket 一貼標籤，PR 就準備好等 review

`codex-cli` 是一個能自動處理重複性程式工作的 AI coding 助手，更多資訊可以看[這裡](https://github.com/openai/codex/)


## 重點整理
- 整個自動化是一條鏈：Jira 標籤 → Jira Automation → `workflow_dispatch` → `codex-cli` → PR → 回寫 Jira。
- 用特定標籤（如 `aswe`）當過濾條件，可以精準控制哪些 issue 會被自動處理，也能用不同標籤對應不同 workflow。
- 傳給 workflow 的 description 要先跳脫引號和換行，不然 YAML/JSON 會解析失敗。
- Secrets 都放 repository secrets，不要寫進 workflow 檔。
- 最終還是由人 review PR 再 merge，自動化只負責產出初版。

## 練習
1. 在 Jira rule 裡多傳一個欄位（例如 issue 的 priority）給 workflow，並在 workflow 的 prompt 裡用到它。
2. 新增第二個標籤（例如 `refactor`），對應一份只做重構、prompt 不同的 workflow 檔。
3. 修改 Step 7，讓 Jira 留言除了 PR URL 外，再附上 Codex 這次修改的檔案清單。
