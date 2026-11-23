---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/Evaluate_RAG_with_LlamaIndex.ipynb
---
# 用 LlamaIndex 評估 RAG

> 原文：[examples/evaluation/Evaluate_RAG_with_LlamaIndex.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/Evaluate_RAG_with_LlamaIndex.ipynb)



## 這篇在做什麼

用 LlamaIndex 建一個 RAG pipeline，吃 Paul Graham 的文章，然後用它內建的 evaluation 模組量化這個 pipeline 好不好。評估分兩塊：retrieval 有沒有撈到對的內容（Hit Rate、MRR），還有 response 有沒有幻覺、有沒有回答到問題（Faithfulness、Relevancy）。

## 學完你會

- 用 LlamaIndex 載入資料、建 vector index、做出 query engine 並檢查被撈回的 node。
- 用 `generate_question_context_pairs` 產生評估資料集，再用 `RetrieverEvaluator` 算 Hit Rate 和 MRR。
- 用 `FaithfulnessEvaluator`、`RelevancyEvaluator` 和 `BatchEvalRunner` 批次評估回答品質。

## 開跑前

需要設定 OpenAI API Key（會呼叫 embedding、`gpt-3.5-turbo` 和 `gpt-4`，會產生費用）。

這篇是在講 RAG 的概念，先看它怎麼運作，再來看怎麼評估。

**Retrieval Augmented Generation (RAG)**

LLM 是用大量資料訓練出來的，但裡面不會有你自己的資料。RAG 的做法是在生成回答的過程中，動態把你的資料帶進去。它不是去改 LLM 的訓練資料，而是讓模型在執行時直接存取、使用你的資料，所以回答會更貼近你的情境。

在 RAG 裡，你的資料會先被載入並整理成可查詢的形式，也就是「建索引」（indexing）。使用者的 query 會對 index 作用，把資料篩成最相關的 context。這份 context 和 query 再加上 prompt 一起送給 LLM，LLM 才產生回答。

就算你要做的是 chatbot 或 agent，也需要懂 RAG 的技巧，才知道怎麼把資料送進應用程式。

![RAG Overview](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/llamaindex_rag_overview.png)

**RAG 的幾個階段**

RAG 有五個關鍵階段，任何比較大的應用都會包含它們：

**Loading（載入）：** 把資料從它原本的地方（文字檔、PDF、別的網站、資料庫或 API）拿進 pipeline。LlamaHub 提供數百種 connector 可以選。

**Indexing（索引）：** 建出能查詢資料的結構。對 LLM 來說，幾乎都是建 vector embedding（用數值表示資料的語意），再搭配各種 metadata 策略，讓系統能準確找到相關內容。

**Storing（儲存）：** 資料索引好之後，會想把 index 和 metadata 存起來，避免重新建索引。

**Querying（查詢）：** 同一種索引策略下，有很多方式可以用 LLM 和 LlamaIndex 的資料結構來查，包含 sub-query、multi-step query 和混合策略。

**Evaluation（評估）：** 任何 pipeline 都該檢查它跟其他策略比起來效果如何，或是改動之後有沒有變好。評估能給你客觀的數字，看回答準不準、忠不忠實、快不快。

## 建 RAG 系統

了解 RAG 為什麼重要之後，我們來建一個簡單的 RAG pipeline。

```python
!pip install llama-index
```

```python
# The nest_asyncio module enables the nesting of asynchronous functions within an already running async loop.
# This is necessary because Jupyter notebooks inherently operate in an asynchronous loop.
# By applying nest_asyncio, we can run additional async functions within this existing loop without conflicts.
import nest_asyncio

nest_asyncio.apply()

from llama_index.evaluation import generate_question_context_pairs
from llama_index import VectorStoreIndex, SimpleDirectoryReader, ServiceContext
from llama_index.node_parser import SimpleNodeParser
from llama_index.evaluation import generate_question_context_pairs
from llama_index.evaluation import RetrieverEvaluator
from llama_index.llms import OpenAI

import os
import pandas as pd
```

設定你的 OpenAI API Key

```python
os.environ['OPENAI_API_KEY'] = 'YOUR OPENAI API KEY'
```

我們用 [Paul Graham 的文章](https://www.paulgraham.com/worked.html)來建 RAG pipeline。

#### 下載資料

```python
!mkdir -p 'data/paul_graham/'
!curl 'https://raw.githubusercontent.com/run-llama/llama_index/main/docs/examples/data/paul_graham/paul_graham_essay.txt' -o 'data/paul_graham/paul_graham_essay.txt'
```

??? note "輸出"

    ```text
      % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                     Dload  Upload   Total   Spent    Left  Speed
    100 75042  100 75042    0     0   190k      0 --:--:-- --:--:-- --:--:--  190k--:--  0:00:03 24586
    ```

#### 載入資料並建 index

```python
documents = SimpleDirectoryReader("./data/paul_graham/").load_data()

# Define an LLM
llm = OpenAI(model="gpt-4")

# Build index with a chunk_size of 512
node_parser = SimpleNodeParser.from_defaults(chunk_size=512)
nodes = node_parser.get_nodes_from_documents(documents)
vector_index = VectorStoreIndex(nodes)
```

建一個 QueryEngine 然後開始查詢。

```python
query_engine = vector_index.as_query_engine()
```

```python
response_vector = query_engine.query("What did the author do growing up?")
```

檢查回應。

```python
response_vector.response
```

??? note "輸出"

    ```text
    'The author wrote short stories and worked on programming, specifically on an IBM 1401 computer using an early version of Fortran.'
    ```

預設會撈回 `two` 個相似的 node（chunk）。想改的話用 `vector_index.as_query_engine(similarity_top_k=k)`。

來看看這些被撈回的 node 各自的文字。

```python
# First retrieved node
response_vector.source_nodes[0].get_text()
```

??? note "輸出"

    ```text
    'What I Worked On\n\nFebruary 2021\n\nBefore college the two main things I worked on, outside of school, were writing and programming. I didn\'t write essays. I wrote what beginning writers were supposed to write then, and probably still are: short stories. My stories were awful. They had hardly any plot, just characters with strong feelings, which I imagined made them deep.\n\nThe first programs I tried writing were on the IBM 1401 that our school district used for what was then called "data processing." This was in 9th grade, so I was 13 or 14. The school district\'s 1401 happened to be in the basement of our junior high school, and my friend Rich Draves and I got permission to use it. It was like a mini Bond villain\'s lair down there, with all these alien-looking machines — CPU, disk drives, printer, card reader — sitting up on a raised floor under bright fluorescent lights.\n\nThe language we used was an early version of Fortran. You had to type programs on punch cards, then stack them in the card reader and press a button to load the program into memory and run it. The result would ordinarily be to print something on the spectacularly loud printer.\n\nI was puzzled by the 1401. I couldn\'t figure out what to do with it. And in retrospect there\'s not much I could have done with it. The only form of input to programs was data stored on punched cards, and I didn\'t have any data stored on punched cards. The only other option was to do things that didn\'t rely on any input, like calculate approximations of pi, but I didn\'t know enough math to do anything interesting of that type. So I\'m not surprised I can\'t remember any programs I wrote, because they can\'t have done much. My clearest memory is of the moment I learned it was possible for programs not to terminate, when one of mine didn\'t. On a machine without time-sharing, this was a social as well as a technical error, as the data center manager\'s expression made clear.\n\nWith microcomputers, everything changed.'
    ```

```python
# Second retrieved node
response_vector.source_nodes[1].get_text()
```

??? note "輸出"

    ```text
    "It felt like I was doing life right. I remember that because I was slightly dismayed at how novel it felt. The good news is that I had more moments like this over the next few years.\n\nIn the summer of 2016 we moved to England. We wanted our kids to see what it was like living in another country, and since I was a British citizen by birth, that seemed the obvious choice. We only meant to stay for a year, but we liked it so much that we still live there. So most of Bel was written in England.\n\nIn the fall of 2019, Bel was finally finished. Like McCarthy's original Lisp, it's a spec rather than an implementation, although like McCarthy's Lisp it's a spec expressed as code.\n\nNow that I could write essays again, I wrote a bunch about topics I'd had stacked up. I kept writing essays through 2020, but I also started to think about other things I could work on. How should I choose what to do? Well, how had I chosen what to work on in the past? I wrote an essay for myself to answer that question, and I was surprised how long and messy the answer turned out to be. If this surprised me, who'd lived it, then I thought perhaps it would be interesting to other people, and encouraging to those with similarly messy lives. So I wrote a more detailed version for others to read, and this is the last sentence of it.\n\n\n\n\n\n\n\n\n\nNotes\n\n[1] My experience skipped a step in the evolution of computers: time-sharing machines with interactive OSes. I went straight from batch processing to microcomputers, which made microcomputers seem all the more exciting.\n\n[2] Italian words for abstract concepts can nearly always be predicted from their English cognates (except for occasional traps like polluzione). It's the everyday words that differ. So if you string together a lot of abstract concepts with a few simple verbs, you can make a little Italian go a long way.\n\n[3] I lived at Piazza San Felice 4, so my walk to the Accademia went straight down the spine of old Florence: past the Pitti, across the bridge, past Orsanmichele, between the Duomo and the Baptistery, and then up Via Ricasoli to Piazza San Marco."
    ```

RAG pipeline 建好了，接下來要評估它的表現。我們可以用 LlamaIndex 的核心 evaluation 模組來評估 RAG 系統（query engine），看看怎麼量化檢索加生成的品質。

## 評估

評估應該是衡量 RAG 應用的首要指標。它決定這個 pipeline 面對你的資料來源和各種問題時，能不能產生正確的回答。

一開始逐筆看 query 和回答是有幫助的，但 edge case 和失敗案例變多之後就不實際了。比較有效的做法是建一組彙總指標或自動化評估，用來掌握整體表現，並指出哪些地方需要細看。

RAG 系統的評估看兩件事：

*   **Retrieval Evaluation：** 評估系統撈回來的資訊準不準、相不相關。
*   **Response Evaluation：** 評估系統根據撈回的資訊所產生的回答，品質好不好、恰不恰當。

#### 產生 Question-Context Pair

要評估 RAG 系統，需要有能撈到正確 context、並產生適當回答的 query。`LlamaIndex` 提供 `generate_question_context_pairs` 模組，專門產生問題和 context 的配對，可以同時用在 Retrieval 和 Response 評估。更多關於 Question Generation 的細節請看[文件](https://docs.llamaindex.ai/en/stable/examples/evaluation/QuestionGeneration.html)。

```python
qa_dataset = generate_question_context_pairs(
    nodes,
    llm=llm,
    num_questions_per_chunk=2
)
```

??? note "輸出"

    ```text
    100%|██████████| 58/58 [06:26<00:00,  6.67s/it]
    ```

#### Retrieval Evaluation

現在可以做 retrieval 評估了。我們會用剛產生的評估資料集來跑 `RetrieverEvaluator`。

先建 `Retriever`，再定義兩個函式：`get_eval_results` 負責在資料集上跑 retriever，`display_results` 負責呈現評估結果。

先來建 retriever。

```python
retriever = vector_index.as_retriever(similarity_top_k=2)
```

定義 `RetrieverEvaluator`。我們用 **Hit Rate** 和 **MRR** 兩個指標來評估 Retriever。

**Hit Rate：**

Hit rate 算的是正確答案出現在前 k 個撈回文件裡的 query 比例。簡單講，就是系統在前幾次猜測內猜對的頻率。

**Mean Reciprocal Rank (MRR)：**

對每個 query，MRR 看排名最高的相關文件排第幾。具體來說，是把所有 query 的排名倒數取平均。所以第一個相關文件排第一，倒數排名就是 1；排第二就是 1/2，以此類推。

來看這些指標，確認 retriever 的表現。

```python
retriever_evaluator = RetrieverEvaluator.from_metric_names(
    ["mrr", "hit_rate"], retriever=retriever
)
```

```python
# Evaluate
eval_results = await retriever_evaluator.aevaluate_dataset(qa_dataset)
```

定義一個函式，把 Retrieval 評估結果用表格顯示。

```python
def display_results(name, eval_results):
    """Display results from evaluate."""

    metric_dicts = []
    for eval_result in eval_results:
        metric_dict = eval_result.metric_vals_dict
        metric_dicts.append(metric_dict)

    full_df = pd.DataFrame(metric_dicts)

    hit_rate = full_df["hit_rate"].mean()
    mrr = full_df["mrr"].mean()

    metric_df = pd.DataFrame(
        {"Retriever Name": [name], "Hit Rate": [hit_rate], "MRR": [mrr]}
    )

    return metric_df
```

```python
display_results("OpenAI Embedding Retriever", eval_results)
```

??? note "輸出"

    ```text
                   Retriever Name  Hit Rate      MRR
    0  OpenAI Embedding Retriever  0.758621  0.62069
    ```

#### 觀察

用 OpenAI Embedding 的 Retriever，hit rate 是 `0.7586`，MRR 是 `0.6206`，代表要讓最相關的結果排在最前面還有進步空間。MRR 比 hit rate 低，表示排最前面的結果不一定是最相關的。要提升 MRR 可以用 reranker 重新排序撈回的文件。想深入了解 reranker 怎麼最佳化 retrieval 指標，請看這篇[部落格文章](https://blog.llamaindex.ai/boosting-rag-picking-the-best-embedding-reranker-models-42d079022e83)。

#### Response Evaluation

1. FaithfulnessEvaluator：衡量 query engine 的回答是否符合 source node，可以用來判斷回答有沒有幻覺。
2. Relevancy Evaluator：衡量回答加 source node 是否符合 query。

```python
# Get the list of queries from the above created dataset

queries = list(qa_dataset.queries.values())
```

#### Faithfulness Evaluator

先從 FaithfulnessEvaluator 開始。

我們用 `gpt-3.5-turbo` 針對 query 產生回答，用 `gpt-4` 做評估。

分別為 `gpt-3.5-turbo` 和 `gpt-4` 建立 service_context。

```python
# gpt-3.5-turbo
gpt35 = OpenAI(temperature=0, model="gpt-3.5-turbo")
service_context_gpt35 = ServiceContext.from_defaults(llm=gpt35)

# gpt-4
gpt4 = OpenAI(temperature=0, model="gpt-4")
service_context_gpt4 = ServiceContext.from_defaults(llm=gpt4)
```

用 `gpt-3.5-turbo` 的 service_context 建一個 `QueryEngine`，用來為 query 產生回答。

```python
vector_index = VectorStoreIndex(nodes, service_context = service_context_gpt35)
query_engine = vector_index.as_query_engine()
```

建立 FaithfulnessEvaluator。




```python
from llama_index.evaluation import FaithfulnessEvaluator
faithfulness_gpt4 = FaithfulnessEvaluator(service_context=service_context_gpt4)
```

先評估一個問題。

```python
eval_query = queries[10]

eval_query
```

??? note "輸出"

    ```text
    "Based on the author's experience and observations, why did he consider the AI practices during his first year of grad school as a hoax? Provide specific examples from the text to support your answer."
    ```

先產生回答，再用 faithfulness evaluator 評估。

```python
response_vector = query_engine.query(eval_query)
```

```python
# Compute faithfulness evaluation

eval_result = faithfulness_gpt4.evaluate_response(response=response_vector)
```

```python
# You can check passing parameter in eval_result if it passed the evaluation.
eval_result.passing
```

??? note "輸出"

    ```text
    True
    ```

#### Relevancy Evaluator

RelevancyEvaluator 用來衡量回答和 source node（撈回的 context）是否符合 query，可以看回答到底有沒有回答到問題。

建立用 `gpt-4` 做 relevancy 評估的 `RelevancyEvaluator`。

對其中一個 query 做 relevancy 評估。

```python
from llama_index.evaluation import RelevancyEvaluator

relevancy_gpt4 = RelevancyEvaluator(service_context=service_context_gpt4)
```

```python
# Pick a query
query = queries[10]

query
```

??? note "輸出"

    ```text
    "Based on the author's experience and observations, why did he consider the AI practices during his first year of grad school as a hoax? Provide specific examples from the text to support your answer."
    ```

```python
# Generate response.
# response_vector has response and source nodes (retrieved context)
response_vector = query_engine.query(query)

# Relevancy evaluation
eval_result = relevancy_gpt4.evaluate_response(
    query=query, response=response_vector
)
```

```python
# You can check passing parameter in eval_result if it passed the evaluation.
eval_result.passing
```

??? note "輸出"

    ```text
    True
    ```

```python
# You can get the feedback for the evaluation.
eval_result.feedback
```

??? note "輸出"

    ```text
    'YES'
    ```

#### Batch Evaluator

Faithfulness 和 Relevancy 都單獨評估過了，LlamaIndex 有 `BatchEvalRunner` 可以一次批次跑多個評估。

```python
from llama_index.evaluation import BatchEvalRunner

# Let's pick top 10 queries to do evaluation
batch_eval_queries = queries[:10]

# Initiate BatchEvalRunner to compute FaithFulness and Relevancy Evaluation.
runner = BatchEvalRunner(
    {"faithfulness": faithfulness_gpt4, "relevancy": relevancy_gpt4},
    workers=8,
)

# Compute evaluation
eval_results = await runner.aevaluate_queries(
    query_engine, queries=batch_eval_queries
)
```

```python
# Let's get faithfulness score

faithfulness_score = sum(result.passing for result in eval_results['faithfulness']) / len(eval_results['faithfulness'])

faithfulness_score
```

??? note "輸出"

    ```text
    1.0
    ```

```python
# Let's get relevancy score

relevancy_score = sum(result.passing for result in eval_results['relevancy']) / len(eval_results['relevancy'])

relevancy_score
```

??? note "輸出"

    ```text
    1.0
    ```

#### 觀察

Faithfulness 分數 `1.0` 代表產生的回答沒有幻覺，完全是根據撈回的 context。

Relevancy 分數 `1.0` 代表回答跟撈回的 context 以及 query 一致。

## 結論

這篇用 LlamaIndex 建了一個 RAG pipeline 並評估它，重點放在 pipeline 裡的 retrieval 系統和生成的回答。

LlamaIndex 還有其他評估模組，可以到[這裡](https://docs.llamaindex.ai/en/stable/module_guides/evaluating/root.html)了解更多。

## 重點整理

- RAG 評估要分兩塊看：retrieval 有沒有撈到對的 context，以及 response 的品質。
- Hit Rate 看正確結果有沒有出現在前 k 個，MRR 還看它排得多前面。MRR 低於 hit rate 代表排序有改善空間，可以加 reranker。
- Faithfulness 檢查回答有沒有脫離 source node（幻覺），Relevancy 檢查回答有沒有切題。
- 用強一點的模型（這裡是 `gpt-4`）來評估較弱模型（`gpt-3.5-turbo`）的輸出，是常見的做法。
- 逐筆看結果撐不久，要靠資料集加自動化指標才能追蹤改動的效果。

## 練習

1. 把 `vector_index.as_query_engine(similarity_top_k=k)` 的 k 改成 4，看撈回的 node 和回答有什麼變化。
2. 改 retriever 的 `similarity_top_k`，重跑 `RetrieverEvaluator`，比較 Hit Rate 和 MRR 怎麼變。
3. 把評估用的模型從 `gpt-4` 換成別的，重跑 `BatchEvalRunner`，看 Faithfulness 和 Relevancy 分數有沒有差異。
