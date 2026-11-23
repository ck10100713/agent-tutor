---
translated: true
source: examples/How_to_combine_GPT4o_with_RAG_Outfit_Assistant.ipynb
---
# 結合 GPT-4o mini 和 RAG 做一個服裝搭配 app

> 原文：[examples/How_to_combine_GPT4o_with_RAG_Outfit_Assistant.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_combine_GPT4o_with_RAG_Outfit_Assistant.ipynb)

## 這篇在做什麼

這篇做一個服裝搭配 app：先用 GPT-4o mini 看衣服圖片，抽出顏色、風格和類型，再用 embedding 加 cosine similarity 的 RAG 去資料庫找搭得起來的單品。最後再讓模型回頭檢查建議是否真的合適，當作 guardrail。

## 學完你會

- 用 embedding 模型為商品資料建立向量，並平行化處理，寫出自己的 cosine similarity 檢索函式（支援 threshold 和 top_k）
- 用 `gpt-4o-mini` 分析圖片，靠輸出格式規範、清楚指令和 one-shot 範例，穩定拿到 JSON 結果
- 把圖片分析結果接到資料集過濾與 RAG 檢索，並用 yes/no 的二次檢查過濾掉不搭的建議

## 開跑前

- OpenAI API key
- 資料夾裡的 `sample_styles.csv` 和範例圖片（`data/sample_clothes/`）
- embedding 會花一點點費用：約 1K 筆資料大約 $0.001，完整 44K 筆約 $0.07。也可以改載入預先算好的 embedding 跳過這步

歡迎來到服裝搭配 app 的 Jupyter Notebook！這個專案示範 GPT-4o mini 模型分析服裝圖片、抽出顏色、風格和類型等關鍵特徵的能力。我們 app 的核心就是 OpenAI 開發的這個進階圖像分析模型，它讓我們能準確辨識輸入服裝的特性。

GPT-4o mini 是一個小型模型，結合了自然語言處理和圖像辨識，能理解文字與視覺輸入並據此回應，而且延遲低。

在 GPT-4o mini 的能力之上，我們用自訂的比對演算法和 RAG 技術，在知識庫中搜尋能搭配已辨識特徵的單品。這個演算法會考慮顏色相容性和風格一致性等因素，給使用者合適的推薦。透過這份 notebook，我們想展示這些技術在建立服裝推薦系統上的實際應用。

GPT-4o mini 加 RAG（Retrieval-Augmented Generation）的組合有幾個好處：

1. **Contextual Understanding（情境理解）**：GPT-4o mini 能分析輸入圖片並理解情境，例如圖中的物件、場景和活動。這讓它在各個領域，不論是室內設計、烹飪或教育，都能給出更準確、更相關的建議或資訊
2. **豐富的知識庫**：RAG 把 GPT-4 的生成能力和檢索元件結合，檢索元件能存取跨領域的大量資料。這代表系統可以根據廣泛的知識提供建議或洞察，從歷史事實到科學概念都有
3. **客製化**：這個做法很容易針對各種應用中的特定使用者需求或偏好做客製。不管是依使用者的藝術品味調整建議，或依學生的學習程度提供教育內容，系統都能調整成提供個人化的體驗

整體來說，GPT-4o mini 加 RAG 的做法，結合生成式和檢索式 AI 的優點，為各種時尚相關應用提供快速、強大又彈性的解法。


### 環境設定

先安裝需要的套件，接著 import 函式庫，並寫一些之後會用到的 utility function。

```python
%pip install openai --quiet
%pip install tenacity --quiet
%pip install tqdm --quiet
%pip install numpy --quiet
%pip install typing --quiet
%pip install tiktoken --quiet
%pip install concurrent --quiet
```

```python
import pandas as pd
import numpy as np
import json
import ast
import tiktoken
import concurrent
from openai import OpenAI
from tqdm import tqdm
from tenacity import retry, wait_random_exponential, stop_after_attempt
from IPython.display import Image, display, HTML
from typing import List

client = OpenAI()

GPT_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_COST_PER_1K_TOKENS = 0.00013
```

### 建立 Embedding
現在要選一個資料庫並為它產生 embedding，來建立知識庫。這裡用 data 資料夾裡的 `sample_styles.csv`，它是一個含 `~44K` 筆資料的較大資料集的樣本。這一步也可以換成使用現成的 vector database，例如照著[這些 cookbook](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases) 之一來建立你的 vector database。

```python
styles_filepath = "data/sample_clothes/sample_styles.csv"
styles_df = pd.read_csv(styles_filepath, on_bad_lines='skip')
print(styles_df.head())
print("Opened dataset successfully. Dataset has {} items of clothing.".format(len(styles_df)))
```

現在對整個資料集產生 embedding。我們可以平行化這些 embedding 的執行，讓腳本能擴展到更大的資料集。用這個邏輯，替完整的 `44K` 筆資料建立 embedding 的時間，從約 4 小時降到約 2 到 3 分鐘。

```python
## Batch Embedding Logic

# Simple function to take in a list of text objects and return them as a list of embeddings
@retry(wait=wait_random_exponential(min=1, max=40), stop=stop_after_attempt(10))
def get_embeddings(input: List):
    response = client.embeddings.create(
        input=input,
        model=EMBEDDING_MODEL
    ).data
    return [data.embedding for data in response]


# Splits an iterable into batches of size n.
def batchify(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx : min(ndx + n, l)]
     

# Function for batching and parallel processing the embeddings
def embed_corpus(
    corpus: List[str],
    batch_size=64,
    num_workers=8,
    max_context_len=8191,
):
    # Encode the corpus, truncating to max_context_len
    encoding = tiktoken.get_encoding("cl100k_base")
    encoded_corpus = [
        encoded_article[:max_context_len] for encoded_article in encoding.encode_batch(corpus)
    ]

    # Calculate corpus statistics: the number of inputs, the total number of tokens, and the estimated cost to embed
    num_tokens = sum(len(article) for article in encoded_corpus)
    cost_to_embed_tokens = num_tokens / 1000 * EMBEDDING_COST_PER_1K_TOKENS
    print(
        f"num_articles={len(encoded_corpus)}, num_tokens={num_tokens}, est_embedding_cost={cost_to_embed_tokens:.2f} USD"
    )

    # Embed the corpus
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        
        futures = [
            executor.submit(get_embeddings, text_batch)
            for text_batch in batchify(encoded_corpus, batch_size)
        ]

        with tqdm(total=len(encoded_corpus)) as pbar:
            for _ in concurrent.futures.as_completed(futures):
                pbar.update(batch_size)

        embeddings = []
        for future in futures:
            data = future.result()
            embeddings.extend(data)

        return embeddings
    

# Function to generate embeddings for a given column in a DataFrame
def generate_embeddings(df, column_name):
    # Initialize an empty list to store embeddings
    descriptions = df[column_name].astype(str).tolist()
    embeddings = embed_corpus(descriptions)

    # Add the embeddings as a new column to the DataFrame
    df['embeddings'] = embeddings
    print("Embeddings created successfully.")
```

#### 建立 embedding 的兩種選擇：
下一行會替範例服裝資料集**建立 embedding**。處理約需 0.02 秒，另外再花約 30 秒把結果寫入本機 .csv 檔。這個流程用我們的 `text_embedding_3_large` 模型，價格是 `$0.00013/1K` token。資料集約有 `1K` 筆，下面的操作大約花 `$0.001`。如果你決定使用完整的 `44K` 筆資料集，這個操作要 2 到 3 分鐘處理，大約花 `$0.07`。

**如果你不想自己建立 embedding**，我們會用一個預先算好 embedding 的資料集。你可以跳過這個 cell，並取消下一個 cell 的註解來載入預先算好的向量。這個操作約需 1 分鐘把所有資料載入記憶體。

```python
generate_embeddings(styles_df, 'productDisplayName')
print("Writing embeddings to file ...")
styles_df.to_csv('data/sample_clothes/sample_styles_with_embeddings.csv', index=False)
print("Embeddings successfully stored in sample_styles_with_embeddings.csv")
```

```python
# styles_df = pd.read_csv('data/sample_clothes/sample_styles_with_embeddings.csv', on_bad_lines='skip')

# # Convert the 'embeddings' column from string representations of lists to actual lists of floats
# styles_df['embeddings'] = styles_df['embeddings'].apply(lambda x: ast.literal_eval(x))

print(styles_df.head())
print("Opened dataset successfully. Dataset has {} items of clothing along with their embeddings.".format(len(styles_df)))
```

### 建立比對演算法

這一節要開發 cosine similarity 檢索演算法，在 dataframe 裡找相似的商品。我們會用自己寫的 cosine similarity function。`sklearn` 雖然有內建的 cosine similarity function，但它 SDK 最近的更新造成相容性問題，所以我們自己實作標準的 cosine similarity 計算。

如果你已經設好 vector database，可以跳過這一步。大多數標準資料庫都有自己的搜尋函式，能簡化後續步驟。不過我們想示範的是，比對演算法可以依特定需求客製，例如特定的 threshold 或回傳指定數量的比對結果。

`find_similar_items` 函式接受四個參數：
- `embedding`：我們想找比對結果的那個 embedding
- `embeddings`：要從中搜尋最佳比對的 embedding 清單
- `threshold`（選填）：指定比對要被視為有效所需的最低相似度分數。threshold 越高，結果越接近（越好）；越低則能回傳更多商品，但可能和原本的 `embedding` 沒那麼相近
- `top_k`（選填）：決定要回傳多少個超過 threshold 的商品，這些會是和給定 `embedding` 分數最高的比對結果

```python
def cosine_similarity_manual(vec1, vec2):
    """Calculate the cosine similarity between two vectors."""
    vec1 = np.array(vec1, dtype=float)
    vec2 = np.array(vec2, dtype=float)


    dot_product = np.dot(vec1, vec2)
    norm_vec1 = np.linalg.norm(vec1)
    norm_vec2 = np.linalg.norm(vec2)
    return dot_product / (norm_vec1 * norm_vec2)


def find_similar_items(input_embedding, embeddings, threshold=0.5, top_k=2):
    """Find the most similar items based on cosine similarity."""
    
    # Calculate cosine similarity between the input embedding and all other embeddings
    similarities = [(index, cosine_similarity_manual(input_embedding, vec)) for index, vec in enumerate(embeddings)]
    
    # Filter out any similarities below the threshold
    filtered_similarities = [(index, sim) for index, sim in similarities if sim >= threshold]
    
    # Sort the filtered similarities by similarity score
    sorted_indices = sorted(filtered_similarities, key=lambda x: x[1], reverse=True)[:top_k]

    # Return the top-k most similar items
    return sorted_indices
```

```python
def find_matching_items_with_rag(df_items, item_descs):
   """Take the input item descriptions and find the most similar items based on cosine similarity for each description."""
   
   # Select the embeddings from the DataFrame.
   embeddings = df_items['embeddings'].tolist()

   
   similar_items = []
   for desc in item_descs:
      
      # Generate the embedding for the input item
      input_embedding = get_embeddings([desc])
    
      # Find the most similar items based on cosine similarity
      similar_indices = find_similar_items(input_embedding, embeddings, threshold=0.6)
      similar_items += [df_items.iloc[i] for i in similar_indices]
    
   return similar_items
```

### 分析模組

這個模組用 `gpt-4o-mini` 分析輸入圖片，抽出詳細描述、風格和類型等重要特徵。分析透過一個簡單的 API 呼叫完成：我們提供要分析的圖片 URL，並請模型找出相關特徵。

為了讓模型回傳準確的結果，我們在 prompt 裡用了幾個特定技巧：

1. **指定輸出格式**：我們指示模型回傳一個結構預先定義好的 JSON 區塊，包含：
   - `items`（str[]）：字串清單，每個字串是一件服裝的簡短標題，包含風格、顏色和性別。這些標題很接近我們原始資料庫裡的 `productDisplayName` 屬性
   - `category`（str）：最能代表該商品的類別。模型從原始 styles dataframe 裡所有不重複的 `articleTypes` 清單中選擇
   - `gender`（str）：標示商品適用性別的標籤。模型從 `[Men, Women, Boys, Girls, Unisex]` 選項中選擇

2. **清楚簡潔的指示**：
   - 我們清楚說明商品標題該包含什麼，以及輸出格式是什麼。輸出要是 JSON 格式，但不要有模型回應通常會帶的 `json` 標記

3. **One Shot 範例**：
   - 為了進一步說明預期的輸出，我們給模型一個範例輸入描述和對應的範例輸出。這可能會增加用掉的 token 數（也就增加呼叫成本），但能引導模型，整體表現更好

透過這個結構化的做法，我們希望從 `gpt-4o-mini` 模型取得精確、有用的資訊，供後續分析和整合進我們的資料庫。

````python
def analyze_image(image_base64, subcategories):
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
            "role": "user",
            "content": [
                {
                "type": "text",
                "text": f"""Given an image of an item of clothing, analyze the item and generate a JSON output with the following fields: "items", "category", and "gender".
                           Use your understanding of fashion trends, styles, and gender preferences to provide accurate and relevant suggestions for how to complete the outfit.
                           The items field should be a list of items that would go well with the item in the picture. Each item should represent a title of an item of clothing that contains the style, color, and gender of the item.
                           The category needs to be chosen between the types in this list: {subcategories}.
                           You have to choose between the genders in this list: [Men, Women, Boys, Girls, Unisex]
                           Do not include the description of the item in the picture. Do not include the ```json ``` tag in the output.

                           Example Input: An image representing a black leather jacket.

                           Example Output: {{"items": ["Fitted White Women's T-shirt", "White Canvas Sneakers", "Women's Black Skinny Jeans"], "category": "Jackets", "gender": "Women"}}
                           """,
                },
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}",
                },
                }
            ],
            }
        ]
    )
    # Extract relevant features from the response
    features = response.choices[0].message.content
    return features
````

### 用範例圖片測試 Prompt

為了評估 prompt 的效果，我們從資料集中載入並測試幾張圖片。我們用 `"data/sample_clothes/sample_images"` 資料夾裡的圖片，確保有多樣的風格、性別和類型。選的範例如下：

- `2133.jpg`：男士襯衫
- `7143.jpg`：女士襯衫
- `4226.jpg`：休閒男士印花 T 恤

用這些多樣的圖片測試 prompt，就能評估它從不同服裝和配件中準確分析並抽出相關特徵的能力。

我們需要一個 utility function，把 .jpg 圖片編碼成 base64

```python
import base64

def encode_image_to_base64(image_path):
    with open(image_path, 'rb') as image_file:
        encoded_image = base64.b64encode(image_file.read())
        return encoded_image.decode('utf-8')
```

```python
# Set the path to the images and select a test image
image_path = "data/sample_clothes/sample_images/"
test_images = ["2133.jpg", "7143.jpg", "4226.jpg"]

# Encode the test image to base64
reference_image = image_path + test_images[0]
encoded_image = encode_image_to_base64(reference_image)
```

```python
# Select the unique subcategories from the DataFrame
unique_subcategories = styles_df['articleType'].unique()

# Analyze the image and return the results
analysis = analyze_image(encoded_image, unique_subcategories)
image_analysis = json.loads(analysis)

# Display the image and the analysis results
display(Image(filename=reference_image))
print(image_analysis)
```

接著，我們處理圖片分析的輸出，用它來過濾並顯示資料集中比對到的商品。程式碼說明如下：

1. **擷取圖片分析結果**：我們從 `image_analysis` dictionary 取出商品描述、類別和性別

2. **過濾資料集**：我們過濾 `styles_df` DataFrame，只保留符合圖片分析性別（或 unisex）的商品，並排除與被分析圖片同類別的商品

3. **尋找比對商品**：我們用 `find_matching_items_with_rag` 函式，在過濾後的資料集中找出符合圖片分析所抽出描述的商品

4. **顯示比對商品**：我們建立一個 HTML 字串來顯示比對商品的圖片。用商品 ID 組出圖片路徑，並把每張圖片附加到 HTML 字串。最後用 `display(HTML(html))` 在 notebook 裡渲染圖片

這個 cell 有效示範了怎麼用圖片分析的結果過濾資料集，並視覺化顯示符合被分析圖片特徵的商品。

```python
# Extract the relevant features from the analysis
item_descs = image_analysis['items']
item_category = image_analysis['category']
item_gender = image_analysis['gender']


# Filter data such that we only look through the items of the same gender (or unisex) and different category
filtered_items = styles_df.loc[styles_df['gender'].isin([item_gender, 'Unisex'])]
filtered_items = filtered_items[filtered_items['articleType'] != item_category]
print(str(len(filtered_items)) + " Remaining Items")

# Find the most similar items based on the input item descriptions
matching_items = find_matching_items_with_rag(filtered_items, item_descs)

# Display the matching items (this will display 2 items for each description in the image analysis)
html = ""
paths = []
for i, item in enumerate(matching_items):
    item_id = item['id']
        
    # Path to the image file
    image_path = f'data/sample_clothes/sample_images/{item_id}.jpg'
    paths.append(image_path)
    html += f'<img src="{image_path}" style="display:inline;margin:1px"/>'

# Print the matching item description as a reminder of what we are looking for
print(item_descs)
# Display the image
display(HTML(html))
```

### Guardrails

在使用 GPT-4o mini 這類大型語言模型（LLM）的情境中，「guardrails」是指為了確保模型輸出維持在期望的參數或範圍內而設置的機制或檢查。這些 guardrail 對維持模型回應的品質和相關性很重要，尤其是處理複雜或微妙的任務時。

guardrail 有用的原因有幾個：

1. **準確性**：幫助確保模型輸出對輸入準確且相關
2. **一致性**：維持模型回應的一致性，尤其是處理相似或相關的輸入時
3. **安全性**：防止模型產生有害、冒犯或不適當的內容
4. **情境相關性**：確保模型的輸出和它所用在的特定任務或領域相關

在我們的案例中，我們用 GPT-4o mini 分析時尚圖片，並建議能搭配原本穿搭的單品。要實作 guardrail，我們可以**精煉結果**：從 GPT-4o mini 拿到初步建議後，把原始圖片和建議的單品送回給模型，請 GPT-4o mini 評估每個建議的單品是不是真的適合原本的穿搭。

這讓模型能根據回饋或額外資訊，自我修正並調整自己的輸出。透過實作這些 guardrail 並啟用自我修正，我們可以在時尚分析和推薦的情境中，提升模型輸出的可靠性和實用性。

為了做到這點，我們寫了一個 prompt，請 LLM 對「建議的單品是否搭配原本穿搭」這個問題只回答簡單的「yes」或「no」。這種二元回應能簡化精煉流程，並確保從模型得到清楚、可執行的回饋。

````python
def check_match(reference_image_base64, suggested_image_base64):
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
            "role": "user",
            "content": [
                {
                "type": "text",
                "text": """ You will be given two images of two different items of clothing.
                            Your goal is to decide if the items in the images would work in an outfit together.
                            The first image is the reference item (the item that the user is trying to match with another item).
                            You need to decide if the second item would work well with the reference item.
                            Your response must be a JSON output with the following fields: "answer", "reason".
                            The "answer" field must be either "yes" or "no", depending on whether you think the items would work well together.
                            The "reason" field must be a short explanation of your reasoning for your decision. Do not include the descriptions of the 2 images.
                            Do not include the ```json ``` tag in the output.
                           """,
                },
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{reference_image_base64}",
                },
                },
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{suggested_image_base64}",
                },
                }
            ],
            }
        ],
        max_tokens=300,
    )
    # Extract relevant features from the response
    features = response.choices[0].message.content
    return features
````

最後，來判斷上面找到的單品中，哪些真的能搭配這套穿搭。

```python
# Select the unique paths for the generated images
paths = list(set(paths))

for path in paths:
    # Encode the test image to base64
    suggested_image = encode_image_to_base64(path)
    
    # Check if the items match
    match = json.loads(check_match(encoded_image, suggested_image))
    
    # Display the image and the analysis results
    if match["answer"] == 'yes':
        display(Image(filename=path))
        print("The items match!")
        print(match["reason"])
```

可以看到，最初的潛在單品清單被進一步精煉，得到一個更精選、和穿搭很搭的結果。此外，模型還解釋為什麼每個單品被認為是好搭配，讓我們看到它的決策過程。

### 結論

在這份 Jupyter Notebook 裡，我們探索了 GPT-4o mini 和其他機器學習技術在時尚領域的應用。我們示範了如何分析服裝圖片、抽出相關特徵，並用這些資訊找出能搭配原本穿搭的單品。透過實作 guardrail 和自我修正機制，我們精煉了模型的建議，確保它們準確且符合情境。

這個做法在真實世界有幾個實際用途，包括：

1. **個人化購物助理**：零售商可以用這項技術為顧客提供個人化的穿搭推薦，提升購物體驗和顧客滿意度
2. **虛擬衣櫥應用**：使用者可以上傳自己衣服的圖片來建立虛擬衣櫥，並收到能搭配現有單品的新品建議
3. **時尚設計與造型**：時尚設計師和造型師可以用這個工具嘗試不同的組合和風格，簡化創作流程

不過要注意的一點是**成本**。使用 LLM 和圖像分析模型可能產生費用，尤其是大量使用的時候。評估導入這些技術的成本效益很重要。`gpt-4o-mini` 的價格是每 1000 個 token `$0.01`，一張 256px x 256px 的圖片加起來是 `$0.00255`。

整體來說，這份 notebook 是在時尚和 AI 交會處進一步探索與開發的基礎，為更個人化、更聰明的時尚推薦系統打開大門。

## 重點整理

- RAG 的流程是先把資料變成 embedding，再用相似度檢索找出相關項目，這篇是用圖片分析的結果當查詢
- 檢索演算法可以自己寫，用 threshold 控制品質、`top_k` 控制數量，已有 vector database 的話就直接用它內建的搜尋
- 要讓模型穩定輸出 JSON，靠的是指定結構、清楚的指示和一個 one-shot 範例，代價是多一點 token
- guardrail 的做法之一是把初步結果送回模型做 yes/no 二次檢查，讓它自我修正
- 圖片分析會按 token 計費，大量使用前要先估成本

## 練習

1. 把 `find_similar_items` 的 `threshold` 和 `top_k` 調高或調低，觀察回傳的搭配商品數量與品質怎麼變。
2. 換一張不在範例裡的服裝圖片，用 base64 編碼後丟給圖片分析的 prompt，確認回傳的 `items`、`category`、`gender` 格式正確，並看看過濾和檢索後的結果。
3. 修改 guardrail 的 prompt，讓模型除了 yes/no 之外，也輸出一句不搭的原因，並只保留 yes 的單品，比較精煉前後的清單差異。
