---
translated: true
source: examples/Visualizing_embeddings_in_2D.ipynb
---

# 把 embedding 視覺化成 2D

> 原文：[examples/Visualizing_embeddings_in_2D.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Visualizing_embeddings_in_2D.ipynb)

## 這篇在做什麼

這篇把評論資料集的 1536 維 embedding 用 t-SNE 降到 2 維，再畫成散點圖，並依星等上色，看看 embedding 在低維空間裡有沒有分群。資料集來自前一篇 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md)。

## 學完你會

- 用 t-SNE 把高維 embedding 降到 2 維。
- 用 matplotlib 畫出 2D 散點圖，並依類別（星等）上色。
- 從圖上判斷 embedding 有沒有保留類別之間的區隔。

## 開跑前

需要先照 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md) 產生帶 embedding 的資料集。

## 把 embedding 視覺化成 2D

我們用 t-SNE 把 embedding 的維度從 1536 降到 2。降到兩維之後，就可以畫成 2D 散點圖。資料集是在 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md) 裡建立的。

### 1. 降維

我們用 t-SNE 分解把維度降到 2 維。

```python
import pandas as pd
from sklearn.manifold import TSNE
import numpy as np
from ast import literal_eval

# Load the embeddings
datafile_path = "data/fine_food_reviews_with_embeddings_1k.csv"
df = pd.read_csv(datafile_path)

# Convert to a list of lists of floats
matrix = np.array(df.embedding.apply(literal_eval).to_list())

# Create a t-SNE model and transform the data
tsne = TSNE(n_components=2, perplexity=15, random_state=42, init='random', learning_rate=200)
vis_dims = tsne.fit_transform(matrix)
vis_dims.shape
```

??? note "輸出"

    ```text
    (1000, 2)
    ```

### 2. 畫出 embedding

我們依星等替每則評論上色，從紅色到綠色。

即使降到 2 維，也能看出相當不錯的資料分離。

```python
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

colors = ["red", "darkorange", "gold", "turquoise", "darkgreen"]
x = [x for x,y in vis_dims]
y = [y for x,y in vis_dims]
color_indices = df.Score.values - 1

colormap = matplotlib.colors.ListedColormap(colors)
plt.scatter(x, y, c=color_indices, cmap=colormap, alpha=0.3)
for score in [0,1,2,3,4]:
    avg_x = np.array(x)[df.Score-1==score].mean()
    avg_y = np.array(y)[df.Score-1==score].mean()
    color = colors[score]
    plt.scatter(avg_x, avg_y, marker='x', color=color, s=100)

plt.title("Amazon ratings visualized in language using t-SNE")
```

??? note "輸出"

    ```text
    Text(0.5, 1.0, 'Amazon ratings visualized in language using t-SNE')
    ```

## 重點整理

- t-SNE 可以把 1536 維的 embedding 壓到 2 維，方便人眼檢視。
- 用已知標籤（星等）上色，可以快速檢查 embedding 有沒有抓到語意差異。
- 降到 2 維仍有明顯分離，代表原始 embedding 帶有足夠的類別資訊。

## 練習

1. 把 t-SNE 的 `perplexity` 改成別的值，重畫並比較分群的樣子。
2. 把顏色改成依評論長度或其他欄位上色，看有沒有別的結構。
3. 改用 PCA 取代 t-SNE 降到 2 維，比較兩張圖的分離程度。
