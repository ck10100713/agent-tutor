---
translated: true
source: examples/vector_databases/zilliz/Getting_started_with_Zilliz_and_OpenAI.ipynb
---

# Zilliz 與 OpenAI 入門

> 原文：[examples/vector_databases/zilliz/Getting_started_with_Zilliz_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/zilliz/Getting_started_with_Zilliz_and_OpenAI.ipynb)



## 這篇在做什麼

用 OpenAI 幫書籍簡介產生 embedding，存進 Zilliz，再用語意搜尋找出相關的書。資料集來自 HuggingFace，有 100 多萬筆書名和簡介配對。

## 學完你會

- 用 `pymilvus` 連上 Zilliz，建立 collection 並建索引
- 批次 embed 書籍簡介，連同書名寫進 Zilliz
- 用字串或字串清單查詢，看每筆結果的分數、書名和簡介

## 開跑前

- 一個 Zilliz 帳號跟資料庫（照[這裡](https://zilliz.com/doc/quick_start)設定）
- OpenAI API key

### 找下一本想看的書

這份 notebook 會用 OpenAI 產生書籍簡介的 embedding，再用這些 embedding 在 Zilliz 裡找相關的書。資料集來自 HuggingFace datasets，有 100 多萬筆書名和簡介配對。

先安裝這份 notebook 需要的套件：
- `openai` 用來呼叫 OpenAI 的 embedding 服務
- `pymilvus` 用來跟 Zilliz 實例溝通
- `datasets` 用來下載資料集
- `tqdm` 用來顯示進度條


```python
! pip install openai pymilvus datasets tqdm
```

??? note "輸出"

    ```text
    Looking in indexes: https://pypi.org/simple, https://pypi.ngc.nvidia.com
    Requirement already satisfied: openai in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (0.27.2)
    Requirement already satisfied: pymilvus in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (2.2.2)
    Requirement already satisfied: datasets in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (2.10.1)
    Requirement already satisfied: tqdm in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (4.64.1)
    Requirement already satisfied: requests>=2.20 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from openai) (2.28.2)
    Requirement already satisfied: aiohttp in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from openai) (3.8.4)
    Requirement already satisfied: ujson<=5.4.0,>=2.0.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (5.1.0)
    Requirement already satisfied: grpcio-tools<=1.48.0,>=1.47.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (1.47.2)
    Requirement already satisfied: grpcio<=1.48.0,>=1.47.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (1.47.2)
    Requirement already satisfied: mmh3<=3.0.0,>=2.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (3.0.0)
    Requirement already satisfied: pandas>=1.2.4 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (1.5.3)
    Requirement already satisfied: numpy>=1.17 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (1.23.5)
    Requirement already satisfied: xxhash in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (3.2.0)
    Requirement already satisfied: responses<0.19 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.18.0)
    Requirement already satisfied: dill<0.3.7,>=0.3.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.3.6)
    Requirement already satisfied: huggingface-hub<1.0.0,>=0.2.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.12.1)
    Requirement already satisfied: pyarrow>=6.0.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (10.0.1)
    Requirement already satisfied: multiprocess in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.70.14)
    Requirement already satisfied: pyyaml>=5.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (5.4.1)
    Requirement already satisfied: fsspec[http]>=2021.11.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (2023.1.0)
    Requirement already satisfied: packaging in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (23.0)
    Requirement already satisfied: frozenlist>=1.1.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (1.3.3)
    Requirement already satisfied: async-timeout<5.0,>=4.0.0a3 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (4.0.2)
    Requirement already satisfied: aiosignal>=1.1.2 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (1.3.1)
    Requirement already satisfied: attrs>=17.3.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (22.2.0)
    Requirement already satisfied: charset-normalizer<4.0,>=2.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (3.0.1)
    Requirement already satisfied: yarl<2.0,>=1.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (1.8.2)
    Requirement already satisfied: multidict<7.0,>=4.5 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (6.0.4)
    Requirement already satisfied: six>=1.5.2 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from grpcio<=1.48.0,>=1.47.0->pymilvus) (1.16.0)
    Requirement already satisfied: protobuf<4.0dev,>=3.12.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from grpcio-tools<=1.48.0,>=1.47.0->pymilvus) (3.20.1)
    Requirement already satisfied: setuptools in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from grpcio-tools<=1.48.0,>=1.47.0->pymilvus) (65.6.3)
    Requirement already satisfied: typing-extensions>=3.7.4.3 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from huggingface-hub<1.0.0,>=0.2.0->datasets) (4.5.0)
    Requirement already satisfied: filelock in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from huggingface-hub<1.0.0,>=0.2.0->datasets) (3.9.0)
    Requirement already satisfied: python-dateutil>=2.8.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pandas>=1.2.4->pymilvus) (2.8.2)
    Requirement already satisfied: pytz>=2020.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pandas>=1.2.4->pymilvus) (2022.7.1)
    Requirement already satisfied: urllib3<1.27,>=1.21.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from requests>=2.20->openai) (1.26.14)
    Requirement already satisfied: idna<4,>=2.5 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from requests>=2.20->openai) (3.4)
    Requirement already satisfied: certifi>=2017.4.17 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from requests>=2.20->openai) (2022.12.7)
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
openai.api_key = 'sk-your-key'

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

## Zilliz
這一段處理 Zilliz 本身，為這個用途準備資料庫。在 Zilliz 裡要先建 collection 並建索引。

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
Zilliz 準備好之後就可以抓資料了。`Hugging Face Datasets` 是一個收了很多使用者資料集的 hub，這個範例用 Skelebor 的書籍資料集，裡面有 100 多萬本書的書名和簡介配對。我們會把每本的簡介 embed，連同書名一起存進 Zilliz。

```python
import datasets

# Download the dataset and only use the `train` portion (file is around 800Mb)
dataset = datasets.load_dataset('Skelebor/book_titles_and_descriptions_en_clean', split='train')
```

??? note "輸出"

    ```text
    /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages/tqdm/auto.py:22: TqdmWarning: IProgress not found. Please update jupyter and ipywidgets. See https://ipywidgets.readthedocs.io/en/stable/user_install.html
      from .autonotebook import tqdm as notebook_tqdm
    Found cached dataset parquet (/Users/filiphaltmayer/.cache/huggingface/datasets/Skelebor___parquet/Skelebor--book_titles_and_descriptions_en_clean-3596935b1d8a7747/0.0.0/2a3b91fbd88a2c90d1dbbb32b460cf621d31bd5b05b934492fdef7d8d6f236ec)
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

下一步才是真正的寫入。因為資料點非常多，如果想馬上測試，可以提早中斷這個 cell 繼續往下。資料變少準確度大概會下降，但拿來測試還是夠用。

```python
from tqdm import tqdm

data = [
    [], # title
    [], # description
]

# Embed and insert in batches
for i in tqdm(range(0, len(dataset))):
    data[0].append(dataset[i]['title'])
    data[1].append(dataset[i]['description'])
    if len(data[0]) % BATCH_SIZE == 0:
        data.append(embed(data[1]))
        collection.insert(data)
        data = [[],[]]

# Embed and insert the remainder 
if len(data[0]) != 0:
    data.append(embed(data[1]))
    collection.insert(data)
    data = [[],[]]
```

??? note "輸出"

    ```text
      0%|          | 2999/1032335 [00:19<1:49:30, 156.66it/s]
    ```

    ```text
    KeyboardInterrupt:
    ```

## 查詢資料庫
資料都安全寫進 Zilliz 後就可以查詢了。查詢可以吃一個字串或字串清單，並對它們搜尋。結果會印出你提供的描述，以及每筆結果的分數、書名和書籍簡介。

```python
import textwrap

def query(queries, top_k = 5):
    if type(queries) != list:
        queries = [queries]
    res = collection.search(embed(queries), anns_field='embedding', param=QUERY_PARAM, limit = top_k, output_fields=['title', 'description'])
    for i, hit in enumerate(res):
        print('Description:', queries[i])
        print('Results:')
        for ii, hits in enumerate(hit):
            print('\t' + 'Rank:', ii + 1, 'Score:', hits.score, 'Title:', hits.entity.get('title'))
            print(textwrap.fill(hits.entity.get('description'), 88))
            print()
```

```python
query('Book about a k-9 from europe')
```

??? note "輸出"

    ```text
    Description: Book about a k-9 from europe
    Results:
    	Rank: 1 Score: 0.3047754764556885 Title: Bark M For Murder
    Who let the dogs out? Evildoers beware! Four of mystery fiction's top storytellers are
    setting the hounds on your trail -- in an incomparable quartet of crime stories with a
    canine edge. Man's (and woman's) best friends take the lead in this phenomenal
    collection of tales tense and surprising, humorous and thrilling: New York
    Timesbestselling author J.A. Jance's spellbinding saga of a scam-busting septuagenarian
    and her two golden retrievers; Anthony Award winner Virginia Lanier's pureblood thriller
    featuring bloodhounds and bloody murder; Chassie West's suspenseful stunner about a
    life-saving German shepherd and a ghastly forgotten crime; rising star Lee Charles
    Kelley's edge-of-your-seat yarn that pits an ex-cop/kennel owner and a yappy toy poodle
    against a craven killer.

    	Rank: 2 Score: 0.3283390402793884 Title: Texas K-9 Unit Christmas: Holiday Hero\Rescuing Christmas
    CHRISTMAS COMES WRAPPED IN DANGER Holiday Hero by Shirlee McCoy Emma Fairchild never
    expected to find trouble in sleepy Sagebrush, Texas. But when she's attacked and left
    for dead in her own diner, her childhood friend turned K-9 cop Lucas Harwood offers a
    chance at justice--and love. Rescuing Christmas by Terri Reed She escaped a kidnapper,
    but now a killer has set his sights on K-9 dog trainer Lily Anderson. When fellow
    officer Jarrod Evans appoints himself her bodyguard, Lily knows more than her life is at
    risk--so is her heart. Texas K-9 Unit: These lawmen solve the toughest cases with the
    help of their brave canine partners

    	Rank: 3 Score: 0.33899369835853577 Title: Dogs on Duty: Soldiers' Best Friends on the Battlefield and Beyond
    When the news of the raid on Osama Bin Laden's compound broke, the SEAL team member that
    stole the show was a highly trained canine companion. Throughout history, dogs have been
    key contributors to military units. Dorothy Hinshaw Patent follows man's best friend
    onto the battlefield, showing readers why dogs are uniquely qualified for the job at
    hand, how they are trained, how they contribute to missions, and what happens when they
    retire. With full-color photographs throughout and sidebars featuring heroic canines
    throughout history, Dogs on Duty provides a fascinating look at these exceptional
    soldiers and companions.

    	Rank: 4 Score: 0.34207457304000854 Title: Toute Allure: Falling in Love in Rural France
    After saying goodbye to life as a successful fashion editor in London, Karen Wheeler is
    now happy in her small village house in rural France. Her idyll is complete when she
    meets the love of her life - he has shaggy hair, four paws and a wet nose!

    	Rank: 5 Score: 0.343595951795578 Title: Otherwise Alone (Evan Arden, #1)
    ... (省略 10 行)
    ```

## 重點整理

- 用向量資料庫的流程是：建 collection、建索引、寫入 embedding、查詢。
- 寫入跟查詢要用同一個 embedding 模型，DIMENSION 要跟模型輸出一致。
- 大資料集要批次處理，BATCH_SIZE 控制一次 embed 和寫入的量。
- INDEX_PARAM 和 QUERY_PARAM 會影響搜尋速度跟準確度。

## 練習

1. 調整 BATCH_SIZE，觀察寫入速度的變化。
2. 換成你自己的查詢描述，看回傳的書是否符合直覺。
3. 一次傳多個查詢字串，比較各自回傳的分數分布。
