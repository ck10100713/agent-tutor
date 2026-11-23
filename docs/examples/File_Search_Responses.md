---
translated: true
source: examples/File_Search_Responses.ipynb
---

# 用 Responses API 的 File Search 對 PDF 做 RAG

> 原文：[examples/File_Search_Responses.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/File_Search_Responses.ipynb)

用 Responses API 的 file search tool 搜尋 PDF。

## 這篇在做什麼
把一批 PDF 上傳到 OpenAI 的 vector store，再用 Responses API 的 `file_search` tool 一次呼叫就完成檢索加回答。最後還會自動產生評估資料集，量測檢索的 recall、precision、MRR 和 MAP。

## 學完你會
- 建立 vector store 並上傳 PDF，直接用 vector search API 查詢內容。
- 在 Responses API 裡掛上 `file_search` tool，讓模型根據檢索到的內容回答。
- 自己產生評估資料集，算出檢索的 precision、recall、MRR、MAP。

## 開跑前
- 需要 OpenAI API key。
- 需要準備一批本機 PDF（範例用的是 OpenAI 部落格文章匯出的 PDF）。

RAG 常常讓人覺得很複雜，但搜尋 PDF 其實不該那麼麻煩。目前最常見的做法是：解析 PDF、決定 chunking 策略、把 chunk 上傳到儲存服務、對文字 chunk 跑 embedding、把 embedding 存進 vector database。這還只是前置作業，在 LLM 流程裡取回內容也要好幾個步驟。

這時候就輪到 file search 了。它是 Responses API 裡的 hosted tool，可以搜尋你的知識庫，並根據檢索到的內容產生答案。這份教學會把 PDF 上傳到 OpenAI 的 vector store，用 file search 從中取出額外脈絡，來回答我們一開始產生的問題。我們先根據 OpenAI 部落格（[openai.com/news](https://openai.com/news)）匯出的 PDF 建立一小批問題。

_File search 以前在 Assistants API 上提供，現在移到新的 Responses API，這個 API 可以有狀態也可以無狀態，並多了像 metadata filtering 這類新功能_

# 用 PDF 建立 Vector Store

```python
!pip install PyPDF2 pandas tqdm openai -q
```

```python
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import concurrent
import PyPDF2
import os
import pandas as pd
import base64

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
dir_pdfs = 'openai_blog_pdfs' # have those PDFs stored locally here
pdf_files = [os.path.join(dir_pdfs, f) for f in os.listdir(dir_pdfs)]
```

我們會在 OpenAI API 上建立 Vector Store，並把 PDF 上傳進去。OpenAI 會讀取 PDF、把內容切成多個文字 chunk、對它們跑 embedding，再把 embedding 和文字存進 Vector Store。之後就能查詢這個 Vector Store，依 query 回傳相關內容。

```python
def upload_single_pdf(file_path: str, vector_store_id: str):
    file_name = os.path.basename(file_path)
    try:
        file_response = client.files.create(file=open(file_path, 'rb'), purpose="assistants")
        attach_response = client.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=file_response.id
        )
        return {"file": file_name, "status": "success"}
    except Exception as e:
        print(f"Error with {file_name}: {str(e)}")
        return {"file": file_name, "status": "failed", "error": str(e)}

def upload_pdf_files_to_vector_store(vector_store_id: str):
    pdf_files = [os.path.join(dir_pdfs, f) for f in os.listdir(dir_pdfs)]
    stats = {"total_files": len(pdf_files), "successful_uploads": 0, "failed_uploads": 0, "errors": []}
    
    print(f"{len(pdf_files)} PDF files to process. Uploading in parallel...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(upload_single_pdf, file_path, vector_store_id): file_path for file_path in pdf_files}
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(pdf_files)):
            result = future.result()
            if result["status"] == "success":
                stats["successful_uploads"] += 1
            else:
                stats["failed_uploads"] += 1
                stats["errors"].append(result)

    return stats

def create_vector_store(store_name: str) -> dict:
    try:
        vector_store = client.vector_stores.create(name=store_name)
        details = {
            "id": vector_store.id,
            "name": vector_store.name,
            "created_at": vector_store.created_at,
            "file_count": vector_store.file_counts.completed
        }
        print("Vector store created:", details)
        return details
    except Exception as e:
        print(f"Error creating vector store: {e}")
        return {}
```

```python
store_name = "openai_blog_store"
vector_store_details = create_vector_store(store_name)
upload_pdf_files_to_vector_store(vector_store_details["id"])
```

??? note "輸出"

    ```text
    Vector store created: {'id': 'vs_67d06b9b9a9c8191bafd456cf2364ce3', 'name': 'openai_blog_store', 'created_at': 1741712283, 'file_count': 0}
    21 PDF files to process. Uploading in parallel...
    ```

    ```text
    100%|███████████████████████████████| 21/21 [00:09<00:00,  2.32it/s]
    ```

    ```text
    {'total_files': 21,
     'successful_uploads': 21,
     'failed_uploads': 0,
     'errors': []}
    ```

# 單獨使用 vector search

Vector store 準備好後，我們可以直接查詢它，針對某個 query 取回相關內容。用新的 [vector search API](https://platform.openai.com/docs/api-reference/vector-stores/search)，不用接進 LLM 呼叫，也能從知識庫找出相關項目。

```python
query = "What's Deep Research?"
search_results = client.vector_stores.search(
    vector_store_id=vector_store_details['id'],
    query=query
)
```

```python
for result in search_results.data:
    print(str(len(result.content[0].text)) + ' of character of content from ' + result.filename + ' with a relevant score of ' + str(result.score))
```

??? note "輸出"

    ```text
    3502 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.9813588865322393
    3493 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.9522476825143714
    3634 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.9397930296526796
    2774 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.9101975747303771
    3474 of character of content from Deep research System Card _ OpenAI.pdf with a relevant score of 0.9036647613464299
    3123 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.887120981288272
    3343 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.8448454849432881
    3262 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.791345286655509
    3271 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.7485530025091963
    2721 of character of content from Introducing deep research _ OpenAI.pdf with a relevant score of 0.734033360849088
    ```

可以看到搜尋結果回傳了不同大小（底層也是不同文字）的內容。每筆都有各自的相關性分數，由我們的 ranker 計算，它使用 hybrid search。

# 在單一 API 呼叫裡整合搜尋結果和 LLM

不過比起先查 vector store、再把資料丟進 Responses 或 Chat Completion API，更方便的做法是在 OpenAI Responses API 裡直接掛上 file_search tool。

```python
query = "What's Deep Research?"
response = client.responses.create(
    input= query,
    model="gpt-4o-mini",
    tools=[{
        "type": "file_search",
        "vector_store_ids": [vector_store_details['id']],
    }]
)

# Extract annotations from the response
annotations = response.output[1].content[0].annotations
    
# Get top-k retrieved filenames
retrieved_files = set([result.filename for result in annotations])

print(f'Files used: {retrieved_files}')
print('Response:')
print(response.output[1].content[0].text) # 0 being the filesearch call
```

??? note "輸出"

    ```text
    Files used: {'Introducing deep research _ OpenAI.pdf'}
    Response:
    Deep Research is a new capability introduced by OpenAI that allows users to conduct complex, multi-step research tasks on the internet efficiently. Key features include:

    1. **Autonomous Research**: Deep Research acts as an independent agent that synthesizes vast amounts of information across the web, enabling users to receive comprehensive reports similar to those produced by a research analyst.

    2. **Multi-Step Reasoning**: It performs deep analysis by finding, interpreting, and synthesizing data from various sources, including text, images, and PDFs.

    3. **Application Areas**: Especially useful for professionals in fields such as finance, science, policy, and engineering, as well as for consumers seeking detailed information for purchases.

    4. **Efficiency**: The output is fully documented with citations, making it easy to verify information, and it significantly speeds up research processes that would otherwise take hours for a human to complete.

    5. **Limitations**: While Deep Research enhances research capabilities, it is still subject to limitations, such as potential inaccuracies in information retrieval and challenges in distinguishing authoritative data from unreliable sources.

    Overall, Deep Research marks a significant advancement toward automated general intelligence (AGI) by improving access to thorough and precise research outputs.
    ```

可以看到 `gpt-4o-mini` 能回答一個需要較新、較專門知識（關於 OpenAI Deep Research）的問題。它用到的是檔案 `Introducing deep research _ OpenAI.pdf` 裡最相關的文字 chunk。如果想更深入分析檢索到的文字，可以在 query 加上 `include=["output[*].file_search_call.search_results"]`，就能看到搜尋引擎回傳的各段文字。

# 評估效能

這類資訊檢索系統很關鍵的一點，是要衡量檢索到的檔案相關性和品質。這份教學接下來會產生評估資料集，並在上面計算各種指標。這個做法不完美，我們一向建議用人工驗證過的評估資料集，但它能讓你看到評估的方法。不完美的原因是，產生的問題有些很籠統（例如「這份文件裡主要關係人說了什麼」），檢索測試很難判斷這個問題是從哪份文件產生的。

## 產生評估資料

我們會寫函式讀取本機的 PDF，並產生只有這份文件能回答的問題，這就是之後要用的評估資料集。

```python
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    return text

def generate_questions(pdf_path):
    text = extract_text_from_pdf(pdf_path)

    prompt = (
        "Can you generate a question that can only be answered from this document?:\n"
        f"{text}\n\n"
    )

    response = client.responses.create(
        input=prompt,
        model="gpt-4o",
    )

    question = response.output[0].content[0].text

    return question
```

對第一份 PDF 執行 generate_question，就能看到它產生的是什麼樣的問題。

```python
generate_questions(pdf_files[0])
```

??? note "輸出"

    ```text
    'What new capabilities will ChatGPT have as a result of the partnership between OpenAI and Schibsted Media Group?'
    ```

接著為本機所有 PDF 產生問題。

```python
# Generate questions for each PDF and store in a dictionary
questions_dict = {}
for pdf_path in pdf_files:
    questions = generate_questions(pdf_path)
    questions_dict[os.path.basename(pdf_path)] = questions
```

```python
questions_dict
```

??? note "輸出"

    ```text
    {'OpenAI partners with Schibsted Media Group _ OpenAI.pdf': 'What is the purpose of the partnership between Schibsted Media Group and OpenAI announced on February 10, 2025?',
     'OpenAI and the CSU system bring AI to 500,000 students & faculty _ OpenAI.pdf': 'What significant milestone did the California State University system achieve by partnering with OpenAI, making it the first of its kind in the United States?',
     '1,000 Scientist AI Jam Session _ OpenAI.pdf': 'What was the specific AI model used during the "1,000 Scientist AI Jam Session" event across the nine national labs?',
     'Announcing The Stargate Project _ OpenAI.pdf': 'What are the initial equity funders and lead partners in The Stargate Project announced by OpenAI, and who holds the financial and operational responsibilities?',
     'Introducing Operator _ OpenAI.pdf': 'What is the name of the new model that powers the Operator agent introduced by OpenAI?',
     'Introducing NextGenAI _ OpenAI.pdf': 'What major initiative did OpenAI launch on March 4, 2025, and which research institution from Europe is involved as a founding partner?',
     'Introducing the Intelligence Age _ OpenAI.pdf': "What is the name of the video generation tool used by OpenAI's creative team to help produce their Super Bowl ad?",
     'Operator System Card _ OpenAI.pdf': 'What is the preparedness score for the "Cybersecurity" category according to the Operator System Card?',
     'Strengthening America’s AI leadership with the U.S. National Laboratories _ OpenAI.pdf': "What is the purpose of OpenAI's agreement with the U.S. National Laboratories as described in the document?",
     'OpenAI GPT-4.5 System Card _ OpenAI.pdf': 'What is the Preparedness Framework rating for "Cybersecurity" for GPT-4.5 according to the system card?',
     'Partnering with Axios expands OpenAI’s work with the news industry _ OpenAI.pdf': "What is the goal of OpenAI's new content partnership with Axios as announced in the document?",
     'OpenAI and Guardian Media Group launch content partnership _ OpenAI.pdf': 'What is the main purpose of the partnership between OpenAI and Guardian Media Group announced on February 14, 2025?',
     'Introducing GPT-4.5 _ OpenAI.pdf': 'What is the release date of the GPT-4.5 research preview?',
     'Introducing data residency in Europe _ OpenAI.pdf': 'What are the benefits of data residency in Europe for new ChatGPT Enterprise and Edu customers according to the document?',
     'The power of personalized AI _ OpenAI.pdf': 'What is the purpose of the "Model Spec" document published by OpenAI for ChatGPT?',
     'Disrupting malicious uses of AI _ OpenAI.pdf': "What is OpenAI's mission as stated in the document?",
     'Sharing the latest Model Spec _ OpenAI.pdf': 'What is the release date of the latest Model Spec mentioned in the document?',
     'Deep research System Card _ OpenAI.pdf': "What specific publication date is mentioned in the Deep Research System Card for when the report on deep research's preparedness was released?",
     'Bertelsmann powers creativity and productivity with OpenAI _ OpenAI.pdf': 'What specific AI-powered solutions is Bertelsmann planning to implement for its divisions RTL Deutschland and Penguin Random House according to the document?',
     'OpenAI’s Economic Blueprint _ OpenAI.pdf': 'What date and location is scheduled for the kickoff event of OpenAI\'s "Innovating for America" initiative as mentioned in the Economic Blueprint document?',
     'Introducing deep research _ OpenAI.pdf': 'What specific model powers the "deep research" capability in ChatGPT that is discussed in this document, and what are its main features designed for?'}
    ```

現在有了一個 `filename:question` 的字典，可以逐一迴圈去問 gpt-4o(-mini)，過程中不提供文件，gpt-4o 應該要能在 Vector Store 裡找到相關文件。

## 評估

我們把字典轉成 dataframe，用 gpt-4o-mini 處理，並檢查預期的檔案有沒有被找到。

```python
rows = []
for filename, query in questions_dict.items():
    rows.append({"query": query, "_id": filename.replace(".pdf", "")})

# Metrics evaluation parameters
k = 5
total_queries = len(rows)
correct_retrievals_at_k = 0
reciprocal_ranks = []
average_precisions = []

def process_query(row):
    query = row['query']
    expected_filename = row['_id'] + '.pdf'
    # Call file_search via Responses API
    response = client.responses.create(
        input=query,
        model="gpt-4o-mini",
        tools=[{
            "type": "file_search",
            "vector_store_ids": [vector_store_details['id']],
            "max_num_results": k,
        }],
        tool_choice="required" # it will force the file_search, while not necessary, it's better to enforce it as this is what we're testing
    )
    # Extract annotations from the response
    annotations = None
    if hasattr(response.output[1], 'content') and response.output[1].content:
        annotations = response.output[1].content[0].annotations
    elif hasattr(response.output[1], 'annotations'):
        annotations = response.output[1].annotations

    if annotations is None:
        print(f"No annotations for query: {query}")
        return False, 0, 0

    # Get top-k retrieved filenames
    retrieved_files = [result.filename for result in annotations[:k]]
    if expected_filename in retrieved_files:
        rank = retrieved_files.index(expected_filename) + 1
        rr = 1 / rank
        correct = True
    else:
        rr = 0
        correct = False

    # Calculate Average Precision
    precisions = []
    num_relevant = 0
    for i, fname in enumerate(retrieved_files):
        if fname == expected_filename:
            num_relevant += 1
            precisions.append(num_relevant / (i + 1))
    avg_precision = sum(precisions) / len(precisions) if precisions else 0
    
    if expected_filename not in retrieved_files:
        print("Expected file NOT found in the retrieved files!")
        
    if retrieved_files and retrieved_files[0] != expected_filename:
        print(f"Query: {query}")
        print(f"Expected file: {expected_filename}")
        print(f"First retrieved file: {retrieved_files[0]}")
        print(f"Retrieved files: {retrieved_files}")
        print("-" * 50)
    
    
    return correct, rr, avg_precision
```

```python
process_query(rows[0])
```

??? note "輸出"

    ```text
    (True, 1.0, 1.0)
    ```

這個例子的 Recall 和 Precision 都是 1，而且目標檔案排第一，所以 MRR 和 MAP 都是 1。

接著對整組問題執行同樣的處理。

```python
with ThreadPoolExecutor() as executor:
    results = list(tqdm(executor.map(process_query, rows), total=total_queries))

correct_retrievals_at_k = 0
reciprocal_ranks = []
average_precisions = []

for correct, rr, avg_precision in results:
    if correct:
        correct_retrievals_at_k += 1
    reciprocal_ranks.append(rr)
    average_precisions.append(avg_precision)

recall_at_k = correct_retrievals_at_k / total_queries
precision_at_k = recall_at_k  # In this context, same as recall
mrr = sum(reciprocal_ranks) / total_queries
map_score = sum(average_precisions) / total_queries
```

??? note "輸出"

    ```text
     62%|███████████████████▏           | 13/21 [00:07<00:03,  2.57it/s]
    ```

    ```text
    Expected file NOT found in the retrieved files!
    Query: What is OpenAI's mission as stated in the document?
    Expected file: Disrupting malicious uses of AI _ OpenAI.pdf
    First retrieved file: Introducing the Intelligence Age _ OpenAI.pdf
    Retrieved files: ['Introducing the Intelligence Age _ OpenAI.pdf']
    --------------------------------------------------
    ```

    ```text
     71%|██████████████████████▏        | 15/21 [00:14<00:06,  1.04s/it]
    ```

    ```text
    Expected file NOT found in the retrieved files!
    Query: What is the purpose of the "Model Spec" document published by OpenAI for ChatGPT?
    Expected file: The power of personalized AI _ OpenAI.pdf
    First retrieved file: Sharing the latest Model Spec _ OpenAI.pdf
    Retrieved files: ['Sharing the latest Model Spec _ OpenAI.pdf', 'Sharing the latest Model Spec _ OpenAI.pdf', 'Sharing the latest Model Spec _ OpenAI.pdf', 'Sharing the latest Model Spec _ OpenAI.pdf', 'Sharing the latest Model Spec _ OpenAI.pdf']
    --------------------------------------------------
    ```

    ```text
    100%|███████████████████████████████| 21/21 [00:15<00:00,  1.38it/s]
    ```

上面記錄的輸出會顯示：評估資料集預期某個檔案排第一但實際沒有，或是完全沒找到。從這份不完美的評估資料集可以看到，有些問題太籠統、預期的是另一份文件，而我們的檢索系統沒有針對這個問題特別取回它。

```python
# Print the metrics with k
print(f"Metrics at k={k}:")
print(f"Recall@{k}: {recall_at_k:.4f}")
print(f"Precision@{k}: {precision_at_k:.4f}")
print(f"Mean Reciprocal Rank (MRR): {mrr:.4f}")
print(f"Mean Average Precision (MAP): {map_score:.4f}")
```

??? note "輸出"

    ```text
    Metrics at k=5:
    Recall@5: 0.9048
    Precision@5: 0.9048
    Mean Reciprocal Rank (MRR): 0.9048
    Mean Average Precision (MAP): 0.8954
    ```

這份教學我們學到：
- 用 PDF context-stuffing（利用 4o 的視覺能力）和傳統 PDF 讀取器產生評估資料集
- 建立 vector store 並放入 PDF
- 利用 OpenAI Responses API 內建的 `file_search` tool call，直接得到 RAG 系統產生的 LLM 答案
- 了解文字 chunk 在 Responses API 裡如何被檢索、排序和使用
- 在先前產生的評估資料集上衡量 accuracy、precision、recall、MRR 和 MAP

用 Responses 搭配 file search，一次 API 呼叫就能簡化 RAG 架構。檔案儲存、embedding、檢索全部整合在一個 tool 裡！


## 重點整理
- file search 把切 chunk、embedding、存 vector database、檢索都包成 hosted tool，不用自己搭 RAG pipeline。
- vector search API 可以單獨用，不一定要接 LLM；掛在 Responses API 的 `file_search` tool 則一次呼叫就能檢索加回答。
- 檢索系統要量測：用 recall、precision、MRR、MAP 看目標文件有沒有被找到、排第幾。
- 自動產生的評估問題可能太籠統，真正上線建議用人工驗證過的資料集。

## 練習
1. 換一個問題去查 vector search，比較不同 query 回傳的 chunk 和相關性分數。
2. 在 `file_search` 的呼叫加上 `include=["output[*].file_search_call.search_results"]`，印出模型實際參考了哪些 chunk。
3. 修改 generate_question 的 prompt，要求問題要包含文件裡的具體細節，再重跑評估，看 MRR 和 MAP 有沒有提升。
