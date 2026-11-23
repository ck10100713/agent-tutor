---
translated: true
source: examples/vector_databases/zilliz/Filtered_search_with_Zilliz_and_OpenAI.ipynb
---

# 用 Zilliz 和 OpenAI 做帶過濾條件的搜尋

> 原文：[examples/vector_databases/zilliz/Filtered_search_with_Zilliz_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/zilliz/Filtered_search_with_Zilliz_and_OpenAI.ipynb)



## 這篇在做什麼

用 OpenAI 幫電影簡介產生 embedding，存進 Zilliz，再用語意搜尋找出相關電影。這篇的重點是在搜尋時加上 metadata 過濾條件，縮小結果範圍。資料來自 HuggingFace 的 netflix-shows 資料集，約 8 千多部。

## 學完你會

- 把電影簡介批次轉成 embedding，連同 title、type、release_year、rating 一起寫進 Zilliz
- 設定 collection、索引參數和搜尋參數
- 用「描述文字加過濾表達式」的組合查詢，只在符合條件的電影裡找相似的

## 開跑前

- 一個 Zilliz 帳號跟資料庫（照[這裡](https://zilliz.com/doc/quick_start)設定）
- OpenAI API key

### 找下一部想看的電影

這份 notebook 會用 OpenAI 產生電影簡介的 embedding，再用這些 embedding 在 Zilliz 裡找相關電影。為了縮小搜尋範圍，我們用過濾條件做 metadata 搜尋。資料集來自 HuggingFace datasets，有 8 千多筆電影資料。

先安裝這份 notebook 需要的套件：
- `openai` 用來呼叫 OpenAI 的 embedding 服務
- `pymilvus` 用來跟 Zilliz 伺服器溝通
- `datasets` 用來下載資料集
- `tqdm` 用來顯示進度條


```python
! pip install openai pymilvus datasets tqdm
```

要啟動 Zilliz 可以看[這裡](https://zilliz.com/doc/quick_start)。帳號跟資料庫都設好之後，設定下面這些值：
- URI：資料庫運行的 URI
- USER：資料庫使用者名稱
- PASSWORD：資料庫密碼
- COLLECTION_NAME：在 Zilliz 裡 collection 的名字
- DIMENSION：embedding 的維度
- OPENAI_ENGINE：要用哪個 embedding 模型
- openai.api_key：你的 OpenAI 帳號 key
- INDEX_PARAM：collection 用的索引設定
- QUERY_PARAM：搜尋參數
- BATCH_SIZE：一次要 embed 並寫入多少筆文字

```python
import openai

URI = 'your_uri'
TOKEN = 'your_token' # TOKEN == user:password or api_key
COLLECTION_NAME = 'book_search'
DIMENSION = 1536
OPENAI_ENGINE = 'text-embedding-3-small'
openai.api_key = 'sk-your_key'

INDEX_PARAM = {
    'metric_type':'L2',
    'index_type':"AUTOINDEX",
    'params':{}
}

QUERY_PARAM = {
    "metric_type": "L2",
    "params": {},
}

BATCH_SIZE = 1000
```

```python
from pymilvus import connections, utility, FieldSchema, Collection, CollectionSchema, DataType

# Connect to Zilliz Database
connections.connect(uri=URI, token=TOKEN)
```

```python
# Remove collection if it already exists
if utility.has_collection(COLLECTION_NAME):
    utility.drop_collection(COLLECTION_NAME)
```

```python
# Create collection which includes the id, title, and embedding.
fields = [
    FieldSchema(name='id', dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name='title', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='type', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='release_year', dtype=DataType.INT64),
    FieldSchema(name='rating', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='description', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='embedding', dtype=DataType.FLOAT_VECTOR, dim=DIMENSION)
]
schema = CollectionSchema(fields=fields)
collection = Collection(name=COLLECTION_NAME, schema=schema)
```

```python
# Create the index on the collection and load it.
collection.create_index(field_name="embedding", index_params=INDEX_PARAM)
collection.load()
```

## 資料集
Zilliz 準備好之後就可以抓資料了。`Hugging Face Datasets` 是一個收了很多使用者資料集的 hub，這個範例用 HuggingLearners 的 netflix-shows 資料集，裡面有 8 千多部電影和它們的 metadata。我們會把每部的簡介 embed，連同 title、type、release_year 和 rating 一起存進 Zilliz。

```python
import datasets

# Download the dataset 
dataset = datasets.load_dataset('hugginglearners/netflix-shows', split='train')
```

??? note "輸出"

    ```text
    /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages/tqdm/auto.py:22: TqdmWarning: IProgress not found. Please update jupyter and ipywidgets. See https://ipywidgets.readthedocs.io/en/stable/user_install.html
      from .autonotebook import tqdm as notebook_tqdm
    Found cached dataset csv (/Users/filiphaltmayer/.cache/huggingface/datasets/hugginglearners___csv/hugginglearners--netflix-shows-03475319fc65a05a/0.0.0/6b34fb8fcf56f7c8ba51dc895bfa2bfbe43546f190a60fcf74bb5e8afdcc2317)
    ```

## 寫入資料
資料都在本機之後，就可以 embed 並寫進 Zilliz。embedding 函式吃文字，回傳 list 格式的 embedding。

```python
# Simple function that converts the texts to embeddings
def embed(texts):
    embeddings = openai.Embedding.create(
        input=texts,
        engine=OPENAI_ENGINE
    )
    return [x['embedding'] for x in embeddings['data']]
```

下一步才是真正的寫入。我們走過所有資料，湊滿設定的 batch size 就寫入一批，迴圈結束後如果還有剩的就再寫一批。

```python
from tqdm import tqdm

data = [
    [], # title
    [], # type
    [], # release_year
    [], # rating
    [], # description
]

# Embed and insert in batches
for i in tqdm(range(0, len(dataset))):
    data[0].append(dataset[i]['title'] or '')
    data[1].append(dataset[i]['type'] or '')
    data[2].append(dataset[i]['release_year'] or -1)
    data[3].append(dataset[i]['rating'] or '')
    data[4].append(dataset[i]['description'] or '')
    if len(data[0]) % BATCH_SIZE == 0:
        data.append(embed(data[4]))
        collection.insert(data)
        data = [[],[],[],[],[]]

# Embed and insert the remainder 
if len(data[0]) != 0:
    data.append(embed(data[4]))
    collection.insert(data)
    data = [[],[],[],[],[]]
```

??? note "輸出"

    ```text
    100%|██████████| 8807/8807 [00:54<00:00, 162.59it/s]
    ```

## 查詢資料庫
資料都安全寫進 Zilliz 後就可以查詢了。查詢吃一個 tuple，包含你要找的電影描述和要用的過濾條件。過濾語法的更多說明在[這裡](https://milvus.io/docs/boolean.md)。搜尋時會先印出你的描述和過濾表達式，接著每筆結果會印出分數、title、type、release year、rating 和簡介。

```python
import textwrap

def query(query, top_k = 5):
    text, expr = query
    res = collection.search(embed(text), anns_field='embedding', expr = expr, param=QUERY_PARAM, limit = top_k, output_fields=['title', 'type', 'release_year', 'rating', 'description'])
    for i, hit in enumerate(res):
        print('Description:', text, 'Expression:', expr)
        print('Results:')
        for ii, hits in enumerate(hit):
            print('\t' + 'Rank:', ii + 1, 'Score:', hits.score, 'Title:', hits.entity.get('title'))
            print('\t\t' + 'Type:', hits.entity.get('type'), 'Release Year:', hits.entity.get('release_year'), 'Rating:', hits.entity.get('rating'))
            print(textwrap.fill(hits.entity.get('description'), 88))
            print()

my_query = ('movie about a fluffly animal', 'release_year < 2019 and rating like \"PG%\"')

query(my_query)
```

??? note "輸出"

    ```text
    Description: movie about a fluffly animal Expression: release_year < 2019 and rating like "PG%"
    Results:
    	Rank: 1 Score: 0.30085673928260803 Title: The Lamb
    		Type: Movie Release Year: 2017 Rating: PG
    A big-dreaming donkey escapes his menial existence and befriends some free-spirited
    animal pals in this imaginative retelling of the Nativity Story.

    	Rank: 2 Score: 0.3352621793746948 Title: Puss in Boots
    		Type: Movie Release Year: 2011 Rating: PG
    The fabled feline heads to the Land of Giants with friends Humpty Dumpty and Kitty
    Softpaws on a quest to nab its greatest treasure: the Golden Goose.

    	Rank: 3 Score: 0.3415083587169647 Title: Show Dogs
    		Type: Movie Release Year: 2018 Rating: PG
    A rough and tough police dog must go undercover with an FBI agent as a prim and proper
    pet at a dog show to save a baby panda from an illegal sale.

    	Rank: 4 Score: 0.3428957462310791 Title: Open Season 2
    		Type: Movie Release Year: 2008 Rating: PG
    Elliot the buck and his forest-dwelling cohorts must rescue their dachshund pal from
    some spoiled pets bent on returning him to domesticity.

    	Rank: 5 Score: 0.34376364946365356 Title: Stuart Little 2
    		Type: Movie Release Year: 2002 Rating: PG
    Zany misadventures are in store as lovable city mouse Stuart and his human brother,
    George, raise the roof in this sequel to the 1999 blockbuster.
    ```

## 重點整理

- 向量搜尋回答「語意上像不像」，metadata 過濾回答「符不符合硬條件」，兩個合用才能找到真正想要的結果。
- 過濾是寫在搜尋請求裡的表達式，用來限定候選範圍，所以描述和條件要一起設計。
- 批次 embed 加批次寫入比逐筆處理有效率，記得迴圈結束後把最後一批殘留的寫完。
- 索引參數跟搜尋參數會影響速度與召回率，要跟資料量搭配。

## 練習

1. 換一個電影描述，保持同樣的過濾條件，看結果有沒有被條件限制住。
2. 修改過濾表達式，例如換成不同的 release_year 範圍或 rating，比較結果。
3. 把 BATCH_SIZE 調大或調小，觀察寫入速度的差異，並想想為什麼最後要再補寫一批。
