---
translated: true
source: misc/how_to_make_sql_queries.ipynb
---

# 用 Claude 產生 SQL 查詢

> 原文：[misc/how_to_make_sql_queries.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/how_to_make_sql_queries.ipynb)

把資料庫 schema 當 context 給 Claude，讓它把自然語言問題轉成 SQL 查詢。

## 這篇在做什麼

建一個 SQLite 測試資料庫，把 schema 整理成字串連同問題一起傳給 Claude，讓它產生 SQL。最後實際執行產生的查詢並印出結果。

## 學完你會

- 從 SQLite 讀出 schema 並格式化成 prompt 能用的字串
- 寫一個函式，把自然語言問題送給 Claude 並取回 SQL
- 在測試資料庫上執行產生的 SQL，驗證結果

## 開跑前

- Anthropic API key

這份 notebook 示範怎麼用 Claude，根據自然語言問題產生 SQL 查詢。我們會建立測試資料庫、把 schema 提供給 Claude，並展示它怎麼把人類語言理解並翻成 SQL。

## 設定

先安裝需要的函式庫，並用 API key 設定 Anthropic client。

```python
# Install the necessary libraries
%pip install anthropic
```

```python
# Import the required libraries
import sqlite3

from anthropic import Anthropic

# Set up the Claude API client
client = Anthropic()
MODEL_NAME = "claude-opus-5-5"
```

## 建立測試資料庫

用 SQLite 建立測試資料庫，並填入範例資料：

```python
# Connect to the test database (or create it if it doesn't exist)
conn = sqlite3.connect("test_db.db")
cursor = conn.cursor()

# Create a sample table
cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY,
        name TEXT,
        department TEXT,
        salary INTEGER
    )
""")

# Insert sample data
sample_data = [
    (1, "John Doe", "Sales", 50000),
    (2, "Jane Smith", "Engineering", 75000),
    (3, "Mike Johnson", "Sales", 60000),
    (4, "Emily Brown", "Engineering", 80000),
    (5, "David Lee", "Marketing", 55000),
]
cursor.executemany("INSERT INTO employees VALUES (?, ?, ?, ?)", sample_data)
conn.commit()
```

## 用 Claude 產生 SQL 查詢

定義一個函式，把自然語言問題送給 Claude，取得產生的 SQL 查詢：

````python
# Define a function to send a query to Claude and get the response
def ask_claude(query, schema):
    prompt = f"""Here is the schema for a database:

{schema}

Given this schema, can you output a SQL query to answer the following question? Only output the SQL query and nothing else. Do not wrap it in a code block.

Question: {query}
"""

    response = client.messages.create(
        model=MODEL_NAME, max_tokens=2048, messages=[{"role": "user", "content": prompt}]
    )
    # The response can start with a thinking block, so read the text block rather than content[0].
    sql = next(block.text for block in response.content if block.type == "text").strip()
    # Strip a Markdown code fence if the model added one anyway.
    return sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
````

取出資料庫 schema，並格式化成字串：

```python
# Get the database schema
schema = cursor.execute("PRAGMA table_info(employees)").fetchall()
schema_str = (
    "CREATE TABLE EMPLOYEES (\n" + "\n".join([f"{col[1]} {col[2]}" for col in schema]) + "\n)"
)
print(schema_str)
```

??? note "輸出"

    ```text
    CREATE TABLE EMPLOYEES (
    id INTEGER
    name TEXT
    department TEXT
    salary INTEGER
    )
    ```

提供一個自然語言問題範例，送給 Claude：

```python
# Example natural language question
question = "What are the names and salaries of employees in the Engineering department?"
# Send the question to Claude and get the SQL query
sql_query = ask_claude(question, schema_str)
print(sql_query)
```

??? note "輸出"

    ```text
    SELECT name, salary
    FROM EMPLOYEES
    WHERE department = 'Engineering';
    ```

## 執行產生的 SQL 查詢

最後在測試資料庫上執行產生的 SQL 查詢，並印出結果：

```python
# Execute the SQL query and print the results
results = cursor.execute(sql_query).fetchall()

for row in results:
    print(row)
```

??? note "輸出"

    ```text
    ('Jane Smith', 75000)
    ('Emily Brown', 80000)
    ```

用完別忘了關閉資料庫連線：

```python
# Close the database connection
conn.close()
```

## 重點整理

- 把資料庫 schema 放進 prompt，Claude 才知道有哪些表和欄位可用
- 自然語言轉 SQL 的品質取決於 schema 的清楚程度和問題的明確度
- 產生的 SQL 要實際執行驗證，不要直接信任
- 這個流程的骨架是：取 schema、組 prompt、呼叫模型、執行查詢

## 練習

1. 換一個自然語言問題（例如加上 GROUP BY 的統計），看 Claude 產生的 SQL 對不對。
2. 在 prompt 裡要求 Claude 只輸出 SQL、不要附說明，再用程式把它乾淨地取出來執行。
3. 對產生的 SQL 加上檢查，只允許 SELECT 開頭，其他一律拒絕執行。
