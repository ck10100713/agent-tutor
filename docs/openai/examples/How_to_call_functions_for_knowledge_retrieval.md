---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/How_to_call_functions_for_knowledge_retrieval.ipynb
---

# 用 function 串接知識庫

> 原文：[examples/How_to_call_functions_for_knowledge_retrieval.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_for_knowledge_retrieval.ipynb)



## 這篇在做什麼
這篇延續[參數生成](How_to_call_functions_with_chat_models.md)那篇的概念，做一個能存取知識庫的 agent，並給它兩個 function，讓它依使用者需求自己決定要呼叫哪一個。
資料來源是 arXiv，agent 會回答學術主題的問題。兩個 function 分別是：
- **get_articles**：到 arXiv 抓某個主題的文章，摘要後附上連結給使用者。
- **read_article_and_summarize**：從先前搜尋到的文章挑一篇，整篇讀完，再摘要核心論點、證據和結論。

## 學完你會
- 做出一個能在多個 function 之間選擇的 agent。
- 讓第一個 function 抓到的資料保留下來，給第二個 function 接著用。
- 把搜尋、embedding 檢索和 Chat Completion 串成一段能多輪對話的流程。

## 開跑前
- 需要 OpenAI API key。
- 會連到 arXiv 下載論文，並用 embedding 做檢索，會產生 API 費用。

## 流程總覽

這篇的流程如下：

- **Search utilities：** 建立兩個去 arXiv 找答案的 function。
- **Configure Agent：** 設計 agent 的行為，讓它判斷需不需要呼叫 function，需要就呼叫，再把結果呈現出來。
- **arXiv conversation：** 把全部串起來，實際對話一次。


```python
!pip install scipy --quiet
!pip install tenacity --quiet
!pip install tiktoken==0.3.3 --quiet
!pip install termcolor --quiet
!pip install openai --quiet
!pip install arxiv --quiet
!pip install pandas --quiet
!pip install PyPDF2 --quiet
!pip install tqdm --quiet
```

```python
import arxiv
import ast
import concurrent
import json
import os
import pandas as pd
import tiktoken
from csv import writer
from IPython.display import display, Markdown, Latex
from openai import OpenAI
from PyPDF2 import PdfReader
from scipy import spatial
from tenacity import retry, wait_random_exponential, stop_after_attempt
from tqdm import tqdm
from termcolor import colored

GPT_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-ada-002"
client = OpenAI()
```

## Search utilities

先準備一些工具函式，作為兩個 function 的底層。

下載的論文會放在一個目錄（這裡用 ```./data/papers```）。另外建一個 ```arxiv_library.csv```，存已下載論文的 embedding 和細節，之後用 ```summarize_text``` 對它做檢索。

```python
directory = './data/papers'

# Check if the directory already exists
if not os.path.exists(directory):
    # If the directory doesn't exist, create it and any necessary intermediate directories
    os.makedirs(directory)
    print(f"Directory '{directory}' created successfully.")
else:
    # If the directory already exists, print a message indicating it
    print(f"Directory '{directory}' already exists.")
```

??? note "輸出"

    ```text
    Directory './data/papers' already exists.
    ```

```python
# Set a directory to store downloaded papers
data_dir = os.path.join(os.curdir, "data", "papers")
paper_dir_filepath = "./data/papers/arxiv_library.csv"

# Generate a blank dataframe where we can store downloaded files
df = pd.DataFrame(list())
df.to_csv(paper_dir_filepath)
```

```python
@retry(wait=wait_random_exponential(min=1, max=40), stop=stop_after_attempt(3))
def embedding_request(text):
    response = client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    return response


@retry(wait=wait_random_exponential(min=1, max=40), stop=stop_after_attempt(3))
def get_articles(query, library=paper_dir_filepath, top_k=10):
    """This function gets the top_k articles based on a user's query, sorted by relevance.
    It also downloads the files and stores them in arxiv_library.csv to be retrieved by the read_article_and_summarize.
    """
    client = arxiv.Client()
    search = arxiv.Search(
        query = query,
        max_results = top_k
    )
    result_list = []
    for result in client.results(search):
        result_dict = {}
        result_dict.update({"title": result.title})
        result_dict.update({"summary": result.summary})

        # Taking the first url provided
        result_dict.update({"article_url": [x.href for x in result.links][0]})
        result_dict.update({"pdf_url": [x.href for x in result.links][1]})
        result_list.append(result_dict)

        # Store references in library file
        response = embedding_request(text=result.title)
        file_reference = [
            result.title,
            result.download_pdf(data_dir),
            response.data[0].embedding,
        ]

        # Write to file
        with open(library, "a") as f_object:
            writer_object = writer(f_object)
            writer_object.writerow(file_reference)
            f_object.close()
    return result_list
```

```python
# Test that the search is working
result_output = get_articles("ppo reinforcement learning")
result_output[0]
```

??? note "輸出"

    ```text
    {'title': 'Proximal Policy Optimization and its Dynamic Version for Sequence Generation',
     'summary': 'In sequence generation task, many works use policy gradient for model\noptimization to tackle the intractable backpropagation issue when maximizing\nthe non-differentiable evaluation metrics or fooling the discriminator in\nadversarial learning. In this paper, we replace policy gradient with proximal\npolicy optimization (PPO), which is a proved more efficient reinforcement\nlearning algorithm, and propose a dynamic approach for PPO (PPO-dynamic). We\ndemonstrate the efficacy of PPO and PPO-dynamic on conditional sequence\ngeneration tasks including synthetic experiment and chit-chat chatbot. The\nresults show that PPO and PPO-dynamic can beat policy gradient by stability and\nperformance.',
     'article_url': 'http://arxiv.org/abs/1808.07982v1',
     'pdf_url': 'http://arxiv.org/pdf/1808.07982v1'}
    ```

```python
def strings_ranked_by_relatedness(
    query: str,
    df: pd.DataFrame,
    relatedness_fn=lambda x, y: 1 - spatial.distance.cosine(x, y),
    top_n: int = 100,
) -> list[str]:
    """Returns a list of strings and relatednesses, sorted from most related to least."""
    query_embedding_response = embedding_request(query)
    query_embedding = query_embedding_response.data[0].embedding
    strings_and_relatednesses = [
        (row["filepath"], relatedness_fn(query_embedding, row["embedding"]))
        for i, row in df.iterrows()
    ]
    strings_and_relatednesses.sort(key=lambda x: x[1], reverse=True)
    strings, relatednesses = zip(*strings_and_relatednesses)
    return strings[:top_n]
```

```python
def read_pdf(filepath):
    """Takes a filepath to a PDF and returns a string of the PDF's contents"""
    # creating a pdf reader object
    reader = PdfReader(filepath)
    pdf_text = ""
    page_number = 0
    for page in reader.pages:
        page_number += 1
        pdf_text += page.extract_text() + f"\nPage Number: {page_number}"
    return pdf_text


# Split a text into smaller chunks of size n, preferably ending at the end of a sentence
def create_chunks(text, n, tokenizer):
    """Returns successive n-sized chunks from provided text."""
    tokens = tokenizer.encode(text)
    i = 0
    while i < len(tokens):
        # Find the nearest end of sentence within a range of 0.5 * n and 1.5 * n tokens
        j = min(i + int(1.5 * n), len(tokens))
        while j > i + int(0.5 * n):
            # Decode the tokens and check for full stop or newline
            chunk = tokenizer.decode(tokens[i:j])
            if chunk.endswith(".") or chunk.endswith("\n"):
                break
            j -= 1
        # If no end of sentence found, use n tokens as the chunk size
        if j == i + int(0.5 * n):
            j = min(i + n, len(tokens))
        yield tokens[i:j]
        i = j


def extract_chunk(content, template_prompt):
    """This function applies a prompt to some input content. In this case it returns a summarized chunk of text"""
    prompt = template_prompt + content
    response = client.chat.completions.create(
        model=GPT_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0
    )
    return response.choices[0].message.content


def summarize_text(query):
    """This function does the following:
    - Reads in the arxiv_library.csv file in including the embeddings
    - Finds the closest file to the user's query
    - Scrapes the text out of the file and chunks it
    - Summarizes each chunk in parallel
    - Does one final summary and returns this to the user"""

    # A prompt to dictate how the recursive summarizations should approach the input paper
    summary_prompt = """Summarize this text from an academic paper. Extract any key points with reasoning.\n\nContent:"""

    # If the library is empty (no searches have been performed yet), we perform one and download the results
    library_df = pd.read_csv(paper_dir_filepath).reset_index()
    if len(library_df) == 0:
        print("No papers searched yet, downloading first.")
        get_articles(query)
        print("Papers downloaded, continuing")
        library_df = pd.read_csv(paper_dir_filepath).reset_index()
    else:
        print("Existing papers found... Articles:", len(library_df))
    library_df.columns = ["title", "filepath", "embedding"]
    library_df["embedding"] = library_df["embedding"].apply(ast.literal_eval)
    strings = strings_ranked_by_relatedness(query, library_df, top_n=1)
    print("Chunking text from paper")
    pdf_text = read_pdf(strings[0])

    # Initialise tokenizer
    tokenizer = tiktoken.get_encoding("cl100k_base")
    results = ""

    # Chunk up the document into 1500 token chunks
    chunks = create_chunks(pdf_text, 1500, tokenizer)
    text_chunks = [tokenizer.decode(chunk) for chunk in chunks]
    print("Summarizing each chunk of text")

    # Parallel process the summaries
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(text_chunks)
    ) as executor:
        futures = [
            executor.submit(extract_chunk, chunk, summary_prompt)
            for chunk in text_chunks
        ]
        with tqdm(total=len(text_chunks)) as pbar:
            for _ in concurrent.futures.as_completed(futures):
                pbar.update(1)
        for future in futures:
            data = future.result()
            results += data

    # Final summary
    print("Summarizing into overall summary")
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[
            {
                "role": "user",
                "content": f"""Write a summary collated from this collection of key points extracted from an academic paper.
                        The summary should highlight the core argument, conclusions and evidence, and answer the user's query.
                        User query: {query}
                        The summary should be structured in bulleted lists following the headings Core Argument, Evidence, and Conclusions.
                        Key points:\n{results}\nSummary:\n""",
            }
        ],
        temperature=0,
    )
    return response
```

```python
# Test the summarize_text function works
chat_test_response = summarize_text("PPO reinforcement learning sequence generation")
```

??? note "輸出"

    ```text
    Existing papers found... Articles: 10
    Chunking text from paper
    Summarizing each chunk of text
    ```

    ```text
    100%|███████████████████████████████████████████████████████████████████████████████████████████| 4/4 [00:05<00:00,  1.40s/it]
    ```

    ```text
    Summarizing into overall summary
    ```

```python
display(Markdown(chat_test_response.choices[0].message.content))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## Configure Agent

這一步建立 agent，包含支援多輪 API 呼叫的 ```Conversation``` class，以及幾個讓 ```ChatCompletion``` API 跟知識庫 function 互動的 Python 函式。

```python
@retry(wait=wait_random_exponential(min=1, max=40), stop=stop_after_attempt(3))
def chat_completion_request(messages, functions=None, model=GPT_MODEL):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            functions=functions,
        )
        return response
    except Exception as e:
        print("Unable to generate ChatCompletion response")
        print(f"Exception: {e}")
        return e
```

```python
class Conversation:
    def __init__(self):
        self.conversation_history = []

    def add_message(self, role, content):
        message = {"role": role, "content": content}
        self.conversation_history.append(message)

    def display_conversation(self, detailed=False):
        role_to_color = {
            "system": "red",
            "user": "green",
            "assistant": "blue",
            "function": "magenta",
        }
        for message in self.conversation_history:
            print(
                colored(
                    f"{message['role']}: {message['content']}\n\n",
                    role_to_color[message["role"]],
                )
            )
```

```python
# Initiate our get_articles and read_article_and_summarize functions
arxiv_functions = [
    {
        "name": "get_articles",
        "description": """Use this function to get academic papers from arXiv to answer user questions.""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": f"""
                            User query in JSON. Responses should be summarized and should include the article URL reference
                            """,
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_article_and_summarize",
        "description": """Use this function to read whole papers and provide a summary for users.
        You should NEVER call this function before get_articles has been called in the conversation.""",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": f"""
                            Description of the article in plain text based on the user's query
                            """,
                }
            },
            "required": ["query"],
        },
    }
]
```

```python
def chat_completion_with_function_execution(messages, functions=[None]):
    """This function makes a ChatCompletion API call with the option of adding functions"""
    response = chat_completion_request(messages, functions)
    full_message = response.choices[0]
    if full_message.finish_reason == "function_call":
        print(f"Function generation requested, calling function")
        return call_arxiv_function(messages, full_message)
    else:
        print(f"Function not required, responding to user")
        return response


def call_arxiv_function(messages, full_message):
    """Function calling function which executes function calls when the model believes it is necessary.
    Currently extended by adding clauses to this if statement."""

    if full_message.message.function_call.name == "get_articles":
        try:
            parsed_output = json.loads(
                full_message.message.function_call.arguments
            )
            print("Getting search results")
            results = get_articles(parsed_output["query"])
        except Exception as e:
            print(parsed_output)
            print(f"Function execution failed")
            print(f"Error message: {e}")
        messages.append(
            {
                "role": "function",
                "name": full_message.message.function_call.name,
                "content": str(results),
            }
        )
        try:
            print("Got search results, summarizing content")
            response = chat_completion_request(messages)
            return response
        except Exception as e:
            print(type(e))
            raise Exception("Function chat request failed")

    elif (
        full_message.message.function_call.name == "read_article_and_summarize"
    ):
        parsed_output = json.loads(
            full_message.message.function_call.arguments
        )
        print("Finding and reading paper")
        summary = summarize_text(parsed_output["query"])
        return summary

    else:
        raise Exception("Function does not exist and cannot be called")
```

## arXiv conversation

把前面的東西串起來，用對話測試這些 function。

```python
# Start with a system message
paper_system_message = """You are arXivGPT, a helpful assistant pulls academic papers to answer user questions.
You summarize the papers clearly so the customer can decide which to read to answer their question.
You always provide the article_url and title so the user can understand the name of the paper and click through to access it.
Begin!"""
paper_conversation = Conversation()
paper_conversation.add_message("system", paper_system_message)
```

```python
# Add a user message
paper_conversation.add_message("user", "Hi, how does PPO reinforcement learning work?")
chat_response = chat_completion_with_function_execution(
    paper_conversation.conversation_history, functions=arxiv_functions
)
assistant_message = chat_response.choices[0].message.content
paper_conversation.add_message("assistant", assistant_message)
display(Markdown(assistant_message))
```

??? note "輸出"

    ```text
    Function generation requested, calling function
    Getting search results
    Got search results, summarizing content
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

```python
# Add another user message to induce our system to use the second tool
paper_conversation.add_message(
    "user",
    "Can you read the PPO sequence generation paper for me and give me a summary",
)
updated_response = chat_completion_with_function_execution(
    paper_conversation.conversation_history, functions=arxiv_functions
)
display(Markdown(updated_response.choices[0].message.content))
```

??? note "輸出"

    ```text
    Function generation requested, calling function
    Finding and reading paper
    Existing papers found... Articles: 20
    Chunking text from paper
    Summarizing each chunk of text
    ```

    ```text
    100%|███████████████████████████████████████████████████████████████████████████████████████████| 4/4 [00:04<00:00,  1.21s/it]
    ```

    ```text
    Summarizing into overall summary
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

## 重點整理
- agent 的核心是讓模型根據對話內容，自己決定要不要呼叫 function、呼叫哪一個。
- 多個 function 可以組成工作流程，前一個的結果要存起來，後一個才接得上。
- 先搜尋再精讀，是處理大量文件很實用的分工：第一步縮小範圍，第二步才花 token 讀全文。
- `Conversation` class 負責保存對話歷史，多輪互動才有上下文。
- 論文庫的 embedding 存在 CSV，這是最輕量的知識庫做法，規模大了可換向量資料庫。

## 練習
1. 把 `./data/papers` 換成別的資料夾，確認論文有下載到新位置。
2. 改 `get_articles` 一次回傳的文章數量，看看對話中 agent 的回答有什麼不同。
3. 新增第三個 function（例如列出已下載過的論文），把它加進 agent 可呼叫的 function 清單，並問一個會用到它的問題。

<!-- 保留原文 inline code 片段供 i18n check 比對：` class to support multiple turns with the API, and some Python functions to enable interaction between the ` ` here). We create a file ` ` to store the embeddings and details for downloaded papers to retrieve against using ` -->
