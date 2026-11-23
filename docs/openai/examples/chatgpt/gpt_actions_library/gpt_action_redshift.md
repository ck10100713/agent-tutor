---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_redshift.ipynb
---

# GPT Actions 範例庫：AWS Redshift

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_redshift.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_redshift.ipynb)



## 這篇在做什麼
示範用 AWS Lambda 類的 function 當 middleware，讓 GPT Action 能對 Redshift 下 SQL query，並把結果以檔案形式回傳給 ChatGPT 做資料分析。

## 學完你會
- 用 AWS SAM 部署一個連到 Redshift Serverless 的 middleware function。
- 查出 Redshift 的 VPC 資訊並填進 `env.yaml`，再部署並用 cURL 測試。
- 寫 Custom GPT 的 Instructions 和 OpenAPI schema，讓 GPT 傳 `query` 並取回檔案。

## 開跑前
- 需要 Redshift 環境，以及在同一個 VPC 部署 AWS function 的權限。
- AWS CLI 要已經驗證過，並安裝 AWS SAM CLI、Python、yq。
- 驗證要照 AWS Middleware cookbook 設定（用到 Cognito）。

## 簡介

這一頁是給開發者的指南，說明怎麼為特定應用程式建立 GPT Action。開始之前，先看過這些資料： 
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個方案讓 GPT action 能從 Redshift 取資料並做資料分析。它使用 AWS Functions，所有動作都在 AWS 生態系和網路內執行。Middleware（AWS function）會執行 SQL query、等它完成，再把資料以檔案形式回傳。程式碼僅供參考，應該依你的需求修改。

這個方案用到[在 Actions 中取回檔案](https://platform.openai.com/docs/actions/sending-files)的能力，讓檔案可以當成直接上傳到對話裡的一樣使用。

這個方案以 Redshift serverless 為例，如果是 provisioned Redshift，取得網路資訊和設定連線的方式可能稍有不同，但整體程式碼和（最少的）整合應該類似。

### 價值與商業使用情境

**價值**：利用 ChatGPT 的自然語言能力連接 Redshift 資料倉儲。

**使用情境範例**：
- 資料科學家可以連到資料表，用 ChatGPT 的 Data Analysis 做資料分析
- 一般資料使用者可以對交易資料問基本問題
- 使用者能更清楚看到自己的資料和潛在異常

## 應用程式資訊

### 應用程式前置需求

開始之前，確定：
- 你能存取 Redshift 環境
- 你有權限在同一個 VPC（虛擬私有網路）部署 AWS function
- 你的 AWS CLI 已經驗證過

## Middleware 資訊

### 安裝需要的函式庫
- 安裝 AWS CLI，AWS SAM 需要它（[docs](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html#getting-started-install-instructions)）
- 安裝 AWS SAM CLI（[docs](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)）
- 安裝 Python
- 安裝 yq [docs](https://github.com/mikefarah/yq?tab=readme-ov-file#install)

### Middleware function

要建立 function，照 [AWS Middleware Action cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function) 的步驟做。

要部署連到 Redshift 的應用程式，請用下面的程式碼，取代 Middleware AWS Function cookbook 裡提到的 "hello-world" GitHub repository。你可以 clone repository，也可以拿下面貼的程式碼依需求修改。

> 這份程式碼是參考用的，雖然應該能直接跑，但設計上是要依你的需求客製化（看文件後半的範例）。

要取得程式碼，可以 clone openai-cookbook repository，然後進到 redshift-middleware 目錄

```
git clone https://github.com/pap-openai/redshift-middleware
cd redshift-middleware
```

```python
import json
import psycopg2
import os
import base64
import tempfile
import csv

# Fetch Redshift credentials from environment variables
host = os.environ['REDSHIFT_HOST']
port = os.environ['REDSHIFT_PORT']
user = os.environ['REDSHIFT_USER']
password = os.environ['REDSHIFT_PASSWORD']
database = os.environ['REDSHIFT_DB']

def execute_statement(sql_statement):
    try:
        # Establish connection
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database
        )
        cur = conn.cursor()
        cur.execute(sql_statement)
        conn.commit()

        # Fetch all results
        if cur.description:
            columns = [desc[0] for desc in cur.description]
            result = cur.fetchall()
        else:
            columns = []
            result = []

        cur.close()
        conn.close()
        return columns, result

    except Exception as e:
        raise Exception(f"Database query failed: {str(e)}")

def lambda_handler(event, context):
    try:
        data = json.loads(event['body'])
        sql_statement = data['sql_statement']

        # Execute the statement and fetch results
        columns, result = execute_statement(sql_statement)
        
        # Create a temporary file to save the result as CSV
        with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.csv', newline='') as tmp_file:
            csv_writer = csv.writer(tmp_file)
            if columns:
                csv_writer.writerow(columns)  # Write the header
            csv_writer.writerows(result)  # Write all rows
            tmp_file_path = tmp_file.name

        # Read the file and encode its content to base64
        with open(tmp_file_path, 'rb') as f:
            file_content = f.read()
            encoded_content = base64.b64encode(file_content).decode('utf-8')

        response = {
            'openaiFileResponse': [
                {
                    'name': 'query_result.csv',
                    'mime_type': 'text/csv',
                    'content': encoded_content
                }
            ]
        }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response)
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

### 取得 VPC 資訊

我們需要把 function 連到 Redshift，所以要先找出 Redshift 用的網路。你可以在 AWS console 的 Redshift 介面找到，路徑是 Amazon Redshift Serverless > Workgroup configuration > `your_workgroup` > Data access，或是用 CLI：

```python
aws redshift-serverless get-workgroup --workgroup-name default-workgroup --query 'workgroup.{address: endpoint.address, port: endpoint.port, SecurityGroupIds: securityGroupIds, SubnetIds: subnetIds}'
```

### 設定 AWS function

把 `env.sample.yaml` 複製成 `env.yaml`，並換成上面取得的值。你需要一個能存取你的 DB/schema 的 Redshift 使用者。

```
cp env.sample.yaml env.yaml
```

把上一個指令取得的值，加上你的 Redshift 憑證，填進 `env.yaml`。
或者你可以手動建立一個叫 `env.yaml` 的檔案，填入下面這些變數：
```
RedshiftHost: default-workgroup.xxxxx.{region}.redshift-serverless.amazonaws.com
RedshiftPort: 5439
RedshiftUser: username
RedshiftPassword: password
RedshiftDb: my-db
SecurityGroupId: sg-xx
SubnetId1: subnet-xx
SubnetId2: subnet-xx
SubnetId3: subnet-xx
SubnetId4: subnet-xx
SubnetId5: subnet-xx
SubnetId6: subnet-xx
```

這個檔案會用來帶參數部署你的 function，如下：

```
PARAM_FILE="env.yaml"
PARAMS=$(yq eval -o=json $PARAM_FILE | jq -r 'to_entries | map("\(.key)=\(.value|tostring)") | join(" ")')
sam deploy --template-file template.yaml --stack-name redshift-middleware --capabilities CAPABILITY_IAM --parameter-overrides $PARAMS
```

template.yaml 的內容如下：

```python
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: >
  redshift-middleware

  Middleware to fetch RedShift data and return it through HTTP as files

Globals:
  Function:
    Timeout: 3

Parameters:
  RedshiftHost:
    Type: String
  RedshiftPort:
    Type: String
  RedshiftUser:
    Type: String
  RedshiftPassword:
    Type: String
  RedshiftDb:
    Type: String
  SecurityGroupId:
    Type: String
  SubnetId1:
    Type: String
  SubnetId2:
    Type: String
  SubnetId3:
    Type: String
  SubnetId4:
    Type: String
  SubnetId5:
    Type: String
  SubnetId6:
    Type: String
  CognitoUserPoolName:
    Type: String
    Default: MyCognitoUserPool
  CognitoUserPoolClientName:
    Type: String
    Default: MyCognitoUserPoolClient

Resources:
  MyCognitoUserPool:
    Type: AWS::Cognito::UserPool
    Properties:
      UserPoolName: !Ref CognitoUserPoolName
      Policies:
        PasswordPolicy:
          MinimumLength: 8
      UsernameAttributes:
        - email
      Schema:
        - AttributeDataType: String
          Name: email
          Required: false

  MyCognitoUserPoolClient:
    Type: AWS::Cognito::UserPoolClient
    Properties:
      UserPoolId: !Ref MyCognitoUserPool
      ClientName: !Ref CognitoUserPoolClientName
      GenerateSecret: true

  RedshiftMiddlewareApi:
    Type: AWS::Serverless::Api
    Properties:
      StageName: Prod
      Cors: "'*'"
      Auth:
        DefaultAuthorizer: MyCognitoAuthorizer
        Authorizers:
          MyCognitoAuthorizer:
            AuthorizationScopes:
              - openid
              - email
              - profile
            UserPoolArn: !GetAtt MyCognitoUserPool.Arn
        
  RedshiftMiddlewareFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: redshift-middleware/
      Handler: app.lambda_handler
      Runtime: python3.11
      Timeout: 45
      Architectures:
        - x86_64
      Events:
        SqlStatement:
          Type: Api
          Properties:
            Path: /sql_statement
            Method: post
            RestApiId: !Ref RedshiftMiddlewareApi
      Environment:
        Variables:
          REDSHIFT_HOST: !Ref RedshiftHost
          REDSHIFT_PORT: !Ref RedshiftPort
          REDSHIFT_USER: !Ref RedshiftUser
          REDSHIFT_PASSWORD: !Ref RedshiftPassword
          REDSHIFT_DB: !Ref RedshiftDb
      VpcConfig:
        SecurityGroupIds:
          - !Ref SecurityGroupId
        SubnetIds:
          - !Ref SubnetId1
          - !Ref SubnetId2
          - !Ref SubnetId3
          - !Ref SubnetId4
          - !Ref SubnetId5
          - !Ref SubnetId6

Outputs:
  RedshiftMiddlewareApi:
    Description: "API Gateway endpoint URL for Prod stage for SQL Statement function"
    Value: !Sub "https://${RedshiftMiddlewareApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/sql_statement/"
  RedshiftMiddlewareFunction:
    Description: "SQL Statement Lambda Function ARN"
    Value: !GetAtt RedshiftMiddlewareFunction.Arn
  RedshiftMiddlewareFunctionIamRole:
    Description: "Implicit IAM Role created for SQL Statement function"
    Value: !GetAtt RedshiftMiddlewareFunctionRole.Arn
  CognitoUserPoolArn:
    Description: "ARN of the Cognito User Pool"
    Value: !GetAtt MyCognitoUserPool.Arn
```

從上一個指令的輸出取得 URL 資訊，然後就可以跑 cURL 請求，應該會回傳檔案格式的資料：

```python
curl -X POST https://<your_url>/Prod/sql_statement/ \
-H "Content-Type: application/json" \
-d '{ "sql_statement": "SELECT * FROM customers LIMIT 10", "workgroup_name": "default-workgroup", "database_name": "pap-db" }'
```

## ChatGPT 的步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 欄位。

```python
**Context**: You are an expert at writing Redshift SQL queries. You will initially retrieve the table schema that you will use thoroughly. Every attributes, table names or data type will be known by you.

**Instructions**:
1. No matter the user's question, start by running `runQuery` operation using this query: "SELECT table_name, column_name FROM INFORMATION_SCHEMA.COLUMNS WHERE table_schema = 'public' ORDER BY table_name, ordinal_position;"  It will help you understand how to query the data. A CSV will be returned with all the attributes and their table. Make sure to read it fully and understand all available tables & their attributes before querying. You don't have to show this to the user.
2. Convert the user's question into a SQL statement that leverages the step above and run the `runQuery` operation on that SQL statement to confirm the query works. Let the user know which table you will use/query.
3. Execute the query and show him the data. Show only the first few rows.

**Additional Notes**: If the user says "Let's get started", explain they can ask a question they want answered about data that we have access to. If the user has no ideas, suggest that we have transactions data they can query - ask if they want you to query that.
**Important**: Never make up a table name or table attribute. If you don't know, go back to the data you've retrieved to check what is available. If you think no table or attribute is available, then tell the user you can't perform this query for them.
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 欄位。

它預期的回應符合我們文件[這裡](https://platform.openai.com/docs/actions/sending-files)說明的檔案取回結構，並傳入 `query` 當參數去執行。

驗證的部分，照 [AWS Middleware cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function) 的步驟設定。

> 記得依你的 function 部署，換掉 function app 名稱。

```python
openapi: 3.1.0
info:
  title: SQL Execution API
  description: API to execute SQL statements and return results as a file.
  version: 1.0.0
servers:
  - url: {your_function_url}/Prod
    description: Production server
paths:
  /sql_statement:
    post:
      operationId: executeSqlStatement
      summary: Executes a SQL statement and returns the result as a file.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                sql_statement:
                  type: string
                  description: The SQL statement to execute.
                  example: SELECT * FROM customers LIMIT 10
              required:
                - sql_statement
      responses:
        '200':
          description: The SQL query result as a JSON file.
          content:
            application/json:
              schema:
                type: object
                properties:
                  openaiFileResponse:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                          description: The name of the file.
                          example: query_result.json
                        mime_type:
                          type: string
                          description: The MIME type of the file.
                          example: application/json
                        content:
                          type: string
                          description: The base64 encoded content of the file.
                          format: byte
                          example: eyJrZXkiOiJ2YWx1ZSJ9
        '500':
          description: Error response
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
                    description: Error message.
                    example: Database query failed error details
```

## 結論

你現在部署好了一個 GPT，它透過 AWS 的 middleware 以已驗證的方式連到 Redsfhit。有權限的使用者（在 Cognito 裡的）現在可以查詢你的資料庫來做資料分析任務：

![../../../images/redshift_gpt.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/redshift_gpt.png)


## 重點整理
- GPT Action 不直接連資料庫，而是透過 VPC 內的 middleware function 執行 SQL。
- Middleware 把查詢結果以檔案回傳，ChatGPT 就能當作上傳的檔案做 Data Analysis。
- 網路設定（VPC、subnet、security group）要和 Redshift 一致，function 才連得到。
- 驗證靠 Cognito，只有授權的使用者能查資料。
- 這份程式碼是範本，查詢限制、權限等要依自己的需求客製。

## 練習
1. 照步驟把 `env.sample.yaml` 複製成 `env.yaml`，填入你的 VPC 資訊，並用 cURL 測一次簡單的 `SELECT 1`。
2. 修改 Custom GPT Instructions，要求 GPT 只能產生 SELECT 語句，不准寫入。
3. 在 OpenAPI schema 加一個參數（例如 row limit），並改 middleware 程式碼讓它套用到 query。
