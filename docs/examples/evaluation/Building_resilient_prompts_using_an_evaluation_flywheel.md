---
translated: true
source: examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md
---
# Building resilient prompts using an evaluation flywheel

> 原文：[examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/Building_resilient_prompts_using_an_evaluation_flywheel.md)



## 這篇在做什麼

這篇教你在 OpenAI Platform 上，用「evaluation flywheel」的流程讓 prompt 變得耐用，也就是不管輸入什麼，都能穩定給出高品質回答。範例是一個公寓租賃助理，從標註失敗案例、建立 grader，到用 prompt optimizer 改進 prompt，走完一整圈。

## 學完你會

- 用 open coding 和 axial coding 標註失敗的 trace，整理出失敗類型
- 建立 LLM grader 自動評估格式與正確性，並用 TPR / TNR 檢驗 LLM judge 可不可信
- 用 synthetic data（維度組合加 perturbation）擴充測試資料

## 開跑前

- 需要 OpenAI Platform 帳號（用 Datasets、graders 和 prompt optimizer）

## 總覽

### 這份 cookbook 的目的

這份 cookbook 提供實用指南，教你怎麼用 OpenAI Platform，輕鬆為 prompt 建立耐用性。

> **耐用的 prompt** 指的是在各種可能的輸入下，都能給出高品質回應的 prompt。

Prompt 的耐用性是在 production 部署 AI 應用的關鍵。沒有這個特性，你的 prompt 在邊界案例可能產生意外的結果，在一般案例也可能給出不夠好的回應，削弱 AI 應用的效果。

要為 prompt 建立耐用性，我們建議用 **evaluation flywheel** 流程。這個方法讓開發者能持續、可衡量地改進 AI 應用。

### 目標讀者

這份 cookbook 適合領域專家、solutions architect、data scientist 和 AI 工程師，如果你想改善 prompt 整體的一致性和品質，或處理 AI 應用中特定的邊界案例，這份就是為你寫的。

## Evaluation flywheel

AI 應用常常感覺很脆弱。一個 prompt 某天運作得很好，隔天可能就產生意外且品質低落的結果。這是因為 prompt 對使用者輸入或 context 的小變動可能很敏感。要打造可靠的 AI 產品，我們需要一個系統化的方法讓 prompt 更耐用。

解法是一個持續、反覆的流程，叫做 **evaluation flywheel**。它不再靠猜哪裡能改進 prompt（"prompt-and-pray"），而是提供一套結構化的工程方法來診斷、衡量並解決問題。

這個 flywheel 有三個階段：

1. **Analyze（分析）**：
   透過質性檢視，了解你的系統怎麼失敗、為什麼失敗。手動檢查並標註模型行為不正確的範例，找出反覆出現的失敗模式。

2. **Measure（衡量）**：
   把找到的失敗模式量化並設定 baseline。無法衡量就無法改進。建立測試資料集，並建立自動化的評估器（"graders"），大規模地為系統表現打分數。

3. **Improve（改進）**：
   做有針對性的改進，例如改寫 prompt、加入更好的範例，或調整系統元件。有了衡量機制，你可以立刻看到改動的影響，反覆迭代，直到失敗率低到可以接受。

這是持續的循環。隨著系統改進，更細微的新失敗模式會浮現，flywheel 就再轉一圈。這個流程是打造穩健、可靠 AI 應用的核心方法。

![Evaluation flywheel](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/evaluation-flywheel.png)
> **Source:** Shankar, S., & Husain, H. (2025). *Application-Centric AI Evals for Engineers and Technical Product Managers*. AI Evals Course Reader.

## 範例

為了說明評估流程，我們用一個 production 中的**公寓租賃助理**的資料。

它回答潛在租客的問題，例如：

* “How large are the apartments?”
* “When can I come in for a tour?”

假設我們想分析應用中的某個特定 prompt。在 OpenAI Platform 上，可以先加入 prompt，並把輸入和輸出資料上傳到 Dataset（怎麼做請看[我們的文件](https://platform.openai.com/docs/guides/evaluations-getting-started)）。

![Leasing agent data](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dataset.png)

prompt 和 trace 都載入後，就可以開始分析 prompt 的效果了。

## 分析 prompt 效果

要改進系統，必須先了解它怎麼失敗。自動化指標適合追蹤進度，但沒辦法告訴你失敗是*為什麼*發生的。手動分析模型輸出，是診斷問題並取得針對性改進洞察最有效的方法。

分析的核心是**標註（annotation）**，也就是對文字套用結構化的標籤，來分類並理解失敗模式。這會把雜亂的失敗變成可執行的改進路線圖。我們建議用質性研究的兩步驟方法：open coding 和 axial coding。

### 1. Open Coding：發現失敗模式

第一步是讀一批失敗的 trace（建議先從約 50 筆開始），對你發現的每個錯誤標上描述性的標籤。這個階段不用煩惱建立完美、有結構的分類，目標是發現問題。

在 OpenAI Platform 上，可以用標註欄位對資料集做 open coding。這裡我們新增一個 **Feedback** 類型的標註欄位，叫 `open_coding`，用來記錄結果。

![Creating a feedback column](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/creating-feedback-column.png)

以我們的公寓租賃助理來說，最初的 open code 可能像這樣：

* “bot suggested a tour time that wasn't available”
* “the list of amenities was a single block of text”
* “failed to cancel the original appointment when rescheduling”
* “the link to the floorplan was broken”

這些具體、來自資料的標籤，是下一步的原始素材。

![Open coding](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/open-coding.png)

這是 open coding 之後的資料集。

### 2. Axial Coding：整理你的洞察

有了一批 open code 之後，下一步是把它們歸成更高層的類別。這就是 axial coding，也就是找出最初標籤之間的關係，對核心問題建立結構化的理解。

我們可以把 open code 歸進預先定義的 axial code：

* **Tour scheduling/rescheduling issue：**
  * Bot suggested a tour time that wasn't available
  * Failed to cancel the original appointment when rescheduling
* **Formatting error with output：**
  * The list of amenities was a single block of text
  * The link to the floorplan was broken

我們會在資料集新增一個 **Label** 類型的標註欄位，叫 `axial_coding`，來記錄這些分類。

![Axial coding](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/axial-coding.png)

這個簡單的分類，讓我們清楚、量化地看到系統主要的弱點。我們可能發現 35% 的失敗跟導覽排程有關，只有 10% 是格式錯誤。這告訴我們改進該把力氣放在哪裡。想了解更多怎麼做錯誤分析，請看[這份逐步示範](https://youtu.be/qH1dZ8JLLdU?si=Sxczt-LpKVVnMEdG)。

## 用自動 grader 增加穩健性

有了分類和資料集，就可以開始把 evaluation flywheel 自動化了。OpenAI Platform 支援[多種 grader 類型](https://platform.openai.com/docs/guides/graders)（包括 Python grader 和 LLM grader），可以對資料集批次執行（詳見[這裡](https://platform.openai.com/docs/guides/evaluation-getting-started#adding-graders)）。這個範例可以建立並執行下列 LLM grader：

* **Formatting grader：** 評估模型的回應是否符合期望的格式
* **Availability accuracy grader：** 把模型回傳的可預約時間，跟你在資料集裡指定的 ground truth 值做比較

Formatting grader 的指令相當直接。
![Creating formatting grader](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/creating-formatting-grader.png)

Availability accuracy grader 會參考我們在資料集額外加的輸入欄位，裡面記錄營業時間和每天的可預約狀況。
![Creating availability grader](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/creating-availability-grader.png)
![Ground truth columns](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/ground-truth-columns.png)

有了自動 grader，系統不論怎麼改，不管是更新 prompt、模型參數，還是新發現的邊界案例，我們都能輕鬆評估表現。

想知道怎麼把 grader 做對，請看下面「對齊你的 LLM judge」那節。

## 最佳化 prompt

我們已經找出並分類錯誤，也建好 grading 把 flywheel 自動化。這時可以選擇用資料來指導手動修改 prompt。不過 OpenAI Platform 支援自動的 [prompt optimization 工具](https://platform.openai.com/docs/guides/prompt-optimizer)，可以加快這個過程。

Prompt optimizer 會同時考慮我們產生的輸出、自訂的標註欄位和 grader，來構造改進後的 prompt。這裡的範例規模很小，但如果有完整資料集（比如前面建議的 50 筆），optimizer 會產生能解決我們發現的許多錯誤的新 prompt。

我們可能還想繼續迭代：重新標註新的模型輸出、新增或調整 grader，再重新最佳化。Grader 和標註欄位的設定會在各分頁間保留，所以工作時可以在新分頁持續建立更多 prompt 版本。分頁也讓我們比較不同模型的表現，因此可以用 grader 衡量哪種模型參數設定表現最好。

這個流程讓我們能隨時間持續改進 prompt，主動回應新的錯誤或新的模型發布。

## 進階技巧

### 用 synthetic data 擴充資料集

核心的 evaluation flywheel 是改進系統的主要工具。但有時你需要的測試資料比 production log 能收集到的更多。在這些情況下，生成 synthetic data 是強大的補充技巧。特別適合：想更深入探索某個特定失敗模式、產品還沒上線需要初始資料，或你對某個弱點有假設但缺乏真實案例驗證。
單純叫 LLM「生成 N 個範例」，常會得到同質性很高的測試案例。更有結構的做法是定義 query 的關鍵維度，再對各維度的組合（形成 tuple）生成資料。這樣測試集會更多元、涵蓋更廣。

以我們的租賃助理為例，可以定義這些維度：

* **Channel：** Voice, Chat, Text
* **Intent：** Tour Scheduling, Maintenance, General Info & Inquiries
* **Persona：** Prospective Resident, Agency

然後把它們組成像 `(Text, Tour Scheduling, Prospective Resident)` 這樣的 tuple，prompt LLM 生成符合這個設定的具體測試案例。這種結構化方法能產生有挑戰性又貼近現實的情境，是比較簡單的生成流程容易漏掉的。

除了變化 query 的核心元件，你還可以套用 **perturbation（擾動）** 讓測試案例更難、更貼近現實。做法是稍微改動生成的範例，測試系統的耐用性。常見的 perturbation 包括加入不相關的資訊、引入錯誤，或使用不同的俚語。

想深入了解這個主題，請看[這個討論](https://hamel.dev/blog/posts/evals-faq/#q-what-is-the-best-approach-for-generating-synthetic-data)。

### 對齊你的 LLM judge

自動化的 LLM judge 只有在判斷值得信賴時才有用。為了確保這點，你必須用「gold standard」資料集，系統化地衡量它跟人類領域專家（SME）比起來的表現。

不過大多數測試集是**不平衡的**，「pass」範例遠多於「fail」範例。這讓單純的 accuracy 分數有誤導性。一個永遠猜「pass」的 judge 可能有 95% accuracy，卻一個失敗都找不出來。

* **True Positive Rate (TPR)：** judge 正確辨識出*失敗*的能力有多好？
* **True Negative Rate (TNR)：** judge 正確辨識出*通過*的能力有多好？

目標是 TPR 和 TNR 都拿高分。這證明 judge 能有效找出真正的問題，又不會過度挑剔。這個衡量流程會用標準的資料集切分。

1. **Train Set（約 20%）**
   這個集合唯一的任務，是為 judge 的 prompt 提供 "few-shot" 範例。你會從中挑幾個明確的 pass / fail 案例，直接放進 prompt，給它一個好的起點。

2. **Validation Set（約 40%）**
   在這裡反覆改進你的 judge。對這個集合執行 judge，分析它的判斷跟專家不同的案例。調整 judge 的 prompt 指令，改善它的 TPR 和 TNR。

3. **Test Set（約 40%）**
   這個最後保留的集合是你的成績單。調整完後，只對它執行一次 judge。最後的 TPR 和 TNR 分數可以確認你沒有 overfit，也給你一個可信的 judge 表現衡量。

想了解更多怎麼讓 LLM judge 跟你的 SME 對齊，請看[這個討論](https://hamel.dev/blog/posts/llm-judge/)。想知道評判你的 AI 該用哪種模型，請看[這篇文章](https://hamel.dev/blog/posts/evals-faq/#q-can-i-use-the-same-model-for-both-the-main-task-and-evaluation)。

## 下一步

這份 cookbook 提供了打造耐用 prompt 的基礎流程，但 evaluation flywheel 不會在一輪之後就停止。下一步是把這個流程變成工程實務的核心：把 grader 整合進 CI/CD pipeline，並監控 production 資料來發現新的失敗模式。

此外，AI 評估的世界很深，充滿我們沒辦法在這裡涵蓋的挑戰。在建立你的 eval 策略時，你可能會遇到更複雜的問題，例如：
* 我要怎麼向團隊說明投資評估的必要性？
* 為什麼二元（pass/fail）評估常常比 1-5 分的評分量表更好？
* 除錯複雜的多輪對話 trace，最好的方法是什麼？
* 我該怎麼評估我的 RAG 系統？
* 這個工作流程要怎麼套用到 agentic 系統？

建議看看[這份 Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) 繼續深入研究。

## 重點整理

- 失敗要先靠人工標註看懂，open coding 找問題，axial coding 把問題歸類並量化，才知道該先改哪裡。
- 自動化 grader 讓每次改 prompt、換模型都能立刻量到影響，這是 flywheel 能持續轉的關鍵。
- 不平衡的測試集不能只看 accuracy，要同時看 TPR 和 TNR 才知道 LLM judge 可不可信。
- Synthetic data 用維度組合加 perturbation 生成，比單純叫 LLM 生成 N 個範例更多元。

## 練習

1. 挑你自己某個應用的 20 筆失敗輸出，寫下 open code，再把它們歸成 2 到 3 個 axial code，算出每類佔幾成。
2. 為其中一個失敗類型寫一個 LLM grader 的 prompt，用 pass / fail 二元輸出，並設計 2 個 few-shot 範例。
3. 用 Channel、Intent、Persona 三個維度（或你自己的），列出 5 個 tuple，為每個 tuple 生成一則測試 query，並替其中兩則加上 perturbation，再依 20% / 40% / 40% 切成 train、validation、test。
