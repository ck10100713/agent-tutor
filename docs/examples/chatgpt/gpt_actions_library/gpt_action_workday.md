---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_workday.md
---

# GPT Actions 範例庫：Workday

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_workday.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_workday.md)



## 這篇在做什麼
教你用 ChatGPT 的 Custom Actions 接上 Workday，做一個 HR 助理 GPT。它能幫員工送出 PTO（休假）申請、查員工資料、查福利方案。

## 學完你會
- 用 OAuth 把 GPT 接到 Workday，並知道 API client 要怎麼設定、需要哪些 scope。
- 寫出讓 GPT 先取得員工 ID 再執行後續操作的 GPT Instructions。
- 用 OpenAPI schema 定義 Request_Time_Off、Get_Workers 等 Workday API 呼叫。

## 開跑前
- 需要 Workday Admin 權限，才能取得 Client ID 和 Client Secret。
- 需要能建立 Custom GPT 的 ChatGPT 帳號。

## **目錄**

1. [General App Information](#general-app-information)  
2. [Authentication from ChatGPT to Workday](#authentication-from-chatgpt-to-workday)  
3. [Sample Use Case: PTO Submission and Benefit Plan Inquiry](#sample-use-case-pto-submission-and-benefit-plan-inquiry)  
4. [Additional Resources](#additional-resources)  
5. [Conclusion](#conclusion)

## 應用程式基本資訊

Workday 是雲端平台，提供人力資本管理、薪資和財務管理的解決方案。透過 Custom Actions 把 ChatGPT 接到 Workday，可以自動回覆員工的問題、帶員工走完 HR 流程，並從 Workday 撈出關鍵資訊。

有了 Custom Actions，企業可以用 AI 改善 HR 流程、自動化工作，並提供個人化的員工支援，例如做一個虛擬 HR 助理，回答福利、休假和薪資相關問題。

## 從 ChatGPT 驗證到 Workday

要把 ChatGPT 接到 Workday，使用 OAuth：

* 需要 Workday Admin 權限來取得 Client ID 和 Client Secret。  
* 重要的 URL：  
    * **Authorization URL**：`[Workday Tenant URL]/authorize`，通常長這樣：`https://wd5-impl.workday.com/<your_tenant>/authorize`  
    * **Token URL**：`[Workday Tenant URL]/token`，通常長這樣：`https://wd5-impl-services1.workday.com/ccx/oauth2/<your_tenant>/token` 

*建立 API Client 之後，以 Workday 給你的 URL 為準，它會依你的 tenant 和資料中心給出實際要用的網址。*

**設定 OAuth 的步驟**：

1. 在 Workday 執行 Register API client 這個 task。
2. 照下面的範例圖設定 API client。  
3. Scope 依 GPT 要做的動作而定。這個案例需要：`Staffing`、`Tenant Non-Configurable`、`Time Off and Leave`、`Include Workday Owned Scope`
4. 把 GPT 裡的 **Redirection URI** 填進 API client 設定。
5. 把 **Client ID** 和 **Client Secret** 存起來，等一下要貼進 GPT。  
6. 照下圖，把 OAuth 資訊填進 GPT 的 Authentication 區塊。  

*Redirection URI 要在 GPT 設定頁選了 OAuth 當驗證方式之後才看得到。* 

![workday-cgpt-oauth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/workday-cgpt-oauth.png)

![workday-api-client.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/workday-api-client.png)

想深入了解可以看 [Workday Community 的 API client 頁面](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/(https:/doc.workday.com/admin-guide/en-us/authentication-and-security/authentication/oauth/dan1370797831010.html))*（需要 community 帳號）*。

## 範例情境：PTO 申請與福利方案查詢

### 概述

這個情境示範怎麼幫員工送出 PTO 申請、取得員工資料，並透過 RAAS report 查看福利方案。

## GPT Instructions

用下面的 instructions 處理 PTO 申請、員工資料查詢和福利方案查詢：

```
# **Context:** You support employees by providing detailed information about their PTO submissions, worker details, and benefit plans through the Workday system. You help them submit PTO requests, retrieve personal and job-related information, and view their benefit plans. Assume the employees are familiar with basic HR terminologies.
# **Instructions:**

## Scenarios
### - When the user asks to submit a PTO request, follow this 3 step process:
1. Ask the user for PTO details, including start date, end date, and type of leave.
2. Submit the request using the `Request_Time_Off` API call.
3. Provide a summary of the submitted PTO request, including any information on approvals.

### - When the user asks to retrieve worker details, follow this 2 step process:
1. Retrieve the worker’s details using `Get_Workers`.
2. Summarize the employee’s job title, department, and contact details for easy reference.

### - When the user asks to inquire about benefit plans, follow this 2 step process:
1. Retrieve benefit plan details using `Get_Report_As_A_Service`.
2. Present a summary of the benefits.
```

### 代替員工建立申請

在 Workday 對員工執行動作需要員工 ID，所以在做任何查詢之前要先取得。我們的做法是在驗證完成後呼叫一個 Workday RAAS report，它會回傳目前登入的使用者。也許光用 REST API 呼叫也能做到。ID 取回來之後，其他所有動作都會用它。

RAAS report 範例：使用 Current User 欄位，會回傳透過 OAuth 驗證的那位員工。    
![custom-report-workday-01.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/custom-report-workday-01.png)

![custom-report-workday-02.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/custom-report-workday-02.png)

### OpenAPI Schema

下面是用 Workday REST API Reference 和 [ActionsGPT](https://chatgpt.com/g/g-TYEliDU6A-actionsgpt) 產生的 OpenAPI schema 範例。

我們用到這幾個 API 呼叫：
* **\[POST\] Request\_Time\_Off**：幫員工建立休假申請。  
* **\[GET\] Get\_Workers**：取得員工資料。  
* **\[GET\] Get\_eligibleAbsenceTypes**：取得可用的休假方案。  
* **\[GET\] Get\_Report\_As\_A\_Service (RAAS)**：拉報表，包含自訂的 RAAS report，用來查福利明細。


路徑要換成正確的 tenant ID，並設定到對應的 server。不同 PTO 類型所需的 ID 也要確認設對。

```yaml
openapi: 3.1.0
info:
  title: Workday Employee API
  description: API to manage worker details, absence types, and benefit plans in Workday.
  version: 1.3.0
servers:
  - url: https://wd5-impl-services1.workday.com/ccx
    description: Workday Absence Management API Server
paths:
  /service/customreport2/tenant/GPT_RAAS:
    get:
      operationId: getAuthenticatedUserIdRaaS
      summary: Retrieve the Employee ID for the authenticated user.
      description: Fetches the Employee ID for the authenticated user from Workday.
      responses:
        '200':
          description: A JSON object containing the authenticated user's Employee ID.
          content:
            application/json:
              schema:
                type: object
                properties:
                  employeeId:
                    type: string
                    description: The Employee ID of the authenticated user.
                    example: "5050"
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
      security:
        - bearerAuth: []

  /api/absenceManagement/v1/tenant/workers/Employee_ID={employeeId}/eligibleAbsenceTypes:
    get:
      operationId: getEligibleAbsenceTypes
      summary: Retrieve eligible absence types by Employee ID.
      description: Fetches a list of eligible absence types for a worker by their Employee ID, with a fixed category filter.
      parameters:
        - name: employeeId
          in: path
          required: true
          description: The Employee ID of the worker (passed as `Employee_ID=3050` in the URL).
          schema:
            type: string
            example: "5050"
        - name: category
          in: query
          required: true
          description: Fixed category filter for the request. This cannot be changed.
          schema:
            type: string
            example: "17bd6531c90c100016d4b06f2b8a07ce"
      responses:
        '200':
          description: A JSON array of eligible absence types.
          content:
            application/json:
              schema:
                type: object
                properties:
                  absenceTypes:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                        name:
                          type: string
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker or absence types not found.
      security:
        - bearerAuth: []

  /api/absenceManagement/v1/tenant/workers/Employee_ID={employeeId}:
    get:
      operationId: getWorkerById
      summary: Retrieve worker details by Employee ID.
      description: Fetches detailed information of a worker using their Employee ID.
      parameters:
        - name: employeeId
          in: path
          required: true
          description: The Employee ID of the worker.
          schema:
            type: string
            example: "5050"
      responses:
        '200':
          description: A JSON object containing worker details.
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: object
                    properties:
                      firstName:
                        type: string
                      lastName:
                        type: string
                  position:
                    type: string
                  email:
                    type: string
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker not found.
      security:
        - bearerAuth: []

  /api/absenceManagement/v1/tenant/workers/Employee_ID={employeeId}/requestTimeOff:
    post:
      operationId: requestTimeOff
      summary: Request time off for a worker.
      description: Allows a worker to request time off by providing the necessary details.
      parameters:
        - name: employeeId
          in: path
          required: true
          description: The Employee ID of the worker requesting time off.
          schema:
            type: string
            example: "5050"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                days:
                  type: array
                  description: Array of days for which the time off is being requested.
                  items:
                    type: object
                    properties:
                      start:
                        type: string
                        format: date
                        description: The start date of the time off.
                        example: "2024-11-26"
                      date:
                        type: string
                        format: date
                        description: The specific date for the time off.
                        example: "2024-11-26"
                      end:
                        type: string
                        format: date
                        description: The end date of the time off.
                        example: "2024-11-26"
                      dailyQuantity:
                        type: number
                        description: The number of hours per day to take off.
                        example: 8
                      timeOffType:
                        type: object
                        description: Time off type with corresponding ID.
                        properties:
                          id:
                            type: string
                            description: The ID of the time off type.
                            example: "b35340ce4321102030f8b5a848bc0000"
                            enum:
                              - <flexible_time_off_id_from_workday>  # Flexible Time Off ID (hexa format)
                              - <sick_leave_id_from_workday>  # Sick Leave ID (hexa format)
      responses:
        '200':
          description: Time off request created successfully.
        '400':
          description: Invalid input or missing parameters.
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker not found.
      security:
        - bearerAuth: []

  /service/customreport2/tenant/GPT_Worker_Benefit_Data:
    get:
      operationId: getWorkerBenefitPlans
      summary: Retrieve worker benefit plans enrolled by Employee ID.
      description: Fetches the benefit plans in which the worker is enrolled using their Employee ID.
      parameters:
        - name: Worker!Employee_ID
          in: query
          required: true
          description: The Employee ID of the worker.
          schema:
            type: string
            example: "5020"
        - name: format
          in: query
          required: true
          description: The format of the response (e.g., `json`).
          schema:
            type: string
            example: "json"
      responses:
        '200':
          description: A JSON array of the worker's enrolled benefit plans.
          content:
            application/json:
              schema:
                type: object
                properties:
                  benefitPlans:
                    type: array
                    items:
                      type: object
                      properties:
                        planName:
                          type: string
                        coverage:
                          type: string
                        startDate:
                          type: string
                          format: date
                        endDate:
                          type: string
                          format: date
        '401':
          description: Unauthorized - Invalid or missing Bearer token.
        '404':
          description: Worker or benefit plans not found.
      security:
        - bearerAuth: []

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    worker:
      type: object
      properties:
        id:
          type: string
        name:
          type: object
          properties:
            firstName:
              type: string
            lastName:
              type: string
        position:
          type: string
        email:
          type: string
    absenceTypes:
      type: array
      items:
        type: object
        properties:
          id:
            type: string
          name:
            type: string
    benefitPlans:
      type: array
      items:
        type: object
        properties:
          planName:
            type: string
          coverage:
            type: string
          startDate:
            type: string
            format: date
          endDate:
            type: string
            format: date
    timeOffTypes:
      type: object
      description: Mapping of human-readable time off types to their corresponding IDs.
      properties:
        Flexible Time Off:
          type: string
          example: "b35340ce4321102030f8b5a848bc0000"
        Sick Leave:
          type: string
          example: "21bd0afbfbf21011e6ccc4dc170e0000"


```

## 結論

恭喜，你已經做好一個 Workday GPT，具備 PTO 申請、員工資料查詢和福利方案查詢的功能。

這個整合可以簡化 HR 流程，讓員工快速查到個人資料，也讓請 PTO 變簡單。這份指南是個可調整的框架，你可以很容易地加入更多 action，進一步擴充 GPT 的能力。

![workday-gpt.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/workday-gpt.png)

![pto-request.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/pto-request.png)

## 重點整理
- Custom Actions 用 OAuth 連 Workday，Client ID 和 Secret 來自 Workday 的 API client，Redirection URI 來自 GPT。
- Scope 要依 GPT 要做的事來選，給太多或太少都會出問題。
- 對員工做的操作都需要員工 ID，所以流程上要先用 RAAS report 取得目前登入者。
- OpenAPI schema 決定 GPT 能呼叫哪些 Workday API，要加功能就加 path。
- Instructions 負責告訴 GPT 什麼情況呼叫哪個 action，是行為的主要控制點。

## 練習
1. 在 OpenAPI schema 裡找出 Request_Time_Off 的 path，把 server 和 tenant 換成你自己的值。
2. 修改 GPT Instructions，讓 GPT 在送出 PTO 申請前，先列出日期和休假類型請使用者確認。
3. 照 Get_Workers 的寫法，在 schema 加一個新的 GET 操作（例如查主管資訊），並在 Instructions 裡說明何時使用。
