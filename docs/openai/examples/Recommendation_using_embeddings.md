---
translated: true
source: examples/Recommendation_using_embeddings.ipynb
---

# 用 embedding 和最近鄰搜尋做推薦

> 原文：[examples/Recommendation_using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Recommendation_using_embeddings.ipynb)

## 這篇在做什麼

用 embedding 找出相似的項目來做推薦。資料集是 AG 新聞語料，要回答的問題是：給定一篇文章，哪些文章跟它最像。內容包含建立 embedding 快取、算距離推薦，以及用 t-SNE 把 embedding 壓到 2D 視覺化。

## 學完你會

- 建立 `(text, model)` 對應 embedding 的快取，避免重複付費
- 用 embedding 距離實作最近鄰推薦函式
- 用 t-SNE 視覺化 embedding，並理解壓到低維度會損失哪些資訊

## 開跑前

- 需要 `OPENAI_API_KEY`，第一次算 embedding 會產生費用
- 需要 AG 新聞資料集檔案


推薦在網路上無所不在。

- 「買了這個？試試這些類似的商品。」
- 「喜歡那本書？試試這些類似的書。」
- 「不是你要找的說明頁？試試這些類似的頁面。」

這個 notebook 示範怎麼用 embedding 找出相似的項目來推薦。我們用 [AG 新聞文章語料](http://groups.di.unipi.it/~gulli/AG_corpus_of_news_articles.html)當資料集。

模型要回答的問題是：給定一篇文章，哪些文章跟它最相似？

```python
import pandas as pd
import pickle

from utils.embeddings_utils import (
    get_embedding,
    distances_from_embeddings,
    tsne_components_from_embeddings,
    chart_from_components,
    indices_of_nearest_neighbors_from_distances,
)

EMBEDDING_MODEL = "text-embedding-3-small"
```

### 2. 載入資料

接著載入 AG 新聞資料，看看它長什麼樣子。

```python
# load data (full dataset available at http://groups.di.unipi.it/~gulli/AG_corpus_of_news_articles.html)
dataset_path = "data/AG_news_samples.csv"
df = pd.read_csv(dataset_path)

n_examples = 5
df.head(n_examples)
```

??? note "輸出"

    ```text
                                                   title  \
    0                                    World Briefings   
    1  Nvidia Puts a Firewall on a Motherboard (PC Wo...   
    2                Olympic joy in Greek, Chinese press   
    3                          U2 Can iPod with Pictures   
    4                                  The Dream Factory   

                                             description  label_int     label  
    0  BRITAIN: BLAIR WARNS OF CLIMATE THREAT Prime M...          1     World  
    1  PC World - Upcoming chip set will include buil...          4  Sci/Tech  
    2  Newspapers in Greece reflect a mixture of exhi...          2    Sports  
    3  SAN JOSE, Calif. -- Apple Computer (Quote, Cha...          4  Sci/Tech  
    4  Any product, any shape, any size -- manufactur...          4  Sci/Tech
    ```

同樣的範例，這次不要用省略號截斷來看。

```python
# print the title, description, and label of each example
for idx, row in df.head(n_examples).iterrows():
    print("")
    print(f"Title: {row['title']}")
    print(f"Description: {row['description']}")
    print(f"Label: {row['label']}")
```

??? note "輸出"

    ```text

    Title: World Briefings
    Description: BRITAIN: BLAIR WARNS OF CLIMATE THREAT Prime Minister Tony Blair urged the international community to consider global warming a dire threat and agree on a plan of action to curb the  quot;alarming quot; growth of greenhouse gases.
    Label: World

    Title: Nvidia Puts a Firewall on a Motherboard (PC World)
    Description: PC World - Upcoming chip set will include built-in security features for your PC.
    Label: Sci/Tech

    Title: Olympic joy in Greek, Chinese press
    Description: Newspapers in Greece reflect a mixture of exhilaration that the Athens Olympics proved successful, and relief that they passed off without any major setback.
    Label: Sports

    Title: U2 Can iPod with Pictures
    Description: SAN JOSE, Calif. -- Apple Computer (Quote, Chart) unveiled a batch of new iPods, iTunes software and promos designed to keep it atop the heap of digital music players.
    Label: Sci/Tech

    Title: The Dream Factory
    Description: Any product, any shape, any size -- manufactured on your desktop! The future is the fabricator. By Bruce Sterling from Wired magazine.
    Label: Sci/Tech
    ```

### 3. 建立快取來儲存 embedding

在取得這些文章的 embedding 之前，先設定一個快取來存我們產生的 embedding。一般來說，把 embedding 存起來以便日後重複使用是個好習慣。不存的話，每次重算都要付一次錢。

快取是一個 dictionary，把 `(text, model)` 這個 tuple 對應到 embedding（一串浮點數）。快取會存成 Python pickle 檔。

```python
# establish a cache of embeddings to avoid recomputing
# cache is a dict of tuples (text, model) -> embedding, saved as a pickle file

# set path to embedding cache
embedding_cache_path = "data/recommendations_embeddings_cache.pkl"

# load the cache if it exists, and save a copy to disk
try:
    embedding_cache = pd.read_pickle(embedding_cache_path)
except FileNotFoundError:
    embedding_cache = {}
with open(embedding_cache_path, "wb") as embedding_cache_file:
    pickle.dump(embedding_cache, embedding_cache_file)

# define a function to retrieve embeddings from the cache if present, and otherwise request via the API
def embedding_from_string(
    string: str,
    model: str = EMBEDDING_MODEL,
    embedding_cache=embedding_cache
) -> list:
    """Return embedding of given string, using a cache to avoid recomputing."""
    if (string, model) not in embedding_cache.keys():
        embedding_cache[(string, model)] = get_embedding(string, model)
        with open(embedding_cache_path, "wb") as embedding_cache_file:
            pickle.dump(embedding_cache, embedding_cache_file)
    return embedding_cache[(string, model)]
```

我們取一個 embedding 來確認它有用。

```python
# as an example, take the first description from the dataset
example_string = df["description"].values[0]
print(f"\nExample string: {example_string}")

# print the first 10 dimensions of the embedding
example_embedding = embedding_from_string(example_string)
print(f"\nExample embedding: {example_embedding[:10]}...")
```

??? note "輸出"

    ```text

    Example string: BRITAIN: BLAIR WARNS OF CLIMATE THREAT Prime Minister Tony Blair urged the international community to consider global warming a dire threat and agree on a plan of action to curb the  quot;alarming quot; growth of greenhouse gases.

    Example embedding: [0.0545826330780983, -0.00428084097802639, 0.04785159230232239, 0.01587914116680622, -0.03640881925821304, 0.0143799539655447, -0.014267769642174244, -0.015175441280007362, -0.002344391541555524, 0.011075624264776707]...
    ```

### 4. 依 embedding 推薦相似文章

要找相似文章，我們照三步驟計畫：
1. 取得所有文章描述的 similarity embedding
2. 計算來源標題和其他所有文章之間的距離
3. 印出離來源標題最近的其他文章

```python
def print_recommendations_from_strings(
    strings: list[str],
    index_of_source_string: int,
    k_nearest_neighbors: int = 1,
    model=EMBEDDING_MODEL,
) -> list[int]:
    """Print out the k nearest neighbors of a given string."""
    # get embeddings for all strings
    embeddings = [embedding_from_string(string, model=model) for string in strings]

    # get the embedding of the source string
    query_embedding = embeddings[index_of_source_string]

    # get distances between the source embedding and other embeddings (function from utils.embeddings_utils.py)
    distances = distances_from_embeddings(query_embedding, embeddings, distance_metric="cosine")
    
    # get indices of nearest neighbors (function from utils.utils.embeddings_utils.py)
    indices_of_nearest_neighbors = indices_of_nearest_neighbors_from_distances(distances)

    # print out source string
    query_string = strings[index_of_source_string]
    print(f"Source string: {query_string}")
    # print out its k nearest neighbors
    k_counter = 0
    for i in indices_of_nearest_neighbors:
        # skip any strings that are identical matches to the starting string
        if query_string == strings[i]:
            continue
        # stop after printing out k articles
        if k_counter >= k_nearest_neighbors:
            break
        k_counter += 1

        # print out the similar strings and their distances
        print(
            f"""
        --- Recommendation #{k_counter} (nearest neighbor {k_counter} of {k_nearest_neighbors}) ---
        String: {strings[i]}
        Distance: {distances[i]:0.3f}"""
        )

    return indices_of_nearest_neighbors
```

### 5. 推薦範例

我們先找跟第一篇（關於 Tony Blair）相似的文章。

```python
article_descriptions = df["description"].tolist()

tony_blair_articles = print_recommendations_from_strings(
    strings=article_descriptions,  # let's base similarity off of the article description
    index_of_source_string=0,  # articles similar to the first one about Tony Blair
    k_nearest_neighbors=5,  # 5 most similar articles
)
```

??? note "輸出"

    ```text
    Source string: BRITAIN: BLAIR WARNS OF CLIMATE THREAT Prime Minister Tony Blair urged the international community to consider global warming a dire threat and agree on a plan of action to curb the  quot;alarming quot; growth of greenhouse gases.

            --- Recommendation #1 (nearest neighbor 1 of 5) ---
            String: The anguish of hostage Kenneth Bigley in Iraq hangs over Prime Minister Tony Blair today as he faces the twin test of a local election and a debate by his Labour Party about the divisive war.
            Distance: 0.514

            --- Recommendation #2 (nearest neighbor 2 of 5) ---
            String: THE re-election of British Prime Minister Tony Blair would be seen as an endorsement of the military action in Iraq, Prime Minister John Howard said today.
            Distance: 0.516

            --- Recommendation #3 (nearest neighbor 3 of 5) ---
            String: Israel is prepared to back a Middle East conference convened by Tony Blair early next year despite having expressed fears that the British plans were over-ambitious and designed 
            Distance: 0.546

            --- Recommendation #4 (nearest neighbor 4 of 5) ---
            String: Allowing dozens of casinos to be built in the UK would bring investment and thousands of jobs, Tony Blair says.
            Distance: 0.568

            --- Recommendation #5 (nearest neighbor 5 of 5) ---
            String: AFP - A battle group of British troops rolled out of southern Iraq on a US-requested mission to deadlier areas near Baghdad, in a major political gamble for British Prime Minister Tony Blair.
            Distance: 0.579
    ```

不錯！5 篇推薦中有 4 篇明確提到 Tony Blair，第 5 篇是來自倫敦、關於氣候變遷的文章，這個主題也常跟 Tony Blair 連在一起。

再看看推薦器在第二篇範例文章上的表現，這篇是關於 NVIDIA 推出更安全的新晶片組。

```python
chipset_security_articles = print_recommendations_from_strings(
    strings=article_descriptions,  # let's base similarity off of the article description
    index_of_source_string=1,  # let's look at articles similar to the second one about a more secure chipset
    k_nearest_neighbors=5,  # let's look at the 5 most similar articles
)
```

??? note "輸出"

    ```text
    Source string: PC World - Upcoming chip set will include built-in security features for your PC.

            --- Recommendation #1 (nearest neighbor 1 of 5) ---
            String: PC World - Updated antivirus software for businesses adds intrusion prevention features.
            Distance: 0.422

            --- Recommendation #2 (nearest neighbor 2 of 5) ---
            String: PC World - Symantec, McAfee hope raising virus-definition fees will move users to\  suites.
            Distance: 0.518

            --- Recommendation #3 (nearest neighbor 3 of 5) ---
            String: originally offered on notebook PCs -- to its Opteron 32- and 64-bit x86 processors for server applications. The technology will help servers to run 
            Distance: 0.522

            --- Recommendation #4 (nearest neighbor 4 of 5) ---
            String: PC World - Send your video throughout your house--wirelessly--with new gateways and media adapters.
            Distance: 0.532

            --- Recommendation #5 (nearest neighbor 5 of 5) ---
            String: Chips that help a computer's main microprocessors perform specific types of math problems are becoming a big business once again.\
            Distance: 0.532
    ```

從印出的距離可以看到，第 1 名的推薦比其他的近很多（0.11 對 0.14 以上）。而且第 1 名看起來跟起始文章很像，同樣是 PC World 一篇談提升電腦安全的文章。不錯！

## 附錄：在更複雜的推薦系統裡使用 embedding

更複雜的推薦系統做法，是訓練一個機器學習模型，輸入幾十到幾百個訊號，像是商品熱門程度或使用者點擊資料。即使在這種系統裡，embedding 仍是很有用的訊號，尤其是處理還在「冷啟動」、沒有任何使用者資料的項目（例如剛加進商品目錄、還沒有任何點擊的新商品）。

## 附錄：用 embedding 視覺化相似文章

為了了解最近鄰推薦器在做什麼，我們把文章 embedding 視覺化。每個 embedding 向量有 2048 維，沒辦法直接畫出來，但可以用 [t-SNE](https://en.wikipedia.org/wiki/T-distributed_stochastic_neighbor_embedding) 或 [PCA](https://en.wikipedia.org/wiki/Principal_component_analysis) 這類技術，把 embedding 壓到 2 或 3 維再畫圖。

在視覺化最近鄰之前，先用 t-SNE 視覺化所有文章描述。注意 t-SNE 不是確定性的，每次跑的結果可能不同。

```python
# get embeddings for all article descriptions
embeddings = [embedding_from_string(string) for string in article_descriptions]
# compress the 2048-dimensional embeddings into 2 dimensions using t-SNE
tsne_components = tsne_components_from_embeddings(embeddings)
# get the article labels for coloring the chart
labels = df["label"].tolist()

chart_from_components(
    components=tsne_components,
    labels=labels,
    strings=article_descriptions,
    width=600,
    height=500,
    title="t-SNE components of article descriptions",
)
```

從上面的圖可以看到，即使壓縮得這麼厲害，embedding 還是能把文章描述依類別分群得很好。值得強調的是，這個分群完全沒用到標籤本身的資訊！

另外，仔細看最離譜的離群點，常常是標籤標錯，而不是 embedding 不好。例如落在綠色 Sports 群裡的藍色 World 點，大多看起來其實是體育新聞。

接著依「來源文章」、「它的最近鄰」和「其他」重新上色。

```python
# create labels for the recommended articles
def nearest_neighbor_labels(
    list_of_indices: list[int],
    k_nearest_neighbors: int = 5
) -> list[str]:
    """Return a list of labels to color the k nearest neighbors."""
    labels = ["Other" for _ in list_of_indices]
    source_index = list_of_indices[0]
    labels[source_index] = "Source"
    for i in range(k_nearest_neighbors):
        nearest_neighbor_index = list_of_indices[i + 1]
        labels[nearest_neighbor_index] = f"Nearest neighbor (top {k_nearest_neighbors})"
    return labels


tony_blair_labels = nearest_neighbor_labels(tony_blair_articles, k_nearest_neighbors=5)
chipset_security_labels = nearest_neighbor_labels(chipset_security_articles, k_nearest_neighbors=5
)
```

```python
# a 2D chart of nearest neighbors of the Tony Blair article
chart_from_components(
    components=tsne_components,
    labels=tony_blair_labels,
    strings=article_descriptions,
    width=600,
    height=500,
    title="Nearest neighbors of the Tony Blair article",
    category_orders={"label": ["Other", "Nearest neighbor (top 5)", "Source"]},
)
```

從上面的 2D 圖可以看到，關於 Tony Blair 的文章在 World 新聞群裡彼此有點靠近。有趣的是，雖然 5 個最近鄰（紅色）在高維空間裡最近，但在壓縮後的 2D 空間裡，它們並不是最近的點。壓到 2 維會丟掉很多資訊，2D 空間裡的最近鄰看起來沒有完整 embedding 空間裡的那麼相關。

```python
# a 2D chart of nearest neighbors of the chipset security article
chart_from_components(
    components=tsne_components,
    labels=chipset_security_labels,
    strings=article_descriptions,
    width=600,
    height=500,
    title="Nearest neighbors of the chipset security article",
    category_orders={"label": ["Other", "Nearest neighbor (top 5)", "Source"]},
)
```

在晶片組安全的例子裡，完整 embedding 空間中最近的 4 個鄰居，在壓縮後的 2D 視覺化裡仍然是最近鄰。第 5 個雖然在完整 embedding 空間裡比較近，卻被畫得比較遠。

如果你想要，也可以用函式 `chart_from_components_3D` 畫互動式的 3D embedding 圖。（這需要用 `n_components=3` 重新計算 t-SNE 成分。）

## 重點整理

- 推薦的核心就是算 embedding 之間的距離，離來源越近的越相似。
- embedding 要存快取，不然每次重算都要付費。
- 距離差距可以當信心指標，第 1 名遠比其他近時，通常推薦很準。
- 在複雜推薦系統裡，embedding 仍是很好的訊號，尤其解決冷啟動。
- t-SNE 把高維壓到 2D 會丟資訊，2D 圖上的鄰居不等於真實空間裡的鄰居。

## 練習

1. 把推薦的篇數從 5 改成 10，看看排名後段的文章還相不相關。
2. 換一篇來源文章（改索引），觀察距離分布，找一個第 1 名距離特別近和一個特別遠的例子。
3. 把 t-SNE 的 `n_components` 改成 3，用 `chart_from_components_3D` 畫出互動式 3D 圖，比較最近鄰在 3D 裡是否更貼近。
