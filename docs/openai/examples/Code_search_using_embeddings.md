---
translated: true
source: examples/Code_search_using_embeddings.ipynb
---

# 用 embedding 做程式碼搜尋

> 原文：[examples/Code_search_using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Code_search_using_embeddings.ipynb)



## 這篇在做什麼
這篇示範怎麼用 embedding 做語意式的程式碼搜尋。範例對象是我們自己的 [openai-python 程式庫](https://github.com/openai/openai-python)。
我們寫了一個簡單版的檔案解析器，從 Python 檔案裡抽出 function，再做 embedding、建索引和查詢。

## 學完你會
- 寫解析函式，從整個程式庫抽出每個 function 的程式碼和資訊。
- 用 `text-embedding-3-small` 替這些 function 取得 embedding。
- 用自然語言描述搜尋 function，靠 cosine similarity 排序找出最相關的結果。

## 開跑前
- 需要 OpenAI API key，embedding 會產生少量費用。
- 需要本機有 openai-python 程式庫的資料夾可以讀。

## 輔助函式

先寫幾個簡單的解析函式，讓我們從程式庫抽出重要資訊。

```python
import pandas as pd
from pathlib import Path

DEF_PREFIXES = ['def ', 'async def ']
NEWLINE = '\n'

def get_function_name(code):
    """
    Extract function name from a line beginning with 'def' or 'async def'.
    """
    for prefix in DEF_PREFIXES:
        if code.startswith(prefix):
            return code[len(prefix): code.index('(')]


def get_until_no_space(all_lines, i):
    """
    Get all lines until a line outside the function definition is found.
    """
    ret = [all_lines[i]]
    for j in range(i + 1, len(all_lines)):
        if len(all_lines[j]) == 0 or all_lines[j][0] in [' ', '\t', ')']:
            ret.append(all_lines[j])
        else:
            break
    return NEWLINE.join(ret)


def get_functions(filepath):
    """
    Get all functions in a Python file.
    """
    with open(filepath, 'r') as file:
        all_lines = file.read().replace('\r', NEWLINE).split(NEWLINE)
        for i, l in enumerate(all_lines):
            for prefix in DEF_PREFIXES:
                if l.startswith(prefix):
                    code = get_until_no_space(all_lines, i)
                    function_name = get_function_name(code)
                    yield {
                        'code': code,
                        'function_name': function_name,
                        'filepath': filepath,
                    }
                    break


def extract_functions_from_repo(code_root):
    """
    Extract all .py functions from the repository.
    """
    code_files = list(code_root.glob('**/*.py'))

    num_files = len(code_files)
    print(f'Total number of .py files: {num_files}')

    if num_files == 0:
        print('Verify openai-python repo exists and code_root is set correctly.')
        return None

    all_funcs = [
        func
        for code_file in code_files
        for func in get_functions(str(code_file))
    ]

    num_funcs = len(all_funcs)
    print(f'Total number of functions extracted: {num_funcs}')

    return all_funcs
```


接著載入 openai-python 資料夾，用上面定義的函式抽出需要的資訊。

```python
# Set user root directory to the 'openai-python' repository
root_dir = Path.home()

# Assumes the 'openai-python' repository exists in the user's root directory
code_root = root_dir / 'openai-python'

# Extract all functions from the repository
all_funcs = extract_functions_from_repo(code_root)
```

??? note "輸出"

    ```text
    Total number of .py files: 51
    Total number of functions extracted: 97
    ```

拿到內容之後，把資料送給 `text-embedding-3-small` 模型，取回向量 embedding。

```python
from utils.embeddings_utils import get_embedding

df = pd.DataFrame(all_funcs)
df['code_embedding'] = df['code'].apply(lambda x: get_embedding(x, model='text-embedding-3-small'))
df['filepath'] = df['filepath'].map(lambda x: Path(x).relative_to(code_root))
df.to_csv("data/code_search_openai-python.csv", index=False)
df.head()
```

??? note "輸出"

    ```text
                                                    code       function_name  \
    0  def _console_log_level():\n    if openai.log i...  _console_log_level   
    1  def log_debug(message, **params):\n    msg = l...           log_debug   
    2  def log_info(message, **params):\n    msg = lo...            log_info   
    3  def log_warn(message, **params):\n    msg = lo...            log_warn   
    4  def logfmt(props):\n    def fmt(key, val):\n  ...              logfmt   

             filepath                                     code_embedding  
    0  openai/util.py  [0.005937571171671152, 0.05450401455163956, 0....  
    1  openai/util.py  [0.017557814717292786, 0.05647840350866318, -0...  
    2  openai/util.py  [0.022524144500494003, 0.06219055876135826, -0...  
    3  openai/util.py  [0.030524108558893204, 0.0667714849114418, -0....  
    4  openai/util.py  [0.05337328091263771, 0.03697286546230316, -0....
    ```

### 測試

用幾個簡單查詢來測試。如果你熟悉 `openai-python` 這個 repo，會發現只要一句簡單的英文描述，就能輕鬆找到想要的 function。

我們定義了 search_functions 方法，它接收含 embedding 的資料、查詢字串和一些設定選項。搜尋流程如下：

1. 先用 `text-embedding-3-small` 對查詢字串（code_query）取 embedding。原因是「a function that reverses a string」這樣的查詢和「def reverse(string): return string[::-1]」這樣的 function，取完 embedding 後會非常相近。
2. 再計算查詢字串 embedding 與資料庫中所有資料點之間的 cosine similarity，得到每個點和查詢的距離。
3. 最後依距離排序，回傳 function 參數指定的結果數量。

```python
from utils.embeddings_utils import cosine_similarity

def search_functions(df, code_query, n=3, pprint=True, n_lines=7):
    embedding = get_embedding(code_query, model='text-embedding-3-small')
    df['similarities'] = df.code_embedding.apply(lambda x: cosine_similarity(x, embedding))

    res = df.sort_values('similarities', ascending=False).head(n)

    if pprint:
        for r in res.iterrows():
            print(f"{r[1].filepath}:{r[1].function_name}  score={round(r[1].similarities, 3)}")
            print("\n".join(r[1].code.split("\n")[:n_lines]))
            print('-' * 70)

    return res
```

```python
res = search_functions(df, 'fine-tuning input data validation logic', n=3)
```

??? note "輸出"

    ```text
    openai/validators.py:format_inferrer_validator  score=0.453
    def format_inferrer_validator(df):
        """
        This validator will infer the likely fine-tuning format of the data, and display it to the user if it is classification.
        It will also suggest to use ada and explain train/validation split benefits.
        """
        ft_type = infer_task_type(df)
        immediate_msg = None
    ----------------------------------------------------------------------
    openai/validators.py:infer_task_type  score=0.37
    def infer_task_type(df):
        """
        Infer the likely fine-tuning task type from the data
        """
        CLASSIFICATION_THRESHOLD = 3  # min_average instances of each class
        if sum(df.prompt.str.len()) == 0:
            return "open-ended generation"
    ----------------------------------------------------------------------
    openai/validators.py:apply_validators  score=0.369
    def apply_validators(
        df,
        fname,
        remediation,
        validators,
        auto_accept,
        write_out_file_func,
    ----------------------------------------------------------------------
    ```

```python
res = search_functions(df, 'find common suffix', n=2, n_lines=10)
```

??? note "輸出"

    ```text
    openai/validators.py:get_common_xfix  score=0.487
    def get_common_xfix(series, xfix="suffix"):
        """
        Finds the longest common suffix or prefix of all the values in a series
        """
        common_xfix = ""
        while True:
            common_xfixes = (
                series.str[-(len(common_xfix) + 1) :]
                if xfix == "suffix"
                else series.str[: len(common_xfix) + 1]
    ----------------------------------------------------------------------
    openai/validators.py:common_completion_suffix_validator  score=0.449
    def common_completion_suffix_validator(df):
        """
        This validator will suggest to add a common suffix to the completion if one doesn't already exist in case of classification or conditional generation.
        """
        error_msg = None
        immediate_msg = None
        optional_msg = None
        optional_fn = None

        ft_type = infer_task_type(df)
    ----------------------------------------------------------------------
    ```

```python
res = search_functions(df, 'Command line interface for fine-tuning', n=1, n_lines=20)
```

??? note "輸出"

    ```text
    openai/cli.py:tools_register  score=0.391
    def tools_register(parser):
        subparsers = parser.add_subparsers(
            title="Tools", help="Convenience client side tools"
        )

        def help(args):
            parser.print_help()

        parser.set_defaults(func=help)

        sub = subparsers.add_parser("fine_tunes.prepare_data")
        sub.add_argument(
            "-f",
            "--file",
            required=True,
            help="JSONL, JSON, CSV, TSV, TXT or XLSX file containing prompt-completion examples to be analyzed."
            "This should be the local file path.",
        )
        sub.add_argument(
            "-q",
    ----------------------------------------------------------------------
    ```

## 重點整理
- 程式碼和自然語言可以放進同一個 embedding 空間，所以能用英文描述找 function。
- 搜尋流程是：查詢取 embedding、算相似度、排序取前幾名。
- 切分粒度是關鍵，這裡以 function 為單位，每個結果就是一段完整可讀的程式。
- embedding 只需建一次，之後每次查詢只多一次查詢字串的 embedding 呼叫。

## 練習
1. 換幾個不同描述的查詢（例如「處理 API 錯誤的 function」），看前幾名結果合不合理。
2. 調整 search_functions 回傳的結果數量，觀察排名後面的結果相關性怎麼下降。
3. 把解析函式改成連 class 或 method 也一起抽出來，重新做 embedding，比較搜尋結果。
