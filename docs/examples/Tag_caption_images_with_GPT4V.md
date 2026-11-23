---
translated: false
source: examples/Tag_caption_images_with_GPT4V.ipynb
---

# Using GPT4o mini to tag and caption images

> 原文：[examples/Tag_caption_images_with_GPT4V.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Tag_caption_images_with_GPT4V.ipynb)



<!-- tutor:goals -->


This notebook explores how to leverage the vision capabilities of the GPT-4* models (for example `gpt-4o`, `gpt-4o-mini` or `gpt-4-turbo`) to tag & caption images. 

We can leverage the multimodal capabilities of these models to provide input images along with additional context on what they represent, and prompt the model to output tags or image descriptions. The image descriptions can then be further refined with a language model (in this notebook, we'll use `gpt-4o-mini`) to generate captions. 

Generating text content from images can be useful for multiple use cases, especially use cases involving search.  
We will illustrate a search use case in this notebook by using generated keywords and product captions to search for products - both from a text input and an image input.

As an example, we will use a dataset of Amazon furniture items, tag them with relevant keywords and generate short, descriptive captions.

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

## Tag images

In this section, we'll use GPT-4o mini to generate relevant tags for our products.

We'll use a simple zero-shot approach to extract keywords, and deduplicate those keywords using embeddings to avoid having multiple keywords that are too similar.

We will use a combination of an image and the product title to avoid extracting keywords for other items that are depicted in the image - sometimes there are multiple items used in the scene and we want to focus on just the one we want to tag.

### Extract keywords

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

#### Testing with a few examples

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

### Looking up existing keywords

Using embeddings to avoid duplicates (synonyms) and/or match pre-defined keywords

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

#### Testing with example keywords

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

## Generate captions

In this section, we'll use GPT-4o mini to generate an image description and then use a few-shot examples approach with GPT-4-turbo to generate captions from the images.

If few-shot examples are not enough for your use case, consider fine-tuning a model to get the generated captions to match the style & tone you are targeting. 

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

### Describing images with GPT-4o mini

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

#### Testing on a few examples

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

### Turning descriptions into captions
Using a few-shot examples approach to turn a long description into a short image caption

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

#### Testing on a few examples

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

## Image search

In this section, we will use generated keywords and captions to search items that match a given input, either text or image.

We will leverage our embeddings model to generate embeddings for the keywords and captions and compare them to either input text or the generated caption from an input image.

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

### Preparing the dataset

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

Processing all 312 lines of the dataset will take a while.
To test out the idea, we will only run it on the first 50 lines: this takes ~20 mins. 
Feel free to skip this step and load the already processed dataset (see below).

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

### Embedding captions and keywords
We can now use the generated captions and keywords to match relevant content to an input text query or caption. 
To do this, we will embed a combination of keywords + captions.
Note: creating the embeddings will take ~3 mins to run. Feel free to load the pre-processed dataset (see below).

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

### Search from input text    

We can compare the input text from a user directly to the embeddings we just created.

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

### Search from image

If the input is an image, we can find similar images by first turning images into captions, and embedding those captions to compare them to the already created embeddings.

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

## Wrapping up


In this notebook, we explored how to leverage the multimodal capabilities of `gpt-4o-mini` to tag and caption images. By providing images along with contextual information to the model, we were able to generate tags and descriptions that can be further refined to create captions. This process has practical applications in various scenarios, particularly in enhancing search functionalities.

The search use case illustrated can be directly applied to applications such as recommendation systems, but the techniques covered in this notebook can be extended beyond items search and used in multiple use cases, for example RAG applications leveraging unstructured image data.

As a next step, you could explore using a combination of rule-based filtering with keywords and embeddings search with captions to retrieve more relevant results.

<!-- tutor:summary -->
