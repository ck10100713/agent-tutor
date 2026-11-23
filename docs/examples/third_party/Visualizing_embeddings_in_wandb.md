---
translated: true
source: examples/third_party/Visualizing_embeddings_in_wandb.ipynb
---

# 用 Weights and Biases 視覺化 embedding

> 原文：[examples/third_party/Visualizing_embeddings_in_wandb.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/Visualizing_embeddings_in_wandb.ipynb)



## 這篇在做什麼
這篇把資料上傳到 [Weights & Biases](http://wandb.ai)，用 [Embedding Projector](https://docs.wandb.ai/ref/app/features/panels/weave/embedding-projector) 搭配 PCA、UMAP、t-SNE 這些常見降維演算法視覺化 embedding。資料集來自 [Get_embeddings_from_dataset](../Get_embeddings_from_dataset.md) 那篇。

## 學完你會
- 把原始資料和 1536 維 embedding 記錄成一張 W&B Table。
- 在 W&B 介面把 Table 切換成 2D 投影檢視。
- 理解 PCA、UMAP、t-SNE 這類降維方法拿來檢視 embedding 的用途。

## 開跑前
- 需要一個 Weights & Biases 帳號，並登入。
- 需要先跑完 Get_embeddings_from_dataset，產生帶 embedding 的資料集。

## 什麼是 Weights & Biases？

[Weights & Biases](http://wandb.ai) 是機器學習平台，OpenAI 和其他 ML 團隊用它更快做出更好的模型。他們用它快速追蹤實驗、評估模型表現、重現模型、視覺化結果，以及跟同事分享發現。

### 1. 把資料記錄到 W&B

我們用原始資料和 embedding 建立一張 [W&B Table](https://docs.wandb.ai/guides/data-vis/log-tables)。每則評論是一列，1536 個 embedding 浮點數各自有一欄，名稱是 `emb_{i}`。

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
```

```python
import wandb

original_cols = df.columns[1:-1].tolist()
embedding_cols = ['emb_'+str(idx) for idx in range(len(matrix[0]))]
table_cols = original_cols + embedding_cols

with wandb.init(project='openai_embeddings'):
    table = wandb.Table(columns=table_cols)
    for i, row in enumerate(df.to_dict(orient="records")):
        original_data = [row[col_name] for col_name in original_cols]
        embedding_data = matrix[i].tolist()
        table.add_data(*(original_data + embedding_data))
    wandb.log({'openai_embedding_table': table})
```

### 2. 以 2D 投影呈現

進入 W&B run 的連結後，點 Table 右上角的 ⚙️ 圖示，把「Render As:」改成「Combined 2D Projection」。

範例：http://wandb.me/openai_embeddings

## 重點整理
- 1536 維的 embedding 無法直接看，降維到 2D 才能目視檢查群聚。
- 把 embedding 攤成多個欄位（每維一欄）記錄到 W&B Table，是這個工具辨識向量的方式。
- PCA、UMAP、t-SNE 各有不同的取捨，同一份資料可以多種方式都看看。

## 練習
1. 只記錄資料集的前 200 筆到 Table，看 2D 投影載入速度和樣貌。
2. 在 Table 裡多放一個欄位（例如 Score），並用它來上色或分組。
3. 在 W&B 介面切換不同的降維演算法，比較同一份資料的群聚樣貌。
