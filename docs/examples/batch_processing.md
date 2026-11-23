---
translated: true
source: examples/batch_processing.ipynb
---

# 用 Batch API 做批次處理

> 原文：[examples/batch_processing.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/batch_processing.ipynb)



## 這篇在做什麼
示範怎麼用 Batch API 建立非同步的批次工作，價格比較低、rate limit 也比較高。內容有兩個實例：用 `gpt-4o-mini` 幫電影分類，再用視覺能力幫家具圖片寫 caption。

## 學完你會
- 把一堆請求寫成 `jsonl` 批次檔、上傳並建立 batch job
- 輪詢 batch 狀態，拿回結果並用 `custom_id` 對回原本的輸入
- 把 Chat Completions 的做法搬到 Batch API，包含 JSON mode 跟圖片輸入

## 開跑前
需要 OpenAI API key。範例資料（IMDB 電影、Amazon 家具）會在程式裡下載。

新的 Batch API 讓你**用比較低的價格、比較高的 rate limit 建立非同步批次工作**。

批次會在 24 小時內完成，視全球使用量也可能更快。

適合用 Batch API 的情境：

- 幫市集或部落格的內容打標籤、寫 caption、做內容補強
- 幫客服工單分類並建議回覆
- 對大量客戶回饋做情緒分析
- 幫一批文件或文章產生摘要或翻譯

還有很多其他用途。

這份 cookbook 用幾個實例帶你走過 Batch API 的用法。

先用 `gpt-4o-mini` 幫電影分類，再示範怎麼用這個模型的視覺能力幫圖片寫 caption。

Batch API 支援多個模型，而且你可以在 Batch API 呼叫裡使用跟 Chat Completions endpoint 一樣的參數。

## 環境設定

```python
# Make sure you have the latest version of the SDK available to use the Batch API
%pip install openai --upgrade
```

```python
import json
from openai import OpenAI
import pandas as pd
from IPython.display import Image, display
```

```python
# Initializing OpenAI client - see https://platform.openai.com/docs/quickstart?context=python
client = OpenAI()
```

## 第一個範例：電影分類

這個範例用 `gpt-4o-mini` 從電影簡介抽出電影類別，同時產生一句話摘要。

我們會用 [JSON mode](https://platform.openai.com/docs/guides/text-generation/json-mode) 讓類別以字串陣列輸出，一句話摘要也用結構化格式輸出。

每部電影我們想拿到的結果長這樣：

```
{
    categories: ['category1', 'category2', 'category3'],
    summary: '1-sentence summary'
}
```

### 載入資料

這個範例用 IMDB top 1000 電影資料集。

```python
dataset_path = "data/imdb_top_1000.csv"

df = pd.read_csv(dataset_path)
df.head()
```

??? note "輸出"

    ```text
                                             Poster_Link  \
    0  https://m.media-amazon.com/images/M/MV5BMDFkYT...   
    1  https://m.media-amazon.com/images/M/MV5BM2MyNj...   
    2  https://m.media-amazon.com/images/M/MV5BMTMxNT...   
    3  https://m.media-amazon.com/images/M/MV5BMWMwMG...   
    4  https://m.media-amazon.com/images/M/MV5BMWU4N2...   

                   Series_Title Released_Year Certificate  Runtime  \
    0  The Shawshank Redemption          1994           A  142 min   
    1             The Godfather          1972           A  175 min   
    2           The Dark Knight          2008          UA  152 min   
    3    The Godfather: Part II          1974           A  202 min   
    4              12 Angry Men          1957           U   96 min   

                      Genre  IMDB_Rating  \
    0                 Drama          9.3   
    1          Crime, Drama          9.2   
    2  Action, Crime, Drama          9.0   
    3          Crime, Drama          9.0   
    4          Crime, Drama          9.0   

                                                Overview  Meta_score  \
    0  Two imprisoned men bond over a number of years...        80.0   
    1  An organized crime dynasty's aging patriarch t...       100.0   
    2  When the menace known as the Joker wreaks havo...        84.0   
    3  The early life and career of Vito Corleone in ...        90.0   
    4  A jury holdout attempts to prevent a miscarria...        96.0   

                   Director           Star1           Star2          Star3  \
    0        Frank Darabont     Tim Robbins  Morgan Freeman     Bob Gunton   
    1  Francis Ford Coppola   Marlon Brando       Al Pacino     James Caan   
    2     Christopher Nolan  Christian Bale    Heath Ledger  Aaron Eckhart   
    3  Francis Ford Coppola       Al Pacino  Robert De Niro  Robert Duvall   
    4          Sidney Lumet     Henry Fonda     Lee J. Cobb  Martin Balsam   

                Star4  No_of_Votes        Gross  
    0  William Sadler      2343110   28,341,469  
    1    Diane Keaton      1620367  134,966,411  
    2   Michael Caine      2303232  534,858,444  
    3    Diane Keaton      1129952   57,300,000  
    ... (省略 1 行)
    ```

### 處理步驟

這裡先用 Chat Completions endpoint 試跑請求。

結果滿意之後，再建立批次檔。

```python
categorize_system_prompt = '''
Your goal is to extract movie categories from movie descriptions, as well as a 1-sentence summary for these movies.
You will be provided with a movie description, and you will output a json object containing the following information:

{
    categories: string[] // Array of categories based on the movie description,
    summary: string // 1-sentence summary of the movie based on the movie description
}

Categories refer to the genre or type of the movie, like "action", "romance", "comedy", etc. Keep category names simple and use only lower case letters.
Movies can have several categories, but try to keep it under 3-4. Only mention the categories that are the most obvious based on the description.
'''

def get_categories(description):
    response = client.chat.completions.create(
    model="gpt-4o-mini",
    temperature=0.1,
    # This is to enable JSON mode, making sure responses are valid json objects
    response_format={ 
        "type": "json_object"
    },
    messages=[
        {
            "role": "system",
            "content": categorize_system_prompt
        },
        {
            "role": "user",
            "content": description
        }
    ],
    )

    return response.choices[0].message.content
```

```python
# Testing on a few examples
for _, row in df[:5].iterrows():
    description = row['Overview']
    title = row['Series_Title']
    result = get_categories(description)
    print(f"TITLE: {title}\nOVERVIEW: {description}\n\nRESULT: {result}")
    print("\n\n----------------------------\n\n")
```

??? note "輸出"

    ```text
    TITLE: The Shawshank Redemption
    OVERVIEW: Two imprisoned men bond over a number of years, finding solace and eventual redemption through acts of common decency.

    RESULT: {
        "categories": ["drama"],
        "summary": "Two imprisoned men develop a deep bond over the years, ultimately finding redemption through their shared acts of kindness."
    }


    ----------------------------


    TITLE: The Godfather
    OVERVIEW: An organized crime dynasty's aging patriarch transfers control of his clandestine empire to his reluctant son.

    RESULT: {
        "categories": ["crime", "drama"],
        "summary": "An aging crime lord hands over his empire to his hesitant son."
    }


    ----------------------------


    TITLE: The Dark Knight
    OVERVIEW: When the menace known as the Joker wreaks havoc and chaos on the people of Gotham, Batman must accept one of the greatest psychological and physical tests of his ability to fight injustice.

    RESULT: {
        "categories": ["action", "thriller", "superhero"],
        "summary": "Batman faces a formidable challenge as the Joker unleashes chaos on Gotham City."
    }


    ----------------------------


    TITLE: The Godfather: Part II
    OVERVIEW: The early life and career of Vito Corleone in 1920s New York City is portrayed, while his son, Michael, expands and tightens his grip on the family crime syndicate.

    RESULT: {
    ... (省略 18 行)
    ```

### 建立批次檔

批次檔是 `jsonl` 格式，每個請求（一個 json 物件）佔一行。
每個請求的格式如下：

```
{
    "custom_id": <REQUEST_ID>,
    "method": "POST",
    "url": "/v1/chat/completions",
    "body": {
        "model": <MODEL>,
        "messages": <MESSAGES>,
        // other parameters
    }
}
```

注意：request ID 在同一個 batch 裡要是唯一的。因為回傳結果的順序跟輸入不同，要靠它把結果對回原本的輸入。

```python
# Creating an array of json tasks

tasks = []

for index, row in df.iterrows():
    
    description = row['Overview']
    
    task = {
        "custom_id": f"task-{index}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            # This is what you would have in your Chat Completions API call
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "response_format": { 
                "type": "json_object"
            },
            "messages": [
                {
                    "role": "system",
                    "content": categorize_system_prompt
                },
                {
                    "role": "user",
                    "content": description
                }
            ],
        }
    }
    
    tasks.append(task)
```

```python
# Creating the file

file_name = "data/batch_tasks_movies.jsonl"

with open(file_name, 'w') as file:
    for obj in tasks:
        file.write(json.dumps(obj) + '\n')
```

### 上傳檔案

```python
batch_file = client.files.create(
  file=open(file_name, "rb"),
  purpose="batch"
)
```

```python
print(batch_file)
```

??? note "輸出"

    ```text
    FileObject(id='file-lx16f1KyIxQ2UHVvkG3HLfNR', bytes=1127310, created_at=1721144107, filename='batch_tasks_movies.jsonl', object='file', purpose='batch', status='processed', status_details=None)
    ```

### 建立 batch job

```python
batch_job = client.batches.create(
  input_file_id=batch_file.id,
  endpoint="/v1/chat/completions",
  completion_window="24h"
)
```

### 檢查 batch 狀態

注意：最久可能要 24 小時，通常會更快完成。

可以一直檢查，直到狀態變成 `completed`。

```python
batch_job = client.batches.retrieve(batch_job.id)
print(batch_job)
```

### 取回結果

```python
result_file_id = batch_job.output_file_id
result = client.files.content(result_file_id).content
```

```python
result_file_name = "data/batch_job_results_movies.jsonl"

with open(result_file_name, 'wb') as file:
    file.write(result)
```

```python
# Loading data from saved file
results = []
with open(result_file_name, 'r') as file:
    for line in file:
        # Parsing the JSON string into a dict and appending to the list of results
        json_object = json.loads(line.strip())
        results.append(json_object)
```

### 讀取結果
提醒：結果的順序跟輸入檔不一樣。
一定要用 custom_id 把結果對回原本的輸入請求。

```python
# Reading only the first results
for res in results[:5]:
    task_id = res['custom_id']
    # Getting index from task id
    index = task_id.split('-')[-1]
    result = res['response']['body']['choices'][0]['message']['content']
    movie = df.iloc[int(index)]
    description = movie['Overview']
    title = movie['Series_Title']
    print(f"TITLE: {title}\nOVERVIEW: {description}\n\nRESULT: {result}")
    print("\n\n----------------------------\n\n")
```

??? note "輸出"

    ```text
    TITLE: American Psycho
    OVERVIEW: A wealthy New York City investment banking executive, Patrick Bateman, hides his alternate psychopathic ego from his co-workers and friends as he delves deeper into his violent, hedonistic fantasies.

    RESULT: {
        "categories": ["thriller", "psychological", "drama"],
        "summary": "A wealthy investment banker in New York City conceals his psychopathic alter ego while indulging in violent and hedonistic fantasies."
    }


    ----------------------------


    TITLE: Lethal Weapon
    OVERVIEW: Two newly paired cops who are complete opposites must put aside their differences in order to catch a gang of drug smugglers.

    RESULT: {
        "categories": ["action", "comedy", "crime"],
        "summary": "An action-packed comedy about two mismatched cops teaming up to take down a drug smuggling gang."
    }


    ----------------------------


    TITLE: A Star Is Born
    OVERVIEW: A musician helps a young singer find fame as age and alcoholism send his own career into a downward spiral.

    RESULT: {
        "categories": ["drama", "music"],
        "summary": "A musician's career spirals downward as he helps a young singer find fame amidst struggles with age and alcoholism."
    }


    ----------------------------


    TITLE: From Here to Eternity
    OVERVIEW: In Hawaii in 1941, a private is cruelly punished for not boxing on his unit's team, while his captain's wife and second-in-command are falling in love.

    RESULT: {
    ... (省略 18 行)
    ```

## 第二個範例：幫圖片寫 caption

這個範例用 `gpt-4-turbo` 幫家具圖片寫 caption。

我們用模型的視覺能力分析圖片並產生 caption。

### 載入資料

這個範例用 Amazon 家具資料集。

```python
dataset_path = "data/amazon_furniture_dataset.csv"
df = pd.read_csv(dataset_path)
df.head()
```

??? note "輸出"

    ```text
             asin                                   url  \
    0  B0CJHKVG6P  https://www.amazon.com/dp/B0CJHKVG6P   
    1  B0B66QHB23  https://www.amazon.com/dp/B0B66QHB23   
    2  B0BXRTWLYK  https://www.amazon.com/dp/B0BXRTWLYK   
    3  B0C1MRB2M8  https://www.amazon.com/dp/B0C1MRB2M8   
    4  B0CG1N9QRC  https://www.amazon.com/dp/B0CG1N9QRC   

                                                   title            brand   price  \
    0  GOYMFK 1pc Free Standing Shoe Rack, Multi-laye...           GOYMFK  $24.99   
    1  subrtex Leather ding Room, Dining Chairs Set o...          subrtex     NaN   
    2  Plant Repotting Mat MUYETOL Waterproof Transpl...          MUYETOL   $5.98   
    3  Pickleball Doormat, Welcome Doormat Absorbent ...          VEWETOL  $13.99   
    4  JOIN IRON Foldable TV Trays for Eating Set of ...  JOIN IRON Store  $89.99   

                              availability  \
    0  Only 13 left in stock - order soon.   
    1                                  NaN   
    2                             In Stock   
    3  Only 10 left in stock - order soon.   
    4    Usually ships within 5 to 6 weeks   

                                              categories  \
    0  ['Home & Kitchen', 'Storage & Organization', '...   
    1  ['Home & Kitchen', 'Furniture', 'Dining Room F...   
    2  ['Patio, Lawn & Garden', 'Outdoor Décor', 'Doo...   
    3  ['Patio, Lawn & Garden', 'Outdoor Décor', 'Doo...   
    4  ['Home & Kitchen', 'Furniture', 'Game & Recrea...   

                                           primary_image  \
    0  https://m.media-amazon.com/images/I/416WaLx10j...   
    1  https://m.media-amazon.com/images/I/31SejUEWY7...   
    2  https://m.media-amazon.com/images/I/41RgefVq70...   
    3  https://m.media-amazon.com/images/I/61vz1Igler...   
    4  https://m.media-amazon.com/images/I/41p4d4VJnN...   

                                                  images  upc  ...          color  \
    0  ['https://m.media-amazon.com/images/I/416WaLx1...  NaN  ...          White   
    1  ['https://m.media-amazon.com/images/I/31SejUEW...  NaN  ...          Black   
    2  ['https://m.media-amazon.com/images/I/41RgefVq...  NaN  ...          Green   
    3  ['https://m.media-amazon.com/images/I/61vz1Igl...  NaN  ...          A5589   
    ... (省略 45 行)
    ```

### 處理步驟

同樣先用 Chat Completions endpoint 準備請求，之後再建立批次檔。

```python
caption_system_prompt = '''
Your goal is to generate short, descriptive captions for images of items.
You will be provided with an item image and the name of that item and you will output a caption that captures the most important information about the item.
If there are multiple items depicted, refer to the name provided to understand which item you should describe.
Your generated caption should be short (1 sentence), and include only the most important information about the item.
The most important information could be: the type of item, the style (if mentioned), the material or color if especially relevant and/or any distinctive features.
Keep it short and to the point.
'''

def get_caption(img_url, title):
    response = client.chat.completions.create(
    model="gpt-4o-mini",
    temperature=0.2,
    max_tokens=300,
    messages=[
        {
            "role": "system",
            "content": caption_system_prompt
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": title
                },
                # The content type should be "image_url" to use gpt-4-turbo's vision capabilities
                {
                    "type": "image_url",
                    "image_url": {
                        "url": img_url
                    }
                },
            ],
        }
    ]
    )

    return response.choices[0].message.content
```

```python
# Testing on a few images
for _, row in df[:5].iterrows():
    img_url = row['primary_image']
    caption = get_caption(img_url, row['title'])
    img = Image(url=img_url)
    display(img)
    print(f"CAPTION: {caption}\n\n")
```

??? note "輸出"

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: A stylish white free-standing shoe rack featuring multiple layers and eight double hooks, perfect for organizing shoes and accessories in living rooms, bathrooms, or hallways.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Set of 2 black leather dining chairs featuring a sleek design with vertical stitching and sturdy wooden legs.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: The MUYETOL Plant Repotting Mat is a waterproof, portable, and foldable gardening work mat measuring 26.8" x 26.8", designed for easy soil changing and indoor transplanting.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Absorbent non-slip doormat featuring the phrase "It's a good day to play PICKLEBALL" with paddle graphics, measuring 16x24 inches.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Set of 4 foldable TV trays in grey, featuring a compact design with a stand for easy storage, perfect for small spaces.
    ```

### 建立 batch job

跟第一個範例一樣，先建一個 json 任務陣列來產生 `jsonl` 檔，再用它建立 batch job。

```python
# Creating an array of json tasks

tasks = []

for index, row in df.iterrows():
    
    title = row['title']
    img_url = row['primary_image']
    
    task = {
        "custom_id": f"task-{index}",
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            # This is what you would have in your Chat Completions API call
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "max_tokens": 300,
            "messages": [
                {
                    "role": "system",
                    "content": caption_system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": title
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": img_url
                            }
                        },
                    ],
                }
            ]            
        }
    }
    
    tasks.append(task)
```

```python
# Creating the file

file_name = "data/batch_tasks_furniture.jsonl"

with open(file_name, 'w') as file:
    for obj in tasks:
        file.write(json.dumps(obj) + '\n')
```

```python
# Uploading the file 

batch_file = client.files.create(
  file=open(file_name, "rb"),
  purpose="batch"
)
```

```python
# Creating the job

batch_job = client.batches.create(
  input_file_id=batch_file.id,
  endpoint="/v1/chat/completions",
  completion_window="24h"
)
```

```python
batch_job = client.batches.retrieve(batch_job.id)
print(batch_job)
```

### 取得結果

跟第一個範例一樣，job 完成後就能取回結果。

提醒：結果的順序跟輸入檔不一樣。
一定要用 custom_id 把結果對回原本的輸入請求。

```python
# Retrieving result file

result_file_id = batch_job.output_file_id
result = client.files.content(result_file_id).content
```

```python
result_file_name = "data/batch_job_results_furniture.jsonl"

with open(result_file_name, 'wb') as file:
    file.write(result)
```

```python
# Loading data from saved file

results = []
with open(result_file_name, 'r') as file:
    for line in file:
        # Parsing the JSON string into a dict and appending to the list of results
        json_object = json.loads(line.strip())
        results.append(json_object)
```

```python
# Reading only the first results
for res in results[:5]:
    task_id = res['custom_id']
    # Getting index from task id
    index = task_id.split('-')[-1]
    result = res['response']['body']['choices'][0]['message']['content']
    item = df.iloc[int(index)]
    img_url = item['primary_image']
    img = Image(url=img_url)
    display(img)
    print(f"CAPTION: {result}\n\n")
```

??? note "輸出"

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Brushed brass pedestal towel rack with a sleek, modern design, featuring multiple bars for hanging towels, measuring 25.75 x 14.44 x 32 inches.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Black round end table featuring a tempered glass top and a metal frame, with a lower shelf for additional storage.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Black collapsible and height-adjustable telescoping stool, portable and designed for makeup artists and hairstylists, shown in various stages of folding for easy transport.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: Ergonomic pink gaming chair featuring breathable fabric, adjustable height, lumbar support, a footrest, and a swivel recliner function.
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    CAPTION: A set of two Glitzhome adjustable bar stools featuring a mid-century modern design with swivel seats, PU leather upholstery, and wooden backrests.
    ```

## 收尾

這份 cookbook 看了兩個 Batch API 的範例。要記得 Batch API 的運作方式跟 Chat Completions endpoint 一樣，支援同樣的參數，也支援大部分近期的模型（gpt-4o、gpt-4o-mini、gpt-4-turbo、gpt-3.5-turbo 等）。

用這個 API 可以大幅降低成本，建議把所有能非同步處理的工作都改成 batch job。

## 重點整理
- Batch API 用非同步處理換來較低價格和較高 rate limit，24 小時內完成。
- 批次檔是 `jsonl`，每行一個請求，請求格式跟 Chat Completions 一樣。
- 每個請求要有唯一的 `custom_id`，因為回傳順序不保證跟輸入一致。
- 先用 Chat Completions 小量試跑確認 prompt 沒問題，再轉成批次檔，可以省掉重跑的成本。
- 圖片輸入、JSON mode 這些功能在 Batch 裡都能用。

## 練習
1. 把電影分類的 prompt 改成多抽一個欄位（例如目標觀眾），先用 Chat Completions 試跑確認輸出。
2. 把批次檔裡的模型換成別的支援 Batch 的模型，比較同一批資料的結果跟成本。
3. 寫一段程式輪詢 batch 狀態，完成後用 `custom_id` 把結果合併回原本的 DataFrame。
