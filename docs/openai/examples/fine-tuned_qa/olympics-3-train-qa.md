---
translated: true
source: examples/fine-tuned_qa/olympics-3-train-qa.ipynb
---

# Fine-Tuned Q&A：訓練

> 原文：[examples/fine-tuned_qa/olympics-3-train-qa.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/fine-tuned_qa/olympics-3-train-qa.ipynb)



## 這篇在做什麼
承接前面做好的「context、問題、答案」資料集，這篇另外造出對抗式的問題與 context 配對（問題不是從那個 context 產生的），訓練模型在這種情況回答「沒有足夠的 context 可以回答」。同時訓練一個 discriminator，判斷問題能不能從 context 回答。

## 學完你會
- 為 Q&A 模型和 discriminator 建立含正例、隨機負例和 hard negative 的 fine-tuning 資料集
- 提交 fine-tuning 工作，並用 logprobs 看 discriminator 對 yes/no 的把握度
- 組合 discriminator 與 Q&A 模型，並接上檢索，做成能依知識庫回答的流程

## 開跑前
- OpenAI API key，以及 fine-tuning 的費用
- 前面步驟產生的資料集
- 注意部分程式碼用到已棄用的 API endpoint


<span style="color:orange; font-weight:bold">注意：如果要根據文字文件回答問題，我們建議用 <a href="https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_embeddings.ipynb">Question Answering using Embeddings</a> 的做法。下面有些程式碼可能依賴<a href="https://github.com/openai/openai-cookbook/tree/main/transition_guides_for_deprecated_API_endpoints">已棄用的 API endpoint</a>。</span>

這份 notebook 會利用 context、問題、答案配對的資料集，額外建立對抗式的問題與 context 配對，也就是問題不是從該 context 產生的。這種情況下，模型會被提示回答「No sufficient context for answering the question」。我們也會訓練一個 discriminator 模型，預測問題能不能根據 context 回答。

我們還會加入困難的對抗式範例，這些範例來自語意相似的段落，或同一篇文章裡相鄰的段落。

```python
import openai
import pandas as pd
df = pd.read_csv('olympics-data/olympics_qa.csv')
olympics_search_fileid = "file-c3shd8wqF3vSCKaukW4Jr1TT"
df.head()
```

??? note "輸出"

    ```text
                      title                                         heading  \
    0  2020 Summer Olympics                                         Summary   
    1  2020 Summer Olympics                             Host city selection   
    2  2020 Summer Olympics                 Impact of the COVID-19 pandemic   
    3  2020 Summer Olympics  Qualifying event cancellation and postponement   
    4  2020 Summer Olympics                          Effect on doping tests   

                                                 content  tokens  \
    0  The 2020 Summer Olympics (Japanese: 2020年夏季オリン...     713   
    1  The International Olympic Committee (IOC) vote...     126   
    2  In January 2020, concerns were raised about th...     369   
    3  Concerns about the pandemic began to affect qu...     298   
    4  Mandatory doping tests were being severely res...     163   

                                                 context  \
    0  2020 Summer Olympics\nSummary\n\nThe 2020 Summ...   
    1  2020 Summer Olympics\nHost city selection\n\nT...   
    2  2020 Summer Olympics\nImpact of the COVID-19 p...   
    3  2020 Summer Olympics\nQualifying event cancell...   
    4  2020 Summer Olympics\nEffect on doping tests\n...   

                                               questions  \
    0  1. What is the 2020 Summer Olympics?\n2. When ...   
    1                                 1. \n2. \n3. \n4.    
    2  1. What was the COVID-19 pandemic?\n2. How did...   
    3  1. What was the original location of the Asia ...   
    4  1. What was the COVID-19 pandemic?\n2. What di...   

                                                 answers  
    0  1. The 2020 Summer Olympics is an internationa...  
    1  1. What is the International Olympic Committee...  
    2  1. The COVID-19 pandemic was a pandemic that o...  
    3  1. The original location of the Asia & Oceania...  
    4  1. The COVID-19 pandemic was a pandemic that o...
    ```

把段落切成訓練集和測試集

```python
from sklearn.model_selection import train_test_split
train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
len(train_df), len(test_df)
```

??? note "輸出"

    ```text
    (3014, 754)
    ```

檢查我們打算使用的分隔符號沒有出現在 context 裡

```python
df.context.str.contains('->').sum()
```

??? note "輸出"

    ```text
    0
    ```

## 3.1 建立 Q&A 和 discriminator 模型的 fine-tuning 資料集
fine-tuning 資料集的建立方式如下。對每一組對應的問題、答案和 context，我們建立：
- 正例：正確的問題、答案、context 配對
- 負例：
  - 隨機負例：把隨機的 context 配上這個問題 
  - 兩個 hard negative 範例
    - 一個來自同一篇 wikipedia 文章
    - 另一個是跟正確 context 最相似的

這個過程有雜訊，因為有時換個 context 問題也能回答，但我們希望平均來說不會對效能造成太大影響。

discriminator 和 Q&A 回答模型用同樣的方式建立資料集。訓練集和測試集分開處理，確保訓練集的範例不會出現在測試集。

```python
import random

def get_random_similar_contexts(question, context, file_id=olympics_search_fileid, search_model='ada', max_rerank=10):
    """
    Find similar contexts to the given context using the search file
    """
    try:
        # TODO: openai.Engine(search_model) is deprecated
        results = openai.Engine(search_model).search(
            search_model=search_model, 
            query=question, 
            max_rerank=max_rerank,
            file=file_id
        )
        candidates = []
        for result in results['data'][:3]:
            if result['text'] == context:
                continue
            candidates.append(result['text'])
        random_candidate = random.choice(candidates)
        return random_candidate
    except Exception as e:
        print(e)
        return ""

def create_fine_tuning_dataset(df, discriminator=False, n_negative=1, add_related=False):
    """
    Create a dataset for fine tuning the OpenAI model; either for a discriminator model, 
    or a model specializing in Q&A, where it says if no relevant context is found.

    Parameters
    ----------
    df: pd.DataFrame
        The dataframe containing the question, answer and context pairs
    discriminator: bool
        Whether to create a dataset for the discriminator
    n_negative: int
        The number of random negative samples to add (using a random context)
    add_related: bool
        Whether to add the related contexts to the correct context. These are hard negative examples

    Returns
    -------
    pd.DataFrame
        The dataframe containing the prompts and completions, ready for fine-tuning
    """
    rows = []
    for i, row in df.iterrows():
        for q, a in zip(("1." + row.questions).split('\n'), ("1." + row.answers).split('\n')):
            if len(q) >10 and len(a) >10:
                if discriminator:
                    rows.append({"prompt":f"{row.context}\nQuestion: {q[2:].strip()}\n Related:", "completion":f" yes"})
                else:
                    rows.append({"prompt":f"{row.context}\nQuestion: {q[2:].strip()}\nAnswer:", "completion":f" {a[2:].strip()}"})

    for i, row in df.iterrows():
        for q in ("1." + row.questions).split('\n'):
            if len(q) >10:
                for j in range(n_negative + (2 if add_related else 0)):
                    random_context = ""
                    if j == 0 and add_related:
                        # add the related contexts based on originating from the same wikipedia page
                        subset = df[(df.title == row.title) & (df.context != row.context)]
                        
                        if len(subset) < 1:
                            continue
                        random_context = subset.sample(1).iloc[0].context
                    if j == 1 and add_related:
                        # add the related contexts based on the most similar contexts according to the search
                        random_context = get_random_similar_contexts(q[2:].strip(), row.context, search_model='ada', max_rerank=10)
                    else:
                        while True:
                            # add random context, which isn't the correct context
                            random_context = df.sample(1).iloc[0].context
                            if random_context != row.context:
                                break
                    if discriminator:
                        rows.append({"prompt":f"{random_context}\nQuestion: {q[2:].strip()}\n Related:", "completion":f" no"})
                    else:
                        rows.append({"prompt":f"{random_context}\nQuestion: {q[2:].strip()}\nAnswer:", "completion":f" No appropriate context found to answer the question."})

    return pd.DataFrame(rows)
```

discriminator 和 Q&A 回答模型用同樣的方式建立資料集。訓練集和測試集分開處理，確保訓練集的範例不會出現在測試集。

```python
for name, is_disc in [('discriminator', True), ('qa', False)]:
    for train_test, dt in [('train', train_df), ('test', test_df)]:
        ft = create_fine_tuning_dataset(dt, discriminator=is_disc, n_negative=1, add_related=True)
        ft.to_json(f'{name}_{train_test}.jsonl', orient='records', lines=True)
```

我們依照 fine-tuning 工具的建議格式化資料，可以這樣使用
> openai tools fine_tunes.prepare_data -f qa_train.jsonl

我們強烈建議使用這個工具，它會針對 fine-tuning 的資料格式提出改進建議。


## 3.2 提交資料集進行 fine-tuning

```python
!openai api fine_tunes.create -t "olympics-data/discriminator_train.jsonl" -v "olympics-data/discriminator_test.jsonl" --batch_size 16  --compute_classification_metrics --classification_positive_class " yes" --model ada
```

```python
!openai api fine_tunes.create -t "olympics-data/qa_train.jsonl" -v "olympics-data/qa_test.jsonl" --batch_size 16
```

## 3.3 使用 fine-tuned 模型

現在使用 fine-tuned discriminator 和 fine-tuned Q&A 模型。要求回傳 logprobs，就能看出 discriminator 對 `yes` 和 `no` 答案有多確定。

```python
ft_discriminator = "curie:ft-openai-internal-2021-08-23-23-58-57"
ft_qa = "curie:ft-openai-internal-2021-08-23-17-54-10"

def apply_ft_discriminator(context, question, discriminator_model):
    """
    Apply the fine tuned discriminator to a question, to assess whether it can be answered from the context.
    """
    prompt = f"{context}\nQuestion: {question}\n Related:"
    result = openai.chat.completions.create(model=discriminator_model, prompt=prompt, max_tokens=1, temperature=0, top_p=1, n=1, logprobs=2)
    return result['choices'][0]['logprobs']['top_logprobs']

apply_ft_discriminator('The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957.', 
                        'What was the first human-made object in space?', ft_discriminator)
```

??? note "輸出"

    ```text
    [<OpenAIObject at 0x7fe812e602b0> JSON: {
       " no": -10.819577,
       " yes": -2.045765e-05
     }]
    ```

可以看到模型能很好地泛化到不同的 context 和問題。 

```python
def apply_ft_qa_answer(context, question, answering_model):
    """
    Apply the fine tuned discriminator to a question
    """
    prompt = f"{context}\nQuestion: {question}\nAnswer:"
    result = openai.chat.completions.create(model=answering_model, prompt=prompt, max_tokens=30, temperature=0, top_p=1, n=1, stop=['.','\n'])
    return result['choices'][0]['text']

apply_ft_qa_answer('The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957.', 
                    'What was the first human-made object in space?', ft_qa)
```

??? note "輸出"

    ```text
    ' The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957'
    ```

可以看到，context 合適時，模型能回答問題。

```python
apply_ft_qa_answer('The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957.',
                    'What is impressive about the Soviet Union?', ft_qa)
```

??? note "輸出"

    ```text
    ' The Soviet Union was the first country to successfully launch a satellite into space'
    ```

```python
apply_ft_qa_answer('The first human-made object in space was the Soviet Union satellite Sputnik 1 on 4 October 1957.',
                    'How many cars were produced in the Soviet Union in 1970?', ft_qa)
```

??? note "輸出"

    ```text
    ' No appropriate context found to answer the question'
    ```

可以看到模型知道什麼時候該回答問題，什麼時候該說 context 不足以回答。

我們也可以把 discriminator 和基礎模型，或 fine-tuned Q&A 模型組合起來。discriminator 基本上可以用來決定：給定 context 之後，這個問題能不能回答。

```python
def answer_question_conditionally(answering_model, discriminator_model, context, question, discriminator_logprob_yes_modifier=0):
    logprobs = apply_ft_discriminator(context, question, discriminator_model)
    yes_logprob = logprobs[' yes'] if ' yes' in logprobs else -100
    no_logprob = logprobs[' no'] if ' no' in logprobs else -100
    if yes_logprob + discriminator_logprob_yes_modifier < no_logprob:
        return " No appropriate context found to answer the question based on the discriminator."
    return apply_ft_qa_answer(context, question, answering_model)
answer_question_conditionally(ft_qa, ft_discriminator, 
                                "Crowdless games are a rare although not unheard-of occurrence in sports. \
                                 When they do occur, it is usually the result of events beyond the control \
                                 of the teams or fans, such as weather-related concerns, public health concerns, \
                                 or wider civil disturbances unrelated to the game. For instance, \
                                 the COVID-19 pandemic caused many sports leagues around the world \
                                 to be played behind closed doors.",
                                "Could weather cause a sport event to have no crowd?")
```

??? note "輸出"

    ```text
    ' Weather could cause a sport event to have no crowd'
    ```

上面的函式示範了怎麼組合 discriminator 和 fine-tuned Q&A 模型。這能更細緻地控制模型要多確定才回答問題。

接下來看 answers endpoint 怎麼運作：先搜尋，從知識庫取得相關 context，再用 fine-tuned Q&A 模型回答問題。

## 3.4 根據知識庫回答問題
最後，我們可以用類似 [/answers](https://beta.openai.com/docs/api-reference/answers) endpoint 的邏輯：先搜尋相關 context，再請 Q&A 模型根據那個 context 回答問題。想看實作細節，請看 [`answers_with_ft.py`](https://github.com/openai/openai-cookbook/blob/main/examples/fine-tuned_qa/answers_with_ft.py) 檔案。

```python
from answers_with_ft import answer_question
answer_question(olympics_search_fileid, ft_qa, "Which country won the Women's football tournament at the 2020 Olympic games?")
```

??? note "輸出"

    ```text
    " Canada won the Women's football tournament at the 2020 Olympic games"
    ```

## 重點整理
- 只用正確配對訓練的 Q&A 模型，遇到答不出來的問題還是會亂答，所以要加入負例教它說「context 不足」。
- 負例分三種：隨機 context、同一篇文章的 context、最相似的 context，hard negative 讓模型學會區分接近的情況。
- discriminator 用 logprobs 輸出對 yes/no 的把握度，可以拿來調整「多確定才回答」的門檻。
- 訓練集和測試集要分開造資料，避免洩漏。
- 完整流程是先檢索 context，再讓 Q&A 模型回答，必要時由 discriminator 把關。

## 練習
1. 看建立資料集的程式，把每組例子的隨機負例數量改成 2 個，觀察資料集大小怎麼變。
2. 在組合 discriminator 與 Q&A 模型的函式裡，調整 discriminator 的信心門檻，比較模型回答和拒答的比例。
3. 對知識庫流程換一個自己的問題，檢查檢索到的 context 是否正確，以及模型是否在 context 不足時拒答。
