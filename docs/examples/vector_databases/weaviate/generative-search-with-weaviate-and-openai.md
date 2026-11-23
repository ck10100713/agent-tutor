---
translated: true
source: examples/vector_databases/weaviate/generative-search-with-weaviate-and-openai.ipynb
---

# 用 Weaviate 的 generative OpenAI 模組做生成式搜尋

> 原文：[examples/vector_databases/weaviate/generative-search-with-weaviate-and-openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/generative-search-with-weaviate-and-openai.ipynb)



## 這篇在做什麼

資料已經在 Weaviate 裡，這篇教你用 Weaviate 的 Generative OpenAI 模組，讓搜尋結果直接交給 OpenAI 模型產生回答。寫法跟一般語意搜尋很像，只是多加一個 `with_generate()`。

## 學完你會

- 連上 Weaviate 並帶入 OpenAI API key
- 寫一個語意搜尋查詢，指定類別、欄位、關鍵概念和筆數
- 用 `single_prompt` 對每筆結果各生成一段回應，或用 `grouped_task` 把所有結果合成一段回應

## 開跑前

- 先完成 [Getting Started cookbook](getting-started-with-weaviate-and-openai.md)，並匯入範例資料
- 一個 Weaviate 實例
- OpenAI API key，設成環境變數 `OPENAI_API_KEY`

## 前置需求

這篇只講生成式搜尋，不含設定跟資料匯入。要看懂這篇，請先完成 [Getting Started cookbook](getting-started-with-weaviate-and-openai.md)，裡面會教 Weaviate 的基本操作並匯入示範資料。

確認清單：
* 完成 [Getting Started cookbook](getting-started-with-weaviate-and-openai.md)，
* 建好 `Weaviate` 實例，
* 資料已匯入你的 `Weaviate` 實例，
* 有一把 [OpenAI API key](https://beta.openai.com/account/api-keys)

===========================================================
## 設定 OpenAI API key

`OpenAI API key` 用來在匯入時把資料向量化，也用來執行查詢。

沒有 OpenAI API key 的話，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 申請。

拿到之後，請把它加進環境變數 `OPENAI_API_KEY`。

```python
# Export OpenAI API Key
!export OPENAI_API_KEY="your key"
```

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = 'your-key-goes-here'

if os.getenv("OPENAI_API_KEY") is not None:
    print ("OPENAI_API_KEY is ready")
else:
    print ("OPENAI_API_KEY environment variable not found")
```

## 連上 Weaviate 實例

這一節要做的事：

1. 檢查環境變數 `OPENAI_API_KEY`，**確定**你已經完成 [#Prepare-your-OpenAI-API-key](#Prepare-your-OpenAI-API-key) 那一步
2. 帶著 `OpenAI API Key` 連上 Weaviate
3. 測試 client 連線

### Client

這一步之後，所有跟 Weaviate 有關的操作都用 `client` 物件來做。

```python
import weaviate
from datasets import load_dataset
import os

# Connect to your Weaviate instance
client = weaviate.Client(
    url="https://your-wcs-instance-name.weaviate.network/",
    # url="http://localhost:8080/",
    auth_client_secret=weaviate.auth.AuthApiKey(api_key="<YOUR-WEAVIATE-API-KEY>"), # comment out this line if you are not using authentication for your Weaviate instance (i.e. for locally deployed instances)
    additional_headers={
        "X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")
    }
)

# Check if your instance is live and ready
# This should return `True`
client.is_ready()
```

## 生成式搜尋
Weaviate 有一個 [Generative Search OpenAI](https://weaviate.io/developers/weaviate/modules/reader-generator-modules/generative-openai) 模組，可以根據存在 Weaviate 裡的資料產生回應。

生成式搜尋的查詢寫法跟一般的 Weaviate 語意搜尋很像。

例如：
* 在 "Articles" 裡搜尋，
* 回傳 "title"、"content"、"url"
* 找跟 "football clubs" 相關的物件
* 結果限制 5 筆

```
    result = (
        client.query
        .get("Articles", ["title", "content", "url"])
        .with_near_text("concepts": "football clubs")
        .with_limit(5)
        # generative query will go here
        .do()
    )
```

接著加上 `with_generate()` 就能套用生成轉換。`with_generate` 可以接：
- `single_prompt`：對每個回傳的物件各生成一段回應，
- `grouped_task`：把所有回傳的物件合起來，生成單一一段回應。


```python
def generative_search_per_item(query, collection_name):
    prompt = "Summarize in a short tweet the following content: {content}"

    result = (
        client.query
        .get(collection_name, ["title", "content", "url"])
        .with_near_text({ "concepts": [query], "distance": 0.7 })
        .with_limit(5)
        .with_generate(single_prompt=prompt)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]
```

```python
query_result = generative_search_per_item("football clubs", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']}")
    print(article['_additional']['generate']['singleResult']) # print generated response
    print("-----------------------")
```

```python
def generative_search_group(query, collection_name):
    generateTask = "Explain what these have in common"

    result = (
        client.query
        .get(collection_name, ["title", "content", "url"])
        .with_near_text({ "concepts": [query], "distance": 0.7 })
        .with_generate(grouped_task=generateTask)
        .with_limit(5)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]
```

```python
query_result = generative_search_group("football clubs", "Article")

print (query_result[0]['_additional']['generate']['groupedResult'])
```

跟著做到這裡，你已經可以自己建向量資料庫，並用 embedding 做各種有趣的事，好好玩吧！更複雜的情境可以繼續看這個 repo 裡的其他 cookbook。

## 重點整理

- 生成式搜尋是先檢索、再讓模型根據檢索到的資料回答（RAG 的做法），Weaviate 把這兩步包在同一個查詢裡。
- `single_prompt` 是一筆結果一次生成，`grouped_task` 是全部結果一次生成，選哪個看你要逐筆處理還是要整體摘要。
- 搜尋條件（類別、欄位、筆數）會直接影響模型拿到的素材，檢索品質決定回答品質。
- OpenAI API key 同時用在向量化跟生成，兩邊都要能用。

## 練習

1. 把搜尋的概念從 "football clubs" 換成別的主題，看生成結果怎麼變。
2. 把 `limit` 從 5 改成 2，比較 `grouped_task` 的回答差異。
3. 同一個查詢分別用 `single_prompt` 和 `grouped_task` 跑一次，改寫 prompt 讓它輸出一句話摘要，比較兩種輸出的形狀。
