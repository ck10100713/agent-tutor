---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/stripe_model_eval/selecting_a_model_based_on_stripe_conversion.ipynb
---
# 用 Stripe 轉換率選模型：給新創的實用 eval

> 原文：[examples/stripe_model_eval/selecting_a_model_based_on_stripe_conversion.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/stripe_model_eval/selecting_a_model_based_on_stripe_conversion.ipynb)



## 這篇在做什麼
這篇用 HyperWrite 的實際案例，教你怎麼不看 benchmark，直接用 A/B test 比較不同模型對 Stripe 付費轉換率的影響。重點是挑出「不會讓使用者少付錢、但成本更低」的模型。整篇偏方法論，只有一小段 Python 用來算 p-value。

## 學完你會
- 設計一個以付費轉換為指標的 A/B test，來比較兩個以上的 LLM
- 決定 one-tailed、non-inferiority 這類檢定參數（alpha、power、MDE），並用 Python 跑 two-proportion Z-test
- 規劃一條把使用者行為和 Stripe `checkout.session.completed` webhook 串起來的資料流程

## 開跑前
這篇是方法介紹，要自己套用的話需要 Stripe（或其他金流）帳號，以及每個測試組至少約一千名使用者。

## 概覽
最適合你的模型，取決於你的商業目標。很多新創是看離線評測和公開 benchmark 來選 LLM，但 benchmark 分數高，不代表使用者會願意付費、訂閱或持續使用。帳面上很強的模型，在實際商業指標上可能表現不好。

這份指南的評測方法鎖定新創最重要的商業結果之一：使用者願不願意付錢。

我們會走一遍 HyperWrite 的模型評估流程，重點放在真實的付費轉換，也就是 Stripe 的一次性購買或月訂閱（MRR）。如果你想提高轉換率，或是想換成比較便宜的模型又不想掉轉換率，這個範例可以當參考。

## 前提與範圍
要把這份指南套到你的業務上，你需要：

- **一個金流服務。** 這裡用 Stripe，但稍微調整後，同樣的做法可以用在任何金流。
- **足夠的使用者數量才有意義的訊號。** 每個測試組至少一千名使用者；想要更高的統計顯著性，就需要更多。
- **一個有轉換事件的 AI 產品。** 我們用的是 LLM 應用，轉換事件是付款。語音、影片等其他模態的 app 也適用同樣的測法。

## 依實際目標選模型
HyperWrite 做 AI 寫作工具和研究助理，核心產品是一個具備進階研究能力的寫作助理。

離線 benchmark 沒辦法預測 HyperWrite 最在意的事：使用者有沒有用這個寫作助理用到願意訂閱、持續使用。所以 HyperWrite 團隊把重心放在目標結果，也就是轉換，改用真實的 A/B test 比較 Stripe 轉換率來挑模型。

## 新創真正在乎的：轉換
對很多新創來說，目標就是讓使用者註冊並持續使用產品。用經典的 A/B testing，也就是科學家用了幾十年的統計方法，你可以設計一套模型評估流程：
- 新使用者分批，每一批用不同的 AI 模型。
- 為了讓使用者遇到升級提示的時機一致，使用者傳了固定數量的訊息之後就套用同樣的 rate limit，製造一個有意義的升級時刻。
- 追蹤每一組轉換成付費訂閱（透過 Stripe）的比例。

隨機分配使用者到不同模型，並控制其他因素（onboarding、功能、prompt 等），轉換率的差異就能歸因到被測試的模型，而不是外部變數。統計方法則讓你有信心說，看到的差異不太可能是巧合。

當你找到真實、非隨機的改善（例如某個模型的轉換率比較高），影響很具體：更高的 Stripe 轉換、更多付費使用者，而且如果模型更有效率，成本通常也更低。

## 怎麼用 A/B test 選模型
A/B testing 可以當成真實世界的評測工具來選模型。把使用者隨機分組，每組給不同的體驗（這裡是不同的 AI 模型），再看哪一組在關鍵指標上表現較好，這裡的指標就是 Stripe 轉換。

### 基本款：一個模型對另一個
標準設定有一個「control」（你目前用的模型）和一個「variant」（挑戰者）。使用者隨機分到其中一組。為了讓測試只反映模型的影響，其他東西都要一樣：onboarding、功能、prompt，還有轉換的機會。等到預先設定的期間或人數到了，就比較轉換率：用 Model A 還是 Model B 的人付費比較多？

### 真實案例：HyperWrite 的模型替換測試
HyperWrite 的目標是換成比較便宜的 LLM，而且不要明顯影響營收。這是 non-inferiority（非劣性）情境：重點是確認新模型沒有顯著比 control 差。考慮到要省成本，他們設計了單邊的非劣性檢定。
- **測試重點：** 省成本，同時不傷害 Stripe 轉換。
- **設計：** 單尾 two-proportion Z-test（重點是偵測新模型是不是比較差）。
- **Alpha（Type I error 率）：** 0.15（也就是 85% 信心）。對這家新創來說，迭代速度比很嚴格的顯著性門檻重要。
- **Power：** 0.60（足以抓到有意義的下滑，同時兼顧流量限制）。
- **Minimum detectable effect（MDE）：** 轉換率掉 30%，小於這個幅度的下滑，只要省下的成本划算，就視為「夠接近」。
- **族群：** 某段期間內的一批新註冊使用者，註冊時用 `user_id` 隨機分組。
- **觸發點：** 使用者傳訊息、碰到升級 paywall，之後可能透過 Stripe checkout 轉換。

## 設定參數：怎樣算贏？
不是每個觀察到的差異都有意義，有些只是巧合。A/B testing 幫你把真實效果和隨機雜訊分開。最常用的統計工具是「two-proportion Z-test」，它檢查兩組轉換率的差異夠不夠大，大到可以視為統計顯著。

這個檢定有幾種變化：
- **單尾檢定（One-tailed test）：** 檢查新模型是否比 control 好（或依設計，檢查是否「沒有比較差」）
- **雙尾檢定（Two-tailed test）：** 檢查有沒有任何差異，不管是變好或變差
- **多變量檢定（A/B/n）：** 同時比較三個以上的模型

要選哪種看你的目標。如果你要的是明確的轉換提升，找改善的單尾檢定就夠。如果你願意換成「沒有比較差但比較便宜」的模型，就可以設計非劣性（單邊）檢定，確保新模型沒有顯著變差。

### 關鍵名詞
- **Type I Error（偽陽性）：** 實際沒有效果，卻判定有效果
- **Type II Error（偽陰性）：** 實際有效果，卻沒偵測到
- **Alpha（α）：** 可接受的 Type I error 風險（常設 0.05，也就是 5%）
- **Power：** 偵測到真實效果的機率（常見目標是 80%）

### 範例：跑一次真實的模型測試
假設要在目前的模型（Control）和新的 variant（Model X）之間做選擇。你跑單尾 two-proportion Z-test，看 Model X 的轉換是不是比 Control 好。設定 α = 0.05，用你的 baseline 轉換率和想偵測的最小效果做 power 計算後，得出每組約 1,500 名使用者可以達到約 75% 的 power，這是為了更快拿到方向性結果的折衷。

兩組都達到所需樣本數後，資料可能長這樣：

| Group                      | Users Assigned | Conversions | Conversion Rate | p-value | Stat. Significant? | Winner? | Type I Error Guarded? | Type II Error Guarded? |
|----------------------------|----------------|-------------|-----------------|---------|--------------------|---------|-----------------------|------------------------|
| Control (Current Model)    | 1500           | 15          | 1.0%            | --      | Reference          | No      | Yes                   | Yes                    |
| Model X (Variant)          | 1500           | 30          | 2.0%            | 0.012   | Yes                | Yes     | Yes                   | Yes                    |

- **Users Assigned：** 每組隨機分到的使用者數。
- **Conversions：** 每組透過 Stripe 付費的人數。
- **Conversion Rate：** 轉換數除以分到的使用者數。
- **p-value：** 單尾 two-proportion Z-test 的結果，用來看 Model X 較高的轉換率是不是不太可能來自巧合。
- **Stat. Significant?：** p-value 有沒有小於你的 alpha（這裡是 0.05）。
- **Winner?：** 如果統計顯著，Model X 就是新的贏家。
- **Type I Error Guarded?：** 偽陽性風險有沒有控制在 alpha 門檻內。
- **Type II Error Guarded?：** 樣本數夠不夠偵測到真實效果。

這次的結果中，Model X 的轉換率比 control 高 1 個百分點（2.0% 對 1.0%），相對提升 100%。p-value 0.012 遠低於 0.05，所以標記為統計顯著，Model X 是贏家。因為我們是照 75% 的統計 power 規劃樣本數，所以也有信心沒有漏掉真實效果（Type II error）。又因為 alpha 設在 0.05，偽陽性（Type I error）的風險也在控制內。

### 真實案例：HyperWrite 的測試參數
HyperWrite 沒有照課本預設用 95% 信心和 80% power。流量很貴，追求最大統計確定性會拖慢學習速度、燒掉資金。他們選 85% 信心和 60% power，可以偵測任何明顯的下滑（約 30% 的降幅），又不會為了很小的差異過度最佳化。

轉換率通常會隨測試時間拉長而上升。這些測試在達到所需樣本數（N）後就停止。每個測試組只分配一小部分進站流量，大部分流量仍留在已驗證的 control 體驗。

### 多重比較的說明
他們用的是 A/B/n（「多對一」）設計：每個候選模型（GPT-4.1 和 GPT-4.1-mini）都跟 production control（Claude 3.5 Sonnet）比，但彼此之間不互比。

因為上線決策是針對單一 variant（「如果該組自己的單尾非劣性檢定在 α = 0.15 下通過就上線，否則丟掉」），所以沒有做 family-wise error rate 校正。這在小 k、以 control 為中心的測試中很標準。偽陽性風險只落在最後上線的那一組，不做 Bonferroni 這類切分也能保住 power。

### 用 Python 檢查 A/B test 顯著性
為了示範 A/B test 背後的統計怎麼運作，下面這段 10 行左右的 Python 把原始轉換數轉成 p-value，用的是單尾 two-proportion Z-test（variant 優於 control）。貼到任何 Python REPL、Colab 或 notebook 都能跑，做真實實驗時換成你自己的數字就好。
```python
# One-tailed two-proportion Z-test
from statsmodels.stats.proportion import proportions_ztest

conversions   = [30, 15]     # [variant, control]
sample_sizes  = [1500, 1500] # [variant, control]

z_stat, p_val = proportions_ztest(
    conversions,
    sample_sizes,
    alternative="larger"      # "larger" → variant > control
)

print(f"Z-statistic = {z_stat:.2f}")
print(f"p-value     = {p_val:.3f}")    # → 0.012 (α = 0.05)
```

怎麼看結果：
- 如果 p-value **≤ 0.05**，表示 variant 較高的轉換在統計上顯著，可以上線，或繼續收資料觀察。
- 如果 **> 0.05**，結果可能只是雜訊，可以多收資料，或繼續用 control。

### 注意事項
- **挑尾巴 / p-hacking：** 在第一位使用者進來之前，就要決定用單尾還是雙尾，之後再改會讓 Type I error（偽陽性）膨脹。
- **數量太少：** 如果任一組的轉換數少於約 10，就把 Z-test 換成 Fisher's exact test，或用 Wilson/Wald 信賴區間。
- **提早偷看：** 沒有 α-spending 校正就反覆查看資料，會提高偽陽性風險。用固定樣本數，或 group-sequential 設計。
- **使用者重疊 / 汙染：** 確保同一個 user ID 不會落到兩組（例如透過登出再登入）。
- **多個挑戰者：** 如果打算從很多 variant 中挑出單一「最佳」，要控制 family-wise error（Bonferroni、Holm），或改用 multi-armed bandit。
- **快取與 prompt 漂移：** 確認你的 inference 層不會把一個模型的回應漏到另一個的快取，各組的 prompt 要保持一致。
想進一步了解這些陷阱和避免方式，可以看 Evan Miller 的 ["How Not to Run an A/B Test"](https://www.evanmiller.org/how-not-to-run-an-ab-test.html)

### 最大的收穫
A/B testing 不只用在 landing page 或按鈕顏色，它對挑選產品該用哪個 LLM 也很關鍵。把它放進工作流程，你可以避開代價高昂的錯誤，找到真正符合使用者價值的升級：一個值得付費的產品。

## 真實案例：HyperWrite 用 GPT-4.1 省成本
模型的價格常常隨能力提升而上漲。HyperWrite 花了幾個月找一個能追平現有模型（Anthropic 的 Claude 3.5 Sonnet）、又不傷害轉換和使用者體驗的模型，最好成本還更低。試了幾個表現較差的模型之後，OpenAI 的 GPT-4.1 給出了亮眼結果：在更低的價格下，追平現有模型的 Stripe 轉換。

各 variant 在 Stripe 轉換上的比較如下：

| Variant                                      | Assigned | Conversions | Rate  | Req N | % Done | Conv cut-off (≤) | Worse? |
|----------------------------------------------|---------:|------------:|------:|------:|-------:|-----------------:|:------:|
| anthropic/claude-3.5-sonnet (control)        |    4550 |          42 | 0.92% |  3378 |   135% | —                | —      |
| openai/gpt-4.1 (variant)                     |    4513 |          58 | 1.29% |  3378 |   134% | 32               | No     |
| openai/gpt-4.1-mini (variant)                |    4557 |          45 | 0.99% |  3378 |   135% | 33               | No     |
- **Variant：** 模型名稱（control 或挑戰者）。
- **Assigned：** 隨機分到該組的使用者數。
- **Conversions：** 該組透過 Stripe 付費的使用者數。
- **Rate：** Conversions 除以 Assigned。
- **Req N：** 非劣性檢定預先算好的樣本數目標。
- **% Done：** Assigned 除以 Req N（達成目標的進度）。
- **Conv cut-off (≤)：** 轉換數低於這個值，該組就會被判定「顯著比 control 差」。
- **Worse?：** 如果該組低於它的 cut-off（也就是統計上較差）就是「Yes」，否則「No」。

**結果**

- 兩個 GPT-4.1 variant 都高過各自的 cut-off，表示都沒有在統計上比 control 差。
- GPT-4.1（完整版）在轉換率上跟 Claude 3.5 Sonnet 不相上下，同時大幅省下成本。

### 衡量轉換需要一點創意和資料
要做這個分析，你需要一套把使用者行為和 Stripe 付款事件串起來的系統。這沒有通用範本，但 HyperWrite 用的架構可以當一種實作參考。這個流程可以改成適用於任何「使用者跟 AI 互動、並能透過 Stripe 升級」的新創。
1. **使用者追蹤：** 為每個新註冊使用者指派一個唯一識別碼，貫穿整個生命週期。
2. **模型分配：** 在註冊時把每位使用者隨機分到一個測試組（模型 variant），並把分配結果存進資料庫。
3. **互動記錄：** 記錄關鍵事件（例如第一次使用、碰到 rate limit），連同使用者 ID 和模型分配一起存。
4. **轉換事件擷取：** 設定 Stripe webhook 監聽 `checkout.session.completed` 事件。觸發時，把 Stripe customer 對應到內部 user ID，並更新資料庫標記為已付費轉換。
5. **資料彙整：** 定期把測試組分配和轉換資料拉到同一張表或 dashboard 做分析。
6. **統計檢定：** 用基本的 Z-test（很多函式庫和 Excel 範本都有）分析轉換率差異有沒有意義。

下面的流程圖說明整個過程：

![Process diagram](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/stripe_eval_diagram.png)

#### 使用者流程
HyperWrite 的使用者歷程大概是這樣：
1. **使用者註冊：** 使用者建立帳號，資料存進資料庫並指派唯一的 `user_id`。
2. **送出第一則訊息：** 新使用者第一次跟寫作助理互動。
3. **觸發 rate limit：** 送出一定數量的訊息後碰到 rate limit，這提供了一個固定的時間點可以顯示升級提示。
4. **轉換機會：** 有些使用者在這時選擇訂閱，會被導向 Stripe checkout。

#### Stripe 流程
我們在意兩個 Stripe 動作：
1. **監聽 Stripe 事件：** 系統監聽 Stripe webhook 的 `checkout.session.completed` 事件，付款成功時會觸發。
2. **更新資料庫：** 收到 webhook 後，把對應的 `user_id` 在資料庫標記為已轉換。

#### 執行測試
定期檢查測試是否完成：
1. **查詢測試組：** 取出分到每個模型 variant 的所有使用者。
2. **合併 Stripe 資料：** 把使用者資料和 Stripe 訂閱事件合併，這樣就知道每組中哪些人轉換了。
3. **跑統計：** 用單尾 two-proportion Z-test（見前面的段落）檢查轉換率差異在統計上有沒有意義。

## 結論與下一步
這個方法的主要心得是，跟商業指標（例如 Stripe 轉換）綁在一起的真實測試，能看出哪些模型選擇真的帶來成果。離線 benchmark 和實驗室測試有它的用處，但把評測連到使用者決定付費的那一刻，常常能做出對客戶和公司都有利的決策。

### 這對新創的意義
不一定要打敗現有模型；在關鍵指標上表現「一樣好」但成本更低的模型，同樣很有價值。這個案例中，OpenAI 的 GPT-4.1 在降低成本的同時，追平了現有模型的 Stripe 轉換率。

這凸顯了把模型評測綁在 Stripe 驅動的 A/B test 上的價值：你拿到的是跟營收連動的明確答案，而不是只靠 benchmark 或主觀印象。

新創可以往幾個方向延伸這個測試：
- **依 persona 或使用情境分群：** 把受眾切開（例如重度使用者對新手、不同產業），看哪個模型或 prompt 對哪一群最有效。
- **找營收與成本的甜蜜點：** 不只看營收，也要考慮每個模型的服務成本。最佳選擇可能是平衡獲利，而不是單純把銷售衝到最高。
- **監測長期影響：** 不只看當下的轉換，也追蹤訂閱者終身價值、churn、留存等指標，為可持續成長做最佳化。

在衡量什麼、怎麼實驗上有很大的發揮空間，你可以針對團隊最在意的事把產品調到最好。

如果對這類測試有疑問、想對你的做法得到回饋，或需要建立自己測試的建議，歡迎聯絡：[josh@othersideai.com](mailto:josh@othersideai.com)。

祝你建造順利、實驗順利，讓使用者和你的 Stripe dashboard 帶路。

## 貢獻者

這份 cookbook 由 [Josh Bickett](https://www.linkedin.com/in/josh-bickett-4219b166/) 貢獻，他是 HyperWrite 的 Lead Engineer，HyperWrite 是一家做 AI 寫作工具和研究助理的公司。文中的方法和案例反映了 HyperWrite 的經驗，但目的是作為新創用付費轉換指標評估 LLM 的通用指南。

## 重點整理
- 離線 benchmark 分數高不等於使用者願意付費，直接用 Stripe 轉換這類商業指標做 A/B test 更貼近真實。
- 要換便宜模型時，用非劣性檢定回答「有沒有顯著變差」，比追求「一定要贏」更實際。
- alpha、power、MDE 要依流量成本和決策速度調整，不必照課本的 95% 和 80%。
- 實驗要守紀律：事先決定單尾或雙尾、固定樣本數、避免提早偷看、避免使用者落入兩組。
- 整條資料線的關鍵是 user_id、分組紀錄，加上 `checkout.session.completed` webhook 把付款對回使用者。

## 練習
1. 把 Python 範例裡的轉換數換成表格中 GPT-4.1 和 Claude 3.5 Sonnet 的數字（42/4550 與 58/4513），看 p-value 是多少，並判斷以 α = 0.05 是否顯著。
2. 把程式改成非劣性檢定：把 control 的轉換率乘上 0.7 當作門檻，檢查 gpt-4.1-mini（45/4557）是不是沒有顯著低於這個門檻。
3. 在程式裡加一個檢查：任一組轉換數少於 10 時印出警告，建議改用 Fisher's exact test，並用 `scipy.stats.fisher_exact` 實作這個分支。
