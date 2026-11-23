---
translated: true
source: multimodal/using_sub_agents.ipynb
---

# 用 Haiku 當 sub-agent

> 原文：[multimodal/using_sub_agents.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/multimodal/using_sub_agents.ipynb)

用 Haiku sub-agent 負責擷取資訊、Opus 負責整合，來分析財報。

## 這篇在做什麼

這份範例分析 Apple 2023 年的財報 PDF。先用 Claude Haiku 5.5 sub-agent 從各份財報擷取相關資訊，再用 Claude Opus 5.5 整合出答案，並用 matplotlib 畫出對應的圖。

## 學完你會

- 把 PDF 轉成 base64 PNG 圖片，交給 Haiku 讀取充滿表格的文件。
- 讓 Opus 當 orchestrator，替每個 Haiku sub-agent 寫出針對性的 prompt，並平行執行。
- 把 sub-agent 擷取的結果交給 Opus 生成答案與 matplotlib 程式碼，再抽出程式碼執行。

## 開跑前

需要 Anthropic API key。範例會用 `exec` 執行模型寫的程式碼，正式環境請放在 sandbox 裡。

在這份範例中，我們示範怎麼分析 Apple 2023 年的財報，用 Claude Haiku 5.5 sub-agent model 從財報 PDF 擷取相關資訊。接著用 Claude Opus 5.5 針對我們的問題產生回應，並用 matplotlib 畫出搭配回應的圖。

## 步驟 1：設定環境
首先安裝需要的套件，並設定 Claude API client。

```python
%pip install anthropic IPython PyMuPDF matplotlib
```

```python
# Import the required libraries
import base64
import io
import os
from concurrent.futures import ThreadPoolExecutor

import fitz
import requests
from anthropic import Anthropic
from PIL import Image

# Set up the Claude API client
client = Anthropic()
MODEL_NAME = "claude-haiku-5-5"
```

## 步驟 2：蒐集文件並提問
這個範例會用 Apple 2023 會計年度的所有財務報表，並詢問整年度的淨銷售額。

```python
# List of Apple's earnings release PDF URLs
pdf_urls = [
    "https://www.apple.com/newsroom/pdfs/fy2023-q4/FY23_Q4_Consolidated_Financial_Statements.pdf",
    "https://www.apple.com/newsroom/pdfs/fy2023-q3/FY23_Q3_Consolidated_Financial_Statements.pdf",
    "https://www.apple.com/newsroom/pdfs/FY23_Q2_Consolidated_Financial_Statements.pdf",
    "https://www.apple.com/newsroom/pdfs/FY23_Q1_Consolidated_Financial_Statements.pdf",
]

# User's question
QUESTION = "How did Apple's net sales change quarter to quarter in the 2023 financial year and what were the key contributors to the changes?"
```

## 步驟 3：下載 PDF 並轉成圖片
接著定義 function 下載財報 PDF，並轉成 base64 編碼的 PNG 圖片。需要這樣做，是因為這些 PDF 滿是表格，傳統的 PDF parser 很難解析。直接轉成圖片再傳給 Haiku 比較簡單。

The ```download_pdf``` function downloads a PDF file from a given URL and saves it to the specified folder. The ```pdf_to_base64_pngs``` function converts a PDF to a list of base64-encoded PNG images.

白話講：前者負責下載 PDF，後者負責把 PDF 轉成 base64 PNG 圖片清單。

```python
# Function to download a PDF file from a URL and save it to a specified folder
def download_pdf(url, folder):
    response = requests.get(url, timeout=60)
    if response.status_code == 200:
        file_name = os.path.join(folder, url.split("/")[-1])
        with open(file_name, "wb") as file:
            file.write(response.content)
        return file_name
    else:
        print(f"Failed to download PDF from {url}")
        return None


# Define the function to convert a PDF to a list of base64-encoded PNG images
def pdf_to_base64_pngs(pdf_path, quality=75, max_size=(1024, 1024)):
    # Open the PDF file
    doc = fitz.open(pdf_path)

    base64_encoded_pngs = []

    # Iterate through each page of the PDF
    for page_num in range(doc.page_count):
        # Load the page
        page = doc.load_page(page_num)

        # Render the page as a PNG image
        pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))

        # Convert the pixmap to a PIL Image
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Resize the image if it exceeds the maximum size
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Convert the PIL Image to base64-encoded PNG
        image_data = io.BytesIO()
        image.save(image_data, format="PNG", optimize=True, quality=quality)
        image_data.seek(0)
        base64_encoded = base64.b64encode(image_data.getvalue()).decode("utf-8")
        base64_encoded_pngs.append(base64_encoded)

    # Close the PDF document
    doc.close()

    return base64_encoded_pngs


# Folder to save the downloaded PDFs
folder = "../images/using_sub_agents"


# Create the directory if it doesn't exist
os.makedirs(folder, exist_ok=True)

# Download the PDFs concurrently
with ThreadPoolExecutor() as executor:
    pdf_paths = list(executor.map(download_pdf, pdf_urls, [folder] * len(pdf_urls)))

# Remove any None values (failed downloads) from pdf_paths
pdf_paths = [path for path in pdf_paths if path is not None]
```

我們用 ThreadPoolExecutor 平行下載 PDF，並把檔案路徑存進 pdf_paths。

## 步驟 4：用 Opus 為 Haiku 產生具體的 prompt
讓 Opus 當 orchestrator，根據使用者提供的問題，為每個 Haiku sub-agent 寫出具體的 prompt。

```python
def generate_haiku_prompt(question):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Based on the following question, please generate a specific prompt for an LLM sub-agent to extract relevant information from an earning's report PDF. Each sub-agent only has access to a single quarter's earnings report. Output only the prompt and nothing else.\n\nQuestion: {question}",
                }
            ],
        }
    ]

    response = client.messages.create(model="claude-opus-5-5", max_tokens=2048, messages=messages)

    return "".join(block.text for block in response.content if block.type == "text")


haiku_prompt = generate_haiku_prompt(QUESTION)
print(haiku_prompt)
```

??? note "輸出"

    ```text
    You are analyzing a single Apple Inc. earnings document, such as a Form 10-Q, a Form 10-K, or a quarterly earnings press release. Your output will be combined with other agents' extractions from the other quarters of Apple's fiscal year 2023 to answer this question: "How did Apple's net sales change quarter to quarter in the 2023 financial year and what were the key contributors to the changes?"

    Apple's fiscal year 2023 ran from September 25, 2022 to September 30, 2023:
    - Q1 FY23 ended December 31, 2022
    - Q2 FY23 ended April 1, 2023
    - Q3 FY23 ended July 1, 2023
    - Q4 FY23 ended September 30, 2023 (usually reported in the Form 10-K or the Q4 press release)

    Extract only information stated in your document. Do not estimate or use outside knowledge. If something is missing, write "Not reported in this document."

    **1. Document identification**
    - Document type (10-Q, 10-K, or press release) and filing or release date.
    - The fiscal quarter covered and its exact period-end date.
    - If the document covers the full year (e.g., a 10-K), note this. Extract any Q4-specific figures stated. If only annual and year-to-date figures appear, report them and clearly label them as such. Do not derive Q4 values yourself.

    **2. Total net sales for the quarter**
    - Total net sales for the current quarter, with units (e.g., millions of USD).
    - Total net sales for the same quarter of the prior year.
    - Dollar change and percentage change, exactly as reported.
    - Any year-to-date totals, labeled as year-to-date.

    **3. Net sales by category (current quarter vs. prior-year quarter, with % change)**
    - iPhone
    - Mac
    - iPad
    - Wearables, Home and Accessories
    - Services
    - Total Products vs. total Services, if reported separately

    **4. Net sales by reportable segment (current quarter vs. prior-year quarter, with % change)**
    - Americas
    - Europe
    - Greater China
    - Japan
    - Rest of Asia Pacific

    **5. Key contributors to changes in net sales**
    Extract management's stated explanations, quoting or closely paraphrasing the text from MD&A, segment discussion, or press release commentary. Include:
    - Drivers of increases or decreases for each product category and Services, such as product launches, product mix, demand, pricing, or growth in advertising, cloud, App Store, or payment services.
    - Drivers for each geographic segment.
    ... (省略 18 行)
    ```

## 步驟 5：從 PDF 擷取資訊
現在定義問題，並用 sub-agent Haiku model 從 PDF 擷取資訊。我們把每個 model 的資訊整理成定義明確的一組 XML 標籤。

```python
def extract_info(pdf_path, haiku_prompt):
    base64_encoded_pngs = pdf_to_base64_pngs(pdf_path)

    messages = [
        {
            "role": "user",
            "content": [
                *[
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": base64_encoded_png,
                        },
                    }
                    for base64_encoded_png in base64_encoded_pngs
                ],
                {"type": "text", "text": haiku_prompt},
            ],
        }
    ]

    response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=messages)

    return "".join(block.text for block in response.content if block.type == "text"), pdf_path


def process_pdf(pdf_path):
    return extract_info(pdf_path, haiku_prompt)


# Process the PDFs concurrently with Haiku sub-agent models
with ThreadPoolExecutor() as executor:
    extracted_info_list = list(executor.map(process_pdf, pdf_paths))

extracted_info = ""
# Display the extracted information from each model call
for info in extracted_info_list:
    extracted_info += (
        '<info quarter="' + info[1].split("/")[-1].split("_")[1] + '">' + info[0] + "</info>\n"
    )
print(extracted_info)
```

??? note "輸出"

    ```text
    <info quarter="Q4"># Apple Inc. Earnings Analysis: Q4 FY23 (Three Months Ended September 30, 2023)

    ## 1. Document Identification

    **Document Type:** Condensed Consolidated Statements of Operations and Balance Sheets (Unaudited) and Condensed Consolidated Statements of Cash Flows (Unaudited)

    **Filing/Release Date:** Not explicitly stated in the provided document pages. The document shows financial data as of and for periods ended September 30, 2023 and September 24, 2022.

    **Fiscal Quarter Covered:** Q4 FY23 (Three Months Ended September 30, 2023)

    **Period-End Date:** September 30, 2023

    **Full-Year Data:** The document also presents twelve-month data ended September 30, 2023 and September 24, 2022, representing the full fiscal year 2023.

    **Note:** This appears to be extracted from a Form 10-K or earnings release, as it presents both quarterly and full-year financial statements.

    ---

    ## 2. Total Net Sales for the Quarter

    | Metric | Q4 FY23 (Sept 30, 2023) | Q4 FY22 (Sept 24, 2022) | $ Change | % Change |
    |--------|-------------------------|-------------------------|-----------|-----------|
    | **Total Net Sales** | $89,498 million | $90,146 million | $(648) million | (0.7%) |

    **Year-to-Date (Full Fiscal Year 2023):**

    | Metric | FY 2023 (12 months ended Sept 30, 2023) | FY 2022 (12 months ended Sept 24, 2022) | $ Change | % Change |
    |--------|------------------------------------------|------------------------------------------|-----------|-----------|
    | **Total Net Sales** | $383,285 million | $394,328 million | $(11,043) million | (2.8%) |

    ---

    ## 3. Net Sales by Category (Current Quarter vs. Prior-Year Quarter)

    ### Q4 FY23 vs. Q4 FY22 (Three Months Ended September 30, 2023 vs. September 24, 2022)

    | Product Category | Q4 FY23 | Q4 FY22 | $ Change | % Change |
    |------------------|---------|---------|-----------|-----------|
    | **iPhone** | $43,805 million | $42,626 million | $1,179 million | 2.8% |
    | **Mac** | $7,614 million | $11,508 million | $(3,894) million | (33.8%) |
    ... (省略 378 行)
    ```

我們用 sub-agent model 平行地從 PDF 擷取資訊，並把擷取到的資訊合併起來。接著為強力的 model 準備訊息，包含問題和擷取到的資訊，請它產生回應和 matplotlib 程式碼。

## 步驟 6：把資訊交給 Opus 產生回應
有了 sub-agent 從各份 PDF 取得的資訊，現在呼叫 Opus 實際回答問題，並寫程式畫出搭配答案的圖。

```python
# Prepare the messages for the powerful model
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"Based on the following extracted information from Apple's earnings releases, please provide a response to the question: {QUESTION}\n\nAlso, please generate Python code using the matplotlib library to accompany your response. Enclose the code within <code> tags.\n\nExtracted Information:\n{extracted_info}",
            }
        ],
    }
]

# Generate the matplotlib code using the powerful model
response = client.messages.create(model="claude-opus-5-5", max_tokens=4096, messages=messages)

generated_response = "".join(block.text for block in response.content if block.type == "text")
print("Generated Response:")
print(generated_response)
```

??? note "輸出"

    ```text
    Generated Response:
    # Apple's Quarter-to-Quarter Net Sales Changes in Fiscal 2023

    ## Summary

    Apple's net sales fell for two quarters in a row and then recovered partly in Q4:

    | Quarter (period end) | Net Sales | QoQ $ Change | QoQ % Change | YoY % Change |
    |---|---|---|---|---|
    | Q1 FY23 (Dec 31, 2022) | $117,154M | n/a | n/a | (5.5%) |
    | Q2 FY23 (Apr 1, 2023) | $94,836M | $(22,318)M | (19.1%) | (2.5%) |
    | Q3 FY23 (Jul 1, 2023) | $81,797M | $(13,039)M | (13.7%) | (1.4%) |
    | Q4 FY23 (Sep 30, 2023) | $89,498M | +$7,701M | +9.4% | (0.7%) |
    | **FY23 Total** | **$383,285M** | | | **(2.8%)** |

    The four quarters add up exactly to the reported full-year total of $383,285M.

    **Key takeaways:**
    - **Seasonality drives the pattern.** Q1 is the holiday quarter and the peak. Sales then fell through Q3 and rebounded in Q4.
    - **Year-over-year declines narrowed every quarter**, from −5.5% to −2.5% to −1.4% to −0.7%. Even as the business shrank versus FY22, the trend was improving.
    - **Q1 had an extra week.** Based on the period dates (Sept 25 to Dec 31, 2022), Q1 FY23 covered about 14 weeks versus 13 in the other quarters. Q1 sales still declined 5.5% year over year despite this.

    > **Important caveat:** All four source documents say management's explanations (MD&A / press release commentary) are **not included**. The "contributors" below are therefore derived from the reported category and segment figures, not from management's stated reasons.

    ---

    ## Contributors by Product Category ($ millions)

    | Category | Q1 | Q2 | Q3 | Q4 | Q1→Q2 | Q2→Q3 | Q3→Q4 |
    |---|---|---|---|---|---|---|---|
    | iPhone | 65,775 | 51,334 | 39,669 | 43,805 | (14,441) / −22.0% | (11,665) / −22.7% | +4,136 / +10.4% |
    | Mac | 7,735 | 7,168 | 6,840 | 7,614 | (567) / −7.3% | (328) / −4.6% | +774 / +11.3% |
    | iPad | 9,396 | 6,670 | 5,791 | 6,443 | (2,726) / −29.0% | (879) / −13.2% | +652 / +
    ```

## 步驟 7：抽出回應並執行 Matplotlib 程式碼
最後，從產生的回應中抽出 matplotlib 程式碼並執行，視覺化營收成長趨勢。

我們定義 ```extract_code_and_response``` function，從產生的回應中抽出 matplotlib 程式碼和非程式碼的回應。我們印出非程式碼的回應，如果有找到 matplotlib 程式碼就執行。

注意，在 sandbox 之外對模型寫的程式碼用 ```exec``` 不是好做法，但這個 demo 為了示範就這麼做了 :)

```python
# Extract the matplotlib code from the response
# Function to extract the code and non-code parts from the response
def extract_code_and_response(response):
    start_tag = "<code>"
    end_tag = "</code>"
    start_index = response.find(start_tag)
    end_index = response.find(end_tag)
    if start_index != -1 and end_index != -1:
        code = response[start_index + len(start_tag) : end_index].strip()
        non_code_response = response[:start_index].strip()
        return code, non_code_response
    else:
        return None, response.strip()


matplotlib_code, non_code_response = extract_code_and_response(generated_response)

print(non_code_response)
if matplotlib_code:
    # Execute the extracted matplotlib code
    # Note: exec is used here for demonstration purposes to run model-generated visualization code.
    # In production, use a sandboxed environment for executing untrusted code.
    exec(matplotlib_code)  # noqa: S102
else:
    print("No matplotlib code found in the response.")
```

??? note "輸出"

    ```text
    # Apple's Quarter-to-Quarter Net Sales Changes in Fiscal 2023

    ## Summary

    Apple's net sales fell for two quarters in a row and then recovered partly in Q4:

    | Quarter (period end) | Net Sales | QoQ $ Change | QoQ % Change | YoY % Change |
    |---|---|---|---|---|
    | Q1 FY23 (Dec 31, 2022) | $117,154M | n/a | n/a | (5.5%) |
    | Q2 FY23 (Apr 1, 2023) | $94,836M | $(22,318)M | (19.1%) | (2.5%) |
    | Q3 FY23 (Jul 1, 2023) | $81,797M | $(13,039)M | (13.7%) | (1.4%) |
    | Q4 FY23 (Sep 30, 2023) | $89,498M | +$7,701M | +9.4% | (0.7%) |
    | **FY23 Total** | **$383,285M** | | | **(2.8%)** |

    The four quarters add up exactly to the reported full-year total of $383,285M.

    **Key takeaways:**
    - **Seasonality drives the pattern.** Q1 is the holiday quarter and the peak. Sales then fell through Q3 and rebounded in Q4.
    - **Year-over-year declines narrowed every quarter**, from −5.5% to −2.5% to −1.4% to −0.7%. Even as the business shrank versus FY22, the trend was improving.
    - **Q1 had an extra week.** Based on the period dates (Sept 25 to Dec 31, 2022), Q1 FY23 covered about 14 weeks versus 13 in the other quarters. Q1 sales still declined 5.5% year over year despite this.

    > **Important caveat:** All four source documents say management's explanations (MD&A / press release commentary) are **not included**. The "contributors" below are therefore derived from the reported category and segment figures, not from management's stated reasons.

    ---

    ## Contributors by Product Category ($ millions)

    | Category | Q1 | Q2 | Q3 | Q4 | Q1→Q2 | Q2→Q3 | Q3→Q4 |
    |---|---|---|---|---|---|---|---|
    | iPhone | 65,775 | 51,334 | 39,669 | 43,805 | (14,441) / −22.0% | (11,665) / −22.7% | +4,136 / +10.4% |
    | Mac | 7,735 | 7,168 | 6,840 | 7,614 | (567) / −7.3% | (328) / −4.6% | +774 / +11.3% |
    | iPad | 9,396 | 6,670 | 5,791 | 6,443 | (2,726) / −29.0% | (879) / −13.2% | +652 / +
    No matplotlib code found in the response.
    ```

## 重點整理

- Orchestrator 加 sub-agent 的模式：貴的大 model 負責規劃與整合，便宜快速的小 model 負責大量擷取工作。
- 充滿表格的 PDF 轉成圖片給 vision model 讀，常比傳統 parser 好用。
- 讓 orchestrator 依問題動態產生 sub-agent 的 prompt，比寫死的通用 prompt 更精準。
- Sub-agent 的輸出用 XML 標籤整理，方便程式合併後再交給下一階段。
- 執行模型產生的程式碼要放在 sandbox，`exec` 只適合 demo。

## 練習

1. 把問題改成問整年度的毛利率，看 Opus 產生的 sub-agent prompt 有什麼不同。
2. 調整 ThreadPoolExecutor 的 worker 數，比較處理所有 PDF 的總時間。
3. 修改步驟 7，不要用 `exec`，改成把抽出的程式碼存成檔案，用獨立的 subprocess 並設定 timeout 來執行。
