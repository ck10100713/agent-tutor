---
translated: true
source: examples/Clustering.ipynb
---
# Clustering

> 原文：[examples/Clustering.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Clustering.ipynb)



## 這篇在做什麼

拿已經算好的評論 embedding 丟進 k-means，把相似的評論自動分成幾群，再把每群的畫在 2D 圖上看。最後從每群隨機抽 5 則評論，請 gpt-4 幫這一群取名字。

## 學完你會

- 用 k-means 對 embedding 做分群，並自己決定群數
- 把高維 embedding 投影到 2D 畫出分群結果
- 從每群抽樣文字，用 LLM 幫群集命名

## 開跑前

需要先跑過 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md) 產生資料集，命名那段要用 OpenAI API key。

## 用 OpenAI embedding 做 K-means 分群

這裡用最簡單的 k-means 示範分群怎麼做。分群可以幫你找出資料裡有價值、但原本看不出來的群組。資料集是在 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md) 裡建立的。

```python
# imports
import numpy as np
import pandas as pd
from ast import literal_eval

# load data
datafile_path = "./data/fine_food_reviews_with_embeddings_1k.csv"

df = pd.read_csv(datafile_path)
df["embedding"] = df.embedding.apply(literal_eval).apply(np.array)  # convert string to numpy array
matrix = np.vstack(df.embedding.values)
matrix.shape
```

??? note "輸出"

    ```text
    (1000, 1536)
    ```

### 1. 用 K-means 找出群集

這裡只示範 K-means 最簡單的用法。群數可以依你的情境自己挑。

```python
from sklearn.cluster import KMeans

n_clusters = 4

kmeans = KMeans(n_clusters=n_clusters, init="k-means++", random_state=42)
kmeans.fit(matrix)
labels = kmeans.labels_
df["Cluster"] = labels

df.groupby("Cluster").Score.mean().sort_values()
```

??? note "輸出"

    ```text
    /opt/homebrew/lib/python3.11/site-packages/sklearn/cluster/_kmeans.py:870: FutureWarning: The default value of `n_init` will change from 10 to 'auto' in 1.4. Set the value of `n_init` explicitly to suppress the warning
      warnings.warn(
    ```

    ```text
    Cluster
    0    4.105691
    1    4.191176
    2    4.215613
    3    4.306590
    Name: Score, dtype: float64
    ```

```python
from sklearn.manifold import TSNE
import matplotlib
import matplotlib.pyplot as plt

tsne = TSNE(n_components=2, perplexity=15, random_state=42, init="random", learning_rate=200)
vis_dims2 = tsne.fit_transform(matrix)

x = [x for x, y in vis_dims2]
y = [y for x, y in vis_dims2]

for category, color in enumerate(["purple", "green", "red", "blue"]):
    xs = np.array(x)[df.Cluster == category]
    ys = np.array(y)[df.Cluster == category]
    plt.scatter(xs, ys, color=color, alpha=0.3)

    avg_x = xs.mean()
    avg_y = ys.mean()

    plt.scatter(avg_x, avg_y, marker="x", color=color, s=100)
plt.title("Clusters identified visualized in language 2d using t-SNE")
```

??? note "輸出"

    ```text
    Text(0.5, 1.0, 'Clusters identified visualized in language 2d using t-SNE')
    ```

這是分群結果投影到 2D 的視覺化。這次跑的結果裡，綠色那群（#1）跟其他群看起來差蠻多。我們來看看每一群的幾個樣本。

### 2. 各群的文字樣本與群集命名

從每個群集隨機抽幾則樣本出來看。我們用 gpt-4 根據每群隨機抽出的 5 則評論來幫該群命名。

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

# Reading a review which belong to each group.
rev_per_cluster = 5

for i in range(n_clusters):
    print(f"Cluster {i} Theme:", end=" ")

    reviews = "\n".join(
        df[df.Cluster == i]
        .combined.str.replace("Title: ", "")
        .str.replace("\n\nContent: ", ":  ")
        .sample(rev_per_cluster, random_state=42)
        .values
    )

    messages = [
        {"role": "user", "content": f'What do the following customer reviews have in common?\n\nCustomer reviews:\n"""\n{reviews}\n"""\n\nTheme:'}
    ]

    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0,
        max_tokens=64,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0)
    print(response.choices[0].message.content.replace("\n", ""))

    sample_cluster_rows = df[df.Cluster == i].sample(rev_per_cluster, random_state=42)
    for j in range(rev_per_cluster):
        print(sample_cluster_rows.Score.values[j], end=", ")
        print(sample_cluster_rows.Summary.values[j], end=":   ")
        print(sample_cluster_rows.Text.str[:70].values[j])

    print("-" * 100)
```

??? note "輸出"

    ```text
    Cluster 0 Theme: The theme of these customer reviews is food products purchased on Amazon.
    5, Loved these gluten free healthy bars, saved $$ ordering on Amazon:   These Kind Bars are so good and healthy & gluten free.  My daughter ca
    1, Should advertise coconut as an ingredient more prominently:   First, these should be called Mac - Coconut bars, as Coconut is the #2
    5, very good!!:   just like the runts<br />great flavor, def worth getting<br />I even o
    5, Excellent product:   After scouring every store in town for orange peels and not finding an
    5, delicious:   Gummi Frogs have been my favourite candy that I have ever tried. of co
    ----------------------------------------------------------------------------------------------------
    Cluster 1 Theme: Pet food reviews
    2, Messy and apparently undelicious:   My cat is not a huge fan. Sure, she'll lap up the gravy, but leaves th
    4, The cats like it:   My 7 cats like this food but it is a little yucky for the human. Piece
    5, cant get enough of it!!!:   Our lil shih tzu puppy cannot get enough of it. Everytime she sees the
    1, Food Caused Illness:   I switched my cats over from the Blue Buffalo Wildnerness Food to this
    5, My furbabies LOVE these!:   Shake the container and they come running. Even my boy cat, who isn't 
    ----------------------------------------------------------------------------------------------------
    Cluster 2 Theme: All the reviews are about different types of coffee.
    5, Fog Chaser Coffee:   This coffee has a full body and a rich taste. The price is far below t
    5, Excellent taste:   This is to me a great coffee, once you try it you will enjoy it, this 
    4, Good, but not Wolfgang Puck good:   Honestly, I have to admit that I expected a little better. That's not 
    5, Just My Kind of Coffee:   Coffee Masters Hazelnut coffee used to be carried in a local coffee/pa
    5, Rodeo Drive is Crazy Good Coffee!:   Rodeo Drive is my absolute favorite and I'm ready to order more!  That
    ----------------------------------------------------------------------------------------------------
    Cluster 3 Theme: The theme of these customer reviews is food and drink products.
    5, Wonderful alternative to soda pop:   This is a wonderful alternative to soda pop.  It's carbonated for thos
    5, So convenient, for so little!:   I needed two vanilla beans for the Love Goddess cake that my husbands 
    2, bot very cheesy:   Got this about a month ago.first of all it smells horrible...it tastes
    5, Delicious!:   I am not a huge beer lover.  I do enjoy an occasional Blue Moon (all o
    3, Just ok:   I bought this brand because it was all they had at Ranch 99 near us. I
    ----------------------------------------------------------------------------------------------------
    ```

要注意，分出來的群不一定符合你原本想拿它做什麼。群數多的話，會抓到比較細的特徵；群數少的話，通常只會抓到資料裡最大的差異。

## 重點整理

- k-means 直接對 embedding 做分群，不需要標籤。
- 群數要自己選，多就分得細，少就只分出最大的差異。
- 分群結果不一定符合你想要的用途，要看樣本確認。
- 2D 投影只是方便看，不代表真實的群集邊界。
- 可以讓 LLM 讀每群的樣本幫忙命名，快速理解群的意思。

## 練習

1. 把 k-means 的群數改成不同的值（例如 3 跟 8），比較分群結果跟 2D 圖有什麼不同。
2. 把抽樣數量從 5 則改成 10 則，看 gpt-4 取的群名有沒有變得更準。
3. 把命名用的 prompt 改成要求輸出「群名加一句描述」，並對每一群都跑一次。
