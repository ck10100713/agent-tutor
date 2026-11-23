---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_canvas.md
---
# GPT Actions 範例庫：Canvas 學習管理系統

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_canvas.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_canvas.md)



## 這篇在做什麼

示範怎麼用 ChatGPT 的 Custom Actions 接上 Canvas LMS（學習管理系統），做出一個能幫學生查課程、出模擬考題、給回饋的 Custom GPT。內容包含 Canvas 的認證方式、GPT instructions 和 OpenAPI schema。

## 學完你會

- 判斷 Canvas 該用 OAuth 還是使用者自己產生的 access token 來認證
- 為 Custom GPT 寫 instructions 和 OpenAPI schema，呼叫 Canvas 的課程、模組 API
- 想出其他可以接 Canvas API 的用途，像課堂分析和作業檢討

## 開跑前

- 一個 Canvas LMS 帳號（OAuth 需要 Admin 設定權限）
- ChatGPT 帳號，能建立 Custom GPT

---

### 目錄

1. [**App 基本資訊**](#general-app-information)：Canvas LMS 的概述、功能，以及 ChatGPT Custom Actions 如何透過 AI 整合提升教學體驗。

2. [**從 ChatGPT 到 Canvas 的認證**](#authentication-from-chatgpt-to-canvas)：說明連接 ChatGPT 與 Canvas 的認證方式（OAuth 和使用者產生的 access token），以及各自的設定步驟。

3. [**範例情境：學生課程助理**](#sample-use-case-student-course-assistant)：詳細示範用 ChatGPT 幫學生瀏覽課程、準備考試、取得個人化回饋，包含具體的 API 呼叫和流程。

4. [**其他可考慮的用途**](#other-use-cases-for-consideration)：用 Canvas API 能做的其他整合，像課堂分析和報告產生。

5. [**恭喜**](#congratulations)

## App 基本資訊

Canvas 是廣泛使用的學習管理系統（LMS），用來支援線上學習和教學。它提供一整套工具，涵蓋課程管理、內容發布、評量和學生協作。透過 [Canvas REST API](https://canvas.instructure.com/doc/api/all_resources.html)，Canvas 可以高度客製，也能整合第三方應用，包含 ChatGPT 這類 AI 工具。

ChatGPT 的 Custom Actions 搭配 Canvas，讓教育者能用 AI 強化課程內容、自動化任務，並為學生打造個人化的學習歷程。例如根據進行中的課程做虛擬助教，因為這類功能很適合從 Canvas 拉資訊進來，形成教學對話。ChatGPT 加 Custom Actions 不是要自動化整個 Canvas 體驗，也不是取代許多更適合在 Canvas app 裡完成的功能。

## 從 ChatGPT 到 Canvas 的認證

Custom Actions 認證的整體說明，見 [Action authentication 文件](https://platform.openai.com/docs/actions/authentication)。

Canvas 有兩種認證方式：1) OAuth 和 2) 使用者產生的 access token。
- 大規模部署一定要用 OAuth 來做 Action 認證。
- 如果只是單人使用，或沒有 Admin 設定的權限，可以考慮使用者產生的 access token。要注意 action 發出的任何請求都是用使用者產生的 token，所以 Canvas 會把所有請求記成該使用者的活動，並用該使用者的權限來完成。

### 在 Canvas 實作 OAuth

這份 Canvas cookbook 沒有用 OAuth，但任何超過一個使用者的部署都必須用。詳細流程見 [OAuth for Canvas 文件](https://canvas.instructure.com/doc/api/file.oauth.html#oauth2-flow)。

在 Canvas Custom Action 實作 OAuth 時，要記住這幾點：

-  OAuth 需要 Canvas 的 Admin 設定權限，才能取得 Client ID 和 Client Secret。
-  Authorization URL 長這樣（記得換成你的 Canvas 安裝網址）：https://<canvas-install-url>/login/oauth2/auth
-  Token URL 長這樣（記得換成你的 Canvas 安裝網址）：ttps://<canvas-install-url>/login/oauth2/token
-  Custom Action 裡不一定要定義 scope。如果 developer key 不要求 scope、也沒指定 scope 參數，access token 就能存取所有 scope。如果 developer key 要求 scope、卻沒指定 scope 參數，Canvas 會回應 "invalid_scope"。更多 developer key 的資訊看[這裡](https://canvas.instructure.com/doc/api/file.developer_keys.html)，endpoint 看[這裡](https://canvas.instructure.com/doc/api/file.oauth_endpoints.html#get-login-oauth2-auth)。
-  Token Exchange Method 用預設（POST Request）
-  Canvas 用 `redirect_uri` 這個詞，ChatGPT 則叫 `Callback URL`，都是認證成功後用來完成 redirect 的網址。

### 用使用者產生的 access token 認證

有些情況適合用[使用者產生的 access token](https://canvas.instructure.com/doc/api/file.oauth.html#manual-token-generation) 做 Custom Action 的 Canvas 認證。步驟如下：

  1. 進到 Canvas 的帳號設定，如下圖：
  ![canvas_lms_settings_link.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/canvas_lms_settings_link.png)
  2. 往下捲到 token 清單，如下圖：          
  ![canvas_lms_list_of_tokens.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/canvas_lms_list_of_tokens.png)
  3. 產生新的 token，並且**把 token 存好**，之後就看不到了。
  ![canvas_lms_new_token.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/canvas_lms_new_token.png)

## 範例情境：學生課程助理

### 概述

幫學生瀏覽和理解自己的課程：提供詳細資訊、產生個人化的模擬考，並給出建設性的回饋來加強學習。

### 注意事項

- 有些資訊（像 Syllabus）透過 API 請求時會回傳 HTML 頁面，在 ChatGPT 裡無法顯示。改成參考課程描述、模組和作業來引導使用者。
- 可以用 `include[]` 這個 query parameter 修改請求，取得特定的資訊。如果你需要查課程的某項特定資訊，在 GPT instructions 裡給個範例。

### GPT Instructions

這些 instructions 有很多種寫法。prompt engineering 的策略和最佳實踐看[這裡](https://platform.openai.com/docs/guides/prompt-engineering)。

```
# **Context:** You support college students by providing detailed information about their courses hosted on the Canvas Learning Management System. You help them understand course content, generate practice exams based on provided materials, and offer insightful feedback to aid their learning journey. Assume the students are familiar with basic academic terminologies.

# **Instructions:**

## Scenarios

### - When the user asks for information about a specific course, follow this 5 step process:
1. Ask the user to specify the course they want assistance with and the particular area of focus (e.g., overall course overview, specific module).
2. If you do not know the Course ID for the course requested, use the listYourCourses to find the right course and corresponding ID in Canvas. If none of the courses listed returned courses that seem to match the course request, use the searchCourses to see if there are any similarly named course. 
3. Retrieve the course information from Canvas using the getSingleCourse API call and the listModules API call. 
4. Ask the user which module(s) they would like to focus on and use the listModuleItems to retrieve the requested module items. For any assignments, share links to them.
5. Ask if the user needs more information or if they need to prepare for an exam.

### When a user asks to take a practice test or practice exam for a specific course, follow this 6 step process:
1. Ask how many questions
2. Ask which chapters or topics they want to be tested on, provide a couple examples from the course modules in Canvas.
3. Ask 1 question at a time, be sure the questions are multiple choice (do not generate the next question until the question is answered)
4. When the user answers, tell them if its right or wrong and give a description for the correct answer 
5. Ask the user if they want to export the test results and write the code to create the PDF
6. Offer additional resources and study tips tailored to the user's needs and progress, and inquire if they require further assistance with other courses or topics.

### When a user asks to create a study guide
- Format the generated study guide in a table
```

### OpenAPI Schema

- 用到的 API 呼叫
  - [GET] [listYourCourses](https://canvas.instructure.com/doc/api/courses.html#method.courses.index)
  - [GET] [getSingleCourse](https://canvas.instructure.com/doc/api/courses.html#method.courses.show)
  - [GET] [listModules](https://canvas.instructure.com/doc/api/modules.html#method.context_modules_api.index)
  - [GET] [listModuleItems](https://canvas.instructure.com/doc/api/modules.html#method.context_module_items_api.index)
  - [GET] [searchCourses](https://canvas.instructure.com/doc/api/search.html#method.search.all_courses)

下面這份是結合 [Canvas API Reference](https://canvas.instructure.com/doc/api/index.html) 和 [ActionsGPT](https://chatgpt.com/g/g-TYEliDU6A-actionsgpt) 產生的。

```yaml
openapi: 3.1.0
info:
  title: Canvas API
  description: API for interacting with Canvas LMS, including courses, modules, module items, and search functionalities.
  version: 1.0.0
servers:
  - url: https://canvas.instructure.com/api/v1
    description: Canvas LMS API server
    variables:
      domain:
        default: canvas.instructure.com
        description: The domain of your Canvas instance
paths:
  /courses:
    get:
      operationId: listYourCourses
      summary: List your courses
      description: Retrieves a paginated list of active courses for the current user.
      parameters:
        - name: enrollment_type
          in: query
          description: Filter by enrollment type (e.g., "teacher", "student").
          schema:
            type: string
        - name: enrollment_role
          in: query
          description: Filter by role type. Requires admin permissions.
          schema:
            type: string
        - name: enrollment_state
          in: query
          description: Filter by enrollment state (e.g., "active", "invited").
          schema:
            type: string
        - name: exclude_blueprint_courses
          in: query
          description: Exclude Blueprint courses if true.
          schema:
            type: boolean
        - name: include
          in: query
          description: Array of additional information to include (e.g., "term", "teachers").
          schema:
            type: array
            items:
              type: string
        - name: per_page
          in: query
          description: The number of results to return per page.
          schema:
            type: integer
          example: 10
        - name: page
          in: query
          description: The page number to return.
          schema:
            type: integer
          example: 1
      responses:
        '200':
          description: A list of courses.
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: The ID of the course.
                    name:
                      type: string
                      description: The name of the course.
                    account_id:
                      type: integer
                      description: The ID of the account associated with the course.
                    enrollment_term_id:
                      type: integer
                      description: The ID of the term associated with the course.
                    start_at:
                      type: string
                      format: date-time
                      description: The start date of the course.
                    end_at:
                      type: string
                      format: date-time
                      description: The end date of the course.
                    course_code:
                      type: string
                      description: The course code.
                    state:
                      type: string
                      description: The current state of the course (e.g., "unpublished", "available").
        '400':
          description: Bad request, possibly due to invalid query parameters.
        '401':
          description: Unauthorized, likely due to invalid authentication credentials.

  /courses/{course_id}:
    get:
      operationId: getSingleCourse
      summary: Get a single course
      description: Retrieves the details of a specific course by its ID.
      parameters:
        - name: course_id
          in: path
          required: true
          description: The ID of the course.
          schema:
            type: integer
        - name: include
          in: query
          description: Array of additional information to include (e.g., "term", "teachers").
          schema:
            type: array
            items:
              type: string
      responses:
        '200':
          description: A single course object.
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: integer
                    description: The ID of the course.
                  name:
                    type: string
                    description: The name of the course.
                  account_id:
                    type: integer
                    description: The ID of the account associated with the course.
                  enrollment_term_id:
                    type: integer
                    description: The ID of the term associated with the course.
                  start_at:
                    type: string
                    format: date-time
                    description: The start date of the course.
                  end_at:
                    type: string
                    format: date-time
                    description: The end date of the course.
                  course_code:
                    type: string
                    description: The course code.
                  state:
                    type: string
                    description: The current state of the course (e.g., "unpublished", "available").
                  is_public:
                    type: boolean
                    description: Whether the course is public.
                  syllabus_body:
                    type: string
                    description: The syllabus content of the course.
                  term:
                    type: object
                    description: The term associated with the course.
                    properties:
                      id:
                        type: integer
                      name:
                        type: string
                      start_at:
                        type: string
                        format: date-time
                      end_at:
                        type: string
                        format: date-time
        '400':
          description: Bad request, possibly due to an invalid course ID or query parameters.
        '401':
          description: Unauthorized, likely due to invalid authentication credentials.
        '404':
          description: Course not found, possibly due to an invalid course ID.

  /courses/{course_id}/modules:
    get:
      operationId: listModules
      summary: List modules in a course
      description: Retrieves the list of modules for a given course in Canvas.
      parameters:
        - name: course_id
          in: path
          required: true
          description: The ID of the course.
          schema:
            type: integer
        - name: include
          in: query
          description: Include additional information such as items in the response.
          schema:
            type: array
            items:
              type: string
            example: ["items"]
        - name: search_term
          in: query
          description: The partial title of the module to match and return.
          schema:
            type: string
        - name: student_id
          in: query
          description: Return module completion information for the student with this ID.
          schema:
            type: integer
        - name: per_page
          in: query
          description: The number of results to return per page.
          schema:
            type: integer
          example: 10
        - name: page
          in: query
          description: The page number to return.
          schema:
            type: integer
          example: 1
      responses:
        '200':
          description: A list of modules in the course.
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: The ID of the module.
                    name:
                      type: string
                      description: The name of the module.
                    items_count:
                      type: integer
                      description: The number of items in the module.
                    state:
                      type: string
                      description: The state of the module (e.g., "active", "locked").
        '400':
          description: Bad request, possibly due to an invalid course ID or query parameters.
        '401':
          description: Unauthorized, likely due to invalid authentication credentials.
        '404':
          description: Course not found, possibly due to an invalid course ID.

  /courses/{course_id}/modules/{module_id}/items:
    get:
      operationId: listModuleItems
      summary: List items in a module
      description: Retrieves the list of items within a specific module in a Canvas course.
      parameters:
        - name: course_id
          in: path
          required: true
          description: The ID of the course.
          schema:
            type: integer
        - name: module_id
          in: path
          required: true
          description: The ID of the module.
          schema:
            type: integer
        - name: include
          in: query
          description: Include additional information in the response, such as content details.
          schema:
            type: array
            items:
              type: string
            example: ["content_details"]
        - name: student_id
          in: query
          description: Return completion information for the student with this ID.
          schema:
            type: integer
        - name: per_page
          in: query
          description: The number of results to return per page.
          schema:
            type: integer
          example: 10
        - name: page
          in: query
          description: The page number to return.
          schema:
            type: integer
          example: 1
      responses:
        '200':
          description: A list of items in the module.
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: The ID of the module item.
                    title:
                      type: string
                      description: The title of the module item.
                    type:
                      type: string
                      description: The type of the module item (e.g., "Assignment", "File").
                    position:
                      type: integer
                      description: The position of the item within the module.
                    indent:
                      type: integer
                      description: The level of indentation of the item in the module.
                    completion_requirement:
                      type: object
                      description: The completion requirement for the item.
                      properties:
                        type:
                          type: string
                        min_score:
                          type: integer
                    content_id:
                      type: integer
                      description: The ID of the associated content item (e.g., assignment, file).
                    state:
                      type: string
                      description: The state of the item (e.g., "active", "locked").
        '400':
          description: Bad request, possibly due to an invalid module ID or query parameters.
        '401':
          description: Unauthorized, likely due to invalid authentication credentials.
        '404':
          description: Module or course not found, possibly due to an invalid module or course ID.

  /search/all_courses:
    get:
      operationId: searchCourses
      summary: Search for courses
      description: Searches for public courses in Canvas.
      parameters:
        - name: search
          in: query
          description: The search term to filter courses.
          schema:
            type: string
        - name: public_only
          in: query
          description: If true, only returns public courses.
          schema:
            type: boolean
        - name: open_enrollment_only
          in: query
          description: If true, only returns courses with open enrollment.
          schema:
            type: boolean
        - name: enrollment_type
          in: query
          description: Filter by enrollment type (e.g., "teacher", "student").
          schema:
            type: string
        - name: sort
          in: query
          description: Sort the results by "asc" or "desc" order.
          schema:
            type: string
          enum:
            - asc
            - desc
        - name: per_page
          in: query
          description: The number of results to return per page.
          schema:
            type: integer
          example: 10
        - name: page
          in: query
          description: The page number to return.
          schema:
            type: integer
          example: 1
      responses:
        '200':
          description: A list of courses matching the search criteria.
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                      description: The ID of the course.
                    name:
                      type: string
                      description: The name of the course.
                    account_id:
                      type: integer
                      description: The ID of the account associated with the course.
                    enrollment_term_id:
                      type: integer
                      description: The ID of the term associated with the course.
                    start_at:
                      type: string
                      format: date-time
                      description: The start date of the course.
                    end_at:
                      type: string
                      format: date-time
                      description: The end date of the course.
                    course_code:
                      type: string
                      description: The course code.
                    state:
                      type: string
                      description: The current state of the course (e.g., "unpublished", "available").
                    is_public:
                      type: boolean
                      description: Whether the course is public.
                    term:
                      type: object
                      description: The term associated with the course.
                      properties:
                        id:
                          type: integer
                        name:
                          type: string
                        start_at:
                          type: string
                          format: date-time
                        end_at:
                          type: string
                          format: date-time
        '400':
          description: Bad request, possibly due to invalid query parameters.
        '401':
          description: Unauthorized, likely due to invalid authentication credentials.
        '404':
          description: No courses found matching the criteria.
```

### 對話開場建議

- Help me take a practice exam.
- Give an overview of one of my courses.
- List all of my courses.

### GPT 功能設定

- [開] Web Browsing
- [開] DALL·E Image Generation
- [開] Code Interpreter & Data Analysis

## 其他可考慮的用途

下面是用 Canvas API 可以探索的其他用途，不是完整清單。每個只給基本輪廓，GPT instructions 和要用的 API 呼叫刻意留給你，依需求決定。

### 課堂分析與報告

**用途：** 讓老師拿到學生參與度、成績和課堂表現的完整分析報告。有了這些資料，老師能做出有根據的決策，調整教學方式、找出有風險的學生，提升整體課堂成效。

**API 資源：**

- [**Analytics**](https://canvas.instructure.com/doc/api/analytics.html) 和 [**Quiz Statistics**](https://canvas.instructure.com/doc/api/quiz_statistics.html)：取得學生參與、成績和課程層級統計的詳細資料。
- [**Quiz Reports**](https://canvas.instructure.com/doc/api/quiz_reports.html)：產生並檢視各種報告，分析全班表現並追蹤長期進度。

### 已評分作業的檢討與改進指引

**用途：** 提供學生一個工具，檢討已評分的作業、分析表現，並針對知識缺口拿到有針對性的改進建議。工具可以標出學生卡住的題目或章節，並推薦額外的資源或練習教材。

**API 資源：**

- [**Submissions**](https://canvas.instructure.com/doc/api/submissions.html) 和 [**Quiz Submissions**](https://canvas.instructure.com/doc/api/quiz_submissions.html)：取得學生的繳交內容和對應的成績。
- [**Assignments**](https://canvas.instructure.com/doc/api/assignments.html)：取得作業的詳細資訊，包含 rubric 和評分標準。
- [**Rubric Assessments**](https://canvas.instructure.com/doc/api/rubrics.html)：取得詳細的回饋和 rubric 評量
- [**Modules**](https://canvas.instructure.com/doc/api/modules.html)：用 List modules API 推薦針對學生弱項的額外學習模組。
- [**Quizzes**](https://canvas.instructure.com/doc/api/quizzes.html)：推薦練習測驗，幫助學生補強特定的知識缺口

# 恭喜！

你已經成功建立一個 Custom GPT，並接上能用的 Canvas LMS Custom Action。你應該能進行類似下面截圖的對話。做得好，繼續加油！

![canvas_lms_sample_conversation.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/canvas_lms_sample_conversation.png)

## 重點整理

- 多人使用的部署一定要用 OAuth；單人測試才適合用自己產生的 access token，但所有請求都會以那個人的身分和權限執行。
- Canvas 的 `redirect_uri` 就是 ChatGPT 的 `Callback URL`，設定 OAuth 時要對起來。
- API 回傳 HTML（像 Syllabus）的資料在 ChatGPT 裡顯示不了，要改用課程描述、模組、作業等替代。
- 用 `include[]` 這類 query parameter 取特定資料時，要在 GPT instructions 裡給範例，模型才會用對。

## 練習

1. 照步驟用使用者產生的 token 設定認證，跑一次「List all of my courses」，確認有拿到課程。
2. 在 GPT instructions 加一個 `include[]` 的範例，讓它在介紹課程時一併取得你想要的欄位。
3. 挑「作業檢討」的用途，在 OpenAPI schema 加上 Submissions 的 GET 呼叫，並改 instructions 讓 GPT 能分析成績。
