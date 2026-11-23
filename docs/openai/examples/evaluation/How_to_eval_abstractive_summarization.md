---
translated: true
source: examples/evaluation/How_to_eval_abstractive_summarization.ipynb
---
# 如何評估摘要任務

> 原文：[examples/evaluation/How_to_eval_abstractive_summarization.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/How_to_eval_abstractive_summarization.ipynb)



## 這篇在做什麼

拿一個很小的摘要例子，比較三種評估摘要品質的方法：傳統的 ROUGE、用 BERT embedding 的 BERTScore，還有讓 gpt-4 當評審的 G-Eval 風格評分。重點是看這幾種方法對同一組摘要給出的結論有什麼不同。

## 學完你會

- 用 `rouge` 跟 `bert_score` 套件算出兩份摘要對參考摘要的分數
- 寫出針對 Relevance、Coherence、Consistency、Fluency 的 prompt，讓 gpt-4 以 1 到 5 分打分數
- 判斷什麼情況下傳統指標會失真，以及 LLM 評審有哪些偏差要小心

## 開跑前

需要 OpenAI API key（呼叫 gpt-4 要付費）。


現在這篇要談的是摘要任務的評估技巧，我們用一個簡單的例子來看。除了 [ROUGE](https://aclanthology.org/W04-1013/) 和 [BERTScore](https://arxiv.org/abs/1904.09675) 這些傳統方法，也會示範比較新的做法：拿 LLM 當評審。

評估摘要品質很花時間，因為要看連貫性、簡潔度、可讀性、內容等不同面向。`ROUGE`、`BERTScore` 這類自動指標很明確也穩定，但跟摘要的實際品質不一定吻合。它們跟人類判斷的相關性偏低，尤其是開放式生成任務（[Liu et al., 2023](https://arxiv.org/pdf/2303.16634.pdf)）。所以越來越需要靠人工評估、使用者回饋或 model-based 指標，同時要留意其中的偏差。人工判斷很有價值，但通常很難擴大規模，成本也高。

除了傳統指標，這篇也示範 [G-Eval](https://arxiv.org/pdf/2303.16634.pdf) 這個方法，它把 LLM 當成不需要參考答案（reference-free）的新指標，用來評估摘要。這裡用 `gpt-4` 幫候選輸出打分。`gpt-4` 內部已經學到一套語言品質的模型，能分辨流暢連貫的文字和低品質的文字。利用這個內部評分機制，就能自動評估 LLM 產生的新輸出。


## 環境設定


```python
# Installing necessary packages for the evaluation
# rouge: For evaluating with ROUGE metric
# bert_score: For evaluating with BERTScore
# openai: To interact with OpenAI's API
!pip install rouge --quiet
!pip install bert_score --quiet
!pip install openai --quiet
```

```python
from openai import OpenAI
import os
import re
import pandas as pd

# Python Implementation of the ROUGE Metric
from rouge import Rouge

# BERTScore leverages the pre-trained contextual embeddings from BERT and matches words in candidate and reference sentences by cosine similarity.
from bert_score import BERTScorer

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

??? note "輸出"

    ```text
    <IPython.core.display.Javascript object>
    ```

## 範例任務

這篇用下面這個摘要例子。注意我們準備了兩份要比較的系統生成摘要，以及一份人寫的參考摘要，`ROUGE` 和 `BERTScore` 這類指標需要參考摘要才能算。

原文節錄（`excerpt`）：

> OpenAI's mission is to ensure that artificial general intelligence (AGI) benefits all of humanity. OpenAI will build safe and beneficial AGI directly, but will also consider its mission fulfilled if its work aids others to achieve this outcome. OpenAI follows several key principles for this purpose. First, broadly distributed benefits - any influence over AGI's deployment will be used for the benefit of all, and to avoid harmful uses or undue concentration of power. Second, long-term safety - OpenAI is committed to doing the research to make AGI safe, and to promote the adoption of such research across the AI community. Third, technical leadership - OpenAI aims to be at the forefront of AI capabilities. Fourth, a cooperative orientation - OpenAI actively cooperates with other research and policy institutions, and seeks to create a global community working together to address AGI's global challenges.

摘要：

| Reference Summary /`ref_summary` (human generated)                                                                                                                                                                                                                                                                                                                         | Eval Summary 1 / `eval_summary_1` (system generated)                                                                                                                                                                                                                                                                                                                               | Eval Summary 2 / `eval_summary_2` (system generated)                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| OpenAI aims to ensure artificial general intelligence (AGI) is used for everyone's benefit, avoiding harmful uses or undue power concentration. It is committed to researching AGI safety, promoting such studies among the AI community. OpenAI seeks to lead in AI capabilities and cooperates with global research and policy institutions to address AGI's challenges. | OpenAI aims to AGI benefits all humanity, avoiding harmful uses and power concentration. It pioneers research into safe and beneficial AGI and promotes adoption globally. OpenAI maintains technical leadership in AI while cooperating with global institutions to address AGI challenges. It seeks to lead a collaborative worldwide effort developing AGI for collective good. | OpenAI aims to ensure AGI is for everyone's use, totally avoiding harmful stuff or big power concentration. Committed to researching AGI's safe side, promoting these studies in AI folks. OpenAI wants to be top in AI things and works with worldwide research, policy groups to figure AGI's stuff. |

先想一下，你自己比較喜歡哪一份摘要，哪一份又最能抓到 OpenAI 的使命。


```python
excerpt = "OpenAI's mission is to ensure that artificial general intelligence (AGI) benefits all of humanity. OpenAI will build safe and beneficial AGI directly, but will also consider its mission fulfilled if its work aids others to achieve this outcome. OpenAI follows several key principles for this purpose. First, broadly distributed benefits - any influence over AGI's deployment will be used for the benefit of all, and to avoid harmful uses or undue concentration of power. Second, long-term safety - OpenAI is committed to doing the research to make AGI safe, and to promote the adoption of such research across the AI community. Third, technical leadership - OpenAI aims to be at the forefront of AI capabilities. Fourth, a cooperative orientation - OpenAI actively cooperates with other research and policy institutions, and seeks to create a global community working together to address AGI's global challenges."
ref_summary = "OpenAI aims to ensure artificial general intelligence (AGI) is used for everyone's benefit, avoiding harmful uses or undue power concentration. It is committed to researching AGI safety, promoting such studies among the AI community. OpenAI seeks to lead in AI capabilities and cooperates with global research and policy institutions to address AGI's challenges."
eval_summary_1 = "OpenAI aims to AGI benefits all humanity, avoiding harmful uses and power concentration. It pioneers research into safe and beneficial AGI and promotes adoption globally. OpenAI maintains technical leadership in AI while cooperating with global institutions to address AGI challenges. It seeks to lead a collaborative worldwide effort developing AGI for collective good."
eval_summary_2 = "OpenAI aims to ensure AGI is for everyone's use, totally avoiding harmful stuff or big power concentration. Committed to researching AGI's safe side, promoting these studies in AI folks. OpenAI wants to be top in AI things and works with worldwide research, policy groups to figure AGI's stuff."
```

??? note "輸出"

    ```text
    <IPython.core.display.Javascript object>
    ```

## 用 ROUGE 評估

[ROUGE](https://aclanthology.org/W04-1013/) 全名是 Recall-Oriented Understudy for Gisting Evaluation，主要看生成輸出跟參考文字之間有多少詞重疊，是評估自動摘要很常用的指標。它的變體 `ROUGE-L` 看的是系統摘要和參考摘要之間最長的共同子序列，用來衡量系統有沒有保留參考摘要的核心。


```python
# function to calculate the Rouge score
def get_rouge_scores(text1, text2):
    rouge = Rouge()
    return rouge.get_scores(text1, text2)


rouge_scores_out = []

# Calculate the ROUGE scores for both summaries using reference
eval_1_rouge = get_rouge_scores(eval_summary_1, ref_summary)
eval_2_rouge = get_rouge_scores(eval_summary_2, ref_summary)

for metric in ["rouge-1", "rouge-2", "rouge-l"]:
    for label in ["F-Score"]:
        eval_1_score = eval_1_rouge[0][metric][label[0].lower()]
        eval_2_score = eval_2_rouge[0][metric][label[0].lower()]

        row = {
            "Metric": f"{metric} ({label})",
            "Summary 1": eval_1_score,
            "Summary 2": eval_2_score,
        }
        rouge_scores_out.append(row)


def highlight_max(s):
    is_max = s == s.max()
    return [
        "background-color: lightgreen" if v else "background-color: white"
        for v in is_max
    ]


rouge_scores_out = (
    pd.DataFrame(rouge_scores_out)
    .set_index("Metric")
    .style.apply(highlight_max, axis=1)
)

rouge_scores_out
```

??? note "輸出"

    ```text
    <pandas.io.formats.style.Styler at 0x140b7dee0>
    ```

    ```text
    <IPython.core.display.Javascript object>
    ```

表格是兩份摘要對參考文字的 `ROUGE` 分數。`rouge-1` 方面 Summary 2 比 Summary 1 高，表示單字重疊比較多；`rouge-l` 也是 Summary 2 比較高，表示最長共同子序列比較接近，看起來更能抓到原文的主要內容和順序。但 Summary 2 有很多字詞和短語是直接從原文抄來的，跟參考摘要的重疊自然比較高，所以 `ROUGE` 分數才會高。

`ROUGE` 和類似的指標，像 [BLEU](https://aclanthology.org/P02-1040.pdf)、[METEOR](https://www.cs.cmu.edu/~alavie/METEOR/)，雖然能提供量化數字，但常常抓不到好摘要真正的價值，跟人類評分的相關性也比較差。現在 LLM 很會寫流暢連貫的摘要，`ROUGE` 這種傳統指標反而可能誤罰它們，尤其當摘要換了說法、但核心資訊都正確的時候。


## 用 BERTScore 評估

ROUGE 靠的是預測文字和參考文字裡有沒有完全相同的字，看不懂語意。[BERTScore](https://arxiv.org/abs/1904.09675) 就是來補這塊的，它用 BERT 模型的 contextual embedding，在機器生成文字的情境下比較預測句和參考句的相似度。比較兩邊的 embedding，`BERTScore` 能抓到 n-gram 指標漏掉的語意相似性。


```python
# Instantiate the BERTScorer object for English language
scorer = BERTScorer(lang="en")

# Calculate BERTScore for the summary 1 against the excerpt
# P1, R1, F1_1 represent Precision, Recall, and F1 Score respectively
P1, R1, F1_1 = scorer.score([eval_summary_1], [ref_summary])

# Calculate BERTScore for summary 2 against the excerpt
# P2, R2, F2_2 represent Precision, Recall, and F1 Score respectively
P2, R2, F2_2 = scorer.score([eval_summary_2], [ref_summary])

print("Summary 1 F1 Score:", F1_1.tolist()[0])
print("Summary 2 F1 Score:", F2_2.tolist()[0])
```

??? note "輸出"

    ```text
    Some weights of the model checkpoint at roberta-large were not used when initializing RobertaModel: ['lm_head.dense.weight', 'lm_head.dense.bias', 'lm_head.layer_norm.bias', 'lm_head.layer_norm.weight', 'lm_head.decoder.weight', 'lm_head.bias']
    - This IS expected if you are initializing RobertaModel from the checkpoint of a model trained on another task or with another architecture (e.g. initializing a BertForSequenceClassification model from a BertForPreTraining model).
    - This IS NOT expected if you are initializing RobertaModel from the checkpoint of a model that you expect to be exactly identical (initializing a BertForSequenceClassification model from a BertForSequenceClassification model).
    ```

    ```text
    Summary 1 F1 Score: 0.9227314591407776
    Summary 2 F1 Score: 0.9189572930335999
    ```

    ```text
    <IPython.core.display.Javascript object>
    ```

兩份摘要的 F1 分數很接近，表示它們在抓關鍵資訊上可能表現差不多。但這個小差距要小心解讀。`BERTScore` 不一定能掌握人類評審看得懂的細微差異和高層概念，只靠這個指標可能會誤判摘要的實際品質。把 `BERTScore` 跟人工判斷和其他指標一起用，會比較可靠。


## 用 GPT-4 評估

這裡用 `gpt-4` 做一個 **reference-free**（不需要參考答案）的文字評估器，靈感來自 [G-Eval](https://arxiv.org/pdf/2303.16634.pdf) 框架，它用大型語言模型來評估生成文字的品質。跟 `ROUGE`、`BERTScore` 要拿參考摘要來比不同，`gpt-4` 評估器只根據輸入的 prompt 和文字來判斷品質，不需要任何標準答案。所以在人工參考很少或根本沒有的新資料集和新任務上也能用。

方法大概是這樣：

1. 定義四個評分準則：
    1. **Relevance（相關性）**：摘要是不是只包含重要資訊、沒有多餘重複。
    2. **Coherence（連貫性）**：摘要的邏輯流程和組織好不好。
    3. **Consistency（一致性）**：摘要有沒有跟原文的事實對得上。
    4. **Fluency（流暢度）**：文法和可讀性。
2. 為每個準則寫 prompt，輸入原文和摘要，用 chain-of-thought 生成，並引導模型對每個準則輸出 1 到 5 的數字分數。
3. 用這些 prompt 讓 `gpt-4` 產生分數，再比較不同摘要的結果。

這個示範用的是直接打分的函式，`gpt-4` 對每個指標給一個離散分數（1 到 5）。如果把分數正規化再做加權總和，可以得到更穩健、連續的分數，更能反映摘要品質的差異。

```python
# Evaluation prompt template based on G-Eval
EVALUATION_PROMPT_TEMPLATE = """
You will be given one summary written for an article. Your task is to rate the summary on one metric.
Please make sure you read and understand these instructions very carefully. 
Please keep this document open while reviewing, and refer to it as needed.

Evaluation Criteria:

{criteria}

Evaluation Steps:

{steps}

Example:

Source Text:

{document}

Summary:

{summary}

Evaluation Form (scores ONLY):

- {metric_name}
"""

# Metric 1: Relevance

RELEVANCY_SCORE_CRITERIA = """
Relevance(1-5) - selection of important content from the source. \
The summary should include only important information from the source document. \
Annotators were instructed to penalize summaries which contained redundancies and excess information.
"""

RELEVANCY_SCORE_STEPS = """
1. Read the summary and the source document carefully.
2. Compare the summary to the source document and identify the main points of the article.
3. Assess how well the summary covers the main points of the article, and how much irrelevant or redundant information it contains.
4. Assign a relevance score from 1 to 5.
"""

# Metric 2: Coherence

COHERENCE_SCORE_CRITERIA = """
Coherence(1-5) - the collective quality of all sentences. \
We align this dimension with the DUC quality question of structure and coherence \
whereby "the summary should be well-structured and well-organized. \
The summary should not just be a heap of related information, but should build from sentence to a\
coherent body of information about a topic."
"""

COHERENCE_SCORE_STEPS = """
1. Read the article carefully and identify the main topic and key points.
2. Read the summary and compare it to the article. Check if the summary covers the main topic and key points of the article,
and if it presents them in a clear and logical order.
3. Assign a score for coherence on a scale of 1 to 5, where 1 is the lowest and 5 is the highest based on the Evaluation Criteria.
"""

# Metric 3: Consistency

CONSISTENCY_SCORE_CRITERIA = """
Consistency(1-5) - the factual alignment between the summary and the summarized source. \
A factually consistent summary contains only statements that are entailed by the source document. \
Annotators were also asked to penalize summaries that contained hallucinated facts.
"""

CONSISTENCY_SCORE_STEPS = """
1. Read the article carefully and identify the main facts and details it presents.
2. Read the summary and compare it to the article. Check if the summary contains any factual errors that are not supported by the article.
3. Assign a score for consistency based on the Evaluation Criteria.
"""

# Metric 4: Fluency

FLUENCY_SCORE_CRITERIA = """
Fluency(1-3): the quality of the summary in terms of grammar, spelling, punctuation, word choice, and sentence structure.
1: Poor. The summary has many errors that make it hard to understand or sound unnatural.
2: Fair. The summary has some errors that affect the clarity or smoothness of the text, but the main points are still comprehensible.
3: Good. The summary has few or no errors and is easy to read and follow.
"""

FLUENCY_SCORE_STEPS = """
Read the summary and evaluate its fluency based on the given criteria. Assign a fluency score from 1 to 3.
"""


def get_geval_score(
    criteria: str, steps: str, document: str, summary: str, metric_name: str
):
    prompt = EVALUATION_PROMPT_TEMPLATE.format(
        criteria=criteria,
        steps=steps,
        metric_name=metric_name,
        document=document,
        summary=summary,
    )
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=5,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )
    return response.choices[0].message.content


evaluation_metrics = {
    "Relevance": (RELEVANCY_SCORE_CRITERIA, RELEVANCY_SCORE_STEPS),
    "Coherence": (COHERENCE_SCORE_CRITERIA, COHERENCE_SCORE_STEPS),
    "Consistency": (CONSISTENCY_SCORE_CRITERIA, CONSISTENCY_SCORE_STEPS),
    "Fluency": (FLUENCY_SCORE_CRITERIA, FLUENCY_SCORE_STEPS),
}

summaries = {"Summary 1": eval_summary_1, "Summary 2": eval_summary_2}

data = {"Evaluation Type": [], "Summary Type": [], "Score": []}

for eval_type, (criteria, steps) in evaluation_metrics.items():
    for summ_type, summary in summaries.items():
        data["Evaluation Type"].append(eval_type)
        data["Summary Type"].append(summ_type)
        result = get_geval_score(criteria, steps, excerpt, summary, eval_type)
        score_num = int(result.strip())
        data["Score"].append(score_num)

pivot_df = pd.DataFrame(data, index=None).pivot(
    index="Evaluation Type", columns="Summary Type", values="Score"
)
styled_pivot_df = pivot_df.style.apply(highlight_max, axis=1)
display(styled_pivot_df)
```

??? note "輸出"

    ```text
    <pandas.io.formats.style.Styler at 0x143907b50>
    ```

    ```text
    <IPython.core.display.Javascript object>
    ```


整體來看，Summary 1 在四項裡有三項（Coherence、Relevance、Fluency）勝過 Summary 2，兩份摘要在 Consistency 上都跟原文一致。依照這些評分準則，結果顯示 Summary 1 大致比較好。

### 限制

LLM 型指標可能偏好 LLM 生成的文字，勝過人寫的文字。另外它們對 system message 和 prompt 很敏感。建議多試其他技巧來改善表現或讓分數更一致，在高品質但昂貴的評估和自動化評估之間找平衡。還有一點，這套評分方式目前會受 `gpt-4` 的 context window 限制。

## 結論

摘要生成的評估仍然有很大的進步空間。`ROUGE`、`BLEU`、`BERTScore` 這些傳統指標能提供有用的自動評估，但在抓語意相似度和摘要品質的細微面向上有限制，而且需要參考輸出，收集和標註的成本很高。LLM 型指標有機會成為不需要參考答案的做法，用來評估連貫性、流暢度和相關性，但它們也可能偏好 LLM 生成的文字。最理想的做法是自動指標加人工評估一起用。人工評估對全面理解摘要品質不可或缺，但要搭配自動評估，才能有效率地大規模測試。評估技術還會持續演進，在品質、規模和公平性之間取得平衡。要把這些東西用在 production，改進評估方法是關鍵。

## 參考資料

- [G-EVAL: NLG Evaluation Using GPT-4 with Better Human Alignment](https://arxiv.org/pdf/2303.16634.pdf) - Liu Y, Iter D, Xu Y, Wang S, Xu R, Zhu C. Published May, 2023.
- [BERTScore: Evaluating Text Generation with BERT](https://arxiv.org/abs/1904.09675) - Zhang T, Kishore V, Wu F, Weinberger KQ, Artzi Y. Published online February, 2020.
- [ROUGE: A Package for Automatic Evaluation of Summaries](https://aclanthology.org/W04-1013/) - Lin CY. Published July, 2004.
- [SummEval: Re-evaluating Summarization Evaluation](https://aclanthology.org/2021.tacl-1.24) - Fabbri et al. Published April, 2021.


## 重點整理

- 傳統指標（ROUGE、BERTScore）都要參考摘要，LLM 評審不用。
- ROUGE 只看字面重疊，抄原文的摘要分數會偏高，換說法的好摘要反而吃虧。
- BERTScore 看語意，但分數差距小的時候不能太相信。
- 把品質拆成 Relevance、Coherence、Consistency、Fluency 四個準則，各寫一個 prompt，讓 gpt-4 打分，比單一總分好解讀。
- LLM 評審有偏向 LLM 文字、對 prompt 敏感的問題，最好搭配人工評估。

## 練習

1. 在 `eval_summary_1` 跟 `eval_summary_2` 之外，自己再寫一份摘要，重跑 ROUGE 和 BERTScore，看分數排在哪裡。
2. 把 G-Eval 的評分 prompt 裡的 1 到 5 分改成 1 到 10 分，重跑 gpt-4 評分，看兩份摘要的排名會不會變。
3. 對同一份摘要用同一個 prompt 重複打分 5 次，記下分數變異，再試著改成取平均，觀察 LLM 評審是否穩定。
