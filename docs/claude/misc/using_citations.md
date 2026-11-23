---
translated: true
source: misc/using_citations.ipynb
---

# Citations

> 原文：[misc/using_citations.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/using_citations.ipynb)

讓 Claude 在回答文件相關問題時附上詳細的來源引用，方便查證。

## 這篇在做什麼

示範 Claude API 的 citations 功能：回答文件問題時，API 會回傳結構化的引用資料，讓使用者能追溯和驗證來源。內容涵蓋純文字、PDF、自訂內容三種文件，還有 `context` 欄位和 PDF 標記。

## 學完你會

- 用三種文件型態（純文字、PDF、自訂內容）送進 Claude 並取得引用。
- 把結構化的引用資料轉成帶編號的參考文獻格式。
- 用 PyMuPDF 把引用的文字在 PDF 上標記出來。

## 開跑前

需要 Anthropic API key。

Claude API 支援 citations，讓 Claude 回答文件相關問題時附上詳細引用。在很多 LLM 應用裡，引用能幫使用者追蹤並驗證回答的資訊來源。

所有目前的 Claude 模型都支援 citations，清單見 [citations 文件](https://platform.claude.com/docs/en/build-with-claude/citations)。這份 notebook 使用 `claude-sonnet-5-5`。

Citations 功能可以取代用 prompt 要求引用的做法，優點如下：
- 用 prompt 的做法通常要 Claude 輸出想引用的完整原文，會增加 output token，也就增加成本。
- Citations 功能不會回傳指向你沒提供的文件或位置的引用。
- 我們測試時發現，citations 功能產生的引用在 recall 和 precision 上都比用 prompt 的做法高。

Citations 文件在[這裡](https://platform.claude.com/docs/en/build-with-claude/citations)。

## 設定

先安裝需要的套件並初始化 Anthropic client。

```python
%pip install anthropic pymupdf --quiet
```

```python
import json
import os

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# ANTHROPIC_API_KEY = "" # Put your API key here!

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-5-5"
```

## 文件型態

Citations 支援三種文件型態，輸出的引用格式取決於被引用的文件：

* 純文字文件的引用 → char location 格式
* PDF 文件的引用 → page location 格式
* 自訂內容文件的引用 → content block location 格式

下面的例子會逐一示範。

### 純文字文件

用純文字文件時，你把文件當成原始文字交給模型。可以提供一份或多份。文字會自動切成句子，模型會視情況引用這些句子。模型可以把多個句子合併成一個引用，但不會引用比句子更小的片段。

除了輸出的文字，API 回應還會包含所有引用的結構化資料。

我們用一家虛構公司 PetWorld 的客服 help center 聊天機器人來看完整範例。

```python
# Read all help center articles and create a list of documents
articles_dir = "./data/help_center_articles"
documents = []

for filename in sorted(os.listdir(articles_dir)):
    if filename.endswith(".txt"):
        with open(os.path.join(articles_dir, filename)) as f:
            content = f.read()
            # Split into title and body
            title_line, body = content.split("\n", 1)
            title = title_line.replace("title: ", "")
            documents.append(
                {
                    "type": "document",
                    "source": {"type": "text", "media_type": "text/plain", "data": body},
                    "title": title,
                    "citations": {"enabled": True},
                }
            )

QUESTION = "I just checked out, where is my order tracking number? Track package is not available on the website yet for my order."

# Add the question to the content
content = documents

response = client.messages.create(
    model=MODEL,
    max_tokens=2048,
    system="You are a customer support bot working for PetWorld. Your task is to provide short, helpful answers to user questions. Since you are in a chat interface avoid providing extra details. You will be given access to PetWorld's help center articles to help you answer questions.",
    messages=[
        {"role": "user", "content": documents},
        {
            "role": "user",
            "content": [{"type": "text", "text": f"Here is the user's question: {QUESTION}"}],
        },
    ],
)


def visualize_raw_response(response):
    raw_response = {"content": []}

    print("\n" + "=" * 80 + "\nRaw response:\n" + "=" * 80)

    for content in response.content:
        if content.type == "text":
            block = {"type": "text", "text": content.text}
            if hasattr(content, "citations") and content.citations:
                block["citations"] = []
                for citation in content.citations:
                    citation_dict = {
                        "type": citation.type,
                        "cited_text": citation.cited_text,
                        "document_title": citation.document_title,
                    }
                    if citation.type == "page_location":
                        citation_dict.update(
                            {
                                "start_page_number": citation.start_page_number,
                                "end_page_number": citation.end_page_number,
                            }
                        )
                    block["citations"].append(citation_dict)
            raw_response["content"].append(block)

    return json.dumps(raw_response, indent=2)


print(visualize_raw_response(response))
```

??? note "輸出"

    ```text

    ================================================================================
    Raw response:
    ================================================================================
    {
      "content": [
        {
          "type": "text",
          "text": "Based on the documentation, I can explain why you don't see tracking yet: "
        },
        {
          "type": "text",
          "text": "You'll receive an email with your tracking number once your order ships. If you don't receive a tracking number within 48 hours of your order confirmation, please contact our customer support team for assistance.",
          "citations": [
            {
              "type": "char_location",
              "cited_text": "Once your order ships, you'll receive an email with a tracking number. ",
              "document_title": "Order Tracking Information"
            },
            {
              "type": "char_location",
              "cited_text": "If you haven't received a tracking number within 48 hours of your order confirmation, please contact our customer support team.",
              "document_title": "Order Tracking Information"
            }
          ]
        },
        {
          "type": "text",
          "text": "\n\nSince you just checked out, your order likely hasn't shipped yet. Once it ships, you'll receive the tracking information via email."
        }
      ]
    }
    ```

#### 把引用視覺化
有了引用資料，我們就能做出這樣的 UI：

1. 讓使用者看到資訊確切出自哪裡
2. 直接連結到來源文件
3. 在上下文中標出被引用的文字
4. 用透明的出處建立信任

下面是一個簡單的視覺化函式，把 Claude 結構化的引用轉成類似學術論文、帶編號的易讀格式。

這個函式接收 Claude 的 response 物件，輸出：
- 帶編號引用標記的文字（例如「答案 [1] 包含這個事實 [2]」）
- 編號的參考清單，列出每段被引用的文字和來源文件

```python
def visualize_citations(response):
    """
    Takes a response object and returns a string with numbered citations.
    Example output: "here is the plain text answer [1][2] here is some more text [3]"
    with a list of citations below.
    """
    # Dictionary to store unique citations
    citations_dict = {}
    citation_counter = 1

    # Final formatted text
    formatted_text = ""
    citations_list = []

    print("\n" + "=" * 80 + "\nFormatted response:\n" + "=" * 80)

    for content in response.content:
        if content.type == "text":
            text = content.text
            if hasattr(content, "citations") and content.citations:
                # Sort citations by their appearance in the text
                def get_sort_key(citation):
                    if hasattr(citation, "start_char_index"):
                        return citation.start_char_index
                    elif hasattr(citation, "start_page_number"):
                        return citation.start_page_number
                    elif hasattr(citation, "start_block_index"):
                        return citation.start_block_index
                    return 0  # fallback

                sorted_citations = sorted(content.citations, key=get_sort_key)

                # Process each citation
                for citation in sorted_citations:
                    doc_title = citation.document_title
                    cited_text = citation.cited_text.replace("\n", " ").replace("\r", " ")
                    # Remove any multiple spaces that might have been created
                    cited_text = " ".join(cited_text.split())

                    # Create a unique key for this citation
                    citation_key = f"{doc_title}:{cited_text}"

                    # If this is a new citation, add it to our dictionary
                    if citation_key not in citations_dict:
                        citations_dict[citation_key] = citation_counter
                        citations_list.append(
                            f'[{citation_counter}] "{cited_text}" found in "{doc_title}"'
                        )
                        citation_counter += 1

                    # Add the citation number to the text
                    citation_num = citations_dict[citation_key]
                    text += f" [{citation_num}]"

            formatted_text += text

    # Combine the formatted text with the citations list
    final_output = formatted_text + "\n\n" + "\n".join(citations_list)
    return final_output


formatted_response = visualize_citations(response)
print(formatted_response)
```

??? note "輸出"

    ```text

    ================================================================================
    Formatted response:
    ================================================================================
    Based on the documentation, I can explain why you don't see tracking yet: You'll receive an email with your tracking number once your order ships. If you don't receive a tracking number within 48 hours of your order confirmation, please contact our customer support team for assistance. [1] [2]

    Since you just checked out, your order likely hasn't shipped yet. Once it ships, you'll receive the tracking information via email.

    [1] "Once your order ships, you'll receive an email with a tracking number." found in "Order Tracking Information"
    [2] "If you haven't received a tracking number within 48 hours of your order confirmation, please contact our customer support team." found in "Order Tracking Information"
    ```

### PDF 文件

處理 PDF 時，Claude 可以給出指向特定頁碼的引用，方便追蹤資訊來源。PDF 引用的運作方式如下：

- PDF 內容以 base64 編碼的資料提供
- 文字會自動切成句子
- 引用包含資訊所在的頁碼（從 1 開始）
- 模型可以把多個句子合併成一個引用，但不會引用比句子更小的片段
- 圖片雖然會被處理，但目前只有文字內容可以被引用

下面用 Constitutional AI 論文來示範 PDF 引用：

```python
import base64
import json

# Read and encode the PDF
pdf_path = "data/Constitutional AI.pdf"
with open(pdf_path, "rb") as f:
    pdf_data = base64.b64encode(f.read()).decode()

pdf_response = client.messages.create(
    model=MODEL,
    max_tokens=2048,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_data},
                    "title": "Constitutional AI Paper",
                    "citations": {"enabled": True},
                },
                {"type": "text", "text": "What is the main idea of Constitutional AI?"},
            ],
        }
    ],
)

print(visualize_raw_response(pdf_response))
print(visualize_citations(pdf_response))
```

??? note "輸出"

    ```text

    ================================================================================
    Raw response:
    ================================================================================
    {
      "content": [
        {
          "type": "text",
          "text": "Based on the paper, here are the key aspects of Constitutional AI:\n\n"
        },
        {
          "type": "text",
          "text": "Constitutional AI is a method for training a harmless AI assistant through self-improvement, without any human labels identifying harmful outputs. The only human oversight is provided through a list of rules or principles, hence the name \"Constitutional AI\".",
          "citations": [
            {
              "type": "page_location",
              "cited_text": "We experiment with methods for training a harmless AI assistant through self\u0002improvement, without any human labels identifying harmful outputs. The only human\r\noversight is provided through a list of rules or principles, and so we refer to the method as\r\n\u2018Constitutional AI\u2019. ",
              "document_title": "Constitutional AI Paper",
              "start_page_number": 1,
              "end_page_number": 2
            }
          ]
        },
        {
          "type": "text",
          "text": "\n\nThe process involves two main phases:\n\n1. Supervised Learning Phase:\n"
        },
        {
          "type": "text",
          "text": "In this phase, they sample from an initial model, generate self-critiques and revisions, and then finetune the original model on revised responses.",
          "citations": [
            {
              "type": "page_location",
              "cited_text": "In the supervised phase we sample from an initial model, then generate\r\nself-critiques and revisions, and then finetune the original model on revised responses. ",
              "document_title": "Constitutional AI Paper",
              "start_page_number": 1,
              "end_page_number": 2
            }
          ]
        },
    ... (省略 86 行)
    ```

### 自訂內容文件

純文字文件會自動切成句子，自訂內容文件則讓你完全控制引用的粒度。這種 API 形式讓你可以：

* 自己定義任意大小的 chunk
* 控制最小的引用單位
* 針對不適合用句子切分的文件做最佳化

下面的例子用跟上面純文字範例一樣的 help center 文章，但不允許句子層級的引用，而是把每篇文章當成單一 chunk。這能說明文件型態的選擇如何影響引用行為和粒度。你會看到 `cited_text` 是整篇文章，而不是原文中的一個句子。

```python
# Read all help center articles and create a list of custom content documents
articles_dir = "./data/help_center_articles"
documents = []

for filename in sorted(os.listdir(articles_dir)):
    if filename.endswith(".txt"):
        with open(os.path.join(articles_dir, filename)) as f:
            content = f.read()
            # Split into title and body
            title_line, body = content.split("\n", 1)
            title = title_line.replace("title: ", "")

            documents.append(
                {
                    "type": "document",
                    "source": {"type": "content", "content": [{"type": "text", "text": body}]},
                    "title": title,
                    "citations": {"enabled": True},
                }
            )

QUESTION = "I just checked out, where is my order tracking number? Track package is not available on the website yet for my order."

custom_content_response = client.messages.create(
    model=MODEL,
    max_tokens=2048,
    system="You are a customer support bot working for PetWorld. Your task is to provide short, helpful answers to user questions. Since you are in a chat interface avoid providing extra details. You will be given access to PetWorld's help center articles to help you answer questions.",
    messages=[
        {"role": "user", "content": documents},
        {
            "role": "user",
            "content": [{"type": "text", "text": f"Here is the user's question: {QUESTION}"}],
        },
    ],
)

print(visualize_raw_response(custom_content_response))
print(visualize_citations(custom_content_response))
```

??? note "輸出"

    ```text

    ================================================================================
    Raw response:
    ================================================================================
    {
      "content": [
        {
          "type": "text",
          "text": "You should receive an email with your tracking number once your order ships. If it's been less than 48 hours since your order confirmation, please wait as the tracking number may not be available yet. If you haven't received a tracking number after 48 hours, please contact our customer support team for assistance.",
          "citations": [
            {
              "type": "content_block_location",
              "cited_text": "Once your order ships, you'll receive an email with a tracking number. To track your package, log in to your PetWorld account and go to \"Order History.\" Click on the order you want to track and select \"Track Package.\" This will show you the current status and estimated delivery date. You can also enter the tracking number directly on our shipping partner's website for more detailed information. If you haven't received a tracking number within 48 hours of your order confirmation, please contact our customer support team.",
              "document_title": "Order Tracking Information"
            }
          ]
        }
      ]
    }

    ================================================================================
    Formatted response:
    ================================================================================
    You should receive an email with your tracking number once your order ships. If it's been less than 48 hours since your order confirmation, please wait as the tracking number may not be available yet. If you haven't received a tracking number after 48 hours, please contact our customer support team for assistance. [1]

    [1] "Once your order ships, you'll receive an email with a tracking number. To track your package, log in to your PetWorld account and go to "Order History." Click on the order you want to track and select "Track Package." This will show you the current status and estimated delivery date. You can also enter the tracking number directly on our shipping partner's website for more detailed information. If you haven't received a tracking number within 48 hours of your order confirmation, please contact our customer support team." found in "Order Tracking Information"
    ```

### 使用 context 欄位

`context` 欄位讓你提供文件的額外資訊，Claude 產生回答時可以參考，但這些內容不會被引用。適合用在：

* 提供文件的 metadata（例如發佈日期、作者）
* [Contextual retrieval](https://www.anthropic.com/news/contextual-retrieval)
* 放不該被直接引用的使用說明或背景

下面的例子在 context 欄位放了一則關於忠誠度方案文章的警告。可以看到 Claude 會用 context 裡的資訊來影響回答，但 context 的內容不能被引用。

```python
import json

# Create a document with context field
document = {
    "type": "document",
    "source": {
        "type": "text",
        "media_type": "text/plain",
        "data": "PetWorld offers a loyalty program where customers earn 1 point for every dollar spent. Once you accumulate 100 points, you'll receive a $5 reward that can be used on your next purchase. Points expire 12 months after they are earned. You can check your point balance in your account dashboard or by asking customer service.",
    },
    "title": "Loyalty Program Details",
    "context": "WARNING: This article has not been updated in 12 months. Content may be out of date. Be sure to inform the user this content may be incorrect after providing guidance.",
    "citations": {"enabled": True},
}

QUESTION = "How does PetWorld's loyalty program work? When do points expire?"

context_response = client.messages.create(
    model=MODEL,
    max_tokens=2048,
    messages=[{"role": "user", "content": [document, {"type": "text", "text": QUESTION}]}],
)

print(visualize_raw_response(context_response))
print(visualize_citations(context_response))
```

??? note "輸出"

    ```text

    ================================================================================
    Raw response:
    ================================================================================
    {
      "content": [
        {
          "type": "text",
          "text": "Let me explain PetWorld's loyalty program based on the provided information:\n\n"
        },
        {
          "type": "text",
          "text": "PetWorld's loyalty program is straightforward - you earn 1 point for every dollar you spend. These points can be redeemed once you reach 100 points, which will get you a $5 reward that you can use on your next purchase.",
          "citations": [
            {
              "type": "char_location",
              "cited_text": "PetWorld offers a loyalty program where customers earn 1 point for every dollar spent. Once you accumulate 100 points, you'll receive a $5 reward that can be used on your next purchase. ",
              "document_title": "Loyalty Program Details"
            }
          ]
        },
        {
          "type": "text",
          "text": "\n\n"
        },
        {
          "type": "text",
          "text": "Points have an expiration period of 12 months from the date they are earned.",
          "citations": [
            {
              "type": "char_location",
              "cited_text": "Points expire 12 months after they are earned. ",
              "document_title": "Loyalty Program Details"
            }
          ]
        },
        {
          "type": "text",
          "text": "\n\n"
        },
    ... (省略 34 行)
    ```

### PDF 標記

PDF 引用有個限制：只會回傳頁碼。你可以用第三方函式庫，把回傳的引用文字對到頁面內容，標出被引用的部分。這個 cell 用 Claude 和 PyMuPDF 示範 PDF 引用標記，並產生一份新的標註 PDF：

```python
import fitz  # PyMuPDF

# Setup paths and read PDF
pdf_path = "data/Amazon-com-Inc-2023-Shareholder-Letter.pdf"
output_pdf_path = "data/Amazon-com-Inc-2023-Shareholder-Letter-highlighted.pdf"

# Read and encode the PDF
with open(pdf_path, "rb") as f:
    pdf_data = base64.b64encode(f.read()).decode()

response = client.messages.create(
    model=MODEL,
    max_tokens=2048,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_data},
                    "title": "Amazon 2023 Shareholder Letter",
                    "citations": {"enabled": True},
                },
                {
                    "type": "text",
                    "text": "What was Amazon's total revenue in 2023 and how much did it grow year-over-year?",
                },
            ],
        }
    ],
)

print(visualize_raw_response(response))

# Collect PDF citations
pdf_citations = []
for content in response.content:
    if hasattr(content, "citations") and content.citations:
        for citation in content.citations:
            if citation.type == "page_location":
                pdf_citations.append(citation)

doc = fitz.open(pdf_path)

# Process each citation
for citation in pdf_citations:
    if citation.type == "page_location":
        text_to_find = citation.cited_text.replace("\u0002", "")
        start_page = citation.start_page_number - 1  # Convert to 0-based index
        end_page = citation.end_page_number - 2

        # Process each page in the citation range
        for page_num in range(start_page, end_page + 1):
            page = doc[page_num]

            text_instances = page.search_for(text_to_find.strip())

            if text_instances:
                print(f"Found cited text on page {page_num + 1}")
                for inst in text_instances:
                    highlight = page.add_highlight_annot(inst)
                    highlight.set_colors({"stroke": (1, 1, 0)})  # Yellow highlight
                    highlight.update()
            else:
                print(f"{text_to_find} not found on page {page_num + 1}")

# Save the new PDF
doc.save(output_pdf_path)
doc.close()

print(f"\nCreated highlighted PDF at: {output_pdf_path}")
```

??? note "輸出"

    ```text

    ================================================================================
    Raw response:
    ================================================================================
    {
      "content": [
        {
          "type": "text",
          "text": "According to the letter, "
        },
        {
          "type": "text",
          "text": "Amazon's total revenue grew 12% year-over-year (\"YoY\") from $514B to $575B in 2023",
          "citations": [
            {
              "type": "page_location",
              "cited_text": "In 2023, Amazon\u2019s total revenue grew 12% year-over-year (\u201cYoY\u201d) from $514B to $575B. ",
              "document_title": "Amazon 2023 Shareholder Letter",
              "start_page_number": 1,
              "end_page_number": 2
            }
          ]
        },
        {
          "type": "text",
          "text": ".\n\nBreaking this down by segment:\n"
        },
        {
          "type": "text",
          "text": "\n- North America revenue increased 12% YoY from $316B to $353B\n- International revenue grew 11% YoY from $118B to $131B  \n- AWS revenue increased 13% YoY from $80B to $91B",
          "citations": [
            {
              "type": "page_location",
              "cited_text": "By segment, North\r\nAmerica revenue increased 12% YoY from $316B to $353B, International revenue grew 11% YoY from\r\n$118B to $131B, and AWS revenue increased 13% YoY from $80B to $91B.\r\n",
              "document_title": "Amazon 2023 Shareholder Letter",
              "start_page_number": 1,
              "end_page_number": 2
            }
          ]
        }
    ... (省略 6 行)
    ```

## 重點整理
- Citations 由 API 直接回傳結構化引用，比用 prompt 要求引用省 token，也不會引用不存在的來源。
- 引用格式跟文件型態綁定：純文字是 char location，PDF 是 page location，自訂內容是 content block location。
- 純文字和 PDF 以句子為最小引用單位，要更粗或更細的粒度就用自訂內容文件。
- `context` 欄位能給 Claude 背景資訊但不會被引用。
- PDF 引用只有頁碼，要在頁面上標出文字得自己搭配第三方函式庫。

## 練習
1. 在純文字範例多加一份 help center 文件，問一個需要跨兩份文件回答的問題，觀察引用。
2. 把自訂內容文件的 chunk 改成按段落切，看 `cited_text` 的粒度變化。
3. 在 `context` 放一段不同的警告或日期資訊，確認它影響回答但不出現在引用裡。
