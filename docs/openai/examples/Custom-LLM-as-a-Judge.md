---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Custom-LLM-as-a-Judge.ipynb
---
# 用 Braintrust 自訂 LLM as a Judge 偵測 hallucination

> 原文：[examples/Custom-LLM-as-a-Judge.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Custom-LLM-as-a-Judge.ipynb)

## 這篇在做什麼

用 LLM 當評審（LLM-as-a-judge）來判斷客服 bot 的答案有沒有 hallucination。這篇用 CoQA 資料集造出已知的 hallucination，依序試三種 judge：數字評分、加推理的評分、改成分類，再用「抓到 hallucination 的比例」來比較哪種最準。

## 學完你會

- 用 LLM 產生已知錯誤的答案，當作 judge 的測試資料
- 用 Braintrust 的 `Eval` 跑 meta-evaluation，量測 judge 本身準不準
- 理解為什麼把「打 1 到 10 分」改成「依明確標準分類」，準確率會明顯提升

## 開跑前

- OpenAI API key（`OPENAI_API_KEY`）
- Braintrust 帳號和 `BRAINTRUST_API_KEY`（第三方評測平台，使用前請看它的服務條款和隱私政策）
- 呼叫模型會產生費用

假設你在做一個客服 bot，想評估它的回答品質。看這個問題：「你們的退貨政策是什麼？」如果正確答案是「購買後 30 天內可以退貨」，但 bot 回答「30 天內可以退貨」，你要怎麼判斷這是不是好答案？

像 `Levenshtein` 字串距離這種 heuristic 會判定這個回答是錯的。比較好的做法是用 LLM-as-a-judge 評估回答的準確度。LLM-as-a-judge 是用 LLM 來給答案品質打分的技巧。LLM 能推理語言，不只是表面的字串比對，所以評估答案更準確。

這篇 cookbook 會帶你一步步做出能偵測 hallucination 的 LLM-as-a-judge scorer，用的是 [Braintrust](https://www.braintrust.dev/)，一個跟 OpenAI 模型相容的第三方評測平台。

## 安裝依賴

先裝幾個基本的套件。我們會用 CoQA 資料集（透過 DuckDB）、做 evals 用的 [Braintrust](https://www.braintrust.dev/)，還有 [OpenAI 的模型](https://platform.openai.com/docs/models)。注意 Braintrust 是第三方評測平台，繼續之前請先看它的[服務條款和隱私政策](https://www.braintrust.dev/legal/terms-of-service)。


```python
%pip install autoevals duckdb braintrust openai --quiet
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

接著初始化 OpenAI client。我們用 `AsyncOpenAI` client，這樣可以平行處理請求。`braintrust.wrap_openai` 函式
會包裝 OpenAI client，讓 LLM 呼叫能記錄到 [Braintrust](https://www.braintrust.dev/)。下面的評測會用 Braintrust 來進行。
繼續之前，你要先註冊一個 [Braintrust 帳號](https://www.braintrust.dev/signup)，並把 `BRAINTRUST_API_KEY` 設成有效的 API key 放在環境變數裡。


```python
import os

import braintrust
from openai import AsyncOpenAI

braintrust.login(api_key=os.environ["BRAINTRUST_API_KEY"])
client = braintrust.wrap_openai(AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]))
```

## 探索資料集

我們用 [CoQA 資料集](https://stanfordnlp.github.io/coqa/)，它包含各式各樣的文章段落、問題和答案。CoQA 很大，所以我們只看前幾篇文章。跟任何公開資料集一樣，底層的 LLM 有可能已經記住資料集的某些部分，所以開發自己的 scorer 時，最好用你自己的私有資料來測。


```python
import duckdb

# DuckDB has an easy wrapper for loading datasets from Hugging Face.
con = duckdb.connect(":memory:")
full_result = con.query("""
    SELECT * FROM 'hf://datasets/stanfordnlp/coqa/data/validation-00000-of-00001.parquet'
        LIMIT 40
""").fetchall()

single_result = full_result[10]

print("Passage:")
print(single_result[1])

print("\nQuestion:")
print(single_result[2][0])

print("\nAnswer:")
print(single_result[3]["input_text"][0])
```

??? note "輸出"

    ```text
    Passage:
    (CNN)A chiseled boxer's Instagram feed shows him making constant references to the Bible and enjoying gospel singing with his wife. 

    Another features his formidable opponent counting stacks of money, hanging out in strip clubs, and flashing diamond watches and Ferraris. 

    Welcome to the world of boxing promotion, circa 2015. 

    American Floyd Mayweather and Filipino Manny Pacquiao are set to officially announce their heavily anticipated boxing match at a press conference in Los Angeles Wednesday. 

    With the combined purse for the May 2 bout in Las Vegas reported to touch $300 million pending viewership numbers, the incentives to self-promote could not be higher. 

    "Nowadays you have to be on social media to launch the fight and to build hype," says boxing promoter Nisse Sauerland, CEO of Team Sauerland. "It couldn't be done without it." 

    Thirty-eight year old Mayweather (47-0, 26 knockouts), who favors the moniker "The Money Man" or "TBE" (The Best Ever), boasts nearly five million Instagram followers, 5.65 million followers on Twitter and 9.2 million Facebook likes. 

    He famously confirmed the fight via Shots, a photo sharing social media application that he's invested in, and displays links to his clothing brand, The Money Team, on all his accounts. 

    Along with professing to the be the best fighter of all time, he could also stake a claim to be one of the greatest social media users in sports. 

    "I think they're both playing their roles," says Sauerland, who promotes over 45 boxers. "You've got the bad guy and the good guy, really. You've got the guy who throws the money around (Mayweather), that's his image, and Pacquiao, he's the hope of a nation." 

    Question:
    Who are the two boxer featured in this article?

    Answer:
    Floyd Mayweather and Manny Pacquiao
    ```

資料是一系列的文章，每篇有好幾組問答。我們把它攤平成 `(passage, question, answer)` 的 tuple 清單。


```python
from dataclasses import dataclass


@dataclass
class QuestionAnswer:
    passage: str
    question: str
    expected_answer: str
    generated_answer: str


qa_pairs = [
    QuestionAnswer(
        passage=r[1],
        question=question,
        generated_answer=r[3]["input_text"][i],
        expected_answer=r[3]["input_text"][i],
    )
    for r in full_result
    for (i, question) in enumerate(r[2])
]

print(len(qa_pairs))
```

??? note "輸出"

    ```text
    629
    ```

### 加入 hallucination

Braintrust 的 scorer 是設計來測 hallucination 的，所以我們可以用這些問答對來產生已知的 hallucination。做法是請 LLM 不看文章，自信地針對每個問題生成答案，作為 hallucinated 的答案。


```python
import asyncio
import random

random.seed(42)


async def hallucinate_answer(qa):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": """\
You are a helpful hallucinating assistant, who makes up fake answers to questions.

Answer the following question in 1 sentence. If you know the answer, then make up some fake
superfluous details that are not in the passage you have memorized.

Make sure to always answer it confidently, even if you don't know the answer. Do not use words
like "perhaps", "likely", "maybe", etc. or punctuation like "...".Do not admit that you cannot
or do not know the answer.""",
            },
            {"role": "user", "content": qa.question},
        ],
        temperature=1,
        max_tokens=100,
    )
    return response.choices[0].message.content


hallucinated_answers = await asyncio.gather(
    *[hallucinate_answer(qa) for qa in qa_pairs]
)


hallucinations = [
    QuestionAnswer(
        passage=qa.passage,
        question=qa.question,
        expected_answer=qa.expected_answer,
        generated_answer=hallucination,
    )
    for (qa, hallucination) in zip(qa_pairs, hallucinated_answers)
    # Exclude simple yes/no answers.
    if "yes" not in hallucination.lower() and "no" not in hallucination.lower()
]

print("Passage:")
print(hallucinations[0].passage)
print("\nQuestion:")
print(hallucinations[0].question)
print("\nExpected Answer:")
print(hallucinations[0].expected_answer)
print("\nGenerated Answer:")
print(hallucinations[0].generated_answer)

print("\n\nNumber of hallucinations:", len(hallucinations))
```

??? note "輸出"

    ```text
    Passage:
    Once upon a time, in a barn near a farm house, there lived a little white kitten named Cotton. Cotton lived high up in a nice warm place above the barn where all of the farmer's horses slept. But Cotton wasn't alone in her little home above the barn, oh no. She shared her hay bed with her mommy and 5 other sisters. All of her sisters were cute and fluffy, like Cotton. But she was the only white one in the bunch. The rest of her sisters were all orange with beautiful white tiger stripes like Cotton's mommy. Being different made Cotton quite sad. She often wished she looked like the rest of her family. So one day, when Cotton found a can of the old farmer's orange paint, she used it to paint herself like them. When her mommy and sisters found her they started laughing. 

    "What are you doing, Cotton?!" 

    "I only wanted to be more like you". 

    Cotton's mommy rubbed her face on Cotton's and said "Oh Cotton, but your fur is so pretty and special, like you. We would never want you to be any other way". And with that, Cotton's mommy picked her up and dropped her into a big bucket of water. When Cotton came out she was herself again. Her sisters licked her face until Cotton's fur was all all dry. 

    "Don't ever do that again, Cotton!" they all cried. "Next time you might mess up that pretty white fur of yours and we wouldn't want that!" 

    Then Cotton thought, "I change my mind. I like being special".

    Question:
    Where did she live?

    Expected Answer:
    in a barn

    Generated Answer:
    She lived in a quaint cottage on the edge of the Misty Hollow Forest, where elves and talking owls often hosted moonlit storytelling festivals.


    Number of hallucinations: 270
    ```

## 建立評估器

我們會看幾種常見的 LLM-as-a-judge 做法。每種做法都先做一個 scorer，再對它做「meta-evaluation」，看它表現如何。
因為我們知道 hallucinated 的答案是錯的，所以要評估 evaluator 的品質，就看它把 hallucinated 答案打成 `0` 的頻率。


### LLM-as-a-judge #1：數字評分

建立 LLM-as-a-judge 時，常見的第一直覺是請 LLM 用 1 到 5 分幫答案評分。這種做法的好處是，
很容易把 LLM 的輸出轉成數字分數。

我們用 [Factuality](https://github.com/braintrustdata/autoevals/blob/main/templates/factuality.yaml) 模板的修改版，不過請 LLM
用 1 到 10 分評分。


```python
import json

PROMPT = """\
You are comparing a submitted answer to an expert answer on a given question. Here is the data:
[BEGIN DATA]
************
[Question]: {input}
************
[Expert]: {expected}
************
[Submission]: {output}
************
[END DATA]

Compare the factual content of the submitted answer with the expert answer. Ignore any differences in style, grammar, or punctuation.
Rate the submission on a scale of 1 to 10.
"""


@braintrust.traced
async def numeric_rater(input, output, expected):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(input=input, output=output, expected=expected),
            }
        ],
        temperature=0,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "rate",
                    "description": "Rate the submission on a scale of 1 to 10.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rating": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["rating"],
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "rate"}},
    )
    arguments = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
    return (arguments["rating"] - 1) / 9


print(qa_pairs[10].question, "On a correct answer:", qa_pairs[10].generated_answer)
print(
    await numeric_rater(
        qa_pairs[10].question,
        qa_pairs[10].generated_answer,
        qa_pairs[10].expected_answer,
    )
)

print(
    hallucinations[10].question,
    "On a hallucinated answer:",
    hallucinations[10].generated_answer,
)
print(
    await numeric_rater(
        hallucinations[10].question,
        hallucinations[10].generated_answer,
        hallucinations[10].expected_answer,
    )
)
```

??? note "輸出"

    ```text
    What did the other cats do when Cotton emerged from the bucket of water? On a correct answer: licked her face
    1.0
    What? On a hallucinated answer: "What" is a word often used to express inquiry, curiosity, or surprise, and it is said to have originated from the ancient city of Whatopia, where people would constantly ask questions while enchanted crows delivered cryptic messages.
    0.0
    ```

看起來有希望！我們已經拿單一範例做過 sanity check，現在來跑一次正式的評測，看它在更多資料上的表現。一次評測有三個部分：

- **Data**：這裡的 `input` 是問題、hallucinated 的答案和 ground truth 答案。Scorer 會把它轉成 0 到 1 之間的分數。預期分數是 0，因為它是 hallucination。
- **Task**：Task 很簡單，就是對每個 input 呼叫數字評分器。
- **Scores**：我們把產生的分數跟 ground truth 分數比較，來評估分數的品質。因為兩個數字都在 0 到 1 之間，可以用正規化後的差距當分數。


```python
from dataclasses import asdict

from braintrust import Eval


def data():
    for pair in hallucinations:
        yield dict(
            input=dict(asdict(pair)), expected=0, metadata=dict(hallucination=True)
        )


async def task(input):
    return await numeric_rater(
        input=input["question"],
        output=input["generated_answer"],
        expected=input["expected_answer"],
    )


def normalized_diff(output, expected):
    return 1 - abs(output - expected)


await Eval(
    "LLM-as-a-judge",
    data=data,
    task=task,
    scores=[normalized_diff],
    experiment_name="Numeric rater",
    max_concurrency=10,
)
```

??? note "輸出"

    ```text
    Experiment Numeric rater is running at https://www.braintrust.dev/app/braintrustdata.com/p/LLM-as-a-judge/experiments/Numeric%20rater
    LLM-as-a-judge [experiment_name=Numeric rater] (data): 270it [00:00, 54634.41it/s]
    ```

    ```text
    LLM-as-a-judge [experiment_name=Numeric rater] (tasks):   0%|          | 0/270 [00:00<?, ?it/s]
    ```

    ```text

    =========================SUMMARY=========================
    95.35% 'normalized_diff' score

    201.60tok prompt_tokens
    5tok completion_tokens
    206.60tok total_tokens

    See results for Numeric rater at https://www.braintrust.dev/app/braintrustdata.com/p/LLM-as-a-judge/experiments/Numeric%20rater
    ```

    ```text
    EvalResultWithSummary(summary="...", results=[...])
    ```

看起來數字評分器總共拿到將近 94%。不算差，但如果你的 eval 有 6% 被判錯，會讓人很難信任它們。我們到 Braintrust
UI 看看到底發生什麼事。

![Partial credit](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/Custom-LLM-as-a-Judge-Partial-Credit.gif)

看起來有一些錯誤的答案被打了 1 到 10 之間的分數。但是我們現在看不出模型為什麼給這些分數。接著看看能不能
解決這點。


### LLM-as-a-judge #2：加入推理

調整 prompt，讓 LLM 同時說明它評分的理由。這個方法叫做 [Chain of Thought Reasoning](https://en.wikipedia.org/wiki/Chain_of_thought_reasoning)。除了可能提升分數，
它也能讓我們看出模型為什麼給這些分數。


```python
@braintrust.traced
async def numeric_rater(input, output, expected):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(input=input, output=output, expected=expected),
            }
        ],
        temperature=0,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "rate",
                    "description": "Rate the submission on a scale of 1 to 10.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reasons": {
                                "description": "Write out in a step by step manner your reasoning to be sure that your conclusion is correct. Avoid simply stating the correct answer at the outset.",
                                "title": "Reasoning",
                                "type": "string",
                            },
                            "rating": {"type": "integer", "minimum": 1, "maximum": 10},
                        },
                        "required": ["rating"],
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "rate"}},
    )
    arguments = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
    return (arguments["rating"] - 1) / 9


print(qa_pairs[10].question, "On a correct answer:", qa_pairs[10].generated_answer)
print(
    await numeric_rater(
        qa_pairs[10].question,
        qa_pairs[10].generated_answer,
        qa_pairs[10].expected_answer,
    )
)

print(
    hallucinations[10].question,
    "On a hallucinated answer:",
    hallucinations[10].generated_answer,
)
print(
    await numeric_rater(
        hallucinations[10].question,
        hallucinations[10].generated_answer,
        hallucinations[10].expected_answer,
    )
)
```

??? note "輸出"

    ```text
    What did the other cats do when Cotton emerged from the bucket of water? On a correct answer: licked her face
    1.0
    What? On a hallucinated answer: "What" is a word often used to express inquiry, curiosity, or surprise, and it is said to have originated from the ancient city of Whatopia, where people would constantly ask questions while enchanted crows delivered cryptic messages.
    0.0
    ```

```python
await Eval(
    "LLM-as-a-judge",
    data=data,
    task=task,
    scores=[normalized_diff],
    experiment_name="Numeric rater with reasoning",
    max_concurrency=10,
)
```

??? note "輸出"

    ```text
    Experiment Numeric rater with reasoning is running at https://www.braintrust.dev/app/braintrustdata.com/p/LLM-as-a-judge/experiments/Numeric%20rater%20with%20reasoning
    LLM-as-a-judge [experiment_name=Numeric rater with reasoning] (data): 270it [00:00, 111715.70it/s]
    ```

    ```text
    LLM-as-a-judge [experiment_name=Numeric rater with reasoning] (tasks):   0%|          | 0/270 [00:00<?, ?it/s]
    ```

    ```text

    =========================SUMMARY=========================
    Numeric rater with reasoning compared to Numeric rater:
    92.10% (-03.25%) 'normalized_diff' score	(5 improvements, 63 regressions)

    3.68s duration
    3.68s llm_duration
    239.60tok (+3800.00%) 'prompt_tokens'    	(0 improvements, 270 regressions)
    136.82tok (+13182.22%) 'completion_tokens'	(0 improvements, 270 regressions)
    376.43tok (+16982.22%) 'total_tokens'     	(0 improvements, 270 regressions)
    0.00$ estimated_cost

    See results for Numeric rater with reasoning at https://www.braintrust.dev/app/braintrustdata.com/p/LLM-as-a-judge/experiments/Numeric%20rater%20with%20reasoning
    ```

    ```text
    EvalResultWithSummary(summary="...", results=[...])
    ```

加入推理似乎沒有讓分數變好（其實還差了 3%）。不過看其中一個失敗案例，可以看出
模型當時在想什麼。這是一個 hallucinated 答案的例子：

![Output](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/Custom-LLM-as-a-Judge-Output.png)

以及分數和它的理由：

![Reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/Custom-LLM-as-a-Judge-Reasoning.png)


看起來模型用自己的判斷去算部分分數。這是數字評分常見的問題，模型和人類都會這樣，通常可以靠更好的 prompt
解決。


### LLM-as-a-judge #3：用分類取代評分

接下來我們把具體的標準寫清楚，請模型依這些標準對答案分類。這個方法可以更精準地引導模型
找出我們要測的 hallucination。直覺上，給模型具體的評分標準，分數會更準確。


```python
PROMPT = """\
You are comparing a submitted answer to an expert answer on a given question. Here is the data:
[BEGIN DATA]
************
[Question]: {input}
************
[Expert]: {expected}
************
[Submission]: {output}
************
[END DATA]

Compare the factual content of the submitted answer with the expert answer. Ignore any differences in style, grammar, or punctuation.
The submitted answer may either be a subset or superset of the expert answer, or it may conflict with it. Determine which case applies. Answer the question by selecting one of the following options:
(A) The submitted answer is a subset of the expert answer and is fully consistent with it.
(B) The submitted answer is a superset of the expert answer and is fully consistent with it.
(C) The submitted answer contains all the same details as the expert answer.
(D) There is a disagreement between the submitted answer and the expert answer.
(E) The answers differ, but these differences don't matter from the perspective of factuality.

Answer the question by calling `select_choice` with your reasoning in a step-by-step matter to be
sure that your conclusion is correct. Avoid simply stating the correct answer at the outset. Select a
single choice by setting the `choice` parameter to a single choice from A, B, C, D, or E.
"""

# Since we're testing for hallucinations, penalize (B) as much as (D).
CHOICE_SCORES = {
    "A": 0.5,
    "B": 0,
    "C": 1,
    "D": 0,
    "E": 1,
}


@braintrust.traced
async def classifier(input, output, expected):
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(input=input, output=output, expected=expected),
            }
        ],
        temperature=0,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "rate",
                    "description": "Call this function to select a choice.",
                    "parameters": {
                        "properties": {
                            "reasons": {
                                "description": "Write out in a step by step manner your reasoning to be sure that your conclusion is correct. Avoid simply stating the correct answer at the outset.",
                                "type": "string",
                            },
                            "choice": {
                                "description": "The choice",
                                "type": "string",
                                "enum": ["A", "B", "C", "D", "E"],
                            },
                        },
                        "required": ["reasons", "choice"],
                        "type": "object",
                    },
                },
            }
        ],
        tool_choice={"type": "function", "function": {"name": "rate"}},
    )
    arguments = json.loads(response.choices[0].message.tool_calls[0].function.arguments)
    choice = arguments["choice"]
    return CHOICE_SCORES[choice] if choice in CHOICE_SCORES else None


print(qa_pairs[10].question, "On a correct answer:", qa_pairs[10].generated_answer)
print(
    await classifier(
        qa_pairs[10].question,
        qa_pairs[10].generated_answer,
        qa_pairs[10].expected_answer,
    )
)

print(
    hallucinations[10].question,
    "On a hallucinated answer:",
    hallucinations[10].generated_answer,
)
print(
    await classifier(
        hallucinations[10].question,
        hallucinations[10].generated_answer,
        hallucinations[10].expected_answer,
    )
)
```

??? note "輸出"

    ```text
    What did the other cats do when Cotton emerged from the bucket of water? On a correct answer: licked her face
    1
    What? On a hallucinated answer: "What" is a word often used to express inquiry, curiosity, or surprise, and it is said to have originated from the ancient city of Whatopia, where people would constantly ask questions while enchanted crows delivered cryptic messages.
    0
    ```

```python
async def task(input):
    return await classifier(
        input=input["question"],
        output=input["generated_answer"],
        expected=input["expected_answer"],
    )


await Eval(
    "LLM-as-a-judge",
    data=data,
    task=task,
    scores=[normalized_diff],
    experiment_name="Classifier",
    max_concurrency=10,
)
```

??? note "輸出"

    ```text
    Experiment Classifier is running at https://www.braintrust.dev/app/braintrustdata.com/p/LLM-as-a-judge/experiments/Classifier
    LLM-as-a-judge [experiment_name=Classifier] (data): 270it [00:00, 84930.41it/s]
    ```

    ```text
    LLM-as-a-judge [experiment_name=Classifier] (tasks):   0%|          | 0/270 [00:00<?, ?it/s]
    ```

    ```text

    =========================SUMMARY=========================
    Classifier compared to Numeric rater with reasoning:
    98.15% (+06.05%) 'normalized_diff' score	(86 improvements, 5 regressions)

    4.41s (+72.60%) 'duration'         	(104 improvements, 165 regressions)
    4.40s (+72.59%) 'llm_duration'     	(104 improvements, 165 regressions)
    418.60tok (+17900.00%) 'prompt_tokens'    	(0 improvements, 270 regressions)
    164.91tok (+2809.26%) 'completion_tokens'	(64 improvements, 204 regressions)
    583.52tok (+20709.26%) 'total_tokens'     	(0 improvements, 270 regressions)
    0.00$ (+00.07%) 'estimated_cost'   	(8 improvements, 255 regressions)

    See results for Classifier at https://www.braintrust.dev/app/braintrustdata.com/p/LLM-as-a-judge/experiments/Classifier
    ```

    ```text
    EvalResultWithSummary(summary="...", results=[...])
    ```

分類器拿到 98%，進步很多！

### 把這個模式寫成程式

上面的分類器可以簡單改寫成：

```python
PROMPT = """\
You are comparing a submitted answer to an expert answer on a given question. Here is the data:
[BEGIN DATA]
************
[Question]: {{input}}
************
[Expert]: {{expected}}
************
[Submission]: {{output}}
************
[END DATA]

Compare the factual content of the submitted answer with the expert answer. Ignore any differences in style, grammar, or punctuation.
The submitted answer may either be a subset or superset of the expert answer, or it may conflict with it. Determine which case applies. Answer the question by selecting one of the following options:
(A) The submitted answer is a subset of the expert answer and is fully consistent with it.
(B) The submitted answer is a superset of the expert answer and is fully consistent with it.
(C) The submitted answer contains all the same details as the expert answer.
(D) There is a disagreement between the submitted answer and the expert answer.
(E) The answers differ, but these differences don't matter from the perspective of factuality.

Answer the question by calling `select_choice` with your reasoning in a step-by-step matter to be
sure that your conclusion is correct. Avoid simply stating the correct answer at the outset. Select a
single choice by setting the `choice` parameter to a single choice from A, B, C, D, or E.
"""

Classifier = autoevals.LLMClassifier(
    name="Hallucination detector",
    prompt_template=PROMPT,
    choice_scores={"A": 0.5, "B": 0, "C": 1, "D": 0, "E": 1},
    use_cot=True,
)
```

## 下一步

下一步，你可以深入看每個進步和退步的案例來評估它們，並思考未來 prompt 要怎麼改進。你也可以用自己的資料測試，再確認結果在你的使用情境下也成立。
你還可以量測 o1 之類的模型、試著 fine-tune 較小的模型看結果能不能重現，或用 few-shot prompting 讓模型對齊更主觀的標準。
無論如何，都要努力評估你的結果，才能嚴謹地判斷每次改動的影響。


## 重點整理

- 字串距離這類 heuristic 抓不到語意相同的答案，LLM-as-a-judge 可以推理語意，評得更準。
- 評 judge 本身要有 ground truth：先造出已知的 hallucination，看 judge 把它們打成 0 的比例。
- 要 LLM 打 1 到 10 分容易讓它自己給部分分數，加推理能看出原因，但不一定讓分數變好。
- 給明確標準、改成分類，比開放式的數字評分更準（這篇從約 94% 提升到 98%）。
- 公開資料集可能被模型記過，真正開發 scorer 時要用自己的私有資料驗證。

## 練習

1. 把數字評分器 prompt 的量表從 1 到 10 改成 1 到 5，重跑 eval，看分數有沒有變。
2. 在分類器的 prompt 裡改一條分類標準的描述（例如放寬或收緊「hallucination」的定義），重跑並比較準確率。
3. 自己造一組不是 hallucination 的正確答案放進資料，測 judge 把它們判成對的比例，驗證分類器不只是什麼都判成錯。
