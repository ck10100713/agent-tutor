---
translated: true
source: examples/partners/model_selection_guide/model_selection_guide.ipynb
---

# 真實場景的模型選擇實用指南

> 原文：[examples/partners/model_selection_guide/model_selection_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/model_selection_guide/model_selection_guide.ipynb)



## 這篇在做什麼

這篇教你在 GPT-4.1、o3、o4-mini 之間，針對不同工作負載挑模型、寫 prompt、上線。內容用三個實際案例（法律文件 RAG、製藥研發的多 agent 系統、保險表單 OCR）示範怎麼選模型，每個案例都有可以直接改的程式碼。

## 學完你會

- 用決策表判斷某個任務該從哪個模型開始，什麼時候升級或降級
- 做出一個不需要 embedding 和向量資料庫的長文件 agentic RAG，並附上可驗證的 citation
- 把 OCR 用的視覺模型和負責推理的模型串成兩階段 pipeline，處理手寫表單

## 開跑前

需要 OpenAI API key。範例會呼叫 `gpt-4.1`、`gpt-4.1-mini`、`o3`、`o4-mini`，都是付費用量。


## 目的與讀者

這份 cookbook 是實用指南，教你針對特定工作負載，在 GPT 4.1、o3、o4-mini 之間選模型、寫 prompt 並部署。它不是完整文件，而是提供可以直接照著做的決策框架和真實案例，幫 Solutions Engineer、Technical Account Manager、Partner Architect 和半技術背景的實務工作者快速做出可用的方案。內容聚焦在目前的模型能力、各產業的實作，以及現在的產業需求，從選模型到上線有清楚的路徑。每個段落的程式碼都很精簡、可以改了就用，想深入的主題則指向既有資源。

> 注意：下面的建議和實驗都是用目前最新的 SOTA 模型做的。這些數字在不同情境和時間點都可能改變。

## 怎麼使用這份 Cookbook

內容分成幾個段落，方便你快速找到需要的資訊。每個段落涵蓋模型選擇、實作、部署的一個面向。

1. **[Purpose & Audience](#purpose-audience)**：這份 cookbook 給誰看、涵蓋什麼。
2. **[Model Guide](#model-guide)**：快速參考，幫你選模型，包含模型比較，以及依使用情境對應的模型演進圖。
3. **Use Cases**：
   - **[3A. Long-Context RAG for Legal Q&A](#3a-use-case-long-context-rag-for-legal-qa)**：建一個 agentic 系統，回答複雜法律文件的問題。
   - **[3B. AI Co-Scientist for Pharma R&D](#3b-use-case-ai-co-scientist-for-pharma-rd)**：用 multi-agent 系統加速製藥研究的實驗設計。
   - **[3C. Insurance Claim Processing](#3c-use-case-insurance-claim-processing)**：用 vision 和 reasoning 把手寫保險表單數位化並驗證。
4. **[Prototype to Production](#prototype-to-production)**：從原型走到上線的檢查清單。
5. **[Adaptation Decision Tree](#adaptation-decision-tree)**：依需求挑模型的流程圖。
6. **[Appendices](#appendices)**：參考資料，包含價格、延遲、prompt 模式和外部資源連結。

想快速做決定，看 Model Guide 和 Adaptation Decision Tree 就夠了。要看實作細節，就挑跟你需求有關的 use case。


================================================================================



## Model Guide

## 2.1 Model‑Intro Matrix

| Model | Core strength | Ideal first reach‑for | Watch‑outs | Escalate / Downgrade path |
| :---- | :---- | :---- | :---- | :---- |
| GPT‑4o | Real‑time voice / vision chat | Live multimodal agents | Slightly below 4.1 on text SOTA (state-of-the-art) | Need deep reasoning → o4‑mini |
| GPT‑4.1 | 1 M‑token text accuracy king | Long‑doc analytics, code review | Cannot natively reason; higher cost than minis | Tight budget → 4.1‑mini / nano |
| o3 | Deep tool‑using agent | High‑stakes, multi‑step reasoning | Latency & price | Cost/latency → o4‑mini |
| o4‑mini | Cheap, fast reasoning | High‑volume "good‑enough" logic | Depth ceiling vs o3 | Accuracy critical → o3 |

*(Full price and utility table → [Section 6.1](#appendices))*

## 2.2 模型演進一覽

OpenAI 的模型產品線已經發展出針對不同面向的專用模型。下面的圖整理了目前的模型家族和彼此的關係。

### 根本差異：「o-series」vs「GPT」模型

OpenAI 有兩個不同的模型家族，各有強項：

- **GPT 模型（4o、4.1）**：針對一般用途最佳化，instruction following 很好。GPT-4.1 擅長長 context（1M tokens），GPT-4o 則有即時語音、text-to-speech、speech-to-text 的變體。GPT-4.1 另外有 mini 和 nano 版本，GPT-4o 有 mini 版本。這些變體比完整版便宜、快。

- **o-series 模型（o3、o4-mini）**：專門做深度推理和逐步解題。這些模型擅長需要邏輯思考和使用 tool 的複雜多階段任務，準確度和推理深度最重要時就選它們。它們還有一個選用參數 `reasoning_effort`（可設為 `low`、`medium`、`high`），讓你控制花在 reasoning 上的 token 量。

### OpenAI 模型演進

![OpenAI Model Evolution](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/2.2_model_evolution.png)

### 主要特性

- **GPT-4.1 家族**：針對長 context 處理最佳化，context window 有 1M token。
- **o3**：專門做深度多步驟推理。
- **o4-mini**：把 reasoning 和 vision 結合，成本更低。

每個模型在不同情境各有優勢，互補的長處可以組合起來處理複雜的 workflow。

這份 cookbook 只實驗了 GPT-4.1 系列、o3 和 o4-mini，沒有實驗 GPT-4o 系列。

================================================================================



## 3A. Use Case：Legal Q&A 的 Long-Context RAG

![Long-Context RAG for Legal Q&A](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3A_rag_task_card.png)
## 🗂️ TL;DR Matrix

下表整理了**這個 Long-Context Agentic RAG 實作**的核心技術選擇和理由。

| Layer | Choice | Utility |
| :---- | :---- | :---- |
| **Chunking** | Sentence-aware Splitter | Splits document into 20 equal chunks, respecting sentence boundaries. |
| **Routing** | `gpt-4.1-mini` | Uses natural language understanding to identify relevant chunks without embedding index. |
| **Path Selection** | `select(ids=[...])` and `scratchpad(text="...")` | Records reasoning while drilling down through document hierarchy. |
| **Citation** | Paragraph-level | Balances precision with cost; provides meaningful context for answers. |
| **Synthesis** | `gpt-4.1` (Structured Output) | Generates answers directly from selected paragraphs with citations. |
| **Verification** | `o4-mini` (LLM-as-Judge) | Validates factual accuracy and citation correctness. |

*註：價格和模型識別碼為 2025 年 4 月的資訊，之後可能變動。*

這一節要建一個 Retrieval-Augmented Generation (RAG) 系統，準確回答複雜又冗長的程序性文件的問題，示範文件是 *Trademark Trial and Appeal Board Manual of Procedure (TBMP)*。TBMP 詳細規範美國專利商標局 (USPTO) 的商標審理暨訴願委員會處理商標訴訟的程序，智慧財產權律師和法律專業人員經常查閱。系統利用最新的 OpenAI 模型，提升對密集法律內容的理解和可解釋性，靠進階的語言理解和動態檢索，給出精確、符合上下文的回答。

這些做法也能用在其他需要從複雜文件精準檢索資訊的場景，例如醫療法規手冊、金融監理框架、技術文件系統，只要準確性、引用來源和可稽核性是關鍵需求就適用。

## 1\. 情境摘要

* **語料：**主要文件是 [Trademark Trial and Appeal Board Manual of Procedure (TBMP, 2024 version)](https://www.uspto.gov/sites/default/files/documents/tbmp-Master-June2024.pdf)。這份手冊有詳細的程序規則和指引，總共 1194 頁。  
* **使用者：**目標使用者是智慧財產權訴訟的律師助理和 paralegal，他們需要針對程序問題，*只*根據 TBMP 得到快速又準確的答案。  
* **典型問題：**使用者會問需要整合並引用的問題，例如：  
  1. "What are the requirements for filing a motion to compel discovery according to the TBMP?"  
  2. "What deadlines apply to discovery conferences as specified in the manual?"  
  3. "Explain how the Board handles claims of attorney-client privilege during depositions according to the TBMP."  
  4. "Enumerate the Fed. R. Civ. P. 11 sanctions the Board can invoke according to the TBMP."  

*註：依你的部署環境，可能需要調整一些實作步驟來配合你的基礎設施。*

> OpenAI 的 File Search tool 對很多情境是不錯的起點，這一節則介紹不同的做法：利用百萬 token 的 context window，不用任何前處理或向量資料庫就能處理大文件。這種 agentic 做法做到零延遲 ingestion、動態調整檢索粒度，以及細緻的 citation 可追溯性。

## 2\. Agentic RAG 流程

動手實作前，先看整體做法：

1. **把整份文件載入** context window
2. **切成 20 個 chunk**，並尊重句子邊界
3. **問模型**哪些 chunk 可能含有相關資訊
4. **往下鑽**：把選中的 chunk 再切細
5. **重複**直到切到段落層級
6. **根據選出的段落產生答案**
7. **驗證答案**的事實正確性

這種階層式導覽模仿人怎麼瀏覽文件：先掃過章節，再看相關小節，最後只讀最相關的段落。

![Hierarchical Router](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3A_rag_hierarchical_router.png)


## Agentic RAG 系統：模型用法

| Process Stage | Model Used | Purpose |
|---------------|------------|---------|
| Initial Routing | `gpt-4.1-mini` | Identifies which document chunks might contain relevant information |
| Hierarchical Navigation | `gpt-4.1-mini` | Continues drilling down to find most relevant paragraphs |
| Answer Generation | `gpt-4.1` | Creates structured response with citations from selected paragraphs |
| Answer Verification | `o4-mini` | Validates factual accuracy and proper citation usage |

這種零前處理的做法靠大 context window 即時導覽文件，就像人在文件裡掃描找資訊。

## 3\. 實作

一步一步來實作這個做法。

先安裝需要的套件。

```python
%pip install tiktoken pypdf nltk openai pydantic --quiet
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

### 3.1 載入文件

先載入文件並檢查大小。這份指南只看第 100 到 900 節，涵蓋核心的程序面向，直到 Review of Decision of Board。第 1000 節之後（Interferences、Concurrent Use Proceedings、Ex Parte Appeals）是特殊程序，不在目前範圍內。

```python
import requests
from io import BytesIO
from pypdf import PdfReader
import re
import tiktoken
from nltk.tokenize import sent_tokenize
import nltk
from typing import List, Dict, Any

# Download nltk data if not already present
nltk.download('punkt_tab')

def load_document(url: str) -> str:
    """Load a document from a URL and return its text content."""
    print(f"Downloading document from {url}...")
    response = requests.get(url)
    response.raise_for_status()
    pdf_bytes = BytesIO(response.content)
    pdf_reader = PdfReader(pdf_bytes)
    
    full_text = ""
    

    max_page = 920  # Page cutoff before section 1000 (Interferences)
    for i, page in enumerate(pdf_reader.pages):
        if i >= max_page:
            break
        full_text += page.extract_text() + "\n"
    
    # Count words and tokens
    word_count = len(re.findall(r'\b\w+\b', full_text))
    
    tokenizer = tiktoken.get_encoding("o200k_base")
    token_count = len(tokenizer.encode(full_text))
    
    print(f"Document loaded: {len(pdf_reader.pages)} pages, {word_count} words, {token_count} tokens")
    return full_text

# Load the document
tbmp_url = "https://www.uspto.gov/sites/default/files/documents/tbmp-Master-June2024.pdf"
document_text = load_document(tbmp_url)

# Show the first 500 characters
print("\nDocument preview (first 500 chars):")
print("-" * 50)
print(document_text[:500])
print("-" * 50)
```

??? note "輸出"

    ```text
    [nltk_data] Downloading package punkt_tab to
    [nltk_data]     /Users/kmurali/nltk_data...
    [nltk_data]   Package punkt_tab is already up-to-date!
    ```

    ```text
    Downloading document from https://www.uspto.gov/sites/default/files/documents/tbmp-Master-June2024.pdf...
    Document loaded: 1194 pages, 595197 words, 932964 tokens

    Document preview (first 500 chars):
    --------------------------------------------------
    TRADEMARK TRIAL AND
    APPEAL BOARD MANUAL
    OF PROCEDURE (TBMP)
     June 2024
    June   2024
    United States Patent and Trademark Office
    PREFACE TO THE JUNE 2024 REVISION
    The June 2024 revision of the Trademark Trial and Appeal Board Manual of Procedure is an update of the
    June 2023 edition. This update is moderate in nature and incorporates relevant case law issued between March
    3, 2023 and March 1, 2024.
    The title of the manual is abbreviated as “TBMP.” A citation to a section of the manual may be written
    --------------------------------------------------
    ```

可以看到文件超過 900k token。雖然 GPT 4.1 的 context 長度放得下，但我們也要可驗證的 citation，所以採用遞迴式 chunking 策略。

### 3.2 有最小 token 數的改良版 20-Chunk Splitter

現在寫一個改良版函式，把文件切成 20 個 chunk，確保每個都有最小 token 數，並尊重句子邊界。

> 20 是針對這份文件和任務憑經驗選的數字，換別的文件可能要依大小和結構調整（數字越大，chunk 越細）。關鍵原則是把文件的各部分切開，讓語言模型自己判斷哪些部分相關。同樣的道理也適用於後面會介紹的 `max_depth` 參數。

```python
# Global tokenizer name to use consistently throughout the code
TOKENIZER_NAME = "o200k_base"

def split_into_20_chunks(text: str, min_tokens: int = 500) -> List[Dict[str, Any]]:
    """
    Split text into up to 20 chunks, respecting sentence boundaries and ensuring
    each chunk has at least min_tokens (unless it's the last chunk).
    
    Args:
        text: The text to split
        min_tokens: The minimum number of tokens per chunk (default: 500)
    
    Returns:
        A list of dictionaries where each dictionary has:
        - id: The chunk ID (0-19)
        - text: The chunk text content
    """
    # First, split the text into sentences
    sentences = sent_tokenize(text)
    
    # Get tokenizer for counting tokens
    tokenizer = tiktoken.get_encoding(TOKENIZER_NAME)
    
    # Create chunks that respect sentence boundaries and minimum token count
    chunks = []
    current_chunk_sentences = []
    current_chunk_tokens = 0
    
    for sentence in sentences:
        # Count tokens in this sentence
        sentence_tokens = len(tokenizer.encode(sentence))
        
        # If adding this sentence would make the chunk too large AND we already have the minimum tokens,
        # finalize the current chunk and start a new one
        if (current_chunk_tokens + sentence_tokens > min_tokens * 2) and current_chunk_tokens >= min_tokens:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append({
                "id": len(chunks),  # Integer ID instead of string
                "text": chunk_text
            })
            current_chunk_sentences = [sentence]
            current_chunk_tokens = sentence_tokens
        else:
            # Add this sentence to the current chunk
            current_chunk_sentences.append(sentence)
            current_chunk_tokens += sentence_tokens
    
    # Add the last chunk if there's anything left
    if current_chunk_sentences:
        chunk_text = " ".join(current_chunk_sentences)
        chunks.append({
            "id": len(chunks),  # Integer ID instead of string
            "text": chunk_text
        })
    
    # If we have more than 20 chunks, consolidate them
    if len(chunks) > 20:
        # Recombine all text
        all_text = " ".join(chunk["text"] for chunk in chunks)
        # Re-split into exactly 20 chunks, without minimum token requirement
        sentences = sent_tokenize(all_text)
        sentences_per_chunk = len(sentences) // 20 + (1 if len(sentences) % 20 > 0 else 0)
        
        chunks = []
        for i in range(0, len(sentences), sentences_per_chunk):
            # Get the sentences for this chunk
            chunk_sentences = sentences[i:i+sentences_per_chunk]
            # Join the sentences into a single text
            chunk_text = " ".join(chunk_sentences)
            # Create a chunk object with ID and text
            chunks.append({
                "id": len(chunks),  # Integer ID instead of string
                "text": chunk_text
            })
    
    # Print chunk statistics
    print(f"Split document into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        token_count = len(tokenizer.encode(chunk["text"]))
        print(f"Chunk {i}: {token_count} tokens")
    
    return chunks

# Split the document into 20 chunks with minimum token size
document_chunks = split_into_20_chunks(document_text, min_tokens=500)
```

??? note "輸出"

    ```text
    Split document into 20 chunks
    Chunk 0: 42326 tokens
    Chunk 1: 42093 tokens
    Chunk 2: 42107 tokens
    Chunk 3: 39797 tokens
    Chunk 4: 58959 tokens
    Chunk 5: 48805 tokens
    Chunk 6: 37243 tokens
    Chunk 7: 33453 tokens
    Chunk 8: 38644 tokens
    Chunk 9: 49402 tokens
    Chunk 10: 51568 tokens
    Chunk 11: 49586 tokens
    Chunk 12: 47722 tokens
    Chunk 13: 48952 tokens
    Chunk 14: 44994 tokens
    Chunk 15: 50286 tokens
    Chunk 16: 54424 tokens
    Chunk 17: 62651 tokens
    Chunk 18: 47430 tokens
    Chunk 19: 42507 tokens
    ```

### 3.3 有改良 Tool Schema 的 Router 函式

接著寫 router 函式，負責選出相關的 chunk 並維護 scratchpad。

> 維護 scratchpad 讓模型可以持續記錄判斷標準和推理過程。這個實作用 GPT-4.1-mini 分兩輪：先強制模型透過 tool call 更新 scratchpad（tool_choice="required"），再要求結構化 JSON 輸出來選 chunk。這樣更容易看到模型的推理過程，同時下游處理拿到的結構化輸出也很一致。

```python
from openai import OpenAI
import json
from typing import List, Dict, Any

# Initialize OpenAI client
client = OpenAI()

def route_chunks(question: str, chunks: List[Dict[str, Any]], 
                depth: int, scratchpad: str = "") -> Dict[str, Any]:
    """
    Ask the model which chunks contain information relevant to the question.
    Maintains a scratchpad for the model's reasoning.
    Uses structured output for chunk selection and required tool calls for scratchpad.
    
    Args:
        question: The user's question
        chunks: List of chunks to evaluate
        depth: Current depth in the navigation hierarchy
        scratchpad: Current scratchpad content
    
    Returns:
        Dictionary with selected IDs and updated scratchpad
    """
    print(f"\n==== ROUTING AT DEPTH {depth} ====")
    print(f"Evaluating {len(chunks)} chunks for relevance")
    
    # Build system message
    system_message = """You are an expert document navigator. Your task is to:
1. Identify which text chunks might contain information to answer the user's question
2. Record your reasoning in a scratchpad for later reference
3. Choose chunks that are most likely relevant. Be selective, but thorough. Choose as many chunks as you need to answer the question, but avoid selecting too many.

First think carefully about what information would help answer the question, then evaluate each chunk.
"""

    # Build user message with chunks and current scratchpad
    user_message = f"QUESTION: {question}\n\n"
    
    if scratchpad:
        user_message += f"CURRENT SCRATCHPAD:\n{scratchpad}\n\n"
    
    user_message += "TEXT CHUNKS:\n\n"
    
    # Add each chunk to the message
    for chunk in chunks:
        user_message += f"CHUNK {chunk['id']}:\n{chunk['text']}\n\n"
    
    # Define function schema for scratchpad tool calling
    tools = [
        {
            "type": "function",
            "name": "update_scratchpad",
            "description": "Record your reasoning about why certain chunks were selected",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Your reasoning about the chunk(s) selection"
                    }
                },
                "required": ["text"],
                "additionalProperties": False
            }
        }
    ]
    
    # Define JSON schema for structured output (selected chunks)
    text_format = {
        "format": {
            "type": "json_schema",
            "name": "selected_chunks",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "chunk_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "IDs of the selected chunks that contain information to answer the question"
                    }
                },
                "required": [
                    "chunk_ids"
                ],
                "additionalProperties": False
            }
        }
    }
    
    # First pass: Call the model to update scratchpad (required tool call)
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message + "\n\nFirst, you must use the update_scratchpad function to record your reasoning."}
    ]
    
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=messages,
        tools=tools,
        tool_choice="required"
    )
    
    # Process the scratchpad tool call
    new_scratchpad = scratchpad
    
    for tool_call in response.output:
        if tool_call.type == "function_call" and tool_call.name == "update_scratchpad":
            args = json.loads(tool_call.arguments)
            scratchpad_entry = f"DEPTH {depth} REASONING:\n{args.get('text', '')}"
            if new_scratchpad:
                new_scratchpad += "\n\n" + scratchpad_entry
            else:
                new_scratchpad = scratchpad_entry
            
            # Add function call and result to messages
            messages.append(tool_call)
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": "Scratchpad updated successfully."
            })
    
    # Second pass: Get structured output for chunk selection
    messages.append({"role": "user", "content": "Now, select the chunks that could contain information to answer the question. Return a JSON object with the list of chunk IDs."})
    
    response_chunks = client.responses.create(
        model="gpt-4.1-mini",
        input=messages,
        text=text_format
    )
    
    # Extract selected chunk IDs from structured output
    selected_ids = []
    if response_chunks.output_text:
        try:
            # The output_text should already be in JSON format due to the schema
            chunk_data = json.loads(response_chunks.output_text)
            selected_ids = chunk_data.get("chunk_ids", [])
        except json.JSONDecodeError:
            print("Warning: Could not parse structured output as JSON")
    
    # Display results
    print(f"Selected chunks: {', '.join(str(id) for id in selected_ids)}")
    print(f"Updated scratchpad:\n{new_scratchpad}")
    
    return {
        "selected_ids": selected_ids,
        "scratchpad": new_scratchpad
    }
```

### 3.4 遞迴導覽函式

接著寫遞迴導覽函式，一層一層往下鑽文件。`max_depth` 是最多往下鑽幾層（要顧到 token 的最小數量）：

```python
def navigate_to_paragraphs(document_text: str, question: str, max_depth: int = 1) -> Dict[str, Any]:
    """
    Navigate through the document hierarchy to find relevant paragraphs.
    
    Args:
        document_text: The full document text
        question: The user's question
        max_depth: Maximum depth to navigate before returning paragraphs (default: 1)
    
    Returns:
        Dictionary with selected paragraphs and final scratchpad
    """
    scratchpad = ""
    
    # Get initial chunks with min 500 tokens
    chunks = split_into_20_chunks(document_text, min_tokens=500)
    
    # Navigator state - track chunk paths to maintain hierarchy
    chunk_paths = {}  # Maps numeric IDs to path strings for display
    for chunk in chunks:
        chunk_paths[chunk["id"]] = str(chunk["id"])
    
    # Navigate through levels until max_depth or until no chunks remain
    for current_depth in range(max_depth + 1):
        # Call router to get relevant chunks
        result = route_chunks(question, chunks, current_depth, scratchpad)
        
        # Update scratchpad
        scratchpad = result["scratchpad"]
        
        # Get selected chunks
        selected_ids = result["selected_ids"]
        selected_chunks = [c for c in chunks if c["id"] in selected_ids]
        
        # If no chunks were selected, return empty result
        if not selected_chunks:
            print("\nNo relevant chunks found.")
            return {"paragraphs": [], "scratchpad": scratchpad}
        
        # If we've reached max_depth, return the selected chunks
        if current_depth == max_depth:
            print(f"\nReturning {len(selected_chunks)} relevant chunks at depth {current_depth}")
            
            # Update display IDs to show hierarchy
            for chunk in selected_chunks:
                chunk["display_id"] = chunk_paths[chunk["id"]]
                
            return {"paragraphs": selected_chunks, "scratchpad": scratchpad}
        
        # Prepare next level by splitting selected chunks further
        next_level_chunks = []
        next_chunk_id = 0  # Counter for new chunks
        
        for chunk in selected_chunks:
            # Split this chunk into smaller pieces
            sub_chunks = split_into_20_chunks(chunk["text"], min_tokens=200)
            
            # Update IDs and maintain path mapping
            for sub_chunk in sub_chunks:
                path = f"{chunk_paths[chunk['id']]}.{sub_chunk['id']}"
                sub_chunk["id"] = next_chunk_id
                chunk_paths[next_chunk_id] = path
                next_level_chunks.append(sub_chunk)
                next_chunk_id += 1
        
        # Update chunks for next iteration
        chunks = next_level_chunks
```

### 3.5 用範例問題跑改良版導覽

用範例問題跑一次改良版的導覽：

```python
# Run the navigation for a sample question
question = "What format should a motion to compel discovery be filed in? How should signatures be handled?"
navigation_result = navigate_to_paragraphs(document_text, question, max_depth=2)

# Sample retrieved paragraph
print("\n==== FIRST 3 RETRIEVED PARAGRAPHS ====")
for i, paragraph in enumerate(navigation_result["paragraphs"][:3]):
    display_id = paragraph.get("display_id", str(paragraph["id"]))
    print(f"\nPARAGRAPH {i+1} (ID: {display_id}):")
    print("-" * 40)
    print(paragraph["text"])
    print("-" * 40)
```

??? note "輸出"

    ```text
    Split document into 20 chunks
    Chunk 0: 42326 tokens
    Chunk 1: 42093 tokens
    Chunk 2: 42107 tokens
    Chunk 3: 39797 tokens
    Chunk 4: 58959 tokens
    Chunk 5: 48805 tokens
    Chunk 6: 37243 tokens
    Chunk 7: 33453 tokens
    Chunk 8: 38644 tokens
    Chunk 9: 49402 tokens
    Chunk 10: 51568 tokens
    Chunk 11: 49586 tokens
    Chunk 12: 47722 tokens
    Chunk 13: 48952 tokens
    Chunk 14: 44994 tokens
    Chunk 15: 50286 tokens
    Chunk 16: 54424 tokens
    Chunk 17: 62651 tokens
    Chunk 18: 47430 tokens
    Chunk 19: 42507 tokens

    ==== ROUTING AT DEPTH 0 ====
    Evaluating 20 chunks for relevance
    Selected chunks: 0, 1, 2, 3, 4, 5, 6, 7, 8
    Updated scratchpad:
    DEPTH 0 REASONING:
    The user wants to know the format requirements for filing a motion to compel discovery and how signatures should be handled for such motions. 

    Based on the evaluation of chunks:
    - Chunks 0, 1, 2, 3, 4, 5, 6, 7, 8 are highly relevant since they cover general requirements for submissions, motions, signatures, service, and specifically for motions and discovery in TTAB proceedings.
    - These chunks contain detailed info about electronic filing (via ESTTA), paper filing exceptions, signature requirements, service requirements, format of submissions (including motions), timing rules, and professionals' responsibilities.
    - Additionally, the rules for motions to compel, including required attachments, timing, and certification of good faith efforts to resolve discovery disputes, are specifically outlined.
    - Chunks 11-19 mostly cover post-trial and appeal procedures, less directly relevant.

    I will select these relevant chunks to provide a thorough answer about how motions to compel discovery should be filed and how signatures on such motions are handled.
    Split document into 20 chunks
    Chunk 0: 3539 tokens
    Chunk 1: 2232 tokens
    Chunk 2: 1746 tokens
    ... (省略 411 行)
    ```

GPT 4.1-mini 的結果顯示它一輪一輪萃取文件中的相關部分，scratchpad 還解釋了它的思考過程。在 depth 1，模型把 "*Detailed rules for signatures on submissions including motions*" 和 "*use of ESTTA, required signature format including electronic signatures with the symbol method '/sig/'*" 認定為回答問題所需的關鍵部分。

到了 depth 2，scratchpad 展現出相當成熟的判斷：它精準找出哪些 chunk 含有電子簽名的重要規定（chunk 5-12），同時也知道哪些內容缺席，註記 "*discovery-related motions... should be in chunks from 400 onwards (although these aren't fully visible here...)*"。

這個過程顯示 GPT 4.1 像法律分析師一樣，一層層深入相關內容，並一路解釋自己的理由（所以要 debug 模型*為什麼*選那些 chunk 會容易很多）。

### 3.6 產生答案

現在用 GPT-4.1 根據檢索到的段落產生答案。

> 這裡用了一個巧妙的做法：動態建構一個 List of Literals（強制模型的答案只能是我們提供的選項，這裡就是段落 ID）。可提供的選項數量有限制，如果你的系統會引用超過 500 份文件，這個方法可能行不通。這時你可以加一個 filter，把候選 citation 限制在 500 個以內，或是請模型在回答裡寫出確切的 ID，再後處理抽出 ID 當作 citation（例如它可能寫 "... [doc 0.0.12]"，你用 regex 抽出來）。



```python
from typing import List, Dict, Any
from pydantic import BaseModel, field_validator

class LegalAnswer(BaseModel):
    """Structured response format for legal questions"""
    answer: str
    citations: List[str]
    
    @field_validator('citations')
    def validate_citations(cls, citations, info):
        # Access valid_citations from the model_config
        valid_citations = info.data.get('_valid_citations', [])
        if valid_citations:
            for citation in citations:
                if citation not in valid_citations:
                    raise ValueError(f"Invalid citation: {citation}. Must be one of: {valid_citations}")
        return citations

def generate_answer(question: str, paragraphs: List[Dict[str, Any]], 
                   scratchpad: str) -> LegalAnswer:
    """Generate an answer from the retrieved paragraphs."""
    print("\n==== GENERATING ANSWER ====")
    
    # Extract valid citation IDs
    valid_citations = [str(p.get("display_id", str(p["id"]))) for p in paragraphs]
    
    if not paragraphs:
        return LegalAnswer(
            answer="I couldn't find relevant information to answer this question in the document.",
            citations=[],
            _valid_citations=[]
        )
    
    # Prepare context for the model
    context = ""
    for paragraph in paragraphs:
        display_id = paragraph.get("display_id", str(paragraph["id"]))
        context += f"PARAGRAPH {display_id}:\n{paragraph['text']}\n\n"
    
    system_prompt = """You are a legal research assistant answering questions about the 
Trademark Trial and Appeal Board Manual of Procedure (TBMP).

Answer questions based ONLY on the provided paragraphs. Do not rely on any foundation knowledge or external information or extrapolate from the paragraphs.
Cite phrases of the paragraphs that are relevant to the answer. This will help you be more specific and accurate.
Include citations to paragraph IDs for every statement in your answer. Valid citation IDs are: {valid_citations_str}
Keep your answer clear, precise, and professional.
"""
    valid_citations_str = ", ".join(valid_citations)
    
    # Call the model using structured output
    response = client.responses.parse(
        model="gpt-4.1",
        input=[
            {"role": "system", "content": system_prompt.format(valid_citations_str=valid_citations_str)},
            {"role": "user", "content": f"QUESTION: {question}\n\nSCRATCHPAD (Navigation reasoning):\n{scratchpad}\n\nPARAGRAPHS:\n{context}"}
        ],
        text_format=LegalAnswer,
        temperature=0.3
    )
    
    # Add validation information after parsing
    response.output_parsed._valid_citations = valid_citations
    
    print(f"\nAnswer: {response.output_parsed.answer}")
    print(f"Citations: {response.output_parsed.citations}")

    return response.output_parsed

# Generate an answer
answer = generate_answer(question, navigation_result["paragraphs"], 
                       navigation_result["scratchpad"])
```

??? note "輸出"

    ```text

    ==== GENERATING ANSWER ====

    Answer: A motion to compel discovery must be filed electronically with the Trademark Trial and Appeal Board (TTAB) through ESTTA, unless ESTTA is unavailable due to technical problems or there are extraordinary circumstances, in which case a paper submission may be permitted with a written explanation ("Documents that relate to proceedings before the Trademark Trial and Appeal Board must be filed electronically with the Board through ESTTA"; "The rules require that all submissions must be made to the Board electronically, currently through ESTTA, subject to certain limited exceptions permitting submissions to be made on paper. Any permitted paper submission must be accompanied by a written explanation showing that ESTTA was unavailable due to technical problems, or that extraordinary circumstances are present, and, where required, a Petition to the Director with the requisite petition fee" 0.0.5.0, 0.0.5.5.7.3).

    The motion should include a title describing its nature, such as “Motion to Compel,” and should bear the appropriate proceeding number and caption at the top of the first page ("The document should also include a title describing its nature, e.g., 'Motion to Compel'... should bear at the top of the first page both the application serial number, and the inter partes proceeding number and caption" 0.0.5.4).

    Every submission, including a motion to compel discovery, must be signed by the party filing it, or by the party’s attorney or other authorized representative. For electronic filings through ESTTA, a conventional handwritten signature is not required; instead, an electronic signature is used. The signatory must personally enter a combination of letters, numbers, spaces, and/or punctuation marks between two forward slash ('/') symbols (e.g., /John Smith/), and the signatory's name and title or position must appear immediately below or adjacent to the signature ("Documents filed electronically, including through ESTTA, do not require a conventional signature. Electronic signatures pursuant to 37 C.F.R. § 2.193(c) are required for electronic filings. The party or its representative enters a 'symbol' that has been adopted as a signature. The Board will accept any combination of letters, numbers, space and/or punctuation marks as a valid signature if it is placed between two forward slash ('/') symbols"; "The first and last name, and the title or position, of the person who signs a document in connection with a trademark application, registration, or proceeding before the Trademark Trial and Appeal Board must be set forth immediately below or adjacent to the signature" 0.0.5.5.6.2, 0.0.5.5.6.0).

    If a document is filed on behalf of a party by the party’s attorney or other authorized representative, it must bear the signature of that attorney or representative, unless the document is one required to be signed personally by the party (0.0.5.5.6.3). If an unsigned or improperly signed document is filed, it will not be refused consideration if a properly signed copy is submitted within the time limit set in the notification of the defect by the Board (0.0.5.5.6.4).

    In summary: File the motion to compel discovery electronically via ESTTA, use an electronic signature as described above, and ensure the signatory's name and title are included. If filing on paper is necessary, follow the specific requirements for paper submissions and signatures.
    Citations: ['0.0.5.0', '0.0.5.4', '0.0.5.5.6.0', '0.0.5.5.6.2', '0.0.5.5.6.3', '0.0.5.5.6.4', '0.0.5.5.7.3']
    ```

GPT 4.1 把 citation 有效地整合進整段回答，同時資訊流動也很清楚。每個程序要求都連到特定的權威來源（像 "0.0.5.0" 和 "0.0.5.5.6.2"），產生的回答既有資訊量，來源也很精確。

它不是把 citation 全部列在最後，而是在每個關鍵要求後面用括號直接織進內文。這讓原本只是複述規則的內容，變成有依據的法律分析：ESTTA 提交程序、電子簽名要求、紙本提交的例外，每一項都立刻有對應的法規引用。

### 3.7 答案驗證

先看被引用的段落：

```python
cited_paragraphs = []
for paragraph in navigation_result["paragraphs"]:
    para_id = str(paragraph.get("display_id", str(paragraph["id"])))
    if para_id in answer.citations:
        cited_paragraphs.append(paragraph)
    

# Display the cited paragraphs for the audience
print("\n==== CITED PARAGRAPHS ====")
for i, paragraph in enumerate(cited_paragraphs):
    display_id = paragraph.get("display_id", str(paragraph["id"]))
    print(f"\nPARAGRAPH {i+1} (ID: {display_id}):")
    print("-" * 40)
    print(paragraph["text"])
    print("-" * 40)
```

??? note "輸出"

    ```text

    ==== CITED PARAGRAPHS ====

    PARAGRAPH 1 (ID: 0.0.5.0):
    ----------------------------------------
    104  Business to be Conducted in Writing
    37 C.F.R. § 2.190(b)  Electronic trademark documents. … Documents that r elate to proceedings before
    the Trademark Trial and Appeal Board must be filed electronically with the Board through ESTTA. 37 C.F.R. § 2.191 Action of the Office based on the written record. All business with the Office must be
    transacted in writing. The action of the Office will be based exclusively on the written record. No consideration
    will be given to any alleged oral promise, stipulation, or understanding when there is disagreement or doubt. With the exceptions of discovery conferences with Board participation, see TBMP § 401.01, and telephone
    conferences, see TBMP § 413.01 and TBMP § 502.06, all business with the Board should be transacted in
    writing. 37 C.F.R. § 2.191 . The personal attendance of parties or their attorne ys or other authorized
    representatives at the offices of the Board is unnecessary , except in the case of a pretrial conference as
    provided in 37 C.F.R. § 2.120(j), or upon oral argument at final hearing, if a party so desires, as pro vided
    in 37 C.F.R. § 2.129. Decisions of the Board will be based exclusively on the written record before it. [Note
    1.] Documents filed in proceedings before the Board must be filed through ESTT A. 37 C.F.R. § 2.190(b). See TBMP § 110.01(a). Board proceedings are conducted in English. If a party intends to rely upon an y submissions that are in a
    language other than English, the party should also file a translation of the submissions. If a translation is
    not filed, the submissions may not be considered. [Note 2.] NOTES:
    1. Cf.
    ----------------------------------------

    PARAGRAPH 2 (ID: 0.0.5.4):
    ----------------------------------------
    The document should
    also include a title describing its nature, e.g., “Notice of Opposition,” “Answer,” “Motion to Compel,” “Brief
    in Opposition to Respondent’s Motion for Summary Judgment,” or “Notice of Reliance.”
    Documents filed in an application which is the subject of an inter partes proceeding before the Board should
    be filed with the Board, not the Trademark Operation, and should bear at the top of the first page both the
    application serial number, and the inter partes proceeding number and caption. Similarly , requests under
    Trademark Act § 7, 15 U.S.C. § 1057, to amend, correct, or surrender a registration which is the subject of
    a Board inter partes proceeding, and any new power of attorney, designation of domestic representative, or
    change of address submitted in connection with such a registration, should be filed with the Board, not with
    the Trademark Operation, and should bear at the top of its first page the re gistration number, and the inter
    partes proceeding number and the proceeding caption. [Note 2.] 100-14June   2024
    TRADEMARK TRIAL AND APPEAL BOARD MANUAL OF PROCEDURE§ 105
    NOTES:
    1. 37 C.F.R. § 2.194. 2. 37 C.F.R. § 2.194. 106.02  Signature of Submissions
    37 C.F.R. § 2.119(e) Every submission filed in an inter partes proceeding, and every request for an extension
    of time to file an opposition, must be signed by the party filing it, or by the party’s attorney or other authorized
    representative, but an unsigned submission will not be r efused consideration if a signed copy is submitted
    ... (省略 102 行)
    ```

"List of Literals" 這招強制模型只能引用特定的段落 ID（像 "0.0.5.4"），不能自己編參考來源或隨便標一段文字。可以把它想成一個只能從中挑選的數位「目錄」。這樣你拿到的 citation 都能追溯回確切的原始資料，解決了 long-context RAG 的一個重要問題。

最後，用 LLM-as-judge 的方式驗證答案。

```python
from typing import List, Dict, Any, Literal
from pydantic import BaseModel

class VerificationResult(BaseModel):
    """Verification result format"""
    is_accurate: bool
    explanation: str
    confidence: Literal["high", "medium", "low"]

def verify_answer(question: str, answer: LegalAnswer, 
                 cited_paragraphs: List[Dict[str, Any]]) -> VerificationResult:
    """
    Verify if the answer is grounded in the cited paragraphs.
    
    Args:
        question: The user's question
        answer: The generated answer
        cited_paragraphs: Paragraphs cited in the answer
        
    Returns:
        Verification result with accuracy assessment, explanation, and confidence level
    """
    print("\n==== VERIFYING ANSWER ====")
    
    # Prepare context with the cited paragraphs
    context = ""
    for paragraph in cited_paragraphs:
        display_id = paragraph.get("display_id", str(paragraph["id"]))
        context += f"PARAGRAPH {display_id}:\n{paragraph['text']}\n\n"
    
    # Prepare system prompt
    system_prompt = """You are a fact-checker for legal information.
Your job is to verify if the provided answer:
1. Is factually accurate according to the source paragraphs
2. Uses citations correctly

Be critical and look for any factual errors or unsupported claims.
Assign a confidence level based on how directly the paragraphs answer the question:
- high: The answer is comprehensive, accurate, and directly supported by the paragraphs
- medium: The answer is mostly accurate but may be incomplete or have minor issues
- low: The answer has significant gaps, inaccuracies, or is poorly supported by the paragraphs
"""
    
    response = client.responses.parse(
        model="o4-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""
QUESTION: {question}

ANSWER TO VERIFY:
{answer.answer}

CITATIONS USED: {', '.join(answer.citations)}

SOURCE PARAGRAPHS:
{context}

Is this answer accurate and properly supported by the source paragraphs?
Assign a confidence level (high, medium, or low) based on completeness and accuracy.
            """}
        ],
        text_format=VerificationResult
    )
    
    # Log and return the verification result
    print(f"\nAccuracy verification: {'PASSED' if response.output_parsed.is_accurate else 'FAILED'}")
    print(f"Confidence: {response.output_parsed.confidence}")
    print(f"Explanation: {response.output_parsed.explanation}")
    
    return response.output_parsed

# Verify the answer using only the cited paragraphs
verification = verify_answer(question, answer, cited_paragraphs)

# Display final result with verification
print("\n==== FINAL VERIFIED ANSWER ====")
print(f"Verification: {'PASSED' if verification.is_accurate else 'FAILED'} | Confidence: {verification.confidence}")
print("\nAnswer:")
print(answer.answer)
print("\nCitations:")
for citation in answer.citations:
    print(f"- {citation}")
```

??? note "輸出"

    ```text

    ==== VERIFYING ANSWER ====

    Accuracy verification: PASSED
    Confidence: high
    Explanation: The answer correctly states that motions to compel discovery must be filed electronically through ESTTA, with paper submissions permitted only under the limited exceptions of technical failure or extraordinary circumstances (37 C.F.R. § 2.190(b) and 2.193(b)). It accurately describes the required title and caption placement (TBMP § 105), and it appropriately summarizes the signature requirements for electronic filings (37 C.F.R. § 2.193(c) and TBMP §§ 106.02, 106.02(b)–(e)), including the use of slash‐enclosed electronic signatures and identification of the signatory’s name and title. It also correctly notes the rule regarding defective signatures (37 C.F.R. § 2.119(e) and TBMP § 106.02). The citations align with the source paragraphs. 

    ==== FINAL VERIFIED ANSWER ====
    Verification: PASSED | Confidence: high

    Answer:
    A motion to compel discovery must be filed electronically with the Trademark Trial and Appeal Board (TTAB) through ESTTA, unless ESTTA is unavailable due to technical problems or there are extraordinary circumstances, in which case a paper submission may be permitted with a written explanation ("Documents that relate to proceedings before the Trademark Trial and Appeal Board must be filed electronically with the Board through ESTTA"; "The rules require that all submissions must be made to the Board electronically, currently through ESTTA, subject to certain limited exceptions permitting submissions to be made on paper. Any permitted paper submission must be accompanied by a written explanation showing that ESTTA was unavailable due to technical problems, or that extraordinary circumstances are present, and, where required, a Petition to the Director with the requisite petition fee" 0.0.5.0, 0.0.5.5.7.3).

    The motion should include a title describing its nature, such as “Motion to Compel,” and should bear the appropriate proceeding number and caption at the top of the first page ("The document should also include a title describing its nature, e.g., 'Motion to Compel'... should bear at the top of the first page both the application serial number, and the inter partes proceeding number and caption" 0.0.5.4).

    Every submission, including a motion to compel discovery, must be signed by the party filing it, or by the party’s attorney or other authorized representative. For electronic filings through ESTTA, a conventional handwritten signature is not required; instead, an electronic signature is used. The signatory must personally enter a combination of letters, numbers, spaces, and/or punctuation marks between two forward slash ('/') symbols (e.g., /John Smith/), and the signatory's name and title or position must appear immediately below or adjacent to the signature ("Documents filed electronically, including through ESTTA, do not require a conventional signature. Electronic signatures pursuant to 37 C.F.R. § 2.193(c) are required for electronic filings. The party or its representative enters a 'symbol' that has been adopted as a signature. The Board will accept any combination of letters, numbers, space and/or punctuation marks as a valid signature if it is placed between two forward slash ('/') symbols"; "The first and last name, and the title or position, of the person who signs a document in connection with a trademark application, registration, or proceeding before the Trademark Trial and Appeal Board must be set forth immediately below or adjacent to the signature" 0.0.5.5.6.2, 0.0.5.5.6.0).

    If a document is filed on behalf of a party by the party’s attorney or other authorized representative, it must bear the signature of that attorney or representative, unless the document is one required to be signed personally by the party (0.0.5.5.6.3). If an unsigned or improperly signed document is filed, it will not be refused consideration if a properly signed copy is submitted within the time limit set in the notification of the defect by the Board (0.0.5.5.6.4).

    In summary: File the motion to compel discovery electronically via ESTTA, use an electronic signature as described above, and ensure the signatory's name and title are included. If filing on paper is necessary, follow the specific requirements for paper submissions and signatures.

    Citations:
    - 0.0.5.0
    - 0.0.5.4
    - 0.0.5.5.6.0
    - 0.0.5.5.6.2
    - 0.0.5.5.6.3
    - 0.0.5.5.6.4
    - 0.0.5.5.7.3
    ```

驗證步驟產生乾淨的結構化評估，引用具體法規，有條理地檢查答案的正確性和 citation 的使用是否恰當。它不是只說「正確」，還解釋了為什麼正確，讓你有信心把答案連同具體 citation 交給使用者。

## 4. 基礎設施成本

拆解這個 agentic RAG 做法的成本結構：

### 固定成本 vs. 變動成本估算

* **估計固定（一次性）成本：**  
  * **Traditional RAG：**約 $0.43（embedding + metadata 產生）
  * **Agentic RAG：**$0.00（完全不用前處理）


* **估計變動（每次查詢）成本：**  
  * **Router 模型（`gpt-4.1-mini`）：**  
    * 初次 routing（20 個 chunk）：約 $0.10  
    * 兩層遞迴：約 $0.20
  * **Synthesis（`gpt-4.1`）：**約 $0.05
  * **Verification（`o4-mini`）：**約 $0.01
  * **每次查詢總計：**約 $0.36

雖然每次查詢成本比傳統 RAG 高，這個做法的好處是：
- 新文件馬上就能用
- citation 更精確
- 更能處理換句話說和概念性的問題
- 不用維護基礎設施

成本可以這樣優化：
- 對常見查詢做結果 cache
- 限制模型呼叫的 max tokens
- 用混合做法，先對文件做預過濾

## 5. 相較傳統 RAG 的優點與取捨

### 優點
- **零 ingest 延遲**：新文件不用前處理，馬上能問問題。
- **動態導覽**：模仿人的閱讀方式，專注在有希望的段落。
- **跨段落推理**：模型能找出獨立 chunk 檢索可能漏掉的段落關聯，有機會提高答案準確度，也省下優化檢索 pipeline 的時間。

### 取捨
- **每次查詢成本較高**：每個問題需要的運算比 embedding 檢索多。
- **延遲增加**：階層式導覽比單純的向量查詢慢。
- **擴展性有限**：文件集合非常大時可能吃力，這時前處理反而比較有效率。

## 6. 後續方向

這個做法還可以做一些修改：
- **產生 Knowledge Graph**：用 GPT 4.1-mini 的大 context window 反覆產生詳細的 knowledge graph，再讓 GPT 4.1 走訪這個 graph 來回答問題。這樣不管問什麼問題，文件只需要「ingest」一次。
- **改良 Scratchpad Tool**：scratchpad tool 可以給更多選擇，例如編輯或刪除過去的記憶，讓模型挑對當前問題最相關的內容。
- **調整深度**：調整階層式導覽的深度，在成本和效能之間找平衡。有些情境需要句子層級的 citation（像法律文件），有些只需要段落層級（像新聞文章）。

## 7. 重點

1. **Context Window 是超能力：**百萬 token 的 context window 讓你可以即時導覽文件。
2. **階層式做法模仿人的閱讀：**agentic routing 就像人在文件裡掃描找相關章節。
3. **Scratchpad 支援多步驟推理：**保留推理記錄能提升導覽品質。
4. **實作快、不需資料庫：**整個系統只靠 API call 就能建起來，不需要基礎設施。
5. **驗證提升可靠度：**LLM-as-judge 模式可以在錯誤送到使用者前攔下來。

================================================================================

## 3B. Use Case：製藥研發的 AI Co-Scientist
![AI Co-Scientist for Pharma R&D](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3B_reasoning_task_card.png)

這一節說明怎麼建一個扮演「co-scientist」的 AI 系統，加速製藥研發的實驗設計，重點是在特定限制下優化藥物合成流程。

## 🗂️ TL;DR Matrix

下表整理了這個 AI Co-Scientist 實作的核心技術選擇和理由。

| Layer              | Choice                                                                  | Utility                                                                                           |
| :----------------- | :------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------------------- |
| **Ideation**       | `o4-mini` (Parallel Role-Playing Agents)                                  | Generates diverse hypotheses & protocols rapidly and cost-effectively; role-playing enhances creativity. |
| **Grounding**      | External Tool Calls (`chem_lookup`, `cost_estimator`, `outcome_db`, etc.) | Ensures plans are based on real-world data (chemical properties, costs, past results).                   |
| **Ranking**        | `o4-mini` (Pairwise Tournament Comparison)                                | Nuanced evaluation beyond simple scoring; selects promising candidates efficiently.                      |
| **Critique/Synth** | `o3` (Deep Review & Synthesis)                                            | Provides rigorous, senior-level analysis, identifies risks, and ensures scientific validity.             |
| **Safety (Opt.)**  | `gpt-4.1-mini` (Targeted Check)                                       | Adds an extra layer of specialized safety review before human handoff.                                   |
| **Learning**       | `o3` + Code Interpreter (Result Analysis → DB)                            | Captures experimental outcomes systematically, enabling continuous improvement over time.                |
| **Core Technique** | Multi-Agent Collaboration & Escalation                                    | Leverages strengths of different models (speed vs. depth) for a complex, multi-step reasoning task.      |

*註：模型識別碼為 2025 年 4 月的資訊，之後可能變動。*

## 1. 情境摘要

* **問題領域：**優化製藥研發中複雜的實驗流程，例如在嚴格限制下，提升新藥化合物 ("XYZ-13") 的合成產率。
* **使用者：**參與藥物探索和開發的研究科學家與實驗室技術人員。
* **典型需求：**
    1. Suggest 3 distinct protocols to increase XYZ-13 yield by ≥15% by testing different catalysts, staying under $15k using approved reagents.
    2. Propose protocols to optimize XYZ-13 yield below 60°C (due to past heat issues), exploring different approved solvents within budget.
    3. Design two XYZ-13 yield strategies (aiming for ≥15%): a. one maximizing potential yield within the \$15k budget, b. one prioritizing cost under \$10k.
* **限制：**
    * **預算：**在既定的財務上限內運作（例如每個實驗系列 $15,000）。
    * **法規/安全：**只能使用預先核准的化學品/試劑，並嚴格遵守安全規範。
    * **人工監督：**最終的實驗計畫必須由人類專家審閱並確認後才能執行。
> 傳統上，優化這類實驗要花好幾週做人工規劃、文獻回顧、反覆的實驗操作和分析。這個 AI Co-Scientist 做法想大幅縮短週期，自動化假設產生、protocol 設計和初步評估，讓科學家專心在高層策略和最終確認。科學家的角色從手動執行規劃步驟，變成專家監督並與 AI 協作。


## 2. 架構（Multi-Agent Reasoning）

系統採用 multi-agent 架構，模擬高效能的科學團隊。不同的 AI 元件扮演專門角色（例如發想、批判、從結果學習），用各種模型和 tool 協作完成 workflow。

![AI Co-Scientist Architecture](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3B_coscientist_architecture.png)

### 2.1. **科學家輸入與限制：** 
流程從科學家定義目標、目標化合物和限制開始。

```python
from openai import OpenAI
from agent_utils import Context, call_openai, log_json

# Example Initial Input
user_input = {
    "compound": "XYZ-13",
    "goal": "Improve synthesis yield by 15%",
    "budget": 15000,
    "time_h": 48,
    "previous": "Prior attempts failed at high temp; explore potential catalyst effects."
}
ctx = Context(client=OpenAI(), **user_input)
```

### 2.2.  **發想（`o4-mini` + Tools）：** 
多個 `o4-mini` 實例用不同角色的 prompt（例如 `Hypothesis Agent`、`Protocol Agent`、`Resource Agent`），平行產生實驗計畫。給每個實例不同的 persona，能在發想階段同時帶來多元觀點，涵蓋問題的不同面向。

```python
ROLE_FOCUS = {
    # Hypothesis Agent Prompt
    "hypothesis_agent": """You are a pharmaceutical hypothesis specialist. 
        Focus exclusively on analyzing the compound structure and research goals to generate testable hypotheses. 
        Consider mechanism of action, binding affinity predictions, and potential off-target effects.""",

    # Protocol Agent Prompt
    "protocol_agent"  : """You are a laboratory protocol specialist. 
        Design experimental procedures that will effectively test the provided hypothesis. 
        Focus on experimental conditions, controls, and measurement techniques.""",

    # Resource Agent Prompt
    "resource_agent"  : """You are a laboratory resource optimization specialist. 
        Review the proposed protocol and optimize for efficiency. 
        Identify opportunities to reduce reagent use, equipment time, and overall costs while maintaining scientific validity.""",
}

# Create a structured prompt template for ideation
IDEATION_PROMPT = """You are a pharmaceutical {role} specialist. Your goal is to {goal} for compound {compound}.
Constraints:
- Budget: ${budget}
- Approved reagents only
- Complete within {time_h} hours
- Previous attempts: {previous}
Respond with structured JSON describing your protocol."""
```

```python
import json, logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import asdict
from functools import partial

MODEL_IDEATE   = "o4-mini-2025-04-16"  # o4-mini model for ideation - balances speed and quality

# Configure logging to help with tracking experiment progress and debugging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.info(f"Run‑id {ctx.run_id}  Compound: {ctx.compound}")
logging.info(f"Logs will be stored in: {Path('logs') / ctx.run_id}")

def ideation(ctx: Context):
    logging.info("Starting ideation phase...")
    ideas = []
    for role, focus in ROLE_FOCUS.items():
        logging.info(f"Running ideation agent ${role}")
        sys = IDEATION_PROMPT.format(role=role, focus=focus, **ctx.prompt_vars())
        usr = f"Design a protocol to {ctx.goal} within ${ctx.budget}."
        idea = call_openai(ctx.client, MODEL_IDEATE, sys, usr, ctx)
        ideas.append(idea)
    log_json("ideation_done", ideas, ctx)
    return ideas
```

??? note "輸出"

    ```text
    Run‑id 9835f69c  Compound: XYZ-13
    Logs will be stored in: logs/9835f69c
    ```

發想 agent 可以使用外部 tool，例如 `literature_search`、`chem_lookup`（化學資料庫）、`cost_estimator`、`outcome_db`（先前實驗的結果），讓建議有資料依據。明確開啟並 prompt 模型使用外部 tool，能確保產生的計畫可行、合規，而且參考了既有知識。什麼時候呼叫哪個 tool，由模型依任務自己決定。

```python
IDEATION_PROMPT += """\nUse the following tools as appropriate:
- Use the `list_available_chemicals` tool to get list of approved reagents.
- Use the `chem_lookup` tool to verify properties of reagents mentioned.
- Use the `cost_estimator` tool to calculate the approximate cost based on reagents and proposed steps.
- Check the `outcome_db` for relevant prior experiments with {compound}"""

ideas = ideation(ctx)
logging.info("Ideation complete!")
```

??? note "輸出"

    ```text
    Starting ideation phase...
    Running ideation agent $hypothesis_agent
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) List available chemicals
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Outcome DB: XYZ-13, yield, 5
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Cost estimator: [{'name': 'Palladium chloride', 'amount': 0.05, 'unit': 'g'}, {'name': 'Triphenylphosphine', 'amount': 0.1, 'unit': 'g'}, {'name': 'Potassium carbonate', 'amount': 1, 'unit': 'g'}, {'name': 'Dimethylformamide', 'amount': 50, 'unit': 'mL'}, {'name': 'Toluene', 'amount': 50, 'unit': 'mL'}, {'name': 'Sodium borohydride', 'amount': 0.1, 'unit': 'g'}, {'name': 'Triethylamine', 'amount': 0.5, 'unit': 'mL'}], ['round-bottom flask', 'magnetic stirrer', 'reflux condenser'], 36
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Running ideation agent $protocol_agent
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Outcome DB: XYZ-13, yield, 5
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) List available chemicals
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Literature search: XYZ-13 synthesis palladium triphenylphosphine ligand yield improvement, None, 3
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Cost estimator: [{'name': 'Palladium acetate', 'amount': 0.05, 'unit': 'g'}, {'name': 'Triphenylphosphine', 'amount': 0.1, 'unit': 'g'}, {'name': 'Potassium carbonate', 'amount': 2, 'unit': 'g'}, {'name': 'Triethylamine', 'amount': 2, 'unit': 'mL'}, {'name': 'Dimethylformamide', 'amount': 100, 'unit': 'mL'}], ['Magnetic stirrer', 'Oil bath', 'Inert gas setup'], 48
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Running ideation agent $resource_agent
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Outcome DB: XYZ-13, yield, 5
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) List available chemicals
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Cost estimator: [{'name': 'Palladium acetate', 'amount': 0.05, 'unit': 'g'}, {'name': 'Triphenylphosphine', 'amount': 0.1, 'unit': 'g'}, {'name': 'Potassium carbonate', 'amount': 1, 'unit': 'g'}, {'name': 'Dimethylformamide', 'amount': 5, 'unit': 'mL'}, {'name': 'Triethylamine', 'amount': 2, 'unit': 'mL'}], ['Round-bottom flask', 'Reflux condenser', 'Heating mantle', 'Magnetic stirrer'], 36
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Chemical lookup: Sodium borohydride, None
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Ideation complete!
    ```

這些 tool 定義在 `agent_utils.py`。為了這個方案，tool call 在 `tools.py` 裡是 mock 的，實際使用時這些 tool 會呼叫真正的 API。


### 2.3. **Tournament 排名（`o4-mini` / `o3`）：** 
產生的 protocol 會兩兩比較，標準包括預期效果、可行性、成本和新穎度。與其請模型單獨幫每個 protocol 打分數，每次給兩個 protocol、依特定標準直接比較，通常會得到更可靠的相對排名。

這種 Elo 式排名能找出最有潛力的候選，進入更深入的審查。

```python
TOURNAMENT_PROMPT = """
Protocol A: [details...]
Protocol B: [details...]

Compare Protocol A and Protocol B for synthesizing {compound} aimed at {goal}. Score them on:
1. Likelihood of achieving ≥ 15% yield increase.
2. Practical feasibility (reagents, time).
3. Estimated cost-efficiency (use tool if needed).
4. Scientific novelty/risk.

Return JSON {{\"winner\": \"A\"|\"B\", \"justification\": \"...\"}}."""

# This is a mock tourname implementation that only compares the first two protocols
# A real implementation would compare pairs in a tournament bracket style
def tournament(protocols: List[Dict[str, Any]], ctx: Context):
    logging.info("Starting tournament phase...")
    if len(protocols) == 1:
        return protocols[:1]
    a, b = protocols[0], protocols[1]
    sys = TOURNAMENT_PROMPT.format(**ctx.prompt_vars())
    usr = json.dumps({"A": a, "B": b}, indent=2)
    res = call_openai(ctx.client, MODEL_IDEATE, sys, usr, ctx)
    winner = a if res.get("winner", "A").upper() == "A" else b
    log_json("tournament", res, ctx)
    return [winner]

top_proto = tournament(ideas, ctx)[0]
logging.info("Tournament winner picked!")
```

??? note "輸出"

    ```text
    Starting tournament phase...
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Tournament winner picked!
    ```

> 早期實驗中我們發現，請模型用 1-10 分幫 protocol 打分數，結果不一致，而且分數會擠在一起。Tournament 做法強迫模型做相對判斷，結果更可靠。這也符合人類專家的行為，科學家常常覺得直接比較兩個選項，比給絕對分數容易。

### 2.4. **深度批判與整合（`o3`）：** 
排名前面的 protocol 交給 `o3` 做嚴格審查。`o3` 像資深科學家一樣，評估科學有效性、方法、安全性、預算是否合規，並提出改進建議，或整合出最終的精煉版 protocol。它也可以呼叫 tool 來驗證。

```python
# Deep critique phase using a more powerful model for rigorous review
CRITIQUE_PROMPT = """You are a senior researcher reviewing a proposed synthesis protocol 
for {compound} aiming for {goal}, budget ${budget} using approved reagents. Review the protocol below rigorously:
1. Identify scientific flaws or methodological weaknesses.
2. Assess safety risks and budget compliance (use `cost_estimator` tool if needed).
3. Check for consistency with prior `outcome_db` results if relevant.
4. Suggest concrete improvements or rewrite sections if necessary.
5. Provide a final go/no-go recommendation.

Return JSON {{\"revised_protocol\": ..., \"critique\": \"...\", \"recommendation\": \"go|no-go\"}}.

Protocol to Review:
[Protocol details...]
"""

MODEL_CRITIQUE = "o3-2025-04-16"  # o3 model for deep critique

def critique(protocol: Dict[str, Any], ctx: Context):
    logging.info("Starting critique phase...")
    sys = CRITIQUE_PROMPT.format(**ctx.prompt_vars())
    usr = json.dumps(protocol, indent=2)
    crit = call_openai(ctx.client, MODEL_CRITIQUE, sys, usr, ctx)
    log_json("critique", crit, ctx)
    return crit.get("revised_protocol", protocol)

critiqued = critique(top_proto, ctx)
logging.info("Deep critique completed!")
```

??? note "輸出"

    ```text
    Starting critique phase...
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Cost estimator: [{'name': 'Palladium chloride', 'amount': 0.0045, 'unit': 'g'}, {'name': 'Triphenylphosphine', 'amount': 0.013, 'unit': 'g'}, {'name': 'Sodium borohydride', 'amount': 0.0038, 'unit': 'g'}, {'name': 'Potassium carbonate', 'amount': 0.14, 'unit': 'g'}, {'name': 'Triethylamine', 'amount': 0.07, 'unit': 'mL'}, {'name': 'Dimethylformamide', 'amount': 2, 'unit': 'mL'}, {'name': 'Toluene', 'amount': 5, 'unit': 'mL'}], ['100 mL round-bottom flask', 'magnetic stirrer', 'reflux condenser', 'inert gas line'], 24
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Outcome DB: XYZ-13, None, 5
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Deep critique completed!
    ```

> 我們刻意用不同的模型和 persona 把發想和批判分開。同一個模型自己產生又自己批判，常常變成自我辯護，而不是客觀評估。扮演「資深科學家」的 o3 模型，一直都能找出 o4-mini 在發想時漏掉的方法學弱點。

### 2.5. **（選用）安全檢查：** 
可以用專門的模型，例如 `gpt-4.1-mini`，對特定安全疑慮（例如危險的試劑組合）做最後檢查。

```python
# Optional safety check using a targeted model
SAFETY_PROMPT = """You are a lab‑safety specialist. 
Identify hazards, unsafe conditions, or compliance issues in this protocol for {compound}. 
Use `chem_lookup` tool if needed. Return JSON assessment."""

MODEL_SAFETY   = "gpt-4.1-mini-2025-04-14"  # gpt-4.1-mini model for safety checks - optimized for instruction following

def safety(protocol: Dict[str, Any], ctx: Context):
    logging.info("Starting safety assessment...")
    sys = SAFETY_PROMPT.format(**ctx.prompt_vars())
    usr = json.dumps(protocol, indent=2)
    assessment = call_openai(ctx.client, MODEL_SAFETY, sys, usr, ctx)
    log_json("safety", assessment, ctx)
    return {"protocol": protocol, "safety": assessment}

secured = safety(critiqued, ctx)
logging.info("Safety check completed!")
```

??? note "輸出"

    ```text
    Starting safety assessment...
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Chemical lookup: Palladium chloride, None
    (Tool) Chemical lookup: Triphenylphosphine, None
    (Tool) Chemical lookup: Sodium borohydride, None
    (Tool) Chemical lookup: Potassium carbonate, None
    (Tool) Chemical lookup: Dimethylformamide, None
    (Tool) Chemical lookup: Toluene, None
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Safety check completed!
    ```

### 2.6. **人工審閱：** 
AI 產生的最終計畫會透過介面呈現給人類科學家，由他確認、必要時編輯，並做最後核准。

```python
def human_review(safety_package: Dict[str, Any], ctx: Context):
    logging.info("Awaiting human review...")
    protocol = safety_package["protocol"]
    safety_assessment = safety_package["safety"]
    
    print(f"\n=== PROTOCOL FOR REVIEW: {ctx.compound} - {ctx.goal} ===")
    print(f"DETAILS: {json.dumps(protocol, indent=2)}")
    print(f"SAFETY: {json.dumps(safety_assessment, indent=2)}")
    
    while True:
        approval = input("\nApprove for execution? (yes/no): ").lower()
        if approval in ['yes', 'y', 'no', 'n']:
            approved = approval in ['yes', 'y']
            logging.info(f"Protocol {'approved' if approved else 'rejected'}")
            return {"protocol": protocol, "approved": approved}
        print("Please enter 'yes' or 'no'")

human_decision = human_review(secured, ctx)
```

??? note "輸出"

    ```text
    Awaiting human review...
    ```

    ```text

    === PROTOCOL FOR REVIEW: XYZ-13 - Improve synthesis yield by 15% ===
    DETAILS: {
      "protocol_title": "Optimised In-Situ Pd(0)/PPh3 Coupling for XYZ-13 \u2013 Target \u2265 72 % Yield",
      "key_changes_vs_original": [
        "Catalyst loading reduced from 5 mol % to 2 mol % Pd to cut cost and metal contamination without loss of activity.",
        "Reaction run at 0.10 M substrate concentration (12 mL solvent total) instead of 50 mL; higher effective collision frequency boosts conversion and reduces waste.",
        "Single solvent system (toluene/DMF 4:1) avoids phase separation and simplifies work-up.",
        "Redundant triethylamine removed; K2CO3 (2.5 eq) provides sufficient basicity.",
        "Reaction temperature raised slightly to 80 \u00b0C (still below side-reaction threshold found in exp-001) and time shortened to 24 h with in-process HPLC check at 6 h intervals.",
        "Work-up switched from large silica column to two-step: (a) aqueous EDTA wash to strip Pd, (b) recrystallisation from EtOAc/hexane \u2013 typically 5\u20138 % higher isolated yield on this substrate."
      ],
      "objective": "Isolated yield \u2265 72 % within 24 h, total direct cost \u2264 US $5 000.",
      "scale": "0.5 mmol XYZ-13 (170 mg, assume MW \u2248 340).",
      "reagents": [
        {
          "name": "Palladium chloride",
          "amount": 0.02,
          "unit": "g",
          "role": "precatalyst (2 mol %)"
        },
        {
          "name": "Triphenylphosphine",
          "amount": 0.041,
          "unit": "g",
          "role": "ligand (2 eq vs Pd)"
        },
        {
          "name": "Sodium borohydride",
          "amount": 0.02,
          "unit": "g",
          "role": "Pd(II)\u2192Pd(0) reducer"
        },
        {
          "name": "Potassium carbonate",
          "amount": 0.345,
          "unit": "g",
          "role": "base (2.5 eq)"
        },
        {
    ... (省略 115 行)
    ```

    ```text
    Protocol approved
    ```

### 2.7. **執行與學習（`o3` + Code Interpreter）：** 
人類核准後，計畫送去實驗室執行。實驗結束後，結果回饋進系統。`o3` 搭配 `Code Interpreter` 分析資料、產生 insight，並把結構化的結果（protocol、參數、結果、insight）存進資料庫 (`Outcome DB`)。這個資料庫會用在之後的發想循環，形成學習迴圈。

```python
# Simulating execution and analyzing results
ANALYSIS_PROMPT = """You are a data analyst. 
Did the experiment achieve {goal}?  Analyse factors, suggest improvements, and return structured JSON.
"""

def execute_and_analyse(pkt: Dict[str, Any], ctx: Context):
    logging.info("Starting mock execution and analysis...")
    # These are mock results for a lab experiment
    mock_results = {
        "yield_improvement": 12.5,
        "success": False,
        "actual_cost": ctx.budget * 0.85,
        "notes": "Mock execution"
    }
    sys = ANALYSIS_PROMPT.format(**ctx.prompt_vars())
    usr = json.dumps({"protocol": pkt, "results": mock_results}, indent=2)
    analysis = call_openai(ctx.client, MODEL_CRITIQUE, sys, usr, ctx)
    log_json("analysis", analysis, ctx)
    return analysis

# Only proceed to execution if approved by the human reviewer
if human_decision["approved"]:
    summary = execute_and_analyse(human_decision, ctx)
    logging.info("Analysis complete")
else:
    logging.info("Protocol rejected by human reviewer - execution skipped")
    summary = None

Path("output").mkdir(exist_ok=True)
out_path = Path("output") / f"{ctx.run_id}_summary.json"
out_path.write_text(json.dumps(summary, indent=2))
print(f"\n🎉 Completed. Summary written to {out_path}")
```

??? note "輸出"

    ```text
    Starting mock execution and analysis...
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Literature search: Pd(0) PPh3 coupling yield optimization EDTA work-up recrystallization losses, None, 3
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    (Tool) Outcome DB: XYZ-13, yield, 5
    HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    Analysis complete
    ```

    ```text

    🎉 Completed. Summary written to output/9835f69c_summary.json
    ```

## 3. 模型 Playbook

在 `o4-mini` 和 `o3` 之間選，取決於任務的複雜度和需要的深度。其他任務用 `gpt-4.1-mini` 可以在成本和效能之間取得平衡，需要更強能力或更細膩判斷時，建議用更強的 `gpt4.1`。

| Task               | Start With     | Upgrade When...                                            | Escalate To  | Rationale                                                                                    |
| :----------------- | :------------- | :--------------------------------------------------------- | :----------- | :------------------------------------------------------------------------------------------- |
| Ideation & Protocol Generation | `o4-mini` | Hypotheses lack depth or creativity needed for complex chemical synthesis. | `o3` | `o4-mini` rapidly generates diverse protocols cost-effectively. `o3` provides deeper scientific reasoning when more nuanced approaches are required. |
| Protocol Ranking | `o4-mini` | Comparison requires deeper scientific assessment or multi-factor trade-offs. | `o3` | Tournament-style ranking with `o4-mini` efficiently identifies promising candidates. Escalate when subtle scientific validity needs evaluation. |
| Deep Critique & Synthesis | `o3` | N/A - Already using the most capable model for this critical task. | N/A | `o3` excels at rigorous scientific review, identifying methodological flaws, and synthesizing improvements across complex protocols. This task inherently requires deep reasoning. |
| Safety Assessment | `gpt-4.1-mini` | Domain-specific hazards require higher accuracy or specialized knowledge. | `gpt-4.1` | `gpt-4.1-mini` offers a good balance of cost and performance for standard safety checks. Escalate to `gpt4.1` when higher accuracy or more nuanced reasoning is needed for complex safety risks. |

**關鍵洞察：**
> 這個 use case 示範了一個很有力的模式：先用更快更便宜的模型（`o4-mini`）處理廣度和初步篩選，再升級到更強的模型（`o3`）做深度、關鍵審查和整合。這種分層做法兼顧創意/速度和嚴謹/準確，同時有效控制運算成本。與 tool 整合是必要的，這樣 AI 的推理才有可驗證的真實資料當依據。

## 4. 部署注意事項

把 AI Co-Scientist 從原型轉到實驗室使用，需要仔細規劃。

* **成本控制：**
    * 實作可設定的「模式」（例如 `Fast`、`Standard`、`Thorough`），調整 `o4-mini` 發想 agent 的數量、`o3` 批判的深度，或是否做選用的檢查，在結果品質和成本、延遲之間取捨。
    * 追蹤每個階段（發想、排名、批判）和每次 tool call 的 token 用量，做細緻的成本監控。
* **Observability：**
    * 記錄每個步驟的輸入、輸出、模型選擇、tool call/回應、延遲和 token 數。
    * 監控 tournament 排名的表現，以及 `o3` 批判的影響（例如計畫被大幅修改或否決的頻率）。
    * 追蹤使用者互動：哪些計畫被人類科學家核准、編輯或否決。
* **安全與合規：**
    * 實作多層安全機制：prompt 裡的限制、tool 型檢查（例如透過 `chem_lookup` 查試劑相容性）、選用的專用模型檢查（`gpt-4.1-mini`）、自動 filter（例如已知的危險組合），以及強制的人工審閱。
    * 確保 tool endpoint（例如內部資料庫）符合安全要求。
* **上線策略：** 
    * 先對過去的實驗做回溯分析，再進入 shadow mode（AI 與人類規劃者並行提出計畫），然後在密切監控下做有限的實際使用，最後才擴大採用。


## 5. 重點

1. **模型搭配產生綜效**：`o4-mini` 快速涵蓋更多範圍，`o3` 帶來精準度和深度。
2. **Tool 整合讓推理落在現實**：化學品成本、安全限制這類真實資料會影響決策。
3. **人類科學家仍是核心**：系統是替專家省掉雜務，不是取代他們。


## 6. 實用 Cookbook 與資源

下面是幾個和 AI Co-Scientist 系統設計與實作互補的資源：

- **[Orchestrating Agents: Routines and Handoffs](https://cookbook.openai.com/examples/orchestrating_agents)** Structuring multi-agent workflows with routines and handoffs, relevant to the ideation→ranking→critique pipeline.

- **[GPT-4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)** Advanced prompting, tool use, and task decomposition for improved accuracy in critique and safety reviews.

- **[Structured Outputs for Multi-Agent Systems](https://cookbook.openai.com/examples/structured_outputs_multi_agent)** Enforcing consistent JSON outputs with schema validation for agent interoperability.

- **[Agents - OpenAI API](https://platform.openai.com/docs/guides/agents)**  
  Comprehensive guide to building multi-agent systems with OpenAI tools, covering orchestration, tool use, and best practices foundational to this system's architecture.

================================================================================



## 3C. Use Case：保險理賠處理

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3C_insurance_task_card.png)

很多企業都要處理手寫表單數位化的工作。這一節示範怎麼用 OpenAI 把手寫的保險表單數位化並驗證。這在保險業很常見，同樣的技術也能用在其他產業和表單，例如稅務表單、發票等。

## 🗂️ TL;DR Matrix

下表整理了這個針對保險場景的 OCR 實作的核心技術選擇和理由。

| Layer | Choice | Utility |
| :---- | :---- | :---- |
| JSON Output | Structured output with Pydantic | Easy to specify formatting, adheres to schema better than `JSON mode` |
| OCR and Vision | `gpt-4.1` | Powerful OCR and vision capabilities, structured output |
| Reasoning | `o4-mini` | Affordable but capable reasoning, function calling available |
| Form Validation | Custom function calling | Can provide interaction with custom or internal databases |

\*註：價格和模型識別碼為 2025 年 4 月的資訊，之後可能變動。

## 1\. 情境摘要

* **使用者：**目標使用者是保險服務與營運團隊，需要從手寫表單 ingest 資料。  
* **典型需求：**每種表單的結構和要擷取的欄位都不同。  
* **限制：**  
  * **準確度：**需要高準確度，確保資料正確且完整。  
  * **不確定性：**系統必須處理資料的不確定性，例如缺漏資料、模糊資料，以及同一欄位的不同格式。如果模型無法解決不確定性，系統需要有機制請求人工審閱。  
  * **效能與成本：**系統延遲不是重點，但需要高準確度，同時要控制成本。目標是每處理 1000 頁不超過 $20。

## 2\. 架構

解決方案的高階基本架構如下。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3C_insurance_architecture.png)

這個任務很複雜，需要多種模型能力，包括 vision、function calling、reasoning 和 structured output。`o3` 雖然能一次做完這些，但實驗發現只靠 `o4-mini` 達不到需要的效能。因為 `o3` 成本相對較高，我們改採兩階段做法。

1. 第一階段用 GPT 4.1 的 vision 能力。這個階段最佳化的目標是用最高準確度擷取文字，把不確定的部分留給推理階段，不對頁面上看不到的內容做任何假設。在第一階段做 OCR，推理模型就不用直接看圖片，因為推理模型本來就有很多其他工作要做，再加上看圖會很吃力。  
     
2. 第二階段利用 `o4-mini` 的推理能力。我們用 `o4-mini` 驗證 OCR 的準確度，並把資料擷取成結構化格式。重點是，我們期待 o4-mini 成為第二道品質關卡 \-- 如果這個階段發現 OCR 不完整，可以用 o4-mini 來修正並驗證原本的結果。

為了具體示範怎麼運作，來看一張保險表單的範例圖片。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3C_insurance_form.png)

這張表單本身很單純，但有缺漏和模糊的資料，傳統 OCR 系統很難正確填完。第一，注意郵遞區號和 county 沒填。第二，使用者的 email 很模糊 \-- 可能是 `jsmith1@gmail.com`，也可能是 `jsmithl@gmail.com`。接下來幾節會一步步說明，設計良好的方案怎麼處理這些模糊之處，並回傳正確的表單結果。

**環境設定與函式庫程式碼：**

為了讓範例程式碼更清楚，我們把環境設定（例如 `pip install` 指令）和函式庫函式獨立放到另一個 code block。這樣你就能在每個步驟專心看相關的邏輯。

```python
# Install Python requirements
%pip install -qU pydantic "openai>=1.76.0"

# All imports
import os
import json

from pydantic import BaseModel

# Create the OpenAI client
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "sk-dummykey"))
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

```python
def run_conversation_loop(
    client,
    messages,
    tools,
    tool_handlers,
    response_format,
    model,
):
    """Run the OpenAI response completion loop, handling function calls via tool_handlers until parsing final response."""
    summaries = []
    while True:
        print(
            f"Requesting completion from model '{model}' (messages={len(messages)})"
        )
        response = client.responses.parse(
            model=model,
            input=messages,
            tools=tools,
            text_format=response_format,
            reasoning={"summary": "auto"},
        )
        summaries.append(response.output[0].summary)

        if not response.output_parsed:
            print("Assistant requested tool calls, resolving ...")

            reasoning_msg, tool_call = response.output
            messages.append(reasoning_msg)
            messages.append({
                "id": tool_call.id,
                "call_id": tool_call.call_id,
                "type": tool_call.type,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            })

            if tool_call.name in tool_handlers:
                try:
                    args = json.loads(tool_call.arguments)
                except Exception as exc:
                    print(
                        "Failed to parse %s arguments: %s", tool_call.name, exc
                    )
                    args = {}
                result = tool_handlers[tool_call.name](**args)
                messages.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": str(result),
                    }
                )
                print(f"Tool call {tool_call.name} complete, result: {str(result)}")
            else:
                print("Unhandled function call: %s", tool_call.name)

        if response.output_parsed is not None:
            print("Received parsed result from model")
            return response, summaries
```

**流程說明：第一階段**

1. **圖片：**用戶用手機拍的表單圖片會傳給模型。OpenAI 的模型能接受多種圖片格式，我們通常用 PNG，讓文字保持清晰並減少瑕疵。這個範例是從公開的內容 URL 把圖片傳給模型。在 production 環境，你多半會傳 signed URL，指向放在自己雲端 storage bucket 的圖片。  
     
2. **Structured Output Schema：**我們定義一個 Pydantic model 來規範輸出資料的結構。這個 model 包含表單上所有要擷取的欄位，以及每個欄位適當的型別。整個 model 拆成幾個子元件，每個子元件本身也是 Pydantic model，由上層 model 引用。

```python
class PersonContact(BaseModel):
    name: str
    home_phone: str
    work_phone: str
    cell_phone: str
    email: str

class Address(BaseModel):
    street: str
    city: str
    state: str
    zip: str
    county: str

class DwellingDetails(BaseModel):
    coverage_a_limit: str
    companion_policy_expiration_date: str
    occupancy_of_dwelling: str
    type_of_policy: str
    unrepaired_structural_damage: bool
    construction_type: str
    roof_type: str
    foundation_type: str
    has_post_and_pier_or_post_and_beam_foundation: bool
    cripple_walls: bool
    number_of_stories: str
    living_space_over_garage: bool
    number_of_chimneys: str
    square_footage: str
    year_of_construction: str
    anchored_to_foundation: bool
    water_heater_secured: bool

class InsuranceFormData(BaseModel):
    applicant: PersonContact
    co_applicant: PersonContact
    risk_address: Address
    mailing_address_if_different_than_risk_address: Address
    participating_insurer: str
    companion_policy_number: str
    dwelling_details: DwellingDetails
    effective_date: str
    expiration_date: str
```

3. **執行 OCR：**用 GPT-4.1 的 vision 能力執行 pipeline 的第一階段，把文件文字以結構化格式擷取出來。這個初始階段的目標是達到高準確度，並把不確定性傳給第二階段。我們的 prompt 明確指示模型不要推測輸入內容，盡可能精確地填入細節。圖片輸入的 detail 我們設成 `auto`，讓它依圖片推斷合適的細節程度。實驗中 `auto` 效果不錯，但如果你發現 OCR 品質有問題，可以考慮改用 `high`。

```python
OCR_PROMPT = """You are a helpful assistant who excels at processing insurance forms.

You will be given an image of a hand-filled insurance form. Your job is to OCR the data into the given structured format.
Fill out the fields as exactly as possible. If a written character could possibly be ambiguous (i.e. l or 1, o or 0), include all possiblities in the field separated by "OR", especially for email addresses.
"""

user_content = [
    {"type": "input_text", "text": "Here is a photo of the form filled out by the user:"},
    {
        "type": "input_image",
        "image_url": "https://drive.usercontent.google.com/download?id=1-tZ526AW3mX1qthvgi8spaaxxeqFG5_6",
        "detail": "auto",
    },
]

messages = [
    {"role": "system", "content": OCR_PROMPT},
    {"role": "user", "content": user_content},
]

response = client.responses.parse(
    model="gpt-4.1-2025-04-14",
    input=messages,
    text_format=InsuranceFormData,
    # Set temp to 0 for reproducibility
    temperature=0,
)

s1_json_results = json.dumps(json.loads(response.output_parsed.model_dump_json()), indent=2)
print(s1_json_results)
```

??? note "輸出"

    ```text
    {
      "applicant": {
        "name": "Smith, James L",
        "home_phone": "510 331 5555",
        "work_phone": "",
        "cell_phone": "510 212 5555",
        "email": "jsmithl@gmail.com OR jsmith1@gmail.com"
      },
      "co_applicant": {
        "name": "Roberts, Jesse T",
        "home_phone": "510 331 5555",
        "work_phone": "415 626 5555",
        "cell_phone": "",
        "email": "jrobertsjr@gmail.com"
      },
      "risk_address": {
        "street": "855 Brannan St",
        "city": "San Francisco",
        "state": "CA",
        "zip": "",
        "county": ""
      },
      "mailing_address_if_different_than_risk_address": {
        "street": "",
        "city": "",
        "state": "",
        "zip": "",
        "county": ""
      },
      "participating_insurer": "Acme Insurance Co",
      "companion_policy_number": "81265919",
      "dwelling_details": {
        "coverage_a_limit": "$900,000",
        "companion_policy_expiration_date": "5/31/27",
        "occupancy_of_dwelling": "Owner",
        "type_of_policy": "Homeowners",
        "unrepaired_structural_damage": false,
        "construction_type": "Frame",
        "roof_type": "Composition",
        "foundation_type": "Raised",
    ... (省略 13 行)
    ```

注意輸出缺了好幾個欄位。下一個處理階段會用 OpenAI 的 reasoning 模型，盡可能推論出缺漏的欄位。

**流程說明：第二階段**

1. **Function 定義：**我們定義一組自訂 function，讓模型用來解決不確定性。這裡定義的 function 可以檢查 email 是否存在來驗證 email 地址，用來解決模糊的 email 欄位，也就是模型必須在多個可能值之間選一個的情況。預設情況下，o4-mini 支援內建 tool 像 web search，這裡它會用來補上郵遞區號和不完整的地址。

```python
tools = [{
    "type": "function",
    "name": "validate_email",
    "description": "Check if an email address is valid and exists.",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "The email address to validate."
            }
        },
        "required": [
            "email"
        ],
        "additionalProperties": False
    }
},
{
    "type": "function",
    "name": "search_web",
    "description": "Perform a web search.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to run through the search engine."
            }
        },
        "required": [
            "query"
        ],
        "additionalProperties": False
    }
}]
```

2. **Prompt：**我們給模型一個 prompt，說明我們已經用 OCR 擷取了文字，請模型做推理和 function calling，填入缺漏或模糊的欄位。

```python
PROMPT = """You are a helpful assistant who excels at processing insurance forms.

You will be given a javascript representation of an OCR'd document. Consider at which fields are ambiguous reason about how to fill them in. Fill any missing fields that are possible to infer from existing data, or search the web. If you cannot fill a field, reason about why.

Use the tools provided if necessary to clarify the results. If the OCR system has provided two possibilities, do your best to definitely pick which option is correct.
"""
```

```python
messages = [
    {"role": "system", "content": PROMPT},
    {"role": "user", "content": s1_json_results},
]

# For demonstration purposes, we'll hardcode the correct email answer.
def email_mock(*args, **kwargs):
    if kwargs["email"] == "jsmithl@gmail.com":
        return True
    return False

# Reasoning models like `o4-mini` will soon support built-in web search, but for now
# we demonstrate this capability using a simple mock function.
def web_mock(*args, **kwargs):
    if "855 Brannan" in kwargs["query"]:
        return "855 Brannan St, San Francisco, 94103, San Francisco County"
    
    return ""
    
tool_handlers = {"validate_email": email_mock, "search_web": web_mock}

response, summaries = run_conversation_loop(
    client=client,
    messages=messages,
    tools=tools,
    tool_handlers=tool_handlers,
    response_format=InsuranceFormData,
    model="o4-mini-2025-04-16",
)

print(json.dumps(json.loads(response.output_parsed.model_dump_json()), indent=2))
```

??? note "輸出"

    ```text
    Requesting completion from model 'o4-mini-2025-04-16' (messages=2)
    Assistant requested tool calls, resolving ...
    Tool call validate_email complete, result: True
    Requesting completion from model 'o4-mini-2025-04-16' (messages=5)
    Assistant requested tool calls, resolving ...
    Tool call validate_email complete, result: False
    Requesting completion from model 'o4-mini-2025-04-16' (messages=8)
    Received parsed result from model
    {
      "applicant": {
        "name": "Smith, James L",
        "home_phone": "510 331 5555",
        "work_phone": "",
        "cell_phone": "510 212 5555",
        "email": "jsmithl@gmail.com"
      },
      "co_applicant": {
        "name": "Roberts, Jesse T",
        "home_phone": "510 331 5555",
        "work_phone": "415 626 5555",
        "cell_phone": "",
        "email": "jrobertsjr@gmail.com"
      },
      "risk_address": {
        "street": "855 Brannan St",
        "city": "San Francisco",
        "state": "CA",
        "zip": "94107",
        "county": "San Francisco"
      },
      "mailing_address_if_different_than_risk_address": {
        "street": "855 Brannan St",
        "city": "San Francisco",
        "state": "CA",
        "zip": "94107",
        "county": "San Francisco"
      },
      "participating_insurer": "Acme Insurance Co",
      "companion_policy_number": "81265919",
      "dwelling_details": {
    ... (省略 21 行)
    ```

可以看到 email 地址被收斂成單一值，郵遞區號和 county 被補上，mailing address 也用 risk address 填好了。模型還以結構化格式（yes/no 問題用 boolean 這類適當型別）回傳結果，下游系統很容易解析。

為了幫助我們理解和 debug 模型，也可以印出模型產生的 chain-of-thought 摘要。這能暴露常見的失敗模式、模型不確定的地方，或上游不正確的細節。

開發這個方案時，chain-of-thought 摘要就揭露了一些命名和型別不正確的 schema 值。

```python
for summary in summaries:
    for response in summary:
        print(response.text + '\n')
```

??? note "輸出"

    ```text
    **Determining insurance form details**

    I have a JSON representation of a partially filled insurance form, and there are a few missing or ambiguous fields that I need to address.

    For the email address, I see two options. I can validate which one is correct by checking both with the tool.

    The risk address fields for zip code and county are empty. Based on the address "855 Brannan St, San Francisco, CA," I can determine the correct zip code is 94107, as that area corresponds to South Beach. Lastly, since the mailing address is empty, I assume it's the same as the risk address.

    **Filling insurance form details**

    I think it’s best to set the mailing address to be the same as the risk address or clarify that a blank one implies the same. Since it’s an explicit instruction to fill missing fields, I’ll fill in the mailing address with the risk address to avoid confusion.

    All co-applicant fields are present, and dwelling details are complete. The effective and expiration dates are also provided. I plan to validate both email options by checking each one separately. Let's begin with validating the first email.
    ```

## 3\. 模型與能力 Playbook

挑對工具是得到最佳結果的關鍵。一般來說，先從符合需求的最簡單方案開始，需要更多能力再升級。

| Task | Start With | Upgrade When... | Escalate To | Rationale |
| :---- | :---- | :---- | :---- | :---- |
| OCR | `gpt-4.1` | Complex forms that are difficult to understand at a glance | `o3` | `gpt-4.1` is fast and cost-effective for most OCR. `o-3` has the ability to reason about form structure. |
| Results Refinement | `o4-mini` | Complex logic for inferring details, many function calls required. | `o3` | Better for very long chains of reasoning, especially with both function calls and structured output. |

## 4\. 評估指標

追蹤關鍵指標，確保系統準確、符合預期。

### 關鍵指標

* **OCR 準確度：**每字元和每個字的準確度。  
* **推論欄位比率：**未填的欄位中，能從既有資料或 function calling 正確推論出來的比例。  
* **人工介入比率：**文件包含 UNKNOWN 而必須轉給人處理的頻率。  

我們建議建一個有標註的 hold-out 表單集和預期回應。這個資料集應該能代表預期的部署環境，建立和評估系統的詳細做法請見 [OpenAI evals](https://platform.openai.com/docs/guides/evals) 指南。

## 5\. 部署注意事項

從原型走到 production 等級的系統，需要注意營運細節 (LLMOps)。

### 成本拆解

我們假設文件 ingestion 可以用 [batch pricing](https://platform.openai.com/docs/guides/batch)，因為延遲容忍度高（例如跑一晚也沒問題）。

#### **第一階段：OCR (Optical Character Recognition)**

**模型：**`gpt-4.1`

| Type | Tokens | Rate (per 1M) | Cost |
| :---- | :---- | :---- | :---- |
| Input | 2,000 | $1.00 | $0.002 |
| Output | 1,500 | $4.00 | $0.006 |
| **Total for 1,000 pages (Stage 1\)** |  |  | **$8.00** |

#### **第二階段：Reasoning**

**模型：**`o4-mini`

| Type | Tokens | Rate (per 1M) | Cost |
| :---- | :---- | :---- | :---- |
| Input | 2,000 | $0.55 | $0.0011 |
| Output | 3,000 | $2.20 | $0.0066 |
| **Total for 1,000 pages (Stage 2\)** |  |  | **$7.70** |

#### 總計（每 1,000 頁）：**$15.70**

拿這個成本跟單階段的 `o3` 部署比。假設 token 用量相同、都用 batch，更強的推理模型會多花 $70/1000 頁。

### 監控與部署

記錄關鍵指標來監控系統：

* 每個模型的 `llm_model_used`、`llm_input_tokens`、`llm_output_tokens`、`llm_latency_ms`  
* 每個模型的 `total_query_latency_ms`、`estimated_query_cost`  
* `function_calls_per_document`、`num_email_validation_calls`  
* `human_review_required`

部署時，透過設定或環境變數固定（pin）用到的特定模型版本識別碼（例如 `o4-mini-2025-04-16`），避免模型被悄悄更新而出現意外行為。

## 6\. 實用 Cookbook 與資源

想深入特定元件，可參考這些相關資源：

* [Structured Output](https://platform.openai.com/docs/guides/structured-outputs)  
* [Vision Models](https://platform.openai.com/docs/guides/images)  
* [Function Calling](https://platform.openai.com/docs/guides/function-calling)

================================================================================


<h2 id="prototype-to-production">Prototype to Production</h2>

把原型轉成 production 需要仔細規劃和執行。這份檢查清單根據我們的主要 use case，整理了關鍵步驟，確保你的部署穩健、有效率，並符合商業目標。

## 🗂️ TL;DR Matrix

| Checklist Area | Key Focus / Actions | Why it Matters |
| :---- | :---- | :---- |
| **Define Success Criteria** | • Define measurable KPIs & SLOs (accuracy, cost, latency). • Ensure targets are measurable via logs. | Provides clear targets; proves value. |
| **Document Model Rationale** | • Select initial models deliberately based on trade-offs. • Document the "why" behind model choices. | Justifies choices; aids future updates. |
| **Robust Evaluation & Testing** | • Build automated tests ("eval suite") using a golden set. • Focus on factuality, hallucinations, tool errors.  • Test tool reliability & edge cases. | Ensures quality; prevents regressions before release. |
| **Observability & Cost** | • Implement essential logging for monitoring & debugging. • Set cost guardrails (token limits, usage modes). | Enables tuning; keeps spending within budget. |
| **Safety & Compliance** | • Use safety mechanisms (moderation APIs, prompts). • Enforce domain-specific compliance rules. • Mandate Human-in-the-Loop (HITL) for high-risk outputs. | Ensures responsible operation; meets requirements. |
| **Model Updates & Versioning** | • Define version pinning strategy • Implement A/B testing for new versions • Create rollback procedures | Maintains stability while allowing improvements. |

1. **用量化方式定義成功標準：**在大規模開發前，從「能動」進一步到可衡量的目標。  
     
   * **設定關鍵績效指標 (KPI) 與 SLO：**定義商業價值的具體目標（例如 RAG 準確度 \> 95%、OCR 成本 \< $X/頁）和效能目標（例如 P95 延遲 \< 1s、錯誤率）。  
   * **確保可衡量：**確認所有 KPI 和 SLO 都能直接從系統 log 衡量（例如追蹤 `total_tokens`、`critique_status`）。

   

2. **記錄最初選擇模型的理由：**為日後參考，說明你起手選這些模型的原因。  
     
   * **刻意選模型：**用 Model-Intro Matrix 和各 use case 為每個任務選合適的模型（例如 `o4-mini` 求速度/成本、`gpt-4.1` 求準確度、`o3` 求深度）。  
   * **記下「為什麼」：**簡短記錄你選擇背後的考量（成本、延遲、能力的取捨），寫在程式碼註解或設計文件裡，讓之後的團隊了解背景。

   

3. **做穩健的評估與測試：**在上線變更前驗證品質，避免 regression。  
     
   * **建立自動化 eval suite：**用「golden set」（50-100 個多元、專家驗證過的範例）建立可重複的測試流程。測試重點放在 `factuality`、`hallucination rate`、`tool-error rate` 和任務專屬的指標。  
   * **可靠地測試：**嚴格測試整合進來的 tool 可靠度（成功率、錯誤處理），以及系統在負載下和邊界情況（格式錯誤的資料、對抗性輸入）的行為。

   

4. **建立 Observability 與成本控制：**監控效能，並讓花費在預算內。  
     
   * **設定成本護欄：**為每個階段定義 max token 上限，並考慮用運作模式（"Fast"、"Standard"、"Thorough"）在成本和效能之間取捨，避免成本意外增加。  
   * **做好必要的 logging：**為每個處理階段用結構化 log 記錄關鍵營運資料，方便 debug 和監控。

   

5. **建立安全與合規護欄：**確保負責任地運作並符合要求。  
     
   * **使用安全機制：**使用像 OpenAI moderation API、以安全為重點的 system prompt 或 sentinel 模型來做檢查，特別是處理使用者輸入或敏感主題時。  
   * **落實合規：**內建符合你所屬產業和風險的檢查（例如法律限制、實驗室安全）。  
   * **要求 Human-in-the-Loop (HITL)：**低信心的輸出、高風險情境或關鍵決策都要強制人工審閱，並確保 workflow 清楚標記這些項目。


6. **管理模型更新與版本：**為模型隨時間演進做好準備。
   
   * **版本固定策略：**決定要固定特定模型版本求穩定，還是自動採用新版本來獲得改進。
   * **A/B 測試框架：**建立流程，在全面部署前，用關鍵指標評估新的模型版本。
   * **Rollback 計畫：**建立明確的程序，在更新出問題時退回先前的模型版本。
   * **監控版本效能：**追蹤各模型版本的指標，找出效能趨勢，作為日後選模型的參考。

================================================================================



## Adaptation Decision Tree

![Model Selection Decision Tree](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3D_model_selection_flowchart.png)

## 向非技術背景的利害關係人說明模型選擇

向業務利害關係人解釋你的模型選擇時，著重這幾點：

1. **對齊商業成果**：說明你選的模型如何直接支援特定的商業目標（節省時間、降低成本、提升準確度）。

2. **翻譯技術指標**：把技術考量轉成商業影響：
   - "This model reduces processing time from 5 seconds to 0.7 seconds, allowing us to handle customer inquiries 7x faster"
   - "By using the mini variant, we can process 5x more documents within the same budget"

3. **強調取捨**：針對不同模型提出清楚的情境：
   - "Option A (GPT-4.1): Highest accuracy but higher cost - ideal for client-facing legal analysis"
   - "Option B (GPT-4.1 mini): 90% of the accuracy at 30% of the cost - perfect for internal document processing"

4. **用具體例子**：展示不同模型輸出的實際差異，說明各選項的價值。

================================================================================



## Appendices

## 詞彙表

| Term | Definition |
|------|------------|
| **Context Window** | The maximum number of tokens a model can process in a single request |
| **Hallucination** | When a model generates content that appears plausible but is factually incorrect or unsupported |
| **Latency** | The time delay between sending a request to a model and receiving a response |
| **LLM** | Large Language Model; an AI system trained on vast amounts of text data |
| **Prompt Engineering** | The practice of designing effective prompts to elicit desired outputs from AI models |
| **RAG** | Retrieval-Augmented Generation; combining information retrieval with text generation |
| **SOTA** | State-of-the-Art; representing the most advanced stage in a field at a given time |
| **Token** | The basic unit of text that models process (roughly 0.75 words in English) |

## 6.1 價格與用途表（2025 年 4 月）

| Model | Context Window | Input Price (per 1M tokens) | Output Price (per 1M tokens) | Best For |
|-------|----------------|-----------------------------|-----------------------------|----------|
| GPT-4.1 | 1M | \$2.00 | \$8.00 | Long-doc analytics, code review |
| GPT-4.1 mini | 1M | \$0.40 | \$1.60 | Production agents, balanced cost/performance |
| GPT-4.1 nano | 1M | \$0.10 | \$0.40 | High-throughput, cost-sensitive applications |
| GPT-4o | 128K | \$5.00 | \$15.00 | Real-time voice/vision chat |
| GPT-4o mini | 128K | \$0.15 | \$0.60 | Vision tasks, rapid analytics |
| o3 (low) | 200K | \$10.00* | \$40.00* | Bulk triage, catalog enrichment |
| o3 (med) | 200K | \$10.00* | \$40.00* | Knowledge base Q&A |
| o3 (high) | 200K | \$10.00* | \$40.00* | Multi-step reasoning, troubleshooting |
| o4-mini (low) | 200K | \$1.10* | \$4.40* | Vision tasks, rapid analytics |
| o4-mini (med) | 200K | \$1.10* | \$4.40* | Balanced vision + reasoning |
| o4-mini (high) | 200K | \$1.10* | \$4.40* | Deep reasoning with cost control |

\* *註：low/med/high 設定影響的是 token 用量，不是基本價格。較高的設定可能用更多 token 做更深的推理，增加每次請求的成本和延遲。*

## 6.2 Prompt 模式速查表（Token 與延遲差異）

| Prompt Pattern | Description | Token Impact | Latency Impact | Best Model Fit |
|----------------|-------------|--------------|----------------|----------------|
| **Self-Critique** | Ask model to evaluate its own answer before finalizing | +20-30% tokens | +15-25% latency | GPT-4.1, o3 |
| **Chain-of-Thought (CoT)** | Explicitly instruct to "think step by step" | +40-80% tokens | +30-50% latency | o3, o4-mini (high) |
| **Structured Outputs** | Use JSON schema or pydantic models for consistent formatting | +5-10% tokens | +5-10% latency | All models |
| **Zero-Token Memory** | Store context in external DB rather than in conversation | -70-90% tokens | -5-10% latency | GPT-4.1 family |
| **Skeleton-Fill-In** | Provide template structure for model to complete | -10-20% tokens | -5-15% latency | o4-mini, GPT-4.1 nano |
| **Self-Consistency** | Generate multiple answers and select most consistent | +200-300% tokens | +150-250% latency | o3 (high) |
| **Role-Playing** | Assign specific personas to model for specialized knowledge | +5-15% tokens | Neutral | GPT-4o, o4-mini |
| **Tournament Ranking** | Compare options pairwise rather than scoring individually | +50-100% tokens | +30-60% latency | o3, o4-mini (high) |
| **Tool-Calling Reflex** | Prompt model to call tools when uncertainty is detected | +10-30% tokens | +20-40% latency | o3, GPT-4.1 |

## 6.3 外部 Cookbook 與文件連結

### OpenAI Official Resources
- [OpenAI Cookbook Main Repository](https://cookbook.openai.com/)
- [Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Vision Models Guide](https://platform.openai.com/docs/guides/vision)
- [Agents Documentation](https://platform.openai.com/docs/guides/agents)
- [Structured Outputs Guide](https://platform.openai.com/docs/guides/structured-outputs)

### RAG & Retrieval
- [RAG on PDFs](https://cookbook.openai.com/examples/file_search_responses)

### Specialized Use Cases
- [Voice Assistant with Agents SDK](https://cookbook.openai.com/examples/agents_sdk/app_assistant_voice_agents)
- [Multi-Tool Orchestration](https://cookbook.openai.com/examples/responses_api/responses_api_tool_orchestration)
- [Data Extraction and Transformation](https://cookbook.openai.com/examples/data_extraction_transformation)

### Prompting & Model Selection
- [GPT-4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)
- [Prompt Engineering Best Practices](https://platform.openai.com/docs/guides/prompt-engineering)

### Evaluation & Deployment
- [Getting Started with OpenAI Evals](https://cookbook.openai.com/examples/evaluation/getting_started_with_openai_evals)
- [How to use the Usage API and Cost API to monitor your OpenAI usage](https://cookbook.openai.com/examples/completions_usage_api)

================================================================================



## 貢獻者

 這份 cookbook 是 OpenAI 和 [Tribe AI](https://www.tribe.ai/) 合作完成的成果。
- [Kashyap Coimbatore Murali](https://www.linkedin.com/in/kashyap-murali/)
- [Nate Harada](https://www.linkedin.com/in/nate-harada/) 
- [Sai Prashanth Soundararaj](https://www.linkedin.com/in/saiprashanths/)
- [Shikhar Kwatra](https://www.linkedin.com/in/shikharkwatra/)

## 重點整理

- 選模型先看任務性質：長文件和一般任務用 GPT-4.1 系列，需要多步驟推理和 tool 使用用 o3，要便宜又快的推理用 o4-mini。
- 常見模式是先用便宜的模型處理廣度，再升級到強的模型做深度審查，成本和品質都兼顧。
- 把工作拆成階段、每階段用最合適的模型（例如 gpt-4.1 做 OCR、o4-mini 做推理），比單用一個最強模型省很多。
- 動態限制輸出選項（List of Literals）和 LLM-as-judge 驗證，能讓 citation 可追溯、答案更可靠。
- 上線前要有量化的成功標準、eval suite、成本護欄、版本固定與 rollback 計畫，高風險輸出要有人工審閱。

## 練習

1. 把 3A 範例的 chunk 數 20 改成 10 或 40，並調整 `max_depth`，觀察導覽結果和成本怎麼變。
2. 把 3A 的 router 模型從 `gpt-4.1-mini` 換成 `gpt-4.1-nano`，比較它選出的 chunk 和 scratchpad 的品質。
3. 在 3C 第二階段多加一個自訂 function（例如檢查郵遞區號是否符合 county），並確認 o4-mini 會呼叫它來補欄位。
