---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/responses_api/responses_api_tool_orchestration.ipynb
---

# 用 Responses API 搭配 RAG 做多工具調度

> 原文：[examples/responses_api/responses_api_tool_orchestration.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/responses_api/responses_api_tool_orchestration.ipynb)

用 Responses API 搭配 RAG，把查詢路由到不同的工具。

## 這篇在做什麼

把醫療推理資料集存進 Pinecone 向量資料庫，再用 Responses API 同時掛上 web search 內建工具和自訂的 Pinecone 搜尋 function。模型會依問題自己選工具，最後把工具結果餵回去產生答案。

## 學完你會

- 把資料集做成 embedding，建立 Pinecone index 並批次 upsert
- 用查詢 embedding 做相似度搜尋，把結果當 context 交給 Responses API 生成答案
- 同時定義 web search 與 function tool，並處理 tool call 的往返流程，甚至讓模型依指示依序串接多個工具

## 開跑前

- 需要 `OPENAI_API_KEY`
- 需要 Pinecone 帳號與 API key（外部服務）
- 資料集來自 Hugging Face，embedding 與模型呼叫會產生費用


### 用 Responses API 搭配 RAG 做多工具調度

這份 cookbook 帶你用 OpenAI 的 Responses API 建立動態的多工具 workflow。它示範怎麼實作 Retrieval-Augmented Generation (RAG)，把使用者的查詢聰明地路由到合適的內建或外部工具。查詢如果是一般知識，或需要從向量資料庫（像 Pinecone）取內部 context，這篇都會說明怎麼整合 function call、web search 內建工具，並用文件檢索產生準確、有脈絡的回答。

想看用 Responses API 的 file search 功能對 PDF 做 RAG 的實例，請參考[這份](https://cookbook.openai.com/examples/file_search_responses) notebook。

這個例子展現 Responses API 的彈性：除了連到內部向量庫的 `file_search` 工具，也能輕鬆接外部向量資料庫。這讓你可以把 RAG 跟 hosted 工具搭配使用，應付各種檢索與生成任務。

```python
#%pip install datasets tqdm pandas pinecone openai --quiet

import os
import time
from tqdm.auto import tqdm
from pandas import DataFrame
from datasets import load_dataset
import random
import string


# Import OpenAI client and initialize with your API key.
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Import Pinecone client and related specifications.
from pinecone import Pinecone
from pinecone import ServerlessSpec
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 24.0 -> 25.0.1
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

    ```text
    /Users/shikhar/openai_projects/github_repos/success-git/success_new/success/oneoffs/shikhar/responses_rag_cookbook/env/lib/python3.11/site-packages/tqdm/auto.py:21: TqdmWarning: IProgress not found. Please update jupyter and ipywidgets. See https://ipywidgets.readthedocs.io/en/stable/user_install.html
      from .autonotebook import tqdm as notebook_tqdm
    ```

這個例子用 Hugging Face 的醫療推理資料集範例。我們把資料集轉成 Pandas DataFrame，並把「Question」和「Response」欄位合併成單一字串。合併後的文字會用來做 embedding，之後也會存成 metadata。

```python
# Load the dataset (ensure you're logged in with huggingface-cli if needed)
ds = load_dataset("FreedomIntelligence/medical-o1-reasoning-SFT", "en", split='train[:100]', trust_remote_code=True)
ds_dataframe = DataFrame(ds)

# Merge the Question and Response columns into a single string.
ds_dataframe['merged'] = ds_dataframe.apply(
    lambda row: f"Question: {row['Question']} Answer: {row['Response']}", axis=1
)
print("Example merged text:", ds_dataframe['merged'].iloc[0])
```

??? note "輸出"

    ```text
    Example merged text: Question: A 61-year-old woman with a long history of involuntary urine loss during activities like coughing or sneezing but no leakage at night undergoes a gynecological exam and Q-tip test. Based on these findings, what would cystometry most likely reveal about her residual volume and detrusor contractions? Answer: Cystometry in this case of stress urinary incontinence would most likely reveal a normal post-void residual volume, as stress incontinence typically does not involve issues with bladder emptying. Additionally, since stress urinary incontinence is primarily related to physical exertion and not an overactive bladder, you would not expect to see any involuntary detrusor contractions during the test.
    ```

```python
ds_dataframe
```

??? note "輸出"

    ```text
                                                 Question  \
    0   A 61-year-old woman with a long history of inv...   
    1   A 45-year-old man with a history of alcohol us...   
    2   A 45-year-old man presents with symptoms inclu...   
    3   A patient with psoriasis was treated with syst...   
    4   What is the most likely diagnosis for a 2-year...   
    ..                                                ...   
    95  An electrical current flows along a flat plate...   
    96  A herpetologist bitten by a poisonous snake is...   
    97  A 34 years old person has rapidly developing c...   
    98  What is the term used to describe the type of ...   
    99  During the process of chlorination of water, t...   

                                              Complex_CoT  \
    0   Okay, let's think about this step by step. The...   
    1   Alright, let’s break this down. We have a 45-y...   
    2   Okay, so here's a 45-year-old guy who's experi...   
    3   I'm thinking about this patient with psoriasis...   
    4   Okay, so we're dealing with a 2-year-old child...   
    ..                                                ...   
    95  Alright, to find out the temperature at the ce...   
    96  Alright, so we're dealing with a case where a ...   
    97  Alright, let's break down what's happening wit...   
    98  Okay, so I need to figure out what kind of inj...   
    99  Alright, let's think this through starting fro...   

                                                 Response  \
    0   Cystometry in this case of stress urinary inco...   
    1   Considering the clinical presentation of sudde...   
    2   Based on the clinical findings presented—wide-...   
    3   The development of generalized pustules in a p...   
    4   Based on the described symptoms and the unusua...   
    ..                                                ...   
    95                   The correct answer is F. 1549°F.   
    96  The snake venom is most likely affecting the a...   
    97  The symptoms described in the question fit mos...   
    98  The term used to describe the type of injury c...   
    99  The effective disinfecting action during the c...   

                                                   merged  
    ... (省略 13 行)
    ```

### 依資料集建立 Pinecone Index
用資料集本身決定 embedding 的維度。例如先對合併後的欄位算出一個 embedding，再依此建立 index。

```python
MODEL = "text-embedding-3-small"  # Replace with your production embedding model if needed
# Compute an embedding for the first document to obtain the embedding dimension.
sample_embedding_resp = client.embeddings.create(
    input=[ds_dataframe['merged'].iloc[0]],
    model=MODEL
)
embed_dim = len(sample_embedding_resp.data[0].embedding)
print(f"Embedding dimension: {embed_dim}")
```

??? note "輸出"

    ```text
    Embedding dimension: 1536
    ```

```python

# Initialize Pinecone using your API key.
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# Define the Pinecone serverless specification.
AWS_REGION = "us-east-1"
spec = ServerlessSpec(cloud="aws", region=AWS_REGION)

# Create a random index name with lower case alphanumeric characters and '-'
index_name = 'pinecone-index-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

# Create the index if it doesn't already exist.
if index_name not in pc.list_indexes().names():
    pc.create_index(
        index_name,
        dimension=embed_dim,
        metric='dotproduct',
        spec=spec
    )

# Connect to the index.
index = pc.Index(index_name)
time.sleep(1)
print("Index stats:", index.describe_index_stats())
```

??? note "輸出"

    ```text
    Index stats: {'dimension': 1536,
     'index_fullness': 0.0,
     'metric': 'dotproduct',
     'namespaces': {},
     'total_vector_count': 0,
     'vector_type': 'dense'}
    ```

#### 把資料集 upsert 進 Pinecone index

分批處理資料集：對每筆合併後的文字產生 embedding、準備 metadata（包含獨立的 Question 與 Answer 欄位），再把每個批次 upsert 進 index。需要的話也可以更新特定項目的 metadata。

```python
batch_size = 32
for i in tqdm(range(0, len(ds_dataframe['merged']), batch_size), desc="Upserting to Pinecone"):
    i_end = min(i + batch_size, len(ds_dataframe['merged']))
    lines_batch = ds_dataframe['merged'][i: i_end]
    ids_batch = [str(n) for n in range(i, i_end)]
    
    # Create embeddings for the current batch.
    res = client.embeddings.create(input=[line for line in lines_batch], model=MODEL)
    embeds = [record.embedding for record in res.data]
    
    # Prepare metadata by extracting original Question and Answer.
    meta = []
    for record in ds_dataframe.iloc[i:i_end].to_dict('records'):
        q_text = record['Question']
        a_text = record['Response']
        # Optionally update metadata for specific entries.
        meta.append({"Question": q_text, "Answer": a_text})
    
    # Upsert the batch into Pinecone.
    vectors = list(zip(ids_batch, embeds, meta))
    index.upsert(vectors=vectors)
```

??? note "輸出"

    ```text
    Upserting to Pinecone: 100%|██████████| 4/4 [00:06<00:00,  1.64s/it]
    ```

![Pinecone Image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/responses_pinecone_rag.png)

### 查詢 Pinecone Index

建立一個自然語言查詢，算出它的 embedding，在 Pinecone index 上做相似度搜尋。回傳結果的 metadata 提供生成答案所需的脈絡。

```python
def query_pinecone_index(client, index, model, query_text):
    # Generate an embedding for the query.
    query_embedding = client.embeddings.create(input=query_text, model=model).data[0].embedding

    # Query the index and return top 5 matches.
    res = index.query(vector=[query_embedding], top_k=5, include_metadata=True)
    print("Query Results:")
    for match in res['matches']:
        print(f"{match['score']:.2f}: {match['metadata'].get('Question', 'N/A')} - {match['metadata'].get('Answer', 'N/A')}")
    return res
```

```python
# Example usage with a different query from the train/test set
query = (
    "A 45-year-old man with a history of alcohol use presents with symptoms including confusion, ataxia, and ophthalmoplegia. "
    "What is the most likely diagnosis and the recommended treatment?"
)
query_pinecone_index(client, index, MODEL, query)
```

??? note "輸出"

    ```text
    Query Results:
    0.70: A 45-year-old man with a history of alcohol use, who has been abstinent for the past 10 years, presents with sudden onset dysarthria, shuffling gait, and intention tremors. Given this clinical presentation and history, what is the most likely diagnosis? - Considering the clinical presentation of sudden onset dysarthria, shuffling gait, and intention tremors in a 45-year-old man with a history of alcohol use who has been abstinent for the past 10 years, the most likely diagnosis is acquired hepatocerebral degeneration.

    This condition is associated with chronic liver disease, which can often be a consequence of long-term alcohol use. Despite the patient's abstinence from alcohol for a decade, previous alcohol use may have led to underlying liver dysfunction. This dysfunction, even if subclinical, can cause encephalopathy due to the accumulation of neurotoxic substances that affect the brain. The sudden onset of these neurological symptoms aligns with how acquired hepatocerebral degeneration can manifest, making it a probable diagnosis in this scenario.
    0.55: A 45-year-old man presents with symptoms including a wide-based gait, a blank facial expression, hallucinations, memory issues, a resting tremor that resolves with movement, and bradykinesia. Based on these clinical findings, what is most likely to be observed in the histological specimen of his brain? - Based on the clinical findings presented—wide-based gait, blank facial expression, hallucinations, memory issues, resting tremor that resolves with movement, and bradykinesia—it is likely that the 45-year-old man is experiencing a condition related to Parkinsonism, possibly Parkinson's disease or dementia with Lewy bodies. Both of these conditions are associated with the presence of Lewy bodies in the brain. Lewy bodies are abnormal aggregates of protein, primarily alpha-synuclein, which can cause both the motor and cognitive symptoms observed in this patient. Therefore, in the histological specimen of his brain, you would most likely observe the presence of Lewy bodies.
    0.53: A 73-year-old man is evaluated for increasing forgetfulness, getting lost while walking, irritability, and difficulty recalling recent events while retaining detailed memories from over 20 years ago. On examination, he is oriented to person and place but disoriented to time, and an MRI of the brain reveals significant changes. Considering these symptoms and the imaging findings, what is the most likely underlying pathological process contributing to the patient's condition? - The symptoms and MRI findings of this 73-year-old man suggest the most likely underlying pathological process is the buildup of amyloid-beta plaques and tau protein tangles, which are characteristic of Alzheimer's disease. These changes often begin in brain regions involved in memory, such as the hippocampus and temporal lobes, leading to the gradual memory decline, disorientation, and personality changes observed in the patient.
    0.42: A 2-day-old male newborn delivered at 36 weeks presents with generalized convulsions, lethargy, feeding difficulties, icterus, purpura, posterior uveitis, and failed auditory screening. Cranial ultrasonography shows ventricular dilatation and hyperechoic foci in multiple brain areas. Considering these clinical signs and history, what is the most likely diagnosis? - The symptoms and findings you've described in this 2-day-old newborn point towards congenital Toxoplasmosis. The combination of neurological symptoms (such as convulsions and ventricular dilatation with hyperechoic foci), the presence of posterior uveitis, and the skin manifestations like purpura, all fit into the classic presentation of a TORCH infection. Toxoplasmosis, specifically, is known to cause widespread calcifications in the brain, not limited to the periventricular areas, which matches the ultrasound findings. Additionally, while hearing loss is more traditionally associated with CMV, it can also occur in Toxoplasmosis. Thus, the most likely diagnosis given this clinical picture is congenital Toxoplasmosis.
    0.42: A 45-year-old male patient experiences double vision specifically when walking upstairs. Considering his well-controlled history of Type-II diabetes, which cranial nerve is most likely involved in his symptoms? - Based on the symptoms described, the cranial nerve most likely involved in the double vision experienced by this patient while walking upstairs is the trochlear nerve, or cranial nerve IV. This nerve controls the superior oblique muscle, which plays a role in stabilizing the eye during certain movements, including the coordination required when looking upwards while walking upstairs. Given the patient's history of diabetes, cranial neuropathies can occur, and CN IV involvement can lead to vertical diplopia that becomes noticeable during specific activities like walking up stairs. Therefore, the trochlear nerve is a likely candidate for the involvement in these symptoms.
    ```

    ```text
    {'matches': [{'id': '1',
                  'metadata': {'Answer': 'Considering the clinical presentation of '
                                         'sudden onset dysarthria, shuffling gait, '
                                         'and intention tremors in a 45-year-old '
                                         'man with a history of alcohol use who '
                                         'has been abstinent for the past 10 '
                                         'years, the most likely diagnosis is '
                                         'acquired hepatocerebral degeneration.\n'
                                         '\n'
                                         'This condition is associated with '
                                         'chronic liver disease, which can often '
                                         'be a consequence of long-term alcohol '
                                         "use. Despite the patient's abstinence "
                                         'from alcohol for a decade, previous '
                                         'alcohol use may have led to underlying '
                                         'liver dysfunction. This dysfunction, '
                                         'even if subclinical, can cause '
                                         'encephalopathy due to the accumulation '
                                         'of neurotoxic substances that affect the '
                                         'brain. The sudden onset of these '
                                         'neurological symptoms aligns with how '
                                         'acquired hepatocerebral degeneration can '
                                         'manifest, making it a probable diagnosis '
                                         'in this scenario.',
                               'Question': 'A 45-year-old man with a history of '
                                           'alcohol use, who has been abstinent '
                                           'for the past 10 years, presents with '
                                           'sudden onset dysarthria, shuffling '
                                           'gait, and intention tremors. Given '
                                           'this clinical presentation and '
                                           'history, what is the most likely '
                                           'diagnosis?'},
                  'score': 0.697534442,
                  'values': []},
                 {'id': '2',
                  'metadata': {'Answer': 'Based on the clinical findings '
                                         'presented—wide-based gait, blank facial '
                                         'expression, hallucinations, memory '
                                         'issues, resting tremor that resolves '
                                         'with movement, and bradykinesia—it is '
    ... (省略 118 行)
    ```

### 用檢索到的 context 生成回答

從查詢結果挑出最符合的一筆，用 OpenAI Responses API 把檢索到的 context 和原本的問題結合，生成最終答案。

```python
# Retrieve and concatenate top 3 match contexts.
matches = index.query(
    vector=[client.embeddings.create(input=query, model=MODEL).data[0].embedding],
    top_k=3,
    include_metadata=True
)['matches']

context = "\n\n".join(
    f"Question: {m['metadata'].get('Question', '')}\nAnswer: {m['metadata'].get('Answer', '')}"
    for m in matches
)
# Use the context to generate a final answer.
response = client.responses.create(
    model="gpt-4o",
    input=f"Provide the answer based on the context: {context} and the question: {query} as per the internal knowledge base",
)
print("\nFinal Answer:")
print(response.output_text)
```

??? note "輸出"

    ```text

    Final Answer:
    The presentation of confusion, ataxia, and ophthalmoplegia in a 45-year-old man with a history of alcohol use is suggestive of Wernicke's encephalopathy. This condition is caused by thiamine (vitamin B1) deficiency, often associated with chronic alcohol use.

    The recommended treatment is the immediate administration of thiamine, typically given intravenously or intramuscularly, to prevent progression to more severe neurological damage or Korsakoff syndrome.
    ```

### 調度多個工具呼叫

接著我們定義 Responses API 可用的內建功能，並以 Pinecone 為例加入呼叫外部向量庫的能力。

*Web Search Preview 工具*：讓模型做即時的網路搜尋並預覽結果，適合取得即時或最新的網路資訊。

*Pinecone Search 工具*：讓模型用語意搜尋查詢向量資料庫，特別適合取得已向量化儲存的相關文件，例如醫學文獻或其他特定領域內容。

```python
# Tools definition: The list of tools includes:
# - A web search preview tool.
# - A Pinecone search tool for retrieving medical documents.

# Define available tools.
tools = [   
    {"type": "web_search_preview",
      "user_location": {
        "type": "approximate",
        "country": "US",
        "region": "California",
        "city": "SF"
      },
      "search_context_size": "medium"},
    {
        "type": "function",
        "name": "PineconeSearchDocuments",
        "description": "Search for relevant documents based on the medical question asked by the user that is stored within the vector database using a semantic query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The natural language query to search the vector database."
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top results to return.",
                    "default": 3
                }
            },
            "required": ["query"],
            "additionalProperties": False
        }
    }
]
```

```python
# Example queries that the model should route appropriately.
queries = [
    {"query": "Who won the cricket world cup in 1983?"},
    {"query": "What is the most common cause of death in the United States according to the internet?"},
    {"query": ("A 7-year-old boy with sickle cell disease is experiencing knee and hip pain, "
               "has been admitted for pain crises in the past, and now walks with a limp. "
               "His exam shows a normal, cool hip with decreased range of motion and pain with ambulation. "
               "What is the most appropriate next step in management according to the internal knowledge base?")}
]
```

```python
# Process each query dynamically.
for item in queries:
    input_messages = [{"role": "user", "content": item["query"]}]
    print("\n🌟--- Processing Query ---🌟")
    print(f"🔍 **User Query:** {item['query']}")
    
    # Call the Responses API with tools enabled and allow parallel tool calls.
    response = client.responses.create(
        model="gpt-4o",
        input=[
            {"role": "system", "content": "When prompted with a question, select the right tool to use based on the question."
            },
            {"role": "user", "content": item["query"]}
        ],
        tools=tools,
        parallel_tool_calls=True
    )
    
    print("\n✨ **Initial Response Output:**")
    print(response.output)
    
    # Determine if a tool call is needed and process accordingly.
    if response.output:
        tool_call = response.output[0]
        if tool_call.type in ["web_search_preview", "function_call"]:
            tool_name = tool_call.name if tool_call.type == "function_call" else "web_search_preview"
            print(f"\n🔧 **Model triggered a tool call:** {tool_name}")
            
            if tool_name == "PineconeSearchDocuments":
                print("🔍 **Invoking PineconeSearchDocuments tool...**")
                res = query_pinecone_index(client, index, MODEL, item["query"])
                if res["matches"]:
                    best_match = res["matches"][0]["metadata"]
                    result = f"**Question:** {best_match.get('Question', 'N/A')}\n**Answer:** {best_match.get('Answer', 'N/A')}"
                else:
                    result = "**No matching documents found in the index.**"
                print("✅ **PineconeSearchDocuments tool invoked successfully.**")
            else:
                print("🔍 **Invoking simulated web search tool...**")
                result = "**Simulated web search result.**"
                print("✅ **Simulated web search tool invoked successfully.**")
            
            # Append the tool call and its output back into the conversation.
            input_messages.append(tool_call)
            input_messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": str(result)
            })
            
            # Get the final answer incorporating the tool's result.
            final_response = client.responses.create(
                model="gpt-4o",
                input=input_messages,
                tools=tools,
                parallel_tool_calls=True
            )
            print("\n💡 **Final Answer:**")
            print(final_response.output_text)
        else:
            # If no tool call is triggered, print the response directly.
            print("💡 **Final Answer:**")
            print(response.output_text)
```

??? note "輸出"

    ```text

    🌟--- Processing Query ---🌟
    🔍 **User Query:** Who won the cricket world cup in 1983?

    ✨ **Initial Response Output:**
    [ResponseOutputMessage(id='msg_67e6e7a9f7508191a9d18c3ff25310290811a0720cf47168', content=[ResponseOutputText(annotations=[], text='India won the Cricket World Cup in 1983.', type='output_text')], role='assistant', status='completed', type='message')]
    💡 **Final Answer:**
    India won the Cricket World Cup in 1983.

    🌟--- Processing Query ---🌟
    🔍 **User Query:** What is the most common cause of death in the United States according to the internet?

    ✨ **Initial Response Output:**
    [ResponseFunctionWebSearch(id='ws_67e6e7aad0248191ab974d4b09b460c90537f90023d2dd32', status='completed', type='web_search_call'), ResponseOutputMessage(id='msg_67e6e7ace08081918f06b5cac32e8c0e0537f90023d2dd32', content=[ResponseOutputText(annotations=[AnnotationURLCitation(end_index=363, start_index=225, title='10 Leading Causes of Death in the U.S.', type='url_citation', url='https://www.usnews.com/news/healthiest-communities/slideshows/top-10-causes-of-death-in-america?slide=11&utm_source=openai'), AnnotationURLCitation(end_index=753, start_index=625, title='Top causes of death in the US — see the CDC’s latest list - Rifnote', type='url_citation', url='https://rifnote.com/health/2024/08/11/top-causes-of-death-in-the-us-see-the-cdcs-latest-list/?utm_source=openai'), AnnotationURLCitation(end_index=1014, start_index=886, title='Top causes of death in the US — see the CDC’s latest list - Rifnote', type='url_citation', url='https://rifnote.com/health/2024/08/11/top-causes-of-death-in-the-us-see-the-cdcs-latest-list/?utm_source=openai'), AnnotationURLCitation(end_index=1216, start_index=1061, title='US deaths are down and life expectancy is up, but improvements are slowing', type='url_citation', url='https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai'), AnnotationURLCitation(end_index=1394, start_index=1219, title='A Mysterious Health Wave Is Breaking Out Across the U.S.', type='url_citation', url='https://www.theatlantic.com/ideas/archive/2024/12/violence-obesity-overdoses-health-covid/681079/?utm_source=openai')], text='According to the Centers for Disease Control and Prevention (CDC), heart disease was the leading cause of death in the United States in 2023, accounting for 680,980 deaths, which is approximately 22% of all deaths that year. ([usnews.com](https://www.usnews.com/news/healthiest-communities/slideshows/top-10-causes-of-death-in-america?slide=11&utm_source=openai))\n\nThe top 10 causes of death in the U.S. for 2023 were:\n\n1. Heart disease\n2. Cancer\n3. Unintentional injury\n4. Stroke\n5. Chronic lower respiratory diseases\n6. Alzheimer’s disease\n7. Diabetes\n8. Kidney disease\n9. Chronic liver disease and cirrhosis\n10. COVID-19\n\n([rifnote.com](https://rifnote.com/health/2024/08/11/top-causes-of-death-in-the-us-see-the-cdcs-latest-list/?utm_source=openai))\n\nNotably, COVID-19, which was the fourth leading cause of death in 2022, dropped to the tenth position in 2023, with 76,446 deaths. ([rifnote.com](https://rifnote.com/health/2024/08/11/top-causes-of-death-in-the-us-see-the-cdcs-latest-list/?utm_source=openai))\n\n\n## Recent Trends in U.S. Mortality Rates:\n- [US deaths are down and life expectancy is up, but improvements are slowing](https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai)\n- [A Mysterious Health Wave Is Breaking Out Across the U.S.](https://www.theatlantic.com/ideas/archive/2024/12/violence-obesity-overdoses-health-covid/681079/?utm_source=openai) ', type='output_text')], role='assistant', status='completed', type='message')]
    💡 **Final Answer:**
    According to the Centers for Disease Control and Prevention (CDC), heart disease was the leading cause of death in the United States in 2023, accounting for 680,980 deaths, which is approximately 22% of all deaths that year. ([usnews.com](https://www.usnews.com/news/healthiest-communities/slideshows/top-10-causes-of-death-in-america?slide=11&utm_source=openai))

    The top 10 causes of death in the U.S. for 2023 were:

    1. Heart disease
    2. Cancer
    3. Unintentional injury
    4. Stroke
    5. Chronic lower respiratory diseases
    6. Alzheimer’s disease
    7. Diabetes
    8. Kidney disease
    9. Chronic liver disease and cirrhosis
    10. COVID-19

    ([rifnote.com](https://rifnote.com/health/2024/08/11/top-causes-of-death-in-the-us-see-the-cdcs-latest-list/?utm_source=openai))

    Notably, COVID-19, which was the fourth leading cause of death in 2022, dropped to the tenth position in 2023, with 76,446 deaths. ([rifnote.com](https://rifnote.com/health/2024/08/11/top-causes-of-death-in-the-us-see-the-cdcs-latest-list/?utm_source=openai))


    ## Recent Trends in U.S. Mortality Rates:
    - [US deaths are down and life expectancy is up, but improvements are slowing](https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai)
    - [A Mysterious Health Wave Is Breaking Out Across the U.S.](https://www.theatlantic.com/ideas/archive/2024/12/violence-obesity-overdoses-health-covid/681079/?utm_source=openai) 

    🌟--- Processing Query ---🌟
    ... (省略 21 行)
    ```

如上所示，模型會依查詢呼叫合適的工具，以得出最佳回答。

舉例來說，在第三個例子中，模型呼叫 `PineconeSearchDocuments` 時，程式會把目前的查詢傳給 `query_pinecone_index`，並回傳最符合的結果當 context。遇到一般或非健康相關的問題，或使用者明確要求上網搜尋時，程式會呼叫 `web_search_call`。其他問題，模型可能不用工具就直接回答。

最後，工具呼叫和它的輸出會被附加到對話中，再由 Responses API 生成最終回答。

### 多工具調度流程

接著我們修改輸入的查詢和給 Responses API 的 system instructions，讓它依照工具呼叫的順序執行並產生輸出。

```python
# Process one query as an example to understand the tool calls and function calls as part of the response output
item = "What is the most common cause of death in the United States"

# Initialize input messages with the user's query.
input_messages = [{"role": "user", "content": item}]
print("\n🌟--- Processing Query ---🌟")
print(f"🔍 **User Query:** {item}")
    
    # Call the Responses API with tools enabled and allow parallel tool calls.
print("\n🔧 **Calling Responses API with Tools Enabled**")
print("\n🕵️‍♂️ **Step 1: Web Search Call**")
print("   - Initiating web search to gather initial information.")
print("\n📚 **Step 2: Pinecone Search Call**")
print("   - Querying Pinecone to find relevant examples from the internal knowledge base.")
    
response = client.responses.create(
        model="gpt-4o",
        input=[
            {"role": "system", "content": "Every time it's prompted with a question, first call the web search tool for results, then call `PineconeSearchDocuments` to find real examples in the internal knowledge base."},
            {"role": "user", "content": item}
        ],
        tools=tools,
        parallel_tool_calls=True
    )
    
# Print the initial response output.
print("input_messages", input_messages)

print("\n✨ **Initial Response Output:**")
print(response.output)
```

??? note "輸出"

    ```text

    🌟--- Processing Query ---🌟
    🔍 **User Query:** What is the most common cause of death in the United States

    🔧 **Calling Responses API with Tools Enabled**

    🕵️‍♂️ **Step 1: Web Search Call**
       - Initiating web search to gather initial information.

    📚 **Step 2: Pinecone Search Call**
       - Querying Pinecone to find relevant examples from the internal knowledge base.
    input_messages [{'role': 'user', 'content': 'What is the most common cause of death in the United States'}]

    ✨ **Initial Response Output:**
    [ResponseFunctionWebSearch(id='ws_67e6e83241ac81918f93ffc96491ec390fdddafaeefcefc1', status='completed', type='web_search_call'), ResponseOutputMessage(id='msg_67e6e833a2cc8191a9df22f324a876b00fdddafaeefcefc1', content=[ResponseOutputText(annotations=[AnnotationURLCitation(end_index=698, start_index=613, title='Products - Data Briefs - Number 521 - December 2024', type='url_citation', url='https://www.cdc.gov/nchs/products/databriefs/db521.htm?utm_source=openai'), AnnotationURLCitation(end_index=984, start_index=891, title='US deaths are down and life expectancy is up, but improvements are slowing', type='url_citation', url='https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai'), AnnotationURLCitation(end_index=1186, start_index=1031, title='US deaths are down and life expectancy is up, but improvements are slowing', type='url_citation', url='https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai')], text="As of 2023, the leading causes of death in the United States are:\n\n1. **Heart Disease**: 680,981 deaths\n2. **Cancer**: 613,352 deaths\n3. **Unintentional Injuries**: 222,698 deaths\n4. **Stroke**: 162,639 deaths\n5. **Chronic Lower Respiratory Diseases**: 145,357 deaths\n6. **Alzheimer's Disease**: 114,034 deaths\n7. **Diabetes**: 95,190 deaths\n8. **Kidney Disease**: 55,253 deaths\n9. **Chronic Liver Disease and Cirrhosis**: 52,222 deaths\n10. **COVID-19**: 49,932 deaths\n\nNotably, COVID-19 has dropped from the fourth leading cause in 2022 to the tenth in 2023, reflecting a significant decrease in related deaths. ([cdc.gov](https://www.cdc.gov/nchs/products/databriefs/db521.htm?utm_source=openai))\n\nOverall, the U.S. experienced a decline in total deaths and a modest increase in life expectancy in 2023, attributed to reductions in deaths from COVID-19, heart disease, and drug overdoses. ([apnews.com](https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai))\n\n\n## Recent Trends in U.S. Mortality Rates:\n- [US deaths are down and life expectancy is up, but improvements are slowing](https://apnews.com/article/be061f9f14c883178eea6dddc9550e60?utm_source=openai) ", type='output_text')], role='assistant', status='completed', type='message'), ResponseFunctionToolCall(arguments='{"query":"most common cause of death in the United States","top_k":3}', call_id='call_6YWhEw3QSI7wGZBlNs5Pz4zI', name='PineconeSearchDocuments', type='function_call', id='fc_67e6e8364e4c819198501fba5d3f155b0fdddafaeefcefc1', status='completed')]
    ```

```python
# Understand the tool calls and function calls as part of the response output

import pandas as pd

# Create a list to store the tool call and function call details
tool_calls = []

# Iterate through the response output and collect the details
for i in response.output:
    tool_calls.append({
        "Type": i.type,
        "Call ID": i.call_id if hasattr(i, 'call_id') else i.id if hasattr(i, 'id') else "N/A",
        "Output": str(i.output) if hasattr(i, 'output') else "N/A",
        "Name": i.name if hasattr(i, 'name') else "N/A"
    })

# Convert the list to a DataFrame for tabular display
df_tool_calls = pd.DataFrame(tool_calls)

# Display the DataFrame
df_tool_calls
```

??? note "輸出"

    ```text
                  Type                                            Call ID Output  \
    0  web_search_call  ws_67e6e83241ac81918f93ffc96491ec390fdddafaeef...    N/A   
    1          message  msg_67e6e833a2cc8191a9df22f324a876b00fdddafaee...    N/A   
    2    function_call                      call_6YWhEw3QSI7wGZBlNs5Pz4zI    N/A   

                          Name  
    0                      N/A  
    1                      N/A  
    2  PineconeSearchDocuments
    ```

```python
tool_call_1 = response.output[0]
print(tool_call_1)
print(tool_call_1.id)

tool_call_2 = response.output[2]
print(tool_call_2)
print(tool_call_2.call_id)
```

??? note "輸出"

    ```text
    ResponseFunctionWebSearch(id='ws_67e6e83241ac81918f93ffc96491ec390fdddafaeefcefc1', status='completed', type='web_search_call')
    ws_67e6e83241ac81918f93ffc96491ec390fdddafaeefcefc1
    ResponseFunctionToolCall(arguments='{"query":"most common cause of death in the United States","top_k":3}', call_id='call_6YWhEw3QSI7wGZBlNs5Pz4zI', name='PineconeSearchDocuments', type='function_call', id='fc_67e6e8364e4c819198501fba5d3f155b0fdddafaeefcefc1', status='completed')
    call_6YWhEw3QSI7wGZBlNs5Pz4zI
    ```

```python
# append the tool call and its output back into the conversation.
input_messages.append(response.output[2])
input_messages.append({
    "type": "function_call_output",
    "call_id": tool_call_2.call_id,
    "output": str(result)
})
print(input_messages)
```

??? note "輸出"

    ```text
    [{'role': 'user', 'content': 'What is the most common cause of death in the United States'}, ResponseFunctionToolCall(arguments='{"query":"most common cause of death in the United States"}', call_id='call_8Vzsn4RwMOgXyX98UpZY8hls', name='PineconeSearchDocuments', type='function_call', id='fc_67e348f36f7c81919d0aeef1855df3f20d0bd7f2a5744b88', status='completed')]
    [{'role': 'user', 'content': 'What is the most common cause of death in the United States'}, ResponseFunctionToolCall(arguments='{"query":"most common cause of death in the United States"}', call_id='call_8Vzsn4RwMOgXyX98UpZY8hls', name='PineconeSearchDocuments', type='function_call', id='fc_67e348f36f7c81919d0aeef1855df3f20d0bd7f2a5744b88', status='completed'), {'type': 'function_call_output', 'call_id': 'call_8Vzsn4RwMOgXyX98UpZY8hls', 'output': "**Question:** A 7-year-old boy with sickle cell disease is experiencing knee and hip pain, has been admitted for pain crises in the past, and now walks with a limp. His physical exam shows a normal and cool hip to the touch, with decreased range of motion at the hip and pain with ambulation. Given these findings, what is the most appropriate next step in the management of this patient's hip pain?\n**Answer:** In managing the hip pain of a 7-year-old boy with sickle cell disease, who presents with knee and hip pain, a limp, and decreased range of motion in the hip, the most appropriate next step is to obtain an X-ray of the hip. This will help evaluate the possibility of avascular necrosis (AVN) or other structural abnormalities. X-rays are typically the first-line imaging technique in such cases due to their accessibility and ability to reveal gross pathological changes. If the X-ray does not provide conclusive information and clinical suspicion of AVN remains high, an MRI may subsequently be considered for a more detailed assessment."}]
    ```

```python

# Get the final answer incorporating the tool's result.
print("\n🔧 **Calling Responses API for Final Answer**")

response_2 = client.responses.create(
    model="gpt-4o",
    input=input_messages,
)
print(response_2)
```

??? note "輸出"

    ```text

    🔧 **Calling Responses API for Final Answer**
    Response(id='resp_67e6e886ac7081918b07224fb1ed38ab05c4a598f9697c7c', created_at=1743186054.0, error=None, incomplete_details=None, instructions=None, metadata={}, model='gpt-4o-2024-08-06', object='response', output=[ResponseOutputMessage(id='msg_67e6e8872ddc81918e92c9e4508abbe005c4a598f9697c7c', content=[ResponseOutputText(annotations=[], text='The most common cause of death in the United States is heart disease.', type='output_text')], role='assistant', status='completed', type='message')], parallel_tool_calls=True, temperature=1.0, tool_choice='auto', tools=[], top_p=1.0, max_output_tokens=None, previous_response_id=None, reasoning=Reasoning(effort=None, generate_summary=None), status='completed', text=ResponseTextConfig(format=ResponseFormatText(type='text')), truncation='disabled', usage=ResponseUsage(input_tokens=37, input_tokens_details=InputTokensDetails(cached_tokens=0), output_tokens=15, output_tokens_details=OutputTokensDetails(reasoning_tokens=0), total_tokens=52), user=None, store=False)
    ```

```python
# print the final answer
print(response_2.output_text)
```

??? note "輸出"

    ```text
    The most common cause of death in the United States is heart disease.
    ```


這裡我們用 OpenAI 的 Responses API 搭配多個工具實作了 RAG。模型會依查詢選擇工具：內建的 web search 處理一般問題，function call 則能從 Pinecone 這類向量資料庫取回內部醫療 context。我們也依 Responses API 的 instructions 把多個工具呼叫依序串起來，產生最終回答。

接下來你可以繼續實驗並延伸這些概念，也可以多看其他資源和範例，加深理解並應用在自己的專案上。

祝寫程式愉快！

## 重點整理

- Responses API 能同時掛內建工具（web search）和自訂 function，由模型依問題決定用哪個。
- 外部向量資料庫（如 Pinecone）可以包成 function tool，接進 RAG 流程。
- 要建 index 前先確定 embedding 的維度，再批次 upsert，metadata 順便存原始 Question 與 Answer。
- tool call 與其輸出要附加回對話，模型才能產生最後答案。
- 靠 instructions 可以規定工具的呼叫順序，做出多步驟的串接。

## 練習

1. 換一個問題，分別試一般常識、醫療問題和「請上網搜尋」，觀察模型選了哪個工具。
2. 把查詢 Pinecone 時的 `top_k` 改成 3，把三筆結果都當 context 傳給 Responses API，比較答案有沒有變好。
3. 修改 system instructions，要求模型一定先查 Pinecone、再用 web search 補充，檢查 tool call 的順序是否照辦。
