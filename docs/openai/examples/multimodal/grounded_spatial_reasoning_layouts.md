---
translated: true
source: examples/multimodal/grounded_spatial_reasoning_layouts.ipynb
---

# 用 GPT-5.5 評估有依據的空間推理

> 原文：[examples/multimodal/grounded_spatial_reasoning_layouts.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/grounded_spatial_reasoning_layouts.ipynb)

用 vision、structured outputs 和確定性的空間 eval，做出一個 spec 優先的平面圖配置 workflow。

## 這篇在做什麼

給 GPT-5.5 一張空的辦公室平面圖、一份配置 SOP 和一份家具目錄，讓它輸出一份結構化的配置 spec，再用確定性的幾何檢查和語意評分去評估這份 spec。重點在怎麼設計 eval，才能分辨模型是哪一層出錯。

## 學完你會

- 把「平面圖變家具配置」拆成圖像證據、規劃政策（SOP）、物件尺寸（家具目錄）三個輸入。
- 設計三種 eval：validity 當硬性關卡、grounded_program 和 reference_similarity 當軟性分數，並說得出各自抓什麼問題。
- 判斷哪些工作交給模型（讀圖、判斷房間用途），哪些交給確定性程式碼（碰撞、邊界、旋轉、修正）。

## 開跑前

- 這篇主要在講設計與結果，頁面上沒有需要你設定的步驟。
- 原 notebook 的完整流程會用到 OpenAI API（GPT-5.5、GPT Image 2）和 Promptfoo。

傳統上，電腦視覺系統是把空間理解拆成比較窄的感知任務：偵測物件、分割區域、分類場景，或把語言對應到 box 和 mask。目標是定位的時候，這種拆法很好用。但如果任務要模型解讀一個視覺場景、推理這個結構的意義、套用限制條件、再產出一份仍然有效的規劃，這種拆法就沒那麼直接。

前沿的多模態模型讓另一種做法成為可能。我們不必針對某個配置領域，用大量成對的資料去訓練專用模型，而是測試像 GPT-5.5 這種有 reasoning 能力的模型，在給足 scaffolding 的情況下能不能直接解決更多問題。這些 scaffolding 包括：清楚的視覺 context、一份作業流程、受限的物件、結構化的輸出格式，以及能指出結果在哪裡壞掉的 eval。

使用情境是從空的平面圖產生辦公室配置。給它一張空的平面圖、一份辦公室配置 SOP 和一份家具目錄，GPT-5.5 會產出結構化的配置 spec：辨識空間、推斷房間用途、套用數值規則、擺放家具，並記錄它對原始圖面所做的假設。這個想法也來自真實的辦公室問題：我們紐約辦公室的人數成長得很快，「能不能在哪裡再塞幾張桌子？」開始變成一個很適合問模型的問題。

我們選辦公室平面圖當測試案例，因為失敗很容易檢查。GPT-5.5 拿到空的平面圖、可重複使用的配置 SOP 和一小份家具目錄，然後產出結構化的配置 spec。這份 spec 會辨識空間、推斷房間用途、套用數值規則、擺放家具，並記錄對原圖的假設。

整個實驗圍繞著評估這份 spec，而不是只看渲染出來的圖。每次執行都可以檢查機械上的有效性、語意是否有依據，以及有人工參考答案時跟它的相似度。這樣可以把視覺 mockup 會混在一起的失敗模式分開：幾何無效、房間解讀錯誤、家具配置不對、對原圖的依據薄弱。

## 任務設定：從平面圖到配置 spec

生成這一步把問題拆成三個輸入：1) 平面圖的視覺證據，2) SOP 的規劃政策，3) 家具目錄的物件尺寸。

可見的證據是空的平面圖 `empty.png`。模型要從圖本身推斷牆、門、樓梯、廁所、隔間、開口和可用的房間形狀。生成期間它看不到填好家具的參考圖或 gold JSON，這些留到評估時才用。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/grounded_spatial_figure_1_empty_vs_reference.png" alt="Figure 1: empty floorplan and hand-filled reference" width="90%">
</p>
<p align="center"><em>圖 1：生成時模型只看得到空的平面圖，填好的參考圖留給評估和質性比較。</em></p>

`constraints.json` 裡可重複使用的 SOP 定義了規劃政策。它描述配置應該包含哪些功能空間、這些空間需要的主要家具，以及規劃要盡量滿足的空間規則。

```json
{
  "profile_id": "office_furniture_sop_v1",
  "client_brief": {
    "required_spaces": [
      { "semantic_type": "open_office", "count": 2 },
      { "semantic_type": "reception", "count": 1 },
      { "semantic_type": "executive_suite", "count": 1 }
    ],
    "required_objects": [
      { "object_type": "reception_desk", "count": 1, "preferred_semantic_type": "reception" },
      { "object_type": "executive_desk", "count": 1, "preferred_semantic_type": "executive_suite" },
      { "object_type": "guest_chair", "count": 3, "preferred_semantic_type": "executive_suite" }
    ]
  },
  "spatial_constraints": [
    {
      "id": "primary_circulation_clearance",
      "enforcement": "hard",
      "primary_path_min_clearance_in": 48,
      "cluster_spacing_min_in": 42
    },
    {
      "id": "workstation_cluster_size",
      "enforcement": "soft",
      "allowed_cluster_sizes": [4, 6]
    },
    {
      "id": "storage_ratio",
      "enforcement": "soft",
      "rule": "Prefer roughly 1 storage cabinet for every 8 open-office workstations, rounded up."
    }
  ]
}
```
家具目錄提供物件尺寸。它把 `workstation`、`reception_desk`、`storage_cabinet` 這類標籤變成有尺寸和簡單擺放先驗的物件，所以模型得推理物件到底放不放得下。

```json
{
  "workstation": {
    "dimensions_in": [60, 30],
    "rules": ["keep grouped", "orient for circulation"]
  },
  "reception_desk": {
    "dimensions_in": [72, 30],
    "rules": ["place near entrance", "keep visitor path clear"]
  },
  "executive_desk": {
    "dimensions_in": [84, 36],
    "rules": ["prefer private enclosed room", "keep guest-facing approach clear"]
  },
  "guest_chair": {
    "dimensions_in": [28, 28],
    "rules": ["use for visitor seating", "keep balanced around executive or meeting furniture"]
  },
  "storage_cabinet": {
    "dimensions_in": [48, 20],
    "rules": ["prefer wall adjacency", "avoid circulation"]
  }
}
```
這樣的分離讓整個設定可以重複使用。新的平面圖只改幾何，SOP 和目錄不變，任務就更偏向空間推理，而不是針對個案的 prompt 調整。

目前的實作裡，生成有兩個 reasoning 階段。首先 GPT-5.5 從圖像中確立房間的語意，接著根據這份語意房間規劃和固定的主要家具需求，產生最終配置。這個拆法是 hillclimb 得來的：辨識房間配置和擺放家具有關，但並不是同一種推理問題。

主要輸出是 `raw_layout.json`。它是機器可檢查的空間規格，在渲染之前就能驗證、修復、編譯和檢視。這份 spec 包含可行性判斷、假設、未滿足的限制、語意區域、家具擺放和動線路徑。每筆擺放包含物件類型、中心座標、尺寸、正交旋轉、所屬區域、選用的分組、理由和信心程度。

所有座標和尺寸的單位是英寸，旋轉角度是離散的：`0`、`90`、`180` 或 `270`。這樣輸出貼近家具規劃的實務，也比較容易用幾何檢查來驗證。

渲染是下游步驟。GPT Image 2 可以用原始平面圖加上從結構化 spec 推導的指示，產生一張供視覺檢查的成品。渲染讓人更容易審閱規劃，但真正的依據是 spec。評估維持 spec 優先，因為有效性是幾何問題。

## Eval 設定

生成和評估是分開的兩個階段。GPT-5.5 先產出候選的配置 spec `raw_layout.json`，然後 Promptfoo 對這份存好的 spec 跑 eval。設定檔用的是 echo provider，因為配置已經生成好了，Promptfoo 不負責產生規劃，只負責協調對候選 JSON 的各項檢查。

每個候選會經過三種檢查：

1. **validity，確定性的硬性關卡。**
這是唯一的 pass/fail 關卡。它檢查生成的配置對照 constraints.json 和原始平面圖，在機械上是否有效。檢查涵蓋硬性的空間限制，例如跟原圖牆壁碰撞、物件重疊、擺放超出宣告的區域，以及其他會讓規劃無法使用的幾何錯誤，不管渲染看起來多合理。

2. **grounded_program，語意依據分數。**
這個分數結合確定性的房間覆蓋檢查，以及 GPT-5.5 的判斷：配置是否忠於可見的平面圖和需求說明。它看有沒有辨識出對的房間類型、主要空間有沒有適當地擺放家具，以及分區的解讀是不是有圖面依據而不是憑空捏造。這是分數而不是硬性拒絕的規則，因為語意解讀很難濃縮成一個確定性的檢查。

3. **reference_similarity，確定性的 gold-spec 分數。**
有 gold JSON spec 的時候，這個檢查用區域一致程度、家具配置一致程度和容許誤差的擺放接近程度，去比較生成的配置和參考答案。這提供類似 benchmark 的訊號，但不會讓人工參考答案變成唯一可接受的配置。拿來比較候選很有用，但不是硬性關卡。

每次執行的輸出會寫到 `eval_results.json`，並顯示在 trace viewer 裡。viewer 刻意做得很簡單，但讓評估迴圈變得具體：每次執行都在同一個地方顯示案例、模型、reasoning 設定、渲染狀態、validity 結果、語意依據分數和參考相似度分數。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/grounded_spatial_failed_run_viewer.png" alt="Example failed run in the trace viewer" width="90%">
</p>
<p align="center"><em>viewer 裡顯示的一次失敗執行範例。</em></p>

這個候選沒通過硬性的 `validity` 關卡，因為主管辦公桌和訪客椅跟原圖的牆或隔間線條重疊。它仍然拿到 `grounded_program` 和 `reference_similarity` 各自的軟性分數，所以比單一的 pass/fail 標籤更容易診斷失敗原因。

這種分離是關鍵的設計選擇，因為一次執行可能機械上無效，但語意上仍然有參考價值。它可能通過硬性幾何檢查，卻選錯房間配置；也可能家具數量跟 gold spec 很像，但擺放或分區偏掉了。把這些訊號分開，我們才能 hillclimb 整個系統：依照是哪一層失敗，去改 prompt、修訂 spec、加 validator、修擺放問題，或蒐集更好的 gold 參考答案。

## 結果：挑選的 hillclimb 檢查點

最有用的幾次執行不是一連串乾淨的漸進改進，而是各自暴露 workflow 不同問題的檢查點。規律是：指標錯、拆解錯、契約錯，然後才找到模型推理和確定性幾何之間更好的分工。

### Run 1：有效的配置暴露了錯誤的指標

一個早期案例通過了硬性檢查，也產出連貫的辦公室規劃。GPT-5.5 選了東側的大房間當開放辦公區，把中央大廳當接待區，用北側較小的房間當主管室。在這個解讀下，配置內部是一致的。


<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/grounded_spatial_run_1_valid_layout.png" alt="Run 1: empty floorplan, filled floorplan, and rendered floorplan" width="90%">
</p>
<p align="center"><em>生成的規劃看起來合理，但跟人工參考答案的視覺相似度，不該是主要指標。</em></p>

問題出在評估目標。這次執行的 reference 分數只有 `0.0644`，因為我們當時還在用家具 mask 的 IoU 去比對人工圖。這讓分數對像素層級的重疊太敏感，即使生成的是一份連貫的替代配置也一樣。

JSON 比渲染圖更容易看出模型的解讀：

```json
{
  "assumptions": [
    "The broad double doors at the south edge of the central lobby are treated as the primary public entrance.",
    "The large east room is assigned as the usable open-office zone.",
    "Other unlabeled large rooms are left unprogrammed rather than classified as open-office because the source image provides no room labels."
  ],
  "zones": [
    {
      "id": "zone_open_office_east",
      "label": "East open-office room used for workstation density calculation"
    }
  ]
}
```
這讓專案轉向 spec 優先的評估。渲染圖對檢查仍然有用，但主要的評估對象必須是結構化的規劃：模型選了哪些區域、指派了什麼房間配置，以及配置在機械上是否有效。

### Run 2：合理的配置暴露了錯誤的拆解

在比較複雜的辦公室平面圖上，生成的家具規劃看起來合理，但房間解讀是錯的。接待區跑到錯的地方，南側的私人辦公室區域沒有保留，候選的房間拆解跟參考配置有實質上的差異。


<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/grounded_spatial_run_2_wrong_decomposition.png" alt="Run 2: empty floorplan, filled floorplan, and rendered floorplan" width="90%">
</p>
<p align="center"><em>看得到的家具規劃很合理，但房間配置的解讀在擺放之前就已經偏掉了。</em></p>

這改變了 workflow。我們把任務拆成兩個階段，也就是兩次 LLM call：先從圖像確立房間語意，再根據這份語意房間規劃和固定的主要家具需求產生家具配置。我們也加了明確的客戶需求說明（client brief），讓模型不必光靠幾何去推斷完整的業務需求。

### Run 8：塞太滿的配置暴露了錯誤的契約

拆成兩階段之後，workflow 變得比較容易檢查，但短暫地變差了，而且是有用的那種變差。確定性的家具配置邏輯產出了 38 個工作站的規劃，因為需求被太廣泛地套用到模糊的 `other` 房間。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/grounded_spatial_run_8_overfilled_layout.png" alt="Run 8: overfilled rendered floorplan" width="75%">
</p>
<p align="center"><em>過度指定的家具配置契約把工作站需求套得太廣，導致不切實際的 38 個工作站規劃。</em></p>

這暴露出過度指定的問題。模型不再只是在解空間任務，benchmark 開始獎勵「重現隱藏的配置邏輯」。解法是把語意房間的確立和家具配置契約分開，加上 brief 與空間的綁定，並減少對 `other` 這類寬泛標籤的依賴。

目標變得更窄：主要家具維持確定性，但保留足夠的設計自由度，讓有效的替代配置也能成立。

### Run 15：一個有效的端到端案例釐清了分工

在後期最強的案例裡，這次執行達到了物理上的有效性，雖然跟參考的房間配置還有一些語意上的分歧。候選在模型修復一次區域邊界問題之後達到 `completed_valid`，而剩下的桌子和收納櫃碰撞，由確定性幾何透過修復流程、正交旋轉搜尋、局部修復和一個小型的聯合重新排列後備方案清掉。

<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/grounded_spatial_run_15_trace_viewer.png" alt="Run 15: valid rendered floorplan and trace viewer" width="90%">
</p>
<p align="center"><em>較難的辦公大樓案例中，第一個物理上有效的結果。GPT-5.5 產出有依據的配置規劃，確定性修復清掉最後的幾何錯誤。</em></p>

這釐清了系統的邊界。GPT-5.5 最有用的是有依據的語意決策：辨識房間角色、指派房間配置、提出結構化的規劃。確定性程式碼比較適合便宜的幾何清理：邊界檢查、物件重疊、原圖牆壁碰撞、旋轉和重新排列。

這就成了 hillclimb 的做法。模型提出有依據的配置 spec。eval 堆疊判斷失敗是語意層、機械層還是參考層。確定性程式碼修復不該再多花一次模型呼叫的部分。渲染對檢查仍然有用，但進度是在 spec 層級衡量的。

## 重點結論

前沿模型確實改變了有依據的空間規劃 workflow 的可行範圍。它們可以讀懂簡略的平面圖、推斷房間配置、套用數值配置規則、輸出結構化 spec、揭露假設，並回應 eval 回饋，而不需要針對這個配置問題做專門的 fine-tuning。

要求 GPT-5.5 輸出機器可檢查的配置 spec，系統就把空間推理變成可檢視的成品：房間角色、假設、限制、擺放和修復點，在渲染之前都已經明確呈現。

這個表示方式也釐清了正確的分工。GPT-5.5 負責高層次的解讀：讀懂模糊的幾何、指派房間配置、提出連貫的配置。確定性元件負責必須精確的部分，包括邊界檢查、碰撞偵測、間距規則和局部修復。所以模型的推理不被當成會自我驗證的東西，而是由周邊系統來約束、檢查和改進。

剩下的挑戰是語意依據。最難的平面圖不是沒有有效解的，而是有好幾個合理解的。這時成敗取決於系統有沒有辨識出圖面想要的配置，而不只是能不能產出物理上有效的排列。未來的進展要靠更廣的 eval 覆蓋、更強的原圖幾何擷取，以及視覺區域和語意角色之間更精確的對應。更大的結論是，GPT-5.5 可以把更多空間規劃的工作移進通用的多模態推理。

## 重點整理

- 把輸入拆成視覺證據、規劃政策、物件尺寸，新平面圖只換幾何，SOP 和目錄不動，才能重複使用。
- 讓模型輸出機器可檢查的 spec，而不是只看渲染圖，失敗才能被定位到語意、機械或參考層。
- eval 要分層：validity 是唯一的硬性關卡，語意依據和參考相似度只是分數，三者分開看才能 hillclimb。
- 指標、拆解、契約都可能是錯的，一次看起來合理的結果不代表系統設計對了。
- 模型負責語意判斷，確定性程式碼負責精確的幾何檢查與修復。

## 練習

1. 照頁面上 `raw_layout.json` 的欄位（中心座標、尺寸、旋轉），手寫一個小函式檢查兩個物件是否重疊，並測試旋轉 `90` 度時尺寸要怎麼對調。
2. 把 validity 檢查裡「擺放在宣告區域內」的規則改成容許一點誤差（例如 2 英寸），比較哪些原本失敗的候選會變成通過，想想這樣合不合理。
3. 仿照三種 eval 的做法，替自己的一個結構化輸出任務（例如行程表或資料表 schema）設計一個硬性關卡加兩個軟性分數，並寫出各自的判斷程式。
