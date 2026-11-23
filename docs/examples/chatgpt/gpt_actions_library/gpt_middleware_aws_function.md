---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function.ipynb
---
# GPT Actions 範例庫：AWS Middleware

> 原文：[examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function.ipynb)



## 這篇在做什麼

示範怎麼用 AWS SAM 建一個 AWS Lambda function 當 middleware，用 Cognito 做 OAuth 保護，再接到 ChatGPT 的 GPT Action。做完之後，ChatGPT 就能用登入過的身分安全地呼叫你在 AWS 上的程式。

## 學完你會

- 用 AWS SAM template 部署 Lambda、API Gateway 和 Cognito Authorizer
- 在 Cognito 建立 user、domain 和 app client，並用 Postman 驗證 OAuth 流程
- 在 ChatGPT 建立 Action、填入 OAuth 設定，並把 ChatGPT 的 callback URL 設回 Cognito

## 開跑前

- 需要 AWS 帳號，並有權限建立 Lambda、S3 bucket、Cognito User Pool 與 App Client、API Gateway、IAM role、CloudFormation stack
- 需要安裝 AWS SAM CLI
- 需要能建立 GPT Action 的 ChatGPT 帳號，Postman 是選用的驗證工具


## 簡介

這個 GPT Action 概述怎麼建一個 **AWS Lambda** function。這份文件帶你設定一個有 OAuth 保護的 AWS Function，連到 GPT Action 和一個範例應用程式。範例用 AWS SAM（Serverless Application Model）來建立 AWS stack。

### 價值與商業情境範例

**價值**：現在可以用 ChatGPT 的能力連到 AWS Function。這樣你就能連到 AWS 裡的任何服務並在上面跑程式或應用。可以這樣用：

- 存取第三方服務，例如 AWS Redshift、AWS DynamoDB、AWS S3 等等！
- 預先處理 API 回傳的文字（例如突破 context 限制、補充 context 或 metadata）。
- 可以回傳檔案，而不是從第三方 API 取得文字。這對提供 CSV 檔做資料分析很有用，或帶回 PDF 檔，ChatGPT 會把它當成上傳的檔案處理。


**範例情境**： 
- 使用者需要在 Redshift 查資料，但需要 ChatGPT 和 Redshift 之間有個 middleware 應用來回傳檔案（資料分析要求資料精確，而且資料量很大）
- 使用者在 AWS function 裡建好了好幾個步驟，需要能用 ChatGPT 啟動那個流程。

## 應用程式資訊與前置需求

我們會用 AWS Lambda 服務來建立 middleware function。你可以透過下面的連結熟悉這套 stack： 

- Lambda 網站：https://aws.amazon.com/lambda/
- Lambda 文件：https://docs.aws.amazon.com/lambda/
- AWS SAM 文件：https://docs.aws.amazon.com/serverless-application-model/

### 前置需求

開始前，請確認你的 AWS Console 有權限建立：Lambda Function、S3 Bucket、Application Stack、Cognito User Pool、Cognito User Pool App Client、API Gateway、Lambda role、CloudFormation stack（看起來很多，但這些服務的建立都是自動化的！）。

## 建立 AWS Lambda Function

要建立 AWS Function，可以用 AWS SAM。SAM Template 的範例在[這裡](https://github.com/pap-openai/redshift-middleware/blob/main/template.yaml) [0]。

這個 template 包含：
- 給 OAuth 用的 User Pool 和 User Pool Client
- Cognito Authorizer，確保只有通過驗證的使用者才能呼叫這個 function
- 把 Lambda function 對應到既有的 VPC（要連其他 AWS 服務時很有用）
- 可以動態設定的參數（例如憑證或變數）
- 一個把 HTTP route 對應到 function 的 API Gateway

這段程式碼純粹供參考，幫你起步，不需要事先有 AWS 資源。如果你已經有 user pool，我們建議對應到既有的，而不是新建；如果需要用到其他 AWS 資源，也建議把 Lambda 放進能存取那些資源的 VPC。這類設定的範例可以看 [RedShift cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function)。

Cognito Authorizer 是確保你的 function 只有通過驗證的使用者能呼叫或存取的關鍵，請依你的環境正確設定。

[0]
```
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31
Description: >
  aws-middleware

  AWS middleware function

Parameters:
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

  MiddlewareApi:
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
        
  MiddlewareFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: aws-middleware/
      Handler: app.lambda_handler
      Runtime: python3.11
      Timeout: 45
      Architectures:
        - x86_64
      Events:
        SqlStatement:
          Type: Api
          Properties:
            Path: /my_route
            Method: post
            RestApiId: !Ref MiddlewareApi

Outputs:
  MiddlewareApi:
    Description: "API Gateway endpoint URL for Prod stage for SQL Statement function"
    Value: !Sub "https://${MiddlewareApi}.execute-api.${AWS::Region}.amazonaws.com/Prod/my_route"
  MiddlewareFunction:
    Description: "SQL Statement Lambda Function ARN"
    Value: !GetAtt MiddlewareFunction.Arn
  MiddlewareFunctionIamRole:
    Description: "Implicit IAM Role created for SQL Statement function"
    Value: !GetAtt MiddlewareFunctionRole.Arn
  CognitoUserPoolArn:
    Description: "ARN of the Cognito User Pool"
    Value: !GetAtt MyCognitoUserPool.Arn
```

你可以 clone openai-cookbook repository，從 `lambda-middleware` 目錄取得範例 python 程式和 SAM template：

```
git clone https://github.com/pap-openai/aws-lambda-middleware
cd lambda-middleware
```

要 build 和部署 function，從這個目錄執行下面的指令

```
sam build
sam deploy --template-file template.yaml --stack-name aws-middleware --capabilities CAPABILITY_IAM
```

部署好之後，可以到 AWS Lambda 看你的應用：

![../../../images/aws_lambda_1.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_1.png)

不帶任何驗證執行 curl 指令，可以確認 function 在未驗證時連不到：

```
curl -d {} <middleware_api_output_url_from_deploy_command>
```

應該會回傳 `{"message":"Unauthorized"}`。

## 在 AWS Cognito 設定驗證

_選用：只有在你新建了 user pool、沒有用既有的 pool 時才需要做這些步驟_ 

我們在新建的 user pool 裡建一個 user。做法是從部署指令的輸出取得 CognitoUserPoolArn，拿 "/" 後面的值，格式會是：`your-region_xxxxx`。

```
aws cognito-idp admin-create-user \
    --user-pool-id "your-region_xxxxx" \
    --username johndoe@example.com \
    --user-attributes Name=email,Value=johndoe@example.com \
    --temporary-password "TempPassword123"
```

接著要建立一個可以登入的網頁或 domain。到 AWS Cognito，選擇新建的 user pool，進到 App Integration 分頁：

![../../../images/aws_lambda_3.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_3.png)

點 "Domains"，再點 "Create Cognito Domain" 建立 Cognito Domain

![../../../images/aws_lambda_8.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_8.png)

在 User Pool 的 App Integration 頁面往下捲到 `App client list`：

![../../../images/aws_lambda_9.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_9.png)

選你的 app client，編輯 Hosted UI：

![../../../images/aws_lambda_10.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_10.png)

然後加上 callback URL、Authorization Scheme 和 OAuth scope：

![../../../images/aws_lambda_11.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_11.png)

_注意，等 ChatGPT 替你的 action 產生驗證用的 callback URL 後，你還要回到這一步。postman 的 URL 只應該在開發時使用。_

你可以在 Postman 試這個連線：在 `<api_url>` 的 Authorization 底下，複製貼上 AWS 上的 client_id、client_secret，以及你為驗證 domain 設定的 URL，scope 要記得加 `openid`，才能拿到有效的 access_token：

![../../../images/aws_lambda_12.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_12.png)

![../../../images/aws_lambda_13.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_13.png)

現在如果在 Postman 用剛拿到的 access_token 發 request，會收到成功的 JSON：

![../../../images/aws_lambda_14.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_14.png)

## 在 ChatGPT 建立 Action

現在把它整合進 ChatGPT。

建立一個 action，並複製貼上下面的 spec：

```
openapi: 3.1.0
info:
  title: Success API
  description: API that returns a success message.
  version: 1.0.0
servers:
  - url: https://3ho5n15aef.execute-api.us-east-1.amazonaws.com/Prod
    description: Main production server
paths:
  /my_route:
    post:
      operationId: postSuccess
      summary: Returns a success message.
      description: Endpoint to check the success status.
      responses:
        '200':
          description: A JSON object indicating success.
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                    example: true
```

如果你測試這個 action（可以點 "Test" 按鈕），會看到 401，因為你還沒通過驗證。

現在來在 action 裡加上驗證。

點 Authentication > OAuth。
接下來要取得 AWS Cognito 的變數。到你的 User Pool > User Pool App Client，可以在那裡拿到 client ID 和 client Secret。

![../../../images/aws_lambda_15.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_15.png)

把這些值複製貼到 ChatGPT。接著加上 Token URL。

在你的 User Pool 裡，可以找到之前為 hosted domain 建立的 URL。

![../../../images/aws_lambda_16.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_16.png)

拿這個 URL，加上 [AWS 的 OAuth route](https://docs.aws.amazon.com/cognito/latest/developerguide/federation-endpoints.html)。

- token：`<your_url>/oauth2/token`
- authorization：`<your_url>/oauth2/authorize`

複製貼到 ChatGPT。

在 scope 加上 openid，然後點 Save。

## 在 Cognito 設定 ChatGPT 的 URL

現在回到你的 GPT（離開 action 子畫面），你會看到 ChatGPT 提供的驗證用 callback URL：

![../../../images/aws_lambda_17.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_17.png)

拿這個 URL，去編輯 User Pool App client 的 hosted UI，並儲存變更：

![../../../images/aws_lambda_18.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_18.png)

## 測試 function

現在可以再測試一次這個 action：

![../../../images/aws_lambda_19.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_19.png)

你會被導到 AWS Cognito 頁面，用先前設定好的帳密登入。

如果現在請 GPT 執行同一個 action，它就會正確回答，因為你已經通過驗證，可以執行這個 function 了！

![../../../images/aws_lambda_20.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/aws_lambda_20.png)

# 結論

你現在已經在 ChatGPT 設好一個 action，可以用驗證過的方式跟你在 AWS 上的應用溝通！這份 cookbook 示範怎麼用帳號密碼從頭建立 Cognito Pool，不過我們建議依你的需求設定 Cognito（例如把你自己的 IDP 接進 Cognito）。

另外，這個 function 沒有連到任何其他服務，這正是能安全地跟 AWS Lambda function 溝通的好處。所以你可以調整程式碼和 AWS SAM template 來符合需求。比較複雜的 function 範例是 Redshift，它照這些步驟建立 function 和驗證，但程式碼和部署方式不一樣。

## 重點整理

- Lambda 加 API Gateway 可以當 ChatGPT 和 AWS 服務之間的 middleware，能做預處理，也能回傳檔案。
- Cognito Authorizer 是關鍵，沒有它你的 function 任何人都能呼叫。
- 驗證流程需要兩邊互相設定：Cognito 的 client ID、secret、token 和 authorization URL 填到 ChatGPT，ChatGPT 的 callback URL 再填回 Cognito。
- 先用 curl 和 Postman 驗證後端與 OAuth 都正常，再接 ChatGPT，出問題比較好定位。
- 範例只是起點，正式環境建議接既有的 user pool 或自己的 IDP，並把 Lambda 放進能連到其他資源的 VPC。

## 練習

1. 對部署好的 API 不帶 token 跑 curl，確認回 `{"message":"Unauthorized"}`，再用 Postman 取得的 access_token 帶上 `Authorization` header 重試。
2. 修改 Lambda 的 Python 程式，讓它回傳你自己定義的 JSON 欄位，重新 build 和部署，再從 ChatGPT 的 Action 測試。
3. 修改 SAM template，把新建 user pool 改成對應到你既有的 user pool，部署後確認驗證仍然成功。
