---
translated: true
source: capabilities/classification/guide.ipynb
---
# 用 Claude 做分類

> 原文：[capabilities/classification/guide.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/classification/guide.ipynb)

用 Claude 搭配 RAG 和 chain-of-thought，為保險客服工單建立分類系統。

## 這篇在做什麼

把保險客服工單分成 10 個類別，一步步把準確率從約 70% 拉到 95% 以上。過程是先建一個隨機分類器當基準，再依序加上 prompt 設計、RAG（用向量資料庫撈相似範例）和 chain-of-thought，每一步都用同一組測試資料量化進步多少。

## 學完你會

- 用 XML 標籤和 stop sequence 寫出輸出格式穩定的 Claude 分類 prompt
- 用 VoyageAI embedding 和簡單的 `VectorDB` 撈出最相似的 5 個範例做 few-shot
- 寫評估函式和 confusion matrix，用數據比較不同 prompt 做法的效果

## 開跑前

- 需要 Anthropic API key。
- VoyageAI API key 是選配，因為 embedding 已經預先算好並有 cache。
- 在 Colab 上用 Secrets 設好 key，並在第一個 cell 用 `pip install` 裝套件即可。

在這份指南裡，你會建一個高準確率的分類系統，把保險客服工單分成 10 個類別。你會學到怎麼結合 prompt engineering、retrieval-augmented generation（RAG）和 chain-of-thought 推理，把分類準確率從 70% 逐步提升到 95% 以上。

讀完後，你會理解怎麼設計能處理複雜商業規則、在訓練資料有限時也能運作、並且提供可解釋結果的分類系統。

## 前置條件
- Python 3.11+，有基本使用經驗
- Anthropic API key（[在這裡申請](https://console.anthropic.com)）
- VoyageAI API key（選配，embedding 已預先算好）
- 了解分類問題

## 設定

先安裝需要的套件

- anthropic 
- voyageai
- pandas
- matplotlib
- sklearn
- numpy

我們也會從環境變數載入 API key，並設定模型名稱。

```python
%%capture
%pip install -U anthropic voyageai pandas numpy matplotlib scikit-learn
```

```python
# Setup our environment
import os

import anthropic

MODEL = "claude-haiku-5-5"
client = anthropic.Anthropic(
    # This is the default and can be omitted
    api_key=os.getenv("ANTHROPIC_API_KEY"),
)
```

## 用 Claude 做分類

大型語言模型（LLM）徹底改變了分類領域，尤其是傳統機器學習系統一直吃力的場景。LLM 在處理商業規則複雜、或訓練資料品質低或數量有限的分類問題上表現很好。另外，LLM 還能用自然語言解釋和說明它的判斷，讓分類過程更好理解、更透明。善用 LLM，我們可以建出超越傳統機器學習做法的分類系統，在資料稀少或商業需求複雜的情況下表現特別好。

在這份指南裡，我們會探討怎麼用 LLM 處理進階的分類任務，涵蓋以下重點元件和步驟：

1. **資料準備**：先準備訓練和測試資料。訓練資料用來建分類模型，測試資料用來評估表現。資料準備做得好，分類系統才會有效。

2. **Prompt Engineering**：Prompt engineering 對發揮 LLM 的分類能力很關鍵。我們會設計一個 prompt 模板，定義分類用 prompt 的結構和格式。模板會放入使用者查詢、類別定義，以及從向量資料庫撈出的相關範例。仔細設計 prompt，就能引導 LLM 產生準確又符合情境的分類。

3. **實作 Retrieval-Augmented Generation（RAG）**：為了加強分類，我們會用向量資料庫儲存訓練資料的 embedding 並有效率地檢索。向量資料庫支援相似度搜尋，讓我們能找到跟某個查詢最相關的範例。用撈出的範例擴充 LLM，可以提供額外的 context，提升分類的準確度。

4. **測試與評估**：分類系統建好後，我們會用轉換好的測試資料嚴格測試表現。我們會逐一走過測試查詢，用分類函式分類每一個，並把預測類別跟預期類別比對。分析分類結果，就能評估系統的成效並找出可以改進的地方。

## 問題定義：保險客服工單分類器

*註：這個範例的問題定義、資料和標籤都是 Claude 3 Opus 合成產生的*

在保險業，客服對維持客戶滿意度和留存很重要。保險公司每天會收到大量客服工單，主題涵蓋帳單、保單管理、理賠協助等等。人工分類這些工單既耗時又沒效率，會拉長回應時間，也可能影響客戶體驗。

#### 類別定義

1. Billing Inquiries（帳單詢問）
- 關於發票、費用、手續費和保費的問題
- 要求說明帳單內容
- 詢問付款方式和到期日

2. Policy Administration（保單管理）
- 要求變更、更新或取消保單
- 關於保單續約和恢復的問題
- 詢問新增或移除承保項目

3. Claims Assistance（理賠協助）
- 關於理賠流程和申請程序的問題
- 要求協助提交理賠文件
- 詢問理賠進度和賠付時間

4. Coverage Explanations（保障說明）
- 關於特定保單類型承保範圍的問題
- 要求說明保障上限和除外責任
- 詢問自付額和自費項目

5. Quotes and Proposals（報價與提案）
- 要求新保單的報價和價格比較
- 關於可用折扣和組合方案的問題
- 詢問從其他保險公司轉換

6. Account Management（帳戶管理）
- 要求登入憑證或重設密碼
- 關於線上帳戶功能的問題
- 詢問更新聯絡或個人資料

7. Billing Disputes（帳單爭議）
- 抱怨意外或錯誤的收費
- 要求退款或保費調整
- 詢問滯納金或催收通知

8. Claims Disputes（理賠爭議）
- 抱怨理賠被拒或賠不夠
- 要求重新考慮理賠決定
- 詢問如何申訴理賠結果

9. Policy Comparisons（保單比較）
- 關於各保單選項差異的問題
- 要求協助在不同保障等級中做選擇
- 詢問保單跟競爭對手的產品相比如何

10. General Inquiries（一般詢問）
- 關於公司聯絡方式或營業時間的問題
- 要求產品或服務的一般資訊
- 不太適合歸到其他類別的詢問

## 載入與準備資料

問題和類別都定義好了，接著載入有標籤的訓練和測試資料。我們會讀 TSV 檔，轉成結構化格式，並準備好評估用的測試集。

訓練資料有 68 個有標籤的範例，稍後會用在 retrieval-augmented generation（RAG）。測試集也有 68 個範例，用來評估各種分類做法。

我們會用這些資料集：
- `./data/test.tsv`
- `./data/train.tsv`

```python
import pandas as pd

data = {
    "train": [],
    "test": [],
}


# Helper function to convert a DataFrame to a list of dictionaries
def dataframe_to_dict_list(df):
    return df.apply(lambda x: {"text": x["text"], "label": x["label"]}, axis=1).tolist()


# Read the TSV file into a DataFrame
test_df = pd.read_csv("./data/test.tsv", sep="\t")
data["test"] = dataframe_to_dict_list(test_df)

train_df = pd.read_csv("./data/train.tsv", sep="\t")
data["train"] = dataframe_to_dict_list(train_df)


# Understand the labels in the dataset
labels = list(set(train_df["label"].unique()))

# Print the first training example and the number of training examples
print(data["train"][0], len(data["train"]))

# Create the test set
X_test = [example["text"] for example in data["test"]]
y_test = [example["label"] for example in data["test"]]

# Print the length of the test set
print(len(X_test), len(y_test))
```

??? note "輸出"

    ```text
    {'text': 'I just got my auto policy renewal bill and the cost seems to be more than what I usually pay. Could you explain the reason for the increase?', 'label': 'Billing Inquiries'} 68
    68 68
    ```

## 評估框架

在建分類器之前，先建立評估框架來衡量它們的表現。我們會建兩個關鍵函式：

1. **`evaluate(X, y, classifier, batch_size)`**：用並行執行在所有測試範例上跑你的分類器以加快速度，然後計算準確率指標並產生 confusion matrix。`batch_size` 參數控制同時發出多少個 API 請求。

2. **`plot_confusion_matrix(cm, labels)`**：把 confusion matrix 畫出來，顯示哪些類別互相被搞混，幫助找出分類器卡在哪。

這個框架讓我們能用實證比較不同的分類做法，不只看整體準確率，也看哪些類別特別難。

**Rate Limits**：`MAXIMUM_CONCURRENT_REQUESTS` 預設是 1。如果你的使用額度層級比較高，可以調高這個值來加快評估。各層級的限制見 [rate limits 文件](https://docs.claude.com/en/api/rate-limits)。

```python
import concurrent.futures

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import classification_report, confusion_matrix

MAXIMUM_CONCURRENT_REQUESTS = 5


def plot_confusion_matrix(cm, labels):
    # Visualize the confusion matrix
    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(cm, cmap="Blues")

    # Add colorbar
    ax.figure.colorbar(im, ax=ax)

    # Set tick labels and positions
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)

    # Add labels to each cell
    thresh = cm.max() / 2.0
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(
                j,
                i,
                cm[i, j],
                ha="center",
                va="center",
                color="white" if cm[i, j] > thresh else "black",
            )

    # Set labels and title
    plt.xlabel("Predicted Labels")
    plt.ylabel("True Labels")
    plt.title("Confusion Matrix")
    plt.tight_layout()
    plt.show()


def evaluate(X, y, classifier, batch_size=MAXIMUM_CONCURRENT_REQUESTS):
    # Initialize lists to store the predicted and true labels
    y_true = []
    y_pred = []

    # Store results with their original index to maintain order
    results = [None] * len(X)

    # Create a ThreadPoolExecutor with limited workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
        # Submit tasks one at a time, but executor will only run batch_size concurrently
        future_to_index = {executor.submit(classifier, x): i for i, x in enumerate(X)}

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            predicted_label = future.result()
            results[index] = predicted_label

    # Extract predictions and true labels in order
    y_pred = results
    y_true = y

    # Normalize y_true and y_pred
    y_true = [label.strip() for label in y_true]
    y_pred = [label.strip() for label in y_pred]

    # Calculate the classification metrics
    report = classification_report(y_true, y_pred, labels=labels, zero_division=1)
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    print(report)
    plot_confusion_matrix(cm, labels)
```

## 基準：隨機分類器

為了建立效能基準並確認評估框架運作正常，先從一個對每張工單隨機挑類別的隨機分類器開始。

這給出表現的下界：任何真正的分類做法都該明顯贏過亂猜（10 個類別大約會得到 10% 的準確率）。這個基準幫我們量化 context engineering 實際加了多少價值。

```python
import random


def random_classifier(text):
    return random.choice(labels)
```

```python
print("Evaluating the random classification method on the test set...")
evaluate(X_test, y_test, random_classifier)
```

??? note "輸出"

    ```text
    Evaluating the random classification method on the test set...
                           precision    recall  f1-score   support

        Claims Assistance       0.14      0.17      0.15         6
     Quotes and Proposals       0.40      0.40      0.40         5
          Claims Disputes       0.38      0.33      0.35         9
    Coverage Explanations       0.29      0.22      0.25         9
         Billing Disputes       0.20      0.11      0.14         9
    Policy Administration       0.25      0.33      0.29         6
        Billing Inquiries       0.00      0.00      0.00         6
        General Inquiries       0.00      0.00      0.00         7
       Policy Comparisons       0.00      0.00      0.00         5
       Account Management       0.00      0.00      0.00         6

                 accuracy                           0.16        68
                macro avg       0.17      0.16      0.16        68
             weighted avg       0.18      0.16      0.17        68
    ```

跟隨機亂猜預期的一樣，confusion matrix 顯示預測散布在所有類別，沒有任何有意義的規律。對角線（預測正確）每個類別只有 1 到 4 個正確分類，錯誤則隨機分布。

這確認了大約 10% 的準確率基準，也就是 10 個類別下純粹靠運氣的表現。任何有結構的分類做法，對角線都該明顯強很多，代表模型真的在學類別間的差異，而不是亂猜。

### 簡單分類測試

現在用 Claude 建一個簡單的分類器。

首先把類別編碼成 XML 格式，這樣 Claude 比較容易解讀資訊。用 XML 編碼資訊是通用的 prompting 策略，更多資訊[見這裡](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags)

```python
import textwrap

categories = textwrap.dedent("""<category>
    <label>Billing Inquiries</label>
    <content> Questions about invoices, charges, fees, and premiums Requests for clarification on billing statements Inquiries about payment methods and due dates
    </content>
</category>
<category>
    <label>Policy Administration</label>
    <content> Requests for policy changes, updates, or cancellations Questions about policy renewals and reinstatements Inquiries about adding or removing coverage options
    </content>
</category>
<category>
    <label>Claims Assistance</label>
    <content> Questions about the claims process and filing procedures Requests for help with submitting claim documentation Inquiries about claim status and payout timelines
    </content>
</category>
<category>
    <label>Coverage Explanations</label>
    <content> Questions about what is covered under specific policy types Requests for clarification on coverage limits and exclusions Inquiries about deductibles and out-of-pocket expenses
    </content>
</category>
<category>
    <label>Quotes and Proposals</label>
    <content> Requests for new policy quotes and price comparisons Questions about available discounts and bundling options Inquiries about switching from another insurer
    </content>
</category>
<category>
    <label>Account Management</label>
    <content> Requests for login credentials or password resets Questions about online account features and functionality Inquiries about updating contact or personal information
    </content>
</category>
<category>
    <label>Billing Disputes</label>
    <content> Complaints about unexpected or incorrect charges Requests for refunds or premium adjustments Inquiries about late fees or collection notices
    </content>
</category>
<category>
    <label>Claims Disputes</label>
    <content> Complaints about denied or underpaid claims Requests for reconsideration of claim decisions Inquiries about appealing a claim outcome
    </content>
</category>
<category>
    <label>Policy Comparisons</label>
    <content> Questions about the differences between policy options Requests for help deciding between coverage levels Inquiries about how policies compare to competitors' offerings
    </content>
</category>
<category>
    <label>General Inquiries</label>
    <content> Questions about company contact information or hours of operation Requests for general information about products or services Inquiries that don't fit neatly into other categories
    </content>
</category>""")
```

## 建立簡單分類器

現在用 Claude 建第一個真正的分類器。`simple_classify` 函式示範三個關鍵的 prompt engineering 技巧：

1. **結構化的 prompt 模板**：用清楚的 XML 格式提供類別定義和客服工單，讓 Claude 容易解析。

2. **用標籤加 stop sequence 控制輸出**：Prompt 要求 Claude 把標籤放在 `<category>` 標籤之間，我們設定 `stop_sequences=["</category>"]`，讓 Claude 在標籤之後馬上停下來。然後我們取回應 text block 裡 `<category>` 後面的內容，解析因此很可靠。

3. **預設取樣**：目前的 Claude 模型（包含 Claude Haiku 5.5）不接受 `temperature`、`top_p` 或 `top_k`，所以取樣維持預設值。受限的輸出格式讓預測保持一致。

```python
def simple_classify(X):
    prompt = (
        textwrap.dedent("""
    You will classify a customer support ticket into one of the following categories:
    <categories>
        {{categories}}
    </categories>

    Here is the customer support ticket:
    <ticket>
        {{ticket}}
    </ticket>

    Respond with just the label of the category between category tags.
    """)
        .replace("{{categories}}", categories)
        .replace("{{ticket}}", X)
    )
    response = client.messages.create(
        messages=[{"role": "user", "content": prompt}],
        stop_sequences=["</category>"],
        max_tokens=4096,
        model=MODEL,
    )

    # The reply is "<category>Label" (the stop sequence trims the closing tag) and may be
    # preceded by a thinking block, so read only the text blocks and take what follows the tag.
    text = "".join(b.text for b in response.content if b.type == "text")
    return text.split("<category>")[-1].strip()
```

```python
print("Evaluating the simple classification method on the test set...")
evaluate(X_test, y_test, simple_classify)
```

??? note "輸出"

    ```text
    Evaluating the simple classification method on the test set...
                           precision    recall  f1-score   support

        Claims Assistance       1.00      0.67      0.80         6
     Quotes and Proposals       1.00      0.60      0.75         5
          Claims Disputes       1.00      1.00      1.00         9
    Coverage Explanations       0.53      1.00      0.69         9
         Billing Disputes       0.67      0.67      0.67         9
    Policy Administration       0.71      0.83      0.77         6
        Billing Inquiries       0.50      0.50      0.50         6
        General Inquiries       1.00      0.00      0.00         7
       Policy Comparisons       0.71      1.00      0.83         5
       Account Management       1.00      1.00      1.00         6

                 accuracy                           0.74        68
                macro avg       0.81      0.73      0.70        68
             weighted avg       0.80      0.74      0.70        68
    ```

好多了！Confusion matrix 顯示明顯的對角線，大多數類別都達到很高的準確率。

這個約 70% 的整體準確率明顯贏過隨機亂猜，但相近類別之間的混淆顯示 Claude 需要更多 context 才能做更細的區分。

為了解決這些混淆，我們加入 **retrieval-augmented generation（RAG）**，把訓練資料裡相關的範例提供給 Claude。運作方式如下：

1. **對訓練範例做 embedding**：用 VoyageAI 的 embedding 模型把全部 68 張訓練工單轉成向量 embedding
2. **語意搜尋**：對每張新工單，依 cosine similarity 找出最相似的 5 個訓練範例
3. **擴充 prompt**：把這些相似範例放進分類 prompt 來引導 Claude

這個做法對分類特別有效，因為：
- 相似的過去範例幫 Claude 區分語意相近的類別
- Few-shot learning 不用 fine-tuning 就能提升準確率
- 檢索是動態的，每個查詢都拿到最相關的範例

我們會建一個簡單的 `VectorDB` class 來處理 embedding 儲存和相似度搜尋，用的是 [VoyageAI 的 embedding 模型](https://docs.claude.com/en/docs/embeddings)。

```python
import json
import os
import pickle

import numpy as np
import voyageai


class VectorDB:
    def __init__(self, api_key=None):
        if api_key is None:
            api_key = os.getenv("VOYAGE_API_KEY")
        self.client = voyageai.Client(api_key=api_key)
        self.embeddings = []
        self.metadata = []
        self.query_cache = {}
        self.db_path = "./data/vector_db.pkl"

    def load_data(self, data):
        # Check if the vector database is already loaded
        if self.embeddings and self.metadata:
            print("Vector database is already loaded. Skipping data loading.")
            return
        # Check if vector_db.pkl exists
        if os.path.exists(self.db_path):
            print("Loading vector database from disk.")
            self.load_db()
            return

        texts = [item["text"] for item in data]

        # Embed more than 128 documents with a for loop
        batch_size = 128
        result = [
            self.client.embed(texts[i : i + batch_size], model="voyage-2").embeddings
            for i in range(0, len(texts), batch_size)
        ]

        # Flatten the embeddings
        self.embeddings = [embedding for batch in result for embedding in batch]
        self.metadata = [item for item in data]
        self.save_db()
        # Save the vector database to disk
        print("Vector database loaded and saved.")

    def search(self, query, k=5, similarity_threshold=0.75):
        query_embedding = None
        if query in self.query_cache:
            query_embedding = self.query_cache[query]
        else:
            query_embedding = self.client.embed([query], model="voyage-2").embeddings[0]
            self.query_cache[query] = query_embedding

        if not self.embeddings:
            raise ValueError("No data loaded in the vector database.")

        similarities = np.dot(self.embeddings, query_embedding)
        top_indices = np.argsort(similarities)[::-1]
        top_examples = []

        for idx in top_indices:
            if similarities[idx] >= similarity_threshold:
                example = {
                    "metadata": self.metadata[idx],
                    "similarity": similarities[idx],
                }
                top_examples.append(example)

                if len(top_examples) >= k:
                    break
        self.save_db()
        return top_examples

    def save_db(self):
        data = {
            "embeddings": self.embeddings,
            "metadata": self.metadata,
            "query_cache": json.dumps(self.query_cache),
        }
        with open(self.db_path, "wb") as file:
            pickle.dump(data, file)

    def load_db(self):
        if not os.path.exists(self.db_path):
            raise ValueError(
                "Vector database file not found. Use load_data to create a new database."
            )

        with open(self.db_path, "rb") as file:
            data = pickle.load(file)

        self.embeddings = data["embeddings"]
        self.metadata = data["metadata"]
        self.query_cache = json.loads(data["query_cache"])
```

我們可以定義 vector db 並載入訓練資料。

沒有綁信用卡的 VoyageAI 帳號有 3RPM 的 rate limit，為了方便示範，我們會用 cache。

```python
vectordb = VectorDB()
vectordb.load_data(data["train"])
```

??? note "輸出"

    ```text
    Loading vector database from disk.
    ```

## 加強版 RAG 分類器

現在用 retrieval-augmented generation 重建分類器。`rag_classify` 函式在簡單分類器之上做了這些加強：
1. **檢索相似範例**：對每張工單，在向量資料庫中搜尋語意最相似的 5 個訓練範例
2. **格式化成 few-shot 範例**：把這些範例用 `<query>` 和 `<label>` 標籤組成 XML 結構，讓 Claude 看到相似的工單是怎麼分類的
3. **擴充 prompt**：在請 Claude 分類新工單之前，把這些範例注入 prompt

這種 few-shot learning 的做法，是用具體範例展示語言相近的工單該怎麼分類，幫 Claude 更準確地區分相近類別。比如測試工單提到「unexpected charges」，撈出過去的「Billing Disputes」和「Billing Inquiries」範例，就能幫 Claude 理解兩者的細微差別。

看看這對上一輪容易搞混的類別提升了多少準確率。

```python
def rag_classify(X):
    rag = vectordb.search(X, 5)
    rag_string = ""
    for example in rag:
        rag_string += textwrap.dedent(f"""
        <example>
            <query>
                "{example["metadata"]["text"]}"
            </query>
            <label>
                {example["metadata"]["label"]}
            </label>
        </example>
        """)
    prompt = (
        textwrap.dedent("""
    You will classify a customer support ticket into one of the following categories:
    <categories>
        {{categories}}
    </categories>

    Here is the customer support ticket:
    <ticket>
        {{ticket}}
    </ticket>

    Use the following examples to help you classify the query:
    <examples>
        {{examples}}
    </examples>

    Respond with just the label of the category between category tags.
    """)
        .replace("{{categories}}", categories)
        .replace("{{ticket}}", X)
        .replace("{{examples}}", rag_string)
    )
    response = client.messages.create(
        messages=[{"role": "user", "content": prompt}],
        stop_sequences=["</category>"],
        max_tokens=4096,
        model=MODEL,
    )

    text = "".join(b.text for b in response.content if b.type == "text")
    return text.split("<category>")[-1].strip()
```

```python
print("Evaluating the RAG method on the test set...")
evaluate(X_test, y_test, rag_classify)
```

??? note "輸出"

    ```text
    Evaluating the RAG method on the test set...
                           precision    recall  f1-score   support

        Claims Assistance       1.00      1.00      1.00         6
     Quotes and Proposals       1.00      1.00      1.00         5
          Claims Disputes       1.00      1.00      1.00         9
    Coverage Explanations       0.82      1.00      0.90         9
         Billing Disputes       0.82      1.00      0.90         9
    Policy Administration       1.00      1.00      1.00         6
        Billing Inquiries       1.00      0.67      0.80         6
        General Inquiries       1.00      0.71      0.83         7
       Policy Comparisons       1.00      1.00      1.00         5
       Account Management       1.00      1.00      1.00         6

                 accuracy                           0.94        68
                macro avg       0.96      0.94      0.94        68
             weighted avg       0.95      0.94      0.94        68
    ```

## RAG 結果分析

RAG 把準確率從約 70% 提升到 **94%**。Confusion matrix 的對角線強很多，大多數類別現在都達到完美或接近完美。

剩下的少數錯誤顯示，即使有相關範例，還是有些邊界案例很模糊。這時 chain-of-thought 推理可以幫 Claude 更仔細地想清楚這些細微差異。

## RAG 加 Chain-of-Thought 推理

Chain-of-thought（CoT）prompting 請 Claude 在做分類決定之前先「出聲思考」。

這種明確的推理過程，幫 Claude 抓到直接分類時可能漏掉的細微差別。比如區分「I have a question about my bill」（Billing Inquiry）和「This charge seems wrong」（Billing Dispute），需要理解意圖和語氣，這正是逐步分析有幫助的地方。

`rag_chain_of_thought_classify` 函式加了一個 `<scratchpad>` 區塊，讓 Claude 在輸出最終的 `<category>` 之前先在裡面推理。

```python
def rag_chain_of_thought_classify(X):
    rag = vectordb.search(X, 5)
    rag_string = ""
    for example in rag:
        rag_string += textwrap.dedent(f"""
        <example>
            <query>
                "{example["metadata"]["text"]}"
            </query>
            <label>
                {example["metadata"]["label"]}
            </label>
        </example>
        """)
    prompt = (
        textwrap.dedent("""
    You will classify a customer support ticket into one of the following categories:
    <categories>
        {{categories}}
    </categories>

    Here is the customer support ticket:
    <ticket>
        {{ticket}}
    </ticket>

    Use the following examples to help you classify the query:
    <examples>
        {{examples}}
    </examples>

    First you will think step-by-step about the problem in scratchpad tags.
    You should consider all the information provided and create a concrete argument for your classification.

    Respond using this format:
    <response>
        <scratchpad>Your thoughts and analysis go here</scratchpad>
        <category>The category label you chose goes here</category>
    </response>
    """)
        .replace("{{categories}}", categories)
        .replace("{{ticket}}", X)
        .replace("{{examples}}", rag_string)
    )
    response = client.messages.create(
        messages=[{"role": "user", "content": prompt}],
        stop_sequences=["</category>"],
        max_tokens=4096,
        model=MODEL,
    )

    # The prompt asks for <response><scratchpad>...</scratchpad><category>Label</category>;
    # take what follows <category> in the text blocks.
    text = "".join(b.text for b in response.content if b.type == "text")
    return text.split("<category>")[-1].strip()
```

```python
print("Evaluating the RAG method with Chain of Thought on the test set...")
evaluate(X_test, y_test, rag_chain_of_thought_classify)
```

??? note "輸出"

    ```text
    Evaluating the RAG method with Chain of Thought on the test set...
                           precision    recall  f1-score   support

        Claims Assistance       1.00      1.00      1.00         6
     Quotes and Proposals       1.00      1.00      1.00         5
          Claims Disputes       1.00      1.00      1.00         9
    Coverage Explanations       1.00      1.00      1.00         9
         Billing Disputes       0.82      1.00      0.90         9
    Policy Administration       1.00      1.00      1.00         6
        Billing Inquiries       1.00      0.67      0.80         6
        General Inquiries       1.00      1.00      1.00         7
       Policy Comparisons       1.00      1.00      1.00         5
       Account Management       1.00      1.00      1.00         6

                 accuracy                           0.97        68
                macro avg       0.98      0.97      0.97        68
             weighted avg       0.98      0.97      0.97        68
    ```

## Chain-of-Thought 結果分析

Chain-of-thought 推理把準確率推到 **97%**，解決了前幾種做法碰到的大部分邊界案例。

**逐步進步摘要：**
- 隨機基準：約 10% 準確率
- 簡單分類器：約 70% 準確率
- RAG 分類器：94% 準確率  
- **RAG + Chain-of-Thought：97% 準確率**

明確地逐步推理每個分類決定，讓 Claude 更能區分模稜兩可的案例。

# 用 Promptfoo 擴大評估規模

整份指南裡，我們一直在示範設計 prompt 時**實證評估**有多重要。我們不靠直覺，而是在每一步都量測表現：

- 隨機基準：約 10% → 簡單：約 70% → RAG：94% → RAG + CoT：97%

這種數據導向的做法清楚顯示了哪些技巧（RAG、chain-of-thought）加了價值、加了多少。這個方法論的更多內容見我們的 [prompt engineering 指南](https://docs.claude.com/en/docs/prompt-engineering)。

## 超越 Notebook

Jupyter notebook 很適合快速迭代和探索，但正式環境的分類系統需要更紮實的評估基礎設施：

- **更大的測試集**：你會想在幾百、幾千個範例上評估，而不只是 68 個
- **多個 prompt 變體**：A/B 測試不同的措辭、結構和做法
- **模型比較**：測試不同的 Claude 模型（Haiku 對 Sonnet）或 temperature 設定
- **偵測退步**：確保改 prompt 不會不小心傷到準確率
- **版本控制**：隨著系統演進追蹤 prompt 的表現

這就是 [Promptfoo](https://www.promptfoo.dev/) 這類專門的評估工具變得不可或缺的地方。

## 執行 Promptfoo 評估

Promptfoo 是開源的 LLM 評估工具組，能自動化跨多種設定的 prompt 測試。這份指南裡我們已經設好一個 Promptfoo 評估，測試三種做法（Simple、RAG、RAG w/ CoT）。放在 repo 裡的設定和 `data/results.csv` 是用 `claude-haiku-4-5` 在五種 temperature 設定下記錄的；目前的模型已經不接受 `temperature`，所以要用 Claude Haiku 5.5 重跑，請拿掉 `temperature` 那幾行，改成比較不同模型。

**執行評估：**

1. 進入評估目錄：`cd ./evaluation`
2. 照 `./evaluation/README.md` 的指示設定
3. 跑評估，再回到這裡分析下面的結果

結果會顯示每個 prompt 變體在完整測試集上的表現，揭露只在 notebook 測試時可能看不出來的規律。

```python
import json

import pandas as pd

promptfoo_results = pd.read_csv("./data/results.csv")
examples_columns = promptfoo_results.columns[2:]

number_of_providers = 5
number_of_prompts = 3

prompts = ["Simple", "RAG", "RAG w/ CoT"]

columns = ["label", "text"] + [
    json.loads(examples_columns[prompt * number_of_providers + provider])["provider"]
    + " Prompt: "
    + str(prompts[prompt])
    for prompt in range(number_of_prompts)
    for provider in range(number_of_providers)
]

promptfoo_results.columns = columns

result = (
    promptfoo_results.iloc[:, 2:].astype(str).apply(lambda x: x.str.count("PASS")).sum()
    / len(promptfoo_results)
    * 100
).sort_values(ascending=False)

print(result)
```

??? note "輸出"

    ```text
    Haiku: T-0.0 Prompt: RAG w/ CoT    95.588235
    Haiku: T-0.2 Prompt: RAG w/ CoT    95.588235
    Haiku: T-0.8 Prompt: RAG w/ CoT    95.588235
    Haiku: T-0.0 Prompt: RAG           94.117647
    Haiku: T-0.4 Prompt: RAG           94.117647
    Haiku: T-0.6 Prompt: RAG           94.117647
    Haiku: T-0.4 Prompt: RAG w/ CoT    94.117647
    Haiku: T-0.6 Prompt: RAG w/ CoT    94.117647
    Haiku: T-0.2 Prompt: RAG           92.647059
    Haiku: T-0.8 Prompt: RAG           89.705882
    Haiku: T-0.6 Prompt: Simple        72.058824
    Haiku: T-0.0 Prompt: Simple        70.588235
    Haiku: T-0.2 Prompt: Simple        70.588235
    Haiku: T-0.8 Prompt: Simple        70.588235
    Haiku: T-0.4 Prompt: Simple        69.117647
    dtype: float64
    ```

## 用 Promptfoo 做系統化評估

上面的結果展現了大規模系統化 prompt 評估的威力。Notebook 在開發期間提供了快速迭代，而 [Promptfoo](https://www.promptfoo.dev/) 讓我們能從多個面向嚴格測試 prompt：

### 我們測了什麼

用 Promptfoo，我們評估三種 prompt 做法（Simple、RAG、RAG w/ CoT）在下列條件下的表現：
- **多種 temperature 設定**（0.0、0.2、0.4、0.6、0.8），用 `claude-haiku-4-5` 記錄：測試決定性的分類（T=0.0）是否優於略帶隨機的輸出。目前的模型不接受 `temperature`，所以這個維度只適用於那次記錄的執行。
- **同一組測試集**（68 個範例）：確保所有設定之間公平比較
- **自動化的通過/失敗檢查**：每個預測都自動跟 ground truth 標籤比對

### 主要發現

Promptfoo 的結果印證了 notebook 的發現，同時揭露更多洞察：

1. **Temperature 對 CoT 影響很小**：RAG w/ CoT 在 T=0.0、0.2 和 0.8 都穩定達到 95.59% 準確率，代表不論取樣隨機性如何，chain-of-thought 推理都會讓輸出穩定

2. **RAG 對 temperature 變化很穩健**：RAG 的表現在大多數 temperature 設定下都維持高水準（89-94%），不過 T=0.0 最好（94.12%）

3. **簡單 prompt 跟 temperature 無關**：簡單分類器不論 temperature 都在約 70% 準確率附近，確認了沒有 RAG 或 CoT 時，模型主要靠類別定義

4. **正式環境建議**：要最佳準確率就用 RAG w/ CoT（記錄的那次執行是 95.59%）；在目前的模型上，取樣維持預設值

想自己跑這些評估，設定方式見 `./evaluation/README.md`。

## 重點整理

- 先建基準再優化：隨機分類器約 10%，讓你知道每個技巧真正加了多少。
- 簡單 prompt 加上 XML 結構和 stop sequence 就能到約 70%，但相近類別（例如帳單詢問與帳單爭議）會被搞混。
- RAG 用相似的標註範例做 few-shot，不用 fine-tuning 就把準確率拉到 94%。
- Chain-of-thought 讓模型先在 `<scratchpad>` 推理再下判斷，處理意圖和語氣的細微差別，進一步提升準確率。
- 正式環境要用 Promptfoo 這類工具在大測試集上做系統化評估，才能比較 prompt、模型並偵測退步。

## 練習

1. 把 `rag_classify` 撈取的相似範例數從 5 改成 2 和 10，比較準確率變化。
2. 在類別定義裡把 Billing Inquiries 和 Billing Disputes 的描述改得更模糊或更精確，看 confusion matrix 對應的格子怎麼變。
3. 修改 `rag_chain_of_thought_classify` 的 `<scratchpad>` 指示，要求列出每個候選類別的支持與反對理由，再比較準確率和輸出長度。
