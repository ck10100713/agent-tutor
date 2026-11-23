---
translated: true
source: examples/third_party/Visualizing_embeddings_with_Atlas.ipynb
---
# 用 Atlas 視覺化 embedding

> 原文：[examples/third_party/Visualizing_embeddings_with_Atlas.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/Visualizing_embeddings_with_Atlas.ipynb)

## 這篇在做什麼

把食物評論的 OpenAI embedding 上傳到 Atlas，在瀏覽器或 Jupyter notebook 裡互動式地看這些 embedding 的分佈。

## 學完你會

- 登入 Atlas 並把現成的 embedding 資料上傳成一張地圖
- 在 Jupyter notebook 裡直接和上傳後的 embedding 互動
- 理解為什麼視覺化 embedding 有助於觀察資料裡的群聚

## 開跑前

- 需要一個 [Atlas](https://atlas.nomic.ai) 帳號
- 需要已經算好的食物評論 embedding 資料

## 在 Atlas 視覺化 OpenAI Embedding

這個範例要把食物評論的 embedding 上傳到 [Atlas](https://atlas.nomic.ai)，把 embedding 視覺化。

## Atlas 是什麼？

[Atlas](https://atlas.nomic.ai) 是一個機器學習工具，能在你的網頁瀏覽器裡視覺化超大型的 embedding 資料集。你可以把數百萬筆 embedding 上傳到 Atlas，在網頁瀏覽器或 jupyter notebook 裡和它們互動。

### 1. 登入 Atlas。


```python
!pip install nomic
```

```python
import pandas as pd
import numpy as np
from ast import literal_eval

# Load the embeddings
datafile_path = "data/fine_food_reviews_with_embeddings_1k.csv"
df = pd.read_csv(datafile_path)

# Convert to a list of lists of floats
embeddings = np.array(df.embedding.apply(literal_eval).to_list())
df = df.drop('embedding', axis=1)
df = df.rename(columns={'Unnamed: 0': 'id'})
```

```python
import nomic
from nomic import atlas
nomic.login('7xDPkYXSYDc1_ErdTPIcoAR9RNd8YDlkS3nVNXcVoIMZ6') #demo account

data = df.to_dict('records')
project = atlas.map_embeddings(embeddings=embeddings, data=data,
                               id_field='id',
                               colorable_fields=['Score'])
map = project.maps[0]
```

### 2. 在 Jupyter 裡和你的 embedding 互動

```python
map
```

??? note "輸出"

    ```text
    meek-laborer: https://atlas.nomic.ai/map/fddc0e07-97c5-477c-827c-96bca44519aa/463f4614-7689-47e4-b55b-1da0cc679559
    ```

## 重點整理

- Atlas 讓你在瀏覽器或 notebook 裡視覺化大量 embedding，不用自己畫降維圖。
- 流程是登入、上傳 embedding 資料建立地圖、再互動探索。
- 視覺化能幫你快速看出資料裡有哪些群聚和離群點。

## 練習

1. 跑完登入和上傳的 cell，打開 Atlas 網頁，找出一個你看得出主題的群聚。
2. 在 Jupyter 裡互動時，挑幾筆評論點開，確認同一群的評論內容真的相近。
3. 換成另一批資料（例如你自己的評論），用同樣的上傳 cell 建一張新地圖。
