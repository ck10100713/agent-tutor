---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_google_calendar.md
---

# GPT Actions 範例庫：Google Calendar

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_google_calendar.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_google_calendar.md)



## 這篇在做什麼

教你做一個 GPT Action，用 OAuth 連到 Google Calendar，讓 ChatGPT 能用自然語言幫你查詢和建立行事曆活動。內容分兩半，前半在 Google Cloud Console 開 API、建 OAuth 憑證，後半在 GPT 裡貼 OpenAPI schema 並回填 callback URL。

## 學完你會

- 在 Google Cloud Console 啟用 Calendar API、設定 OAuth consent screen 和 scope
- 在 GPT 的 Action 填入 Client ID、Client Secret、Authorization URL、Token URL 和 OpenAPI schema
- 把 ChatGPT 產生的 callback URL 加回 Google 的 Authorized redirect URIs，並用一句話測試

## 開跑前

- 一個有 Google Calendar 的 Google 帳號
- 能使用 Google Cloud Console 並設定 OAuth 憑證的權限（建專案可能需要綁 billing account）
- 能建立 GPT 的 ChatGPT 帳號

## Introduction

這頁是給要為特定應用程式做 GPT Action 的開發者看的說明。開始前，建議先看過下面幾份資料：

- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 示範怎麼連到你的 **Google Calendar**。它用 OAuth 連結你的 Google 帳號，讓你可以在行事曆裡建立、讀取、更新和刪除活動。

### 價值與商業使用情境範例

**價值**：使用者可以用 ChatGPT 的自然語言能力，直接連到自己的 Google Calendar。

**使用情境範例**：
- 想在行事曆新增一個活動。
- 想依特定條件搜尋行事曆裡的活動。
- 想刪除行事曆裡的某個活動。

***注意：*** 這是一個很適合被其他 GPT 呼叫的 GPT，可以用 @<你的 GPT 名稱> 的功能叫它。這個功能的說明在我們的 [help site](https://help.openai.com/en/articles/8908924-what-is-the-mentions-feature-for-gpts)。

## 應用程式資訊

### 前置條件

開始前，先確認你符合下面的條件。

 - 一個能使用 Google Calendar 的 Google 帳號。
 - 有權限存取 Google Calendar API，並能使用 Google Cloud Console 設定 OAuth 憑證。

# Google Calendar 設定步驟

## 啟用 Google Calendar API

- 到 [console.cloud.google.com](https://console.cloud.google.com)。
- 在專案選擇器裡選這個 GPT Action 要用的專案。還沒有專案的話，點 **Create Project**。
- 建新專案時，輸入名稱並選要關聯的 billing account。這個範例選的是 ‘No Organization’。

<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(55.43981481481482% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/0QxHM3NKyUZcv3di9CkA?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook | Create Google Cloud Project" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

這樣你就有 Google Cloud Project 了，接著設定 Google Calendar 的 API 存取。

- 在 Quick Access 選單選 **APIs & Services** > **Library**
- 搜尋 **Google Calendar API**（不是 DKIM）並點進去。
- 點 **Enable** 按鈕。

<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/uEOZVBdf8OZ8sP0DZAld?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook | Enable Google Calendar API" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

## 建立 OAuth 憑證

下一步是設定 OAuth 憑證，讓你的 GPT Action 能存取你的 Google Calendar。

依你目前的設定，可能要先設定 OAuth consent screen，我們先從這個開始。

- 在左邊選單點 **Credentials**
- 點 **Configure consent screen**
- 如果有選項，選 **Go To New Experience** 並點 **Get Started**
- 輸入 app 名稱，並在 User support email 下拉選單選你的 email。
- Audience 選 Internal，輸入聯絡 email。
- 同意條款，點 **Create**


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/Xs5oyXa1ssYY9zyPsL0s?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook | Create Consent Screen" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

現在可以建立 OAuth 憑證了。

- 點 **Create OAuth Credentials**
- 選 **Web Application**
- 輸入 application 名稱
- 在 Authorizes JavaScript Origins 輸入 `https://chat.openai.com` 和 `https://chatgpt.com`
- **Authorized redirect URIs** 先留空（後面會回來填）
- 點 **Create**
- 打開 credentials 頁面，畫面右邊會看到 OAuth client ID 和 client secret。


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/OHyS6C3ETFPCc4eqrQ4a?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="OAuth overview – Google Auth Platform – cookbook-demo – Google Cloud console" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

## 設定 OAuth Scopes

接著設定這個 OAuth client ID 可以存取哪些 scope（服務）。這裡要設定的是 Google Calendar API 的存取。

- 在左邊選單點 **Data Access**
- 點 **Add or Remove Scopes**
- 在右邊面板用 `https://www.googleapis.com/auth/calendar` 篩選
- 在篩選結果裡選第一個，scope 結尾應該是 `/auth/calendar`
- 點 **Update**，再點 **Save**


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(53.793774319066145% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/mbsRtOs10arPZtzjeum2?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Clients – Google Auth Platform – cookbook-demo – Google Cloud console" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

# GPT Action 設定步驟

現在可以設定 GPT Action 了。先設定 OAuth，讓 GPT 能向 Google Calendar 認證。

- 在你的 GPT 裡建立一個 action。
- 點設定齒輪圖示，選 **OAuth**
- 輸入從 Google Cloud Console 拿到的 **Client ID** 和 **Client Secret**。
- 輸入下列內容：
  - Authorization URL: `https://accounts.google.com/o/oauth2/auth`
  - Token URL: `https://oauth2.googleapis.com/token`
  - Scopes: `https://www.googleapis.com/auth/calendar`
- Token Exchange Method 保持預設。
- 點 **Save**


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/google-calendar-action-config.png" alt="Google Calendar OAuth" width="400"/>

接著輸入這個 action 的 OpenAPI schema。下面的設定可以讀取和建立活動，貼到 OpenAPI schema 欄位。

```yaml
openapi: 3.1.0
info:
  title: Google Calendar API
  description: This API allows you to read and create events in a user's Google Calendar.
  version: 1.0.0
servers:
  - url: https://www.googleapis.com/calendar/v3
    description: Google Calendar API server

paths:
  /calendars/primary/events:
    get:
      summary: List events from the primary calendar
      description: Retrieve a list of events from the user's primary Google Calendar.
      operationId: listEvents
      tags:
        - Calendar
      parameters:
        - name: timeMin
          in: query
          description: The lower bound (inclusive) of the events to retrieve, in RFC3339 format.
          required: false
          schema:
            type: string
            format: date-time
            example: "2024-11-01T00:00:00Z"
        - name: timeMax
          in: query
          description: The upper bound (exclusive) of the events to retrieve, in RFC3339 format.
          required: false
          schema:
            type: string
            format: date-time
            example: "2024-12-01T00:00:00Z"
        - name: maxResults
          in: query
          description: The maximum number of events to return.
          required: false
          schema:
            type: integer
            default: 10
        - name: singleEvents
          in: query
          description: Whether to expand recurring events into instances. Defaults to `false`.
          required: false
          schema:
            type: boolean
            default: true
        - name: orderBy
          in: query
          description: The order of events. Can be "startTime" or "updated".
          required: false
          schema:
            type: string
            enum:
              - startTime
              - updated
            default: startTime
      responses:
        '200':
          description: A list of events
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: The event ID
                        summary:
                          type: string
                          description: The event summary (title)
                        start:
                          type: object
                          properties:
                            dateTime:
                              type: string
                              format: date-time
                              description: The start time of the event
                            date:
                              type: string
                              format: date
                              description: The start date of the all-day event
                        end:
                          type: object
                          properties:
                            dateTime:
                              type: string
                              format: date-time
                              description: The end time of the event
                            date:
                              type: string
                              format: date
                              description: The end date of the all-day event
                        location:
                          type: string
                          description: The location of the event
                        description:
                          type: string
                          description: A description of the event
        '401':
          description: Unauthorized access due to missing or invalid OAuth token
        '400':
          description: Bad request, invalid parameters

    post:
      summary: Create a new event on the primary calendar
      description: Creates a new event on the user's primary Google Calendar.
      operationId: createEvent
      tags:
        - Calendar
      requestBody:
        description: The event data to create.
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                summary:
                  type: string
                  description: The title of the event
                  example: "Team Meeting"
                location:
                  type: string
                  description: The location of the event
                  example: "Conference Room 1"
                description:
                  type: string
                  description: A detailed description of the event
                  example: "Discuss quarterly results"
                start:
                  type: object
                  properties:
                    dateTime:
                      type: string
                      format: date-time
                      description: Start time of the event
                      example: "2024-11-30T09:00:00Z"
                    timeZone:
                      type: string
                      description: Time zone of the event start
                      example: "UTC"
                end:
                  type: object
                  properties:
                    dateTime:
                      type: string
                      format: date-time
                      description: End time of the event
                      example: "2024-11-30T10:00:00Z"
                    timeZone:
                      type: string
                      description: Time zone of the event end
                      example: "UTC"
                attendees:
                  type: array
                  items:
                    type: object
                    properties:
                      email:
                        type: string
                        description: The email address of an attendee
                        example: "attendee@example.com"
              required:
                - summary
                - start
                - end
      responses:
        '201':
          description: Event created successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                    description: The ID of the created event
                  summary:
                    type: string
                    description: The event summary (title)
                  start:
                    type: object
                    properties:
                      dateTime:
                        type: string
                        format: date-time
                        description: The start time of the event
                  end:
                    type: object
                    properties:
                      dateTime:
                        type: string
                        format: date-time
                        description: The end time of the event
        '400':
          description: Bad request, invalid event data
        '401':
          description: Unauthorized access due to missing or invalid OAuth token
        '500':
          description: Internal server error
```

成功的話，設定畫面底部會出現兩個 endpoint。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/google-calendar-action-endpoints.png" alt="Google Calendar Action Endpoints" width="600"/>

# 設定 callback URL

OAuth 設定和 OpenAPI schema 都弄好後，ChatGPT 會產生一個 callback URL。你要把這個 URL 加到 Google Cloud Console 的 **Authorized redirect URIs**。

離開 ChatGPT 的 action 設定畫面，捲到最下面，就能看到產生的 callback URL。

**注意：** 如果你改了 OAuth 設定，會產生新的 callback URL，也要再加到 Google Cloud Console 的 **Authorized redirect URIs**。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/google-calendar-callback.png" alt="Google Calendar Callback URL" width="600"/>

複製這個 URL，加到 Google Cloud Console 的 **Authorized redirect URIs**，然後點 **Save**。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/google-calendar-callback-settings.png" alt="Google Calendar Callback URL" width="600"/>


# 測試這個 Action

Action 設定好後，就可以在 ChatGPT 測試。先問你的 GPT 一個測試問題，例如：`What events do I have today?` 第一次用這個 action 會要求授權，點 **Sign in with googleapis.com** 並照畫面完成授權。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/google-signin.png" alt="Google Calendar Sign In" width="600"/>

授權完成後，就會看到你行事曆的結果。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/google-calendar-results.png" alt="Google Calendar results" width="600"/>

## 重點整理

- GPT Action 的 OAuth 分兩邊設定，Google 端發 Client ID/Secret 和 scope，GPT 端填這些值加上 Authorization/Token URL。
- OpenAPI schema 決定 GPT 能呼叫哪些 endpoint，這篇只開放讀取和建立活動。
- Callback URL 是 ChatGPT 產生的，要回填到 Google 的 Authorized redirect URIs，OAuth 設定一改就會換新的。
- Scope 給多大權限是安全決定，`/auth/calendar` 是完整讀寫。

## 練習

1. 看 OpenAPI schema，數一下有哪些 path 和 HTTP method，說出各自對應哪個行事曆操作。
2. 在 schema 加一個刪除活動的 endpoint（`DELETE /calendars/{calendarId}/events/{eventId}`），重新儲存，確認設定畫面多出一個 endpoint。
3. 改掉 OAuth 的 Client Secret 或其他設定再儲存，觀察 callback URL 有沒有變，並把新的 URL 補回 Google Console 後重新測試。
