---
translated: true
source: examples/Realtime_eval_guide.ipynb
---
# Realtime Eval 指南

> 原文：[examples/Realtime_eval_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Realtime_eval_guide.ipynb)

## 這篇在做什麼

這是一份教你怎麼替語音系統（Realtime API）做 eval 的方法論指南。從最簡單的 Crawl、加入真實感的 Walk、到多輪對話的 Run，一步步建立資料集、grader 和 eval harness，最後用正式環境的失敗案例持續擴充測試。

## 學完你會

- 分辨語音 eval 的兩個獨立面向（內容品質、音訊品質），並知道為什麼 transcript 不能當 ground truth
- 用 Crawl / Walk / Run 與 eval 象限，規劃由簡到難的測試路線
- 設計 gold 種子資料集、分層的 grader，並照步驟寫出單輪重播的 harness

## 開跑前

文章本身沒有要執行的程式碼。想看可執行的 harness，可以用文中連到的 `examples/evals/realtime_evals` 資料夾，跑 Realtime API 需要 OpenAI API key。

<p align="center">
<img
  width="650"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_01_image_01.png"
  alt="Diagram from page 1"
/>
</p>


## 簡介

Evals 能讓語音 demo 變成大家可以依賴的東西。「看起來還行」和「每天都能用」之間的差距，幾乎都是 eval。

這份指南說明怎麼評估語音系統，做法是逐步增加複雜度：先從簡單的開始（Crawl），加入真實感（Walk），再測試多輪對話（Run）。過程中你會學到怎麼建立讓結果穩固的三樣東西：資料集、grader 和 eval harness，另外還有一個正式環境的飛輪，讓真實的失敗變成新的測試。

投資在 eval 的團隊可以**快 5 到 10 倍**上線，因為他們看得到哪裡壞了、找得出原因，也能有把握地修好。


### Realtime Eval Harness 程式碼

如果你想要可以執行的程式碼來建立 eval harness，先看這個 repo 資料夾：

- **GitHub repo 路徑：** [openai-cookbook/examples/evals/realtime_evals](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals)
- 裡面有每個成熟度階段的完整參考 harness：
  - [Crawl harness (single-turn replay)](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals/crawl_harness)
  - [Walk harness (saved audio replay)](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals/walk_harness)
  - [Run harness (model-simulated multi-turn)](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals/run_harness)

你可以讓 Codex 指向想用的 harness，請它依你的資料和 grader 改寫。

## 第一部分：基礎

### 1) 為什麼 realtime eval 很難

Realtime 比文字難，因為你要評分的是一個**串流互動**，有兩種輸出：assistant **做了什麼**，以及它**聽起來怎麼樣**。一個回應可以「內容正確」，但聽起來是壞的。

#### 1.1 Realtime 品質的兩個軸

文字 eval 多半只問內容對不對。Realtime 多了第二個軸：音訊品質。內容和音訊可以各自獨立出問題，所以單一分數可能把真正的問題藏起來。

**大多數 realtime eval 可以簡化成兩個獨立的軸：**

1. 內容品質：assistant 有沒有聽懂使用者並做對事？包括正確性、有沒有幫助、tool 選擇、tool 參數，以及指令遵循。

2. 音訊品質：assistant 聽起來能不能接受？包括自然度、韻律、發音、穩定性，以及在雜訊和不完美收音下的表現。



#### 1.2 難以除錯

用 **Responses API** 時，心智模型很簡單：**request 進 → response 出**。用 **Realtime API** 時，一個「turn」是一條**串接起來的 pipeline**。這種編排讓語音應用很容易建，但做 eval 時，你必須替每個階段記 log，才能隔離失敗並找到根本原因。

<p align="center">
<img
  width="700"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_02_image_01.png"
  alt="Diagram from page 2"
/>
</p>


一個「turn」是一串事件（開始說話 / 停止說話 → commit → response.create → audio deltas → done），失敗可能發生在任何一個階段。如果把系統當黑盒子，你會一直在追「模型問題」，其實是 turn detection、buffering 或 tool 整合的問題。

**範例：**

- 內容正確，但體驗是壞的：barge-in 時打斷的邊界抓錯，導致音訊被切掉。

- 答案「正確」但感覺很慢：延遲來自網路品質或 turn detection 太慢，不是模型推理。

想更了解 Realtime API 會觸發的各種事件，可以看[這裡](https://platform.openai.com/docs/api-reference/realtime-server-events)。

#### 1.3 Transcript 不等於 ground truth

在 realtime API 裡，「使用者說了什麼」的 ground truth 是**實際的音訊訊號**（麥克風收到、模型聽到的東西）。transcript 不是 ground truth，而是**模型對那段音訊產生的詮釋**，會受限於**轉錄模型的錯誤**而出錯。

**如果把 transcript 當成真相，你的 eval 可能會誤導你：**

- 誤判失敗：ASR 漏掉一個數字，但模型其實聽到了、也正確呼叫了 tool，結果你的 LLM grader 判成「錯」。

- 誤判通過：transcript 看起來很乾淨，但音訊被截斷、模型是用猜的，你就錯過了真正的問題。

**最佳實務：**

- **改善轉錄：** 調整轉錄的 [prompt](https://platform.openai.com/docs/guides/speech-to-text#prompting)，試不同的[模型](https://platform.openai.com/docs/guides/speech-to-text)，或試其他方法，例如 [oob transcription](https://cookbook.openai.com/examples/realtime_out_of_band_transcription)。

- **用 transcript 做規模化：** 大部分自動化評分跑在 **transcript + trace** 上。

- **用混亂的真實資料校準 grader：** 用**接近正式環境、有雜訊的 transcript**（不是乾淨的文字）來迭代 grader，這樣它們不會對 ASR 錯誤反應過度。

- **加一個音訊稽核循環：** 對 **約 1–5%** 的 session 做端到端抽查。

<p align="center">
<img
  width="650"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_03_image_01.png"
  alt="Diagram from page 3"
/>
</p>


## 第二部分：策略

### 2) Crawl / Walk / Run

團隊一開始就挑最難的設定（真實音訊、多輪對話、真實 tool）時，realtime eval 會讓人覺得壓力很大。解法是**一步步增加複雜度**。**連爬都不會，就跑不起來**。早期的 eval 要簡單到失敗可以診斷、可重現，而且迭代成本低。複雜度可以沿兩個獨立的軸增加。

#### 2.1 隔離輸入條件：乾淨音訊 vs 正式環境音訊

這個軸看的是模型聽到什麼。控制輸入音訊的條件，就能把模型智力的失敗和語音感知的失敗分開。

- **從合成音訊開始 → 測試智力：**
    - 想衡量模型的推理和決策、又不想讓音訊變異干擾訊號時，用乾淨、可重複的合成音訊（例如 TTS）→ 有助於隔離 intent routing、tool calling、指令遵循

- **換到有雜訊、接近正式環境的音訊 → 測試音訊感知：**
    - 智力穩定之後，再引入接近正式環境的音訊：壓縮、回音、遠場收音、背景雜訊、猶豫和自我更正。這能測試輸入含糊、混亂或部分遺失時，系統行為是否還正確 → 有助於衡量聽錯字詞的程度，以及對聲學變化的穩健性

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_04_image_01.png"
  alt="Diagram from page 4"
/>
</p>


#### 2.2 隔離互動條件：單輪 vs 多輪

這個軸看的是你在評估什麼：評估下一個 turn，還是整段**對話**。

- **從單輪開始 → 測試核心能力：**
    - 想對基本功得到最乾淨的訊號時，就跑一個 request → 一個 response：正確的 intent routing、正確的 tool 選擇、有效的參數，以及基本的指令遵循。如果系統在這裡連正確選 tool 或產出有效 schema 都做不到，評估更多輪也沒有幫助。

- **換到多輪 → 測試穩健性：**
    - 單輪穩定後，再進入多輪：系統必須在多個 turn 之間維持目標和限制、正確安排 tool 的順序、從 tool 失敗中恢復，並處理使用者的更正。多輪會讓你從 turn 層級的正確性，轉向**整段對話層級的結果**：有沒有完成目標、花了幾個 turn、出錯時有沒有乾淨地恢復？

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_04_image_02.png"
  alt="Diagram from page 4"
/>
</p>


單輪告訴你*能不能贏一場戰役*，多輪告訴你*能不能贏整場戰爭*。

#### 2.3 Eval 象限

用 2x2 的圖來規劃評估：**往右** = 音訊更真實，**往上** = 互動更真實。從左下角開始，一次只提高一個軸的難度。

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_05_image_01.png"
  alt="Diagram from page 5"
/>
</p>


**Eval 模式（複雜度遞增）：**

1. Crawl（左下）：合成音訊 + 單輪

2. Walk（往右）：真實有雜訊的音訊 + 單輪

3. Run（往上）：合成音訊 + 多輪模擬 

右上角（真實音訊 + 完整多輪流程）是手動 eval：像使用者在正式環境那樣，跑端到端的 session。整個專案生命週期都要把它放在流程裡。

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_05_image_02.png"
  alt="Diagram from page 5"
/>
</p>


**範例：**

使用者：「Change my reservation to 7pm.」

- **Crawl：** 你餵入「Change my reservation to 7pm」的固定 TTS 音訊，只評分 assistant 的下一個 turn：它應該 route 到更新訂位的 tool 並傳入正確的 time=7pm（如果缺少必要的識別資訊，就問一個精準的釋疑問題）。
- **Walk：** 錄一段真人麥克風版本的「Change my reservation to 7pm」，再用電話頻寬壓縮和輕微背景雜訊重播同一句話；系統仍應聽成「7pm」（不是「7」或「7:15」），並產生同樣正確的 tool call。
- **Run：** 由模型模擬使用者說出「Change my reservation to 7pm」，再模擬真實的後續追問（「It's under Minhajul for tonight… actually make it 7:30… wait, tomorrow」），並注入一次 tool 錯誤；agent 應該只釐清缺少的資訊、保持狀態一致、乾淨地恢復，最後只呼叫一次正確的更新 tool，反映最終預期的結果。

你可以在這裡找到可以拿來改寫的參考實作：[realtime eval start](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals)。

## 第三部分：三大建構元件

### 4) 資料：建立 benchmark

#### 4.1 從「gold」種子集開始（10–50 筆）

涵蓋你絕對不能失敗的流程：核心 intent、必須成功的 tool call、升級（escalation）與拒絕的行為。快速產生，再請人檢查真實性和缺口。

**目標是先開始，不是做到完美。**

#### 4.2 為迭代而建，不只是為量

eval 資料集是用來驅動迭代的，不是為了看起來很大。這個循環才是產品：**跑 eval → 把失敗定位到特定行為 → 只改一件事 → 重跑 → 確認修好了而且沒有退步**。如果 benchmark 能讓這個循環快速、可重複、容易診斷，它就是「好」的。

這需要的是覆蓋度，不是單純的數量：你要代表實際的使用者行為，以及造成正式環境失敗的特定邊界案例。光靠數量不會揭露脆弱的地方，對的覆蓋才會。 

覆蓋也要平衡。對每個行為，都要同時包含正例（系統應該做 X）和反例（系統不該做 X）。沒有反例，你就是在獎勵走捷徑。

>**客戶範例：** 有個團隊做了語音客服 bot，並且拼命優化「escalate_to_human」這個 tool call。離線分數在 escalation 上達到 98%。實際內部試用時，這個 bot 開始幾乎什麼都 escalate。根本原因是資料集不平衡：「必須 escalate」的案例很多，「不該 escalate」的案例幾乎沒有，所以模型學到一個捷徑：不確定就 escalate。 
最後，你必須精準地替資料打 tag，才能做細粒度的評估。這些 tag 要提供足夠的細節，讓你能從「分數掉了」這種一般觀察，走到具體的根本原因，例如 **「這個 intent 在這種音訊條件、這個政策邊界下會失敗」**。

Tag 的例子：

- intent、預期結果、音訊條件、語言，以及預期的 tool call。有 tag 的資料能讓團隊做細粒度評估，迭代循環也更快。

<p align="center">
<img
  width="1200"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_07_image_01.png"
  alt="Diagram from page 7"
/>
</p>


#### 4.3 從正式環境的失敗擴充

離線 eval 是你快速迭代的方式，但也很容易被超越。如果一直針對固定的 benchmark 優化，**分數可能一直上升，但真實品質（現實）卻停滯**，因為使用者做的事你的資料集沒涵蓋到。

<p align="center">
<img
  width="650"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_07_image_02.png"
  alt="Diagram from page 7"
/>
</p>


運作模式是一個循環：由正式環境擴充 benchmark。新的失敗出現，你重現它、標註它、把它加進去。隨著時間，你的離線測試集應該跟著產品一起成長。

**管理的簡單做法是分成三個集合：**

- **Regression suite：** 你已經修好的困難案例。每次改 prompt、模型和 tool 都要跑。這是你「不能弄壞」的約定。

- **Rolling discovery set：** 正式環境的新失敗和差點失敗的案例。你在這裡學到自己漏了什麼，以及接下來該優先處理什麼。如果它們觸發了失敗模式，就升級到**你的離線資料集**。團隊通常這樣填充：

    - 執行線上 grader 直接抓失敗，和／或

    - 觀察 proxy 指標（延遲、tool 錯誤率、escalation 率、重試），在指標飄移時抽樣資料。
- **Holdout set：** 離線測試的一個子集，保持不動，偶爾跑一次，用來偵測 benchmark 過擬合。如果測試分數上升但 holdout 持平，就表示你在針對考試訓練。

<p align="center">
<img
  width="650"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_08_image_01.png"
  alt="Diagram from page 8"
/>
</p>


### 5) Graders

Grader 是你的**量測儀器**。它們把混亂的即時語音 session 變成**你能信任的訊號**。

#### 5.1 人工審查（槓桿最大）

人工審查 = 聽真實音訊 + 從頭到尾讀完整的 trace。這是建立產品直覺、抓到使用者立刻就會注意到的失敗最快的方法。自動化 eval 告訴你能量測什麼，人工審查告訴你*應該*量測什麼。

**自動化常常低估、但使用者立刻有感的問題：**

- Turn-taking 失敗：尷尬的空檔、雙方同時說話、模型打斷使用者。

- 節奏與韻律：模型說話太快或太慢、囉嗦、平板、抖動、「機器人式的客氣」。

- Transcript 不一致：ASR 延遲／漏字／正規化 → 你最後評分的是錯的東西。

- Eval 系統本身的 bug：golden set 缺少覆蓋、預期值標錯、grader 系統性地太嚴或太鬆。 

> **客戶範例：** 一家大公司讓主管每天花 **約 3 小時**聽 session、掃 trace。他們找出了「隱藏」的問題，像是太早被切掉、幽靈打斷、尷尬的韻律，這些離線 eval 都會直接漏過。

#### 5.2 自動化 grader

人力無法規模化。沒有自動化，退步會溜過去，「改進」也會變成憑感覺。

**使用分層的 grader：**

1. **Deterministic grader** 處理任何客觀、可機器檢查的東西。它們快、便宜、穩定，很適合緊湊的迭代循環和 regression 把關（tool calling、JSON 有效性、字串和 pattern 檢查）。

2. **LLM grader** 幫你衡量重要但不適合用決定性規則表達的東西：正確性、指令遵循、釋疑問題是否恰當、完整性和有沒有幫助。

3. **Audio grader**，因為使用者體驗的是聲音，不是 transcript。音訊仍是最難可靠評判的，所以不要等一個完美的評分器，先從簡單、可量測的檢查開始（靜音、重疊、打斷處理），再隨時間疊加更豐富的 rubric。

<p align="center">
<img
  width="900"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_09_image_01.png"
  alt="Diagram from page 9"
/>
</p>


### 6) Eval Harness

realtime eval 的可信度，取決於執行它的 harness。好的 harness 只有一個任務：**讓每次執行可以比較**。如果同樣的輸入無法在同樣設定下重播並得到相近的結果，就很難量測和迭代。

#### [6.1 從單輪重播開始（「Crawl」harness）](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals/crawl_harness)

從這裡開始。單輪重播能給你最快、最乾淨的訊號，因為幾乎所有東西都能固定。每次執行都要保持完全相同的音訊 bytes、預處理、VAD 設定、codec 和 chunking 策略。

實務上，通常最好一開始就把 voice activity detection (VAD) 關掉，這樣能移除一個主要的變異來源。VAD 關閉時，使用者 turn 何時結束由你決定。

**一個簡單的單輪 harness 長這樣：**

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_10_image_01.png"
  alt="Diagram from page 10"
/>
</p>


**用 Realtime API 的說法更明確地描述：**

1. 產生或載入輸入音訊

    - 如果資料點是文字，就產生 TTS 音訊。
    
        - 通常從文字 → TTS → 音訊開始是最好的第一步，因為迭代快得多。能快速調整文字時，eval 比較容易微調和精進。

2. 把音訊串流進 input buffer

    - 以固定大小的 chunk 傳送音訊（例如：每個 chunk 使用一致的 frame 大小）。

    - 重要：chunking 和時間會影響行為。選一個標準就固守。例如，每個 chunk 20 ms 是在反應速度和額外負擔之間不錯的平衡。

3. Commit 使用者音訊

    - （建議）VAD 關閉時：在最後一個音訊 chunk 之後立刻 commit。

    - VAD 開啟時：由伺服器偵測 turn 邊界。

4. 觸發 assistant 回應

    - VAD 關閉時：呼叫 response.create 開始產生。

    - VAD 開啟時：自動觸發。

5. 收集輸出

    - 輸出音訊 chunk（串流 delta）

    - 輸出 transcript（如果有啟用）

    - Tool call / tool 參數（如果有）

    - 最終完成事件

6. 評分並保存
    - 執行 grader

    - 儲存結果

#### [6.2 重播已儲存的音訊（「Walk」harness）](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals/walk_harness)

從合成 TTS 換成真實錄音時，harness 有一個重要的改變：**你是在串流已儲存的真實音訊 buffer**。

**對已儲存的音訊，流程變成：**

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_10_image_02.png"
  alt="Diagram from page 10"
/>
</p>


**實務上怎麼讓 eval 夠真實：**

- **預處理必須和正式環境一致**
  - 相同的 resampling、normalization、聲道處理、雜訊抑制（如果有用）和編碼。

  - 把預處理設定和結果一起存起來，才能解釋分數為什麼變動。

- **串流策略必須明確**

  - 如果你在意延遲：以固定節奏傳送 chunk（例如「每 20ms 送 20ms 的音訊」）。

  - 如果你只在意迭代速度：可以串流得更快，但 chunk 大小要保持不變。

- **Turn 邊界必須可重複**

  - 離線可重現性優先選 VAD 關閉 + 手動 commit。

  - 如果必須開 VAD（為了跟正式環境一致），要記錄 VAD 設定並追蹤邊界事件，才能除錯失敗。

#### [6.3 模型模擬的多輪（「Run」harness）](https://github.com/openai/openai-cookbook/tree/main/examples/evals/realtime_evals/run_harness)

模型模擬的多輪使用**使用者模擬器**，為一整段對話產生下一個使用者 turn。它能增加情境覆蓋，但前提是各次執行的 episode 要保持可比較。

**常見循環：**

<p align="center">
<img
  width="1000"
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_eval_page_11_image_01.png"
  alt="Diagram from page 11"
/>
</p>


**模擬的最佳實務：**
- **固定並版本化模擬器 prompt：** 把它當程式碼對待。prompt 小改動造成的行為變化，可能比換模型還大。

- **限制隨機性：** 固定 temperature 和 sampling 設定。有 seed 就用。在合理的地方使用決定性的 turn（例如使用者的問候）。

- **用決定性方式 mock tool：** 為情境定義預期的 tool 輸出 mock，assistant 呼叫 tool 時就回傳那些一模一樣的輸出。這樣環境穩定，各次執行才能比較。

- **記錄完整軌跡：** 儲存每個產生的使用者文字 turn，以及你串流出去的最終音訊 bytes。保存 tool call、tool 回傳和時間戳。模擬是一個發現引擎。當它找到真實的失敗模式，就把它回填成 crawl 或 walk 方法用的決定性腳本 episode。

## 第四部分：案例研究

#### 7.1 客服語音 bot

**產品目標與限制**

透過 tool 快速且安全地解決常見的客服請求。bot 必須蒐集正確的細節、呼叫正確的後端動作，並遵守政策。無法處理時必須乾淨地 escalate。遇到沮喪的來電者時，不能變得囉嗦或脆弱。

**Crawl、Walk、Run 計畫**

**Crawl：合成 + 單輪**

重點放在 routing 和政策。給定一個簡短請求，bot 應該選對 intent、要求缺少的資訊，並避免不安全的動作。用決定性的合成音訊，才能快速迭代 tool schema 和 prompt。

**Walk：真實 + 單輪**

測試在真實收音條件下的理解力。使用合成或真實錄音，搭配雜訊環境和類似電話的音質。訂單編號、姓名和地址就是在雜訊音訊上壞掉的地方。評估 bot 是會問釋疑問題，還是用猜的。

**Run：合成 + 多輪模擬**

用 gpt-realtime 模擬使用者，搭配 tool mock，模擬完整的工作流程：驗證身分、帳戶查詢、訂單狀態、退貨資格、退款、建立工單、escalation。加入對抗性但真實的模式：來電者中途改變目標、只提供部分資訊、打斷 assistant 說話，或回答的不是被問的問題。

**人工審查：**

對 staging 系統跑內部通話 session。這能抓到 grader 漏掉的 UX 失敗：過長的免責聲明、重複提問、驗證身分時糟糕的 turn-taking。

**核心資料集分類與有用的切片**

- 熱門 intent：訂單狀態、退貨、退款、取消、帳單問題、重設密碼、預約排程。

- 缺漏與衝突的資訊：訂單編號錯誤、兩個帳戶、來電者給的是暱稱、來電者拒絕驗證身分。

- 政策邊界：超過期限的退貨、受限商品、部分退款、訂閱取消規則。

- Escalation 觸發條件：信心低或 tool 失敗時，bot 應該轉交。

- 情緒語氣：生氣、趕時間、困惑。內容目標不變，但表達方式很重要。

**使用的 grader**

- Deterministic：tool 選擇、tool 參數有效性、必要時檢查政策用語。

- LLM rubric grader：指令遵循、解決方案是否正確、同理的語氣、有沒有避免幻想政策、有沒有適當地 escalate，以及有沒有保持簡潔。
- Audio grader：長時間靜音、打斷處理。

## 重點整理

- realtime 要同時看內容和音訊兩個獨立的軸，只看單一分數會藏住問題。
- transcript 是模型對音訊的詮釋，不是 ground truth。大規模評分用 transcript + trace，再抽 1–5% 做音訊稽核。
- 複雜度要一次只加一個軸：Crawl（合成 + 單輪）、Walk（真實音訊 + 單輪）、Run（合成 + 多輪模擬）。
- 資料集要有正反例並打好 tag，再用 regression、discovery、holdout 三個集合讓正式環境的失敗回流。
- harness 的任務是讓每次執行可比較：固定音訊、chunk 大小、VAD 設定、模擬器 prompt 和 tool mock。

## 練習

1. 照 6.1 的六個步驟，寫出你自己應用的單輪 harness 流程清單，標明每一步要固定哪些參數（chunk 大小、VAD 開關）。
2. 針對一個你會做的 tool call（例如更新訂位），列 10 筆 gold 種子資料，正例和反例各半，並替每筆標上 intent、音訊條件和預期 tool call。
3. 設計一個 Run 的模擬情境：寫出使用者模擬器 prompt、一個會注入一次錯誤的 tool mock，以及三個你會用的 grader（deterministic、LLM、audio 各一）。
