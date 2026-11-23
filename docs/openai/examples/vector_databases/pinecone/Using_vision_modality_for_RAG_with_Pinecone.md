---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/pinecone/Using_vision_modality_for_RAG_with_Pinecone.ipynb
---

# 用 GPT-4o Vision 優化 Retrieval-Augmented Generation

> 原文：[examples/vector_databases/pinecone/Using_vision_modality_for_RAG_with_Pinecone.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/Using_vision_modality_for_RAG_with_Pinecone.ipynb)



## 這篇在做什麼
這篇處理圖表、表格很多的 PDF 該怎麼做 RAG。做法是先把每一頁轉成圖片，用 GPT-4o vision 抽出文字並描述圖表，存進 Pinecone；檢索到有視覺內容的頁面時，再把整頁圖片直接丟給 GPT-4o 回答。範例文件是世界銀行 2024 年報。

## 學完你會
- 建立 Pinecone index，並把每頁文字的 embedding 連同 metadata 用 upsert 寫進去
- 把 PDF 頁面轉成圖片，用 GPT-4o vision 抽出文字和圖表、表格的描述，並標記哪些頁面有視覺內容
- 做語意搜尋回答問題，遇到有視覺內容的頁面就改用頁面圖片當 context

## 開跑前
- 需要 Pinecone 帳號和 API key，放在 `.env` 的 `PINECONE_API_KEY`
- 需要 OpenAI API key，另外可能要裝 Poppler 才能轉 PDF 圖片
- Vision 呼叫比較貴也比較慢，處理整份年報會花一些費用

## 用 GPT-4o Vision 優化 Retrieval-Augmented Generation

要對圖片、圖表和表格很多的文件做 Retrieval-Augmented Generation (RAG)，會碰到一些特別的難題。傳統 RAG 處理純文字資料很強，但當視覺元素是傳遞資訊的關鍵時，常常不夠用。這份 cookbook 用 vision modality 來抽取並解讀視覺內容，補上這個缺口，讓產生的回答盡可能完整、準確。

我們的做法是把文件解析成圖片，並用 metadata 標記哪些頁面有圖片、圖表和表格。語意搜尋檢索到這類頁面時，我們把頁面圖片傳給 vision 模型，而不是只靠文字。這樣模型更能理解跟視覺資料有關的使用者問題。

這份 cookbook 會介紹並示範以下重點：

##### 1. 用 Pinecone 建立 Vector Store：
- 學會如何初始化並設定 Pinecone，有效率地儲存向量 embeddings。

##### 2. 解析 PDF 並抽取視覺資訊：
- 了解把 PDF 頁面轉成圖片的技巧。
- 用 GPT-4o vision modality 從有圖片、圖表或表格的頁面抽出文字資訊。  

##### 3. 產生 Embeddings： 
- 用 embedding 模型建立文字資料的向量表示。 
- 標記有視覺內容的頁面，在 vector store 上設一個 metadata 旗標，之後檢索時就能取出圖片，用 vision modality 傳給 GPT-4o。 

##### 4. 把 Embeddings 上傳到 Pinecone： 
- 把這些 embeddings 上傳到 Pinecone 儲存和檢索。 

##### 5. 對相關頁面做語意搜尋：
- 對頁面文字做語意搜尋，找出最符合使用者問題的頁面。 
- 把符合的頁面文字當 context 提供給 GPT-4o，回答使用者的問題。  

##### 6. 處理有視覺內容的頁面（選用步驟）：
- 學會如何用 GPT-4o vision modality 傳入圖片，搭配額外 context 回答問題。 
- 了解這個流程怎麼提高涉及視覺資料的回答準確度。
 
讀完這份 cookbook，你會對如何實作能處理並解讀複雜視覺元素文件的 RAG 系統有紮實的了解，也能做出提供更豐富、更準確資訊的 AI 解決方案。

我們用世界銀行的報告 [A Better Bank for a Better World: Annual Report 2024](https://documents1.worldbank.org/curated/en/099101824180532047/pdf/BOSIB13bdde89d07f1b3711dd8e86adb477.pdf) 來說明這些概念，因為這份文件同時有圖片、表格和圖形資料。 

注意，使用 Vision Modality 很吃資源，會增加延遲和成本。建議只在純文字抽取方法在評測 benchmark 上表現不理想時，才使用 Vision Modality。了解這點之後，我們開始吧。

### Step 1：用 Pinecone 建立 Vector Store 
這一節我們用 Pinecone 建立 vector store，有效率地儲存和管理 embeddings。Pinecone 是針對高維向量資料最佳化的向量資料庫，這對語意搜尋和相似度比對這類任務很重要。

**先決條件** 
1. 註冊 Pinecone 並取得 API key，步驟請看這裡 [Pinecone Database Quickstart](https://docs.pinecone.io/guides/get-started/quickstart)  
2. 用 `pip install "pinecone[grpc]"` 安裝 Pinecone SDK。gRPC（gRPC Remote Procedure Call）是高效能的開源通用 RPC 框架，用 HTTP/2 傳輸，用 Protocol Buffers (protobuf) 當介面定義語言，讓分散式系統中的 client 和 server 能溝通。它是為了讓服務之間的通訊更有效率而設計，很適合 microservices 架構。   

**安全地存放 API Key**  
1. 為了安全，把 API key 存在專案目錄下的 .env 檔裡，格式如下：  
 `PINECONE_API_KEY=your-api-key-here`。   
 2. 安裝 `pip install python-dotenv`，用它從 .env 檔讀取 API Key。 

**建立 Pinecone Index**   
我們用 `create_index` 函式在 Pinecone 上初始化 embeddings 資料庫。有兩個關鍵參數要考慮：

1. Dimension：必須跟你選的模型產生的 embedding 維度一致。例如 OpenAI 的 text-embedding-ada-002 產生 1536 維的 embeddings，text-embedding-3-large 則是 3072 維。我們用 text-embedding-3-large，所以維度設 3072。

2. Metric：距離度量決定向量之間的相似度怎麼計算。Pinecone 支援幾種度量，包括 cosine、dotproduct 和 euclidean。這份 cookbook 用 cosine similarity。更多度量的說明可以看 [Pinecone Distance Metrics documentation](https://docs.pinecone.io/guides/indexes/understanding-indexes#distance-metrics)。

```python
import os
import time
# Import the Pinecone library
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("PINECONE_API_KEY")

# Initialize a Pinecone client with your API key
pc = Pinecone(api_key)

# Create a serverless index
index_name = "my-test-index"

if not pc.has_index(index_name):
    pc.create_index(
        name=index_name,
        dimension=3072,
        metric="cosine",
        spec=ServerlessSpec(
            cloud='aws',
            region='us-east-1'
        )
    )

# Wait for the index to be ready
while not pc.describe_index(index_name).status['ready']:
    time.sleep(1)
```

到 [Pinecone](https://app.pinecone.io/) 的 Indexes 列表，你應該可以在清單中看到 `my-test-index`。 

### Step 2：解析 PDF 並抽取視覺資訊：

這一節我們解析世界銀行報告 [A Better Bank for a Better World: Annual Report 2024](https://documents1.worldbank.org/curated/en/099101824180532047/pdf/BOSIB13bdde89d07f1b3711dd8e86adb477.pdf) 這份 PDF，抽出文字和視覺資訊，例如描述圖片、圖形和表格。過程分三個主要步驟：

1. **把 PDF 解析成單獨的頁面：** 把 PDF 切成一頁一頁，方便處理。
2. **把 PDF 頁面轉成圖片：** 這樣 GPT-4o 的 vision 能力才能把頁面當圖片來分析。  
3. **處理圖片和表格：** 給 GPT-4o 指示，抽出文字，並描述文件中的圖片、圖形或表格。 

**先決條件**

開始之前，確認已安裝下列套件，並確保 OpenAI API key 已設成環境變數。你可能還需要安裝 Poppler 來渲染 PDF。  

`pip install PyPDF2 pdf2image pytesseract pandas tqdm`
 
**步驟拆解：**

**1. 下載並切分 PDF：**  
- `chunk_document` 函式從提供的 URL 下載 PDF，並用 PyPDF2 切成單獨的頁面。
- 每一頁都以獨立的 PDF byte stream 存在一個 list 裡。

**2. 把 PDF 頁面轉成圖片：** 
- `convert_page_to_image` 函式接收單一頁面的 PDF bytes，並用 pdf2image 轉成圖片。
- 圖片會存在本機的 'images' 目錄，供後續處理。

**3. 用 GPT-4o vision modality 抽取文字：**
- `extract_text_from_image` 函式用 GPT-4o 的 vision 能力，從頁面圖片抽出文字。
- 這個方法連掃描文件都能抽出文字資訊。
- 注意這個 modality 很吃資源，所以延遲和成本都比較高。 

**4. 處理整份文件：** 
- process_document 函式負責統籌每一頁的處理。
- 它用進度條（tqdm）顯示處理狀態。
- 每一頁抽出的資訊會收集到 list 裡，再轉成 Pandas DataFrame。

```python
import base64
import requests
import os
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter
from pdf2image import convert_from_bytes
from io import BytesIO
from openai import OpenAI
from tqdm import tqdm

# Link to the document we will use as the example 
document_to_parse = "https://documents1.worldbank.org/curated/en/099101824180532047/pdf/BOSIB13bdde89d07f1b3711dd8e86adb477.pdf"

# OpenAI client 
oai_client = OpenAI()


# Chunk the PDF document into single page chunks 
def chunk_document(document_url):
    # Download the PDF document
    response = requests.get(document_url)
    pdf_data = response.content

    # Read the PDF data using PyPDF2
    pdf_reader = PdfReader(BytesIO(pdf_data))
    page_chunks = []

    for page_number, page in enumerate(pdf_reader.pages, start=1):
        pdf_writer = PdfWriter()
        pdf_writer.add_page(page)
        pdf_bytes_io = BytesIO()
        pdf_writer.write(pdf_bytes_io)
        pdf_bytes_io.seek(0)
        pdf_bytes = pdf_bytes_io.read()
        page_chunk = {
            'pageNumber': page_number,
            'pdfBytes': pdf_bytes
        }
        page_chunks.append(page_chunk)

    return page_chunks


# Function to encode the image
def encode_image(local_image_path):
    with open(local_image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Function to convert page to image     
def convert_page_to_image(pdf_bytes, page_number):
    # Convert the PDF page to an image
    images = convert_from_bytes(pdf_bytes)
    image = images[0]  # There should be only one page

    # Define the directory to save images (relative to your script)
    images_dir = 'images'  # Use relative path here

    # Ensure the directory exists
    os.makedirs(images_dir, exist_ok=True)

    # Save the image to the images directory
    image_file_name = f"page_{page_number}.png"
    image_file_path = os.path.join(images_dir, image_file_name)
    image.save(image_file_path, 'PNG')

    # Return the relative image path
    return image_file_path


# Pass the image to the LLM for interpretation  
def get_vision_response(prompt, image_path):
    # Getting the base64 string
    base64_image = encode_image(image_path)

    response = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        },
                    },
                ],
            }
        ],
    )
    return response


# Process document function that brings it all together 
def process_document(document_url):
    try:
        # Update document status to 'Processing'
        print("Document processing started")

        # Get per-page chunks
        page_chunks = chunk_document(document_url)
        total_pages = len(page_chunks)

        # Prepare a list to collect page data
        page_data_list = []

        # Add progress bar here
        for page_chunk in tqdm(page_chunks, total=total_pages, desc='Processing Pages'):
            page_number = page_chunk['pageNumber']
            pdf_bytes = page_chunk['pdfBytes']

            # Convert page to image
            image_path = convert_page_to_image(pdf_bytes, page_number)

            # Prepare question for vision API
            system_prompt = (
                "The user will provide you an image of a document file. Perform the following actions: "
                "1. Transcribe the text on the page. **TRANSCRIPTION OF THE TEXT:**"
                "2. If there is a chart, describe the image and include the text **DESCRIPTION OF THE IMAGE OR CHART**"
                "3. If there is a table, transcribe the table and include the text **TRANSCRIPTION OF THE TABLE**"
            )

            # Get vision API response
            vision_response = get_vision_response(system_prompt, image_path)

            # Extract text from vision response
            text = vision_response.choices[0].message.content

            # Collect page data
            page_data = {
                'PageNumber': page_number,
                'ImagePath': image_path,
                'PageText': text
            }
            page_data_list.append(page_data)

        # Create DataFrame from page data
        pdf_df = pd.DataFrame(page_data_list)
        print("Document processing completed.")
        print("DataFrame created with page data.")

        # Return the DataFrame
        return pdf_df

    except Exception as err:
        print(f"Error processing document: {err}")
        # Update document status to 'Error'


df = process_document(document_to_parse)
```

??? note "輸出"

    ```text
    Document processing started
    ```

    ```text
    Processing Pages: 100%|██████████| 49/49 [18:54<00:00, 23.14s/it]
    ```

    ```text
    Document processing completed.
    DataFrame created with page data.
    ```

我們來檢查 DataFrame，確認頁面處理正確。為了簡潔，只取出並顯示前五列。另外你也應該能在 'images' 目錄看到產生的頁面圖片。

```python
from IPython.display import display, HTML

# Convert the DataFrame to an HTML table and display top 5 rows 
display(HTML(df.head().to_html()))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

來看一個範例頁面，例如第 21 頁，這頁同時有嵌入的圖形和文字。可以看到 vision modality 有效地抽出並描述了視覺資訊。例如這一頁的圓餅圖被準確描述成：

`"FIGURE 6: MIDDLE EAST AND NORTH AFRICA IBRD AND IDA LENDING BY SECTOR - FISCAL 2024 SHARE OF TOTAL OF $4.6 BILLION" is a circular chart, resembling a pie chart, illustrating the percentage distribution of funds among different sectors. The sectors include:`

```python
# Filter and print rows where pageNumber is 21
filtered_rows = df[df['PageNumber'] == 21]
for text in filtered_rows.PageText:
    print(text)
```

??? note "輸出"

    ```text
    **TRANSCRIPTION OF THE TEXT:**

    We also committed $35 million in grants to support emergency relief in Gaza. Working with the World Food Programme, the World Health Organization, and the UN Children’s Fund, the grants supported the delivery of emergency food, water, and medical supplies. In the West Bank, we approved a $200 million program for the continuation of education for children, $22 million to support municipal services, and $45 million to strengthen healthcare and hospital services.

    **Enabling green and resilient growth**
    To help policymakers in the region advance their climate change and development goals, we published Country Climate and Development Reports for the West Bank and Gaza, Lebanon, and Tunisia. In Libya, the catastrophic flooding in September 2023 devastated eastern localities, particularly the city of Derna. The World Bank, together with the UN and the European Union, produced a Rapid Damage and Needs Assessment to inform recovery and reconstruction efforts.

    We signed a new Memorandum of Understanding (MoU) with the Islamic Development Bank to promote further collaboration between our institutions. The MoU focuses on joint knowledge and operational engagements around the energy, food, and water nexus, climate impact, empowering women and youth to engage with the private sector, and advancing the digital transition and regional integration. The MoU aims to achieve a co-financing value of $6 billion through 2026, 45 percent of which has already been met.

    **Expanding economic opportunities for women**
    The World Bank has drawn on a variety of instruments to support Jordan’s commitment to increase female labor force participation, including through the recently approved Country Partnership Framework. Through operations, technical assistance (such as Mashreq Gender Facility; Women Entrepreneurs Finance Initiative; and the Women, Business and the Law report), and policy dialogue, we have contributed to legal reforms in Jordan that removed job restrictions on women, prohibited gender-based discrimination in the workplace, and criminalized sexual harassment in the workplace. In fiscal 2024, we approved the first women-focused Bank project in the region: the Enhancing Women’s Economic Opportunities Program for Results aims to improve workplace conditions, increase financial inclusion and entrepreneurship, make public transport safer, and increase access to affordable, quality childcare services.

    **Analyzing critical infrastructure needs**
    We published an Interim Damage Assessment for Gaza in partnership with the UN and with financial support from the EU. This found that a preliminary estimate of the cost of damages to critical infrastructure from the conflict in Gaza between October 2023 and the end of January 2024 was around $18.5 billion—equivalent to 97 percent of the 2022 GDP of the West Bank and Gaza combined. When the situation allows, a full-fledged Rapid Damage and Needs Assessment will be conducted.

    **COUNTRY IMPACT**

    Egypt: The Bank-supported Takaful and Karama social protection program has reached 4.7 million vulnerable households, benefitting approximately 20 million individuals, 75 percent of them women.

    Lebanon: A roads project has rehabilitated over 500 km of roads in 25 districts across the country and generated 1.3 million labor days for Lebanese workers and Syrian refugees.

    Morocco: Our programs have benefited more than 400,000 people directly and more than 33 million people indirectly, through more than 230 disaster risk reduction projects.

    **DESCRIPTION OF THE IMAGE OR CHART:**

    The image is a pie chart titled "FIGURE 6: MIDDLE EAST AND NORTH AFRICA IBRD AND IDA LENDING BY SECTOR - FISCAL 2024 SHARE OF TOTAL OF $4.6 BILLION." The chart breaks down the sectors as follows:
    - Public Administration: 24%
    - Social Protection: 13%
    - Health: 13%
    - Education: 17%
    - Agriculture, Fishing, and Forestry: 8%
    - Water, Sanitation, and Waste Management: 8%
    - Transportation: 5%
    - Energy and Extractives: 3%
    - Financial Sector: 1%
    - Industry, Trade, and Services: 2%
    - Information and Communications Technologies: 6%

    **TRANSCRIPTION OF THE TABLE:**

    ... (省略 27 行)
    ```

### Step 3：產生 Embeddings： 

這一節我們把每一頁抽出的文字內容轉成向量 embeddings。這些 embeddings 捕捉文字的語意，讓相似度搜尋和各種自然語言處理（NLP）任務可以有效率地進行。我們也會找出含有圖片、圖形或表格等視覺元素的頁面，標記起來做特殊處理。

**步驟拆解：**

**1. 加上視覺內容的旗標**   
  
為了處理含有視覺資訊的頁面，我們在 Step 2 用 vision modality 抽取圖表、表格和圖片的內容。透過在 prompt 裡加入特定指示，我們讓模型在描述視覺內容時加上標記，例如 `DESCRIPTION OF THE IMAGE OR CHART` 或 `TRANSCRIPTION OF THE TABLE`。這一步如果偵測到這類標記，就把 Visual_Input_Processed 旗標設為 'Y'，否則維持 'N'。

vision modality 雖然能有效捕捉大部分視覺資訊，但有些細節，尤其是工程圖這類複雜的視覺內容，可能在轉成文字時流失。在 Step 6，我們會用這個旗標決定什麼時候把頁面圖片當作額外 context 傳給 GPT-4 Vision。這是選用的強化手段，可以大幅提升 RAG 方案的效果。  

**2. 用 OpenAI 的 Embedding 模型產生 Embeddings**  

我們用 OpenAI 的 embedding 模型 `text-embedding-3-large`，產生代表每頁語意內容的高維 embeddings。 

注意：你用的 embedding 模型的維度，一定要跟 Pinecone vector store 的設定一致。我們的 Pinecone 資料庫設成 3072 維，就是為了配合 `text-embedding-3-large` 的預設維度。  


```python
# Add a column to flag pages with visual content
df['Visual_Input_Processed'] = df['PageText'].apply(
    lambda x: 'Y' if 'DESCRIPTION OF THE IMAGE OR CHART' in x or 'TRANSCRIPTION OF THE TABLE' in x else 'N'
)


# Function to get embeddings
def get_embedding(text_input):
    response = oai_client.embeddings.create(
        input=text_input,
        model="text-embedding-3-large"
    )
    return response.data[0].embedding


# Generate embeddings with a progress bar
embeddings = []
for text in tqdm(df['PageText'], desc='Generating Embeddings'):
    embedding = get_embedding(text)
    embeddings.append(embedding)

# Add the embeddings to the DataFrame
df['Embeddings'] = embeddings
```

??? note "輸出"

    ```text
    Generating Embeddings: 100%|██████████| 49/49 [00:18<00:00,  2.61it/s]
    ```

我們可以確認邏輯有正確標出需要視覺輸入的頁面。例如前面看過的第 21 頁，它的 Visual_Input_Needed 旗標是 "Y"。

```python
# Display the flag for page 21 
filtered_rows = df[df['PageNumber'] == 21]
print(filtered_rows.Visual_Input_Processed)
```

??? note "輸出"

    ```text
    20    Y
    Name: Visual_Input_Processed, dtype: object
    ```

#### Step 4：把 embeddings 上傳到 Pinecone： 

這一節我們把為文件每一頁產生的 embeddings 上傳到 Pinecone。除了 embeddings，也會附上描述每一頁的相關 metadata 標籤，例如頁碼、文字內容、圖片路徑，以及這頁是否含有圖形。 

**步驟拆解：**  

**1. 建立 Metadata 欄位：**  
Metadata 讓我們能做更細緻的搜尋，找到跟向量相關的文字或圖片，並在向量資料庫內做過濾。
* pageId：結合 document_id 和 pageNumber，為每一頁建立唯一識別碼。我們用它當 embeddings 的唯一 ID。 
* pageNumber：頁面在文件中的數字頁碼。
* text：從該頁抽出的文字內容。
* ImagePath：該頁對應圖片的檔案路徑。
* GraphicIncluded：布林值或旗標，表示該頁是否含有可能需要視覺處理的圖形元素。

**2. 上傳 embeddings：**  
我們用 Pinecone API 的 `upsert_vector` 函式去「upsert」這些值 - 

* 一個唯一識別碼
* Embeddings
* 上面定義的 Metadata 

注意：「Upsert」是「update」和「insert」的合成字。在資料庫操作中，upsert 是一個原子操作：記錄存在就更新，不存在就新增。當你想確保資料庫裡是最新的資料，又不想分開做檢查再決定新增或更新時，這很好用。

```python
# reload the index from Pinecone 
index = pc.Index(index_name)

# Create a document ID prefix 
document_id = 'WB_Report'


# Define the async function correctly
def upsert_vector(identifier, embedding, metadata):
    try:
        index.upsert([
            {
                'id': identifier,
                'values': embedding,
                'metadata': metadata
            }
        ])
    except Exception as e:
        print(f"Error upserting vector with ID {identifier}: {e}")
        raise


for idx, row in tqdm(df.iterrows(), total=df.shape[0], desc='Uploading to Pinecone'):
    pageNumber = row['PageNumber']

    # Create meta-data tags to be added to Pinecone 
    metadata = {
        'pageId': f"{document_id}-{pageNumber}",
        'pageNumber': pageNumber,
        'text': row['PageText'],
        'ImagePath': row['ImagePath'],
        'GraphicIncluded': row['Visual_Input_Processed']
    }

    upsert_vector(metadata['pageId'], row['Embeddings'], metadata)
```

??? note "輸出"

    ```text
    Uploading to Pinecone: 100%|██████████| 49/49 [00:08<00:00,  5.93it/s]
    ```

到 [Pinecone](https://app.pinecone.io/) 的 Indexes 列表，你應該可以看到已 upsert 進資料庫、帶有 metadata 的向量。

### Step 5：對相關頁面做語意搜尋：
這一節我們實作語意搜尋，找出文件中最能回答使用者問題的頁面。這個做法用存在 Pinecone 向量資料庫裡的 embeddings，根據內容的語意相似度檢索頁面。這樣我們就能有效搜尋文字內容，並把它當 context 提供給 GPT-4o 回答使用者的問題。

**步驟拆解：**  

**1. 為使用者的問題產生 Embedding** 

* 用 OpenAI 的 embedding 模型，為使用者的問題產生高維向量表示。 
* 這個向量捕捉問題的語意，讓我們能對已儲存的 embeddings 做有效率的相似度搜尋。 
* 即使字面不完全一樣，embedding 也能確保搜尋 query 在語意上跟文件內容對得上。

**2. 查詢 Pinecone Index 找出相關頁面** 

* 用產生的 embedding 去查詢 Pinecone index，找出最相關的頁面。 
* Pinecone 用 `cosine` similarity，把問題的 embedding 跟向量資料庫裡儲存的 embeddings 做比較。還記得我們在 Step 1 建立 Pinecone 資料庫時，把它設成 `metric` 參數。 
* 我們指定要取回的前幾名數量，通常是在涵蓋範圍和相關性之間取平衡。例如取前 3 到 5 頁，通常就夠提供完整的回答，又不會讓模型被太多 context 淹沒。 


**3. 整理符合頁面的 Metadata 當作 Context** 

* 找出相關的 embeddings 後，我們收集它們的 metadata，包括抽出的文字和頁碼。
* 這些 metadata 對於組織提供給 GPT-4o 的 context 很重要。 
* 我們也把整理好的資訊格式化成 JSON，讓 LLM 比較容易解讀。

**4. 用 GPT-4o 模型產生答案** 

* 最後，我們把整理好的 context 傳給 GPT-4o。 
* 模型用這些 context 產生資訊豐富、連貫、跟問題相關的答案。
* 檢索到的 context 讓 LLM 能取得文件中的相關資訊，所以回答問題更準確。 

```python
import json


# Function to get response to a user's question 
def get_response_to_question(user_question, pc_index):
    # Get embedding of the question to find the relevant page with the information 
    question_embedding = get_embedding(user_question)

    # get response vector embeddings 
    response = pc_index.query(
        vector=question_embedding,
        top_k=2,
        include_values=True,
        include_metadata=True
    )

    # Collect the metadata from the matches
    context_metadata = [match['metadata'] for match in response['matches']]

    # Convert the list of metadata dictionaries to prompt a JSON string
    context_json = json.dumps(context_metadata, indent=3)

    prompt = f"""You are a helpful assistant. Use the following context and images to answer the question. In the answer, include the reference to the document, and page number you found the information on between <source></source> tags. If you don't find the information, you can say "I couldn't find the information"

    question: {user_question}
    
    <SOURCES>
    {context_json}
    </SOURCES>
    """

    # Call completions end point with the prompt 
    completion = oai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt}
        ]
    )

    return completion.choices[0].message.content
```

現在來問一個需要圖表資訊才能回答的問題，這題的相關細節在一張圓餅圖裡。

```python
question = "What percentage was allocated to social protections in Western and Central Africa?"
answer = get_response_to_question(question, index)

print(answer)
```

??? note "輸出"

    ```text
    Social protection was allocated 8% of the total lending in Western and Central Africa in fiscal 2024. <source>WB_Report-13, page 13</source>
    ```

再提高難度，問一個需要解讀表格資訊的問題。在 Step 2，我們已經用 GPT-4o vision modality 抽出這些資訊。 

```python
question = "What was the increase in access to electricity between 2000 and 2012 in Western and Central Africa?"
answer = get_response_to_question(question, index)

print(answer)
```

??? note "輸出"

    ```text
    The increase in access to electricity between 2000 and 2012 in Western and Central Africa was from 34.1% to 44.1%, which is an increase of 10 percentage points. 

    <source>WB_Report-13, page 13</source>
    ```

這個做法效果不錯。不過有些資訊嵌在圖片或圖形裡，轉成文字時會失真，例如複雜的工程圖。

用 GPT-4o Vision modality，我們可以直接把頁面圖片當 context 傳給模型。下一節會探討怎麼用圖片輸入提升模型回答的準確度。

### Step 6：處理有視覺內容的頁面（選用步驟）：
當 metadata 顯示有圖片、圖形或表格時，我們可以把圖片而不是抽出的文字，當作 context 傳給 GPT-4o。如果視覺資訊的文字描述不足以傳達 context，這個做法就很有用，像是複雜的圖形，例如工程圖或複雜的示意圖。 

**步驟拆解：** 

這一步和 Step 5 的差別在於，我們加了額外的邏輯，判斷某個 embedding 有沒有設 `Visual_Input_Processed` 旗標。有的話，就不傳文字當 context，而是用 GPT-4o vision modality 傳該頁的圖片當 context。 

注意：這個做法會增加延遲和成本，因為處理圖片輸入更吃資源也更貴。所以只有在上面 Step 5 的純文字做法達不到想要的結果時才用。

```python
import base64
import json


def get_response_to_question_with_images(user_question, pc_index):
    # Get embedding of the question to find the relevant page with the information 
    question_embedding = get_embedding(user_question)

    # Get response vector embeddings 
    response = pc_index.query(
        vector=question_embedding,
        top_k=3,
        include_values=True,
        include_metadata=True
    )

    # Collect the metadata from the matches
    context_metadata = [match['metadata'] for match in response['matches']]

    # Build the message content
    message_content = []

    # Add the initial prompt
    initial_prompt = f"""You are a helpful assistant. Use the text and images provided by the user to answer the question. You must include the reference to the page number or title of the section you the answer where you found the information. If you don't find the information, you can say "I couldn't find the information"

    question: {user_question}
    """
    
    message_content.append({"role": "system", "content": initial_prompt})
    
    context_messages = []

    # Process each metadata item to include text or images based on 'Visual_Input_Processed'
    for metadata in context_metadata:
        visual_flag = metadata.get('GraphicIncluded')
        page_number = metadata.get('pageNumber')
        page_text = metadata.get('text')
        message =""

        if visual_flag =='Y':
            # Include the image
            print(f"Adding page number {page_number} as an image to context")
            image_path = metadata.get('ImagePath', None)
            try:
                base64_image = encode_image(image_path)
                image_type = 'jpeg'
                # Prepare the messages for the API call
                context_messages.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{image_type};base64,{base64_image}"
                    },
                })
            except Exception as e:
                print(f"Error encoding image at {image_path}: {e}")
        else:
            # Include the text
            print(f"Adding page number {page_number} as text to context")
            context_messages.append({
                    "type": "text",
                    "text": f"Page {page_number} - {page_text}",
                })
        
                # Prepare the messages for the API call
        messages =  {
                "role": "user",
                "content": context_messages
        }
    
    message_content.append(messages)

    completion = oai_client.chat.completions.create(
    model="gpt-4o",
    messages=message_content
    )

    return completion.choices[0].message.content
```

我們問跟 Step 5 純文字語意搜尋一樣的問題。可以看到 GPT-4o 模型能找出含有相關資訊、可以回答問題的圖表。 

```python
question = "What percentage was allocated to social protections in Western and Central Africa?"
answer = get_response_to_question_with_images(question, index)

print(answer)
```

??? note "輸出"

    ```text
    Adding page number 13.0 as an image to context
    Adding page number 12.0 as an image to context
    Adding page number 11.0 as an image to context
    The percentage allocated to social protection in Western and Central Africa is 8% (Figure 2: Western and Central Africa; IBRD and IDA Lending by Sector).
    ```

現在問一個純文字 modality 可能回答不了的問題，例如在文件中找一張相關的圖片並描述它。 

```python
question = "Can you find the image associated with digital improvements and describe what you see in the images?"
answer = get_response_to_question_with_images(question, index)

print(answer)
```

??? note "輸出"

    ```text
    Adding page number 32.0 as an image to context
    Adding page number 10.0 as an image to context
    Adding page number 4.0 as an image to context
    ### Image Descriptions

    1. **Page 60-61 (Digital Section)**:
       - **Left Side**: A person is sitting and working on a laptop, holding a smartphone. The setting seems informal, possibly in a small office or a cafe.
       - **Text**: Discussion on scaling digital development, thought leadership, partnerships, and establishment of a Digital Vice Presidency unit for digital transformation efforts.

    2. **Page 16-17 (Eastern and Southern Africa Section)**:
       - **Right Side**: A group of people standing on a paved street, some using mobile phones. It seems to be a casual, evening setting.
       - **Text**: Information about improving access to electricity in Rwanda and efforts for education and other services in Eastern and Southern Africa.

    3. **Page 4-5 (Driving Action, Measuring Results)**:
       - **Images**: Various circular images and icons accompany text highlights such as feeding people, providing schooling, access to clean water, transport, and energy.
       - **Text**: Summary of key development results achieved by the World Bank Group in fiscal 2024.

    These images illustrate the initiatives and impacts of the World Bank's projects and activities in various sectors.
    ```

### 結論

在這份 cookbook 裡，我們為圖片、圖形和表格很多的文件，強化了 Retrieval-Augmented Generation (RAG) 系統。傳統 RAG 模型處理文字資料很在行，但常常忽略視覺元素傳達的大量資訊。整合 vision 模型並用 metadata 標記後，我們補上了這個缺口，讓 AI 能有效地解讀並運用視覺內容。

我們從建立 Pinecone vector store 開始，為向量 embeddings 的高效儲存和檢索打好基礎。用 GPT-4o vision modality 解析 PDF 並抽取視覺資訊，讓我們能把文件頁面轉成相關的文字。透過產生 embeddings 並標記有視覺內容的頁面，我們在 vector store 裡建立了穩固的 metadata 過濾機制。

把這些 embeddings 上傳到 Pinecone，讓整合進 RAG 處理流程很順暢。透過語意搜尋，我們檢索到符合使用者問題的相關頁面，確保文字和視覺資訊都被考慮到。把有視覺內容的頁面傳給 vision 模型處理，提升了回答的準確度和深度，特別是依賴圖片或表格的問題。

以世界銀行的 **A Better Bank for a Better World: Annual Report 2024** 為範例，我們示範了這些技巧如何一起處理並解讀複雜文件。這個做法不只豐富了提供給使用者的資訊，也透過更完整、更準確的回答，大幅提升使用者的滿意度和參與度。

照著這份 cookbook 的概念做，你就能建立處理並解讀複雜視覺元素文件的 RAG 系統。這個進展為視覺資料很關鍵的各種領域，帶來 AI 應用的新可能。

## 重點整理
- 純文字 RAG 會漏掉圖表和表格裡的資訊，用 vision 模型把頁面轉成文字描述，是第一層補救。
- 抽取時在 prompt 要求固定標記，之後就能靠標記自動設旗標，不用另外判斷哪些頁面有圖。
- Pinecone 的 dimension 要跟 embedding 模型一致（`text-embedding-3-large` 是 3072），metric 決定相似度怎麼算。
- Metadata 讓你在檢索後取回原文、頁碼和圖片路徑，也能依旗標決定要給模型文字還是圖片。
- Vision 又貴又慢，先用純文字檢索，真的不夠用再對有旗標的頁面改傳圖片。

## 練習
1. 把 `Step 5` 的 top-k 從目前的值改成 3 和 5，用同一個問題比較答案有沒有差別。
2. 在 Step 4 的 metadata 加一個欄位（例如頁面文字長度），upsert 後到 Pinecone 控制台確認它有出現。
3. 改寫 Step 6 的邏輯：只有檢索結果的第一名頁面有旗標時才傳圖片，其餘仍傳文字，並比較答案品質和 token 用量。
