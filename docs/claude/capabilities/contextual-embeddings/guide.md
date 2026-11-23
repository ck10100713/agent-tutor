---
translated: true
source: capabilities/contextual-embeddings/guide.ipynb
---
# 用 Contextual Retrieval 強化 RAG

> 原文：[capabilities/contextual-embeddings/guide.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/contextual-embeddings/guide.ipynb)

在 embedding 之前先替每個 chunk 加上 context，再搭配 prompt caching 壓低成本，藉此提升 RAG 的準確度。

## 這篇在做什麼

傳統 RAG 把文件切成小 chunk 再做檢索，但單獨一個 chunk 常常缺少上下文。這篇用 Claude 替每個 chunk 先寫一段「這塊在整份文件裡的位置與內容」的說明，再一起 embed，檢索準確度就會提升。拿 9 個 codebase 當知識庫，從 baseline 一路做到 Contextual BM25 和 reranking，並用 Pass@k 量化每一步的進步。

## 學完你會

- 寫出一個基本的 RAG pipeline（VectorDB 加 cosine similarity），並用 Pass@5/10/20 量出 baseline
- 用 Claude 加 prompt caching 替每個 chunk 產生 context，建出 `ContextualVectorDB`，並看懂 cache 省了多少錢
- 把 Contextual BM25 混合搜尋和 Cohere reranking 疊上去，知道每一層各補哪個弱點

## 開跑前

- 需要 Anthropic、Voyage AI、Cohere 三組 API key
- BM25 部分要在本機用 Docker 跑 Elasticsearch（可選）
- 整個資料集跑完大約 5 到 10 美元，30 到 45 分鐘

> 注意：想更了解 Contextual Retrieval 的背景，以及在其他資料集上的評測，建議讀搭配的[部落格文章](https://www.anthropic.com/news/contextual-retrieval)。

Retrieval Augmented Generation (RAG) 讓 Claude 回答時可以用到你內部的知識庫、codebase 或任何文件集。企業越來越多用 RAG 來改善客服、公司內部文件問答、財務與法務分析、程式碼生成等流程。

在[另一份 guide](https://github.com/anthropics/anthropic-cookbook/blob/main/capabilities/retrieval_augmented_generation/guide.ipynb) 裡，我們建了一個基本的檢索系統、示範怎麼評估效果，並介紹幾個改善技巧。這份 guide 要介紹其中一個提升檢索效果的技術：Contextual Embeddings。

傳統 RAG 通常把文件切成較小的 chunk 以利檢索。這在很多場景夠用，但當單一 chunk 缺乏足夠上下文時就會出問題。Contextual Embeddings 的做法是在 embedding 之前，先替每個 chunk 補上相關的 context。每個 chunk 的品質變好，檢索就更準，整體表現也更好。在我們測試的所有資料來源上平均，Contextual Embeddings 讓 top-20 chunk 的檢索失敗率降低了 35%。

同樣的 chunk context 也可以拿去做 BM25 搜尋，進一步提升檢索表現。這部分在「Contextual BM25」一節介紹。

這份 guide 會用 9 個 codebase 當知識庫，示範怎麼建出並優化 Contextual Retrieval 系統，步驟如下：

1) 先建一個基本的檢索 pipeline，作為效能 baseline。

2) Contextual Embeddings：它是什麼、為什麼有效，以及 prompt caching 怎麼讓它在 production 用得起。

3) 實作 Contextual Embeddings 並展示效能提升。

4) Contextual BM25：用 *contextual* BM25 做混合搜尋來提升表現。

5) 用 reranking 再往上推。

### 評估指標與資料集

我們用已經切好 chunk 的 9 個 codebase，切法是基本的字元切割。評估資料集有 248 個 query，每個 query 都有一個「golden chunk」。評估指標是 Pass@k：檢查每個 query 的 golden document 有沒有出現在前 k 筆檢索結果裡。這個案例中，Contextual Embeddings 把 Pass@10 從約 87% 提升到約 95%。

程式碼檔案和它們的 chunk 在 `data/codebase_chunks.json`，評估資料集在 `data/evaluation_set.jsonl`。

#### 補充說明

Prompt caching 對控制這種檢索方式的成本很有幫助。這個功能目前在 Anthropic 第一方 API 上可用，AWS Bedrock 和 GCP Vertex 的第三方環境也即將支援。我們知道很多客戶用 AWS Knowledge Bases 和 GCP Vertex AI API 來建 RAG，這個方法在兩個平台上稍微客製一下都能用。想了解細節可以聯絡 Anthropic 或你的 AWS/GCP 帳號團隊。

為了讓這個方法在 Bedrock 上更好用，AWS 團隊提供了一份程式碼，可以實作一個替每份文件加 context 的 Lambda function。部署之後，你在設定 [Bedrock Knowledge Base](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-create.html) 時，可以把它選成自訂 chunking 選項。程式碼在 `contextual-rag-lambda-function`，主要的 Lambda 程式在 `lambda_function.py`。

## 目錄

1) Setup

2) Basic RAG

3) Contextual Embeddings

4) Contextual BM25

5) Reranking

## Setup

開始之前請確認你具備：

**技術能力：**
- 中階 Python 程式能力
- 對 RAG (Retrieval Augmented Generation) 有基本了解
- 熟悉 vector database 和 embedding
- 基本的命令列操作

**系統需求：**
- Python 3.8 以上
- 已安裝並啟動 Docker（可選，用於 BM25 搜尋）
- 4GB 以上可用 RAM
- 約 5 到 10 GB 磁碟空間給 vector database

**API 存取：**
- [Anthropic API key](https://console.anthropic.com/)（免費額度就夠）
- [Voyage AI API key](https://www.voyageai.com/)
- [Cohere API key](https://cohere.com/)

**時間與成本：**
- 預計完成時間：30 到 45 分鐘
- API 費用：跑完整個資料集約 5 到 10 美元

### 套件

會用到幾個套件：

1) `anthropic`：跟 Claude 互動

2) `voyageai`：產生高品質 embedding

3) `cohere`：做 reranking

4) `elasticsearch`：高效能 BM25 搜尋

5) `pandas`、`numpy`、`matplotlib`、`scikit-learn`：資料處理和視覺化

### 環境變數

確認已設好以下環境變數：

```
- VOYAGE_API_KEY
- ANTHROPIC_API_KEY
- COHERE_API_KEY
```

```python
%%capture
%pip install --upgrade anthropic voyageai cohere elasticsearch pandas numpy
```

我們先把 model 名稱定義在最前面，之後有新 model 出來比較好換。

```python
MODEL_NAME = "claude-haiku-5-5"
```

先初始化 Anthropic client，後面會用它產生 contextual 描述。

```python
import os

import anthropic

client = anthropic.Anthropic(
    # This is the default and can be omitted
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)
```

## 初始化 Vector DB 類別

我們建一個 VectorDB 類別來處理 embedding 儲存和相似度搜尋。這個類別在 RAG pipeline 裡有三個功能：

1. **Embedding 產生**：用 Voyage AI 的 embedding model 把文字 chunk 轉成向量
2. **儲存與快取**：把 embedding 存到硬碟，避免重算（省時間也省 API 費用）
3. **相似度搜尋**：用 cosine similarity 找出跟 query 最相關的 chunk

這份 guide 用的是簡單的記憶體內 vector database，用 pickle 序列化。這樣程式好懂，也不需要外部依賴。類別產生 embedding 之後會自動存檔，所以 embedding 的費用你只需要付一次。

Production 建議改用託管的 vector database 服務。

下面的 VectorDB 類別，介面設計跟 production 方案一致，之後要換很容易。主要特色有批次處理（一次 128 個 chunk）、用 tqdm 顯示進度，以及 query 快取，讓評估時重複搜尋更快。

```python
import json
import pickle
from typing import Any

import numpy as np
import voyageai
from tqdm import tqdm


class VectorDB:
    def __init__(self, name: str, api_key=None):
        if api_key is None:
            api_key = os.getenv("VOYAGE_API_KEY")
        self.client = voyageai.Client(api_key=api_key)
        self.name = name
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = f"./data/{name}/vector_db.pkl"

    def load_data(self, dataset: list[dict[str, Any]]):
        if self.embeddings and self.metadata:
            print("Vector database is already loaded. Skipping data loading.")
            return
        if os.path.exists(self.db_path):
            print("Loading vector database from disk.")
            self.load_db()
            return

        texts_to_embed = []
        metadata = []
        total_chunks = sum(len(doc["chunks"]) for doc in dataset)

        with tqdm(total=total_chunks, desc="Processing chunks") as pbar:
            for doc in dataset:
                for chunk in doc["chunks"]:
                    texts_to_embed.append(chunk["content"])
                    metadata.append(
                        {
                            "doc_id": doc["doc_id"],
                            "original_uuid": doc["original_uuid"],
                            "chunk_id": chunk["chunk_id"],
                            "original_index": chunk["original_index"],
                            "content": chunk["content"],
                        }
                    )
                    pbar.update(1)

        self._embed_and_store(texts_to_embed, metadata)
        self.save_db()

        print(f"Vector database loaded and saved. Total chunks processed: {len(texts_to_embed)}")

    def _embed_and_store(self, texts: list[str], data: list[dict[str, Any]]):
        batch_size = 128
        with tqdm(total=len(texts), desc="Embedding chunks") as pbar:
            result = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_result = self.client.embed(batch, model="voyage-2").embeddings
                result.extend(batch_result)
                pbar.update(len(batch))

        self.embeddings = result
        self.metadata = data

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        if query in self.query_cache:
            query_embedding = self.query_cache[query]
        else:
            query_embedding = self.client.embed([query], model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding

        if not self.embeddings:
            raise ValueError("No data loaded in the vector database.")

        similarities = np.dot(self.embeddings, query_embedding)
        top_indices = np.argsort(similarities)[::-1][:k]

        top_results = []
        for idx in top_indices:
            result = {
                "metadata": self.metadata[idx],
                "similarity": float(similarities[idx]),
            }
            top_results.append(result)

        return top_results

    def save_db(self):
        data = {
            "embeddings": self.embeddings,
            "metadata": self.metadata,
            "query_cache": json.dumps(self.query_cache),
        }
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "wb") as file:
            pickle.dump(data, file)

    def load_db(self):
        if not os.path.exists(self.db_path):
            raise ValueError(
                "Vector database file not found. Use load_data to create a new database."
            )
        with open(self.db_path, "rb") as file:
            data = pickle.load(file)
        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"]
        self.query_cache = json.loads(data["query_cache"])
```

現在用這個類別載入資料集。

```python
# Load your transformed dataset
with open("data/codebase_chunks.json") as f:
    transformed_dataset = json.load(f)

# Initialize the VectorDB
base_db = VectorDB("base_db")

# Load and process the data
base_db.load_data(transformed_dataset)
```

??? note "輸出"

    ```text
    Processing chunks: 100%|██████████| 737/737 [00:00<00:00, 985400.72it/s]
    Embedding chunks: 100%|██████████| 737/737 [00:42<00:00, 17.28it/s]
    ```

    ```text
    Vector database loaded and saved. Total chunks processed: 737
    ```

## Basic RAG

先用最陽春的做法建一個基本 RAG pipeline，業界常叫它「Naive RAG」。基本 RAG 包含三個步驟：

1) 依標題切文件，每塊只包含該小節的內容

2) 對每份文件做 embedding

3) 用 cosine similarity 檢索文件來回答 query

```python
import json
from collections.abc import Callable
from typing import Any

from tqdm import tqdm


def load_jsonl(file_path: str) -> list[dict[str, Any]]:
    """Load JSONL file and return a list of dictionaries."""
    with open(file_path) as file:
        return [json.loads(line) for line in file]


def evaluate_retrieval(
    queries: list[dict[str, Any]], retrieval_function: Callable, db, k: int = 20
) -> dict[str, float]:
    total_score = 0
    total_queries = len(queries)

    for query_item in tqdm(queries, desc="Evaluating retrieval"):
        query = query_item["query"]
        golden_chunk_uuids = query_item["golden_chunk_uuids"]

        # Find all golden chunk contents
        golden_contents = []
        for doc_uuid, chunk_index in golden_chunk_uuids:
            golden_doc = next(
                (doc for doc in query_item["golden_documents"] if doc["uuid"] == doc_uuid), None
            )
            if not golden_doc:
                print(f"Warning: Golden document not found for UUID {doc_uuid}")
                continue

            golden_chunk = next(
                (chunk for chunk in golden_doc["chunks"] if chunk["index"] == chunk_index), None
            )
            if not golden_chunk:
                print(
                    f"Warning: Golden chunk not found for index {chunk_index} in document {doc_uuid}"
                )
                continue

            golden_contents.append(golden_chunk["content"].strip())

        if not golden_contents:
            print(f"Warning: No golden contents found for query: {query}")
            continue

        retrieved_docs = retrieval_function(query, db, k=k)

        # Count how many golden chunks are in the top k retrieved documents
        chunks_found = 0
        for golden_content in golden_contents:
            for doc in retrieved_docs[:k]:
                retrieved_content = (
                    doc["metadata"]
                    .get("original_content", doc["metadata"].get("content", ""))
                    .strip()
                )
                if retrieved_content == golden_content:
                    chunks_found += 1
                    break

        query_score = chunks_found / len(golden_contents)
        total_score += query_score

    average_score = total_score / total_queries
    pass_at_n = average_score * 100
    return {"pass_at_n": pass_at_n, "average_score": average_score, "total_queries": total_queries}


def retrieve_base(query: str, db, k: int = 20) -> list[dict[str, Any]]:
    """
    Retrieve relevant documents using either VectorDB or ContextualVectorDB.

    :param query: The query string
    :param db: The VectorDB or ContextualVectorDB instance
    :param k: Number of top results to retrieve
    :return: List of retrieved documents
    """
    return db.search(query, k=k)


def evaluate_db(db, original_jsonl_path: str, k):
    # Load the original JSONL data for queries and ground truth
    original_data = load_jsonl(original_jsonl_path)

    # Evaluate retrieval
    results = evaluate_retrieval(original_data, retrieve_base, db, k)
    return results


def evaluate_and_display(db, jsonl_path: str, k_values: list[int] = None, db_name: str = ""):
    """
    Evaluate retrieval performance across multiple k values and display formatted results.

    Args:
        db: Vector database instance (VectorDB or ContextualVectorDB)
        jsonl_path: Path to evaluation dataset
        k_values: List of k values to evaluate (default: [5, 10, 20])
        db_name: Optional name for the database being evaluated

    Returns:
        Dict mapping k values to their results
    """
    if k_values is None:
        k_values = [5, 10, 20]
    results = {}

    print(f"{'=' * 60}")
    if db_name:
        print(f"Evaluation Results: {db_name}")
    else:
        print("Evaluation Results")
    print(f"{'=' * 60}\n")

    for k in k_values:
        print(f"Evaluating Pass@{k}...")
        results[k] = evaluate_db(db, jsonl_path, k)
        print()  # Add spacing between evaluations

    # Print summary table
    print(f"{'=' * 60}")
    print(f"{'Metric':<15} {'Pass Rate':<15} {'Score':<15}")
    print(f"{'-' * 60}")
    for k in k_values:
        pass_rate = f"{results[k]['pass_at_n']:.2f}%"
        score = f"{results[k]['average_score']:.4f}"
        print(f"{'Pass@' + str(k):<15} {pass_rate:<15} {score:<15}")
    print(f"{'=' * 60}\n")

    return results
```

接著評估基本 RAG 系統，建立 baseline。我們測 k=5、10、20，看 golden chunk 出現在前幾筆檢索結果的比例，之後的改進都拿它來比。


```python
results = evaluate_and_display(
    base_db, "data/evaluation_set.jsonl", k_values=[5, 10, 20], db_name="Baseline RAG"
)
```

??? note "輸出"

    ```text
    ============================================================
    Evaluation Results: Contextual Embeddings
    ============================================================

    Evaluating Pass@5...
    ```

    ```text
    Evaluating retrieval: 100%|██████████| 248/248 [00:03<00:00, 65.26it/s]
    ```

    ```text

    Evaluating Pass@10...
    ```

    ```text
    Evaluating retrieval: 100%|██████████| 248/248 [00:03<00:00, 64.87it/s]
    ```

    ```text

    Evaluating Pass@20...
    ```

    ```text
    Evaluating retrieval: 100%|██████████| 248/248 [00:03<00:00, 64.72it/s]
    ```

    ```text

    ============================================================
    Metric          Pass Rate       Score          
    ------------------------------------------------------------
    Pass@5          80.92%          0.8092         
    Pass@10         87.15%          0.8715         
    Pass@20         90.06%          0.9006         
    ============================================================
    ```

這些結果就是 baseline。系統在 top 5 有 81% 的機率檢索到正確 chunk，top 10 提升到 87%，top 20 是 90%。

## Contextual Embeddings

基本 RAG 的問題是，chunk 單獨 embed 時常常缺乏上下文。Contextual Embeddings 的做法是請 Claude 產生一小段描述，把每個 chunk「定位」在原始文件裡，再把 chunk 連同這段 context 一起 embed，得到更豐富的向量表示。

對 codebase 資料集裡的每個 chunk，我們把 chunk 和它的完整原始檔案一起丟給 Claude。Claude 產生一段簡潔的說明，講這個 chunk 的內容以及它在整個檔案裡的位置。這段 context 會接在 chunk 前面再做 embedding。


### 成本與延遲

**這個成本什麼時候發生？** Contextualization 只在 ingestion 時做一次，不是每次 query 都做。像 HyDE（hypothetical document embeddings）這類技術會替每次搜尋增加延遲，Contextual Embeddings 則是建 vector database 時的一次性成本。Prompt caching 讓它實際可行：同一份文件的 chunk 會依序處理，所以可以吃到 prompt caching 的大幅折扣。

1. 第一個 chunk：把完整文件寫進 cache（付一點溢價）
2. 後續 chunk：從 cache 讀文件（這些 token 打一折）
3. Cache 維持 5 分鐘，足夠處理完一份文件的所有 chunk

**成本範例**：800 token 的 chunk、8k token 的文件、產生 100 token 的 context，記錄下來的那次執行（較早的 Haiku model）每百萬文件 token 總成本是 1.02 美元；換成目前 Claude Haiku 5.5 的價格，數字會不同。跑下面的程式時，你會在 log 裡看到 cache 省下的金額。

**注意：** 有些 embedding model 有固定的輸入 token 上限。如果你發現加了 context 之後效果反而變差，可能是 contextualized chunk 被截斷了，可以考慮換 context window 較大的 embedding model。

--- 

先用單一 chunk 示範 contextual embeddings 怎麼運作。我們請 Claude 產生定位用的 context，你也可以同時看到 prompt caching 的指標。


```python
DOCUMENT_CONTEXT_PROMPT = """
<document>
{doc_content}
</document>
"""

CHUNK_CONTEXT_PROMPT = """
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_content}
</chunk>

Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
Answer only with the succinct context and nothing else.
"""


def situate_context(doc: str, chunk: str) -> str:
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=doc),
                        "cache_control": {
                            "type": "ephemeral"
                        },  # we will make use of prompt caching for the full documents
                    },
                    {
                        "type": "text",
                        "text": CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk),
                    },
                ],
            }
        ],
    )
    return response


jsonl_data = load_jsonl("data/evaluation_set.jsonl")
# Example usage
doc_content = jsonl_data[0]["golden_documents"][0]["content"]
chunk_content = jsonl_data[0]["golden_chunks"][0]["content"]

response = situate_context(doc_content, chunk_content)
situated = "".join(b.text for b in response.content if b.type == "text")
print(f"Situated context: {situated}")
print("-" * 10)
# Print cache performance metrics
print(f"Input tokens: {response.usage.input_tokens}")
print(f"Output tokens: {response.usage.output_tokens}")
print(f"Cache creation input tokens: {response.usage.cache_creation_input_tokens}")
print(f"Cache read input tokens: {response.usage.cache_read_input_tokens}")
```

??? note "輸出"

    ```text
    Situated context: This chunk contains the module documentation and initial struct definition for a differential fuzzing executor. It introduces the `DiffExecutor` struct that wraps two executors (primary and secondary) to run them sequentially with the same input, comparing their behavior for differential testing. The chunk establishes the core data structure and imports needed for the differential fuzzing implementation.
    ----------
    Input tokens: 3412
    Output tokens: 76
    Cache creation input tokens: 0
    Cache read input tokens: 0
    ```

### 建立 Contextual Vector Database

看過單一 chunk 的 contextual 描述怎麼產生之後，現在擴大到整個資料集。下面的 `ContextualVectorDB` 類別延伸自基本的 `VectorDB`，在 ingestion 時自動做 contextualization。

**主要特色：**

- **平行處理**：用 ThreadPoolExecutor 同時替多個 chunk 做 contextualization（thread 數可設定）
- **自動 prompt caching**：一份文件一份文件處理，讓 cache 命中率最大化
- **Token 追蹤**：監控 cache 表現，並計算實際省下的成本
- **持久化儲存**：embedding 和 contextualized metadata 都存到硬碟

執行時請注意 token 使用統計：你會看到 70 到 80% 的輸入 token 是從 cache 讀的，可見 prompt caching 的省錢效果。在 737 個 chunk 的資料集上，原本約 15 美元的 ingestion 工作被壓到約 3 美元。

```python
import json
import os
import pickle
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import anthropic
import numpy as np
import voyageai
from tqdm import tqdm


class ContextualVectorDB:
    def __init__(self, name: str, voyage_api_key=None, anthropic_api_key=None):
        if voyage_api_key is None:
            voyage_api_key = os.getenv("VOYAGE_API_KEY")
        if anthropic_api_key is None:
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

        self.voyage_client = voyageai.Client(api_key=voyage_api_key)
        self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.name = name
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = f"./data/{name}/contextual_vector_db.pkl"

        self.token_counts = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        self.token_lock = threading.Lock()

    def situate_context(self, doc: str, chunk: str) -> tuple[str, Any]:
        DOCUMENT_CONTEXT_PROMPT = """
        <document>
        {doc_content}
        </document>
        """

        CHUNK_CONTEXT_PROMPT = """
        Here is the chunk we want to situate within the whole document
        <chunk>
        {chunk_content}
        </chunk>

        Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk.
        Answer only with the succinct context and nothing else.
        """

        response = self.anthropic_client.messages.create(
            model=MODEL_NAME,
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": DOCUMENT_CONTEXT_PROMPT.format(doc_content=doc),
                            "cache_control": {
                                "type": "ephemeral"
                            },  # we will make use of prompt caching for the full documents
                        },
                        {
                            "type": "text",
                            "text": CHUNK_CONTEXT_PROMPT.format(chunk_content=chunk),
                        },
                    ],
                },
            ],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return text, response.usage

    def load_data(self, dataset: list[dict[str, Any]], parallel_threads: int = 1):
        if self.embeddings and self.metadata:
            print("Vector database is already loaded. Skipping data loading.")
            return
        if os.path.exists(self.db_path):
            print("Loading vector database from disk.")
            self.load_db()
            return

        texts_to_embed = []
        metadata = []
        total_chunks = sum(len(doc["chunks"]) for doc in dataset)

        def process_chunk(doc, chunk):
            # for each chunk, produce the context
            contextualized_text, usage = self.situate_context(doc["content"], chunk["content"])
            with self.token_lock:
                self.token_counts["input"] += usage.input_tokens
                self.token_counts["output"] += usage.output_tokens
                self.token_counts["cache_read"] += usage.cache_read_input_tokens
                self.token_counts["cache_creation"] += usage.cache_creation_input_tokens

            return {
                # append the context to the original text chunk
                "text_to_embed": f"{contextualized_text}\n\n{chunk['content']}",
                "metadata": {
                    "doc_id": doc["doc_id"],
                    "original_uuid": doc["original_uuid"],
                    "chunk_id": chunk["chunk_id"],
                    "original_index": chunk["original_index"],
                    "original_content": chunk["content"],
                    "contextualized_content": contextualized_text,
                },
            }

        print(f"Processing {total_chunks} chunks with {parallel_threads} threads")
        with ThreadPoolExecutor(max_workers=parallel_threads) as executor:
            futures = []
            for doc in dataset:
                for chunk in doc["chunks"]:
                    futures.append(executor.submit(process_chunk, doc, chunk))

            for future in tqdm(as_completed(futures), total=total_chunks, desc="Processing chunks"):
                result = future.result()
                texts_to_embed.append(result["text_to_embed"])
                metadata.append(result["metadata"])

        self._embed_and_store(texts_to_embed, metadata)
        self.save_db()

        # logging token usage
        print(
            f"Contextual Vector database loaded and saved. Total chunks processed: {len(texts_to_embed)}"
        )
        print(f"Total input tokens without caching: {self.token_counts['input']}")
        print(f"Total output tokens: {self.token_counts['output']}")
        print(f"Total input tokens written to cache: {self.token_counts['cache_creation']}")
        print(f"Total input tokens read from cache: {self.token_counts['cache_read']}")

        total_tokens = (
            self.token_counts["input"]
            + self.token_counts["cache_read"]
            + self.token_counts["cache_creation"]
        )
        savings_percentage = (
            (self.token_counts["cache_read"] / total_tokens) * 100 if total_tokens > 0 else 0
        )
        print(
            f"Total input token savings from prompt caching: {savings_percentage:.2f}% of all input tokens used were read from cache."
        )
        print("Tokens read from cache come at a 90 percent discount!")

    # we use voyage AI here for embeddings. Read more here: https://docs.voyageai.com/docs/embeddings
    def _embed_and_store(self, texts: list[str], data: list[dict[str, Any]]):
        batch_size = 128
        result = [
            self.voyage_client.embed(texts[i : i + batch_size], model="voyage-2").embeddings
            for i in range(0, len(texts), batch_size)
        ]
        self.embeddings = [embedding for batch in result for embedding in batch]
        self.metadata = data

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        if query in self.query_cache:
            query_embedding = self.query_cache[query]
        else:
            query_embedding = self.voyage_client.embed([query], model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding

        if not self.embeddings:
            raise ValueError("No data loaded in the vector database.")

        similarities = np.dot(self.embeddings, query_embedding)
        top_indices = np.argsort(similarities)[::-1][:k]

        top_results = []
        for idx in top_indices:
            result = {
                "metadata": self.metadata[idx],
                "similarity": float(similarities[idx]),
            }
            top_results.append(result)
        return top_results

    def save_db(self):
        data = {
            "embeddings": self.embeddings,
            "metadata": self.metadata,
            "query_cache": json.dumps(self.query_cache),
        }
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "wb") as file:
            pickle.dump(data, file)

    def load_db(self):
        if not os.path.exists(self.db_path):
            raise ValueError(
                "Vector database file not found. Use load_data to create a new database."
            )
        with open(self.db_path, "rb") as file:
            data = pickle.load(file)
        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"]
        self.query_cache = json.loads(data["query_cache"])
```

```python
# Load the transformed dataset
with open("data/codebase_chunks.json") as f:
    transformed_dataset = json.load(f)

# Initialize the ContextualVectorDB
contextual_db = ContextualVectorDB("my_contextual_db")

# Load and process the data
# note: consider increasing the number of parallel threads to run this faster, or reducing the number of parallel threads if concerned about hitting your API rate limit
contextual_db.load_data(transformed_dataset, parallel_threads=5)
```

??? note "輸出"

    ```text
    Processing 737 chunks with 5 threads
    ```

    ```text
    Processing chunks: 100%|██████████| 737/737 [05:32<00:00,  2.22it/s]
    ```

    ```text
    Contextual Vector database loaded and saved. Total chunks processed: 737
    Total input tokens without caching: 1223730
    Total output tokens: 58161
    Total input tokens written to cache: 176079
    Total input tokens read from cache: 2267069
    Total input token savings from prompt caching: 61.83% of all input tokens used were read from cache.
    Tokens read from cache come at a 90 percent discount!
    ```

這些數字顯示 prompt caching 對 contextual embeddings 的威力：

- 我們處理了 9 個 codebase 檔案裡的 **737 個 chunk**
- **61.83% 的輸入 token** 是從 cache 讀的（227 萬 token，打一折）
- 在記錄的那次執行（較早的 Haiku model）中，沒有 caching 的輸入 token 成本約 **9.20 美元**
- 有 caching 的實際成本降到約 **2.85 美元**（省 69%）

Cache 命中率取決於每份文件有多少 chunk。chunk 越多的檔案越划算，因為完整文件只寫進 cache 一次，之後每個 chunk 都從 cache 讀。這也是為什麼要依文件順序處理（而不是把 chunk 隨機打亂），這對 cache 效率很關鍵。

接下來評估 contextualization 比 baseline 提升了多少檢索表現。

```python
results = evaluate_and_display(
    contextual_db,
    "data/evaluation_set.jsonl",
    k_values=[5, 10, 20],
    db_name="Contextual Embeddings",
)
```

??? note "輸出"

    ```text
    ============================================================
    Evaluation Results: Contextual Embeddings
    ============================================================

    Evaluating Pass@5...
    ```

    ```text
    Evaluating retrieval: 100%|██████████| 248/248 [00:03<00:00, 64.58it/s]
    ```

    ```text

    Evaluating Pass@10...
    ```

    ```text
    Evaluating retrieval: 100%|██████████| 248/248 [00:03<00:00, 64.37it/s]
    ```

    ```text

    Evaluating Pass@20...
    ```

    ```text
    Evaluating retrieval: 100%|██████████| 248/248 [00:03<00:00, 64.14it/s]
    ```

    ```text

    ============================================================
    Metric          Pass Rate       Score          
    ------------------------------------------------------------
    Pass@5          88.12%          0.8812         
    Pass@10         92.34%          0.9234         
    Pass@20         94.29%          0.9429         
    ============================================================
    ```

幫每個 chunk 在 embedding 前加上 context 之後，所有 k 值的檢索失敗率都降低了 **約 30 到 40%**。意思是 top 結果裡不相關的內容變少，把這些 chunk 丟給 Claude 產生最終回答時，答案也更好。

進步最明顯的是 Pass@5，也就是最講究精準度的地方。這代表加了 context 的 chunk 不只被檢索到的次數變多，相關的時候排名也更前面。

## Contextual BM25：混合搜尋

單靠 contextual embeddings，Pass@10 就從 87% 提升到 92%。再結合語意搜尋和關鍵字搜尋，也就是 **Contextual BM25** 這種混合做法，還能把檢索失敗率再往下壓。

### 為什麼要混合搜尋？

語意搜尋擅長理解意思和上下文，但可能漏掉完全吻合的關鍵字。BM25（一種機率式的關鍵字排序演算法）擅長找特定詞彙，但不懂語意。兩個合起來可以互補：

- **語意搜尋**：抓概念相似和換句話說
- **BM25**：抓精確的術語、函式名稱和特定片語
- **Reciprocal Rank Fusion**：把兩邊的結果合併成一份排名

### 什麼是 BM25？

BM25 是一個機率式的排序函數，改進了 TF-IDF，考慮了文件長度和詞頻飽和。它在 production 搜尋引擎（包含 Elasticsearch）中被廣泛使用，因為排序關鍵字相關性的效果很好。技術細節可以看[這篇部落格文章](https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables)。

我們不只搜原始 chunk 內容，而是同時搜 chunk 和先前產生的 contextual 描述。這樣 BM25 在原文或說明裡都能比對到關鍵字。

### 設定：啟動 Elasticsearch

執行下面的程式前，本機要先跑一個 Elasticsearch。最簡單的方式是用 Docker：

```bash
docker run -d --name elasticsearch -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  elasticsearch:9.2.0
```

## 疑難排解
- 確認有在跑：docker ps | grep elasticsearch
- 如果 9200 port 被佔用：docker stop elasticsearch && docker rm elasticsearch
- 出問題時看 log：docker logs elasticsearch

## 混合搜尋怎麼運作

下面的 retrieve_advanced 函式分三步：

1. 取得候選：從語意搜尋和 BM25 各取前 150 筆
2. 分數融合：用加權的 Reciprocal Rank Fusion 合併排名
    - 預設：語意搜尋 80% 權重，BM25 20%
    - 權重可以調，依你的情境實驗找最佳值
3. 回傳 top-k：融合後取分數最高的結果

這個加權機制讓你可以依資料特性，在語意理解和關鍵字精準度之間取捨。

```python
import json
import os
from typing import Any

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from tqdm import tqdm


class ElasticsearchBM25:
    def __init__(self, index_name: str = "contextual_bm25_index"):
        self.es_client = Elasticsearch("http://localhost:9200")
        self.index_name = index_name
        self.create_index()

    def create_index(self):
        index_settings = {
            "settings": {
                "analysis": {"analyzer": {"default": {"type": "english"}}},
                "similarity": {"default": {"type": "BM25"}},
                "index.queries.cache.enabled": False,
            },
            "mappings": {
                "properties": {
                    "content": {"type": "text", "analyzer": "english"},
                    "contextualized_content": {"type": "text", "analyzer": "english"},
                    "doc_id": {"type": "keyword", "index": False},
                    "chunk_id": {"type": "keyword", "index": False},
                    "original_index": {"type": "integer", "index": False},
                }
            },
        }

        # Change this line - remove 'body=' parameter
        if not self.es_client.indices.exists(index=self.index_name):
            self.es_client.indices.create(
                index=self.index_name,
                settings=index_settings["settings"],
                mappings=index_settings["mappings"],
            )
            print(f"Created index: {self.index_name}")

    def index_documents(self, documents: list[dict[str, Any]]):
        actions = [
            {
                "_index": self.index_name,
                "_source": {
                    "content": doc["original_content"],
                    "contextualized_content": doc["contextualized_content"],
                    "doc_id": doc["doc_id"],
                    "chunk_id": doc["chunk_id"],
                    "original_index": doc["original_index"],
                },
            }
            for doc in documents
        ]
        success, _ = bulk(self.es_client, actions)
        self.es_client.indices.refresh(index=self.index_name)
        return success

    def search(self, query: str, k: int = 20) -> list[dict[str, Any]]:
        self.es_client.indices.refresh(index=self.index_name)

        # Change this - remove 'body=' and pass query directly
        response = self.es_client.search(
            index=self.index_name,
            query={
                "multi_match": {
                    "query": query,
                    "fields": ["content", "contextualized_content"],
                }
            },
            size=k,
        )

        return [
            {
                "doc_id": hit["_source"]["doc_id"],
                "original_index": hit["_source"]["original_index"],
                "content": hit["_source"]["content"],
                "contextualized_content": hit["_source"]["contextualized_content"],
                "score": hit["_score"],
            }
            for hit in response["hits"]["hits"]
        ]


def create_elasticsearch_bm25_index(db: ContextualVectorDB):
    es_bm25 = ElasticsearchBM25()
    es_bm25.index_documents(db.metadata)
    return es_bm25


def retrieve_advanced(
    query: str,
    db: ContextualVectorDB,
    es_bm25: ElasticsearchBM25,
    k: int,
    semantic_weight: float = 0.8,
    bm25_weight: float = 0.2,
):
    num_chunks_to_recall = 150

    # Semantic search
    semantic_results = db.search(query, k=num_chunks_to_recall)
    ranked_chunk_ids = [
        (result["metadata"]["doc_id"], result["metadata"]["original_index"])
        for result in semantic_results
    ]

    # BM25 search using Elasticsearch
    bm25_results = es_bm25.search(query, k=num_chunks_to_recall)
    ranked_bm25_chunk_ids = [
        (result["doc_id"], result["original_index"]) for result in bm25_results
    ]

    # Combine results
    chunk_ids = list(set(ranked_chunk_ids + ranked_bm25_chunk_ids))
    chunk_id_to_score = {}

    # Initial scoring with weights
    for chunk_id in chunk_ids:
        score = 0
        if chunk_id in ranked_chunk_ids:
            index = ranked_chunk_ids.index(chunk_id)
            score += semantic_weight * (1 / (index + 1))  # Weighted 1/n scoring for semantic
        if chunk_id in ranked_bm25_chunk_ids:
            index = ranked_bm25_chunk_ids.index(chunk_id)
            score += bm25_weight * (1 / (index + 1))  # Weighted 1/n scoring for BM25
        chunk_id_to_score[chunk_id] = score

    # Sort chunk IDs by their scores in descending order
    sorted_chunk_ids = sorted(
        chunk_id_to_score.keys(), key=lambda x: (chunk_id_to_score[x], x[0], x[1]), reverse=True
    )

    # Assign new scores based on the sorted order
    for index, chunk_id in enumerate(sorted_chunk_ids):
        chunk_id_to_score[chunk_id] = 1 / (index + 1)

    # Prepare the final results
    final_results = []
    semantic_count = 0
    bm25_count = 0
    for chunk_id in sorted_chunk_ids[:k]:
        chunk_metadata = next(
            chunk
            for chunk in db.metadata
            if chunk["doc_id"] == chunk_id[0] and chunk["original_index"] == chunk_id[1]
        )
        is_from_semantic = chunk_id in ranked_chunk_ids
        is_from_bm25 = chunk_id in ranked_bm25_chunk_ids
        final_results.append(
            {
                "chunk": chunk_metadata,
                "score": chunk_id_to_score[chunk_id],
                "from_semantic": is_from_semantic,
                "from_bm25": is_from_bm25,
            }
        )

        if is_from_semantic and not is_from_bm25:
            semantic_count += 1
        elif is_from_bm25 and not is_from_semantic:
            bm25_count += 1
        else:  # it's in both
            semantic_count += 0.5
            bm25_count += 0.5

    return final_results, semantic_count, bm25_count


def evaluate_db_advanced(
    db: ContextualVectorDB,
    original_jsonl_path: str,
    k_values: list[int] = None,
    db_name: str = "Hybrid Search",
):
    """
    Evaluate hybrid search (semantic + BM25) at multiple k values with formatted results.

    Args:
        db: ContextualVectorDB instance
        original_jsonl_path: Path to evaluation dataset
        k_values: List of k values to evaluate (default: [5, 10, 20])
        db_name: Name for the evaluation display

    Returns:
        Dict mapping k values to their results and source breakdowns
    """
    if k_values is None:
        k_values = [5, 10, 20]
    original_data = load_jsonl(original_jsonl_path)
    es_bm25 = create_elasticsearch_bm25_index(db)
    results = {}

    print(f"{'=' * 70}")
    print(f"Evaluation Results: {db_name}")
    print(f"{'=' * 70}\n")

    try:
        # Warm-up queries
        warm_up_queries = original_data[:10]
        for query_item in warm_up_queries:
            _ = retrieve_advanced(query_item["query"], db, es_bm25, k_values[0])

        for k in k_values:
            print(f"Evaluating Pass@{k}...")

            total_score = 0
            total_semantic_count = 0
            total_bm25_count = 0
            total_results = 0

            for query_item in tqdm(original_data, desc=f"Pass@{k}"):
                query = query_item["query"]
                golden_chunk_uuids = query_item["golden_chunk_uuids"]

                golden_contents = []
                for doc_uuid, chunk_index in golden_chunk_uuids:
                    golden_doc = next(
                        (doc for doc in query_item["golden_documents"] if doc["uuid"] == doc_uuid),
                        None,
                    )
                    if golden_doc:
                        golden_chunk = next(
                            (
                                chunk
                                for chunk in golden_doc["chunks"]
                                if chunk["index"] == chunk_index
                            ),
                            None,
                        )
                        if golden_chunk:
                            golden_contents.append(golden_chunk["content"].strip())

                if not golden_contents:
                    continue

                retrieved_docs, semantic_count, bm25_count = retrieve_advanced(
                    query, db, es_bm25, k
                )

                chunks_found = 0
                for golden_content in golden_contents:
                    for doc in retrieved_docs[:k]:
                        retrieved_content = doc["chunk"]["original_content"].strip()
                        if retrieved_content == golden_content:
                            chunks_found += 1
                            break

                query_score = chunks_found / len(golden_contents)
                total_score += query_score

                total_semantic_count += semantic_count
                total_bm25_count += bm25_count
                total_results += len(retrieved_docs)

            total_queries = len(original_data)
            average_score = total_score / total_queries
            pass_at_n = average_score * 100

            semantic_percentage = (
                (total_semantic_count / total_results) * 100 if total_results > 0 else 0
            )
            bm25_percentage = (total_bm25_count / total_results) * 100 if total_results > 0 else 0

            results[k] = {
                "pass_at_n": pass_at_n,
                "average_score": average_score,
                "total_queries": total_queries,
                "semantic_percentage": semantic_percentage,
                "bm25_percentage": bm25_percentage,
            }

            print(f"Pass@{k}: {pass_at_n:.2f}%")
            print(f"Semantic: {semantic_percentage:.1f}% | BM25: {bm25_percentage:.1f}%\n")

        # Print summary table
        print(f"{'=' * 70}")
        print(f"{'Metric':<12} {'Pass Rate':<12} {'Score':<12} {'Semantic':<12} {'BM25':<12}")
        print(f"{'-' * 70}")
        for k in k_values:
            r = results[k]
            print(
                f"{'Pass@' + str(k):<12} {r['pass_at_n']:>10.2f}% {r['average_score']:>10.4f} "
                f"{r['semantic_percentage']:>10.1f}% {r['bm25_percentage']:>10.1f}%"
            )
        print(f"{'=' * 70}\n")

        return results

    finally:
        # Delete the Elasticsearch index
        if es_bm25.es_client.indices.exists(index=es_bm25.index_name):
            es_bm25.es_client.indices.delete(index=es_bm25.index_name)
            print(f"Deleted Elasticsearch index: {es_bm25.index_name}")
```

```python
results = evaluate_db_advanced(
    contextual_db,
    "data/evaluation_set.jsonl",
    k_values=[5, 10, 20],
    db_name="Contextual BM25 Hybrid Search",
)
```

??? note "輸出"

    ```text
    Created index: contextual_bm25_index
    ======================================================================
    Evaluation Results: Contextual BM25 Hybrid Search
    ======================================================================

    Evaluating Pass@5...
    ```

    ```text
    Pass@5: 100%|██████████| 248/248 [00:05<00:00, 41.79it/s]
    ```

    ```text
    Pass@5: 88.86%
    Semantic: 54.6% | BM25: 45.4%

    Evaluating Pass@10...
    ```

    ```text
    Pass@10: 100%|██████████| 248/248 [00:05<00:00, 42.20it/s]
    ```

    ```text
    Pass@10: 92.31%
    Semantic: 57.6% | BM25: 42.4%

    Evaluating Pass@20...
    ```

    ```text
    Pass@20: 100%|██████████| 248/248 [00:05<00:00, 42.15it/s]
    ```

    ```text
    Pass@20: 95.23%
    Semantic: 60.8% | BM25: 39.2%

    ======================================================================
    Metric       Pass Rate    Score        Semantic     BM25        
    ----------------------------------------------------------------------
    Pass@5            88.86%     0.8886       54.6%       45.4%
    Pass@10           92.31%     0.9231       57.6%       42.4%
    Pass@20           95.23%     0.9523       60.8%       39.2%
    ======================================================================

    Deleted Elasticsearch index: contextual_bm25_index
    ```

## Reranking

混合搜尋已經有很好的成績（Pass@10 93.21%），但還有一個技巧可以再榨出一點效果：**reranking**。

### 什麼是 Reranking？

Reranking 是兩階段檢索：

1. **第一階段，廣泛檢索**：撒大網，檢索比需要更多的候選（例如取 100 個 chunk）
2. **第二階段，精準挑選**：用專門的 reranking model 替這些候選打分，只留下最相關的 top-k

**為什麼有效？** 一開始的檢索方法（embedding、BM25）是為了在數百萬份文件中求快。Reranking model 比較慢但更準，因為它只需要對少量候選做更深入的分析。這是速度與準確度的取捨，實務上很好用。

### 我們的 Reranking 做法

這個範例用比較簡單的 reranking pipeline，只建立在 contextual embeddings 上（不含完整混合搜尋）。流程如下：

1. **多取一些**：取需要數量的 10 倍（需要 10 筆就取 100 筆）
2. **用 Cohere rerank**：用 Cohere 的 `rerank-english-v3.0` 替所有候選打分
3. **選 top-k**：只回傳分數最高的結果

Reranking model 可以同時看到原始 chunk 內容和我們產生的 contextual 描述，有足夠的資訊做精確的相關性判斷。

### 預期效果

Reranking 帶來的進步不大，但有意義：
- **沒有 reranking**：92.34% Pass@10（只用 contextual embeddings）
- **有 reranking**：約 95% Pass@10（再多 2 到 3%）

看起來不多，但在 production 系統裡，把失敗率從 7.66% 降到約 5% 會明顯改善使用者體驗。代價是 query 延遲：依候選集大小，reranking 每次 query 多約 100 到 200ms。

```python
import json
from collections.abc import Callable
from typing import Any

import cohere
from tqdm import tqdm


def evaluate_db_rerank(
    db, original_jsonl_path: str, k_values: list[int] = None, db_name: str = "Reranking"
):
    """
    Evaluate reranking performance at multiple k values with formatted results.

    Args:
        db: ContextualVectorDB instance
        original_jsonl_path: Path to evaluation dataset
        k_values: List of k values to evaluate (default: [5, 10, 20])
        db_name: Name for the evaluation display

    Returns:
        Dict mapping k values to their results
    """
    if k_values is None:
        k_values = [5, 10, 20]
    original_data = load_jsonl(original_jsonl_path)
    co = cohere.Client(os.getenv("COHERE_API_KEY"))
    results = {}

    print(f"{'=' * 60}")
    print(f"Evaluation Results: {db_name}")
    print(f"{'=' * 60}\n")

    for k in k_values:
        print(f"Evaluating Pass@{k} with reranking...")

        total_score = 0
        total_queries = len(original_data)

        for query_item in tqdm(original_data, desc=f"Pass@{k}"):
            query = query_item["query"]
            golden_chunk_uuids = query_item["golden_chunk_uuids"]

            # Find golden contents
            golden_contents = []
            for doc_uuid, chunk_index in golden_chunk_uuids:
                golden_doc = next(
                    (doc for doc in query_item["golden_documents"] if doc["uuid"] == doc_uuid), None
                )
                if golden_doc:
                    golden_chunk = next(
                        (chunk for chunk in golden_doc["chunks"] if chunk["index"] == chunk_index),
                        None,
                    )
                    if golden_chunk:
                        golden_contents.append(golden_chunk["content"].strip())

            if not golden_contents:
                continue

            # Retrieve and rerank
            semantic_results = db.search(query, k=k * 10)

            # Prepare documents for reranking
            documents = [
                f"{res['metadata']['original_content']}\n\nContext: {res['metadata']['contextualized_content']}"
                for res in semantic_results
            ]

            # Rerank
            rerank_response = co.rerank(
                model="rerank-english-v3.0", query=query, documents=documents, top_n=k
            )
            time.sleep(0.1)  # Rate limiting

            # Get final results
            retrieved_docs = []
            for r in rerank_response.results:
                original_result = semantic_results[r.index]
                retrieved_docs.append(
                    {"chunk": original_result["metadata"], "score": r.relevance_score}
                )

            # Check if golden chunks are in results
            chunks_found = 0
            for golden_content in golden_contents:
                for doc in retrieved_docs[:k]:
                    retrieved_content = doc["chunk"]["original_content"].strip()
                    if retrieved_content == golden_content:
                        chunks_found += 1
                        break

            query_score = chunks_found / len(golden_contents)
            total_score += query_score

        average_score = total_score / total_queries
        pass_at_n = average_score * 100

        results[k] = {
            "pass_at_n": pass_at_n,
            "average_score": average_score,
            "total_queries": total_queries,
        }

        print(f"Pass@{k}: {pass_at_n:.2f}%")
        print(f"Average Score: {average_score:.4f}\n")

    # Print summary table
    print(f"{'=' * 60}")
    print(f"{'Metric':<15} {'Pass Rate':<15} {'Score':<15}")
    print(f"{'-' * 60}")
    for k in k_values:
        pass_rate = f"{results[k]['pass_at_n']:.2f}%"
        score = f"{results[k]['average_score']:.4f}"
        print(f"{'Pass@' + str(k):<15} {pass_rate:<15} {score:<15}")
    print(f"{'=' * 60}\n")

    return results
```

```python
results = evaluate_db_rerank(
    contextual_db,
    "data/evaluation_set.jsonl",
    k_values=[5, 10, 20],
    db_name="Contextual Embeddings + Reranking",
)
```

??? note "輸出"

    ```text
    ============================================================
    Evaluation Results: Contextual Embeddings + Reranking
    ============================================================

    Evaluating Pass@5 with reranking...
    ```

    ```text
    Pass@5: 100%|██████████| 248/248 [01:40<00:00,  2.47it/s]
    ```

    ```text
    Pass@5: 92.15%
    Average Score: 0.9215

    Evaluating Pass@10 with reranking...
    ```

    ```text
    Pass@10: 100%|██████████| 248/248 [02:29<00:00,  1.66it/s]
    ```

    ```text
    Pass@10: 95.26%
    Average Score: 0.9526

    Evaluating Pass@20 with reranking...
    ```

    ```text
    Pass@20: 100%|██████████| 248/248 [03:03<00:00,  1.35it/s]
    ```

    ```text
    Pass@20: 97.45%
    Average Score: 0.9745

    ============================================================
    Metric          Pass Rate       Score          
    ------------------------------------------------------------
    Pass@5          92.15%          0.9215         
    Pass@10         95.26%          0.9526         
    Pass@20         97.45%          0.9745         
    ============================================================
    ```


Reranking 的成績最好，幾乎消除了檢索失敗。來看每個技術怎麼一層層疊上去。

從 baseline RAG 的 Pass@10 87% 出發，系統性套用進階檢索技術之後，我們爬到 95% 以上。每個方法補的弱點不同：contextual embeddings 解決「chunk 孤立」的問題，混合搜尋抓住 embedding 漏掉的關鍵字型 query，reranking 則用更精細的相關性評分來修整最終的結果。

| Approach | Pass@5 | Pass@10 | Pass@20 |
|----------|--------|---------|---------|
| **Baseline RAG** | 80.92% | 87.15% | 90.06% |
| **+ Contextual Embeddings** | 88.12% | 92.34% | 94.29% |
| **+ Hybrid Search (BM25)** | 86.43% | 93.21% | 94.99% |
| **+ Reranking** | 92.15% | 95.26% | 97.45% |

**重點：**

1. **Contextual embeddings 是單項進步最大的**（提升 5 到 7 個百分點），證明替 chunk 加上文件層級的 context 能明顯改善檢索品質。光這個技術就能讓你達到最佳表現的 90%。

2. **Reranking 的絕對表現最高**，Pass@10 達到 95.26%，也就是 95% 的 query 在前 10 筆結果裡有正確的 chunk。相較 baseline RAG，檢索失敗減少 **47%**（失敗率從 12.85% 降到 4.74%）。

3. **取捨很重要**：每個技術都增加複雜度和成本：
   - Contextual embeddings：一次性的 ingestion 成本（這個資料集搭配 prompt caching 約 3 美元）
   - 混合搜尋：需要 Elasticsearch 基礎設施和維運
   - Reranking：增加 100 到 200ms 的 query 延遲，以及每次 query 的 API 費用（約 0.002 美元）

4. **依需求選方案**：
   - **大量查詢、成本敏感**：只用 contextual embeddings（Pass@10 92%，沒有每次 query 的費用）
   - **要最高準確度、能容忍延遲**：完整 reranking pipeline（Pass@10 95%，精準度最好）
   - **均衡的 production 系統**：用混合搜尋，不用每次 query 付費也有不錯表現（Pass@10 93%）

對大部分 production RAG 系統來說，**contextual embeddings 的效能成本比最高**，只有一次性的 ingestion 成本就能有 92% 的 Pass@10。需要再多 2 到 3 個百分點的精準度、又負擔得起額外基礎設施或 query 成本時，再加混合搜尋和 reranking。

### 下一步與重點

1) 我們示範了怎麼用 Contextual Embeddings 提升檢索表現，再用 Contextual BM25 和 reranking 取得進一步的改進。

2) 這個範例用的是 codebase，但這些方法也適用於其他資料型態，例如公司內部知識庫、財務與法務內容、教育內容等等。

3) 如果你是 AWS 使用者，可以從 `contextual-rag-lambda-function` 裡的 Lambda function 開始；如果你是 GCP 使用者，可以自己架一個 Cloud Run instance，照類似的模式做。

## 重點整理

- 單獨 embed 的 chunk 缺上下文，讓 Claude 先替每個 chunk 寫一段定位說明再 embed，是單項進步最大的改法。
- Contextualization 只在 ingestion 時做一次，搭配 prompt caching（同一份文件依序處理）可以把成本壓到原本的三成左右。
- 混合搜尋讓語意和關鍵字互補，語意抓意思，BM25 抓函式名稱這類精確字串。
- Reranking 用「先多撈再精選」換更高的準確度，代價是每次 query 多 100 到 200ms 和 API 費用。
- 技術要依需求選：成本敏感用 contextual embeddings 就夠，要極致準確再往上疊。

## 練習

1. 把評估時的 k 值改成 3 和 50，跑 baseline 和 contextual 兩版，看進步幅度在哪個 k 最大。
2. 在 `retrieve_advanced` 把語意搜尋和 BM25 的權重從 80/20 改成 50/50 和 95/5，比較 Pass@10，找出這個資料集的最佳比例。
3. 把 reranking 的 over-retrieve 倍數從 10 倍改成 3 倍和 20 倍，記錄 Pass@10 和延遲，畫出取捨曲線。

