---
translated: true
source: examples/third_party/Code_quality_and_security_scan_with_GitHub_Actions.md
---

# 用 reasoning model 檢查 GitHub PR 的程式碼品質與安全性

> 原文：[examples/third_party/Code_quality_and_security_scan_with_GitHub_Actions.md](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/Code_quality_and_security_scan_with_GitHub_Actions.md)



## 這篇在做什麼
把 OpenAI 的 reasoning model 接進 GitHub Actions，每次開 PR 就自動 review 程式碼的品質、安全性和公司規範。結果會直接以留言的方式貼回 PR。

## 學完你會
- 寫出一個在 PR 觸發、抓出變更 diff 並丟給 OpenAI 分析的 GitHub Actions workflow
- 用 repository variable（PROMPT、MODELNAME、BEST_PRACTICES）調整 prompt、模型和團隊規範
- 讓第二個 job 產出一張 markdown 表格，總結 PR 符合規範的程度

## 開跑前
- 一把 OpenAI API key，存在 GitHub repository secrets，名稱為 `OPENAI_API_KEY`
- 該 repo 已啟用 GitHub Actions，而且你有權限設定 secrets 和 variables

## 簡介
這份教學說明怎麼把 OpenAI reasoning model 接進 GitHub Pull Request (PR) 流程，自動 review 程式碼品質、安全性和企業規範是否符合。越早在開發流程中拿到 AI 的意見，就越早抓到問題，也少花人工，整個 codebase 的 best practice 也比較一致。

## 為什麼要在 PR 裡接 reasoning model？
• 自動抓 code smell、安全漏洞和風格不一致，省下 code review 的時間。  
• 在整個組織落實 coding 標準，讓程式碼品質穩定。  
• 讓開發者很快拿到 AI 給的改進建議。

## 使用情境
• reviewer 想在合併前，先知道這次變更的安全性如何。  
• 團隊想落實統一的 coding 規範，讓全組織的程式碼品質一致。

## 前置準備

### 1. 產生 OpenAI 的「Project Key」
1. 到 platform.openai.com/api-keys 建立一把新的 secret key。  
2. 把這個 token 安全地存進 GitHub repository secrets，名稱用 OPENAI_API_KEY。

### 2. 選 OpenAI 模型
用 [OpenAI Reasoning Models](https://platform.openai.com/docs/guides/reasoning) 深入分析程式碼變更。建議從最強的模型開始，再慢慢調 prompt。

### 3. 選一個 Pull Request
1. 確認你的 repository 已啟用 GitHub Actions。  
2. 確認你有權限設定 repository secrets 或 variables（例如 PROMPT、MODELNAME、BEST_PRACTICES 這幾個變數）。

### 4. 定義企業 coding 標準
把標準存成 repository variable（BEST_PRACTICES），內容可以包含：  
• 程式風格與格式  
• 可讀性與可維護性  
• 安全與合規  
• 錯誤處理與 logging  
• 效能與擴充性  
• 測試與 QA  
• 文件與版本控制  
• 無障礙與國際化  

### 5. 定義 prompt 內容
寫一個 meta-prompt，引導模型做安全、品質和 best practice 檢查，內容包含：  
1. 程式碼品質與標準  
2. 安全與漏洞分析  
3. 容錯與錯誤處理  
4. 效能與資源管理  
5. 逐步驗證  

可以要求模型逐行 review，並給出明確的建議。

## 建立 GitHub Actions workflow

這個 workflow 會在每個對 main branch 的 pull request 觸發，包含兩個 job。第一個 job 蒐集所有變更檔案的 diff（排除 .json 和 .png），送給 OpenAI 分析，OpenAI 建議的修正會以留言貼在 PR 上。第二個 job 根據你定義的企業標準評估這個 PR，回傳一張 markdown 表格，總結程式碼符合標準的程度。你可以直接改 prompt、模型名稱和 best practices 這些變數來調整 workflow。

```yaml
name: PR Quality and Security Check

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  quality-security-analysis:
    runs-on: ubuntu-latest
    steps:
      - name: Check out code
        uses: actions/checkout@v3
        with:
          fetch-depth: 0  # Ensure full history for proper diff

      - name: Gather Full Code From Changed Files
        run: |
          CHANGED_FILES=$(git diff --name-only origin/main...HEAD)
          echo '{"original files": [' > original_files_temp.json
          for file in $CHANGED_FILES; do
            if [[ $file == *.json ]] || [[ $file == *.png ]]; then
              continue
            fi
            if [ -f "$file" ]; then
              CONTENT=$(jq -Rs . < "$file")
              echo "{\"filename\": \"$file\", \"content\": $CONTENT}," >> original_files_temp.json
            fi
          done
          sed -i '$ s/,$//' original_files_temp.json
          echo "]}" >> original_files_temp.json

      - name: Display Processed Diff (Debug)
        run: cat original_files_temp.json

      - name: Get Diff
        run: |
          git diff origin/main...HEAD \
            | grep '^[+-]' \
            | grep -Ev '^(---|\+\+\+)' > code_changes_only.txt
          jq -Rs '{diff: .}' code_changes_only.txt > diff.json
          if [ -f original_files_temp.json ]; then
            jq -s '.[0] * .[1]' diff.json original_files_temp.json > combined.json
            mv combined.json diff.json

      - name: Display Processed Diff (Debug)
        run: cat diff.json

      - name: Analyze with OpenAI
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          DIFF_CONTENT=$(jq -r '.diff' diff.json)
          ORIGINAL_FILES=$(jq -r '."original files"' diff.json)
          PROMPT="Please review the following code changes for any obvious quality or security issues. Provide a brief report in markdown format:\n\nDIFF:\n${DIFF_CONTENT}\n\nORIGINAL FILES:\n${ORIGINAL_FILES}"
          jq -n --arg prompt "$PROMPT" '{
            "model": "gpt-4",
            "messages": [
              { "role": "system", "content": "You are a code reviewer." },
              { "role": "user", "content": $prompt }
            ]
          }' > request.json
          curl -sS https://api.openai.com/v1/chat/completions \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer ${OPENAI_API_KEY}" \
            -d @request.json > response.json

      - name: Extract Review Message
        id: extract_message
        run: |
          ASSISTANT_MSG=$(jq -r '.choices[0].message.content' response.json)
          {
            echo "message<<EOF"
            echo "$ASSISTANT_MSG"
            echo "EOF"
          } >> $GITHUB_OUTPUT

      - name: Post Comment to PR
        env:
          COMMENT: ${{ steps.extract_message.outputs.message }}
          GH_TOKEN: ${{ github.token }}
        run: |
          gh api \
            repos/${{ github.repository }}/issues/${{ github.event.pull_request.number }}/comments \
            -f body="$COMMENT"
  enterprise-standard-check:
    runs-on: ubuntu-latest
    needs: [quality-security-analysis]

    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          fetch-depth: 0  # ensures we get both PR base and head

      - name: Gather Full Code From Changed Files
        run: |
          # Identify changed files from the base (origin/main) to the pull request HEAD
          CHANGED_FILES=$(git diff --name-only origin/main...HEAD)

          # Build a JSON array containing filenames and their content
          echo '{"original files": [' > original_files_temp.json
          for file in $CHANGED_FILES; do
            # Skip .json and .txt files
            if [[ $file == *.json ]] || [[ $file == *.txt ]]; then
              continue
            fi

            # If the file still exists (i.e., wasn't deleted)
            if [ -f "$file" ]; then
              CONTENT=$(jq -Rs . < "$file")
              echo "{\"filename\": \"$file\", \"content\": $CONTENT}," >> original_files_temp.json
            fi
          done

          # Remove trailing comma on the last file entry and close JSON
          sed -i '$ s/,$//' original_files_temp.json
          echo "]}" >> original_files_temp.json

      - name: Analyze Code Against Best Practices
        id: validate
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          set -e
          # Read captured code
          ORIGINAL_FILES=$(cat original_files_temp.json)

          # Construct the prompt:
          #  - Summarize each best-practice category
          #  - Provide a rating for each category: 'extraordinary', 'acceptable', or 'poor'
          #  - Return a Markdown table titled 'Enterprise Standards'
          PROMPT="You are an Enterprise Code Assistant. Review each code snippet below for its adherence to the following categories: 
          1) Code Style & Formatting
          2) Security & Compliance
          3) Error Handling & Logging
          4) Readability & Maintainability
          5) Performance & Scalability
          6) Testing & Quality Assurance
          7) Documentation & Version Control
          8) Accessibility & Internationalization

          Using \${{ vars.BEST_PRACTICES }} as a reference, assign a rating of 'extraordinary', 'acceptable', or 'poor' for each category. Return a markdown table titled 'Enterprise Standards' with rows for each category and columns for 'Category' and 'Rating'. 

          Here are the changed file contents to analyze:
          $ORIGINAL_FILES"

          # Create JSON request for OpenAI
          jq -n --arg system_content "You are an Enterprise Code Assistant ensuring the code follows best practices." \
                --arg user_content "$PROMPT" \
          '{
            "model": "${{ vars.MODELNAME }}",
            "messages": [
              {
                "role": "system",
                "content": $system_content
              },
              {
                "role": "user",
                "content": $user_content
              }
            ]
          }' > request.json

          # Make the API call
          curl -sS https://api.openai.com/v1/chat/completions \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $OPENAI_API_KEY" \
            -d @request.json > response.json

          # Extract the model's message
          ASSISTANT_MSG=$(jq -r '.choices[0].message.content' response.json)

          # Store for next step
          {
            echo "review<<EOF"
            echo "$ASSISTANT_MSG"
            echo "EOF"
          } >> $GITHUB_OUTPUT

      - name: Post Table Comment
        env:
          COMMENT: ${{ steps.validate.outputs.review }}
          GH_TOKEN: ${{ github.token }}
        run: |
          # If COMMENT is empty or null, skip posting
          if [ -z "$COMMENT" ] || [ "$COMMENT" = "null" ]; then
            echo "No comment to post."
            exit 0
          fi

          gh api \
            repos/${{ github.repository }}/issues/${{ github.event.pull_request.number }}/comments \
            -f body="$COMMENT"
```

## 測試 workflow
把這個 workflow commit 到你的 repository，然後開一個新的 PR。workflow 會自動執行，並把 AI 產生的意見以 PR 留言貼出來。

*公開範例可以看 OpenAI-Forum repository 的 workflow：[pr_quality_and_security_check.yml](https://github.com/alwell-kevin/OpenAI-Forum/blob/main/.github/workflows/pr_quality_and_security_check.yml)。*

![pr_quality_and_security_check.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pr_quality_and_security_check.png)

![workflow_check.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/workflow_check.png)

## 重點整理
- 把 AI review 放在 PR 階段，問題在合併前就能被抓到。
- prompt、模型名稱和團隊規範都放在 repository variable，不用改 workflow 就能調整。
- 兩個 job 分工：一個給逐行修正建議，一個給符合規範程度的總覽表。
- API key 一定放 secrets，不要寫進 workflow 檔。

## 練習
1. 在 workflow 裡把排除的檔案類型再加上 `.md`，讓文件變更不會被送去分析。
2. 修改 BEST_PRACTICES 變數，只留下「安全與合規」和「錯誤處理」兩項，看輸出的表格怎麼變。
3. 在第一個 job 的 prompt 裡要求模型只回報嚴重等級為 high 的問題，並在留言中加上檔名與行號。
