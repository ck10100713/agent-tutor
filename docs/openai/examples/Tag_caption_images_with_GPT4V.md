---
translated: true
source: examples/Tag_caption_images_with_GPT4V.ipynb
---

# 用 GPT4o mini 幫圖片加標籤和 caption

> 原文：[examples/Tag_caption_images_with_GPT4V.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Tag_caption_images_with_GPT4V.ipynb)



## 這篇在做什麼
用 GPT-4o mini 的視覺能力，替 Amazon 家具商品圖產生關鍵字標籤和簡短 caption，再用 embedding 做商品搜尋，輸入可以是文字或圖片。

## 學完你會
- 用「圖片加商品標題」的 zero-shot prompt 抽出關鍵字，並用 embedding 去重
- 先讓模型描述圖片，再用 few-shot 把長描述改寫成短 caption
- 把關鍵字和 caption 做成 embedding，用文字或圖片查詢相似商品

## 開跑前
- OpenAI API key
- 處理前 50 筆資料大約要 20 分鐘，embedding 約 3 分鐘；也可以直接載入處理好的資料集


這份 notebook 探索怎麼用 GPT-4* 系列模型（例如 `gpt-4o`、`gpt-4o-mini`、`gpt-4-turbo`）的視覺能力替圖片加標籤和 caption。 

我們可以利用這些模型的多模態能力，輸入圖片並附上圖片代表什麼的額外 context，請模型輸出標籤或圖片描述。描述之後可以再用語言模型（這份 notebook 用 `gpt-4o-mini`）精修成 caption。 

從圖片生成文字內容在很多情境都有用，尤其是搜尋相關的。  
這份 notebook 會示範搜尋的用法：用產生的關鍵字和商品 caption 來搜尋商品，輸入可以是文字或圖片。

範例用 Amazon 家具商品資料集，替它們加上相關關鍵字，並產生簡短、描述性的 caption。

## Setup

```python
# Install dependencies if needed
%pip install openai
%pip install scikit-learn
```

```python
from IPython.display import Image, display
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from openai import OpenAI

# Initializing OpenAI client - see https://platform.openai.com/docs/quickstart?context=python
client = OpenAI()
```

```python
# Loading dataset
dataset_path =  "data/amazon_furniture_dataset.csv"
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

## 圖片標籤

這一節用 GPT-4o mini 替商品產生相關標籤。

我們用簡單的 zero-shot 方式抽關鍵字，並用 embedding 對關鍵字去重，避免出現太相近的多個關鍵字。

我們會同時提供圖片和商品標題，避免模型抽出圖中其他物品的關鍵字。圖片裡常有多個物品，但我們只想標記其中一個。

### 抽取關鍵字

```python
system_prompt = '''
    You are an agent specialized in tagging images of furniture items, decorative items, or furnishings with relevant keywords that could be used to search for these items on a marketplace.
    
    You will be provided with an image and the title of the item that is depicted in the image, and your goal is to extract keywords for only the item specified. 
    
    Keywords should be concise and in lower case. 
    
    Keywords can describe things like:
    - Item type e.g. 'sofa bed', 'chair', 'desk', 'plant'
    - Item material e.g. 'wood', 'metal', 'fabric'
    - Item style e.g. 'scandinavian', 'vintage', 'industrial'
    - Item color e.g. 'red', 'blue', 'white'
    
    Only deduce material, style or color keywords when it is obvious that they make the item depicted in the image stand out.

    Return keywords in the format of an array of strings, like this:
    ['desk', 'industrial', 'metal']
    
'''

def analyze_image(img_url, title):
    response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": img_url,
                    }
                },
            ],
        },
        {
            "role": "user",
            "content": title
        }
    ],
        max_tokens=300,
        top_p=0.1
    )

    return response.choices[0].message.content
```

#### 用幾個例子測試

```python
examples = df.iloc[:5]
```

```python
for index, ex in examples.iterrows():
    url = ex['primary_image']
    img = Image(url=url)
    display(img)
    result = analyze_image(url, ex['title'])
    print(result)
    print("\n\n")
```

??? note "輸出"

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    ['shoe rack', 'metal', 'white', 'multi-layer', 'hooks']
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    ['dining chair', 'leather', 'black']
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    ['repotting mat', 'waterproof', 'portable', 'foldable', 'green']
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    ['doormat', 'absorbent', 'non-slip', 'coconut fiber', 'welcome', 'pickleball', 'outdoor']
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    ['tv tray', 'foldable', 'metal', 'grey']
    ```

### 查詢既有關鍵字

用 embedding 避免重複（同義詞），或對上預先定義好的關鍵字

```python
# Feel free to change the embedding model here
def get_embedding(value, model="text-embedding-3-large"): 
    embeddings = client.embeddings.create(
      model=model,
      input=value,
      encoding_format="float"
    )
    return embeddings.data[0].embedding
```

#### 用範例關鍵字測試

```python
# Existing keywords
keywords_list = ['industrial', 'metal', 'wood', 'vintage', 'bed']
```

```python
df_keywords = pd.DataFrame(keywords_list, columns=['keyword'])
df_keywords['embedding'] = df_keywords['keyword'].apply(lambda x: get_embedding(x))
df_keywords
```

??? note "輸出"

    ```text
          keyword                                          embedding
    0  industrial  [-0.026137426, 0.021297162, -0.007273361, -0.0...
    1       metal  [-0.020492474, 0.0044436487, -0.0110632675, -0...
    2        wood  [0.013840097, 0.029538965, 0.00064718135, -0.0...
    3     vintage  [-0.052348174, 0.008181616, -0.015513194, 0.00...
    4         bed  [-0.011677503, 0.023275835, 0.0026937425, -0.0...
    ```

```python
def compare_keyword(keyword):
    embedded_value = get_embedding(keyword)
    df_keywords['similarity'] = df_keywords['embedding'].apply(lambda x: cosine_similarity(np.array(x).reshape(1,-1), np.array(embedded_value).reshape(1, -1)))
    most_similar = df_keywords.sort_values('similarity', ascending=False).iloc[0]
    return most_similar

def replace_keyword(keyword, threshold = 0.6):
    most_similar = compare_keyword(keyword)
    if most_similar['similarity'] > threshold:
        print(f"Replacing '{keyword}' with existing keyword: '{most_similar['keyword']}'")
        return most_similar['keyword']
    return keyword
```

```python
# Example keywords to compare to our list of existing keywords
example_keywords = ['bed frame', 'wooden', 'vintage', 'old school', 'desk', 'table', 'old', 'metal', 'metallic', 'woody']
final_keywords = []

for k in example_keywords:
    final_keywords.append(replace_keyword(k))
    
final_keywords = set(final_keywords)
print(f"Final keywords: {final_keywords}")
```

??? note "輸出"

    ```text
    Replacing 'bed frame' with existing keyword: 'bed'
    Replacing 'wooden' with existing keyword: 'wood'
    Replacing 'vintage' with existing keyword: 'vintage'
    Replacing 'metal' with existing keyword: 'metal'
    Replacing 'metallic' with existing keyword: 'metal'
    Replacing 'woody' with existing keyword: 'wood'
    Final keywords: {'vintage', 'desk', 'wood', 'table', 'old', 'bed', 'metal', 'old school'}
    ```

## 產生 caption

這一節用 GPT-4o mini 產生圖片描述，再用 few-shot 範例的方式，搭配 GPT-4-turbo 從描述產生 caption。

如果 few-shot 範例不夠用，可以考慮 fine-tune 模型，讓產生的 caption 符合你想要的風格和語氣。 

```python
# Cleaning up dataset columns
selected_columns = ['title', 'primary_image', 'style', 'material', 'color', 'url']
df = df[selected_columns].copy()
df.head()
```

??? note "輸出"

    ```text
                                                   title  \
    0  GOYMFK 1pc Free Standing Shoe Rack, Multi-laye...   
    1  subrtex Leather ding Room, Dining Chairs Set o...   
    2  Plant Repotting Mat MUYETOL Waterproof Transpl...   
    3  Pickleball Doormat, Welcome Doormat Absorbent ...   
    4  JOIN IRON Foldable TV Trays for Eating Set of ...   

                                           primary_image              style  \
    0  https://m.media-amazon.com/images/I/416WaLx10j...             Modern   
    1  https://m.media-amazon.com/images/I/31SejUEWY7...  Black Rubber Wood   
    2  https://m.media-amazon.com/images/I/41RgefVq70...             Modern   
    3  https://m.media-amazon.com/images/I/61vz1Igler...             Modern   
    4  https://m.media-amazon.com/images/I/41p4d4VJnN...    X Classic Style   

           material          color                                   url  
    0         Metal          White  https://www.amazon.com/dp/B0CJHKVG6P  
    1        Sponge          Black  https://www.amazon.com/dp/B0B66QHB23  
    2  Polyethylene          Green  https://www.amazon.com/dp/B0BXRTWLYK  
    3        Rubber          A5589  https://www.amazon.com/dp/B0C1MRB2M8  
    4          Iron  Grey Set of 4  https://www.amazon.com/dp/B0CG1N9QRC
    ```

### 用 GPT-4o mini 描述圖片

```python
describe_system_prompt = '''
    You are a system generating descriptions for furniture items, decorative items, or furnishings on an e-commerce website.
    Provided with an image and a title, you will describe the main item that you see in the image, giving details but staying concise.
    You can describe unambiguously what the item is and its material, color, and style if clearly identifiable.
    If there are multiple items depicted, refer to the title to understand which item you should describe.
    '''

def describe_image(img_url, title):
    response = client.chat.completions.create(
    model="gpt-4o-mini",
    temperature=0.2,
    messages=[
        {
            "role": "system",
            "content": describe_system_prompt
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": img_url,
                    }
                },
            ],
        },
        {
            "role": "user",
            "content": title
        }
    ],
    max_tokens=300,
    )

    return response.choices[0].message.content
```

#### 用幾個例子測試

```python
for index, row in examples.iterrows():
    print(f"{row['title'][:50]}{'...' if len(row['title']) > 50 else ''} - {row['url']} :\n")
    img_description = describe_image(row['primary_image'], row['title'])
    print(f"{img_description}\n--------------------------\n")
```

??? note "輸出"

    ```text
    GOYMFK 1pc Free Standing Shoe Rack, Multi-layer Me... - https://www.amazon.com/dp/B0CJHKVG6P :

    The item is a free-standing shoe rack designed for versatile use in living rooms, bathrooms, or hallways. It features a multi-layer metal structure with a sleek white finish. The rack includes eight double hooks at the top for hanging accessories like hats, bags, or scarves. Below, there are multiple shelves that provide ample space for organizing shoes, making it both functional and stylish for entryway storage.
    --------------------------

    subrtex Leather ding Room, Dining Chairs Set of 2,... - https://www.amazon.com/dp/B0B66QHB23 :

    The Subrtex Leather Dining Chairs come in a set of two, featuring a sleek black design. Each chair is upholstered in durable faux leather, offering a modern and stylish look. The high backrest is accentuated with subtle vertical stitching, while the sturdy wooden legs provide stability and support. These chairs are ideal for enhancing the aesthetic of any dining room.
    --------------------------

    Plant Repotting Mat MUYETOL Waterproof Transplanti... - https://www.amazon.com/dp/B0BXRTWLYK :

    The Plant Repotting Mat is a portable and foldable gardening accessory, measuring 26.8" x 26.8". It features a vibrant green color with black edges, designed to be waterproof for easy cleanup during soil changes. The mat provides a spacious area for repotting plants and comes with tools for transplanting. Ideal for indoor gardening, it helps keep your workspace tidy while you care for your succulents and other plants.
    --------------------------

    Pickleball Doormat, Welcome Doormat Absorbent Non-... - https://www.amazon.com/dp/B0C1MRB2M8 :

    The Pickleball Doormat features a natural coir material with a rectangular shape, measuring 16x24 inches. It showcases a playful design with the phrase "It's a good day to play PICKLEBALL" in bold black lettering, accompanied by graphic illustrations of pickleball paddles. The mat is designed to be absorbent and non-slip, making it suitable for entryways or bathrooms. Its light brown color adds a warm touch to any space.
    --------------------------

    JOIN IRON Foldable TV Trays for Eating Set of 4 wi... - https://www.amazon.com/dp/B0CG1N9QRC :

    The JOIN IRON Foldable TV Trays set includes four sleek, grey snack tables designed for convenience and space-saving. Each tray features a sturdy, flat surface supported by a durable metal frame, allowing for easy folding and storage. The minimalist design makes them ideal for small spaces, perfect for enjoying meals or snacks while watching TV. The set also comes with a stand for organized storage when not in use.
    --------------------------
    ```

### 把描述變成 caption
用 few-shot 範例把長描述轉成簡短的圖片 caption

```python
caption_system_prompt = '''
Your goal is to generate short, descriptive captions for images of furniture items, decorative items, or furnishings based on an image description.
You will be provided with a description of an item image and you will output a caption that captures the most important information about the item.
Your generated caption should be short (1 sentence), and include the most relevant information about the item.
The most important information could be: the type of the item, the style (if mentioned), the material if especially relevant and any distinctive features.
'''

few_shot_examples = [
    {
        "description": "This is a multi-layer metal shoe rack featuring a free-standing design. It has a clean, white finish that gives it a modern and versatile look, suitable for various home decors. The rack includes several horizontal shelves dedicated to organizing shoes, providing ample space for multiple pairs. Above the shoe storage area, there are 8 double hooks arranged in two rows, offering additional functionality for hanging items such as hats, scarves, or bags. The overall structure is sleek and space-saving, making it an ideal choice for placement in living rooms, bathrooms, hallways, or entryways where efficient use of space is essential.",
        "caption": "White metal free-standing shoe rack"
    },
    {
        "description": "The image shows a set of two dining chairs in black. These chairs are upholstered in a leather-like material, giving them a sleek and sophisticated appearance. The design features straight lines with a slight curve at the top of the high backrest, which adds a touch of elegance. The chairs have a simple, vertical stitching detail on the backrest, providing a subtle decorative element. The legs are also black, creating a uniform look that would complement a contemporary dining room setting. The chairs appear to be designed for comfort and style, suitable for both casual and formal dining environments.",
        "caption": "Set of 2 modern black leather dining chairs"
    },
    {
        "description": "This is a square plant repotting mat designed for indoor gardening tasks such as transplanting and changing soil for plants. It measures 26.8 inches by 26.8 inches and is made from a waterproof material, which appears to be a durable, easy-to-clean fabric in a vibrant green color. The edges of the mat are raised with integrated corner loops, likely to keep soil and water contained during gardening activities. The mat is foldable, enhancing its portability, and can be used as a protective surface for various gardening projects, including working with succulents. It's a practical accessory for garden enthusiasts and makes for a thoughtful gift for those who enjoy indoor plant care.",
        "caption": "Waterproof square plant repotting mat"
    }
]

formatted_examples = [[{
    "role": "user",
    "content": ex['description']
},
{
    "role": "assistant", 
    "content": ex['caption']
}]
    for ex in few_shot_examples
]

formatted_examples = [i for ex in formatted_examples for i in ex]
```

```python
def caption_image(description, model="gpt-4o-mini"):
    messages = formatted_examples
    messages.insert(0, 
        {
            "role": "system",
            "content": caption_system_prompt
        })
    messages.append(
        {
            "role": "user",
            "content": description
        })
    response = client.chat.completions.create(
    model=model,
    temperature=0.2,
    messages=messages
    )

    return response.choices[0].message.content
```

#### 用幾個例子測試

```python
examples = df.iloc[5:8]
```

```python
for index, row in examples.iterrows():
    print(f"{row['title'][:50]}{'...' if len(row['title']) > 50 else ''} - {row['url']} :\n")
    img_description = describe_image(row['primary_image'], row['title'])
    print(f"{img_description}\n--------------------------\n")
    img_caption = caption_image(img_description)
    print(f"{img_caption}\n--------------------------\n")
```

??? note "輸出"

    ```text
    LOVMOR 30'' Bathroom Vanity Sink Base Cabine, Stor... - https://www.amazon.com/dp/B0C9WYYFLB :

    The LOVMOR 30'' Bathroom Vanity Sink Base Cabinet features a classic design with a rich brown finish. It includes three drawers on the left side for ample storage, complemented by a spacious cabinet door on the right. The cabinet is constructed with detailed paneling, adding a touch of elegance, making it suitable for bathrooms, kitchens, laundry rooms, and more. Its versatile style allows it to blend seamlessly into various decor themes.
    --------------------------

    Classic 30'' brown bathroom vanity sink base cabinet with storage drawers.
    --------------------------

    Folews Bathroom Organizer Over The Toilet Storage,... - https://www.amazon.com/dp/B09NZY3R1T :

    The Folews Bathroom Organizer is a freestanding, 4-tier storage rack designed to fit over a toilet. It features a sleek black metal frame with adjustable shelves, allowing for customizable storage options. The shelves are made of wire, providing a modern look while ensuring durability. This organizer includes baskets for additional storage and is ideal for maximizing bathroom space by holding toiletries, towels, and other essentials. Its design is both functional and stylish, making it a great addition to any bathroom.
    --------------------------

    Freestanding 4-tier black metal bathroom organizer with adjustable wire shelves and baskets.
    --------------------------

    GOYMFK 1pc Free Standing Shoe Rack, Multi-layer Me... - https://www.amazon.com/dp/B0CJHKVG6P :

    The GOYMFK Free Standing Shoe Rack is a versatile storage solution designed for various spaces like living rooms, bathrooms, or hallways. It features a multi-layer metal construction with a sleek white finish. The rack includes eight double hooks at the top for hanging items such as hats, bags, or scarves. Below, there are multiple shelves for organizing shoes, accommodating various styles and sizes. Its modern design combines functionality with a clean aesthetic, making it a practical addition to any home.
    --------------------------

    Versatile white metal free-standing shoe rack with hooks and multiple shelves.
    --------------------------
    ```

## 圖片搜尋

這一節用產生的關鍵字和 caption 去搜尋符合輸入的商品，輸入可以是文字或圖片。

我們用 embedding 模型替關鍵字和 caption 產生 embedding，再跟輸入文字，或輸入圖片產生的 caption 比較。

```python
# Df we'll use to compare keywords
df_keywords = pd.DataFrame(columns=['keyword', 'embedding'])
df['keywords'] = ''
df['img_description'] = ''
df['caption'] = ''
```

```python
# Function to replace a keyword with an existing keyword if it's too similar
def get_keyword(keyword, df_keywords, threshold = 0.6):
    embedded_value = get_embedding(keyword)
    df_keywords['similarity'] = df_keywords['embedding'].apply(lambda x: cosine_similarity(np.array(x).reshape(1,-1), np.array(embedded_value).reshape(1, -1)))
    sorted_keywords = df_keywords.copy().sort_values('similarity', ascending=False)
    if len(sorted_keywords) > 0 :
        most_similar = sorted_keywords.iloc[0]
        if most_similar['similarity'] > threshold:
            print(f"Replacing '{keyword}' with existing keyword: '{most_similar['keyword']}'")
            return most_similar['keyword']
    new_keyword = {
        'keyword': keyword,
        'embedding': embedded_value
    }
    df_keywords = pd.concat([df_keywords, pd.DataFrame([new_keyword])], ignore_index=True)
    return keyword
```

### 準備資料集

```python
import ast

def tag_and_caption(row):
    keywords = analyze_image(row['primary_image'], row['title'])
    try:
        keywords = ast.literal_eval(keywords)
        mapped_keywords = [get_keyword(k, df_keywords) for k in keywords]
    except Exception as e:
        print(f"Error parsing keywords: {keywords}")
        mapped_keywords = []
    img_description = describe_image(row['primary_image'], row['title'])
    caption = caption_image(img_description)
    return {
        'keywords': mapped_keywords,
        'img_description': img_description,
        'caption': caption
    }
```

```python
df.shape
```

??? note "輸出"

    ```text
    (312, 9)
    ```

資料集共 312 行，全部處理要很久。
為了試試這個做法，我們只跑前 50 行，大約要 20 分鐘。
也可以跳過這步，直接載入處理好的資料集（見下方）。

```python
# Running on first 50 lines
for index, row in df[:50].iterrows():
    print(f"{index} - {row['title'][:50]}{'...' if len(row['title']) > 50 else ''}")
    updates = tag_and_caption(row)
    df.loc[index, updates.keys()] = updates.values()
```

??? note "輸出"

    ```text
    0 - GOYMFK 1pc Free Standing Shoe Rack, Multi-layer Me...
    1 - subrtex Leather ding Room, Dining Chairs Set of 2,...
    2 - Plant Repotting Mat MUYETOL Waterproof Transplanti...
    3 - Pickleball Doormat, Welcome Doormat Absorbent Non-...
    4 - JOIN IRON Foldable TV Trays for Eating Set of 4 wi...
    5 - LOVMOR 30'' Bathroom Vanity Sink Base Cabine, Stor...
    6 - Folews Bathroom Organizer Over The Toilet Storage,...
    7 - GOYMFK 1pc Free Standing Shoe Rack, Multi-layer Me...
    8 - subrtex Leather ding Room, Dining Chairs Set of 2,...
    9 - Plant Repotting Mat MUYETOL Waterproof Transplanti...
    10 - Pickleball Doormat, Welcome Doormat Absorbent Non-...
    11 - JOIN IRON Foldable TV Trays for Eating Set of 4 wi...
    12 - LOVMOR 30'' Bathroom Vanity Sink Base Cabine, Stor...
    13 - Folews Bathroom Organizer Over The Toilet Storage,...
    14 - Lerliuo Nightstand, Side Table, Industrial Bedside...
    15 - Boss Office Products Any Task Mid-Back Task Chair ...
    16 - Kingston Brass BA1752BB Heritage 18-Inch Towel-Bar...
    17 - Chief Mfg.Swing-Arm Wall Mount Hardware Mount Blac...
    18 - DOMYDEVM Black End Table, Nightstand with Charging...
    19 - LASCO 35-5019 Hallmack Style 24-Inch Towel Bar Acc...
    20 - Table-Mate II PRO TV Tray Table - Folding Table wi...
    21 - EGFheal White Dress Up Storage
    22 - Caroline's Treasures PPD3013JMAT Enchanted Garden ...
    23 - Leick Home 70007-WTGD Mixed Metal and Wood Stepped...
    24 - Caroline's Treasures CK3435MAT Bichon Frise Doorma...
    25 - Wildkin Kids Canvas Sling Bookshelf with Storage f...
    26 - Gbuzozie 38L Round Laundry Hamper Cute Mermaid Gir...
    27 - Tiita Comfy Saucer Chair, Soft Faux Fur Oversized ...
    28 - Summer Desk Decor,Welcome Summer Wood Block Sign D...
    29 - Homebeez 39.1" Length Bedroom Storage Bench, End B...
    30 - Flash Furniture Webb Commercial Grade 24" Round Bl...
    31 - Mellow 2 Inch Ventilated Memory Foam Mattress Topp...
    32 - CangLong Mid Century Modern Side Chair with Wood L...
    33 - HomePop Metal Accent Table Triangle Base Round Mir...
    34 - MAEPA RV Shoe Storage for Bedside - 8 Extra Large ...
    35 - NearMoon Hand Towel Holder/Towel Ring - Bathroom T...
    36 - FLYJOE Narrow Side Table with PU Leather Magazine ...
    37 - HomePop Home Decor | K2380-YDQY-2 | Luxury Large F...
    38 - Moroccan Leather Pouf Ottoman for Living Room - Ro...
    39 - AnyDesign Christmas Welcome Doormat Decorative Xma...
    ... (省略 10 行)
    ```

```python
df.head()
```

??? note "輸出"

    ```text
                                                   title  \
    0  GOYMFK 1pc Free Standing Shoe Rack, Multi-laye...   
    1  subrtex Leather ding Room, Dining Chairs Set o...   
    2  Plant Repotting Mat MUYETOL Waterproof Transpl...   
    3  Pickleball Doormat, Welcome Doormat Absorbent ...   
    4  JOIN IRON Foldable TV Trays for Eating Set of ...   

                                           primary_image              style  \
    0  https://m.media-amazon.com/images/I/416WaLx10j...             Modern   
    1  https://m.media-amazon.com/images/I/31SejUEWY7...  Black Rubber Wood   
    2  https://m.media-amazon.com/images/I/41RgefVq70...             Modern   
    3  https://m.media-amazon.com/images/I/61vz1Igler...             Modern   
    4  https://m.media-amazon.com/images/I/41p4d4VJnN...    X Classic Style   

           material          color                                   url  \
    0         Metal          White  https://www.amazon.com/dp/B0CJHKVG6P   
    1        Sponge          Black  https://www.amazon.com/dp/B0B66QHB23   
    2  Polyethylene          Green  https://www.amazon.com/dp/B0BXRTWLYK   
    3        Rubber          A5589  https://www.amazon.com/dp/B0C1MRB2M8   
    4          Iron  Grey Set of 4  https://www.amazon.com/dp/B0CG1N9QRC   

                                                keywords  \
    0      [shoe rack, metal, white, multi-layer, hooks]   
    1                     [dining chair, leather, black]   
    2  [repotting mat, waterproof, portable, foldable...   
    3  [doormat, absorbent, non-slip, coconut fiber, ...   
    4                   [tv tray, foldable, metal, grey]   

                                         img_description  \
    0  The GOYMFK Free Standing Shoe Rack is a versat...   
    1  The Subrtex Leather Dining Chairs come in a se...   
    2  The Plant Repotting Mat is a portable and fold...   
    3  The Pickleball Doormat is a charming welcome m...   
    4  The JOIN IRON Foldable TV Tray Set includes fo...   

                                                 caption  
    0  Sleek white multi-layer metal free-standing sh...  
    1  Set of 2 modern black faux leather dining chai...  
    2       Vibrant green waterproof plant repotting mat  
    3  Coir welcome mat featuring a playful "It's a g...  
    ... (省略 1 行)
    ```

```python
data_path = "data/items_tagged_and_captioned.csv"
```

```python
# Saving locally for later - optional: do not execute if you prefer to use the provided file
df.to_csv(data_path, index=False)
```

```python
# Optional: load data from saved file if you haven't processed the whole dataset
df = pd.read_csv(data_path)
```

### 對 caption 和關鍵字做 embedding
現在可以用產生的 caption 和關鍵字，去比對符合輸入文字查詢或 caption 的內容。 
做法是把關鍵字加 caption 合在一起 embed。
注意：建立 embedding 大約要 3 分鐘，也可以直接載入處理好的資料集（見下方）。

```python
df_search = df.copy()
```

```python
def embed_tags_caption(x):
    if x['caption'] != '':
        try:
            keywords_string = ",".join(k for k in x['keywords']) + '\n'
            content = keywords_string + x['caption']
            embedding = get_embedding(content)
            return embedding
        except Exception as e:
            print(f"Error creating embedding for {x}: {e}")
```

```python
df_search['embedding'] = df_search.apply(lambda x: embed_tags_caption(x), axis=1)
```

```python
df_search.head()
```

??? note "輸出"

    ```text
                                                   title  \
    0  GOYMFK 1pc Free Standing Shoe Rack, Multi-laye...   
    1  subrtex Leather ding Room, Dining Chairs Set o...   
    2  Plant Repotting Mat MUYETOL Waterproof Transpl...   
    3  Pickleball Doormat, Welcome Doormat Absorbent ...   
    4  JOIN IRON Foldable TV Trays for Eating Set of ...   

                                           primary_image              style  \
    0  https://m.media-amazon.com/images/I/416WaLx10j...             Modern   
    1  https://m.media-amazon.com/images/I/31SejUEWY7...  Black Rubber Wood   
    2  https://m.media-amazon.com/images/I/41RgefVq70...             Modern   
    3  https://m.media-amazon.com/images/I/61vz1Igler...             Modern   
    4  https://m.media-amazon.com/images/I/41p4d4VJnN...    X Classic Style   

           material          color                                   url  \
    0         Metal          White  https://www.amazon.com/dp/B0CJHKVG6P   
    1        Sponge          Black  https://www.amazon.com/dp/B0B66QHB23   
    2  Polyethylene          Green  https://www.amazon.com/dp/B0BXRTWLYK   
    3        Rubber          A5589  https://www.amazon.com/dp/B0C1MRB2M8   
    4          Iron  Grey Set of 4  https://www.amazon.com/dp/B0CG1N9QRC   

                                                keywords  \
    0  ['shoe rack', 'metal', 'white', 'multi-layer',...   
    1               ['dining chair', 'leather', 'black']   
    2  ['repotting mat', 'waterproof', 'portable', 'f...   
    3  ['doormat', 'absorbent', 'non-slip', 'coconut ...   
    4           ['tv tray', 'foldable', 'metal', 'grey']   

                                         img_description  \
    0  The GOYMFK Free Standing Shoe Rack is a versat...   
    1  The Subrtex Leather Dining Chairs come in a se...   
    2  The Plant Repotting Mat is a portable and fold...   
    3  The Pickleball Doormat is a charming welcome m...   
    4  The JOIN IRON Foldable TV Tray Set includes fo...   

                                                 caption  \
    0  Sleek white multi-layer metal free-standing sh...   
    1  Set of 2 modern black faux leather dining chai...   
    2       Vibrant green waterproof plant repotting mat   
    3  Coir welcome mat featuring a playful "It's a g...   
    ... (省略 8 行)
    ```

```python
# Keep only the lines where we have embeddings
df_search = df_search.dropna(subset=['embedding'])
print(df_search.shape)
```

??? note "輸出"

    ```text
    (50, 10)
    ```

```python
data_embeddings_path = "data/items_tagged_and_captioned_embeddings.csv"
```

```python
# Saving locally for later - optional: do not execute if you prefer to use the provided file
df_search.to_csv(data_embeddings_path, index=False)
```

```python
# Optional: load data from saved file if you haven't processed the whole dataset
from ast import literal_eval
df_search = pd.read_csv(data_embeddings_path)
df_search["embedding"] = df_search.embedding.apply(literal_eval).apply(np.array)
```

### 用輸入文字搜尋    

使用者輸入的文字可以直接拿去跟剛建好的 embedding 比較。

```python
# Searching for N most similar results
def search_from_input_text(query, n = 2):
    embedded_value = get_embedding(query)
    df_search['similarity'] = df_search['embedding'].apply(lambda x: cosine_similarity(np.array(x).reshape(1,-1), np.array(embedded_value).reshape(1, -1)))
    most_similar = df_search.sort_values('similarity', ascending=False).iloc[:n]
    return most_similar
```

```python
user_inputs = ['shoe storage', 'black metal side table', 'doormat', 'step bookshelf', 'ottoman']
```

```python
for i in user_inputs:
    print(f"Input: {i}\n")
    res = search_from_input_text(i)
    for index, row in res.iterrows():
        similarity_score = row['similarity']
        if isinstance(similarity_score, np.ndarray):
            similarity_score = similarity_score[0][0]
        print(f"{row['title'][:50]}{'...' if len(row['title']) > 50 else ''} ({row['url']}) - Similarity: {similarity_score:.2f}")
        img = Image(url=row['primary_image'])
        display(img)
        print("\n\n")
```

??? note "輸出"

    ```text
    Input: shoe storage

    GOYMFK 1pc Free Standing Shoe Rack, Multi-layer Me... (https://www.amazon.com/dp/B0CJHKVG6P) - Similarity: 0.57
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    MAEPA RV Shoe Storage for Bedside - 8 Extra Large ... (https://www.amazon.com/dp/B0C4PL1R3F) - Similarity: 0.55
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input: black metal side table

    FLYJOE Narrow Side Table with PU Leather Magazine ... (https://www.amazon.com/dp/B0CHYDTQKN) - Similarity: 0.58
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    HomePop Metal Accent Table Triangle Base Round Mir... (https://www.amazon.com/dp/B08N5H868H) - Similarity: 0.57
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input: doormat

    GXFC ZHAO Welcome Funny Door Mat Shoes and Bras Of... (https://www.amazon.com/dp/B07X61R7N8) - Similarity: 0.52
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Pickleball Doormat, Welcome Doormat Absorbent Non-... (https://www.amazon.com/dp/B0C1MRB2M8) - Similarity: 0.49
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input: step bookshelf

    Leick Home 70007-WTGD Mixed Metal and Wood Stepped... (https://www.amazon.com/dp/B098KNRNLQ) - Similarity: 0.57
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Wildkin Kids Canvas Sling Bookshelf with Storage f... (https://www.amazon.com/dp/B07GBVFZ1Y) - Similarity: 0.46
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input: ottoman

    Moroccan Leather Pouf Ottoman for Living Room - Ro... (https://www.amazon.com/dp/B0CP45784G) - Similarity: 0.49
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    HomePop Home Decor | K2380-YDQY-2 | Luxury Large F... (https://www.amazon.com/dp/B0B94T1TZ1) - Similarity: 0.46
    ```

    ```text
    <IPython.core.display.Image object>
    ```

### 用圖片搜尋

如果輸入是圖片，可以先把圖片轉成 caption，再 embed 這些 caption，跟已建好的 embedding 比較，找出相似的圖片。

```python
# We'll take a mix of images: some we haven't seen and some that are already in the dataset
example_images = df.iloc[306:]['primary_image'].to_list() + df.iloc[5:10]['primary_image'].to_list()
```

```python
for i in example_images:
    img_description = describe_image(i, '')
    caption = caption_image(img_description)
    img = Image(url=i)
    print('Input: \n')
    display(img)
    res = search_from_input_text(caption, 1).iloc[0]
    similarity_score = res['similarity']
    if isinstance(similarity_score, np.ndarray):
        similarity_score = similarity_score[0][0]
    print(f"{res['title'][:50]}{'...' if len(res['title']) > 50 else ''} ({res['url']}) - Similarity: {similarity_score:.2f}")
    img_res = Image(url=res['primary_image'])
    display(img_res)
    print("\n\n")
```

??? note "輸出"

    ```text
    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    Black Leather Office Chair Mid Back Leather Desk C... (https://www.amazon.com/dp/B0BVQSPCCF) - Similarity: 0.54
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    subrtex Leather ding Room, Dining Chairs Set of 2,... (https://www.amazon.com/dp/B0B66QHB23) - Similarity: 0.52
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    MAEPA RV Shoe Storage for Bedside - 8 Extra Large ... (https://www.amazon.com/dp/B0C4PL1R3F) - Similarity: 0.65
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    Chief Mfg.Swing-Arm Wall Mount Hardware Mount Blac... (https://www.amazon.com/dp/B007E40Z5K) - Similarity: 0.66
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    Homebeez 39.1" Length Bedroom Storage Bench, End B... (https://www.amazon.com/dp/B0BWQ8M4Q3) - Similarity: 0.52
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    subrtex Leather ding Room, Dining Chairs Set of 2,... (https://www.amazon.com/dp/B0B66QHB23) - Similarity: 0.51
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    LOVMOR 30'' Bathroom Vanity Sink Base Cabine, Stor... (https://www.amazon.com/dp/B0C9WYYFLB) - Similarity: 0.58
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    Folews Bathroom Organizer Over The Toilet Storage,... (https://www.amazon.com/dp/B09NZY3R1T) - Similarity: 0.73
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    GOYMFK 1pc Free Standing Shoe Rack, Multi-layer Me... (https://www.amazon.com/dp/B0CJHKVG6P) - Similarity: 0.72
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    subrtex Leather ding Room, Dining Chairs Set of 2,... (https://www.amazon.com/dp/B0B66QHB23) - Similarity: 0.77
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text



    Input:
    ```

    ```text
    <IPython.core.display.Image object>
    ```

    ```text
    Plant Repotting Mat MUYETOL Waterproof Transplanti... (https://www.amazon.com/dp/B0BXRTWLYK) - Similarity: 0.64
    ```

    ```text
    <IPython.core.display.Image object>
    ```

## 總結


這份 notebook 探索了怎麼用 `gpt-4o-mini` 的多模態能力替圖片加標籤和 caption。把圖片連同背景資訊一起給模型，就能產生標籤和描述，再進一步精修成 caption。這個流程在很多情境都實用，尤其能強化搜尋功能。

示範的搜尋用法可以直接套用到推薦系統等應用，這些技巧也能延伸到商品搜尋以外的情境，例如處理非結構化圖片資料的 RAG 應用。

下一步可以試試把關鍵字的規則式過濾，和 caption 的 embedding 搜尋結合，取得更相關的結果。

## 重點整理
- 多模態模型可以同時吃圖片和文字 context，圖片加商品標題能讓模型聚焦在要標記的那個物品。
- 用 embedding 比對關鍵字，可以去掉同義詞或對上預先定義的關鍵字清單。
- 先產生長描述、再用 few-shot 壓成短 caption，比一步到位更好控制風格。
- 圖片搜尋的做法是圖片轉 caption、caption 轉 embedding，再跟已建好的 embedding 比相似度。
- few-shot 不夠時，可以考慮 fine-tune 來對齊風格和語氣。

## 練習
1. 改關鍵字抽取的 prompt（例如限制最多 5 個關鍵字），看輸出的差異。
2. 換一張自己的圖片當查詢，用「圖片轉 caption 再搜尋」找出最相似的商品。
3. 把關鍵字的比對和 caption 的 embedding 搜尋結合：先用關鍵字過濾，再用 embedding 排序。
