---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_snowflake_middleware.ipynb
---
# GPT Actions 範例庫：Snowflake Middleware

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_snowflake_middleware.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_snowflake_middleware.ipynb)



## 這篇在做什麼

教你做一個 GPT Action，讓 ChatGPT 透過一層 middleware（這裡用 Azure Function）去查 Snowflake 資料倉儲，並把查詢結果包成 CSV 檔回傳給 ChatGPT 的 Data Analysis 環境做分析。因為 Data Analysis 只吃檔案，所以中間這層要負責把 SQL 結果轉成檔案。

## 學完你會

- 在 Azure Entra ID 建 OAuth App Registration，並在 Snowflake 建 External OAuth security integration，讓使用者身分對得起來。
- 寫一個 Azure Function：用 token 連 Snowflake、執行 SQL、存成 CSV、上傳 Blob Storage、回傳 `openaiFileResponse`。
- 設定 Custom GPT 的 Instructions 跟 OpenAPI schema，讓 GPT 能呼叫這個 action 並分析回傳的檔案。

## 開跑前

- 一個 Snowflake 資料倉儲，而且登入的使用者對目標資料庫、schema、table 有對應 role 的權限。
- Azure 帳號，能建立 Function App 跟 Entra App Registration。
- Azure Blob Storage 的 connection string。

## 簡介


這頁是給開發者的教學，說明怎麼為特定應用程式做一個 GPT Action。開始前建議先看過下面這些：

* [GPT Actions 簡介](https://platform.openai.com/docs/actions)
* [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
* [從頭做一個 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)


這份指南說明怎麼把 ChatGPT 接上 Snowflake 資料倉儲，讓 SQL 查詢結果回到 ChatGPT，交給 [Data Analysis](https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt) 使用。這個 GPT 需要一個 action 去呼叫 middleware（例如 Azure Function），由 middleware 把 Snowflake 的回應整理成 Python notebook 環境可以用的格式。資料必須[以檔案形式回傳](https://platform.openai.com/docs/actions/sending-files/returning-files)，所以 middleware 要把 SQL 結果轉成 CSV/Excel 檔，大小不能超過 10MB。

這份文件只講 Middleware function 這個 GPT action。middleware function 本身怎麼建，請看 [GPT Actions library (Middleware) - Azure Functions](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function)。你也可以把這個 Snowflake middleware action 跟另一個直連 Snowflake 的 action 搭配，做出能先組 SQL、測試、再正式執行的 GPT。

### 價值與商業情境範例


已經在用 Snowflake 的客戶，可以照這份指南從資料倉儲撈資料，載入 Data Analysis 的 Python 環境做進一步分析，例如資料視覺化、找規律或異常、找出需要清理的資料缺口。這個 GPT 適合用來對較小的資料集做決策，或是先用 AI 探索資料子集、產生假設，再回到 BI 工具看完整資料集，省時間也省錢，還可能發現以前沒看到的規律。

## 應用程式資訊

### 相關連結


開始前先看看 Snowflake 跟 Azure 的這些連結：

**Snowflake Action**

* 官網：[https://app.snowflake.com/](https://app.snowflake.com/)
* Python Connector 文件：[https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-connect)

**Azure Function**

* 官網：[https://learn.microsoft.com/en-us/azure/azure-functions/](https://learn.microsoft.com/en-us/azure/azure-functions/)
* API 文件：[https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference/](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference/)


### 前置需求


開始前先在你的環境完成下面這些：

* 準備好一個 Snowflake 資料倉儲
* 確認透過 ChatGPT 登入 Snowflake 的使用者，有對應 role，可以存取需要的 database、schema 跟 table

另外，在 Azure 建 Function App 之前，你得先處理使用者驗證。要在 Azure Entra ID 建一個 OAuth App Registration，並連到 Snowflake 的 External OAuth security integration。External OAuth 讓外部系統發 access token，Snowflake 用這個 token 判斷存取權限，這裡的外部 token 提供者就是 Azure Entra ID。因為 ChatGPT 連的是 Azure 而不是 Snowflake，GPT 使用者的 OAuth token 是由 Azure 依 Entra ID 裡的使用者發出的，所以你需要把 Snowflake 使用者對應到 Azure 上的使用者。 

Azure 跟 Snowflake 兩邊要做的步驟都寫在下面。

## 在 Azure Entra ID 設定 OAuth resource


我們要建一個新的 App Registration，設定會用到的 Snowflake scope，並取得 Snowflake 跟 ChatGPT 兩邊都需要的 OAuth 設定參數。這一節全部在 Azure 做，下一節在 Snowflake 設定時，才有資訊可以連到這個 App Registration。

1. 到 [Microsoft Azure Portal](https://portal.azure.com/) 登入。
2. 進入 Azure Entra ID（以前叫 Active Directory）。
3. 在 **Manage** 底下點 **App Registrations**。
4. 點 **New Registration**。
5. **Name** 填 `Snowflake GPT OAuth Client` 或類似的名字。
6. 確認 **Supported account types** 是 **Single Tenant**。
7. Redirect URI 先不管，等設定 GPT 時再回來填。
8. 點 **Register**。
9. 記下 **Essentials** 裡的 **Directory (tenant) ID**（`TENANT_ID`），用它組出 `AZURE_AD_ISSUER` 跟 `AZURE_AD_JWS_KEY_ENDPOINT.`
    * `AZURE_AD_ISSUER` 是 `https://sts.windows.net/TENANT_ID/`
    *  `AZURE_AD_JWS_KEY_ENDPOINT` 是 `https://login.microsoftonline.com/TENANT_ID/discovery/v2.0/keys`
10. 在 **Overview** 頁面點 **Endpoints**。
11. 右側的 **OAuth 2.0 authorization endpoint (v2)** 記為 `AZURE_AD_OAUTH_AUTHORIZATION_ENDPOINT`，**OAuth 2.0 token endpoint (v2)** 記為 `AZURE_AD_OAUTH_TOKEN_ENDPOINT`。
    * endpoint 長得像 `https://login.microsoftonline.com/90288a9b-97df-4c6d-b025-95713f21cef9/oauth2/v2.0/authorization` 跟 `https://login.microsoftonline.com/90288a9b-97df-4c6d-b025-95713f21cef9/oauth2/v2.0/token`。
12. 在 **Manage** 底下點 **Expose an API **。
13. 點 **Application ID URI** 旁邊的 **Set** 連結，設定 `Application ID URI`。
    * `Application ID URI` 在你組織的 directory 裡必須是唯一的，例如 `https://your.company.com/4d2a8c2b-a5f4-4b86-93ca-294185f45f2e`。後面的設定步驟會把這個值叫做 `<SNOWFLAKE_APPLICATION_ID_URI>`。
14. 如果是程式用戶端代表使用者的 OAuth 流程，要把 Snowflake role 加成 OAuth scope：點 **Add a scope**，新增一個代表該 Snowflake role 的 scope。
    * scope 名稱用 Snowflake role 名稱加上 `session:scope:` 前綴。例如 Snowflake 的 Analyst role，就填 `session:scope:analyst`。
    * 選擇誰可以同意（consent）。
    * 填 scope 的 **display name**（例如 Account Admin）。
    * 填 scope 的 **description**（例如 Can administer the Snowflake account）。
    * 點 **Add Scope**。
    * 把這個 scope 存成 `AZURE_AD_SCOPE`，內容是 `Application ID URI` 跟 `Scope name` 串在一起。
15. 在 **Overview** 區塊，複製 **Application (client) ID** 欄位的 `ClientID`，後面叫它 `OAUTH_CLIENT_ID`。
16. 點 **Certificates & secrets**，再點 **New client secret**。
17. 填 secret 的描述。
18. 選 **730 days (24 months)**。測試時建議選不會很快過期的 secret。
19. 點 **Add**，複製 secret，後面叫它 `OAUTH_CLIENT_SECRET`。
20. 如果程式用戶端要代表使用者取得 Access Token，要這樣設定 Delegated permissions：
    * 點 **API Permissions**。
    * 點 **Add Permission**。
    * 點 **My APIs**。
    * 點你在 [Configure the OAuth resource in Azure AD](https://docs.snowflake.com/en/user-guide/oauth-azure#configure-the-oauth-resource-in-azure-ad) 建立的 **Snowflake OAuth Resource**。
    * 點 **Delegated Permissions** 方塊。
    * 勾選你想授權給這個用戶端、對應到應用程式中所定義 scope 的權限。
    * 點 **Add Permissions**。
    * 點 **Grant Admin Consent** 按鈕授權給用戶端。注意這是測試用的設定方式，正式環境不建議這樣授權。
    * 點 **Yes**。


## 在 Snowflake 建 security integration

Azure Entra ID 的 App Registration 做好後，下一步是用 External OAuth Security Integration 把它連到 Snowflake。security integration 的 `external_oauth_audience_list` 參數必須跟你在 Azure Entra ID 設的 **Application ID URI** 一致。 

**Issuer** 跟 **JWS Keys endpoint** 也是用前面步驟收集到的值。**User Mapping Attribute** 可以設成 `EMAIL_ADDRESS` 或 `LOGIN_NAME`，這就是使用者的 Microsoft 登入身分對應到 Snowflake 使用者的方式，確保發給 ChatGPT 的 access token 會遵守 Snowflake 裡的權限。 

```python
CREATE OR REPLACE SECURITY INTEGRATION AZURE_OAUTH_INTEGRATION
  TYPE = EXTERNAL_OAUTH
  ENABLED = TRUE
  EXTERNAL_OAUTH_TYPE = 'AZURE'
  EXTERNAL_OAUTH_ISSUER = '<AZURE_AD_ISSUER>'
  EXTERNAL_OAUTH_JWS_KEYS_URL = '<AZURE_AD_JWS_KEY_ENDPOINT>'
  EXTERNAL_OAUTH_AUDIENCE_LIST = ('<SNOWFLAKE_APPLICATION_ID_URI>')
  EXTERNAL_OAUTH_TOKEN_USER_MAPPING_CLAIM = 'upn'
  EXTERNAL_OAUTH_SNOWFLAKE_USER_MAPPING_ATTRIBUTE = 'EMAIL_ADDRESS';
```

### Middleware 資訊：

請確認 Azure 環境符合下面條件：

* 有 Azure Portal 或 VS Code，且有權限建立 Azure Function App 跟 Azure Entra App Registration
* 本指南有[一個詳細的段落](#azure-function-app)，講怎麼部署跟設計這個 function，它負責把 Snowflake 的回應包起來，以 CSV 回傳給 ChatGPT。Azure Function App 能讓你的 GPT 吃進較大的資料集，因為 ChatGPT 從檔案回應能讀的資料量比 application/json payload 多。而且只有回應格式是 CSV 檔，資料才能給 Data Analysis（也就是 Code Interpreter）用。

### Azure Function App

GPT 建好、Azure/Snowflake 的驗證也處理完之後，就可以建 Azure Function App 本身了。它負責執行 SQL 查詢、處理回應格式，讓 GPT 能下載 CSV 給 Data Analysis 用。

部署 Azure Function App 的細節請看這份 [Azure Cookbook Guide](https://cookbook.openai.com/examples/azure/functions)。下面是要加到 function 裡的範例程式碼。

這份程式碼只是參考方向，應該可以直接跑，但你還是要依自己 GPT 跟 IT 環境的需求調整。

### 應用程式程式碼

Azure Function App 要處理下面這些流程：

* 從 HTTP request 取出 token，用它連 Snowflake
* 執行 SQL 查詢，把結果寫成 CSV
* 暫時把 CSV 存到 Blob Storage*
* 產生 pre-signed URL，安全地存取這個 CSV*
* 回應 openaiFileResponse

*如果你用 [file stream](https://platform.openai.com/docs/actions/getting-started/inline-option) 而不是 [url](https://platform.openai.com/docs/actions/getting-started/url-option) 的方式把檔案回傳給 GPT，這幾步可能就不需要。後面會再說明。

確認需要的套件都已安裝並 import 到你的腳本裡。除了 Python 標準函式庫，這份範例腳本還用了下面這些：

```python
import azure.functions as func
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
import snowflake.connector
import jwt    # pyjwt for token decoding
```

#### 連接 Snowflake

要連 Snowflake，你得從 Authorization header 取出 Azure Entra ID 發的 access token，連線時用這個 token。 
這個範例裡，Snowflake 的使用者名稱就是 email，所以從 HTTP access token 取出的 Entra ID 使用者，可以直接對應到連線需要的 Snowflake user ID。如果你的組織不是這樣，可以在 Python 程式裡自己把 email 對應到 Snowflake user ID。

我的應用程式只接一個 Snowflake Account（例如 ab12345.eastus2.azure）跟一個 Warehouse。如果你要連多個 account 或 warehouse，可以考慮把這些參數放進 GPT action 的參數，再從 HTTP request 取出來。

```python
# Extract the token from the Authorization header
auth_header = req.headers.get('Authorization')
token_type, token = auth_header.split()

try:
    # Extract email address from token to use for Snowflake user mapping
    # If Snowflake usernames are not emails, then identify the username accordingly
    decoded_token = jwt.decode(token, options={"verify_signature": False})
    email = decoded_token.get('upn') 
    
    conn = snowflake.connector.connect(
        user=email, # Snowflake username, i.e., user's email in my example
        account=SNOWFLAKE_ACCOUNT, # Snowflake account, i.e., ab12345.eastus2.azure
        authenticator="oauth",
        token=token,
        warehouse=SNOWFLAKE_WAREHOUSE # Replace with Snowflake warehouse
    )
    logging.info("Successfully connected to Snowflake.")
except Exception as e:
    logging.error(f"Failed to connect to Snowflake: {e}")
```

#### 執行查詢並存成 CSV

連上 Snowflake 之後，要執行查詢並把結果存成 CSV。Snowflake 的 role 應該能擋掉有害的查詢，不過你還是可以像處理其他程式化 SQL 執行一樣，在應用程式裡對查詢做清理（下面沒有包含這部分）。 

```python
# Extract SQL query from request parameters or body
sql_query = req.params.get('sql_query')

try:
    # Use the specified warehouse
    cursor = conn.cursor()

    # Execute the query
    cursor.execute(sql_query)
    results = cursor.fetchall()
    column_names = [desc[0] for desc in cursor.description]
    logger.info(f"Query executed successfully: {sql_query}")

    # Convert results to CSV
    csv_file_path = write_results_to_csv(results, column_names)
except Exception as e:
    logger.error(f"Error executing query or processing data: {e}")


def write_results_to_csv(results, column_names):
    try:
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', newline='')
        csv_writer = csv.writer(temp_file)
        csv_writer.writerow(column_names)  # Write the column headers
        csv_writer.writerows(results)      # Write the data rows
        temp_file.close()  # Close the file to flush the contents
        return temp_file.name  # Return file path
    except Exception as e:
        logger.error(f"Error writing results to CSV: {e}")
```

#### 把檔案存到 Blob Storage

把檔案還給 ChatGPT 處理有兩種方式。一種是在 openaiFileResponse 清單裡，直接 [stream](https://platform.openai.com/docs/actions/getting-started/inline-option) base64 編碼的資料，附上 mimeType 跟檔名；另一種是回傳 [URL 清單](https://platform.openai.com/docs/actions/getting-started/url-option)。這個方案用後者。

做法是把 CSV 上傳到 Azure Blob Storage，回傳 pre-signed URL，讓 ChatGPT 安全地存取檔案。要注意，ChatGPT 要能下載 URL，URL 必須帶 content_type 跟 content_disposition，就像下面的範例。想檢查某個 URL 有沒有這些 header，可以在任何終端機跑 ``curl -I <url>``。 

你需要 Azure storage 的 connection string，取得方式看[這裡](https://learn.microsoft.com/en-us/azure/storage/common/storage-configure-connection-string)。 

```python
def upload_csv_to_azure(file_path, container_name, blob_name, connect_str):
    try:
        # Create the BlobServiceClient object which will be used to create a container client
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        
        # Create a blob client using the local file name as the name for the blob
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)

        # Upload the file with specified content settings
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(
                content_type='text/csv',
                content_disposition=f'attachment; filename="{blob_name}"'
            ))
        logger.info(f"Successfully uploaded {file_path} to {container_name}/{blob_name}")

        # Generate a SAS token for the blob
        sas_token = generate_blob_sas(
            account_name=blob_service_client.account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=blob_service_client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=1)  # Token valid for 1 hour
        )

        # Generate a presigned URL using the SAS token
        url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        logger.info(f"Generated presigned URL: {url}")

        return url
    except Exception as e:
        logger.error(f"Error uploading file to Azure Blob Storage: {e}")
        raise
```

#### 格式化 openaiFileResponse

最後要把回應整理成正確格式，讓 ChatGPT 把它當成一個或多個檔案處理。openaiFileResponse 是一個 list，最多可以放 10 個 URL（如果用 [inline option](https://platform.openai.com/docs/actions/getting-started/inline-option)，則是 base64 編碼）。

```python
# Format the response so ChatGPT treats it as a file
response = {
    'openaiFileResponse': [csv_url]
}
cursor.close()
conn.close()
return func.HttpResponse(
    json.dumps(response), 
    status_code=200
)
```


這個應用有很多環節，所以 Azure Function App 要好好測試。ChatGPT 不太適合拿來除錯，因為 request 跟 response 常常看不清楚。建議先用 cURL 或 Postman 在比較可控的環境發 HTTP request 測試，比較容易 debug 跟定位問題。確認這些工具拿到的回應都符合預期，再開始建 GPT。

## ChatGPT 步驟

### Custom GPT Instructions

建好 Custom GPT 之後，可以參考下面的文字填進 Instructions 面板。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

##### Instructions 範例

ChatGPT 必須懂你的 table schema，才能組出正確的 SQL。做法有好幾種，這份 Instructions 是最直接的一種。我們還在準備其他版本的 Snowflake GPT 指令，讓 GPT 能處理多個 table、schema、database，甚至能動態學習常變動的 schema。

下面是針對單一 schema、單一 table 的基本 instructions。這個 GPT 針對單一用途最佳化（分析 2013 年 1 月從紐約出發的航班資料），這樣最簡單的指令就能讓 GPT 表現最穩。

You are an expert at writing SQL queries to fetch data from Snowflake. You help users convert their prompts into SQL queries. Any question around flight data will be converted into a Snowflake SQL query that hits the table `FLIGHTS.PUBLIC.JAN_2013_NYC`. Pass any query into the "sql_query" parameter


The schema of the table includes
```
ID	NUMBER	A unique identifier for each flight
YEAR	NUMBER	The year of the flight
MONTH	NUMBER	The month of the flight
DAY		NUMBER	The day of the month on which the flight departed
DEP_TIME	NUMBER	The actual departure time of the flight
SCHED_DEP_TIME	NUMBER	The scheduled departure time of the flight
DEP_DELAY	NUMBER	The departure delay in minutes (negative values indicate early departures)
ARR_TIME	NUMBER	The actual arrival time of the flight
SCHED_ARR_TIME	NUMBER	The scheduled arrival time of the flight
ARR_DELAY	NUMBER	The arrival delay in minutes (negative values indicate early arrivals)
CARRIER_CODE	TEXT	The carrier code of the airline
FLIGHT	NUMBER	The flight number
TAILNUM	TEXT	The aircraft tail number
ORIGIN_AIRPORT_CODE	TEXT	The origin airport code
DEST_AIRPORT_CODE	TEXT	The destination airport code
AIR_TIME	NUMBER	The total airtime of the flight in minutes
DISTANCE	NUMBER	The distance traveled by the flight in miles
HOUR	NUMBER	The hour part of the scheduled departure time
MINUTE	NUMBER	The minute part of the scheduled departure time
TIME_HOUR	NUMBER	The time at which the flight departed (rounded to the nearest hour)
CARRIER_NAME	TEXT	The full name of the airline carrier
ORIGIN_AIRPORT_NAME	TEXT	The full name of the origin airport
ORIGIN_REGION	TEXT	The region code of the origin airport
ORIGIN_MUNICIPALITY	TEXT	The city where the origin airport is located
ORIGIN_COORDINATES	TEXT	The geographical coordinates of the origin airport
DEST_AIRPORT_NAME	TEXT	The full name of the destination airport
DEST_REGION	TEXT	The region code of the destination airport
DEST_MUNICIPALITY	TEXT	The city where the destination airport is located
DEST_COORDINATES	TEXT	The geographical coordinates of the destination airport
```


When a user asks for data around flights, perform the following:


1. Use the `executeSQL` action to send a POST request to the Azure function endpoint
2. Receive the file that is returned as part of the Action response. Display it as a spreadsheet
3. Perform analysis on the file and provide the necessary information that the user has asked for


The user will wish to ask questions about the data in code interpreter, so use that for any data analysis insights from the dataset you pulled.

### OpenAPI Schema

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板，把 placeholder 換成你自己 function 的資訊，並依你在 Azure Function App 加的額外輸入調整參數。 

有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

```python
openapi: 3.1.0
info:
  title: Snowflake GPT API
  description: API to execute SQL queries on Snowflake and get the results as a CSV file URL.
  version: 1.0.0
servers:
  - url: https://<server-name>.azurewebsites.net
    description: Azure Function App server running Snowflake integration application
paths:
  /api/<function_name>?code=<code>:
    post:
      operationId: executeSQL
      summary: Executes a SQL query on Snowflake and returns the result file URL as a CSV.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                sql_query:
                  type: string
                  description: The SQL query to be executed on Snowflake.
              required:
                - sql_query
      responses:
        '200':
          description: Successfully executed the query.
          content:
            application/json:
              schema:
                type: object
                properties:
                  openaiFileResponse:
                    type: array
                    items:
                      type: string
                      format: uri
                    description: Array of URLs pointing to the result files.
        '401':
          description: Unauthorized. Missing or invalid authentication token.
        '400':
          description: Bad Request. The request was invalid or cannot be otherwise served.
        '500':
          description: Internal Server Error. An error occurred on the server.
components:
  schemas: {}
```

### FAQ 與疑難排解

* 回傳給 ChatGPT 的檔案大小上限是 10MB，超過可能會失敗。如果遇到這個限制，SQL 記得加 LIMIT。
* _為什麼一定要 Azure Function App？_ ChatGPT 的 Data Analysis（也就是 Code Interpreter）依賴一個獨立於模型 context window 的安全 Python 環境，目前資料只能用上傳檔案的方式傳進去。所以回傳資料的 GPT action 必須回 CSV 或其他資料檔。要透過 GPT action 回傳檔案，回應必須包在 `openaiFileResponse` 物件裡，這需要自訂程式碼來整理格式。
* _我公司用的不是 Azure。_ 要用其他 middleware function 透過 GPT action 接 ChatGPT，可以看 [AWS](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function) 或 [GCP](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function) 的 middleware cookbook。這份文件講的概念可以用來設計你的 middleware，不過不同雲端供應商接 Snowflake 的方式可能不一樣，例如 Snowflake 的 External OAuth integration 是專門為了連 Azure Entra ID 做的。 
* _怎麼限制 GPT 能存取的資料集？_ 限制 ChatGPT 在 Snowflake 內的存取範圍很重要，有幾種做法：
    * 用 Snowflake role 限制誰能存取哪些 table，Azure Entra ID 發給 GPT 使用者的 access token 會遵守這些限制
    * 在 middleware function 加檢查，確認存取的 table 是這個應用核准的
    * 另外建一個專門給 ChatGPT 整合用的 Database/Warehouse，把 PII 等敏感資料都清掉
* _Schema 呼叫到錯的 warehouse 或資料集：_ 如果 ChatGPT 呼叫了錯的 warehouse 或 database，可以更新 instructions，寫得更明確：(a) 該用哪個 warehouse / database，或 (b) 要求使用者在執行查詢前提供這些細節


_有想優先支援的整合嗎？我們的整合有錯嗎？歡迎到 GitHub 開 PR 或 issue，我們會去看。_


## 重點整理

- ChatGPT 的 Data Analysis 只吃檔案，所以查資料庫的 action 必須回 `openaiFileResponse`，這就是 middleware 存在的原因。
- 身分驗證靠 Azure Entra ID 發 token，Snowflake 的 External OAuth integration 用 token 對應使用者，權限由 Snowflake role 控制。
- 回傳檔案有 inline（base64）跟 URL 兩種，URL 方式要有 content_type 跟 content_disposition header，最多 10 個檔案、每個 10MB 以內。
- 這個 GPT 的 Instructions 把 table 名稱跟 schema 寫死，單一用途最穩。
- 測試 middleware 先用 cURL 或 Postman，不要直接在 ChatGPT 裡除錯。

## 練習

1. 把 Instructions 裡的 table 名稱換成你自己 Snowflake 裡的另一張表，並更新 schema 描述，看 GPT 能不能產生正確的 SQL。
2. 用 `curl -I` 檢查你產生的 pre-signed URL，確認有 content_type 跟 content_disposition。
3. 改程式，讓 middleware 在執行前檢查 SQL 只存取核准的 table，不符合就回錯誤訊息。
