---
translated: true
source: examples/Get_embeddings_from_dataset.ipynb
---

# 從資料集取得 embedding

> 原文：[examples/Get_embeddings_from_dataset.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Get_embeddings_from_dataset.ipynb)



## 這篇在做什麼
這本 notebook 示範怎麼從大型資料集取得 embedding。用的是 Amazon 的 fine-food 評論資料，把每則評論的標題和內文合併後編碼成單一向量，存起來供後續 notebook 重複使用。

## 學完你會
- 載入評論資料集並取最近 1000 筆當子集。
- 把評論的 Summary 和 Text 合併成單一文字，並用 tokenizer 檢查長度。
- 對整批資料取得 embedding，並存檔供之後重複使用。

## 開跑前
- 需要 OpenAI API key，取 embedding 會產生費用。
- 需要安裝：pandas、openai、transformers、plotly、matplotlib、scikit-learn、torch（transformer 的相依套件）、torchvision、scipy。

## 1. 載入資料集

這個範例用的資料集是 Amazon 的 [fine-food 評論](https://www.kaggle.com/snap/amazon-fine-food-reviews)，包含截至 2012 年 10 月 Amazon 使用者留下的 568,454 則食物評論。為了示範，我們只用其中最近的 1,000 則。評論是英文，傾向正面或負面。每則評論有 ProductId、UserId、Score、評論標題（Summary）和評論內文（Text）。

我們把評論標題和內文合併成單一文字。模型會對這段合併的文字編碼，輸出一個向量 embedding。

要跑這本 notebook，需要安裝：pandas、openai、transformers、plotly、matplotlib、scikit-learn、torch（transformer 的相依套件）、torchvision 和 scipy。

```python
import pandas as pd
import tiktoken

from utils.embeddings_utils import get_embedding
```

```python
embedding_model = "text-embedding-3-small"
embedding_encoding = "cl100k_base"
max_tokens = 8000  # the maximum for text-embedding-3-small is 8191
```

```python
# load & inspect dataset
input_datapath = "data/fine_food_reviews_1k.csv"  # to save space, we provide a pre-filtered dataset
df = pd.read_csv(input_datapath, index_col=0)
df = df[["Time", "ProductId", "UserId", "Score", "Summary", "Text"]]
df = df.dropna()
df["combined"] = (
    "Title: " + df.Summary.str.strip() + "; Content: " + df.Text.str.strip()
)
df.head(2)
```

??? note "輸出"

    ```text
             Time   ProductId          UserId  Score  \
    0  1351123200  B003XPF9BO  A3R7JR3FMEBXQB      5   
    1  1351123200  B003JK537S  A3JBPC3WFUT5ZP      1   

                                                 Summary  \
    0  where does one  start...and stop... with a tre...   
    1                                  Arrived in pieces   

                                                    Text  \
    0  Wanted to save some to bring to my Chicago fam...   
    1  Not pleased at all. When I opened the box, mos...   

                                                combined  
    0  Title: where does one  start...and stop... wit...  
    1  Title: Arrived in pieces; Content: Not pleased...
    ```

```python
# subsample to 1k most recent reviews and remove samples that are too long
top_n = 1000
df = df.sort_values("Time").tail(top_n * 2)  # first cut to first 2k entries, assuming less than half will be filtered out
df.drop("Time", axis=1, inplace=True)

encoding = tiktoken.get_encoding(embedding_encoding)

# omit reviews that are too long to embed
df["n_tokens"] = df.combined.apply(lambda x: len(encoding.encode(x)))
df = df[df.n_tokens <= max_tokens].tail(top_n)
len(df)
```

??? note "輸出"

    ```text
    1000
    ```

## 2. 取得 embedding 並存檔供之後重複使用

```python
# Ensure you have your API key set in your environment per the README: https://github.com/openai/openai-python#usage

# This may take a few minutes
df["embedding"] = df.combined.apply(lambda x: get_embedding(x, model=embedding_model))
df.to_csv("data/fine_food_reviews_with_embeddings_1k.csv")
```

```python
a = get_embedding("hi", model=embedding_model)
```

## 重點整理
- 取 embedding 是一次性成本，存成檔案後，後面的實驗就不必重打 API。
- 評論標題和內文合併成一段文字再編碼，每則評論得到一個向量。
- 先用小子集示範，確認流程正確後再放大到整個資料集。
- 輸入長度受模型限制，所以要先用 tokenizer 檢查 token 數。

## 練習
1. 把子集大小從 1000 筆改成 200 筆，重跑並看耗時。
2. 把合併文字的格式改成只用 Text（不含 Summary），重新取 embedding 並存成另一個檔案。
3. 調整 token 長度的篩選門檻，看有多少評論會被排除。
