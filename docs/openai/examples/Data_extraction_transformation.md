---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Data_extraction_transformation.ipynb
---
# 在 ELT 流程中用 GPT-4o 取代 OCR 做資料擷取與轉換

> 原文：[examples/Data_extraction_transformation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Data_extraction_transformation.ipynb)



## 這篇在做什麼
示範用 GPT-4o 的視覺能力，把多語言的 PDF 發票擷取成 JSON，再依指定 schema 轉換，最後載入關聯式資料庫查詢。整個流程模擬一個簡單的 ELT workflow。

## 學完你會
- 把 PDF 每頁轉成 base64 圖片，用 GPT-4o 擷取成 JSON。
- 用 prompt 搭配目標 schema，把不一致的原始 JSON 轉成統一格式（含翻譯成英文）。
- 把轉換後的資料拆成 Hotels、Invoices、Charges、Taxes 四張表載入資料庫，並用 SQL 查詢。

## 開跑前
- 需要 OpenAI API key，並有 GPT-4o 的使用權限（會產生 API 費用）。



很多企業資料是非結構化的，鎖在難以使用的格式裡，例如 PDF、PPT、PNG，這些格式沒有針對 LLM 或資料庫最佳化。結果這類資料雖然很有價值，卻常常沒被充分用在分析和產品開發上。傳統上從非結構化或不理想的格式擷取資訊的做法是 OCR，但 OCR 對複雜版面吃力，多語言支援也有限。此外，手動對資料做轉換既麻煩又耗時。 

GPT-4o 的多模態能力帶來了擷取和轉換資料的新方式，因為 GPT-4o 能適應不同類型的文件，也能用 reasoning 來詮釋文件內容。下面是在擷取和轉換流程中，選 GPT-4o 而不是傳統方法的一些理由。 


| **擷取**                                               | **轉換**                                              |
|---------------------------------------------------------------|------------------------------------------------------------------|
| **Adaptable**：更能處理複雜的文件版面，減少錯誤 | **Schema Adaptability**：輕鬆把資料轉成符合特定 schema，便於寫入資料庫 |
| **Multilingual Support**：無縫處理多種語言的文件 | **Dynamic Data Mapping**：適應不同的資料結構和格式，提供彈性的轉換規則 |
| **Contextual Understanding**：擷取有意義的關係和 context，不只是文字 | **Enhanced Insight Generation**：運用 reasoning 做出更有洞察的轉換，用衍生指標、metadata 和關係豐富資料集 |
| **Multimodality**：處理各種文件元素，包括圖片和表格 |  |


這份 cookbook 分三個部分：
1. 怎麼從多語言 PDF 擷取資料 
2. 怎麼依 schema 轉換資料，以便載入資料庫
3. 怎麼把轉換後的資料載入資料庫，做後續分析

我們模擬一個簡單的 ELT workflow：先用 GPT-4o 把 PDF 的資料擷取成 JSON，以非結構化的格式存在 data lake 之類的地方，再用 GPT-4o 轉換成符合 schema 的格式，最後寫入關聯式資料庫供查詢。如果想降低這個流程的成本，這些全部都可以用 BatchAPI 做。 

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/elt_workflow.png)

我們用的資料是 2019 年德國的一組公開飯店發票，來自 [Jens Walter 的 GitHub](https://github.com/JensWalter/my-receipts/tree/master/2019/de/hotel)（謝謝 Jens！）。飯店發票通常包含類似的資訊（訂房細節、費用、稅金等），但你會發現這些發票呈現明細的方式各不相同，而且是多語言，同時有德文和英文。幸好 GPT-4o 不需要我們指定格式，就能適應各種不同的文件樣式，也能無縫處理多種語言，連同一份文件裡混用也行。 
其中一張發票長這樣： 

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/sample_hotel_invoice.png)

## 第 1 部分：用 GPT-4o 的視覺能力從 PDF 擷取資料
GPT-4o 不能直接處理 PDF，所以擷取資料前，要先把每一頁轉成圖片，再把圖片編碼成 base64。 

```python
from openai import OpenAI
import fitz  # PyMuPDF
import io
import os
from PIL import Image
import base64
import json

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


@staticmethod
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def pdf_to_base64_images(pdf_path):
    #Handles PDFs with multiple pages
    pdf_document = fitz.open(pdf_path)
    base64_images = []
    temp_image_paths = []

    total_pages = len(pdf_document)

    for page_num in range(total_pages):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        temp_image_path = f"temp_page_{page_num}.png"
        img.save(temp_image_path, format="PNG")
        temp_image_paths.append(temp_image_path)
        base64_image = encode_image(temp_image_path)
        base64_images.append(base64_image)

    for temp_image_path in temp_image_paths:
        os.remove(temp_image_path)

    return base64_images
```

接著把每張 base64 編碼的圖片放進 GPT-4o 的 LLM 呼叫，指定高細節等級，並以 JSON 作為回應格式。這一步不用強制 schema，只要不管型別，把資料全部擷取出來就好。

```python
def extract_invoice_data(base64_image):
    system_prompt = f"""
    You are an OCR-like data extraction tool that extracts hotel invoice data from PDFs.
   
    1. Please extract the data in this hotel invoice, grouping data according to theme/sub groups, and then output into JSON.

    2. Please keep the keys and values of the JSON in the original language. 

    3. The type of data you might encounter in the invoice includes but is not limited to: hotel information, guest information, invoice information,
    room charges, taxes, and total charges etc. 

    4. If the page contains no charge data, please output an empty JSON object and don't make up any data.

    5. If there are blank data fields in the invoice, please include them as "null" values in the JSON object.
    
    6. If there are tables in the invoice, capture all of the rows and columns in the JSON object. 
    Even if a column is blank, include it as a key in the JSON object with a null value.
    
    7. If a row is blank denote missing fields with "null" values. 
    
    8. Don't interpolate or make up data.

    9. Please maintain the table structure of the charges, i.e. capture all of the rows and columns in the JSON object.

    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "extract the data in this hotel invoice and output into JSON "},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "high"}}
                ]
            }
        ],
        temperature=0.0,
    )
    return response.choices[0].message.content
```

因為發票資料可能橫跨 PDF 的多頁，所以我們對發票的每一頁各產生一個 JSON 物件，再把它們接在一起。最後的發票擷取結果是單一個 JSON 檔案。

```python
def extract_from_multiple_pages(base64_images, original_filename, output_directory):
    entire_invoice = []

    for base64_image in base64_images:
        invoice_json = extract_invoice_data(base64_image)
        invoice_data = json.loads(invoice_json)
        entire_invoice.append(invoice_data)

    # Ensure the output directory exists
    os.makedirs(output_directory, exist_ok=True)

    # Construct the output file path
    output_filename = os.path.join(output_directory, original_filename.replace('.pdf', '_extracted.json'))
    
    # Save the entire_invoice list as a JSON file
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(entire_invoice, f, ensure_ascii=False, indent=4)
    return output_filename


def main_extract(read_path, write_path):
    for filename in os.listdir(read_path):
        file_path = os.path.join(read_path, filename)
        if os.path.isfile(file_path):
            base64_images = pdf_to_base64_images(file_path)
            extract_from_multiple_pages(base64_images, filename, write_path)


hotel_invoice_path = "./data/hotel_invoices"
extracted_invoice_json_path = os.path.join(hotel_invoice_path, "extracted_invoice_json")
read_path = os.path.join(hotel_invoice_path, "receipts_2019_de_hotel")

main_extract(read_path, extracted_invoice_json_path)
```

原始發票擷取結果每頁含一個 JSON 物件，以陣列形式存在 `data/hotel_invoices/extracted_invoice_json/`。不同發票和不同次擷取之間，key、語言和值的型別可能不同。[JSON 格式指南](https://github.com/openai/openai-cookbook/blob/main/examples/data/hotel_invoices/README.md)說明了原始擷取結果和資料庫寫入用的標準化物件有何不同。

下一個 cell 從擷取與轉換步驟使用的同一個目錄載入一張發票。


```python
sample_invoice_path = os.path.join(
    extracted_invoice_json_path, "premierinn_GABCI19014325_extracted.json"
)
with open(sample_invoice_path, "r", encoding="utf-8") as f:
    sample_invoice = json.load(f)

print(json.dumps(sample_invoice, ensure_ascii=False, indent=4))
```

??? note "輸出"

    ```text
    [
        {
            "Hotel Information": {
                "Name": "Hamburg City (Zentrum)",
                "Address": "Willy-Brandt-Straße 21, 20457 Hamburg, Deutschland",
                "Phone": "+49 (0) 40 3039 379 0"
            },
            "Guest Information": {
                "Name": "APIMEISTER CONSULTING GmbH",
                "Guest": "Herr Jens Walter",
                "Address": "Friedrichstr. 123, 10117 Berlin"
            },
            "Invoice Information": {
                "Ankunft": "23.09.19",
                "Referenznummer": "GABC015452127",
                "Nächte": 4,
                "Abreise": "27.09.19",
                "Zimmer": 626,
                "Kundereferenz": null,
                "Rechnungsnummer": "GABC19014325",
                "Rechnungsdatum": "23.09.19",
                "Buchungsnummer": "GABR15867"
            },
            "Charges": [
                {
                    "Datum": "23.09.19",
                    "Uhrzeit": "16:36",
                    "Beschreibung": "Übernachtung",
                    "MwSt.%": 7.0,
                    "Betrag": 77.0,
                    "Zahlung": null
                },
                {
                    "Datum": "24.09.19",
                    "Uhrzeit": null,
                    "Beschreibung": "Übernachtung",
                    "MwSt.%": 7.0,
                    "Betrag": 135.0,
                    "Zahlung": null
                },
    ... (省略 72 行)
    ```

## 第 2 部分：依 schema 轉換資料 

你已經從 PDF 擷取了資料，而且大概已經把非結構化的擷取結果以 JSON 物件存進 data lake。ELT workflow 的下一步，是用 GPT-4o 依我們想要的 schema 轉換這些擷取結果，這樣產生的資料表才能寫進資料庫。我們決定了下面這個 schema，大致涵蓋各種發票上會看到的大部分資訊。這個 schema 用來把每個原始 JSON 擷取結果，處理成我們想要的有 schema 的 JSON，也可以指定特定格式，例如 "date": "YYYY-MM-DD"。這一步也會把資料翻譯成英文。 


```python
[
    {
        "hotel_information": {
            "name": "string",
            "address": {
                "street": "string",
                "city": "string",
                "country": "string",
                "postal_code": "string"
            },
            "contact": {
                "phone": "string",
                "fax": "string",
                "email": "string",
                "website": "string"
            }
        },
        "guest_information": {
            "company": "string",
            "address": "string",
            "guest_name": "string"
        },
        "invoice_information": {
            "invoice_number": "string",
            "reservation_number": "string",
            "date": "YYYY-MM-DD",  
            "room_number": "string",
            "check_in_date": "YYYY-MM-DD",  
            "check_out_date": "YYYY-MM-DD"  
        },
        "charges": [
            {
                "date": "YYYY-MM-DD", 
                "description": "string",
                "charge": "number",
                "credit": "number"
            }
        ],
        "totals_summary": {
            "currency": "string",
            "total_net": "number",
            "total_tax": "number",
            "total_gross": "number",
            "total_charge": "number",
            "total_credit": "number",
            "balance_due": "number"
        },
        "taxes": [
            {
                "tax_type": "string",
                "tax_rate": "string",
                "net_amount": "number",
                "tax_amount": "number",
                "gross_amount": "number"
            }
        ]
    }
]
```

```python
def transform_invoice_data(json_raw, json_schema):
    system_prompt = f"""
    You are a data transformation tool that takes in JSON data and a reference JSON schema, and outputs JSON data according to the schema.
    Not all of the data in the input JSON will fit the schema, so you may need to omit some data or add null values to the output JSON.
    Translate all data into English if not already in English.
    Ensure values are formatted as specified in the schema (e.g. dates as YYYY-MM-DD).
    Here is the schema:
    {json_schema}

    """
    
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={ "type": "json_object" },
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Transform the following raw JSON data according to the provided schema. Ensure all data is in English and formatted as specified by values in the schema. Here is the raw JSON: {json_raw}"}
                ]
            }
        ],
        temperature=0.0,
    )
    return json.loads(response.choices[0].message.content)



def main_transform(extracted_invoice_json_path, json_schema_path, save_path):
    # Load the JSON schema
    with open(json_schema_path, 'r', encoding='utf-8') as f:
        json_schema = json.load(f)

    # Ensure the save directory exists
    os.makedirs(save_path, exist_ok=True)

    # Process each JSON file in the extracted invoices directory
    for filename in os.listdir(extracted_invoice_json_path):
        if filename.endswith(".json"):
            file_path = os.path.join(extracted_invoice_json_path, filename)

            # Load the extracted JSON
            with open(file_path, 'r', encoding='utf-8') as f:
                json_raw = json.load(f)

            # Transform the JSON data
            transformed_json = transform_invoice_data(json_raw, json_schema)

            # Save the transformed JSON to the save directory
            transformed_filename = f"transformed_{filename}"
            transformed_file_path = os.path.join(save_path, transformed_filename)
            with open(transformed_file_path, 'w', encoding='utf-8') as f:
                json.dump(transformed_json, f, ensure_ascii=False, indent=2)

   
json_schema_path = os.path.join(hotel_invoice_path, "invoice_schema.json")
save_path = os.path.join(hotel_invoice_path, "transformed_invoice_json")

main_transform(extracted_invoice_json_path, json_schema_path, save_path)
```

## 第 3 部分：把轉換後的資料載入資料庫 

資料都有 schema 之後，就能把它切成多張表，載入關聯式資料庫。具體來說，我們會建四張表：Hotels、Invoices、Charges 和 Taxes。所有發票都屬於同一位住客，所以不建 guest 表。 

```python
import os
import json
import sqlite3

def ingest_transformed_jsons(json_folder_path, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create necessary tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Hotels (
        hotel_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        street TEXT,
        city TEXT,
        country TEXT,
        postal_code TEXT,
        phone TEXT,
        fax TEXT,
        email TEXT,
        website TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Invoices (
        invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
        hotel_id INTEGER,
        invoice_number TEXT,
        reservation_number TEXT,
        date TEXT,
        room_number TEXT,
        check_in_date TEXT,
        check_out_date TEXT,
        currency TEXT,
        total_net REAL,
        total_tax REAL,
        total_gross REAL,
        total_charge REAL,
        total_credit REAL,
        balance_due REAL,
        guest_company TEXT,
        guest_address TEXT,
        guest_name TEXT,
        FOREIGN KEY(hotel_id) REFERENCES Hotels(hotel_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Charges (
        charge_id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        date TEXT,
        description TEXT,
        charge REAL,
        credit REAL,
        FOREIGN KEY(invoice_id) REFERENCES Invoices(invoice_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Taxes (
        tax_id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        tax_type TEXT,
        tax_rate TEXT,
        net_amount REAL,
        tax_amount REAL,
        gross_amount REAL,
        FOREIGN KEY(invoice_id) REFERENCES Invoices(invoice_id)
    )
    ''')

    # Loop over all JSON files in the specified folder
    for filename in os.listdir(json_folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(json_folder_path, filename)

            # Load the JSON data
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Insert Hotel Information
            cursor.execute('''
            INSERT INTO Hotels (name, street, city, country, postal_code, phone, fax, email, website) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data["hotel_information"]["name"],
                data["hotel_information"]["address"]["street"],
                data["hotel_information"]["address"]["city"],
                data["hotel_information"]["address"]["country"],
                data["hotel_information"]["address"]["postal_code"],
                data["hotel_information"]["contact"]["phone"],
                data["hotel_information"]["contact"]["fax"],
                data["hotel_information"]["contact"]["email"],
                data["hotel_information"]["contact"]["website"]
            ))
            hotel_id = cursor.lastrowid

            # Insert Invoice Information
            cursor.execute('''
            INSERT INTO Invoices (hotel_id, invoice_number, reservation_number, date, room_number, check_in_date, check_out_date, currency, total_net, total_tax, total_gross, total_charge, total_credit, balance_due, guest_company, guest_address, guest_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                hotel_id,
                data["invoice_information"]["invoice_number"],
                data["invoice_information"]["reservation_number"],
                data["invoice_information"]["date"],
                data["invoice_information"]["room_number"],
                data["invoice_information"]["check_in_date"],
                data["invoice_information"]["check_out_date"],
                data["totals_summary"]["currency"],
                data["totals_summary"]["total_net"],
                data["totals_summary"]["total_tax"],
                data["totals_summary"]["total_gross"],
                data["totals_summary"]["total_charge"],
                data["totals_summary"]["total_credit"],
                data["totals_summary"]["balance_due"],
                data["guest_information"]["company"],
                data["guest_information"]["address"],
                data["guest_information"]["guest_name"]
            ))
            invoice_id = cursor.lastrowid

            # Insert Charges
            for charge in data["charges"]:
                cursor.execute('''
                INSERT INTO Charges (invoice_id, date, description, charge, credit) 
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    invoice_id,
                    charge["date"],
                    charge["description"],
                    charge["charge"],
                    charge["credit"]
                ))

            # Insert Taxes
            for tax in data["taxes"]:
                cursor.execute('''
                INSERT INTO Taxes (invoice_id, tax_type, tax_rate, net_amount, tax_amount, gross_amount) 
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    invoice_id,
                    tax["tax_type"],
                    tax["tax_rate"],
                    tax["net_amount"],
                    tax["tax_amount"],
                    tax["gross_amount"]
                ))

    conn.commit()
    conn.close()
```

現在跑一個範例 SQL 查詢，找出最貴的飯店住宿和飯店名稱，確認資料有正確寫入！  
這一步甚至可以用 function calling 自動產生 SQL 查詢，做法請看我們的 [model 產生參數的 function calling cookbook](https://cookbook.openai.com/examples/how_to_call_functions_with_chat_models#how-to-call-functions-with-model-generated-arguments)。

```python

def execute_query(db_path, query, params=()):
    """
    Execute a SQL query and return the results.

    Parameters:
    db_path (str): Path to the SQLite database file.
    query (str): SQL query to be executed.
    params (tuple): Parameters to be passed to the query (default is an empty tuple).

    Returns:
    list: List of rows returned by the query.
    """
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Execute the query with parameters
        cursor.execute(query, params)
        results = cursor.fetchall()

        # Commit if it's an INSERT/UPDATE/DELETE query
        if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
            conn.commit()

        return results
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
        return []
    finally:
        # Close the connection
        if conn:
            conn.close()


# Example usage
transformed_invoices_path = "./data/hotel_invoices/transformed_invoice_json"
db_path = "./data/hotel_invoices/hotel_DB.db"
ingest_transformed_jsons(transformed_invoices_path, db_path)

query = '''
    SELECT 
        h.name AS hotel_name,
        i.total_gross AS max_spent
    FROM 
        Invoices i
    JOIN 
        Hotels h ON i.hotel_id = h.hotel_id
    ORDER BY 
        i.total_gross DESC
    LIMIT 1;
    '''

results = execute_query(db_path, query)
for row in results:
    print(row)
```

??? note "輸出"

    ```text
    ('Citadines Michel Hamburg', 903.63)
    ```

總結一下，這份 cookbook 示範了怎麼用 GPT-4o 擷取並轉換原本無法用在資料分析的資料。如果這些流程不需要即時完成，可以用 OpenAI 的 BatchAPI 非同步執行，成本低很多！ 

## 重點整理
- 傳統 OCR 對複雜版面和多語言吃力，GPT-4o 的多模態和 reasoning 能適應不同文件樣式。
- ELT 的順序是先擷取成 JSON 存起來，之後再轉換和載入，擷取階段不強制 schema，轉換階段才套 schema。
- GPT-4o 不能直接吃 PDF，要先把每頁轉成圖片再用 base64 傳入。
- 轉換階段可以順便做格式正規化（如日期）和翻譯。
- 不需要即時的話，用 BatchAPI 可以大幅降低成本。

## 練習
1. 把擷取呼叫的 detail 等級從高改成低，比較擷取結果的差異。
2. 在轉換用的 schema 裡多加一個欄位（例如住客人數），重跑轉換，看有沒有擷取到。
3. 多寫一個 SQL 查詢，例如算每家飯店的稅金總額，驗證載入的 Taxes 表。
