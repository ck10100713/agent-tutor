---
translated: true
source: examples/Regression_using_embeddings.ipynb
---

# 用 embedding 做迴歸

> 原文：[examples/Regression_using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Regression_using_embeddings.ipynb)



## 這篇在做什麼

用評論文字的 embedding 當特徵，訓練迴歸模型去預測 1 到 5 的評分。資料切成訓練集跟測試集，用沒看過的資料評估模型到底準不準。

## 學完你會

- 知道迴歸是預測數字，跟分類（預測類別）的差別。
- 用 embedding 當輸入特徵，訓練一個預測評論分數的模型。
- 用平均誤差判斷預測結果好不好。

## 開跑前

需要先照 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md) 產生帶 embedding 的資料集。

## 用 embedding 做迴歸

迴歸是預測一個數字，而不是預測屬於哪個類別。我們會根據評論文字的 embedding 來預測分數。接下來所有任務都把資料集切成訓練集跟測試集，這樣才能實際評估模型在沒看過的資料上的表現。資料集是在 [Get_embeddings_from_dataset Notebook](Get_embeddings_from_dataset.md) 裡建立的。

我們要預測的是評論的分數，是 1 到 5 之間的數字（1 星代表負評，5 星代表好評）。

```python
import pandas as pd
import numpy as np
from ast import literal_eval

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error

datafile_path = "data/fine_food_reviews_with_embeddings_1k.csv"

df = pd.read_csv(datafile_path)
df["embedding"] = df.embedding.apply(literal_eval).apply(np.array)

X_train, X_test, y_train, y_test = train_test_split(list(df.embedding.values), df.Score, test_size=0.2, random_state=42)

rfr = RandomForestRegressor(n_estimators=100)
rfr.fit(X_train, y_train)
preds = rfr.predict(X_test)

mse = mean_squared_error(y_test, preds)
mae = mean_absolute_error(y_test, preds)

print(f"text-embedding-3-small performance on 1k Amazon reviews: mse={mse:.2f}, mae={mae:.2f}")
```

??? note "輸出"

    ```text
    text-embedding-3-small performance on 1k Amazon reviews: mse=0.65, mae=0.52
    ```

```python
bmse = mean_squared_error(y_test, np.repeat(y_test.mean(), len(y_test)))
bmae = mean_absolute_error(y_test, np.repeat(y_test.mean(), len(y_test)))
print(
    f"Dummy mean prediction performance on Amazon reviews: mse={bmse:.2f}, mae={bmae:.2f}"
)
```

??? note "輸出"

    ```text
    Dummy mean prediction performance on Amazon reviews: mse=1.73, mae=1.03
    ```

結果顯示，embedding 預測分數的平均誤差是每次預測 0.53。大致相當於一半的評論預測得完全正確，另一半差一顆星。

你也可以訓練分類器來預測標籤，或是把 embedding 放進現有的機器學習模型，用來編碼自由文字特徵。

## 重點整理

- 迴歸預測的是數字，這裡是 1 到 5 的評分，不是類別。
- embedding 可以直接當特徵餵給傳統的機器學習模型。
- 一定要切訓練集跟測試集，在沒看過的資料上評估才可信。
- 平均誤差 0.53 約等於一半預測全對、一半差一星。
- 同樣的 embedding 也能拿去訓練分類器，或編碼其他模型的文字特徵。

## 練習

1. 把訓練集跟測試集的切分比例改一下（例如 test_size 改成 0.3），看平均誤差怎麼變。
2. 把迴歸模型換成另一種（例如換 Ridge 或其他 sklearn 模型），比較平均誤差。
3. 把預測值四捨五入成整數，算有多少比例的評論預測完全正確，驗證「約一半預測全對」這個說法。
