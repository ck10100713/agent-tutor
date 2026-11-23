---
translated: true
source: examples/Classification_using_embeddings.ipynb
---

# 用 embedding 做分類

> 原文：[examples/Classification_using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Classification_using_embeddings.ipynb)



## 這篇在做什麼
文字分類有很多做法，這篇示範用 embedding 做文字分類。對很多文字分類任務，我們看過 fine-tuned 模型表現比 embedding 更好，fine-tuned 分類的範例見 [Fine-tuned_classification.ipynb](Fine-tuned_classification.md)。另外也建議資料筆數要比 embedding 維度多，這裡沒有完全做到。

這個任務是根據食物評論文字的 embedding，預測評論分數（1 到 5）。接下來所有工作都把資料集切成訓練集和測試集，才能在沒看過的資料上實際評估表現。資料集來自 [Get_embeddings_from_dataset](Get_embeddings_from_dataset.md) 那篇。

## 學完你會
- 用評論的 embedding 訓練分類器，預測 1 到 5 星的分數。
- 在切開的測試集上評估準確度，並看各星等的表現。
- 判斷哪些分數比較好預測，以及為什麼。

## 開跑前
- 需要先跑完 Get_embeddings_from_dataset，產生帶 embedding 的資料集。


```python
import pandas as pd
import numpy as np
from ast import literal_eval

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

datafile_path = "data/fine_food_reviews_with_embeddings_1k.csv"

df = pd.read_csv(datafile_path)
df["embedding"] = df.embedding.apply(literal_eval).apply(np.array)  # convert string to array

# split data into train and test
X_train, X_test, y_train, y_test = train_test_split(
    list(df.embedding.values), df.Score, test_size=0.2, random_state=42
)

# train random forest classifier
clf = RandomForestClassifier(n_estimators=100)
clf.fit(X_train, y_train)
preds = clf.predict(X_test)
probas = clf.predict_proba(X_test)

report = classification_report(y_test, preds)
print(report)
```

??? note "輸出"

    ```text
                  precision    recall  f1-score   support

               1       0.90      0.45      0.60        20
               2       1.00      0.38      0.55         8
               3       1.00      0.18      0.31        11
               4       0.88      0.26      0.40        27
               5       0.76      1.00      0.86       134

        accuracy                           0.78       200
       macro avg       0.91      0.45      0.54       200
    weighted avg       0.81      0.78      0.73       200
    ```

可以看到模型已經相當不錯地學會區分各個類別。5 星評論整體表現最好，這不意外，因為它們在資料集中最多。

```python
from utils.embeddings_utils import plot_multiclass_precision_recall

plot_multiclass_precision_recall(probas, y_test, [1, 2, 3, 4, 5], clf)
```

??? note "輸出"

    ```text
    RandomForestClassifier() - Average precision score over all classes: 0.90
    ```

不意外的是，5 星和 1 星評論比較容易預測。也許資料更多時，2 到 4 星之間的細微差異能預測得更好，但人們在使用中間分數時，可能本來就比較主觀。

## 重點整理
- embedding 加上一個簡單分類器，就能做出不錯的文字分類。
- 資料量最多的類別（5 星）通常表現最好，類別不平衡會影響結果。
- 極端分數（1 星、5 星）比中間分數容易分，因為語意訊號比較明確。
- 追求更高準確度時，fine-tuned 模型往往比 embedding 更好。

## 練習
1. 調整訓練集和測試集的切分比例，看準確度怎麼變。
2. 只看 1 星和 5 星兩類，重做分類，比較準確度。
3. 把分類器換成另一種 scikit-learn 模型，比較各星等的表現。
