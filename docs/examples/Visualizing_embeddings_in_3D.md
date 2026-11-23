---
translated: true
source: examples/Visualizing_embeddings_in_3D.ipynb
---

# 把 embedding 視覺化成 3D

> 原文：[examples/Visualizing_embeddings_in_3D.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Visualizing_embeddings_in_3D.ipynb)



## 這篇在做什麼

用 PCA 把 1536 維的 embedding 壓到 3 維，再畫成 3D 散點圖，直接看到資料怎麼分群。資料集是從 DBpedia 驗證集隨機抽樣 200 筆的小資料。

## 學完你會

- 載入已經算好 embedding 的資料集
- 用 scikit-learn 的 PCA 把高維 embedding 降到 3 維
- 把降維後的點畫成 3D 圖，並依類別上色

## 開跑前

本機需要安裝 notebook 用到的 Python 套件（例如 pandas、scikit-learn、plotly）。在 Colab 上直接在 cell 裡用 `%pip install` 即可。

這個範例用 [PCA](https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.PCA.html) 把 embedding 的維度從 1536 降到 3，這樣就能把資料點畫在 3D 圖裡。小資料集 `dbpedia_samples.jsonl` 是從 [DBpedia validation dataset](https://www.kaggle.com/danofer/dbpedia-classes?select=DBPEDIA_val.csv) 隨機抽 200 筆整理出來的。

### 1. 載入資料集和 query embedding

```python
import pandas as pd
samples = pd.read_json("data/dbpedia_samples.jsonl", lines=True)
categories = sorted(samples["category"].unique())
print("Categories of DBpedia samples:", samples["category"].value_counts())
samples.head()
```

??? note "輸出"

    ```text
    Categories of DBpedia samples: Artist                    21
    Film                      19
    Plant                     19
    OfficeHolder              18
    Company                   17
    NaturalPlace              16
    Athlete                   16
    Village                   12
    WrittenWork               11
    Building                  11
    Album                     11
    Animal                    11
    EducationalInstitution    10
    MeanOfTransportation       8
    Name: category, dtype: int64
    ```

    ```text
                                                    text      category
    0   Morada Limited is a textile company based in ...       Company
    1   The Armenian Mirror-Spectator is a newspaper ...   WrittenWork
    2   Mt. Kinka (金華山 Kinka-zan) also known as Kinka...  NaturalPlace
    3   Planning the Play of a Bridge Hand is a book ...   WrittenWork
    4   Wang Yuanping (born 8 December 1976) is a ret...       Athlete
    ```

```python
from utils.embeddings_utils import get_embeddings
# NOTE: The following code will send a query of batch size 200 to /embeddings
matrix = get_embeddings(samples["text"].to_list(), model="text-embedding-3-small")
```

### 2. 降低 embedding 的維度

```python
from sklearn.decomposition import PCA
pca = PCA(n_components=3)
vis_dims = pca.fit_transform(matrix)
samples["embed_vis"] = vis_dims.tolist()
```

### 3. 畫出降維後的 embedding

```python
%matplotlib widget
import matplotlib.pyplot as plt
import numpy as np

fig = plt.figure(figsize=(10, 5))
ax = fig.add_subplot(projection='3d')
cmap = plt.get_cmap("tab20")

# Plot each sample category individually such that we can set label name.
for i, cat in enumerate(categories):
    sub_matrix = np.array(samples[samples["category"] == cat]["embed_vis"].to_list())
    x=sub_matrix[:, 0]
    y=sub_matrix[:, 1]
    z=sub_matrix[:, 2]
    colors = [cmap(i/len(categories))] * len(sub_matrix)
    ax.scatter(x, y, zs=z, zdir='z', c=colors, label=cat)

ax.set_xlabel('x')
ax.set_ylabel('y')
ax.set_zlabel('z')
ax.legend(bbox_to_anchor=(1.1, 1))
```

??? note "輸出"

    ```text
    <matplotlib.legend.Legend at 0x1622180a0>
    ```

## 重點整理

- Embedding 是高維向量，要看得到就得先降維，PCA 是常用的線性方法。
- 降到 3 維會損失資訊，圖上的距離只是原本相似度的近似。
- 如果同類別的點在 3D 圖裡聚在一起，表示 embedding 確實抓到了類別的語意。
- 視覺化適合快速檢查資料和 embedding 品質，不適合拿來當精確的相似度判斷。

## 練習

1. 把 PCA 的 `n_components` 改成 2，畫成 2D 散點圖，比較跟 3D 的分群看起來差在哪。
2. 印出 PCA 的 `explained_variance_ratio_`，看 3 個主成分總共保留了多少變異。
3. 換成 t-SNE 降到 3 維並畫圖，跟 PCA 的結果比較哪個分群更清楚。
