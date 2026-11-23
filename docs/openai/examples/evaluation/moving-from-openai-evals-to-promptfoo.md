---
translated: true
source: examples/evaluation/moving-from-openai-evals-to-promptfoo.md
---

# 從 OpenAI Evals 遷移到 Promptfoo

> 原文：[examples/evaluation/moving-from-openai-evals-to-promptfoo.md](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/moving-from-openai-evals-to-promptfoo.md)

手動在 Promptfoo 重建 OpenAI Evals 的評測，然後執行並驗證。

## 這篇在做什麼

OpenAI 正在逐步結束 Evals 產品，建議改用 Promptfoo。這篇說明兩者的對應關係，並帶你手動把既有的 eval 重建成 `promptfooconfig.yaml`，執行後驗證結果。

## 學完你會

- 把 OpenAI Evals 的測試資料、prompt、模型和 grader 對應到 Promptfoo 的設定
- 用 `promptfoo eval` 跑評測，用 `view` 看結果，設定出錯時先驗證設定檔
- 判斷哪些情況（grader、tool、自訂 provider）需要額外手動設定並驗證

## 開跑前

- 要先[安裝 Promptfoo](https://www.promptfoo.dev/docs/installation/)
- 手上要有一個既有的 OpenAI Evals 評測
- 需要評測所用模型供應商的 API key，例如 `OPENAI_API_KEY`


OpenAI 正在逐步結束 Evals 產品，並建議用 [Promptfoo](https://www.promptfoo.dev/) 繼續並延伸你的評測 workflow。

Promptfoo 是開源的 CLI 與函式庫，用來評測和 red-team AI 應用與 agent。它讓你在本機或 CI 裡跑、維護和擴充 eval 時更有彈性。

## 遷移到 Promptfoo 後有什麼不同

OpenAI Evals 和 Promptfoo 有相同的核心元件：測試資料、prompt、provider/模型，以及評分輸出的標準。在 Promptfoo 重建評測時，要把這些元件對應成可攜的設定，才能繼續測試同樣的行為。

主要差別在 workflow。OpenAI Evals 在 OpenAI Platform 上管理，評測、run、結果和相關的資料集流程都在 dashboard 裡。Promptfoo 則以可攜的設定檔和 CLI workflow 為中心。你可以把評測跟應用程式碼放在一起，在本機或 CI 裡執行，並隨著測試需求演進調整。

| OpenAI Evals | Promptfoo |
| --- | --- |
| Evaluations and results are managed in the OpenAI Platform dashboard. | Evaluations are defined in a config file and run with the CLI or in CI. |
| Graders are configured as testing criteria in an eval. | Grading behavior is configured as assertions and metrics. |
| Runs are tied to the Platform evaluation workflow. | Runs can be integrated into development, testing, and deployment workflows. |
| Platform features such as dataset review and prompt iteration remain in OpenAI. | Provider selection and evaluation customization are managed in Promptfoo. |

Promptfoo 不是把 OpenAI Evals 的介面原樣搬到另一個工具，而是提供更可攜、偏程式碼導向的 workflow，方便長期維護、執行和擴充評測。

## 把評測遷移到 Promptfoo

這份指南說明如何手動在 Promptfoo 重建評測，不需要 OpenAI Evals 的匯出功能。

### 開始之前

- [安裝 Promptfoo](https://www.promptfoo.dev/docs/installation/)。
- 一個既有的 OpenAI Evals 評測。
- 你的 eval 所用模型供應商的 API key，例如 `OPENAI_API_KEY`。

### 建立 Promptfoo 設定

把評測的 prompt、provider、測試案例和 assertion 重建到 `promptfooconfig.yaml` 檔案裡。設定格式請看 [Configure evaluations in Promptfoo](https://www.promptfoo.dev/docs/configuration/guide/)。

### 在 Promptfoo 執行手動重建的評測

執行一次全新的評測，並開啟結果檢視器：

```bash
promptfoo eval -c promptfooconfig.yaml --no-cache
promptfoo view
```

`eval` 會建立新的 Promptfoo 評測 run，`view` 則在本機開啟它的結果。這個新的 run 和之前完成的 OpenAI Evals run 是分開的。

如果你修改了設定或遇到設定錯誤，重試前先驗證設定：

```bash
promptfoo validate config -c promptfooconfig.yaml
```

![Promptfoo results view after running the recreated evaluation](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/promptfoo-custom-example-view.png)

### 驗證遷移後的評測

第一次跑完 Promptfoo 後，檢視結果，確認評測的行為符合預期。在把這個 eval 放進長期 workflow 之前，先比對重建後的 prompt、assertion 和輸出。

以相似度為基礎的評分，在不同系統間可能不會產生完全相同的數值。任何手動重建的 grader，尤其是 LLM-as-a-judge 這類，在你依賴它做 regression 判斷之前都應該先驗證。

### 需要手動設定的情況

有些評測可能需要在 Promptfoo 做額外設定。

| 情況 | 該怎麼做 |
| --- | --- |
| 需要重建 grader。 | 把它重建成 Promptfoo assertion，並在依賴它之前驗證行為。 |
| 你的 Promptfoo 設定裡沒有 tool、agent 或自訂 provider 的 workflow。 | 在 Promptfoo 設定該 workflow，並在使用遷移後的 eval 之前先測試。 |

### 在 Promptfoo 客製你的 workflow

遷移後的評測運作符合預期後，你可以用 Promptfoo 擴大測試涵蓋範圍、在 CI 裡跑 eval，並加入 red-team 測試。

如果你用 Codex，請看 [Add evals to your AI application](https://github.com/openai/openai-cookbook/blob/main/codex/use-cases/ai-app-evals)，用 Promptfoo Codex 外掛來建立並維護 Promptfoo eval 套件。

### 下一步

- [Install Promptfoo](https://www.promptfoo.dev/docs/installation/)
- [Configure evaluations in Promptfoo](https://www.promptfoo.dev/docs/configuration/guide/)
- [Configure assertions and expected outputs](https://www.promptfoo.dev/docs/configuration/expected-outputs/)
- [Run Promptfoo in CI/CD](https://www.promptfoo.dev/docs/integrations/ci-cd/)

## 重點整理

- 兩邊的核心元件相同：測試資料、prompt、provider 和評分標準，遷移就是把它們對應到設定檔。
- Promptfoo 以設定檔加 CLI 為中心，可以跟程式碼放一起，也能跑在 CI。
- OpenAI Evals 的 grader 對應到 Promptfoo 的 assertion 和 metric。
- 遷移是重建而不是匯入，結果要自己驗證，LLM-as-a-judge 的 grader 尤其要小心。
- 驗證沒問題後，再擴充測試涵蓋、接 CI 或加 red-team。

## 練習

1. 建一個最小的 `promptfooconfig.yaml`，一個 prompt、一個 provider、兩個測試案例，跑 `promptfoo eval` 再用 `view` 看結果。
2. 替測試案例加一個 assertion（例如輸出必須包含某個字串），故意讓一個案例失敗，看結果頁怎麼呈現。
3. 把原本 OpenAI Evals 裡的一個 LLM grader 改寫成 Promptfoo 的 LLM-as-a-judge assertion，再用已知答案的案例驗證它的評分合不合理。
