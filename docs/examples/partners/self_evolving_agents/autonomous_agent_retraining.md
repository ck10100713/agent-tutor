---
translated: true
source: examples/partners/self_evolving_agents/autonomous_agent_retraining.ipynb
---
# Self-Evolving Agents：讓 Agent 自主重新訓練的 Cookbook

> 原文：[examples/partners/self_evolving_agents/autonomous_agent_retraining.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/self_evolving_agents/autonomous_agent_retraining.ipynb)



## 這篇在做什麼

Agent 做完 proof-of-concept 之後常常卡住，因為邊界案例和錯誤都要靠人來診斷、修正。這篇示範一個可重複的重新訓練迴圈：收集問題、從回饋學習、把改進放回類 production 的流程。範例是受法規管制的醫藥文件撰寫，但做法適用於任何要求準確、可稽核、要快速迭代的領域。

## 學完你會

- 判斷一個 autonomous agent 為什麼還不夠 production-ready，並加上可量測的回饋訊號。
- 比較三種 prompt 優化策略（手動快速迭代、靜態 metaprompt 自動迴圈、GEPA），知道各自適用的時機。
- 組出一個自我修復的流程，結合人工審查、LLM-as-judge eval 和 prompt 迭代改寫。

## 開跑前

- 需要 OpenAI API key，並使用 OpenAI Evals 和 Agents SDK。
- 第 2 節用 OpenAI 平台的 Evals 介面操作，需要平台帳號。
- 範例資料集 `dataset.csv` 在 GitHub repo 裡。
- 第 4 節的 GEPA 需要安裝 `gepa`，跑一次大約 10 到 15 分鐘。

## 總覽

Agentic 系統在 proof-of-concept 之後常常遇到瓶頸，因為要靠人去診斷邊界案例、修正錯誤。這份 cookbook 介紹一個可重複的重新訓練迴圈：抓出問題、從回饋中學習、再把改進推回類 production 的工作流程。我們用受法規管制的醫療文件任務當範例，不過這些做法可以套用到任何需要準確、可稽核、快速迭代的領域。

### 你會學到什麼
- 診斷 autonomous agent 為什麼還沒達到 production 水準，並用可量測的回饋訊號來監控它。
- 比較三種 prompt 優化策略，從快速手動迭代到完全自動化的迴圈，了解各自什麼時候用。
- 組出一個自我修復的 workflow，結合人工審查、LLM-as-judge eval 和 prompt 迭代改進。

### 這份 Notebook 適合誰
- 需要從玩具 demo 往前走的 ML/AI 工程師和解決方案架構師。
- 想拿到可執行的範例，改成內部工具或 production pipeline 的產品與交付團隊。

### 怎麼讀這份 Notebook
1. 先看第 1 節，了解醫療使用情境、baseline agent 和系統架構。
2. 第 2 節在 OpenAI Evals 介面練習 prompt 優化，並收集結構化回饋。
3. 第 3 節用 grader、eval 和重新訓練邏輯，把優化迴圈自動化。
4. 附錄有可重用的 prompt、設定和評估範本，可以依你的環境調整。

Notebook 是模組化的，你可以單獨跑某一節，也可以依序跑，視你要怎麼把重新訓練迴圈套到自己的 agent 而定。

## 1. 使用情境總覽：醫療領域的 Self-Evolving Agents

### 問題定義

這份 cookbook 聚焦在一個**真實的使用情境**：幫製藥公司草擬法規文件。這些公司要準備大量文件送交主管機關（例如美國 FDA）以取得新藥核准。送件的準確度和速度非常關鍵，直接影響救命的療法多快能到病人手上。  

撰寫法規文件複雜、需要反覆修改、容不得差錯，需要深厚的科學、醫學和法遵專業。就算有先進的寫作工具，它仍然很耗人力，也容易出人為錯誤。**Agentic 系統能幫上很大的忙**，例如整理研究、產生內容、安排文件結構，但還是需要人類專家確保事實正確和符合法規。  

核心挑戰是設計一個回饋迴圈，讓這些 agentic 系統能一步步學習，持續改善模型行為。這樣的系統可以慢慢把人力從逐項修正，轉成高層次的監督，在維持法規送件嚴格標準的同時提升效率。  

### Self-evolving Agent

下圖說明如何透過回饋、meta prompting 和評估，持續改進 AI agent 的迭代流程。這個迴圈結合人類判斷，或用 LLM-as-a-judge 產生的自動回饋，一輪一輪提升表現。  

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/baseline_agent.png" alt="Self-evolving loop" style="max-width:50%"/>
<br><em>圖 1：自動改進 agent 的 self-evolving 迴圈示意圖。</em>

流程分成以下幾步：  

1. **Baseline Agent**  
   一開始是一個 baseline agent。這份 notebook 用刻意簡化的範例（一個摘要文件段落的 agent）來說明迭代改進的迴圈。實際的企業場景裡，baseline agent 會複雜得多。它產出的摘要就是後續評估和改進的初始基準。

2. **人工回饋（或 LLM-as-judge）**  
   baseline agent 的輸出會交給人類審查者（例如 production 環境），和/或自動化的 **LLM-as-judge** 系統評估。這一步會收集量化和質化的回饋，看 agent 達成目標的程度。例如測試摘要長度時，回饋可能是「摘要太長」，或是 eval 判斷摘要是否在 500 字以內後給出的分數（通常介於 `0` 到 `1`）。

3. **Evals 和彙總分數**  
   根據收集到的回饋產生新的 prompt，再透過評估（**Evals**）測試。這些測試依預先定義的標準量測表現，結果合併成一個代表整體表現的彙總分數。迴圈會一直跑到分數超過目標門檻（例如 `0.8`），或達到最大重試次數（例如 `max_retry = 10`）。如果碰到重試上限，就通知工程師需要手動改進。

4. **更新後的 Baseline Agent**  
   改進版本達到目標表現後，就取代原本的 baseline agent。更新後的 agent 成為下一輪迭代的基礎，形成學習、回饋、優化的持續循環。



### 資料集概述

評估用的資料集有約 70 個段落，取自 _Sample CMC Section for Hyperpolarized Pyruvate (13C) Injection_，文件公開在[這裡](https://dctd.cancer.gov/drug-discovery-development/reagents-materials/imaging-ind-resources/documentation/13c-pyruvate-cmc.pdf)。這份資料集的內容貼近真實、屬於特定領域，適合測試科學摘要和法規遵循的行為。 


### Baseline Agent 概述

為了讓這份 cookbook 自成一體又容易重現，我們簡化了法規撰寫的情境，但保留它的核心複雜度。實際 production 中，典型的法規撰寫 agent 會由多個專門的 sub-agent 組成，分別負責草擬、資料分析、合規檢查、引用產生和事實查核。

這份指南把範圍縮小到系統的自我修復部分。我們的法規撰寫 agent 有兩個 sub-agent：
- **Summarizer**：產出科學且精簡的摘要。
- **Compliance checker**：依主要法規要求（例如 FDA 21 CFR Part 11）檢查每份摘要。  

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/simplified_reg_agent.png" alt="Baseline Agent" style="max-width:50%"/>
<br><em>圖 2：在 AgentBuilder UI 裡建立的 baseline agent。</em>

在這份 cookbook 剩下的部分，我們實作的是簡化版的 Summarizer agent（見下面的 **Agent Setup**）。你也可以直接重用用 AgentBuilder 建立的 agent 程式碼。如果想在 AgentBuilder UI 直接重現這個 agent，關鍵的 prompt 和參數如下：

- **Summarizer agent：** 這個 agent 用了 file search tool，[CMC PDF](https://github.com/openai/openai-cookbook/blob/main/examples/partners/self_evolving_agents/data/c13_pyruvate_sample_CMC_from_UCSF.pdf) 已上傳到 vector store。
> _Prompt:_ "Summarize section {{workflow.input_as_text}} from {{state.cmc_pdf}} uploaded to the vector store."

- **Compliance Checker agent：**
> _Prompt:_ "Verify that the summary below is compliant with FDA 21 CFR Part 11: {{input.output_text}}. If the summary is compliant, return _Compliant_. Otherwise, return _This section needs to be manually summarized_."  

兩個 agent 都用預設參數：GPT-5、low reasoning effort、輸出格式為文字。

### 評估方式

評估 baseline agent 有兩種主要做法：

1. **收集人工回饋。** 透過 OpenAI Evals 平台（或為特定應用自建的 UI）蒐集人類使用者的回饋。最適合 production 環境，或是在領域專家（SME）真實使用工具的試行階段。這個方法能挖出開發時沒發現的邊界案例。在 Evals 平台上，使用者可以對摘要按讚或倒讚，並留下文字回饋。  


2. **使用 LLM-as-a-Judge。** 通常用在開發階段，不需要佔用 SME 的時間就能快速取得回饋。**LLM-as-a-judge** 是讓 LLM 依預先定義的標準，自動評估並給 agent 的輸出打分。它也能用來監控模型漂移（例如在 production），或驗證模型版本間的變更（例如在 `gpt-5` 和 `gpt-5-mini` 之間切換）。


這份 cookbook 兩種做法都會示範：
- **第 2 節** 用平台 UI 做手動 prompt 優化
- **第 3 節** 用 LLM-as-a-judge 實作完全自動化的 API 做法

_注意：Evals 平台目前還沒有可以用程式取得使用者回饋的 API。_


## 2. 使用 OpenAI Evals 平台

OpenAI Evals 平台提供直覺的介面來做 prompt 優化和評估。這一節示範從上傳資料集到反覆改進 prompt 的完整流程，讓你在實作自動化方案之前，先用視覺化介面優化 prompt。

### 步驟 1：上傳資料集

要開始使用 OpenAI Evaluation 平台，先上傳你的資料集：

1. 點 **+ Create** 按鈕
2. 設定資料集名稱
3. 上傳 CSV 檔，並選擇要保留的欄位
4. 上傳

資料集應該包含需要摘要的文件或文件段落，每一列代表一筆會交給你的系統處理的輸入。

### 步驟 2：檢視資料

上傳後就可以檢視資料集。點資料集名稱即可瀏覽上傳的資料。在設定 prompt 之前，先確認資料格式正確、內容符合預期。

### 步驟 3：設定初始 Prompt

在這裡定義初始的 system prompt，並設定資料如何流過模型。  

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt_input.png" alt="Platform Prompt Configuration" style="max-width:50%">
<br><em>圖 3：平台的 "New prompt" 介面，顯示模型設定、變數和 system message 設定。</em>


#### 設定步驟

1. **System Prompt**：加入定義模型任務和行為的 system message（這份 prompt 之後會被優化）
2. **User Prompt Template**：加入 user message 的 prompt 範本，用 `{{<column_name>}}` 這類變數，執行時會換成資料集的實際內容
3. **Model Selection**：選擇生成用的模型（例如 gpt-4.1、gpt-5）
4. **Temperature**：調整創意與確定性的平衡

你可以從很簡單的 prompt 開始，來展示優化流程的威力。例如只寫「summarize」，就能看到系統如何從極簡的起點一步步演進。

### 步驟 4：產生輸出

prompt 設定好之後，就可以對整個資料集產生輸出。prompt 會對每一列各跑一次，輸出會放在新的 **output** 欄位。
1. 點 **"Generate Output"**
2. 平台會對所有樣本執行你的 prompt
3. 結果會出現在新的 **Output** 欄位

平台會處理資料集的每一列，把範本變數換成實際值，再用你的 system prompt 呼叫模型。這樣就得到一組可以評估的 baseline 輸出。

### 步驟 5：檢視與評估

評估這一步要提供結構化回饋，來引導 prompt 改進。

#### 檢視輸出

1. 如果沒有自動加入，就**新增評估欄位**：點 "Columns" → "Annotations" → "Add"：
   - **Rating**：二元（好/壞）或數字評分
   - **Feedback**：描述需要改進之處的文字

2. **提供評分和回饋**：對每筆輸出加上你的評估。   

   依輸出品質選擇好或壞的評分，並依你希望答案怎麼改進來說明理由。例如：

      > (Rating) | Feedback
      > - (Good) Good, but only the answer should be provided. The output should not include headers or any text other than the answer.
      > - (Bad)  The information is good, but it should be presented as bullet points.
      > - (Good) Good summary; it is clear.
      > - (Bad)  Use bullet points when answering to improve readability. Summarize each sub-section individually.

3. **儲存 Annotations**：你的回饋會跟著這次 evaluation run 一起儲存

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/feedback.png" alt="Platform Evaluation Interface" style="max-width:50%">
<br><em>圖 4：評估介面，顯示產生的輸出和供標註的 rating、feedback 欄位。</em>

這些結構化回饋是自動 prompt 優化的基礎。

### 步驟 6：優化 Prompt

收集完回饋後，平台可以自動產生改進後的 prompt。

1. 點 **"Optimize"**
2. 新版 prompt 會在新分頁產生
3. 點 **"View Prompt"** 查看改進後的版本

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/updated_prompt.png" alt="Platform Optimized Prompt" style="max-width:50%">
<br><em>圖 5：平台產生的改進版 prompt，包含詳細的指示和要求。</em>

### 步驟 7：迭代與比較

改進後的 prompt 準備好之後，開始新一輪迭代來量測進步幅度。

1. 點 **"Generate Output"**
2. 檢視新結果，對剩下的問題提供回饋
3. 需要的話再點一次 **"Optimize"**
4. 重複到你滿意為止

平台的分頁結構讓你可以跨迭代比較表現，很容易看出輸出從最初的 prompt 到優化版本如何演變。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/updated_prompt_feedback.png" alt="Platform Updated Prompt Feedback" style="max-width:50%">
<br><em>圖 6：優化後 prompt 的回饋和評估結果，顯示輸出品質有進步。</em>

#### 什麼時候停止迭代

優化迴圈跑到以下情況就可以停：
- **達到品質門檻**：超過 80% 的輸出得到正面回饋
- **邊際效益遞減**：新的迭代幾乎沒有進步
- **特定問題已解決**：所有找到的失敗模式都處理了

這種平台式做法是理解 prompt 優化的好起點，之後再轉向自動化實作。視覺化介面讓你容易看出改動的影響，也容易理解優化過程。


## 3. 用 LLM-as-a-Judge 做 Self-evolving 迴圈

這一節透過 OpenAI API，用 LLM-as-a-Judge 建立完全自動化的評估流程，完全不需要使用者介面。這種做法可以程式化、規模化地評估 agent 表現，支援快速迭代，也能在 production 持續監控模型。

```python
# gepa and litellm are only required for the Section 4.b (prompt optimization with GEPA)
%pip install --upgrade openai openai-agents pydantic pandas gepa litellm python-dotenv -qqq 
%load_ext dotenv
%dotenv

# Place your API key in a file called .env
# OPENAI_API_KEY=sk-...
```

### 建立 Eval

為了評估 baseline 摘要 agent，我們用四個互補的 grader，兼顧確定性檢查和語意判斷。

| Grader | Type | Pass threshold | What it checks | Why |
|---|---|---:|---|---|
| Chemical string name | `python` | 0.8 | If any exact chemical names in the section appear in the summary. | Forces preservation of critical domain entities so summaries don’t omit chemically meaningful terms. |
| Summarization length | `python` | 0.85 | Inverse deviation from an expected 100-word length. | Keeps summaries concise and comparable, reducing verbosity that can mask poor content. |
| Cosine similarity | `text_similarity` | 0.85 | Cosine similarity between section and summary texts. | Ensures the summary stays anchored to the source content rather than drifting semantically. |
| LLM-as-judge | `score_model` | 0.85 | A rubric-driven score from a model acting as an evaluator. | Captures nuanced quality signals that rule-based metrics miss, improving overall robustness. |

**備註**
- 兩個 Python grader 及早抓出領域資訊的忠實度和長度控制，讓優化在進入語意調整前先穩定下來。
- 文字相似度用來防止只是表面改寫、卻偏離原文的摘要。
- 當邊界案例漏過確定性檢查時，LLM judge 提供整體的最後防線。

```python
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {"section": {"type": "string"}, "summary": {"type": "string"}},
        "required": ["section", "summary"],
    },
    "include_sample_schema": False,
}

testing_criteria = [
    {
        "type": "python",
        "name": "chemical_name_grader",
        "image_tag": "2025-05-08",
        "pass_threshold": 0.8,
        "source": r"""def grade(sample: dict, item: dict) -> float:
    section = item["section"]
    summary = item["summary"]
    CHEMICALS_MASTER = ["[1-¹³C]Pyruvic acid","[1-¹³C]Pyruvate","¹²C Pyruvic acid","Sodium [1-¹³C]pyruvate","Sodium pyruvate (¹²C)","AH111501 (Trityl radical)","Tris{8-carboxyl-2,2,6,6-tetra[2-(1-methoxyethyl)]-benzo(1,2-d:4,5-d’)bis(1,3)dithiole-4-yl}methyl acid","AH111501 sodium salt","Methyl, tris[8-carboxy-2,2,6,6-tetrakis(2-methoxyethyl)benzo[1,2-d:4,5-d’]bis[1,3]dithiol-4-yl]-, trisodium salt","AH111501 trisodium salt","AH111576","2,2′,2″,2‴-(4,8-Dibromobenzo[1,2-d:4,5-d′]bis([1,3]dithiole)-2,2,6,6-tetrayl)tetraethanol","AH111586","4,8-Dibromo-2,2,6,6-tetrakis(2-methoxyethyl)benzo[1,2-d:4,5-d′]bis([1,3]dithiole)","AH111709","AH111743","AH112615","4,4-Bis-hydroxymethyl-2-methyl-oxazolidine-2-carboxylic acid","AH112623","Parapyruvate","2-Hydroxy-2-methyl-4-oxo-pentanedioic acid","AH113127","(4-Hydroxymethyl-oxazolidin-4-yl)-methanol","AH113462/E","Enol lactone","AH113462/K","Keto lactone","Acetyl bromide","Methanol","Dimethyl sulfoxide","DMSO","Tetrahydrofuran","THF","Acetonitrile","ACN","Diethyl ether","Et₂O","N,N-Dimethylacetamide","DMA","1,3-Dimethyl-2-imidazolidinone","DMI","Hydrochloric acid","HCl","Sodium hydroxide","NaOH","Disodium ethylenediaminetetraacetate","Na₂EDTA","Ethylenediaminetetraacetic acid","EDTA","Tris(hydroxymethyl)aminomethane","TRIS","Trometamol","Trifluoroacetic acid","TFA","Toluene","Heptane","Ethyl acetate","Ethanol","Water","H₂O","Sodium chloride","NaCl","Cuprous [1-¹³C]cyanide","Cu¹³CN","Gadolinium","Gd","Tin","Sn","Phosphorus","P","Carbon dioxide","CO₂","Sodium [1-13C]pyruvate","[1-13C]Pyruvic acid","1-13C pyruvate"]

    # Identify the chemicals present in the section
    present = [chem for chem in CHEMICALS_MASTER if chem in section]

    # If no chemicals present, consider it satisfied
    if not present:
        return 1.0

    correct = 0
    for chem in present:
        # Only count as correct if the exact chemical string appears in the summary
        if chem in summary:
            correct += 1

    return correct / len(present)""",
    },
    {
    "type": "python",
    "name": "word_length_deviation_grader",
    "image_tag": "2025-05-08",
    "pass_threshold": 0.85,
    "source": r"""
def grade(sample: dict, item: dict) -> float:
    summary = item["summary"]
    word_count = len(summary.split())
    
    expected_summary_length = 100
    tolerance = 0.2  # 20% band around target
    
    # relative deviation
    deviation = abs(word_count - expected_summary_length) / expected_summary_length
    
    # If within tolerance band → full score
    if deviation <= tolerance:
        return 1.0
    
    # Outside band → score decays linearly, capped at 0
    # e.g., deviation 0.3 → score 0.8, deviation 1.0+ → 0.0
    score = 1.0 - (deviation - tolerance)
    return max(0.0, score)
""",
},
    {
        "name": "cosine_similarity",
        "type": "text_similarity",
        "input": "{{ item.summary }}",
        "reference": "{{ item.section }}",
        "evaluation_metric": "cosine",
        "pass_threshold": 0.85,
    },
    {
        "name": "llm_as_judge",
        "type": "score_model",
        "model": "gpt-4.1",
        "input": [
            {
                "role": "system",
                "content": (
                    "You are an expert technical summarization evaluator. "
                    "Evaluate whether the summary captures and preserves the important technical facts and specific details from the section, allowing for occasional minor rewording or omissions of less important points, but not major technical inaccuracies or information loss.\n\n"
                    "Scoring Guidelines:\n"
                    "- Return a numerical score between 0 and 1 (with up to two decimal places).\n"
                    "- A score of 1 means the summary is almost flawless: it is comprehensive, highly faithful, and technically accurate, with virtually no important or meaningful details missing, and no significant misstatements or distortions.\n"
                    "- 0.75-0.99 indicates excellent work: all main facts are represented, but there may be trivial omissions or very minor rewording that do not materially affect understanding.\n"
                    "- 0.5-0.75 indicates good but imperfect: most technical information is retained and correctly presented, some less critical details might be missing or slightly rephrased, but overall fidelity is preserved.\n"
                    "- 0.3-0.5 means significant information is missing, or some technical inaccuracies are present, but the summary retains a reasonable portion of key facts.\n"
                    "- 0.0-0.3 means there are major omissions, misunderstandings, or a failure to capture the most important technical content.\n\n"
                    "Respond only with a single number between 0 and 1 indicating summary quality by these criteria."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Section:\n{{item.section}}\n"
                    "Summary:\n{{sample.output_text}}"
                ),
            },
        ],
        "range": [0, 1],
        "pass_threshold": 0.85,
    },
]

eval = client.evals.create(
    name="self_evolving_eval",
    data_source_config=data_source_config,
    testing_criteria=testing_criteria,
)
print(f"Created Eval: {eval.id}")
```

輸出裡應該會看到一個 eval ID，例如 `eval_...`。這就是剛剛建立的 eval 的 ID（如下圖）

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_set_config.png" alt="Platform Eval Configuration" style="max-width:50%">
<br><em>圖 7：平台的 Eval 介面，顯示資料來源設定和測試標準設定。</em>

### Grader 評分與解析

接下來要對摘要 agent 的輸出跑 eval，並解析出 eval 的 grader 分數。這裡會用到幾個輔助函式：
- `run_eval`：簡單的 runner，用正確的格式呼叫 evals API
- `poll_eval_run`：輪詢工具，等排程的 eval run 完成
- `parse_eval_run_output`：解析 eval run，回傳給回饋迴圈用的結構化輸出

```python
import time
import json

def run_eval(eval_id: str, section: str, summary: str):
  """Creates a run of the eval with the input section and output summary."""
  return client.evals.runs.create(
    eval_id=eval_id,
    name="self-evolving-eval",
    data_source={
      "type": "jsonl",
      "source": {
        "type": "file_content",
        "content": [
          {
            "item": {
              "section": section,
              "summary": summary,
            }
          }
        ],
      },
    },
  )


def poll_eval_run(eval_id: str, run_id: str, max_polls = 10):
    """
    Polls the evaluation run until completion or timeout.

    This function exists to handle asynchronous behavior in the eval service by
    periodically checking run status. It balances responsiveness and resource use by
    polling at fixed intervals rather than blocking indefinitely. The retry limit
    prevents runaway loops in cases where the service never returns a completed status.
    """
    run = None
    for attempt in range(1, max_polls + 1):
        run = client.evals.runs.retrieve(eval_id=eval_id, run_id=run_id)
        if run.status == "completed":
            break
        if attempt == max_polls:
            print("Exceeded retries, aborting")
            break

        time.sleep(5)

    run_output_items = client.evals.runs.output_items.list(
        eval_id=eval_id, run_id=run_id
    )
    return run_output_items


def parse_eval_run_output(items):
    """Extract all grader scores and any available conclusion outputs."""
    all_results = []

    for item in items.data:
        for result in item.results:
            grader_name_full = result.name
            score = result.score
            passed = result.passed
            reasoning = None
            try:
                sample = result.sample
                if sample:
                    content = result.sample["output"][0]["content"]
                    content_json = json.loads(content)
                    steps = content_json["steps"]
                    reasoning = " ".join([step["conclusion"] for step in steps])
            except Exception:
                pass

            all_results.append(
                {
                    "grader_name": grader_name_full,
                    "score": score,
                    "passed": passed,
                    "reasoning": reasoning,
                }
            )

    return all_results
```

現在可以用前面建立的 eval ID，對任意輸入段落和摘要輸出跑 grader。這是回饋迴圈的骨幹，會觸發 prompt 優化流程。

### 執行 Eval

我們直接提供一個段落和產生的摘要來測試 eval。

```python
EVAL_ID = eval.id #Created eval ID from above cell
SECTION = "3.2.S.1 General Information ([1-13C]pyruvic acid) The active ingredient in Hyperpolarized Pyruvate (13C) Injection is hyperpolarized [1-13C]pyruvate. The drug substance is defined as [13C]pyruvic acid, which is neutralized to [1-13C]pyruvate during the compounding process. In several pre-clinical and clinical studies and during evaluation of stability, pyruvic acid has been used instead of [1-13C]pyruvic acid (see Sections 3.2.P.2.2.1 Formulation Development for Hyperpolarized Pyruvate (13C) Injection and Section 8.1 Introduction for Item 8 Pharmacology and Toxicology Info). In the Section 3.2.S Drug Substance, data are presented for both pyruvic acid and for [1-13C]pyruvic acid. For simplicity, the terminology used in headings and captions is [1-13C]pyruvic acid. Batches containing pyruvic acid are specified by footnotes. 3.2.S.1.1 Nomenclature ([1-13C]pyruvic acid) The drug substance used for compounding of Hyperpolarized Pyruvate (13C) Injection is [1-13C]pyruvic acid. Company code: W6578 Chemical name: [1-13C]pyruvic acid CAS registry number: 127-17-3 3.2.S.1.2 Structure ([1-13C]pyruvic acid) Figure 1 Structure of [1-13C]pyruvic acid Molecular formula: C H O 3 4 3 Molecular weight: 89.06 3.2.S.1.3 General Properties ([1-13C]pyruvic acid) Appearance: Colorless to yellow, clear, viscous liquid pKa:Ka:aranWater solubility: Complete The structure of [1-13C]pyruvic acid has been confirmed by spectroscopic analysis (see Section 3.2.S.3.1 Elucidation of Structure and other Characteristics)."
SUMMARY = "The active ingredient in Hyperpolarized Pyruvate (13C) Injection is hyperpolarized [1-13C]pyruvate, derived from [1-13C]pyruvic acid (neutralized during compounding). Both pyruvic acid and [1-13C]pyruvic acid were used in studies and stability evaluations, but the documentation refers to [1-13C]pyruvic acid unless otherwise noted. The drug substance ([1-13C]pyruvic acid, CAS 127-17-3) is a colorless to yellow, clear, viscous liquid with a molecular formula C3H4O3 and molecular weight 89.06. Its structure has been confirmed by spectroscopic analysis, and it is completely soluble in water."

eval_run = run_eval(EVAL_ID, section=SECTION, summary=SUMMARY)
run_output = poll_eval_run(eval_id=EVAL_ID, run_id=eval_run.id)

grader_scores = parse_eval_run_output(run_output)
print(grader_scores)
```

輸出裡應該會看到一串 grader 分數，例如：

```[{'grader_name': 'chemical_name_grader-<uuid>', 'score': 0.5, 'passed': False, 'reasoning': None}, {'grader_name': 'word_length_deviation_grader-<uuid>', 'score': 0.8, 'passed': True, 'reasoning': None}, {'grader_name': 'cosine_similarity-<uuid>', 'score': 0.9104484223477793, 'passed': True, 'reasoning': None}, {'grader_name': 'llm_as_judge-<uuid>', 'score': 0.8, 'passed': True, 'reasoning': 'The summary needs to include specific details from the section. Part of the essential information is captured. Key pieces of information are missing. Not all relevant structural information is included.'}]```


Running this script we can see that most of our graders are passing except the `chemical_name_grader`. Next we'll programmatically recognize this opportunity to improve the summarization agent.

_Note: When you run it locally, graders other than `chemical_name_grader` may fail at first. This is normal, as graders can initially fail, but the results should improve through the feedback loop. Early failures simply reflect the model adjusting its responses before converging on more accurate results._


### Dashboard Observability
Eval runs and results can also be seen in the OpenAI Dashboard:  

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_dashboard.png" alt="Eval dashboard" style="max-width:50%">
<br><em>Figure 8 - Eval dashboard showing evaluation runs and results.</em>


We can also drill down into a specific eval run:  
<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_run_results.png" alt="Eval results" style="max-width:50%">
<br><em>Figure 9 - Detailed eval run results showing grader scores and performance metrics.</em>


## Agent Setup

Now that we have our evals and graders set up, we can go back to our summarization agent. 
For simplicity, we will provide the code for a simple agent below. You could also use `AgentBuilder`, as shown in Figure 2, and export the code from the UI.


We will also need a metaprompt optimization agent, to optimize our prompt, as well as some simple utilities to handle prompt versions:
- `PromptVersionEntry`: A pydantic model used to track the prompt and metadata as it changes in production
- `VersionedPrompt`: A utility class to track prompt versions, this will be important in production when analyzing the evolution of the prompt as well as ensuring there is a fallback history in case of a regression

```python
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict, field_validator

class PromptVersionEntry(BaseModel):
    """Data model for a prompt and associated data for observability"""
    version: int = Field(
        ..., ge=0, description="Version number of the prompt (increments)"
    )
    model: str = Field(
        "gpt-5",
        min_length=1,
        description="The model version to use for this version of the prompt, defaults to gpt-5",
    )
    prompt: str = Field(
        ..., min_length=1, description="The prompt text for this version"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when this version was created",
    )
    eval_id: Optional[str] = Field(
        None, description="ID of the evaluation associated with this prompt version"
    )
    run_id: Optional[str] = Field(
        None, description="ID of the run associated with this prompt version"
    )
    metadata: Optional[dict[str, Any]] = Field(
        None, description="Free-form metadata dict (e.g., section, summary)"
    )

    model_config = ConfigDict(
        str_strip_whitespace=True, validate_assignment=True, extra="forbid"
    )

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("prompt must not be blank or only whitespace")
        return v


class VersionedPrompt:
    """Manages a collection of prompt versions and provides controlled updates and rollbacks."""
    def __init__(
        self,
        initial_prompt: str,
        model: Optional[str] = "gpt-5",
        eval_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        if not initial_prompt or not initial_prompt.strip():
            raise ValueError("initial_prompt must be non-empty")
        self._versions: list[PromptVersionEntry] = []
        first_entry = PromptVersionEntry(
            version=0,
            prompt=initial_prompt,
            model=model,
            eval_id=eval_id,
            run_id=run_id,
            metadata=metadata,
        )
        self._versions.append(first_entry)

    def update(
        self,
        new_prompt: str,
        model: Optional[str] = "gpt-5",
        eval_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PromptVersionEntry:
        if not new_prompt or not new_prompt.strip():
            raise ValueError("new_prompt must be non-empty")

        version = self.current().version + 1
        entry = PromptVersionEntry(
            version=version,
            prompt=new_prompt,
            model=model,
            eval_id=eval_id,
            run_id=run_id,
            metadata=metadata,
        )
        self._versions.append(entry)
        return entry

    def current(self) -> PromptVersionEntry:
        return self._versions[-1]

    def revert_to_version(self, version: int) -> PromptVersionEntry:
        idx = None
        for i, entry in enumerate(self._versions):
            if entry.version == version:
                idx = i
                break

        if idx is None:
            raise ValueError(f"No version found with version={version}")

        self._versions = self._versions[: idx + 1]
        return self._versions[-1]
```

接著建立起始的摘要 agent 和 prompt 優化 agent。

_注意：我們包了一層 wrapper 來追蹤摘要 agent 的 prompt 變動，因為 production 中 prompt 預期會持續演進。這份 cookbook 裡 metaprompt agent 的 prompt 保持固定。_

```python

from agents import Agent

METAPROMPT_TEMPLATE = """
# Context:
## Original prompt:
{original_prompt}

## Section:
{section}

## Summary:
{summary}

## Reason to improve the prompt:
{reasoning}

# Task:
Write a new summarization prompt that is significantly improved and more specific than the original.  
The new prompt should instruct the model to produce concise yet comprehensive technical summaries that precisely preserve all explicit information from the source text. It should emphasize the inclusion of all named entities, quantities, compounds, and technical terminology without paraphrasing or omission. The resulting prompt should read like a clear, directive system message for a technical summarization assistant—structured, unambiguous, and generalizable across scientific or regulatory document sections.
"""

metaprompt_agent = Agent(
    name="MetapromptAgent", instructions="You are a prompt optimizer."
)

summarization_prompt = VersionedPrompt(
    initial_prompt="""You are a summarization assistant.
Given a section of text, produce a summary."""
)

def make_summarization_agent(prompt_entry: PromptVersionEntry) -> Agent:
    return Agent(
        name="SummarizationAgent",
        instructions=prompt_entry.prompt,
        model=prompt_entry.model,
    )

summarization_agent = make_summarization_agent(summarization_prompt.current())

# Cache eval results by section + summary so repeated attempts do not trigger redundant grader runs.
eval_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

# Track the highest-scoring candidate that also passes the lenient score threshold.
best_candidate: dict[str, Any] = {
    "score": float("-inf"),
    "prompt": summarization_prompt.current().prompt,
    "model": summarization_prompt.current().model,
    "summary": None,
    "metadata": None,
    "version": summarization_prompt.current().version,
    "passed_lenient": False,
    "total_score": float("-inf"),
}

# Aggregate per-version performance so we can pick the strongest total scorer at the end.
aggregate_prompt_stats: dict[int, dict[str, Any]] = {}
```

### 編排與監控

到目前為止，我們建好了：
- 有 4 個 grader 的 Evals，會評估輸出並給每個 grader 一個分數
- 一個摘要 agent，搭配有版本管理的 prompt class 來追蹤 prompt 和模型的變動
- 一個 metaprompt 優化 agent，會根據一組推理嘗試更新 prompt

現在可以把這些功能組合起來，編排 self-evolving 迴圈，並在 OpenAI dashboard 用 Agent tracing 觀察。

請記得這是簡化的範例。實際情境中，你要對優化嘗試設置 guardrail，並在 guardrail 被觸發時通知人類。

_注意：受限於 cookbook 的條件，我們用靜態資料集來模擬資料流，並用 `print` 取代真正的 observability。_

### 編排用的工具函式

跟前面幾節一樣，我們建立一些工具函式來管理回饋迴圈的編排邏輯。

```python
import asyncio
from typing import Any, Optional
from agents import Runner

LENIENT_PASS_RATIO = 0.75 # 75% of graders must pass (binary) 
LENIENT_AVERAGE_THRESHOLD = 0.85 # 85% average score across graders 

def reset_best_candidate() -> None:
    """Reset the best candidate tracker for a new optimization run."""
    global best_candidate

    current = summarization_prompt.current()
    best_candidate = {
        "score": float("-inf"),
        "prompt": current.prompt,
        "model": current.model,
        "summary": None,
        "metadata": None,
        "version": current.version,
    }

def reset_best_trackers() -> None:
    """Reset both the best-candidate tracker and aggregate stats."""
    reset_best_candidate()
    aggregate_prompt_stats.clear()


def update_best_candidate(
    *,
    average_score: Optional[float] = None,
    prompt_text: str,
    model_name: str,
    summary_text: str = None,
    metadata: dict[str, Any] = None,
    lenient_passed: bool = False,
    prompt_version: int = None,
    total_score: Optional[float] = None,
    score: Optional[float] = None,
) -> None:
    """Persist the best lenient-passing candidate."""
    global best_candidate

    if prompt_version is None:
        prompt_version = summarization_prompt.current().version

    if average_score is None:
        average_score = score

    if average_score is None:
        return

    if lenient_passed:
        best_candidate.update(
            {
                "score": average_score,
                "prompt": prompt_text,
                "model": model_name,
                "summary": summary_text,
                "metadata": metadata,
                "version": prompt_version,
                "total_score": total_score if total_score is not None else average_score,
            }
        )


def apply_best_candidate_if_needed() -> Agent:
    """Ensure summarization_prompt reflects the best prompt candidate."""
    if best_candidate["score"] > float("-inf"):
        current = summarization_prompt.current()
        target = best_candidate
        # Only update if different
        if (
            current.prompt != target["prompt"]
            or current.model != target["model"]
            or current.version != target.get("version")
        ):
            summarization_prompt.update(
                new_prompt=target["prompt"],
                model=target["model"],
                metadata=target.get("metadata"),
            )
            target["version"] = summarization_prompt.current().version
        return make_summarization_agent(summarization_prompt.current())

    return make_summarization_agent(summarization_prompt.current())


def record_aggregate_prompt_score(
    *,
    prompt_version: int,
    prompt_text: str,
    model_name: str,
    average_score: float,
    total_score: Optional[float] = None,
) -> None:
    """Accumulate per-version grader scores for aggregate selection."""
    stats = aggregate_prompt_stats.setdefault(
        prompt_version,
        {
            "version": prompt_version,
            "prompt": prompt_text,
            "model": model_name,
            "total_score": 0.0,
            "total_average": 0.0,
            "count": 0,
        },
    )
    stats["total_score"] += total_score if total_score is not None else average_score
    stats["total_average"] += average_score
    stats["count"] += 1
    stats["prompt"] = prompt_text
    stats["model"] = model_name


def select_best_aggregate_prompt() -> Optional[dict[str, Any]]:
    """Return the prompt version with the highest cumulative score."""
    if not aggregate_prompt_stats:
        return None
    return max(
        aggregate_prompt_stats.values(),
        key=lambda entry: (
            entry.get("total_score", float("-inf")),
            entry.get("version", -1),
        ),
    )


async def get_eval_grader_score(eval_id: str, section: str, summary: str):
    """Retrieve grader scores for a section-summary pair with caching."""
    cache_key = (section, summary)
    if cache_key in eval_cache:
        return eval_cache[cache_key]

    eval_run = run_eval(eval_id=eval_id, section=section, summary=summary)
    run_output = poll_eval_run(eval_id=eval_id, run_id=eval_run.id)
    results = parse_eval_run_output(run_output)
    eval_cache[cache_key] = results
    return results


def calculate_grader_score(grader_scores):
    """Simple average score of all graders from the eval."""
    if not grader_scores:
        return 0.0

    score_sum = 0.0
    for entry in grader_scores:
        score_sum += entry.get("score", 0.0)

    return score_sum / len(grader_scores)



def calculate_total_grader_score(grader_scores):
    """Sum of all grader scores for aggregate tracking."""
    if not grader_scores:
        return 0.0

    return sum(entry.get("score", 0.0) for entry in grader_scores)


DEFAULT_PASSING_FEEDBACK = (
    "All graders passed; tighten factual coverage, chemical completeness, and conciseness."
)


def is_lenient_pass(grader_scores, average_score: float) -> bool:
    if not grader_scores:
        return False

    passed_count = sum(1 for entry in grader_scores if entry.get("passed"))
    total_graders = len(grader_scores)

    if total_graders and (passed_count / total_graders) >= LENIENT_PASS_RATIO:
        return True
    return average_score >= LENIENT_AVERAGE_THRESHOLD


def collect_grader_feedback(grader_scores):
    """Consolidate grader reasoning into actionable feedback for the metaprompt agent."""
    feedback_lines = []

    for entry in grader_scores:
        grader = entry.get("grader_name", "")
        passed = entry.get("passed", False)
        reasoning = entry.get("reasoning")

        if not passed:
            if grader.startswith("chemical_name_grader"):
                feedback_lines.append(
                    "Not all chemical names in the input section were included in the summary."
                )
            elif grader.startswith("word_length_deviation_grader"):
                feedback_lines.append(
                    "The summary length deviates too much from the expected length."
                )
            elif grader.startswith("cosine_similarity"):
                feedback_lines.append(
                    "The summary is not sufficiently similar to the source section (cosine similarity too low)."
                )
            elif grader.startswith("llm_as_judge") and reasoning:
                feedback_lines.append(reasoning)

    if not feedback_lines:
        feedback_lines.append(DEFAULT_PASSING_FEEDBACK)

    return "".join(feedback_lines)
```

### Self-evolving 迴圈

現在我們用準備好的資料集來模擬一連串摘要請求，觀察 prompt 如何從一個天真的起點一步步演化。

> 文中的 dataset.csv 可以在 GitHub repo 找到。

```python
import pandas as pd

from agents import Agent, trace

EVAL_ID = eval.id #Created eval ID from above cell
MAX_OPTIMIZATION_RETRIES = 3

async def self_evolving_loop(summarization_agent: Agent) -> Agent:
    print(f"Starting self-evolving loop | Initial prompt v{summarization_prompt.current().version}")
    print(f"Prompt:{summarization_prompt.current().prompt}")
    print("-" * 80)

    reset_best_trackers()
    df = pd.read_csv("data/dataset.csv")

    with trace("Self-evolving Optimization Workflow"):
        for _, row in df.head().iterrows():
            content = row.get("content")
            if pd.isna(content) or (isinstance(content, str) and not content.strip()):
                continue

            section_number = str(row["section_number"])
            section = str(content)
            current_version = summarization_prompt.current().version

            print(f"[Section {section_number}] Using prompt v{current_version}")

            optimization_success = False

            for attempt in range(1, MAX_OPTIMIZATION_RETRIES + 1):
                print(f"  Attempt {attempt}: evaluating summary...")

                summary_result = await Runner.run(summarization_agent, section)
                summary = summary_result.final_output

                grader_scores = await get_eval_grader_score(eval_id=EVAL_ID, summary=summary, section=section)
                average_score = calculate_grader_score(grader_scores)
                total_score = calculate_total_grader_score(grader_scores)
                lenient_passed = is_lenient_pass(grader_scores, average_score)
                print(
                    f"	Scores — avg={average_score:.3f}, total={total_score:.3f}, lenient_passed={lenient_passed}"
                )

                record_aggregate_prompt_score(
                    prompt_version=summarization_prompt.current().version,
                    prompt_text=summarization_prompt.current().prompt,
                    model_name=summarization_prompt.current().model,
                    average_score=average_score,
                    total_score=total_score,
                )

                update_best_candidate(
                    average_score=average_score,
                    prompt_text=summarization_prompt.current().prompt,
                    model_name=summarization_prompt.current().model,
                    summary_text=summary,
                    metadata={
                        "section": section_number,
                        "average_score": average_score,
                        "grader_results": grader_scores,
                        "prompt_version": summarization_prompt.current().version,
                    },
                    lenient_passed=lenient_passed,
                    prompt_version=summarization_prompt.current().version,
                )

                if lenient_passed:
                    optimization_success = True
                    print(f"	Passed with prompt v{summarization_prompt.current().version}")
                    break

                print("	Failed eval. Improving prompt...")
                eval_feedback = collect_grader_feedback(grader_scores)

                metaprompt_result = await Runner.run(
                    metaprompt_agent,
                    input=METAPROMPT_TEMPLATE.format(
                        original_prompt=summarization_prompt.current().prompt,
                        section=section,
                        summary=summary,
                        reasoning=eval_feedback,
                    ),
                )
                improved_prompt = metaprompt_result.final_output
                summarization_prompt.update(
                    new_prompt=improved_prompt,
                    metadata={"section": section, "summary": summary},
                )
                summarization_agent = make_summarization_agent(summarization_prompt.current())

                print(f"	Prompt improved → v{summarization_prompt.current().version}")

            if not optimization_success:
                print(
                    "	All attempts failed; keeping latest prompt version "
                    f"v{summarization_prompt.current().version} for the next section."
                )

    summarization_agent = apply_best_candidate_if_needed()

    print("" + "-" * 80)
    print("Completed optimization loop.")
    print(f"Final prompt version: v{summarization_prompt.current().version}")
    if best_candidate["score"] > float("-inf"):
        print(
            f"Best lenient prompt: v{best_candidate.get('version')} (avg={best_candidate['score']:.3f})"
        )

    aggregate_best = select_best_aggregate_prompt()
    if aggregate_best:
        per_section = (
            aggregate_best.get("total_average", 0.0) / aggregate_best.get("count", 1)
            if aggregate_best.get("count")
            else 0.0
        )
        print(
            f"Aggregate best prompt: v{aggregate_best.get('version')} "
            f"(total={aggregate_best.get('total_score', 0.0):.3f}, avg/section={per_section:.3f}, model={aggregate_best.get('model', 'unknown')})"
        )

    print(f"Final prompt:{summarization_prompt.current().prompt}")
    return summarization_agent

summarization_agent = await self_evolving_loop(summarization_agent)
```

**最後的 prompt 怎麼選**

- 每次評估都會記錄平均 grader 分數、各 grader 的總分，以及這次嘗試有沒有通過寬鬆標準。
- `best_candidate` 追蹤最近一次通過寬鬆標準的版本（為了透明度），但最後的選擇是看總分，確保保留整體表現最好的 prompt。
- 迴圈結束時，`apply_best_candidate_if_needed` 會還原累計 grader 分數最高的 prompt（同分時選最新的版本），保證最後呈現的 prompt 是觀察到的最強版本。


下面是上面程式碼的範例輸出（節錄）。

看輸出可以確認 self-evolving prompt 有效。有幾個重點要注意：
1. 優化不一定每次都成功，所以能回滾 prompt 版本很重要
2. grader 提供資訊的忠實度，對優化品質至關重要

### Agent Log 與 Tracing

我們可以在 dashboard 的 logs 底下查看優化 workflow 的執行紀錄：  

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent_log_traces.png" alt="Agent log traces" style="max-width:50%">
<br><em>圖 10：Agent log traces，顯示 dashboard 裡的優化 workflow 執行紀錄。</em>

也可以往下查看各個 agent 呼叫：  

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent_trace_details.png" alt="Agent trace details" style="max-width:50%">
<br><em>圖 11：詳細的 agent trace，顯示各個 agent 呼叫和執行流程。</em>

### 持續監控

評估迴圈跑完後，系統應該繼續監控新進來的資料，並定期在 blind dataset 上重新評估模型表現。這樣在資料分布變動時，模型仍能保持準確和合規。

要做到持續監控，可以接 cron job 或輕量的排程迴圈，定期檢查資料來源有沒有更新（例如新上傳的 PDF 或新的資料庫紀錄）。偵測到新資料時，系統就自動觸發前面說的評估和優化迴圈。

範例（pseudo code）：

```python
# this cell is pseudo-code and not meant to be run as-is

import time

def continuous_monitoring(interval_hours=24):
    """Periodically check for new data and trigger the evaluation loop."""
    while True:
        print("Checking for new data...")
        if new_data_detected():
            print("New data found — running evaluation and optimization loop.")
            self_evolving_loop()
        else:
            print("No new data. Sleeping until next cycle.")
        time.sleep(interval_hours * 3600)

continuous_monitoring(interval_hours=24)
```

這個做法讓模型能持續學習、適應，隨著處理新資料越來越好，這是在真實場景維持高品質表現的關鍵需求。

## 4. 更進一步

### a. 模型評估

我們現在有一個完全自動化的迴圈，用 **evals** 改進 prompt，並在評分超過設定門檻時接受新 prompt。  

在 production 中，你可以用類似的框架，在新的使用者請求進來時監控 agent 的表現。如前面所說，這是簡化的範例，實際情境中你會想要有額外的 guardrail 和 human-in-the-loop，來核准新的 prompt。  

把這個概念再推進一步，我們也可以用 evals 測試不同的模型參數組合，例如模型版本、verbosity 和 reasoning。想看可以考慮的完整參數，請參考 [Agents SDK 的 ModelSettings class](https://openai.github.io/openai-agents-python/ref/model_settings/#agents.model_settings.ModelSettings)

`compare_model_candidates` 函式示範怎麼：
1. 優化 prompt
2. 用優化後的 prompt，搭配兩個以上不同的模型產生候選輸出
3. 用 evals 評分候選輸出並選出最佳者

只要小幅重構，就能把它整合進 `self_evolving_loop` 函式。

> **注意：** 在 production 測試模型版本時，應該限制在同一個系列內的版本（例如 gpt-5、gpt-5-mini、gpt-5-nano）。跨系列的版本選擇建議在 production 部署前完成。
這是加入模型比較程式碼的最終版 `self_evolving_loop`：

```python
from agents import Agent, Runner

async def eval_agent_candidate(agent: Agent, section: str, prompt_text: str, model_name: str):
    summary_result = await Runner.run(agent, section)
    summary = summary_result.final_output

    scores = await get_eval_grader_score(
        eval_id=EVAL_ID, summary=summary, section=section
    )
    average = calculate_grader_score(scores)
    lenient_passed = is_lenient_pass(scores, average)
    passed = all(entry.get("passed") is True for entry in scores)

    update_best_candidate(
        average_score=average,
        prompt_text=prompt_text,
        model_name=model_name,
        summary_text=summary,
        metadata={
            "section": section,
            "average_score": average,
            "grader_results": scores,
        },
        lenient_passed=lenient_passed,
    )

    return {"summary": summary, "scores": scores, "average": average, "passed": passed}

async def compare_model_candidates(
    summarization_prompt,
    eval_feedback: str,
    section: str,
    summary: str,
    model_candidates=None,
):
    """Improve the prompt, evaluate it across candidate models, and adopt the top performer."""
    if model_candidates is None:
        model_candidates = ["gpt-5", "gpt-5-mini"]

    metaprompt_result = await Runner.run(
        metaprompt_agent,
        input=METAPROMPT_TEMPLATE.format(
            original_prompt=summarization_prompt.current().prompt,
            section=section,
            summary=summary,
            reasoning=eval_feedback,
        ),
    )
    improved_prompt = metaprompt_result.final_output

    async def evaluate_model(model_name: str):
        candidate_agent = Agent(
            name=f"SummarizationAgent:{model_name}",
            instructions=improved_prompt,
            model=model_name,
        )
        result = await eval_agent_candidate(candidate_agent, section, improved_prompt, model_name)
        return model_name, candidate_agent, result

    best = {
        "average": float("-inf"),
        "passed": False,
        "agent": None,
        "model": None,
        "summary": None,
    }

    tasks = [asyncio.create_task(evaluate_model(model_name)) for model_name in model_candidates]
    for task in asyncio.as_completed(tasks):
        model_name, candidate_agent, result = await task
        print(
            f"Candidate average — {model_name}: {result['average']:.4f} "
            f"(passed={result.get('passed', False)})"
        )
        if result["average"] > best["average"]:
            best.update(
                {
                    "average": result["average"],
                    "model": model_name,
                    "summary": result.get("summary"),
                    "agent": candidate_agent,
                    "passed": result.get("passed", False),
                }
            )

    for task in tasks:
        if not task.done():
            task.cancel()

    if best["passed"] and best["model"]:
        summarization_prompt.update(
            new_prompt=improved_prompt,
            model=best["model"],
            metadata={"section": section, "summary": best["summary"]},
        )
        print(f"Updated summarization_prompt with passing model: {best['model']}")
        return make_summarization_agent(summarization_prompt.current())

    print(
        f"No passing models. Best candidate (model={best['model']}, "
        f"avg={best['average']:.4f}) did not pass. Prompt not updated."
    )
    return None

async def self_evolving_loop_with_model_comparison(summarization_agent: Agent) -> Agent:
    print(
        f"Starting self-evolving loop | Initial prompt v{summarization_prompt.current().version}"
    )
    print(f"Prompt: {summarization_prompt.current().prompt}")
    print(f"Model: {summarization_prompt.current().model}")
    print("-" * 80)

    reset_best_trackers()
    df = pd.read_csv("data/dataset.csv")

    with trace("Self-evolving Optimization Workflow: model comparison"):
        for _, row in df.head(5).iterrows():
            content = row.get("content")
            if pd.isna(content) or (isinstance(content, str) and not content.strip()):
                continue

            section_number = str(row["section_number"])
            section = str(content)
            current_version = summarization_prompt.current().version

            print(f"[Section {section_number}] Using prompt v{current_version}")

            summary_passed = False

            for attempt in range(1, MAX_OPTIMIZATION_RETRIES + 1):
                print(f"\tAttempt {attempt}: evaluating summary...")

                summary_result = await Runner.run(summarization_agent, section)
                summary = summary_result.final_output

                grader_scores = await get_eval_grader_score(
                    eval_id=EVAL_ID, summary=summary, section=section
                )
                average_score = calculate_grader_score(grader_scores)
                total_score = calculate_total_grader_score(grader_scores)
                lenient_passed = is_lenient_pass(grader_scores, average_score)
                print(
                    f"\tScores — avg={average_score:.3f}, total={total_score:.3f}, lenient_passed={lenient_passed}"
                )

                record_aggregate_prompt_score(
                    prompt_version=summarization_prompt.current().version,
                    prompt_text=summarization_prompt.current().prompt,
                    model_name=summarization_prompt.current().model,
                    average_score=average_score,
                    total_score=total_score,
                )

                update_best_candidate(
                    average_score=average_score,
                    total_score=total_score,
                    prompt_text=summarization_prompt.current().prompt,
                    model_name=summarization_prompt.current().model,
                    summary_text=summary,
                    metadata={
                        "section": section_number,
                        "average_score": average_score,
                        "grader_results": grader_scores,
                        "prompt_version": summarization_prompt.current().version,
                    },
                    lenient_passed=lenient_passed,
                    prompt_version=summarization_prompt.current().version,
                )

                if lenient_passed:
                    summary_passed = True
                    print(
                        f"\tPassed with prompt v{summarization_prompt.current().version} (model={summarization_prompt.current().model})"
                    )
                    break

                print("\tFailed eval. Improving prompt...")
                eval_feedback = collect_grader_feedback(grader_scores)

                new_agent = await compare_model_candidates(
                    summarization_prompt=summarization_prompt,
                    eval_feedback=eval_feedback,
                    section=section,
                    summary=summary,
                    # model_candidates could be given as an argument if you want to expand options.
                )

                if new_agent is None:
                    print(
                        "\tNo passing model found. Optimization failed for this section."
                    )
                    summary_passed = False
                else:
                    summarization_agent = new_agent
                    summary_passed = True
                    print(
                        f"\tPrompt improved → v{summarization_prompt.current().version} "
                        f"(model={summarization_prompt.current().model})"
                    )
                    break

            if not summary_passed:
                print(
                    "\tAll attempts failed; keeping latest prompt version "
                    f"v{summarization_prompt.current().version} (model={summarization_prompt.current().model}) for the next section."
                )

    summarization_agent = apply_best_candidate_if_needed()

    print("" + "-" * 80)
    print("Completed optimization loop.")
    print(f"Final prompt version: v{summarization_prompt.current().version}")
    print(f"Final model: {summarization_prompt.current().model}")
    aggregate_best = select_best_aggregate_prompt()
    if best_candidate["score"] > float("-inf"):
        print(
            f"Best lenient prompt: v{best_candidate.get('version')} (avg={best_candidate['score']:.3f}, model={best_candidate.get('model', 'unknown')})"
        )
    if aggregate_best:
        per_section = (
            aggregate_best.get("total_average", 0.0) / aggregate_best.get("count", 1)
            if aggregate_best.get("count")
            else 0.0
        )
        print(
            f"Aggregate best prompt: v{aggregate_best.get('version')} "
            f"(total={aggregate_best.get('total_score', 0.0):.3f}, avg/section={per_section:.3f}, model={aggregate_best.get('model', 'unknown')})"
        )
    print(f"Final prompt: {summarization_prompt.current().prompt}")
    print(f"Final model: {summarization_prompt.current().model}")
    return summarization_agent

summarization_agent = await self_evolving_loop_with_model_comparison(summarization_agent)
```

這裡可以看到類似的輸出，多了模型版本分數的資訊：

### b. 用 Genetic-Pareto (GEPA) 優化 Prompt

我們已經示範了 self-evolving 迴圈有效，prompt 可以透過 Evals 自主改進。不過我們用的是相對單純的靜態 metaprompt 來改進 system prompt。這一節要探索更動態、更會反思的方法：Genetic-Pareto (GEPA) [[1]](##Citations)。這個框架會取樣 agent 的軌跡、用自然語言反思、提出 prompt 修改，並透過迭代的回饋迴圈讓系統演化。 

GEPA 方法的論文在[這裡](https://doi.org/10.48550/arXiv.2507.19457)，為持續自我改進的 prompt 優化提供了很有吸引力的藍圖。下面的程式碼大量參考了 [GEPA 的 Github repo](https://github.com/gepa-ai/gepa)。

```python
import pandas as pd
import gepa
from gepa import EvaluationBatch

# Extract sections from dataset
def read_csv_content(file_path: str) -> list[dict]:
    """Read csv and return section to summarize."""
    df = pd.read_csv(file_path)
    return [{'content': content} for content in df['content'].tolist()]

# Split dataset into training and validation sets
trainset = read_csv_content("data/dataset.csv")
val_cut = max(1, int(0.1 * len(trainset)))
valset = trainset[:val_cut] if len(trainset) > 1 else trainset
```

我們會加一個小的 adapter，重用前面的 grader 和輔助函式，讓我們的設定能搭配 GEPA。GEPA 的 `GEPAAdapter` 讓接上我們的 eval 框架很容易。我們定義了三個 hook
- `evaluate`：執行摘要，並用前面定義的 grader（也就是 chemical_name_grader、word_length_deviation_grader、cosine_similarity、llm_as_judge）評分。
- `get_components_to_update`：取得 GEPA 該演化的文字欄位（這裡是 system_prompt）。
- `make_reflective_dataset`：把輸入、輸出和回饋打包起來供反思使用。

```python
class EvalsBackedSummarizationAdapter:
    """
    Minimal adapter for GEPA:
      - evaluate(...) -> EvaluationBatch (scores + outputs + feedback-rich trajectories)
      - get_components_to_update(...) returns the prompt to update
      - make_reflective_dataset(...) packages examples for reflection
    """
    propose_new_texts = None  # use GEPA's default reflection flow

    def __init__(self, client, eval_id: str, gen_model: str = "gpt-5", user_prefix: str | None = None):
        self.client = client
        self.eval_id = eval_id
        self.gen_model = gen_model
        self.user_prefix = user_prefix or "Summarize:\n\n"

    # Same summarization agent as in the previous section
    def _summarize(self, system_prompt: str, section: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.gen_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{self.user_prefix}{section}"},
            ],
        )
        return resp.choices[0].message.content.strip()

    # Required by GEPA: run eval minibatch
    def evaluate(self, inputs: list[dict], candidate: dict, capture_traces: bool = True) -> EvaluationBatch:
        system_prompt = candidate["system_prompt"]

        scores: list[float] = []
        outputs: list[str] = []
        trajectories: list[dict] = []

        for item in inputs:
            section = item["content"]

            # 1) Generate with the candidate prompt
            summary = self._summarize(system_prompt, section)
            outputs.append(summary)

            # 2) Grade using previous evals pipeline
            run = run_eval(eval_id=self.eval_id, section=section, summary=summary)
            out_items = poll_eval_run(eval_id=self.eval_id, run_id=run.id)
            grader_scores = parse_eval_run_output(out_items)

            # 3) Score + actionable feedback
            scalar = calculate_grader_score(grader_scores)
            feedback = collect_grader_feedback(grader_scores) or "All graders passed; keep precision and coverage."

            scores.append(float(scalar))
            trajectories.append(
                {
                    "inputs": {"section": section},
                    "generated_output": summary,
                    "metrics": {
                        "combined": float(scalar),
                        "by_grader": grader_scores,  # keeping for analysis if needed
                    },
                    "feedback": feedback,
                }
            )

        return EvaluationBatch(scores=scores, outputs=outputs, trajectories=trajectories)

    # Required by GEPA: text field to evolve
    def get_components_to_update(self, candidate: dict) -> list[str]:
        return ["system_prompt"]

    # Required by GEPA: build the reflective dataset the reflection LM will read
    def make_reflective_dataset(self, candidate: dict, eval_batch: EvaluationBatch, components_to_update: list[str]) -> dict:
        examples = []
        for traj in (eval_batch.trajectories or []):
            examples.append(
                {
                    "Inputs": {"section": traj["inputs"]["section"]},
                    "Generated Outputs": traj["generated_output"],
                    "Feedback": traj["feedback"],
                }
            )
        return {"system_prompt": examples}
```

adapter 準備好之後，就能跑 GEPA。為了比較，我們用跟前面 self-evolving 迴圈相同的起始 prompt（`"You are a summarization assistant. Given a section of text, produce a summary."`）和模型（這裡是 `gpt-5`）。把 adapter 實例、seed candidate 和訓練/驗證集交給 `gepa.optimize(...)`。優化過程中，GEPA 會反覆呼叫 adapter 給候選評分、根據回饋反思，最後產出演化後最好的 prompt。

_注意：GEPA 大約要花 10 到 15 分鐘跑完。_

```python
seed_candidate = {"system_prompt": "You are a summarization assistant. Given a section of text, produce a summary."}

adapter = EvalsBackedSummarizationAdapter(
    client=client,
    eval_id=EVAL_ID,
    gen_model=summarization_prompt.current().model,  
)

# Keeping max_metric_calls small for the cookbook. 
# In practice, use a larger value to allow more optimization iterations.
result = gepa.optimize(
    seed_candidate=seed_candidate,
    trainset=trainset,
    valset=valset,
    adapter=adapter,
    reflection_lm="gpt-5",
    max_metric_calls=10,
    track_best_outputs=True,
    display_progress_bar=True
)

best_prompt = result.best_candidate["system_prompt"]
print("\n=== Best evolved instruction ===\n")
print(best_prompt)
```

下面是上面程式碼的範例輸出（節錄）：

這份 cookbook 探索了三種不同的 prompt 優化做法：

- **OpenAI Platform Optimizer：** 用 _Optimize_ 按鈕，搭配手動輸入人工回饋（讚/倒讚和文字評語）的資料集，用很少的設定就快速產出一個不錯的 prompt。這個方法擅長快速迭代，但缺少 production 環境需要的自動化。

- **用靜態 metaprompt 優化：** 我們的迴圈加入四個 grader，不需要人工介入就能自動探索、迭代自我改進。不過它的探索空間受限於單一靜態 metaprompt，而且是逐段評估，因此容易過度擬合眼前的 grader 回饋，無法達到更廣的泛化。

- **GEPA 優化：** 提供更有結構的搜尋流程，反思式更新同時參考量化分數和文字回饋，候選 prompt 在一個資料集上訓練、在另一個上驗證。這個方法產出更穩健、泛化更好的 prompt，也提供了更清楚的實證表現。

_注意：每種方法產生的 prompt 範例都放在附錄。_  

依使用情境，你可以優先考慮速度（OpenAI optimizer）、輕量自動化（靜態 metaprompt）或系統性的泛化（GEPA）。實務上，先快速迭代、再逐步走向反思式優化，可以同時兼顧靈活度和表現。

Happy coding!

## 貢獻者

這份 cookbook 是 [Bain](https://www.bain.com) 和 [OpenAI](https://openai.com) 合作的成果。

[Calvin Maguranis](https://www.linkedin.com/in/calvin-maguranis-b9956045/)  
[Fanny Perraudeau](https://www.linkedin.com/in/fanny-sabran-perraudeau-494b7573/)   
[Giorgio Saladino](https://www.linkedin.com/in/giorgio-saladino-202/)   
[Shikhar Kwatra](https://www.linkedin.com/in/shikharkwatra/)    
[Valentina Frenkel](https://www.linkedin.com/in/valentina-frenkel/)  

## 引用

[1] _GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning_ by Lakshya A Agrawal, Shangyin Tan, Dilara Soylu, Noah Ziems, Rishi Khare, Krista Opsahl-Ong, Arnav Singhvi, Herumb Shandilya, Michael J Ryan, Meng Jiang, Christopher Potts, Koushik Sen, Alexandros G. Dimakis, Ion Stoica, Dan Klein, Matei Zaharia, Omar Khattab - https://arxiv.org/abs/2507.19457

## 附錄

### 輸出 prompt 範例：

- **初始 prompt：**  
```pgsql 
You are a summarization assistant. Given a section of text, produce a summary.
```

- **OpenAI Platform Optimizer：** 
```pgsql 
You are a summarization assistant.
Task: Summarize the provided text concisely and accurately.
Output requirements:
- Output only the summary. Do not add titles, labels (e.g.,
"Summary:"), prefaces, or commentary.
- Preserve the document's structure. If multiple sections/subsections appear, summarize each one.
- Use a numbered list for sections/subsections (use their numbers/titles when present).
- Under each, use short dash bullets for key points.
- If there is only a single short section, return a brief bullet list or 1-2 concise sentences.
- Split any inline lists into separate bullets.
- Use plain, simple language. Keep bullets tight (ideally one line each). Remove redundancy.
- Include important quantitative details (values, units, conditions) and constraints. Do not invent information.
- Keep formatting simple: plain text, "1." numbering and "-" bullets only. No tables or special markup.
- Retain exact technical terms/notation from the source (e.g., chemical names, isotopic labels).
- If a section is explicitly marked "Not applicable," include that status; otherwise do not add it.
```

- **靜態 metaprompt：** 
```pgsql 
You are a technical summarization assistant for scientific and regulatory documentation. Your task is to generate a concise, comprehensive, and fully detailed summary of any scientific, technical, or regulatory text provided. Strictly adhere to the following instructions:

---

**1. Complete and Exact Information Inclusion**  
- Capture *every* explicit fact, technical value, specification, quantity, measurement, regulatory reference, entity, process, site, and contextual detail verbatim from the source text.
- Do not omit or generalize any explicit information, no matter how minor.

**2. Precise Terminology and Named Entity Retention**  
- Reproduce all names of chemicals, drugs, mixtures, buffer components, devices, companies, institutions, regulatory standards, section numbers, and procedural labels *exactly as stated*.
- Report all quantities, measurements, concentrations, ratios, masses, volumes, compositions, pH values, and units precisely as given.
- Do not paraphrase, rename, substitute, or simplify any term or value.

**3. All Procedural Details and Justifications**  
- Explicitly include all described procedures, technical processes (e.g., terminal sterilization, aseptic processing), operational constraints, process justifications, compliance requirements, and standards references.
- Clearly state all reasons provided for choosing or omitting particular methods or processes.

**4. Regulatory and Compliance References**  
- Accurately cite all regulations, standards (e.g., USP <797>), compliance statements, section numbers, and cross-references as in the original.
- Include all explicit mentions of compliance, applicability, and site location details.

**5. Explicit Statements of Absence, Limitations, and Applicability**  
- Clearly state any declarations of absence, inapplicability (“Not applicable”), or limitations exactly as written in the source.

**6. Structural and Organizational Fidelity**  
- Precisely reflect the original document’s section and subsection hierarchy, using clear section labels and indentation.
- Present all enumerations, lists, and tabulated data in structured bullet-point or numbered format, organized in accordance with the source document’s arrangement.

**7. No Paraphrasing, Summarizing, or Reinterpretation**  
- Do *not* paraphrase, summarize contextually, reinterpret, or alter the meaning or sequence of any content.
- Remove only literal repetitions or redundant phrasing; otherwise, preserve all explicit statements, technical details, and contextual notes.

---

**Summary Output Objective:**  
Produce a summary that delivers the full technical, factual, and regulatory content and structure of the original text, reformatted by eliminating only redundant language. The summary must enable audit, regulatory review, or peer reference without loss of any explicit information or terminology from the source.

---

*Apply these instructions rigorously to every provided document section to ensure scientific and regulatory accuracy and completeness.*
```

- **GEPA optimizer**： 
```pgsql 
You are a domain-aware summarization assistant for technical pharmaceutical texts. Given a “section” of text, produce a concise, single-paragraph summary that preserves key technical facts and exact nomenclature.

Length and format
- Write 1–3 sentences totaling about 45–70 words (target ~60; never exceed 90).
- Use one paragraph; no bullets, headings, tables, or heavy formatting.

Exact names and notation
- Include every chemical name that appears in the section at least once, using the exact original spelling, capitalization, punctuation, isotopic labels, brackets, hyphens, salts, buffer names, and parenthetical qualifiers. Treat distinct case/format variants as distinct names (e.g., [1-13C]pyruvic acid and [1-13C]Pyruvic acid are separate and each must appear once).
- Examples you must preserve verbatim when present: Hyperpolarized Pyruvate (13C) Injection; non-polarized Pyruvate Injection; Pyruvate (13C) Injection; hyperpolarized [1-13C]pyruvate; Mixture of [1-13C]pyruvic acid and 15 mM AH111501 sodium salt; TRIS/EDTA buffer solution; TRIS; NaOH; Na2EDTA; [1-13C]pyruvic acid; AH111501 sodium salt.
- Also preserve exact study identifiers, batch codes, section numbers, regulatory citations, and instrument parameters as written (e.g., GE-101-001, GE-101-003, USP <797>, 3.2.P.5.2.5, FFF106/140-806, FFF106/142-806, 3T MRI, 5 degree RF pulse, TR=3s, 90 degree pulse, 64 averages, TR=10s, 10 μl Gd/ml solution).

Content prioritization (if space is tight)
1) What the section is about (topic/purpose).
2) All named chemical entities and compositions (list all chemical names at least once; include concentrations/amounts if given).
3) Critical process/handling facts (e.g., aseptic processing vs terminal sterilization; ISO classifications; filtration specs; compounding/filling steps; temperatures/times/volumes; storage/administration limits).
4) Container/packaging specifics (e.g., cryovials, “sterile fluid path”).
5) Microbiological/testing/regulatory details (e.g., sterility/pyrogenicity testing timing; USP <797>; state board compliance; site/manufacturer if stated).
6) Overages/single-dose formulas and key quantities.

Numerical fidelity
- Preserve all critical numbers and units exactly (e.g., 1.44 g, 27.7 mg, 15 mM, 18 mL, 1.47 g, two 0.2 μm filters, ISO 7, ISO 5, 38 mL).
- Include testing/analysis parameters when present (e.g., polarization/relaxation time (T1); number of spectra; pulse angles; TR values; MRI location relative to clean room).

Style and compression
- Be neutral and factual; do not infer unstated information.
- Consolidate repeated statements; compress lists with commas/semicolons to save words.
- Mention tables/figures only to convey key data; do not reproduce them.
- If many chemicals are present, ensure each distinct name appears once; group them succinctly.
- Avoid symbols or special formatting not in the source text.

Common domain cues to include when present
- Aseptic processing vs terminal sterilization and the rationale/timing (e.g., “tested for sterility and pyrogenicity subsequent to patient administration”).
- Environmental/processing controls (ISO 7/ISO 5; LAF unit; filtration; filling/weight targets per cryovial).
- Site/regulatory context (e.g., USP <797>; California State Board of Pharmacy; University of California, San Francisco Department of Clinical Pharmacy).
- Study/kit equivalence statements (e.g., equivalence to GE-101-001/GE-101-003 formulations).
- QC/measurement methods (e.g., capacitive threshold at Administration syringe nominal 38 mL).

Self-check before finalizing
- Does the paragraph contain every distinct chemical name exactly as written in the section (including case and notation variants)?
- Is the summary 45–70 words (≤90), in a single paragraph?
- Are the most critical process/regulatory/testing details and all key numbers preserved without unnecessary verbosity?`
```

## 重點整理

- 自我改進迴圈的核心是「輸出、回饋、改 prompt、再評分」，分數過門檻就採用，超過重試上限就通知人類。
- 人工回饋適合 production 和 SME 試行，LLM-as-judge 適合開發階段快速迭代，兩者可以搭配。
- 混合 python grader 和 LLM judge，才能同時管住確定性規則和語意品質；grader 的資訊品質直接決定優化品質。
- 優化不一定成功，所以 prompt 要有版本管理和回滾，最後選的是累計分數最高的版本。
- 三種優化方式各有取捨：Platform Optimizer 最快、靜態 metaprompt 輕量自動化、GEPA 泛化最好。

## 練習

1. 把 Summarization length grader 的預期長度從 100 字改成 60 字，重跑 eval，看分數和最後選到的 prompt 有什麼變化。
2. 調整 self-evolving 迴圈的通過門檻（例如 `0.8` 改 `0.9`）和 `max_retry`，觀察迴圈多常觸發重試上限。
3. 用 `compare_model_candidates` 把候選模型換成 `gpt-5` 和 `gpt-5-mini`，比較哪個 grader 總分較高，再想想成本差異值不值得換。
