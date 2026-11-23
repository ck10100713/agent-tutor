---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/third_party/Visualizing_embeddings_in_Kangas.ipynb
---

# 用 Kangas 視覺化 embedding

> 原文：[examples/third_party/Visualizing_embeddings_in_Kangas.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/Visualizing_embeddings_in_Kangas.ipynb)



## 這篇在做什麼
這篇用 Jupyter Notebook 建立一個 Kangas DataGrid，裡面放資料以及把 embedding 投影到 2 維的結果。
資料是評論，embedding 每筆有 1536 個浮點數，最後可以在 notebook 裡直接互動檢視。

## 學完你會
- 安裝並匯入 Kangas，把含 embedding 的 CSV 讀成 DataGrid。
- 把一欄數字轉成正確型別的 Embedding 欄位，並存成 datagrid。
- 在 notebook 裡顯示每筆資料的 2D 投影，並依 Score 分組檢視。

## 開跑前
- 需要用 pip 安裝 `kangas`。
- 資料直接從 GitHub 讀取，需要網路連線。

## 什麼是 Kangas？

[Kangas](https://github.com/comet-ml/kangas/) 是一個開源、支援混合媒體、像 dataframe 的資料科學家工具，由 [Comet](https://comet.com/) 開發，這家公司致力於降低模型上線的阻力。

### 1. 安裝

先 pip 安裝 kangas，再匯入。

```python
%pip install kangas --quiet
```

```python
import kangas as kg
```

### 2. 建立 Kangas DataGrid

我們用原始資料和 embedding 建立一個 Kangas DataGrid。資料是一列一列的評論，embedding 是 1536 個浮點數。這個範例直接從 GitHub 取資料，這樣就算你不是在 OpenAI 的 repo 裡跑 notebook 也行。

用 Kangas 把 CSV 檔讀成 DataGrid，方便後續處理。

```python
data = kg.read_csv("https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/data/fine_food_reviews_with_embeddings_1k.csv")
```

??? note "輸出"

    ```text
    Loading CSV file 'fine_food_reviews_with_embeddings_1k.csv'...
    ```

    ```text
    1001it [00:00, 2412.90it/s]
    100%|████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 1000/1000 [00:00<00:00, 2899.16it/s]
    ```

可以看一下 CSV 檔的欄位：

```python
data.info()
```

??? note "輸出"

    ```text
    DataGrid (in memory)
        Name   : fine_food_reviews_with_embeddings_1k
        Rows   : 1,000
        Columns: 9
    #   Column                Non-Null Count DataGrid Type       
    --- -------------------- --------------- --------------------
    1   Column 1                       1,000 INTEGER             
    2   ProductId                      1,000 TEXT                
    3   UserId                         1,000 TEXT                
    4   Score                          1,000 INTEGER             
    5   Summary                        1,000 TEXT                
    6   Text                           1,000 TEXT                
    7   combined                       1,000 TEXT                
    8   n_tokens                       1,000 INTEGER             
    9   embedding                      1,000 TEXT
    ```

再看看第一筆和最後一筆資料：

```python
data
```

??? note "輸出"

    ```text
    <th colspan='1' >          row-id </th> <th colspan='1' >        Column 1 </th> <th colspan='1' >       ProductId </th> <th colspan='1' >          UserId </th> <th colspan='1' >           Score </th> <th colspan='1' >         Summary </th> <th colspan='1' >            Text </th> <th colspan='1' >        combined </th> <th colspan='1' >        n_tokens </th> <th colspan='1' >       embedding </th> <tr>
    <td colspan='1' >               1 </td> <td colspan='1' >               0 </td> <td colspan='1' >      B003XPF9BO </td> <td colspan='1' >  A3R7JR3FMEBXQB </td> <td colspan='1' >               5 </td> <td colspan='1' > where does one  </td> <td colspan='1' > Wanted to save  </td> <td colspan='1' > Title: where do </td> <td colspan='1' >              52 </td> <td colspan='1' > [0.007018072064 </td> <tr>
    <td colspan='1' >               2 </td> <td colspan='1' >             297 </td> <td colspan='1' >      B003VXHGPK </td> <td colspan='1' >  A21VWSCGW7UUAR </td> <td colspan='1' >               4 </td> <td colspan='1' > Good, but not W </td> <td colspan='1' > Honestly, I hav </td> <td colspan='1' > Title: Good, bu </td> <td colspan='1' >             178 </td> <td colspan='1' > [-0.00314055196 </td> <tr>
    <td colspan='1' >               3 </td> <td colspan='1' >             296 </td> <td colspan='1' >      B008JKTTUA </td> <td colspan='1' >  A34XBAIFT02B60 </td> <td colspan='1' >               1 </td> <td colspan='1' > Should advertis </td> <td colspan='1' > First, these sh </td> <td colspan='1' > Title: Should a </td> <td colspan='1' >              78 </td> <td colspan='1' > [-0.01757248118 </td> <tr>
    <td colspan='1' >               4 </td> <td colspan='1' >             295 </td> <td colspan='1' >      B000LKTTTW </td> <td colspan='1' >  A14MQ40CCU8B13 </td> <td colspan='1' >               5 </td> <td colspan='1' > Best tomato sou </td> <td colspan='1' > I have a hard t </td> <td colspan='1' > Title: Best tom </td> <td colspan='1' >             111 </td> <td colspan='1' > [-0.00139322795 </td> <tr>
    <td colspan='1' >               5 </td> <td colspan='1' >             294 </td> <td colspan='1' >      B001D09KAM </td> <td colspan='1' >  A34XBAIFT02B60 </td> <td colspan='1' >               1 </td> <td colspan='1' > Should advertis </td> <td colspan='1' > First, these sh </td> <td colspan='1' > Title: Should a </td> <td colspan='1' >              78 </td> <td colspan='1' > [-0.01757248118 </td> <tr>
    ...
    <td colspan='1' >             996 </td> <td colspan='1' >             623 </td> <td colspan='1' >      B0000CFXYA </td> <td colspan='1' >  A3GS4GWPIBV0NT </td> <td colspan='1' >               1 </td> <td colspan='1' > Strange inflamm </td> <td colspan='1' > Truthfully wasn </td> <td colspan='1' > Title: Strange  </td> <td colspan='1' >             110 </td> <td colspan='1' > [0.000110913533 </td> <tr>
    <td colspan='1' >             997 </td> <td colspan='1' >             624 </td> <td colspan='1' >      B0001BH5YM </td> <td colspan='1' >   A1BZ3HMAKK0NC </td> <td colspan='1' >               5 </td> <td colspan='1' > My favorite and </td> <td colspan='1' > You've just got </td> <td colspan='1' > Title: My favor </td> <td colspan='1' >              80 </td> <td colspan='1' > [-0.02086931467 </td> <tr>
    <td colspan='1' >             998 </td> <td colspan='1' >             625 </td> <td colspan='1' >      B0009ET7TC </td> <td colspan='1' >  A2FSDQY5AI6TNX </td> <td colspan='1' >               5 </td> <td colspan='1' > My furbabies LO </td> <td colspan='1' > Shake the conta </td> <td colspan='1' > Title: My furba </td> <td colspan='1' >              47 </td> <td colspan='1' > [-0.00974910240 </td> <tr>
    <td colspan='1' >             999 </td> <td colspan='1' >             619 </td> <td colspan='1' >      B007PA32L2 </td> <td colspan='1' >  A15FF2P7RPKH6G </td> <td colspan='1' >               5 </td> <td colspan='1' > got this for th </td> <td colspan='1' > all i have hear </td> <td colspan='1' > Title: got this </td> <td colspan='1' >              50 </td> <td colspan='1' > [-0.00521062919 </td> <tr>
    <td colspan='1' >            1000 </td> <td colspan='1' >             999 </td> <td colspan='1' >      B001EQ5GEO </td> <td colspan='1' >  A3VYU0VO6DYV6I </td> <td colspan='1' >               5 </td> <td colspan='1' > I love Maui Cof </td> <td colspan='1' > My first experi </td> <td colspan='1' > Title: I love M </td> <td colspan='1' >             118 </td> <td colspan='1' > [-0.00605782261 </td> <tr>
    <tr>
    <td colspan='10' style="text-align: left;"> [1000 rows x 9 columns] </td> <tr>

    *  Use DataGrid.save() to save to disk
    ** Use DataGrid.show() to start user interface
    ```

現在建立一個新的 DataGrid，把數字轉成 Embedding：

```python
import ast # to convert string of a list of numbers into a list of numbers

dg = kg.DataGrid(
    name="openai_embeddings",
    columns=data.get_columns(),
    converters={"Score": str},
)
for row in data:
    embedding = ast.literal_eval(row[8])
    row[8] = kg.Embedding(
        embedding, 
        name=str(row[3]), 
        text="%s - %.10s" % (row[3], row[4]),
        projection="umap",
    )
    dg.append(row)
```

新的 DataGrid 現在有了型別正確的 Embedding 欄位。

```python
dg.info()
```

??? note "輸出"

    ```text
    DataGrid (in memory)
        Name   : openai_embeddings
        Rows   : 1,000
        Columns: 9
    #   Column                Non-Null Count DataGrid Type       
    --- -------------------- --------------- --------------------
    1   Column 1                       1,000 INTEGER             
    2   ProductId                      1,000 TEXT                
    3   UserId                         1,000 TEXT                
    4   Score                          1,000 TEXT                
    5   Summary                        1,000 TEXT                
    6   Text                           1,000 TEXT                
    7   combined                       1,000 TEXT                
    8   n_tokens                       1,000 INTEGER             
    9   embedding                      1,000 EMBEDDING-ASSET
    ```

把 datagrid 存起來就完成了。

```python
dg.save()
```

### 3. 顯示 2D 投影

要在 notebook 裡直接顯示資料，只要 show 它就好。注意每一列都有一個 embedding 投影。

往最右邊捲動可以看到每列的 embedding 投影。

投影空間中點的顏色代表 Score。

```python
dg.show()
```

??? note "輸出"

    ```text
    <IPython.lib.display.IFrame at 0x7fcdd16bfbe0>
    ```

依「Score」分組，可以看每一組有哪些資料列。

```python
dg.show(group="Score", sort="Score", rows=5, select="Score,embedding")
```

??? note "輸出"

    ```text
    <IPython.lib.display.IFrame at 0x7fcd06209180>
    ```

這個 datagrid 的範例託管在這裡：https://kangas.comet.com/?datagrid=/data/openai_embeddings.datagrid

## 重點整理
- 高維 embedding 很難直接看，投影到 2D 後才能目視檢查資料的群聚。
- DataGrid 讓資料和 embedding 放在同一個表，一邊看原文一邊看分佈。
- 欄位要轉成 Embedding 型別，Kangas 才知道要做投影。
- 依標籤（這裡是 Score）上色或分組，能快速判斷 embedding 有沒有把類別分開。

## 練習
1. 把 DataGrid 存成不同的檔名，重新載入確認資料還在。
2. 改成依其他欄位分組顯示，看看群聚的樣子有沒有不同。
3. 只取 CSV 前 1000 列建 DataGrid，比較投影圖的樣貌和載入速度。
