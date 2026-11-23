---
translated: true
source: examples/Semantic_text_search_using_embeddings.ipynb
---

# 用 embedding 做語意文字搜尋

> 原文：[examples/Semantic_text_search_using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Semantic_text_search_using_embeddings.ipynb)



## 這篇在做什麼
把搜尋查詢做成 embedding，再找出最相似的評論，就能用很有效率、成本很低的方式對所有評論做語意搜尋。資料集來自 [Get_embeddings_from_dataset](Get_embeddings_from_dataset.md) 那篇。

## 學完你會
- 用查詢和評論 embedding 的 cosine similarity 找出前 n 個最佳結果。
- 用語意搜尋找出特定類型的評論，例如配送失敗的案例。
- 了解資料變多時，可以用專門的演算法加速 embedding 搜尋。

## 開跑前
- 需要先跑完 Get_embeddings_from_dataset，產生帶 embedding 的資料集。
- 需要 OpenAI API key，查詢也要取 embedding。

```python
import pandas as pd
import numpy as np
from ast import literal_eval

datafile_path = "data/fine_food_reviews_with_embeddings_1k.csv"

df = pd.read_csv(datafile_path)
df["embedding"] = df.embedding.apply(literal_eval).apply(np.array)
```

這裡比較查詢與文件 embedding 的 cosine similarity，並顯示 top_n 個最佳比對結果。

```python
from utils.embeddings_utils import get_embedding, cosine_similarity

# search through the reviews for a specific product
def search_reviews(df, product_description, n=3, pprint=True):
    product_embedding = get_embedding(
        product_description,
        model="text-embedding-3-small"
    )
    df["similarity"] = df.embedding.apply(lambda x: cosine_similarity(x, product_embedding))

    results = (
        df.sort_values("similarity", ascending=False)
        .head(n)
        .combined.str.replace("Title: ", "")
        .str.replace("; Content:", ": ")
    )
    if pprint:
        for r in results:
            print(r[:200])
            print()
    return results


results = search_reviews(df, "delicious beans", n=3)
```

??? note "輸出"

    ```text
    Delicious!:  I enjoy this white beans seasoning, it gives a rich flavor to the beans I just love it, my mother in law didn't know about this Zatarain's brand and now she is traying different seasoning

    Fantastic Instant Refried beans:  Fantastic Instant Refried Beans have been a staple for my family now for nearly 20 years.  All 7 of us love it and my grown kids are passing on the tradition.

    Delicious:  While there may be better coffee beans available, this is my first purchase and my first time grinding my own beans.  I read several reviews before purchasing this brand, and am extremely
    ```

```python
results = search_reviews(df, "whole wheat pasta", n=3)
```

??? note "輸出"

    ```text
    Tasty and Quick Pasta:  Barilla Whole Grain Fusilli with Vegetable Marinara is tasty and has an excellent chunky vegetable marinara.  I just wish there was more of it.  If you aren't starving or on a 

    sooo good:  tastes so good. Worth the money. My boyfriend hates wheat pasta and LOVES this. cooks fast tastes great.I love this brand and started buying more of their pastas. Bulk is best.

    Bland and vaguely gamy tasting, skip this one:  As far as prepared dinner kits go, "Barilla Whole Grain Mezze Penne with Tomato and Basil Sauce" just did not do it for me...and this is coming from a p
    ```

我們可以很輕鬆地搜尋這些評論。要加速運算，可以用專門為加快 embedding 搜尋設計的演算法。

```python
results = search_reviews(df, "bad delivery", n=1)
```

??? note "輸出"

    ```text
    great product, poor delivery:  The coffee is excellent and I am a repeat buyer.  Problem this time was with the UPS delivery.  They left the box in front of my garage door in the middle of the drivewa
    ```

如你所見，這馬上就能帶來很多價值。這個範例裡我們能快速找出配送失敗的例子。

```python
results = search_reviews(df, "spoilt", n=1)
```

??? note "輸出"

    ```text
    Disappointed:  The metal cover has severely disformed. And most of the cookies inside have been crushed into small pieces. Shopping experience is awful. I'll never buy it online again.
    ```

```python
results = search_reviews(df, "pet food", n=2)
```

??? note "輸出"

    ```text
    Great food!:  I wanted a food for a a dog with skin problems. His skin greatly improved with the switch, though he still itches some.  He loves the food. No recalls, American made with American ingred

    Great food!:  I wanted a food for a a dog with skin problems. His skin greatly improved with the switch, though he still itches some.  He loves the food. No recalls, American made with American ingred
    ```

## 重點整理
- 語意搜尋就是把查詢和文件放到同一個向量空間，找距離最近的。
- 查詢只需一次 embedding 呼叫，之後的比對在本機算就好，所以便宜。
- 語意搜尋能找到字面不同但意思相近的內容，不靠關鍵字比對。
- 資料量大時，用近似最近鄰之類的專門演算法可以加快搜尋。

## 練習
1. 把查詢換成別的描述（例如「口味太甜」），看前幾名評論是否符合。
2. 調整 top_n，觀察排名後段結果的相關性怎麼下降。
3. 對同一個查詢，比較用加速演算法和直接算 cosine similarity 的結果與速度。
