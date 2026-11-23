---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_snowflake_direct.ipynb
---
# GPT Actions 範例庫：直接連 Snowflake

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_snowflake_direct.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_snowflake_direct.ipynb)

## 這篇在做什麼

教你做一個 GPT Action，讓 Custom GPT 直接連上 Snowflake 資料倉儲。使用者問問題後，GPT 會先掃描相關資料表取得 schema，再寫出 SQL 查詢來回答。重點在 OAuth 的 Security Integration 設定和 OpenAPI schema。

## 學完你會

- 寫出 Custom GPT 的 instructions 和 OpenAPI schema，讓它呼叫 Snowflake SQL API
- 在 Snowflake 建好 network rule、network policy 和 OAuth Security Integration，讓 ChatGPT 能連進來
- 把 Client ID、Client Secret、Authorization URL、Token URL 填進 GPT Action 的 OAuth 設定，並回頭更新 Redirect URI

## 開跑前

- 需要一個 Snowflake Data Warehouse，而且透過 ChatGPT 登入的使用者要有對應 role 去存取資料庫、schema 和資料表
- 需要能建立 Custom GPT 的 ChatGPT 帳號

## 簡介

這一頁是給開發者的指南，說明如何為特定應用程式做一個 GPT Action。開始前，先看過下面這些資料：

* [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
* [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
* [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 示範怎麼連到 Snowflake Data Warehouse。它會接收使用者的問題，掃描相關資料表取得資料 schema，再寫 SQL 查詢來回答。

注意：這份 cookbook 回傳的是 [ResultSet SQL statement](https://docs.snowflake.com/en/developer-guide/sql-api/handling-responses#getting-the-data-from-the-results)，不是完整結果，因為完整結果可能超過 GPT Actions 的 `application/json` payload 上限。正式環境和進階用途請用 middleware 回傳 CSV 檔，照 [GPT Actions - Snowflake Middleware cookbook](gpt_action_snowflake_middleware.md) 實作。

### 價值與商業使用情境


價值：使用者可以用 ChatGPT 的自然語言能力，直接連到 Snowflake 資料倉儲。

使用情境範例：

* 資料科學家可以連到資料表，用 ChatGPT 的 Data Analysis 做分析
* 一般資料使用者可以對交易資料問基本問題
* 使用者更容易看到資料全貌和可能的異常

## 應用程式資訊

### 應用程式相關連結

開始前先看看這些連結：

* 應用程式網站：[https://app.snowflake.com/](https://app.snowflake.com/)
* 應用程式 API 文件：[https://docs.snowflake.com/en/developer-guide/sql-api/intro](https://docs.snowflake.com/en/developer-guide/sql-api/intro)

### 應用程式前置條件

開始前，先在你的應用程式環境完成這些步驟：

* 準備好一個 Snowflake Data Warehouse
* 確認透過 ChatGPT 登入 Snowflake 的使用者，用對應的 role 能存取需要的資料庫、schema 和資料表

## 1. 設定 Custom GPT


### 設定 GPT Instructions

建好 Custom GPT 之後，把下面的文字複製到 Instructions 欄位。有疑問可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，那裡有這個步驟的詳細說明。

```python
**Context**: You are an expert at writing Snowflake SQL queries. A user is going to ask you a question. 

**Instructions**:
1. No matter the user's question, start by running `runQuery` operation using this query: "SELECT column_name, table_name, data_type, comment FROM {database}.INFORMATION_SCHEMA.COLUMNS" 
-- Assume warehouse = "<insert your default warehouse here>", database = "<insert your default database here>", unless the user provides different values 
2. Convert the user's question into a SQL statement that leverages the step above and run the `runQuery` operation on that SQL statement to confirm the query works. Add a limit of 100 rows
3. Now remove the limit of 100 rows and return back the query for the user to see
4. Use the <your_role> role when querying Snowflake
5. Run each step in sequence. Explain what you are doing in a few sentences, run the action, and then explain what you learned. This will help the user understand the reason behind your workflow. 

**Additional Notes**: If the user says "Let's get started", explain that the user can provide a project or dataset, along with a question they want answered. If the user has no ideas, suggest that we have a sample flights dataset they can query - ask if they want you to query that
```


### OpenAPI Schema

建好 Custom GPT 之後，把下面的文字複製到 Actions 欄位。把 servers 的 url 改成你的 Snowflake 帳號 URL 加上 `/api/v2`，格式看[這裡](https://docs.snowflake.com/en/user-guide/organizations-connect#standard-account-urls)。有疑問可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)。

```python
openapi: 3.1.0
info:
  title: Snowflake Statements API
  version: 1.0.0
  description: API for executing statements in Snowflake with specific warehouse and role settings.
servers:
  - url: 'https://<orgname>-<account_name>.snowflakecomputing.com/api/v2'


paths:
  /statements:
    post:
      summary: Execute a SQL statement in Snowflake
      description: This endpoint allows users to execute a SQL statement in Snowflake, specifying the warehouse and roles to use.
      operationId: runQuery
      tags:
        - Statements
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                warehouse:
                  type: string
                  description: The name of the Snowflake warehouse to use for the statement execution.
                role:
                  type: string
                  description: The Snowflake role to assume for the statement execution.
                statement:
                  type: string
                  description: The SQL statement to execute.
              required:
                - warehouse
                - role
                - statement
      responses:
        '200':
          description: Successful execution of the SQL statement.
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  data:
                    type: object
                    additionalProperties: true
        '400':
          description: Bad request, e.g., invalid SQL statement or missing parameters.
        '401':
          description: Authentication error, invalid API credentials.
        '500':
          description: Internal server error.
```

## 2. 設定 Snowflake 整合

下面說明怎麼設定這個第三方應用程式的驗證。有疑問可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)。

### 為 ChatGPT 設定 IP 白名單
如果 Snowflake 帳號有用 network policy 限制 IP 連線，可能要為 ChatGPT 加例外。
* 看 Snowflake 的 [Network Policies](https://docs.snowflake.com/en/user-guide/network-policies) 文件
* 到 Snowflake Worksheets
* 用[這裡](https://platform.openai.com/docs/actions/production/ip-egress-ranges#ip-egress-ranges)列的 ChatGPT 出口 IP 範圍建立 network rule
* 建立對應的 Network Policy

```python
## ChatGPT IP ranges available at https://openai.com/chatgpt-actions.json
CREATE NETWORK RULE chatgpt_network_rule
  MODE = INGRESS
  TYPE = IPV4
  VALUE_LIST = ('23.102.140.112/28',...,'40.84.180.128/28');

CREATE NETWORK POLICY chatgpt_network_policy
  ALLOWED_NETWORK_RULE_LIST = ('chatgpt_network_rule');
```

Network policy 可以套用在帳號、security integration 和使用者三個層級，越具體的 policy 會覆蓋比較一般的。依套用方式不同，你可能除了 security integration，還得調整個別使用者的 policy。遇到這個問題時，可能會看到 Snowflake 錯誤碼 390422 或一般的 "Invalid Client" 錯誤。

### 建立 Security Integration
* 看 Snowflake OAuth 概覽：[https://docs.snowflake.com/en/user-guide/oauth-snowflake-overview](https://docs.snowflake.com/en/user-guide/oauth-snowflake-overview)
* 透過 [Security Integration](https://docs.snowflake.com/en/sql-reference/sql/create-security-integration-oauth-snowflake) 建立新的 OAuth 憑證。每個 OAuth app 或 custom GPT 都要一個新的，因為 Snowflake 的 Redirect URI 和 Security Integration 是一對一對應

```python
CREATE SECURITY INTEGRATION CHATGPT_INTEGRATION
  TYPE = OAUTH
  ENABLED = TRUE
  OAUTH_CLIENT = CUSTOM
  OAUTH_CLIENT_TYPE = 'CONFIDENTIAL'
  OAUTH_REDIRECT_URI = 'https://oauth.pstmn.io/v1/callback' --- // this is a temporary value while testing your integration. You will replace this with the value your GPT provides
  OAUTH_ISSUE_REFRESH_TOKENS = TRUE
  OAUTH_REFRESH_TOKEN_VALIDITY = 7776000
  NETWORK_POLICY = chatgpt_network_policy; --- // this line should only be included if you followed step 1 above
```

<details>
  <summary>選用：自動更新 Network Rule 設定</summary>
  
  ChatGPT 現在用了超過 100 個出口 IP 位址，清單不定期更新，也不會事先公告。要保持最新，可以每天抓一次清單，套用到 network rule 上。

  ### 允許對 OpenAI 的外送流量的 network rule
  ```sql
  CREATE OR REPLACE NETWORK RULE chatgpt_actions_rule
  MODE = EGRESS       -- outbound
  TYPE = HOST_PORT
  VALUE_LIST = ('openai.com:443');
  ```
   ### 套用 rule 的 Access Integration
  ```sql
  CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION chatgpt_actions_integration
  ALLOWED_NETWORK_RULES = (chatgpt_actions_rule)
  ENABLED = TRUE;
  ```

  ### 抓取 IP 範圍的 UDF
  ```sql
  CREATE OR REPLACE FUNCTION getChatGPTActionsAddresses()
  RETURNS ARRAY  -- array<varchar>
  LANGUAGE PYTHON
  RUNTIME_VERSION = 3.10
  PACKAGES = ('requests')
  EXTERNAL_ACCESS_INTEGRATIONS = (chatgpt_actions_integration)
  HANDLER = 'get_ip_address_ranges'
AS
$$
import requests

def get_ip_address_ranges():
    resp = requests.get("https://openai.com/chatgpt-actions.json", timeout=10)
    resp.raise_for_status()
    data = [entry["ipv4Prefix"] for entry in resp.json().get("prefixes", []) if "ipv4Prefix" in entry]
    return data
$$;
  ```
  ### 更新 network rule 的 procedure
  ```sql
  CREATE OR REPLACE PROCEDURE update_chatgpt_network_rule()
  RETURNS STRING
  LANGUAGE SQL
AS
$$
DECLARE
  ip_list STRING;
BEGIN
  -- Properly quote the IPs for use in VALUE_LIST
  ip_list := '''' || ARRAY_TO_STRING(getChatGPTActionsAddresses(), ''',''') || '''';

  -- Run the dynamic SQL to update the rule
  EXECUTE IMMEDIATE
    'ALTER NETWORK RULE chatgpt_network_rule SET VALUE_LIST = (' || ip_list || ')';

  RETURN 'chatgpt_network_rule updated with ' || ARRAY_SIZE(getChatGPTActionsAddresses()) || ' entries';
END;
$$;
  ```

  ### 呼叫 procedure
  ```sql
  CALL update_chatgpt_network_rule();
  ```

  ### 每天太平洋時間早上 6 點執行 procedure
  ```sql
  CREATE OR REPLACE TASK auto_update_chatgpt_network_rule
  WAREHOUSE = COMPUTE_WH
  SCHEDULE = 'USING CRON 0 6 * * * America/Los_Angeles'
AS
  CALL update_chatgpt_network_rule();
  ```
</details>

## 3. 設定 GPT Action 驗證
### 從 Snowflake 取得關鍵資訊
* 取得 OAuth Client ID、Auth URL 和 Token URL


```python
DESCRIBE SECURITY INTEGRATION CHATGPT_INTEGRATION;
```


需要的資訊在這 3 列：


![../../../images/snowflake_direct_oauth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/snowflake_direct_oauth.png)


* 用 SHOW_OAUTH_CLIENT_SECRETS 取得 OAuth Client Secret

```python
SELECT 
trim(parse_json(SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('CHATGPT_INTEGRATION')):OAUTH_CLIENT_ID) AS OAUTH_CLIENT_ID
, trim(parse_json(SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('CHATGPT_INTEGRATION')):OAUTH_CLIENT_SECRET) AS OAUTH_CLIENT_SECRET;
```

這時候很適合[在 Postman 測試你的 Snowflake 整合](https://community.snowflake.com/s/article/How-to-configure-postman-for-testing-SQL-API-with-OAuth)。如果你為 security integration 設了 network policy，要確定它包含你測試用機器的 IP。

### 在 GPT Action 驗證裡設定 OAuth 值

在 ChatGPT 點 "Authentication"，選 "OAuth"，填入下面的資訊。

| Form Field | Value  |
| -------- | -------- |
| Authentication Type   | OAuth   |
| Client ID   | OAUTH_CLIENT_ID from SHOW_OAUTH_CLIENT_SECRETS   |
| Client Secret   | OAUTH_CLIENT_SECRET from SHOW_OAUTH_CLIENT_SECRETS   |
| Authorization URL   | OAUTH_AUTHORIZATION_ENDPOINT from DESCRIBE SECURITY INTEGRATION |
| Token URL   | OAUTH_TOKEN_ENDPOINT from DESCRIBE SECURITY INTEGRATION   |
| Scope   | session:role:CHATGPT_INTEGRATION_ROLE*   |
| Token Exchange Method   | Default (POST Request)   |


*Snowflake 的 scope 用 `session:role:<your_role>` 的格式傳 role，例如 `session:role:CHATGPT_INTEGRATION_ROLE`。這個欄位也可以留空，改在 GPT instructions 裡指定 role，但填在這裡會讓它包含在 OAuth 同意請求裡，有時候比較可靠。 

### 4. 更新 Snowflake 整合的 Redirect URI


在 ChatGPT 設好驗證之後，照下面的步驟到應用程式完成 Action 的設定。

* 從 GPT Action 複製 callback URL
* 把 Security Integration 裡的 Redirect URI 改成 ChatGPT 給的 callback URL


```python
ALTER SECURITY INTEGRATION CHATGPT_INTEGRATION SET OAUTH_REDIRECT_URI='https://chat.openai.com/aip/<callback_id>/oauth/callback';
```

### 常見問題與疑難排解

* 這份指南是為了說明一般概念，僅供參考。第三方 API 整合我們沒辦法提供完整支援。 
* 如果你更新 YAML，callback url 可能會變，改完要再檢查一次。
* _Callback URL 錯誤：_ 如果 ChatGPT 出現 callback URL 錯誤，仔細看上面的後續步驟。你必須把 callback URL 直接加到 Security Integration，Action 才能正確驗證
* _schema 呼叫了錯誤的 warehouse 或 database：_ 如果 ChatGPT 呼叫了錯的 warehouse 或 database，可以改 instructions，讓它更明確：(a) 該用哪個 warehouse / database，或 (b) 要求使用者先提供這些確切資訊才執行查詢



_有想要我們優先做的整合嗎？我們的整合有錯誤嗎？歡迎到我們的 github 發 PR 或 issue，我們會處理。_


## 重點整理

- GPT Action 的核心是兩份文字：Custom GPT 的 instructions 和描述 API 的 OpenAPI schema。
- 連 Snowflake 用 OAuth，每個 Custom GPT 要對應一個獨立的 Security Integration，因為 Redirect URI 是一對一。
- 帳號有 IP 限制時，要把 ChatGPT 的出口 IP 加進 network rule，而且清單會變，可以用排程自動更新。
- 這個做法回傳的是 ResultSet 而不是完整結果，大量資料要改用 middleware 回傳 CSV。
- GPT 選錯 warehouse 或 database 時，優先改 instructions 把範圍講清楚。

## 練習

1. 在 Custom GPT 的 instructions 裡指定一個預設的 warehouse 和 database，測試問問題時它是不是都用你指定的。
2. 把 OAuth 的 Scope 欄位留空，改在 instructions 裡指定 role，比較兩種做法的授權流程差別。
3. 把選用的自動更新 procedure 的排程時間改成你自己的時區，並手動呼叫一次 procedure，確認 network rule 的 IP 清單有更新。
