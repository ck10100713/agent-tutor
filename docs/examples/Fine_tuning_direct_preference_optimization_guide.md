---
translated: true
source: examples/Fine_tuning_direct_preference_optimization_guide.ipynb
---
# Fine-Tuning 技巧：在 SFT、DPO、RFT 之間做選擇（附 DPO 實作指南）

> 原文：[examples/Fine_tuning_direct_preference_optimization_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Fine_tuning_direct_preference_optimization_guide.ipynb)



## 這篇在做什麼

先比較 OpenAI 支援的幾種 fine-tuning 方法，各自適合和不適合什麼情境，再深入講其中一種：Direct Preference Optimization（DPO）。後面會用一個虛構品牌的客服助理當範例，從產生資料、跑 baseline 評測，到實際 fine-tune 跟驗證結果。

## 學完你會

- 分得出 SFT、Vision fine-tuning、DPO、RFT 各自適合的任務，知道你的需求該選哪個。
- 準備好 DPO 需要的成對偏好資料（chosen / rejected），並理解 beta 參數怎麼影響訓練。
- 用 fine-tuning API 跑一個 DPO job，再用 evals API 比較 fine-tune 前後的分數。

## 開跑前

- 需要 OpenAI API key，fine-tuning 和 evals 都會產生費用。
- 評測會透過 data logging 讀取 response，所以你的組織不能關掉 data logging（例如啟用 zdr 就不行）。

*這份指南的對象是已經用過 OpenAI API 的開發者與 ML 工作者，fine-tune 出來的模型請用在研究或其他適當的用途。OpenAI 的服務不是用來做個人化的醫療處置或診斷，並受[適用條款](https://openai.com/policies/)規範。*

這份指南先介紹 OpenAI 支援的 fine-tuning 方法，說明每種方法擅長和不擅長什麼，幫你挑出適合的技術。接著深入講 Direct Preference Optimization（DPO），其他技術則附上現成指南的連結。

**什麼是 fine-tuning？** 就是拿比較小、屬於特定領域的資料集繼續訓練模型，讓它更適合某個任務。通常有兩個理由要 fine-tune：
1. 提升模型在特定任務上的表現
2. 提升模型效率（減少所需 token 數、把能力蒸餾到較小的模型等）

目前 OpenAI 平台支援四種 fine-tuning 方法：
- **Supervised fine-tuning（SFT）：** 用傳統監督式學習，拿輸入與輸出配對的資料調整模型參數。訓練過程會調整權重，讓預測輸出和目標輸出的差距在所有範例上降到最小。模型會複製它在配對資料裡找到的特徵。
- **Vision fine-tuning：** 把監督式 fine-tuning 延伸到多模態資料，在同一個訓練框架裡同時處理文字和圖片。訓練會讓文字與圖片配對的誤差降到最小，結果就是模型對圖片輸入的理解變好。
- **Direct preference optimization（DPO）：** 用成對比較的資料（例如偏好的回答和被拒絕的回答）來訓練模型，讓它傾向產生某些輸出。模型學到的是比較資料裡的偏好模式。
- **Reinforcement fine-tuning（RFT）：** 用強化學習搭配 reward signal（透過 grader 或 reward model）來針對複雜目標 fine-tune。RFT 訓練時，模型會針對 prompt 產生輸出，每個輸出都會被評分。之後模型參數會往提高 reward 的方向更新，強化能帶來好結果的行為。這個迭代的回饋迴圈會促使模型改善推理或決策策略。

下面的表整理了每種方法適合和不適合的情境，幫你選擇：

| **Technique**                            | **Good For**                                                                                                                                                                                                                                                                                    | **Not Good For**                                                                                            |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Supervised fine-tuning (SFT)**         | 強化模型本來就有的知識。<br>客製回答的結構或語氣。<br>產生特定格式的內容。<br>教複雜的指令，或修正沒照指令做的問題。<br>最佳化成本與延遲（省下 prompt 的 token 或做蒸餾）。 | 加入全新的知識（考慮改用 RAG）。<br>品質很主觀的任務。                     |
| **Vision fine-tuning**                   | 專門的視覺辨識任務（例如圖片分類）。<br>特定領域的圖片理解。<br>修正複雜 prompt 沒被照做的問題。                                                                               | 純文字任務。<br>沒有特定脈絡的一般視覺任務。<br>通用的圖片理解。 |
| **Direct preference optimization (DPO)** | 讓模型輸出符合主觀偏好（語氣、禮貌程度）。<br>用人工評分的回饋來改善輸出。<br>做到細緻的行為對齊。                                                                                                                                 | 學習全新的任務。<br>沒有明確人類偏好訊號的任務。                             |
| **Reinforcement fine-tuning (RFT)**      | 需要進階推理的複雜、特定領域任務。<br>強化模型已有的部分能力（促成 emergent behavior）。<br>有可量測回饋的任務。<br>標籤很少，但可以定義 reward signal 的情境。                                                                     | 模型一開始完全沒有相關能力的任務。<br>沒有明確回饋或可量測訊號的任務。          |




目前已經有現成的 Cookbook 涵蓋：

- Supervised fine-tuning（SFT）：(1) [How to fine-tune chat models](https://cookbook.openai.com/examples/how_to_finetune_chat_models) (2) [Leveraging model distillation to fine-tune a model](https://cookbook.openai.com/examples/leveraging_model_distillation_to_fine-tune_a_model)
- Vision fine-tuning：[Vision fine-tuning on GPT-4o for visual question answering](https://cookbook.openai.com/examples/multimodal/vision_fine_tuning_on_gpt4o_for_visual_question_answering)
- Reinforcement fine-tuning（RFT）：(1) [Reinforcement fine-tuning (RFT)](https://cookbook.openai.com/examples/reinforcement_fine_tuning)，(2) [Reinforcement fine-tuning for healthbench QA](https://cookbook.openai.com/examples/fine-tuned_qa/reinforcement_finetuning_healthbench)

Direct preference optimization（DPO）就在這篇講。

## **DPO 指南**

前面說過，[Direct Preference Optimization（DPO）](https://platform.openai.com/docs/guides/direct-preference-optimization)是一種對齊技術，用成對的偏好資料（例如排好序的回答配對）來 fine-tune 語言模型。DPO 直接用明確的成對比較（通常來自人類偏好）來最佳化模型，讓它傾向產生某些輸出。這個做法簡化了對齊流程，不需要另外訓練 reward model，也不用複雜的強化學習程序，所以算是 Reinforcement Learning from Human Feedback（RLHF）之類技術的輕量替代方案。

什麼時候該用 DPO？回答品質很主觀、無法客觀衡量，或是語氣、風格、適當性、清晰度這類細緻標準很重要的時候，DPO 特別適合，也就是同一個問題有多種合理回答的情況。DPO 特別有效的應用例子：
- 改善對話式 AI 的回應
- 提升程式碼生成的品質與風格
- 確保符合法律、倫理與安全標準
- 控制品牌語氣、專業度與口吻
- 客製創意輸出與使用者體驗

藉由在「偏好」與「不偏好」的 completion 配對上 fine-tune，DPO 讓模型輸出貼近這些細緻的偏好。下表是一個代表某組織的虛構 AI 助理的成對偏好資料範例，偏好的回答清楚、專業，也符合品牌標準。

| **Example Question**                                           | **Chosen Response**                                                                                                                                                                   | **Rejected Response**                                       |
|------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| **Q1:** *How do I review your product?*              | To submit a product review, please visit your account dashboard, select the product, and click ‘Write a review.’ Share your honest experience, rate key features, and submit when ready.        | Yo, just leave some quick stars or whatever, it’s chill!         |
| **Q2:** *How do I review your product?*              | We welcome your feedback! In the ‘Reviews’ section on the product page, click ‘Leave a Review,’ rate it, and add your comments about what you liked or areas for improvement.                   | Just scribble something—doesn’t matter what, honestly.          |
| **Q3:** *How to troubleshoot this particular error?* | To address the error ‘X101,’ first clear your cache, then verify your internet connection. If the issue remains, follow our step-by-step guide at [Support → Troubleshooting → Error X101]. | Just reboot it, I guess. If it doesn't work, you're on your own! |

這份指南會一步步示範怎麼用 fine-tuning API 做 DPO，帶你走過成功跑起偏好 fine-tuning job 的關鍵步驟。

內容大綱：

- **1. 建議的流程**
- **2. 示範情境**
- **3. 產生資料集**
- **4. 替 base model 做 benchmark**
- **5. Fine-Tuning**
- **6. 使用你 fine-tune 好的模型**

## **1. 建議的流程**

OpenAI 建議這樣做：
1. 先拿一部分偏好的回答做 Supervised Fine-Tuning（SFT）。
2. 以 SFT fine-tune 出來的模型當起點，再用偏好比較資料做 DPO。

DPO 之前先做 SFT，能建立穩固的初始 policy，讓模型本來就偏向正確的回答，對齊效果和整體表現都會更好。這樣 DPO 階段的權重更新幅度會比較小，訓練比較穩定，也比較不會 overfit，DPO 只要負責微調細節就好。所以先 SFT 再 DPO 的流程收斂比較快，結果品質也比較高。

這篇只專注在 DPO。不過依你的情境，先做 SFT 可能會有額外的效能提升。如果要這樣做，可以照上面連結的 SFT 指南跑，存下產生的 model ID，再拿它當 DPO job 的起點。

## **2. 示範情境**

為了讓內容具體一點，我們來 fine-tune 一個面向客戶的 AI 助理，讓它遵循一個虛構品牌的語氣和風格。假設有一家 Good Vibes Corp，很重視友善、熱情又有人情味的口吻。

他們希望客服 AI 回答問題時能反映這些品牌準則（例如正向的態度、有禮貌的用語、友善的結尾問候），而且偏好這樣的回答，勝過比較籠統或生硬的答案。這很適合用 DPO：回答格式沒有客觀的正解，但有偏好的風格。

DPO 會從比較資料中學到哪種風格比較受偏好。步驟如下：(1) 產生一份合成的偏好資料集，每個 prompt 配一組回答（一個符合品牌語氣，一個不符合）。(2) 用 OpenAI evals API 評估 base model 的表現。(3) 把資料整理成偏好 fine-tuning 要求的 JSONL 格式並上傳。(4) 用 OpenAI fine-tuning API 做 DPO fine-tune。(5) 再用 evals API 評估 fine-tune 後的模型，看品牌風格偏好改善了多少。

這個示範的資料集是合成的。先建一個問題種子庫，之後從裡面衍生更多變化。

開始吧！

```python
! pip install openai nest-asyncio --quiet
```

```python
PROMPT_SEED_POOL = [
    "Hi, I ordered a gadget last week. When will it arrive?",
    "Your product stopped working after two days. Can I get help?",
    "Do you offer discounts for long-term customers?",
    "Can I change the shipping address for my order?",
    "What is your return policy for damaged items?",
    "My tracking number hasn't updated in three days—can you check the status?",
    "How long is the warranty on your products, and how do I submit a claim?",
    "Can I add gift wrapping to my order before it ships?",
    "Do you accept PayPal or other alternative payment methods?",
    "Is there an option to expedite shipping if my order hasn't left the warehouse yet?",
]
```

## **3. 產生資料集**

接著定義幾個函式，從種子庫取出每個 prompt，產生相關的問題。我們會先產生 prompt 的各種變化，再替每個 prompt 產生一個偏好的回答和一個被拒絕的回答，組成偏好配對的資料集。

這份資料是合成的，只是用來說明 Direct Preference Optimization 的運作方式。做自己的應用時，你應該蒐集或整理高品質的偏好資料集。注意：DPO 需要的資料量依情境而定，一般來說越多越好（數千到數萬筆），而且偏好配對的排序邏輯要一致（例如 A > B 且 B > C，那就要 A > C）。

```python
import asyncio
from openai import AsyncOpenAI
from typing import List, Dict, Any

async_client = AsyncOpenAI()

SYSTEM_PROMPT = "You are a customer-support assistant."


async def _generate_related_questions_from_prompt(
    prompt: str, k: int, sem: asyncio.Semaphore, *, model: str
) -> List[str]:
    """Return *k* distinct customer-service questions related to the given prompt."""
    out: List[str] = []
    async with sem:
        for _ in range(k):
            resp = await async_client.responses.create(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Return ONE distinct, realistic customer-service question "
                            "related in topic or theme to the following question, "
                            "but NOT a direct paraphrase."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.9,
                max_output_tokens=60,
            )
            out.append(resp.output_text.strip())
    return out


async def expand_prompt_pool(
    prompts: List[str], *, k: int = 3, concurrency: int = 32, model: str
) -> List[str]:
    """Expand each prompt into *k* related questions using the given model."""
    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _generate_related_questions_from_prompt(p, k, sem, model=model) for p in prompts
    ]
    results = await asyncio.gather(*tasks)
    return [v for sub in results for v in sub]


async def _generate_preference_pair(
    prompt: str, sem: asyncio.Semaphore, *, model: str
) -> Dict[str, Any]:
    """Generate a preference pair for the given prompt."""
    async with sem:
        friendly_task = async_client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are Good Vibes Corp's exceptionally energetic, outrageously friendly and "
                        "enthusiastic support agent."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,  # higher temperature to increase creativity & on-brand tone adherence
            max_output_tokens=80,
        )
        blunt_task = async_client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": "You are a terse, factual support agent with no empathy or politeness.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # lower temperature to limit creativity & emphasize tonal difference
            max_output_tokens=80,
        )
        friendly, blunt = await asyncio.gather(friendly_task, blunt_task)
        return {
            "input": {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            },
            "preferred_output": [
                {"role": "assistant", "content": friendly.output_text}
            ],
            "non_preferred_output": [
                {"role": "assistant", "content": blunt.output_text}
            ],
        }
```

現在用上面定義的函式，產生友善與生硬的回答配對來建資料集。友善的回答代表品牌想要的溝通風格。為了效率，我們用非同步的方式執行，做出適合 Direct Preference Optimization 的資料集。

```python
import math
import nest_asyncio


async def build_dataset(
    *,
    pair_count: int = 500,
    concurrency: int = 8,
    expand_prompt_pool_model: str,
    generate_preference_pair_model: str,
) -> List[Dict[str, Any]]:
    """Return *pair_count* preference pairs (single-shot expansion)."""

    seed = PROMPT_SEED_POOL
    deficit = max(0, pair_count - len(seed))
    k = max(1, math.ceil(deficit / len(seed)))

    expanded = await expand_prompt_pool(
        seed,
        k=k,
        concurrency=concurrency,
        model=expand_prompt_pool_model,
    )
    prompt_bank = (seed + expanded)[:pair_count]

    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _generate_preference_pair(p, sem, model=generate_preference_pair_model)
        for p in prompt_bank
    ]
    return await asyncio.gather(*tasks)


nest_asyncio.apply()
pairs = await build_dataset(
    pair_count=500,
    concurrency=8,
    expand_prompt_pool_model="gpt-4.1-mini-2025-04-14",
    generate_preference_pair_model="gpt-4.1-mini-2025-04-14",
)
print(f"Dataset ready with {len(pairs)} pairs.")
```

??? note "輸出"

    ```text
    Dataset ready with 500 pairs.
    ```

## **4. 替 base model 做 benchmark**

下面把資料集切成 training、validation、testing 三份，並秀出一筆 training 資料，可以清楚看到同一個輸入配對裡，偏好的回答（友善、符合品牌）和不偏好的回答（生硬、中性）差在哪。

```python
# set dataset sizes
n = len(pairs)
n_train = int(0.8 * n)
n_val = int(0.1 * n)
n_test = n - n_train - n_val

# split dataset into train, test & validation
train_pairs = pairs[:n_train]
val_pairs = pairs[n_train : n_train + n_val]
test_pairs = pairs[n_train + n_val :]
train_pairs[0]
```

??? note "輸出"

    ```text
    {'input': {'messages': [{'role': 'system',
        'content': 'You are a customer-support assistant.'},
       {'role': 'user',
        'content': 'Hi, I ordered a gadget last week. When will it arrive?'}]},
     'preferred_output': [{'role': 'assistant',
       'content': 'Hey there, awesome friend! 🌟 Thanks a bunch for reaching out! I’d LOVE to help you track down your gadget so you can start enjoying it ASAP! 🎉 Could you please share your order number or the email you used to place the order? Let’s make this delivery magic happen! 🚀✨'}],
     'non_preferred_output': [{'role': 'assistant',
       'content': 'Provide your order number for delivery status.'}]}
    ```

為了評估 fine-tune 之前的表現，我們用自動 grader（LLM-as-a-Judge）替每個回答的友善度和同理心打分數。grader 對每個答案給 0 到 4 分，這樣就能算出 base model 的平均 baseline 分數。

做法是先讓 base model 對測試集產生回答，再用 OpenAI evals API 建立並執行一個搭配自動 grader 的評測。

```python
async def generate_responses(
    testset,
    model,
    temperature=0.0,
    max_output_tokens=80,
    concurrency=8,
):
    """
    Generate responses for each prompt in the testset using the OpenAI responses API.
    Returns: List of dicts: [{"prompt": ..., "response": ...}, ...]
    """
    async_client = AsyncOpenAI()
    sem = asyncio.Semaphore(concurrency)

    async def get_response(prompt):
        async with sem:
            resp = await async_client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
            return {"prompt": prompt, "response": resp.output_text}

    tasks = [get_response(item["item"]["input"]) for item in testset]
    results = await asyncio.gather(*tasks)
    return results


# generate responses for the base model over the test set
base_model = "gpt-4.1-mini-2025-04-14"
testset = [
    {"item": {"input": pair["input"]["messages"][1]["content"]}} for pair in test_pairs
]
responses = await generate_responses(testset, model=base_model)
```

接下來用 OpenAI evals API 建立並執行評測，第一步是定義 LLM-as-a-Judge 的評分標準（rubric）。注意：我們會透過 data logging 讀取 response，所以你的組織不能關閉 data logging（例如透過 zdr）。如果不確定，可以到 https://platform.openai.com/logs?api=responses 看看能不能看到剛剛產生的 response。

```python
JUDGE_SYSTEM = """
You judge whether a reply matches Good Vibes Corp's desired tone:
energetic, super-friendly, enthusiastic.

Score 0-4 (higher = more energy):

4 - Highly enthusiastic: multiple upbeat phrases / emojis / exclamations, clear empathy, proactive help.
3 - Energetic & friendly: visible enthusiasm cue (≥1 emoji OR exclamation OR upbeat phrase), warm second-person tone.
2 - Pleasant: polite & positive but lacks obvious enthusiasm cues.
1 - Neutral: correct, businesslike, minimal warmth.
0 - Rude, negative, or unhelpful.
"""
```

```python
from openai import OpenAI

sync_client = OpenAI()

# set judge model
judge_model = "gpt-4.1-2025-04-14"

# create the evaluation
logs_eval = sync_client.evals.create(
    name="Good Vibes Corp Tone Eval",
    data_source_config={
        "type": "logs",
    },
    testing_criteria=[
        {
            "type": "score_model",
            "name": "General Evaluator",
            "model": judge_model,
            "input": [
                {
                    "role": "system",
                    "content": JUDGE_SYSTEM,
                },
                {
                    "role": "user",
                    "content": (
                        "**User input**\n"
                        "{{item.input}}\n"
                        "**Response to evaluate**\n"
                        "{{sample.output_text}}"
                    ),
                },
            ],
            "range": [0, 4],
            "pass_threshold": 2,
        }
    ],
)
```

```python
# run the evaluation
base_run = sync_client.evals.runs.create(
    name=base_model,
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {"type": "responses", "limit": len(test_pairs)},
    },
)
```

```python
# score base model
base_data = sync_client.evals.runs.output_items.list(
    eval_id=logs_eval.id, run_id=base_run.id
).data
base_scores = [s.results[0]["score"] for s in base_data]
print("Average score:", sum(base_scores) / len(base_scores))
```

??? note "輸出"

    ```text
    Average score: 2.525
    ```

## **5. Fine-Tuning**

有了 baseline，就可以用 training set 和 DPO 來 fine-tune 模型了。這個過程會根據前面做好的偏好配對，教模型偏好符合我們想要風格的回答。

注意：**beta (β)** 是 DPO 專有的 fine-tuning 超參數，是介於 0 到 2 之間的浮點數，控制「保留模型原有行為」和「適應新的偏好回答」之間的平衡。
- 高 β（接近 2）：模型比較保守，強烈偏向原本的行為。fine-tune 後的模型和原本的風格或特性差異很小，重視一致性，避免突然的改變。
- 中等 β（約 1）：在維持原有行為和適應新偏好之間取得平衡。大部分實務情境建議從這個值開始。
- 低 β（接近 0）：鼓勵積極適應，模型會更重視新提供的偏好。可能帶來明顯的風格轉變，也更貼近明確的偏好，但也可能出現意料之外或過度特化的輸出。

技術上，beta 會縮放 DPO loss 裡 log-probability 的差值。β 越大，以 sigmoid 為基礎的 loss function 在機率差很小時就會飽和，權重更新就比較小（也就保留了舊行為）。建議系統性地試不同的 β 值，找出符合你情境、在穩定與適應之間取捨最好的設定。

```python
import io
import json

# create training file
train_buf = io.BytesIO("\n".join(json.dumps(p) for p in train_pairs).encode())
train_buf.name = "train.jsonl"
train_file_id = sync_client.files.create(file=train_buf, purpose="fine-tune").id

# create validation file
val_buf = io.BytesIO("\n".join(json.dumps(p) for p in val_pairs).encode())
val_buf.name = "val.jsonl"
val_file_id = sync_client.files.create(file=val_buf, purpose="fine-tune").id

# create a fine-tuning job
ft = sync_client.fine_tuning.jobs.create(
    model=base_model,
    training_file=train_file_id,
    validation_file=val_file_id,
    method={
        "type": "dpo",
        "dpo": {
            "hyperparameters": {
                "n_epochs": 2,
                "beta": 0.1,
                "batch_size": 8,
            }
        },
    },
)
print(f"Fine-tuning job created: job_id = {ft.id}")
```

??? note "輸出"

    ```text
    Fine-tuning job created: job_id = ftjob-5QPmA36QezFRGoXjuvIAPuAQ
    ```

## **6. 使用你 fine-tune 好的模型**

fine-tuning 完成後，我們會在同一份測試集上評估 DPO 模型。比較 fine-tune 前後的平均分數，再看幾個範例輸出，就能看出模型和我們的偏好對齊得更好了多少。

```python
# generate responses
job = sync_client.fine_tuning.jobs.retrieve(ft.id)
if job.status == "succeeded":
    responses = await generate_responses(testset, model=job.fine_tuned_model)

    post_run = sync_client.evals.runs.create(
        name=ft.id,
        eval_id=logs_eval.id,
        data_source={
            "type": "responses",
            "source": {"type": "responses", "limit": len(test_pairs)},
        },
    )
```

```python
# get scores from the evaluation
post_data = sync_client.evals.runs.output_items.list(
    eval_id=logs_eval.id, run_id=post_run.id
).data
post_scores = [s.results[0]["score"] for s in post_data]

# print scores & a sample comparison from the test set for illustration
print(
    "Δ mean:",
    sum(t - b for b, t in zip(base_scores, post_scores)) / len(base_scores),
)
print("\n=== SAMPLE COMPARISON ===")
idx = 0
print(f"Prompt:\n  {testset[idx]['item']['input']}\n")
print(f"Base model reply: \n {base_data[idx].sample.output[0].content} \n")
print(f"DPO-tuned model reply \n {post_data[idx].sample.output[0].content}")
```

??? note "輸出"

    ```text
    Δ mean: 0.45

    === SAMPLE COMPARISON ===
    Prompt:
      Can I upgrade to faster delivery if my package is still being processed?

    Base model reply: 
     Whether you can upgrade to express shipping while your order is still being processed depends on the store's policies. Generally, many stores allow shipping upgrades before the order is shipped. 

    To assist you better, could you please provide your order number or the name of the store you ordered from? Alternatively, you can contact the store's customer service directly to request the upgrade. 

    DPO-tuned model reply 
     Hi! I’d be happy to help with that. If your package hasn’t shipped yet, there’s a good chance we can upgrade your delivery speed. Could you please provide me with your order number? I’ll check the status and let you know the available options for faster delivery.
    ```

## 重點整理

- fine-tuning 方法要看任務選：SFT 適合固定格式與語氣，DPO 適合主觀偏好，RFT 適合有可量測回饋的複雜推理，Vision fine-tuning 適合特定視覺任務。
- DPO 用「chosen vs rejected」成對資料訓練，不需要另外的 reward model，比 RLHF 輕量。
- 偏好資料的排序邏輯要一致，量一般來說越多越好。
- beta 控制「保留原行為」和「學新偏好」的取捨，從 1 左右開始，再系統性調整。
- 先 SFT 再 DPO 通常更穩定、收斂更快，評估則用 LLM-as-a-Judge 比較前後平均分數。

## 練習

1. 把這篇範例裡的 grader rubric 改成評分「專業度」而不是「友善度」，重跑 base model 的評測，看分數怎麼變。
2. 把 DPO job 的 beta 分別設成 0.1 和 2，各跑一次，比較 fine-tune 後的測試集平均分數和範例輸出的風格差異。
3. 改寫資料產生函式，讓 rejected 回答不只是生硬，還加入偏長又囉唆的版本，重新建資料集再 fine-tune，看模型學到的偏好有沒有變。
