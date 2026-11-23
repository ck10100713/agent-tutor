---
translated: true
source: third_party/MongoDB/rag_using_mongodb.ipynb
---
# 如何用 Claude 和 MongoDB 建一個 RAG 系統

> 原文：[third_party/MongoDB/rag_using_mongodb.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/MongoDB/rag_using_mongodb.ipynb)

用 Claude 和 MongoDB 建一個聊天機器人 RAG 系統，以科技新聞當知識庫。

## 這篇在做什麼

這篇做一個扮演創投科技分析師的聊天機器人，背後是個單純的 RAG 系統，知識來源是一批科技新聞文章。流程是把文章 embedding 存進 MongoDB Atlas，用 vector search 找出相關文章，再交給 Claude 回答。

## 學完你會

- 設定 MongoDB Atlas 的資料庫、collection 和 vector search index，並把 embedding 資料批次寫進去
- 寫一個用 `$vectorSearch` 的 aggregation pipeline，把使用者問題轉成 embedding 後找出最相關的文件
- 把檢索結果當 context 丟給 Claude，產生有根據的回答

## 開跑前

- Claude API Key
- VoyageAI API Key（產生 query embedding）
- Hugging Face Access Token（下載資料集）
- MongoDB Atlas 帳號與 cluster（有免費方案），並記下連線 URI

這個 notebook 實作一個被 prompt 成創投科技分析師的聊天機器人。這個聊天機器人是個單純的 RAG 系統，以一批科技新聞文章當作知識來源。
這本 notebook 涵蓋：

1. 跟著完整教學設定開發環境，從安裝必要的函式庫到設定 MongoDB 資料庫。
2. 學習有效率的資料處理方式，包括建立 vector search index，以及準備資料供匯入和查詢處理。
3. 了解如何在 RAG 系統裡使用 Claude 模型，根據從資料庫檢索到的 context 產生精準的回答。


你會需要：
- Claude API Key
- VoyageAI API Key
- Hugging Face Access Token

## 步驟 1：安裝函式庫、載入並準備資料


下面簡單說明實作程式碼會用到的工具和函式庫：
- anthropic：Anthropic 官方的 Python 函式庫，讓你使用最先進的語言模型。這個函式庫提供 Claude 系列模型的存取，這些模型能理解文字和圖片。
- datasets：Hugging Face 生態系的函式庫。安裝 'datasets' 之後，就能取用許多預先處理好、可直接使用的資料集，這些資料集對訓練、fine-tuning 機器學習模型或評測效能很重要。
- pandas：資料科學函式庫，提供強大的資料結構和資料操作、處理、分析方法。
- voyageai：存取 VoyageAI embedding 模型系列的官方 Python client 函式庫。
- pymongo：MongoDB 的 Python 工具包，讓你能跟 MongoDB 資料庫互動。



```python
%pip install pymongo datasets pandas anthropic voyageai
```

下面的程式碼做這幾件事：
1. 匯入必要的函式庫：
- `os` 用來跟作業系統互動，
- `requests` 用來發 HTTP request，
- `io` 模組的 `BytesIO` 用來把 bytes 物件當成記憶體中的檔案處理，
- `pandas`（別名 pd）用來操作和分析資料，
- `google.colab` 的 `userdata` 用來讀取存在 Google Colab secrets 的環境變數。
2. 定義函式：`download_and_combine_parquet_files` 函式有兩個參數：
- `parquet_file_urls`：字串 URL 的清單，每個指向一個 Parquet 檔，裡面是 tech-news-embedding 資料集的一部分。
- `hf_token` 是 Hugging Face 授權 token 的字串。Access token 可以在 [Hugging Face 平台](https://huggingface.co/docs/hub/en/security-tokens#:~:text=To%20create%20an%20access%20token,you%27re%20ready%20to%20go!)建立或複製。
3. 下載並讀取 Parquet 檔：函式會逐一處理 parquet_file_urls 裡的每個 URL，對每個 URL：
- 用 requests.get 發 GET request，帶上 URL 和授權用的 header。
- 檢查回應狀態碼是不是 200（OK），表示 request 成功。
- 成功的話，把回應內容讀進 BytesIO 物件（當成記憶體中的檔案），再用 pandas.read_parquet 從這個物件讀成 Pandas DataFrame。
- 把 DataFrame 加進 all_dataframes 這個 list。
4. 合併 DataFrame：把所有 Parquet 檔下載並讀成 DataFrame 之後，會檢查 `all_dataframes` 不是空的。如果有 DataFrame，就用 pd.concat 合併成單一 DataFrame，並用 ignore_index=True 重新編 index。這個合併後的 DataFrame 就是 `download_and_combine_parquet_files` 函式的最終輸出。

```python
from io import BytesIO

import pandas as pd
import requests
from google.colab import userdata


def download_and_combine_parquet_files(parquet_file_urls, hf_token):
    """
    Downloads Parquet files from the provided URLs using the given Hugging Face token,
    and returns a combined DataFrame.

    Parameters:
    - parquet_file_urls: List of strings, URLs to the Parquet files.
    - hf_token: String, Hugging Face authorization token.

    Returns:
    - combined_df: A pandas DataFrame containing the combined data from all Parquet files.
    """
    headers = {"Authorization": f"Bearer {hf_token}"}
    all_dataframes = []

    for parquet_file_url in parquet_file_urls:
        response = requests.get(parquet_file_url, headers=headers, timeout=60)
        if response.status_code == 200:
            parquet_bytes = BytesIO(response.content)
            df = pd.read_parquet(parquet_bytes)
            all_dataframes.append(df)
        else:
            print(
                f"Failed to download Parquet file from {parquet_file_url}: {response.status_code}"
            )

    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        return combined_df
    else:
        print("No dataframes to concatenate.")
        return None
```

下面是這個教學需要的 Parquet 檔清單。完整的檔案清單在[這裡](https://huggingface.co/datasets/MongoDB/tech-news-embeddings/tree/refs%2Fconvert%2Fparquet/default/train)。每個 Parquet 檔大約有 45,000 筆資料。

下面的程式碼會把 tech-news-embeddings 資料集的一個子集合併成單一 DataFrame，並指派給變數 `combined_df`。


```python
# Uncomment the links below to load more data
# For the full list of data visit: https://huggingface.co/datasets/MongoDB/tech-news-embeddings/tree/refs%2Fconvert%2Fparquet/default/train
parquet_files = [
    "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0000.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0001.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0002.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0003.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0004.parquet",
    # "https://huggingface.co/api/datasets/AIatMongoDB/tech-news-embeddings/parquet/default/train/0005.parquet",
]

hf_token = userdata.get("HF_TOKEN")
combined_df = download_and_combine_parquet_files(parquet_files, hf_token)
```

資料準備的最後一步，下面的程式碼會從合併的資料集中移除 `_id` 欄位，因為後續步驟用不到。另外，每筆資料 embedding 欄位的內容會從 numpy array 轉成 Python list，避免匯入資料時發生資料型別不相容的錯誤。


```python
# Remove the _id coloum from the intital dataset
combined_df = combined_df.drop(columns=["_id"])

# Remove the initial embedding coloumn as we are going to create new embeddings with VoyageAI embedding model
combined_df = combined_df.drop(columns=["embedding"])
```

```python
combined_df.head()
```

```python
# Limiting the amount of document used to 500 for this demo due to the rate limit on VoyageAI API
# Read more on VoyageAI rate limits: https://docs.voyageai.com/docs/rate-limits
max_documents = 500

if len(combined_df) > max_documents:
    combined_df = combined_df[:max_documents]
```

```python
import voyageai

vo = voyageai.Client(api_key=userdata.get("VOYAGE_API_KEY"))


def get_embedding(text: str) -> list[float]:
    if not text.strip():
        print("Attempted to get embedding for empty text.")
        return []

    embedding = vo.embed(text, model="voyage-large-2", input_type="document")

    return embedding.embeddings[0]


combined_df["embedding"] = combined_df["description"].apply(get_embedding)

combined_df.head()
```

## 步驟 2：建立資料庫和 collection

**要建立新的 MongoDB 資料庫，先設定一個 database cluster：**
1. 註冊[免費的 MongoDB Atlas 帳號](https://www.mongodb.com/cloud/atlas/register?utm_campaign=devrel&utm_source=community&utm_medium=cta&utm_content=Partner%20Cookbook&utm_term=richmond.alake)，已有帳號的話就[登入 MongoDB Atlas](https://account.mongodb.com/account/login?utm_campaign=devrel&utm_source=community&utm_medium=cta&utm_content=Partner%20Cookbook&utm_term=richmond.alake)
2. 選左側面板的「Database」，會進到 Database Deployment 頁面，上面有現有 cluster 的部署規格。按「+Create」按鈕建立新的 database cluster。
3. 設定 database cluster 和取得 URI 需要協助的話，請參考我們設定 MongoDB cluster 和取得連線字串的指南。
注意：別忘了把 Python 主機的 IP 加進白名單，做 proof of concept 時可以用 0.0.0.0/0 允許任何 IP。
4. Cluster 成功建立並部署後，就可以在「Database Deployment」頁面使用。
5. 按 cluster 的「Connect」按鈕，可以看到用各種語言 driver 連到 cluster 的設定選項。
6. 這個教學只需要 cluster 的 URI（unique resource identifier）。複製 URI，貼到 Google Colab Secrets 環境裡，變數名稱叫 MONGO_URI，或是放進 .env 檔之類的地方。


建好 cluster 後，到 cluster 頁面，按 + Create Database，在 MongoDB Atlas cluster 裡建立資料庫和 collection。
資料庫命名為 `tech_news`，collection 命名為 `hacker_noon_tech_news`。



## 步驟 3：建立 vector search index

到這裡，你已經建好 cluster、資料庫和 collection。

這一節的步驟很關鍵，它確保輸入到聊天機器人的查詢，可以對 hacker_noon_tech_news collection 裡的紀錄做 vector search。這一步的目標是建立 vector search index，請參考官方的 [vector search index 建立指南](https://www.mongodb.com/docs/atlas/atlas-vector-search/create-index/)。

在 MongoDB Atlas 用 JSON editor 建立 vector search index 時，確認 index 的名稱是 vector_index，index 定義如下：

```
{
 "fields": [{
     "numDimensions": 1536,
     "path": "embedding",
     "similarity": "cosine",
     "type": "vector"
   }]
}

```

## 步驟 4：資料匯入

要把資料匯入前面步驟建好的 MongoDB 資料庫，必須做以下操作：
- 連到資料庫和 collection
- 清空 collection 裡既有的紀錄
- 匯入前先把資料集的 Pandas DataFrame 轉成 dictionary
- 用批次操作把 dictionary 匯入 MongoDB

這個教學需要 cluster 的 URI（unique resource identifier）。複製 URI，貼到 Google Colab Secrets 環境裡，變數名稱叫 MONGO_URI，或是放進 .env 檔之類的地方。


```python
import pymongo
from google.colab import userdata


def get_mongo_client(mongo_uri):
    """Establish connection to the MongoDB."""
    try:
        client = pymongo.MongoClient(mongo_uri)
        print("Connection to MongoDB successful")
        return client
    except pymongo.errors.ConnectionFailure as e:
        print(f"Connection failed: {e}")
        return None


mongo_uri = userdata.get("MONGO_URI")
if not mongo_uri:
    print("MONGO_URI not set in environment variables")

mongo_client = get_mongo_client(mongo_uri)

DB_NAME = "tech_news"
COLLECTION_NAME = "hacker_noon_tech_news"

db = mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]
```

??? note "輸出"

    ```text
    Connection to MongoDB successful
    ```

```python
# To ensure we are working with a fresh collection
# delete any existing records in the collection
collection.delete_many({})
```

??? note "輸出"

    ```text
    DeleteResult({'n': 228012, 'electionId': ObjectId('7fffffff000000000000000e'), 'opTime': {'ts': Timestamp(1709660559, 7341), 't': 14}, 'ok': 1.0, '$clusterTime': {'clusterTime': Timestamp(1709660559, 7341), 'signature': {'hash': b'jT\xf1\xb4\xa9\xd3\xe3suu\x03`\x15(}\x8f\x00\x9f\xe9\x8a', 'keyId': 7320226449804230661}}, 'operationTime': Timestamp(1709660559, 7341)}, acknowledged=True)
    ```

```python
# Data Ingestion
combined_df_json = combined_df.to_dict(orient="records")
collection.insert_many(combined_df_json)
```

## 步驟 5：Vector Search

這一節示範建立一個自訂的 vector search 函式，它接受使用者查詢（對應輸入聊天機器人的內容）。函式的第二個參數是 `collection`，指向要進行 vector search 的資料庫 collection。

`vector_search` 函式會透過 MongoDB aggregation pipeline 的一連串操作產生 vector search 結果。這個 pipeline 包含 `$vectorSearch` 和 `$project` 階段，根據使用者查詢的 vector embedding 做查詢，然後整理結果，省略後續處理用不到的紀錄屬性。

下面的程式碼做以下操作，以支援語意搜尋：
1. 定義 `vector_search` 函式，輸入是使用者的查詢字串和一個 MongoDB collection，回傳根據 vector 相似度搜尋比對到的文件清單。
2. 呼叫前面定義的函式 `get_embedding`，把查詢字串轉成向量，產生使用者查詢的 embedding。
3. 為 MongoDB 的 aggregate 函式建立 pipeline，包含兩個主要階段：`$vectorSearch` 和 `$project`。
4. `$vectorSearch` 階段執行實際的 vector search。index 欄位指定要用的 vector index，要跟前面步驟 vector search index 定義裡填的名稱一致。queryVector 欄位放使用者查詢的 embedding 表示。path 欄位對應文件中存放 embedding 的欄位。`numCandidates` 指定要考慮的候選文件數量，limit 則是回傳結果的數量上限。
5. `$project` 階段整理結果，排除 _id 和 `embedding` 欄位。
6. aggregate 執行定義好的 pipeline 以取得 vector search 結果。最後一個操作把資料庫回傳的 cursor 轉成 list。

```python
def vector_search(user_query, collection):
    """
    Perform a vector search in the MongoDB collection based on the user query.

    Args:
    user_query (str): The user's query string.
    collection (MongoCollection): The MongoDB collection to search.

    Returns:
    list: A list of matching documents.
    """

    # Generate embedding for the user query
    query_embedding = get_embedding(user_query)

    if query_embedding is None:
        return "Invalid query or embedding generation failed."

    # Define the vector search pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "queryVector": query_embedding,
                "path": "embedding",
                "numCandidates": 150,  # Number of candidate matches to consider
                "limit": 5,  # Return top 5 matches
            }
        },
        {
            "$project": {
                "_id": 0,  # Exclude the _id field
                "embedding": 0,  # Exclude the embedding field
                "score": {
                    "$meta": "vectorSearchScore"  # Include the search score
                },
            }
        },
    ]

    # Execute the search
    results = collection.aggregate(pipeline)
    return list(results)
```

## 步驟 6：用 Claude 處理使用者查詢

教學的最後一節，依序進行以下操作：

- 接受字串形式的使用者查詢。
- 用 VoyageAI embedding 模型產生使用者查詢的 embedding。
- 載入 Anthropic 的 Claude，具體是 `claude-opus-5-5` 模型，當作 RAG 系統的基礎模型。
- 用使用者查詢的 embedding 執行 vector search，從知識庫取得相關資訊，為基礎模型提供額外的 context。
- 把使用者查詢和收集到的額外資訊一起送給基礎模型，產生回應。


重要提醒：使用者查詢 embedding 的維度，要跟 MongoDB Atlas 上 vector search index 定義裡設定的維度一致。

這一節的下一步是匯入 anthropic 函式庫並載入 client，用來存取 anthropic 處理訊息和使用 Claude 模型的方法。請到 [Anthropic 官方網站](https://console.anthropic.com/settings/keys)的設定頁面取得 Claude API key。


```python
import anthropic

client = anthropic.Client(api_key=userdata.get("ANTHROPIC_API_KEY"))
```

下面更詳細說明下面程式碼中的操作：

1. 執行 Vector Search：函式一開始用使用者查詢和指定的 collection 當參數呼叫 `vector_search`。這會在 collection 裡做搜尋，利用 vector embedding 找出跟查詢相關的資訊。
2. 彙整搜尋結果：`search_result` 先初始化成空字串，用來累積搜尋到的資訊。函式逐一走訪 `vector_search` 回傳的結果，把每一項的細節（標題、公司名稱、URL、發布日期、文章 URL 和描述）格式化成人類可讀的字串，附加到 search_result，每筆結尾加換行字元 \n。
3. 用 Anthropic client 產生回應：接著函式向 Claude API 發出 request（透過前面建立的 client 物件，應該是 anthropic.Client 類別的實例）。它指定：
- 要用的模型（`claude-opus-5-5`），指的是 Claude Opus 這個版本。
- 產生回應的最大 token 數（max_tokens=1024）。
- system 描述引導模型扮演「創投科技分析師」，能存取科技公司文章與資訊，並用這些 context 提供建議。
- 要給模型處理的實際訊息，是使用者查詢加上彙整後的搜尋結果當 context。
4. 回傳產生的回應和搜尋結果：把回應 content 裡的 text block 接起來，回傳那段文字，同時回傳彙整好的搜尋結果。


```python
def handle_user_query(query, collection):
    get_knowledge = vector_search(query, collection)

    search_result = ""
    for result in get_knowledge:
        search_result += (
            f"Title: {result.get('title', 'N/A')}, "
            f"Company Name: {result.get('companyName', 'N/A')}, "
            f"Company URL: {result.get('companyUrl', 'N/A')}, "
            f"Date Published: {result.get('published_at', 'N/A')}, "
            f"Article URL: {result.get('url', 'N/A')}, "
            f"Description: {result.get('description', 'N/A')}, \n"
        )

    response = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        system="You are Venture Captital Tech Analyst with access to some tech company articles and information. You use the information you are given to provide advice.",
        messages=[
            {
                "role": "user",
                "content": "Answer this user query: "
                + query
                + " with the following context: "
                + search_result,
            }
        ],
    )

    response_text = "".join(block.text for block in response.content if block.type == "text")
    return response_text, search_result
```

這個教學的最後一步是初始化查詢，把它傳進 `handle_user_query` 函式，並印出回傳的回應。

```python
# Conduct query with retrieval of sources
query = "Give me the best tech stock to invest in and tell me why"
response, source_information = handle_user_query(query, collection)

print(f"Response: {response}")
print(f"\\nSource Information: \\n{source_information}")
```

??? note "輸出"

    ```text
    Response: Based on the information provided in the article titles and descriptions, Alibaba Group Holding Limited appears to be a top technology stock pick for 2023 according to renowned investor Ray Dalio. The article "Top 10 Technology Stocks to Buy in 2023 According to Ray Dalio" suggests that Alibaba is one of Dalio's favored tech investments for the year.

    As a venture capital tech analyst, I would recommend considering an investment in Alibaba for the following reasons:

    1. Endorsement from a respected investor: Ray Dalio, known for his successful investment strategies, has included Alibaba in his top 10 technology stock picks for 2023. His backing lends credibility to the investment potential of the company.

    2. Strong market position: Alibaba is a leading e-commerce company in China with a significant market share. It has a diversified business model spanning e-commerce, cloud computing, digital media, and entertainment.

    3. Growth potential: With China's large and growing middle class, Alibaba is well-positioned to benefit from increasing consumer spending and the shift towards online shopping.

    However, it's essential to consider the following points as well:

    1. Regulatory risks: Chinese tech companies, including Alibaba, have faced increased regulatory scrutiny in recent times. Changes in government policies could impact the company's growth and profitability.

    2. Competition: While Alibaba is a dominant player, it faces competition from other tech giants like Tencent and JD.com in various business segments.

    3. Geopolitical tensions: Ongoing tensions between the U.S. and China could lead to market volatility and impact investor sentiment towards Chinese stocks.

    As with any investment, it's crucial to conduct thorough research, consider your risk tolerance, and diversify your portfolio. Keep in mind that the information provided here is based on limited data points, and stock prices can be influenced by various factors beyond the scope of this context.
    Source Information: \nTitle: Top 10 Technology Stocks to Buy in 2023 According to Ray Dalio, Company Name: ALIBABA GROUP HOLDING LIMITED, Company URL: https://hackernoon.com/company/alibabagroupholdinglimited, Date Published: 2023-04-21 11:58:00, Article URL: https://uk.finance.yahoo.com/news/top-10-technology-stocks-buy-155830366.html, Description: In this article we discuss the top 10 technology stocks to buy in 2023 according to Ray Dalio. If you want to skip our detailed analysis of Dalio’s investment philosophy and portfolio construction, 
    Title: 3 Tech Stocks I Love Right Now, Company Name: 10Clouds, Company URL: https://hackernoon.com/company/10clouds, Date Published: 2023-04-02 11:30:00, Article URL: https://www.msn.com/en-xl/money/other/3-tech-stocks-i-love-right-now/ar-AA19n9Ht, Description: These are tech giants but they''re also great investments., 
    Title: 3 Millionaire-Maker Hydrogen Stocks to Buy Before the Window Closes, Company Name: Air Products & Chemicals, Company URL: https://hackernoon.com/company/airproductschemicals, Date Published: 2023-07-28 12:18:00, Article URL: https://www.msn.com/en-us/money/topstocks/3-millionaire-maker-hydrogen-stocks-to-buy-before-the-window-closes/ar-AA1etN8O, Description: These are the best hydrogen stocks to buy with multibagger returns potential.More From InvestorPlace Buy This $5 Stock BEFORE This Apple Project Goes Live Wall Street Titan: Here’s My #1 Stock for 2023 The $1 Investment You MUST Take Advantage of Right Now It doesn’t matter if you have $500 or $5 million., 
    Title: Why it may be time to sell the pop in tech stocks: BlackRock, Company Name: BlackRock, Company URL: https://hackernoon.com/company/blackrock, Date Published: 2023-02-13 19:06:00, Article URL: https://news.yahoo.com/why-it-may-be-time-to-sell-the-pop-in-tech-stocks-blackrock-190606866.html, Description: Household tech names like Apple Meta and Netflix have soared so far in 2023 but one strategist says the gains aren''t likely to last. It''s time to take profits on tech stocks — the early sector winner of 2023 — as the Federal Reserve may soon dash hopes for a pivot on interest rates, 
    Title: The harsh reality for investors eyeing tech stocks in 2023: Morning Brief, Company Name: 10Clouds, Company URL: https://hackernoon.com/company/10clouds, Date Published: 2023-01-02 11:18:00, Article URL: https://news.yahoo.com/the-harsh-reality-for-investors-eyeing-tech-stocks-in-2023-morning-brief-111854804.html, Description: Curious on how to buy battered tech stocks? Here''s a quick tip. More on that and what else to watch in business on Monday.,
    ```

## 重點整理

- RAG 的基本流程是：問題轉 embedding、vector search 找相關文件、把文件當 context 交給 LLM 回答。
- Vector search index 的維度必須跟 embedding 模型輸出的維度一致，否則查詢會失敗。
- MongoDB 的 `$vectorSearch` 是 aggregation pipeline 的一個階段，`numCandidates` 和 `limit` 控制召回的範圍。
- Claude 的角色靠 system prompt 設定（這裡是創投科技分析師），檢索到的資料則放進 user message 當 context。
- Embedding 欄位匯入前要轉成 Python list，不然會有資料型別錯誤。

## 練習

1. 把 `max_tokens` 或 system prompt 裡的角色換掉（例如改成「新創記者」），看回答風格怎麼變。
2. 調整 `$vectorSearch` 的 `limit` 從小到大（例如 1、5、20），觀察回答的品質和內容如何隨著 context 數量變化。
3. 修改 `search_result` 的組裝方式，只保留標題和描述，或是多加上相似度分數，比較回答有沒有差異。
