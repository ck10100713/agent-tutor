---
translated: true
source: examples/Clustering_for_transaction_classification.ipynb
---

# 用分群做交易分類

> 原文：[examples/Clustering_for_transaction_classification.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Clustering_for_transaction_classification.ipynb)



## 這篇在做什麼

資料沒有標籤，但有可以拿來分群的特徵時怎麼辦？這篇用 K-Means 把交易的 embedding 分成幾群，再用 GPT 為每個 cluster 產生好懂的描述，最後拿這些描述替原本沒標籤的資料貼標籤。

## 學完你會

- 用交易的 embedding 做 K-Means 分群
- 用 Completions endpoint 為每個 cluster 產生有意義的描述
- 檢視分群視覺化，判斷哪些 cluster 重疊、需要再調整

## 開跑前

- OpenAI API key
- 交易 embedding 資料（延續 Multiclass classification for transactions 的做法，涵蓋資料集中全部 359 筆交易）

這份 notebook 處理的情境是：你的資料沒有標籤，但有可以把它們分成有意義類別的特徵。分群的難處在於讓這些凸顯 cluster 的特徵變得人類看得懂，這正是我們要用 GPT-3 為我們產生有意義的 cluster 描述的地方。接著就能用這些描述，替原本沒有標籤的資料集貼上標籤。

餵給模型的是 embedding，產生方式採用 [Multiclass classification for transactions Notebook](https://github.com/openai/openai-cookbook/blob/main/examples/Multiclass_classification_for_transactions.ipynb) 裡展示的做法，並套用到資料集全部 359 筆交易上，讓我們有更大的學習樣本。

## 設定

```python
# optional env import
from dotenv import load_dotenv
load_dotenv()
```

??? note "輸出"

    ```text
    True
    ```

```python
# imports
 
from openai import OpenAI
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.manifold import TSNE
import matplotlib
import matplotlib.pyplot as plt
import os
from ast import literal_eval

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
COMPLETIONS_MODEL = "gpt-3.5-turbo"

# This path leads to a file with data and precomputed embeddings
embedding_path = "data/library_transactions_with_embeddings_359.csv"
```

## 分群

我們會沿用 [Clustering Notebook](Clustering.md) 的做法，用 K-Means 搭配先前建立的特徵 embedding 對資料集分群。接著用 Completions endpoint 為我們產生 cluster 描述，並評估它們的效果。

```python
df = pd.read_csv(embedding_path)
df.head()
```

??? note "輸出"

    ```text
             Date                      Supplier                 Description  \
    0  21/04/2016          M & J Ballantyne Ltd       George IV Bridge Work   
    1  26/04/2016                  Private Sale   Literary & Archival Items   
    2  30/04/2016     City Of Edinburgh Council         Non Domestic Rates    
    3  09/05/2016              Computacenter Uk                 Kelvin Hall   
    4  09/05/2016  John Graham Construction Ltd  Causewayside Refurbishment   

       Transaction value (£)                                           combined  \
    0                35098.0  Supplier: M & J Ballantyne Ltd; Description: G...   
    1                30000.0  Supplier: Private Sale; Description: Literary ...   
    2                40800.0  Supplier: City Of Edinburgh Council; Descripti...   
    3                72835.0  Supplier: Computacenter Uk; Description: Kelvi...   
    4                64361.0  Supplier: John Graham Construction Ltd; Descri...   

       n_tokens                                          embedding  
    0       118  [-0.013169967569410801, -0.004833734128624201,...  
    1       114  [-0.019571533426642418, -0.010801066644489765,...  
    2       114  [-0.0054041435942053795, -6.548957026097924e-0...  
    3       113  [-0.004776035435497761, -0.005533686839044094,...  
    4       117  [0.003290407592430711, -0.0073441751301288605,...
    ```

```python
embedding_df = pd.read_csv(embedding_path)
embedding_df["embedding"] = embedding_df.embedding.apply(literal_eval).apply(np.array)
matrix = np.vstack(embedding_df.embedding.values)
matrix.shape
```

??? note "輸出"

    ```text
    (359, 1536)
    ```

```python
n_clusters = 5

kmeans = KMeans(n_clusters=n_clusters, init="k-means++", random_state=42, n_init=10)
kmeans.fit(matrix)
labels = kmeans.labels_
embedding_df["Cluster"] = labels
```

```python
tsne = TSNE(
    n_components=2, perplexity=15, random_state=42, init="random", learning_rate=200
)
vis_dims2 = tsne.fit_transform(matrix)

x = [x for x, y in vis_dims2]
y = [y for x, y in vis_dims2]

for category, color in enumerate(["purple", "green", "red", "blue","yellow"]):
    xs = np.array(x)[embedding_df.Cluster == category]
    ys = np.array(y)[embedding_df.Cluster == category]
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

```python
# We'll read 10 transactions per cluster as we're expecting some variation
transactions_per_cluster = 10

for i in range(n_clusters):
    print(f"Cluster {i} Theme:\n")

    transactions = "\n".join(
        embedding_df[embedding_df.Cluster == i]
        .combined.str.replace("Supplier: ", "")
        .str.replace("Description: ", ":  ")
        .str.replace("Value: ", ":  ")
        .sample(transactions_per_cluster, random_state=42)
        .values
    )
    response = client.chat.completions.create(
        model=COMPLETIONS_MODEL,
        # We'll include a prompt to instruct the model what sort of description we're looking for
        messages=[
            {"role": "user",
             "content": f'''We want to group these transactions into meaningful clusters so we can target the areas we are spending the most money. 
                What do the following transactions have in common?\n\nTransactions:\n"""\n{transactions}\n"""\n\nTheme:'''}
        ],
        temperature=0,
        max_tokens=100,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )
    print(response.choices[0].message.content.replace("\n", ""))
    print("\n")

    sample_cluster_rows = embedding_df[embedding_df.Cluster == i].sample(transactions_per_cluster, random_state=42)
    for j in range(transactions_per_cluster):
        print(sample_cluster_rows.Supplier.values[j], end=", ")
        print(sample_cluster_rows.Description.values[j], end="\n")

    print("-" * 100)
    print("\n")
```

??? note "輸出"

    ```text
    Cluster 0 Theme:

    The common theme among these transactions is that they all involve spending money on various expenses such as electricity, non-domestic rates, IT equipment, computer equipment, and the purchase of an electric van.


    EDF ENERGY, Electricity Oct 2019 3 buildings
    City Of Edinburgh Council, Non Domestic Rates 
    EDF, Electricity
    EX LIBRIS, IT equipment
    City Of Edinburgh Council, Non Domestic Rates 
    CITY OF EDINBURGH COUNCIL, Rates for 33 Salisbury Place
    EDF Energy, Electricity
    XMA Scotland Ltd, IT equipment
    Computer Centre UK Ltd, Computer equipment
    ARNOLD CLARK, Purchase of an electric van
    ----------------------------------------------------------------------------------------------------


    Cluster 1 Theme:

    The common theme among these transactions is that they all involve payments for various goods and services. Some specific examples include student bursary costs, collection of papers, architectural works, legal deposit services, papers related to Alisdair Gray, resources on slavery abolition and social justice, collection items, online/print subscriptions, ALDL charges, and literary/archival items.


    Institute of Conservation, This payment covers 2 invoices for student bursary costs
    PRIVATE SALE, Collection of papers of an individual
    LEE BOYD LIMITED, Architectural Works
    ALDL, Legal Deposit Services
    RICK GEKOSKI, Papers 1970's to 2019 Alisdair Gray
    ADAM MATTHEW DIGITAL LTD, Resource -  slavery abolution and social justice
    PROQUEST INFORMATION AND LEARN, This payment covers multiple invoices for collection items
    LM Information Delivery UK LTD, Payment of 18 separate invoice for Online/Print subscriptions Jan 20-Dec 20
    ALDL, ALDL Charges
    Private Sale, Literary & Archival Items
    ----------------------------------------------------------------------------------------------------


    Cluster 2 Theme:

    The common theme among these transactions is that they all involve spending money at Kelvin Hall.

    ... (省略 48 行)
    ```

### 結論

我們現在有五個新的 cluster 可以用來描述資料。從視覺化來看，有些 cluster 有重疊，還需要一些調整才能到位，不過已經能看出 GPT-3 做了一些有效的推論。特別是，它發現包含法定送存（legal deposit）的項目跟文獻典藏有關，這是對的，而模型事先沒有被給任何線索。很酷，而且稍加調整，我們就能建立一組基礎 cluster，再搭配多類別分類器，推廣到我們可能用到的其他交易資料集。

## 重點整理

- 沒標籤的資料可以先用 embedding 加分群找出結構，再靠 LLM 把 cluster 翻成人看得懂的描述。
- cluster 描述可以當作標籤，用來替原本沒標籤的資料貼標。
- 分群結果不一定乾淨，視覺化能幫你發現重疊，需要調整。
- 之後可以用這些標籤訓練多類別分類器，推廣到其他資料集。

## 練習

1. 改 K-Means 的 cluster 數量（目前是五個），看描述和視覺化怎麼變。
2. 調整產生 cluster 描述的 prompt，要求更簡短的標籤，比較結果。
3. 挑一個重疊的 cluster，檢查裡面的交易樣本，改 prompt 或 cluster 數量，讓描述更能區分彼此。
