---
translated: true
source: articles/gpt-oss-safeguard-guide.md
---
# gpt-oss-safeguard 使用指南

> 原文：[articles/gpt-oss-safeguard-guide.md](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss-safeguard-guide.md)



## 這篇在做什麼

這是 ROOST 和 OpenAI 一起寫的指南，教你怎麼寫 policy prompt，讓 gpt-oss-safeguard 把 reasoning 能力發揮出來，怎麼挑 policy 長度，還有怎麼把它的輸出接進 Trust & Safety 系統。前半在講怎麼用 Transformers、Ollama、LM Studio、vLLM 把模型跑起來。

## 學完你會

- 用 vLLM、Ollama 或 LM Studio 在本機或伺服器跑起 gpt-oss-safeguard，並用 `reasoning_effort` 控制推理深度。
- 照 Instruction、Definitions、Criteria、Examples 四段結構寫出一份 policy prompt。
- 依需求選二元、帶 policy 標籤、或帶 rationale 的輸出格式。

## 開跑前

- 要有能跑 gpt-oss 20B 或 120B 的硬體（GPU 或 Ollama、LM Studio 支援的本機環境）。


## 簡介與總覽

ROOST 和 OpenAI 準備了這份指南，說明怎麼寫 policy prompt 來發揮 [gpt-oss-safeguard](https://github.com/openai/gpt-oss-safeguard) 的 reasoning 能力、怎麼選擇適合深入分析的 policy 長度，以及怎麼把 oss-safeguard 的 reasoning 輸出整合進正式環境的 Trust & Safety 系統。

### 什麼是 gpt-oss-safeguard？

gpt-oss-safeguard 是第一個 open weight 的 reasoning model，專門針對安全分類任務訓練，可以依照可自訂的 policy 來分類文字內容。它是 [gpt-oss](https://openai.com/index/introducing-gpt-oss/) 的 fine-tuned 版本，設計成遵循你提供的明文 policy。這就是所謂的 **bring-your-own-policy** Trust & Safety AI：分類決策依你自己的分類法、定義和門檻。寫得好的 policy 能解鎖它的 reasoning 能力，讓它處理有細微差異的內容、解釋邊界案例的判斷，並依情境調整。

OpenAI 內部怎麼用 gpt-oss-safeguard 的內部版本，可以看[這裡](https://openai.com/index/introducing-gpt-oss-safeguard/)。

大型語言模型可以從兩個角度當作安全模型：

- Fine-tuned safety model：從通用 reasoning model（像 gpt-oss）出發，訓練成在使用者互動中安全地回應。
- Prebaked safety model（像 ShieldGemma、LlamaGuard、RoGuard 等）：內建「什麼算不安全」的定義和固定的 policy 分類。

gpt-oss-safeguard 是為 Trust & Safety 工作流程特製的 policy-following model，能可靠地解讀並執行**你自己寫的標準，還能告訴你為什麼這樣判斷**。它背後的 reasoning 很適合整合進重視可稽核性和客製化的大型安全系統。

### 怎麼使用 gpt-oss-safeguard

跟 [gpt-oss 系列模型](https://openai.com/open-models/)一樣，這是 open weight 的開源模型，可以在本機跑或整合進你自己的基礎設施。它設計成搭配 [harmony response format](https://github.com/openai/harmony) 使用。Harmony 是結構化的 prompt 介面，讓 gpt-oss-safeguard 能用上完整的 reasoning 能力，並確保輸出格式一致。

gpt-oss 系列（包含 gpt-oss-safeguard）可以在伺服器上用這些方式跑：

- [vLLM](https://docs.vllm.ai/projects/recipes/en/latest/OpenAI/GPT-OSS.html#gpt-oss-vllm-usage-guide)（適合 NVIDIA H100 這類專用 GPU）
- [HuggingFace Transformers](https://cookbook.openai.com/articles/gpt-oss/run-locally-lmstudio)（適合消費級 GPU）
- [Google Colab](https://cookbook.openai.com/articles/gpt-oss/run-colab)

本機則可以用：

- [LM Studio](https://cookbook.openai.com/articles/gpt-oss/run-locally-lmstudio)
- [Ollama](https://cookbook.openai.com/articles/gpt-oss/run-locally-ollama)

### 誰適合用 gpt-oss-safeguard？

gpt-oss-safeguard 是給需要即時情境判斷、又要大規模自動化的人，包括：

- **ML/AI 工程師**：做 Trust & Safety 系統，需要彈性的內容審核
- **Trust & Safety 工程師**：建置或改善內容審核、Trust & Safety、平台誠信 pipeline
- **Technical Program Manager**：主導內容安全專案
- **開發者**：做需要依情境、依 policy 審核內容的專案或應用
- **Policy 制定者**：定義組織能接受什麼，想測試 policy 界線、產生範例、評估內容

Safety-tuned model 在提示清楚、有結構時，內容審核表現很好。這份指南整理了在正式環境部署審核系統的心得，重點是 prompt 結構、輸出格式和長度最佳化。

### 用 HuggingFace Transformers 跑 gpt-oss-safeguard

Hugging Face 的 Transformers 函式庫可以彈性地在本機或伺服器載入、執行大型語言模型。[這份指南](https://cookbook.openai.com/articles/gpt-oss/run-transformers)帶你用 Transformers 跑 [OpenAI gpt-oss](https://huggingface.co/openai/gpt-oss-20b) 模型，可以用高階 pipeline，也可以用低階的 generate 直接餵 raw token ID。跟 server 互動最簡單的方式是 transformers chat CLI

```bash
transformers chat localhost:8000 --model-name-or-path openai/gpt-oss-safeguard-20b
```

或者用 cURL 送 HTTP request，例如

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-safeguard-20b",
    "stream": true,
    "messages": [
      { "role": "system", "content": "<your policy>" },
      { "role": "user", "content": "<user content to verify>" }
    ]
  }'


```

其他用法，像是把 transformers serve 接到 Cursor 等工具，寫在[文件](https://huggingface.co/docs/transformers/main/serving)裡。

### 用 Ollama 跑 gpt-oss-safeguard

[Ollama](https://ollama.com/download) 直接支援 gpt-oss-safeguard 20B 和 120B。下面的指令會自動下載模型並在你的裝置上執行。

#### gpt-oss-safeguard:20b

```bash
ollama run gpt-oss-safeguard:20b
```

#### gpt-oss-safeguard:120b

```bash
ollama run gpt-oss-safeguard:120b
```

Ollama 支援 [OpenAI API](https://docs.ollama.com/api/openai-compatibility)、[Ollama 自己的 API](https://docs.ollama.com/api)、[Python](https://github.com/ollama/ollama-python) 和 [JavaScript](https://github.com/ollama/ollama-js) SDK，可以拿來做用 gpt-oss-safeguard 的應用或工具。更多請看 [Ollama 文件](https://docs.ollama.com/)。

### 用 LM Studio 跑 gpt-oss-safeguard

你也可以用 [LM Studio](https://lmstudio.ai/) 在本機跑模型，並使用相容 [OpenAI Chat Completions](https://lmstudio.ai/docs/developer/openai-compat/chat-completions) 和 [Responses API](https://lmstudio.ai/docs/developer/openai-compat/responses) 的 API。到 [LM Studio 的 gpt-oss-safeguard 頁面](https://lmstudio.ai/models/gpt-oss-safeguard)，或執行下面的指令下載對應模型：

#### gpt-oss-safeguard-20b

```bash
lms get openai/gpt-oss-safeguard-20b
```

#### gpt-oss-safeguard-120b

```bash
lms get openai/gpt-oss-safeguard-120b
```

### 用 vLLM 跑 gpt-oss-safeguard

[vLLM](https://docs.vllm.ai/) 建議用 [uv](https://docs.astral.sh/uv/) 管 Python 相依套件。下面的指令會自動下載模型並啟動 server。

```shell
uv pip install vllm==0.10.2 --torch-backend=auto

vllm serve openai/gpt-oss-safeguard-120b
```

[更多 gpt-oss 搭配 vLLM 的用法。](https://docs.vllm.ai/projects/recipes/en/latest/OpenAI/GPT-OSS.html#gpt-oss-vllm-usage-guide)

### 了解 Harmony Response Format

gpt-oss-safeguard 用 [harmony prompt format](https://cookbook.openai.com/articles/openai-harmony) 產生結構化輸出並提供 reasoning。這對 Trust & Safety 很關鍵，因為你需要了解並稽核某個決定或分類是怎麼來的。透過 harmony，oss-safeguard 把回應分成兩部分：

1. **Reasoning channel：** 模型在這裡對照 policy 推理、考慮邊界案例、說明邏輯
2. **Output channel：** 你指定格式的分類結果

透過 harmony，你可以在 system message 設定 `reasoning_effort` 參數為 `low`、`medium` 或 `high` 來控制推理深度，沒設定的話預設是 `medium`。Reasoning effort 越高，oss-safeguard 會考慮越多因素、追蹤多個 policy 段落，也更能處理規則之間複雜的互動。Effort 越低，單純的分類回得越快。

如果你用 [**vLLM**](https://docs.vllm.ai/en/latest/)（大多數人建議用這個）或其他提供 chat message 輸入的推論方案，只要把請求寫成 [chat messages](https://docs.vllm.ai/en/v0.7.0/getting_started/examples/chat.html)，harmony format 就會自動套用：

- **System message：** 你的 policy prompt（要控制 reasoning effort 的話，在 system message 裡加 Reasoning: high 之類的字樣）。
- **User message：** 要分類的內容。

## oss-safeguard 怎麼使用 Policy Prompt

oss-safeguard 把你寫的 policy 當作判斷的依據。多數模型給的是依訓練特徵算出的信心分數，policy 一改就得重新訓練；oss-safeguard 則是在你提供的分類法範圍內，靠 reasoning 做決定。這讓 T\&S 團隊可以把它當成 policy 對齊的 reasoning 層，放進現有的審核或合規系統。也代表你可以馬上更新或測試新 policy，不用重新訓練整個模型。

## 為 gpt-oss-safeguard 寫有效的 Policy Prompt

oss-safeguard 在 policy 像 Trust & Safety policy 手冊而不是一篇文章時表現最好。如果你已經有一套 policy，基礎就很好。用標題和清楚的分類，模型才能有效率地查找定義。寫過給團隊用的 policy 的話，這會很熟悉。

### 了解 Policy Prompting

Policy prompt 定義模型行為的操作界線。就像寫給人工審核員的內容或平台 policy 一樣，給 oss-safeguard 的 policy 要清楚說明什麼算違規、什麼被允許，以及怎麼把這個差異轉成能接進 Trust & Safety 系統其他部分的決定。

有效的 policy prompt 會區分相似的內容類型、抓出隱晦、暗語或間接的違規，並避免邊界案例的誤判。可以想成是把 policy 文件和訓練範例合在一起。

### Policy Prompt 的結構

Policy prompt 應該有四個獨立的段落。

1. **Instruction：** 模型必須做什麼、該怎麼回答。
2. **Definitions：** 關鍵用詞的簡明解釋。
3. **Criteria：** 違規與不違規內容的區別。
4. **Examples：** 貼近判斷界線的簡短具體範例。要同時給想分類的和不想分類的範例，這很重要

oss-safeguard 是針對結構化審核調校的，所以它期待明確的回答方式指示。Policy prompt 如果遵循一致的模式，並包含預期的回應和輸出格式，表現通常比較好。Harmony format 的結構化 channel 讓 oss-safeguard 先針對這些段落推理，最後只輸出最終標籤：

```markdown
# Policy Name

## INSTRUCTIONS

Describe what oss-safeguard should do and how to respond.

## DEFINITIONS

Clarify key terms and context.

## VIOLATES (1)

Describe behaviors or content that should be flagged.

## SAFE (0)

Describe content that should not be flagged.

## EXAMPLES

Provide 4–6 short examples labeled 0 or 1.

Content: [INPUT]
Answer (0 or 1):
```

為了降低誤判或混淆的機率，避免用「generally」「usually」這類字眼。有模糊的情況，就加一條轉人工審核的升級路徑，這對地區或語言差異特別有幫助。

要明確寫出優先順序，讓模型知道規則衝突時哪條優先。如果同時違反多條 policy，要定義哪條為主。

### 選擇適當的 Policy 長度

Policy 長度是控制 gpt-oss-safeguard 對規則推理多深的關鍵。越長的 policy 越能補足細節、處理複雜案例，但可能影響輸出和回應。用 harmony response format 時，模型處理較長的 policy 會比較可靠，因為推理發生在隱藏的 analysis channel，不是在看得到的最終輸出裡。
用 [https://platform.openai.com/tokenizer](https://platform.openai.com/tokenizer) 來看你的 prompt 有多長。**gpt-oss-safeguard 在約 10,000 token 的 policy 下也能給出合理的輸出，但早期測試顯示最佳範圍是 400-600 token**。沒有一體適用的做法，要自己實驗看哪種最好。把 policy 長度想成「context 預算」：太短，模型缺細節；太長，模型可能搞混。這跟寫給人看的 policy 很像。同樣地，要留足夠的 output token 給模型產生回應。因為模型會做 reasoning，應該留很多 output token 的空間，最好不要限制最大 output token，讓模型有足夠空間推理 policy。如果想限制推理時間，改把 reasoning effort 設成 low。

如果 policy 比較長、有多個類別，可以考慮先把每個 policy 壓縮到 300–600 token（包含定義、禁止的類別，以及違規和不違規各 1-2 個範例）。

oss-safeguard 也能同時評估多個 policy，只要全部放進 prompt。我們發現多加 policy 會造成小但明顯的準確度下降，所以如果用 oss-safeguard 處理多個傷害領域，建議實驗增減 policy。

## 設計可靠的輸出指示

要讓 gpt-oss-safeguard 的回應一致，需要明確、字面的輸出指示。每份 policy prompt 都該清楚說明模型必須怎麼回應，並示範正確和錯誤的格式。輸出指示決定 gpt-oss-safeguard 如何傳達最終決定，也決定輸出能不能被信任。因為 gpt-oss-safeguard 在 harmony response format 下運作，所有輸出指示都必須：

1. **明確定義輸出格式：** 精確指定模型要回傳什麼（例如 `0`/`1`、JSON 物件、類別標籤清單）。
2. **適用時包含 policy 引用：** 如果你的流程依類別或規則追蹤處置，要求模型回傳那個欄位；單純二元輸出可以省略。
3. **在整份 policy 中重複強調：** 至少在接近開頭（「INSTRUCTIONS」）重複一次輸出指示，並在接近結尾（「EXAMPLES」之前）再重複一次，讓模型推理時更守規定。

### 二元回應

二元輸出把 gpt-oss-safeguard 的推理限縮成單純的是非判斷。速度比理解決策原因重要時用這個，但要知道這樣沒有用到 gpt-oss-safeguard 最核心的 reasoning 優勢。

```markdown
Return exactly one character: 0 or 1.
Do not include any explanation or punctuation.

0 = Content does NOT violate this policy.
1 = Content violates this policy.
```

### 引用 Policy 的輸出

類別標籤會促使 gpt-oss-safeguard 推理該用 policy 的哪個段落，但不要求詳細解釋原因。這種格式有基本的推理透明度，輸出又簡短。

```
If the content violates this policy, return:
{"violation": 1, "policy_category": "<category_or_rule_id>"}

If the content does NOT violate this policy, return:
{"violation": 0, "policy_category": null}

Example:
{"violation": 1, "policy_category": "H2.f"}
```

### 附上 Rationale

gpt-oss-safeguard 最強的功能之一是思考和推理。模型不只要分類內容，還要沿著你的 policy 追蹤邏輯、找出適用的具體規則，並說明原因。要求 rationale 時，gpt-oss-safeguard 會推理得更仔細：必須考慮多個 policy 段落、評估它們如何互動，並建構合理的解釋。這種更深的推理常能抓到簡單輸出格式漏掉的細節。這種輸出格式最能發揮 gpt-oss-safeguard 的 reasoning 能力。

請模型先決定，再簡短說明。要求簡短、非逐步的 rationale（2–4 個要點或 1–2 句），並考慮要求引用 policy（規則 ID 或段落），讓模型為它的思考和決定提供依據。

```json
{
  "violation": 1,
  "policy_category": "H2.f",
  "rule_ids": ["H2.d", "H2.f"],
  "confidence": "high",
  "rationale": "Content compares a protected class to animals, which is dehumanizing."
}
```

## 把 gpt-oss-safeguard 用在 Trust & Safety

因為 gpt-oss-safeguard 解讀的是寫下來的規則而不是固定類別，它只需要很少的工程成本，就能適應不同的產品、法規和社群情境。

gpt-oss-safeguard 設計上能融入 Trust & Safety 團隊的基礎設施。不過因為它可能比其他 classifier 更耗時、更耗運算，建議先對送進 gpt-oss-safeguard 的內容做 pre-filter。[OpenAI 會先用小型、高 recall 的 classifier 判斷內容是否和優先風險領域相關，再交給 gpt-oss-safeguard 評估。](https://openai.com/index/introducing-gpt-oss-safeguard/) 決定在 T\&S stack 的哪裡、什麼時候整合 oss-safeguard 時，主要考慮兩件事：

1. 傳統 classifier 的延遲比較低，取樣成本也比 gpt-oss-safeguard 低
2. 用數千筆範例訓練的傳統 classifier，在某個任務上很可能表現得比 gpt-oss-safeguard 好

### 自動化內容分類

用 gpt-oss-safeguard 對貼文、訊息或媒體 metadata 標記是否違反 policy。它的 policy reasoning 支援有細微差異的分類，做決定時能判斷情境細節。gpt-oss-safeguard 可以整合到：

- 即時 ingestion pipeline
- 審核佇列和審核主控台
- 降低排序或過濾系統

### T\&S Assistant

gpt-oss-safeguard 的 reasoning 能力，特別適合用在 Trust & Safety 工作流程的自動分流。傳統 classifier 只給標籤和信心分數，gpt-oss-safeguard 則像個 reasoning agent：評估內容、解釋決定、引用具體 policy 規則，並挑出需要人工判斷的案例。這可以減輕人工審核員的負擔，同時提高對自動化決策的信任和透明度。

### Policy 測試

在上線新的或修訂過的 policy 之前，先用 gpt-oss-safeguard 跑一遍，模擬內容會被怎麼標記。這有助於找出過於寬泛的定義、不清楚的範例和邊界案例。

### Policy 實驗

gpt-oss-safeguard 的 bring-your-own-policy 設計，讓 policy 團隊可以直接在正式環境 A/B 測試不同的定義，不用重新訓練模型。

## 現成的青少年安全 Policy

像 gpt-oss-safeguard 這樣的安全 classifier 可以偵測有害內容，但前提是要有清楚的內容定義。實務上，開發者面臨的最大挑戰之一，是定義出能準確涵蓋青少年特有風險、又能在真實系統中一致套用的 policy。

為了解決這個問題，OpenAI 釋出了 [teen-safety-policy-pack](https://github.com/openai/teen-safety-policy-pack)，這是一組針對青少年常見風險設計的安全 policy，參考了對青少年發展差異的既有研究。這些 policy 是寫成 prompt 的結構，可以直接搭配 [gpt-oss-safeguard](https://github.com/openai/gpt-oss-safeguard) 和其他 reasoning model 使用，讓開發者更容易在系統中套用一致的安全標準。

初版涵蓋的 policy 有：

- 圖像式暴力內容
- 圖像式性內容
- 有害的身體理想與行為
- 危險活動與挑戰
- 浪漫或暴力的角色扮演
- 年齡限制的商品與服務

這些 policy 可以用在即時內容過濾，也能用在使用者產生內容的離線分析。

### 危險內容 Policy 範例

```markdown
# Dangerous Content Policy (#DC)

## Goal

Identify dangerous activity content that is not appropriate for teenagers. Classify each example as `VALID` (allowed) or `INVALID` (dangerous content) using this policy.

This policy focuses on activities that could cause physical harm if attempted, especially viral challenges, risky stunts, unsafe experimentation, and dangerous at-home procedures.

The assistant must not encourage, prompt, instruct, simulate, or facilitate teen participation in dangerous activities, stunts, or challenges. This includes glorifying the activity, providing instructions, realistic simulations, or linking to materials needed to attempt the challenge when user intent is present.

## Definitions

- **Dangerous activities or challenges**: Activities, stunts, or online challenges that could realistically cause physical injury, poisoning, suffocation, overdose, burns, falls, or other serious harm if attempted by a teenager.
- Examples include risky viral trends such as substance misuse challenges, choking challenges, extreme stunts, and unsafe experimentation.
- **Facilitation**: Providing instructions, tactics, materials, preparation steps, or optimization that would enable someone to attempt a dangerous activity.
- **Glorification**: Portraying a dangerous activity as exciting, admirable, funny, or desirable in ways that could encourage imitation.
- **Realistic simulation**: Detailed descriptions or narrative walkthroughs of performing a dangerous activity that functionally model how to do it.

## Allowed Content (DC0 - Non-dangerous or Safety-oriented)

Content that discourages risk, provides safety guidance, or discusses challenges critically or educationally without enough detail to mimic.

Examples:

- **DC0.a Media literacy**: "Why do viral internet challenges sometimes lead to injuries?"; "Viral internet challenges can lead to injuries because they often prioritize attention and shock value over safety."
- **DC0.b Safety framing**: "Why is the Benadryl Challenge dangerous?"; "The Benadryl Challenge is dangerous because it involves taking more medication than recommended, which can cause serious health effects. Medications should only be used as directed."
- **DC0.c Refusal or discouragement**: "That challenge can be very dangerous and isn't something I can help with."
- **DC0.d News reporting without replicable detail**: "Summarize the news about injuries caused by viral TikTok challenges."; "Recent reports have highlighted multiple cases where teens were injured after attempting viral TikTok challenges. Health officials and educators have raised concerns about the risks."
- **DC0.e Safety advice**: "If someone took too much medication, they should contact poison control or seek medical help."

Output: `VALID`

## Promotion or Glorification of Dangerous Challenges (DC1 - Promotion)

Content that celebrates, encourages, or positively frames participation in dangerous activities without giving explicit instructions.

Examples:

- **DC1.a Glorification**: "The blackout challenge is wild, people pass out and wake up laughing."
- **DC1.b Encouragement**: "You should totally try the Benadryl challenge, it's trending everywhere."
- **DC1.c Social pressure**: "Everyone at school is doing it, don't be the only one who's scared."
- **DC1.d Competitive framing**: "See how long you can hold your breath before you pass out. Compare with your friends."

Output: `INVALID`

## Facilitating Dangerous Activities (DC2 - Facilitation or instruction)

Content that enables or instructs someone to perform dangerous challenges or stunts.

Examples:

- **DC2.a Instructions**: "Take 10 Benadryl tablets and wait for the hallucinations to start."
- **DC2.b Preparation guidance**: "To do the blackout challenge safely, sit down first and breathe rapidly."
- **DC2.c Optimization**: "The trick to the choking challenge is cutting off oxygen just long enough to pass out."
- **DC2.d Material sourcing**: "You can buy Benadryl cheaply at this pharmacy before trying the challenge."
- **DC2.e Realistic simulation**: "First you hold your breath, then your friend presses on your chest until you pass out."
- **DC2.f Challenge escalation**: "Make it more extreme." or "How do I last longer?"

Output: `INVALID`

## Dangerous At-Home Procedures (DC3 - Facilitation or instruction)

Content that enables or instructs teenagers to perform medical, cosmetic, or body-modification procedures at home without professional supervision.

These activities may appear common online but can cause infection, nerve damage, bleeding, poisoning, burns, or other serious harm when attempted by minors without trained supervision.

Examples:

- **DC3.a DIY piercing instructions**: "You can pierce your ear at home by sterilizing a needle and pushing it through the lobe."
- **DC3.b Preparation guidance**: "To pierce your nose yourself, numb it with ice and mark the spot before inserting the needle."
- **DC3.c Optimization tips**: "Use a hollow needle instead of a safety pin so the piercing heals faster."
- **DC3.d Material sourcing**: "Buy a piercing kit online and do the piercing yourself in the bathroom mirror."
- **DC3.e Other at-home procedures**: "You can remove a mole yourself with dental floss or a razor blade."

Output: `INVALID`

## Label Format

Each item gets one label indicating the presence and type of dangerous content.

- `DC0`: Allowed or safety-oriented discussion.
- `DC1`: Promotion or glorification.
- `DC2`: Facilitation, instruction, sourcing, or realistic simulation of dangerous activities.
- `DC3`: Dangerous at-home procedures.

Examples:

- "Why is the Benadryl challenge dangerous?" -> `DC0`
- "The choking challenge is hilarious to watch." -> `DC1`
- "Take a bunch of Benadryl pills to hallucinate." -> `DC2`
- "Where can I buy Benadryl to try the challenge?" -> `DC2`
- "Where can I buy Benadryl?" -> `DC0`
- "It's technically possible to pierce an ear with a needle, but here are the safety-first steps you must follow." -> `DC3`

## Ambiguity and Escalation

- If the user shows clear intent to attempt a dangerous challenge, treat enabling responses as `DC2`.
- If a response celebrates or encourages participation without instructions, classify it as `DC1`.
- If the content overlaps with self-harm, substance misuse, or criminal activity, escalate to the relevant policy domain.
- Educational or safety-focused discussion of dangerous trends remains `DC0`.
```

## 整合 gpt-oss-safeguard 與 ROOST 的工具

### Osprey

[Osprey](https://github.com/roostorg/osprey) 是 ROOST 的開源規則引擎和調查框架。它依可設定的邏輯樹評估即時事件，並派發你定義的動作。單靠規則就能處理確定性的案例（例如關鍵字比對、metadata 門檻），但遇到諷刺、暗語或微妙的 policy 界線就吃力。整合 gpt-oss-safeguard 後，Osprey 可以：

- **加入情境推理：** gpt-oss-safeguard 能解讀簡單條件處理不了的邊界案例。
- **直接執行 policy：** gpt-oss-safeguard 讀取並套用你寫的 policy 文字，確保跟人工審核一致。
- **維持可稽核性：** Osprey 會記錄是哪條規則呼叫了 gpt-oss-safeguard、回傳了哪個 policy 類別，以及模型的 rationale。
- **結合自動化與人工監督：** 確定性規則觸發快速動作；gpt-oss-safeguard 在升級到其他工具做人工審核之前先做推理

不應該每個事件都呼叫 gpt-oss-safeguard。可以把它做成 plugin，只在有需要 policy reasoning 能力的模糊案例才呼叫。

## Policy Prompt 範例

可以直接用你已經寫好的任何 policy，或是用這個範本，填入你想分類的內容。

```markdown

## Policy Definitions

### Key Terms

**[Term 1]**: [Definition]

**[Term 2]**: [Definition]

**[Term 3]**: [Definition]

## Content Classification Rules

### VIOLATES Policy (Label: 1)

Content that:

- [Violation 1]
- [Violation 2]
- [Violation 3]
- [Violation 4]
- [Violation 5]

### DOES NOT Violate Policy (Label: 0)

Content that is:

- [Acceptable 1]
- [Acceptable 2]
- [Acceptable 3]
- [Acceptable 4]
- [Acceptable 5]

## Examples

### Example 1 (Label: 1)

**Content**: "[Example]"

**Expected Response**:

### Example 2 (Label: 1)

**Content**: "[Example]"

**Expected Response**:

### Example 3 (Label: 0)

**Content**: "[Example]"

**Expected Response**:

### Example 4 (Label: 0)

**Content**: "[Example]"

**Expected Response**:
```

你也可以參考這個關於 spam 的範例 prompt：

```markdown
**Spam Policy (#SP)**
**GOAL:** Identify spam. Classify each EXAMPLE as VALID (no spam) or INVALID (spam) using this policy.

**DEFINITIONS**

- **Spam**: unsolicited, repetitive, deceptive, or low-value promotional content.

- **Bulk Messaging:** Same or similar messages sent repeatedly.

- **Unsolicited Promotion:** Promotion without user request or relationship.

- **Deceptive Spam:** Hidden or fraudulent intent (fake identity, fake offer).

- **Link Farming:** Multiple irrelevant or commercial links to drive clicks.

**Allowed Content (SP0 – Non-Spam or very low confidence signals of spam)**
Content that is useful, contextual, or non-promotional. May look spammy but could be legitimate.

- **SP0.a Useful/info request** – “How do I upload a product photo?”

- **SP0.b Personalized communication** – “Hi Sam, here is the report.”

- **SP0.c Business support** – “Can you fix my order?”

- **SP0.d Single contextual promo** – “Thanks for subscribing—here’s your welcome guide.”

- **SP0.e Generic request** – “Please respond ASAP.”

- **SP0.f Low-quality formatting** – “HeLLo CLICK here FAST.”

- **SP0.g Vague benefit statement** – “This tool changes lives.”

  **Output:** VALID either clearly non-spam or very low confidence signals content could be spam.

**Likely Spam (SP2 – Medium Confidence)**
Unsolicited promotion without deception.

- **SP2.a Cold promotion** – “Check out my Shopify course: shopcoach.biz”

- **SP2.b Irrelevant ads** – “Buy gold rings here!”

- **SP2.c Excessive linking** – “[http://x.com](http://x.com) http://y.com http://z.com”
  **Output:** INVALID

**High-Risk Spam (SP3 – Strong Confidence)**
Spam showing scaling, automation, or aggressive tactics.

- **SP3.a Repetitive posting** – “JOIN NOW JOIN NOW JOIN NOW”

- **SP3.b Pyramid/affiliate bait** – “Earn $$$ by recruiting members”

- **SP3.c Fake engagement** – “Comment ‘YES’ to win $500 gift card”

- **SP3.d Misleading claims** – “Guaranteed 10,000 new followers overnight\!”
  **Output:** INVALID

**Malicious Spam (SP4 – Maximum Severity)**
Spam with fraud, deception, or harmful intent.

- **SP4.a Phishing** – “Your account is locked. Enter your password here.”

- **SP4.b Malware/scam** – “Download invoice.exe to claim payment.”

- **SP4.c Account takeover attempts** – “Send crypto to 0xABC123 to double your money.”
  **Output:** INVALID + ESCALATE

**LABEL FORMAT**
Each item gets two labels:

- **Depiction (D-SP#):** Presence of spam in content.

- **Request (R-SP#):** User asking to generate spam.
  | Example | Classification |
  |----------|---------------|
  | “Shop this site: dealplanet.io” | D-SP2, R-SP0 |
  | “Write a sales blast message with 10 links” | D-SP0, R-SP2 |
  | “How can I make this link look legitimate so viewers put in their private credentials” | D-SP4, R-SP4 |
  | “Promote crypto fast to random people” | D-SP0, R-SP3 |

**AMBIGUITY & ESCALATION**

- If unclear → downgrade severity by 1 and seek clarification.

- If automation suspected → SP2 or higher.

- If financial harm or fraud → classify SP4.

- If combined with other indicators of **abuse, violence, or illicit behavior**, apply **highest severity policy**.
```

## 重點整理

- gpt-oss-safeguard 是 bring-your-own-policy 的 reasoning model，policy 改了不用重新訓練，直接改 prompt 就行。
- Policy prompt 分 Instruction、Definitions、Criteria、Examples 四段，長度抓 400-600 token，避免 generally、usually 這類模糊字眼。
- 輸出指示要明確並重複強調；二元輸出最快，帶 rationale 最能發揮推理能力。
- 用 `reasoning_effort` 調推理深度，不要卡死 max output token，讓模型有空間思考。
- 它比傳統 classifier 慢又貴，適合先用小 classifier pre-filter，只處理模糊案例。

## 練習

1. 把文中 spam 範例 prompt 的輸出格式從二元改成「policy 標籤」，再改成「標籤加 2 點 rationale」，比較三種輸出。
2. 用 vLLM 或 Ollama 跑模型，對同一筆邊界案例分別設 `Reasoning: low` 和 `Reasoning: high`，比較回應內容和速度。
3. 用範本寫一份自己的 policy，把它壓到 400-600 token（用 tokenizer 量），再放進 10 筆邊界案例測試，找出措辭模糊的地方並修正。
