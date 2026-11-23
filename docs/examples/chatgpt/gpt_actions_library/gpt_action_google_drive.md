---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_google_drive.ipynb
---
# GPT Actions 函式庫：Google Drive

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_google_drive.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_google_drive.ipynb)

## 這篇在做什麼

這篇教你替 Custom GPT 做一個連到 Google Drive 的 GPT Action，讓 ChatGPT 能列出檔案、依檔名查詢、載入檔案內容，並拿來當對話的 context。內容包含 GPT 的 Instructions、OpenAPI schema，以及在 Google Cloud 和 ChatGPT 兩邊設定 OAuth 的步驟。

## 學完你會

1. 在 Google Cloud 啟用 Drive API，建立 OAuth 憑證，拿到 Client ID 和 Client Secret。
2. 為 Custom GPT 設好 Instructions 和 OpenAPI schema，包含列出檔案、取得 metadata 和匯出內容三個 action。
3. 在 ChatGPT 填好 OAuth 設定，並把 callback URL 加回 Google Cloud 的授權重新導向 URI。

## 開跑前

- 需要 Google Cloud 帳號，建立專案並啟用 Google Drive API。
- 需要 ChatGPT 能建立 Custom GPT 的方案。
- 如果應用的 “Publishing Status” 是 “Testing”，要把使用者加進測試名單。

## **簡介**

這一頁提供開發者為特定應用建 GPT Action 的說明和指南。開始之前，先熟悉下面的資訊：


* [GPT Actions 簡介](https://platform.openai.com/docs/actions/introduction)
* [GPT Actions 函式庫簡介](https://platform.openai.com/docs/actions/actions-library)
* [從零開始建 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 概述如何連到 **Google Drive**，也就是 Google 的檔案儲存系統。這個 action 讓你能列出並依檔名查詢檔案、把檔案內容載入你的 GPT，最後在 ChatGPT 裡把那些資料當 context 使用。這組 action 可以透過 [Google Drive API](https://developers.google.com/drive/api/guides/about-sdk) 裡的其他方法擴充。如果你想要一個能讀比較小的檔案的通用型 GPT，這很適合，例如：


* 會議記錄
* 產品設計文件
* 簡短的備忘錄
* 常見問題

如果想讀比較長的文件，像是整本書、有很多列的複雜 CSV，建議建立專門處理 Google Docs 或 Google Sheets 的 GPT。

### 價值與商業案例範例

使用者現在可以利用 ChatGPT 的自然語言能力，直接連到 Google Drive 裡的檔案。

使用案例範例：

- 使用者需要找出哪些檔案跟某個主題有關
- 使用者需要答案，但答案埋在文件深處


## **應用資訊**


### **應用的重要連結**

開始之前，先看看應用這邊的這些連結：


* 應用網站：[https://www.google.com/drive/](https://www.google.com/drive/)
* 應用 API 文件：[https://developers.google.com/drive/api/guides/about-sdk](https://developers.google.com/drive/api/guides/about-sdk)


### **應用的先決條件**

開始之前，確認你有 Google Cloud 帳號，而且已啟用 Drive API：



* 建立 Google Cloud 專案
* 從 Google API Library 啟用 Google Drive API
* 如果應用的 “Publishing Status” 是 “Testing”，確認使用者已加進你的應用


## **ChatGPT 的步驟**


### **Custom GPT Instructions 範例**

建好 Custom GPT 之後，要開始的話，把下面的文字複製到 Instructions 面板。你可能需要加上跟你用途相關的額外 context。所以值得測試你加的額外指示，最佳化清楚度和準確度。有問題嗎？看看[入門範例](https://platform.openai.com/docs/actions/getting-started)，了解這個步驟的更多細節。


```python
*** Context *** 

You are an office helper who takes a look at files within Google Drive and reads in information.  In this way, when asked about something, please take a look at all of the relevant information within the drive.  Respect file names, but also take a look at each document and sheet.

*** Instructions ***

Use the 'listFiles' function to get a list of files available within docs.  In this way, determine out of this list which files make the most sense for you to pull back taking into account name and title.  After the output of listFiles is called into context, act like a normal business analyst.  Things you could be asked to be are:

- Summaries: what happens in a given file?  Please give a consistent, concise answer and read through the entire file before giving an answer.
- Professionalism: Behave professionally, providing clear and concise responses.
- Synthesis, Coding, and Data Analysis: ensure coding blocks are explained.
- When handling dates: make sure that dates are searched using date fields and also if you don't find anything, use titles.
- Clarification: Ask for clarification when needed to ensure accuracy and completeness in fulfilling user requests.  Try to make sure you know exactly what is being asked. 
- Privacy and Security: Respect user privacy and handle all data securely.

*** Examples of Documentation ***
Here is the relevant query documentation from Google for the listFiles function:
What you want to query	Example
Files with the name "hello"	name = 'hello'
Files with a name containing the words "hello" and "goodbye"	name contains 'hello' and name contains 'goodbye'
Files with a name that does not contain the word "hello"	not name contains 'hello'
Folders that are Google apps or have the folder MIME type	mimeType = 'application/vnd.google-apps.folder'
Files that are not folders	mimeType != 'application/vnd.google-apps.folder'
Files that contain the text "important" and in the trash	fullText contains 'important' and trashed = true
Files that contain the word "hello"	fullText contains 'hello'
Files that do not have the word "hello"	not fullText contains 'hello'
Files that contain the exact phrase "hello world"	fullText contains '"hello world"'
Files with a query that contains the "\" character (e.g., "\authors")	fullText contains '\\authors'
Files with ID within a collection, e.g. parents collection	'1234567' in parents
Files in an application data folder in a collection	'appDataFolder' in parents
Files for which user "test@example.org" has write permission	'test@example.org' in writers
Files for which members of the group "group@example.org" have write permission	'group@example.org' in writers
Files modified after a given date	modifiedTime > '2012-06-04T12:00:00' // default time zone is UTC
Files shared with the authorized user with "hello" in the name	sharedWithMe and name contains 'hello'
Files that have not been shared with anyone or domains (only private, or shared with specific users or groups)	visibility = 'limited'
Image or video files modified after a specific date	modifiedTime > '2012-06-04T12:00:00' and (mimeType contains 'image/' or mimeType contains 'video/')
```

### **OpenAPI Schema 範例**

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。這是你的 GPT 可以包含哪些 function 的範例。

有問題嗎？看看[入門範例](https://platform.openai.com/docs/getting-started)，了解這個步驟的更多細節。也可以試試 [ActionsGPT](https://chatgpt.com/g/g-TYEliDU6A-actionsgpt)，這是 OpenAI 做的、幫忙處理 Actions 的 CustomGPT。三個範例是：


* **List Files**：這是列出你雲端硬碟裡檔案的核心 action。裡面有幾個參數，例如 `q`、`includeItemsFromAllDrives,supportsAllDrives`
* **Get Metadata**：萬一 list 不管用，可以依特定結果當備案。例如使用者想用「上週的會議」這類說法搜尋時
* **Export**：以位元組內容匯出。想多了解，請參考 [https://developers.google.com/drive/api/reference/rest/v3/files/export](https://developers.google.com/drive/api/reference/rest/v3/files/export)

一般來說，如果用 ‘get’，模型會嘗試下載檔案，這可能不是你要的。所以建議改用 Export。



```python

{
  "openapi": "3.1.0",
  "info": {
    "title": "Google Drive API",
    "description": "API for interacting with Google Drive",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://www.googleapis.com/drive/v3"
    }
  ],
  "paths": {
    "/files": {
      "get": {
        "operationId": "ListFiles",
        "summary": "List files",
        "description": "Retrieve a list of files in the user's Google Drive.",
        "parameters": [
          {
            "name": "q",
            "in": "query",
            "description": "Query string for searching files.",
            "required": false,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "includeItemsFromAllDrives",
            "in": "query",
            "description": "Whether both My Drive and shared drive items should be included in results.",
            "required": false,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "supportsAllDrives",
            "in": "query",
            "description": "Whether the requesting application supports both My Drives and shared drives.",
            "required": false,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "pageSize",
            "in": "query",
            "description": "Maximum number of files to return.",
            "required": false,
            "schema": {
              "type": "integer",
              "default": 10
            }
          },
          {
            "name": "pageToken",
            "in": "query",
            "description": "Token for continuing a previous list request.",
            "required": false,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "fields",
            "in": "query",
            "description": "Comma-separated list of fields to include in the response.",
            "required": false,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "A list of files.",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "kind": {
                      "type": "string",
                      "example": "drive#fileList"
                    },
                    "nextPageToken": {
                      "type": "string",
                      "description": "Token to retrieve the next page of results."
                    },
                    "files": {
                      "type": "array",
                      "items": {
                        "type": "object",
                        "properties": {
                          "id": {
                            "type": "string"
                          },
                          "name": {
                            "type": "string"
                          },
                          "mimeType": {
                            "type": "string"
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/files/{fileId}": {
      "get": {
        "operationId": "getMetadata",
        "summary": "Get file metadata",
        "description": "Retrieve metadata for a specific file.",
        "parameters": [
          {
            "name": "fileId",
            "in": "path",
            "description": "ID of the file to retrieve.",
            "required": true,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "fields",
            "in": "query",
            "description": "Comma-separated list of fields to include in the response.",
            "required": false,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "Metadata of the file.",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "id": {
                      "type": "string"
                    },
                    "name": {
                      "type": "string"
                    },
                    "mimeType": {
                      "type": "string"
                    },
                    "description": {
                      "type": "string"
                    },
                    "createdTime": {
                      "type": "string",
                      "format": "date-time"
                    }
                  }
                }
              }
            }
          }
        }
      }
    },
    "/files/{fileId}/export": {
      "get": {
        "operationId": "export",
        "summary": "Export a file",
        "description": "Export a Google Doc to the requested MIME type.",
        "parameters": [
          {
            "name": "fileId",
            "in": "path",
            "description": "ID of the file to export.",
            "required": true,
            "schema": {
              "type": "string"
            }
          },
          {
            "name": "mimeType",
            "in": "query",
            "description": "The MIME type of the format to export to.",
            "required": true,
            "schema": {
              "type": "string",
              "enum": [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain"
              ]
            }
          }
        ],
        "responses": {
          "200": {
            "description": "The exported file.",
            "content": {
              "application/pdf": {
                "schema": {
                  "type": "string",
                  "format": "binary"
                }
              },
              "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
                "schema": {
                  "type": "string",
                  "format": "binary"
                }
              },
              "text/plain": {
                "schema": {
                  "type": "string",
                  "format": "binary"
                }
              }
            }
          },
          "400": {
            "description": "Invalid MIME type or file ID."
          },
          "404": {
            "description": "File not found."
          }
        }
      }
    }
  }
}
```

## **驗證設定說明**

下面是設定這個第三方應用驗證的說明。有問題嗎？看看[入門範例](https://platform.openai.com/docs/actions/getting-started)，了解這個步驟的更多細節。


### **Action 之前的步驟**

在 ChatGPT 設定驗證之前，先在應用那邊做下面的步驟。



* 前往 Google Cloud Console
* 進入 Enabled API & Services，啟用 Google Drive API


![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_api_services_pin.png "api_and_services")

![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_nav_to_enabled_api.png "api_lib")


* 在搜尋列裡搜尋 Google Drive API：

![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_search_google_drive_api.png "gpt_actions")


* 建立新的 OAuth 憑證（或用現有的）。注意，如果你還沒設定 OAuth 同意畫面，就需要先設定。


![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_oauth_consent_screen.png "oauth_consent")




* 這個過程中，你需要授予正確的權限，如果啟用了 Testing，要把主要測試者設成測試用的 email，並設定 OAuth 的速率限制。
* 接著前往 credentials，點 “+ Create Credentials”，再點 “Create Credentials”。下面是這個畫面已經設定好時的樣子。


![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_go_to_create_credentials.png "creds")




* 找到你的 OAuth Client ID 和 Client Secret，並安全地保存這兩個值（見下方截圖）



![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_oauthcid_and_csecret.png "id and secret")



### **在 ChatGPT 裡**

在 ChatGPT 裡，點 "Authentication"，選 **"OAuth"**，填入下面的資訊。

* **Client ID**：用上面步驟拿到的 Client ID
* **Client Secret**：用上面步驟拿到的 Client Secret
* **Authorization URL**：[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)
* **Token URL**：[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)
* **Scope**：[https://www.googleapis.com/auth/drive](https://www.googleapis.com/auth/drive.readonly)
    * **注意**：要看已啟用的更詳細 scope 清單，請參考 [Google 的 OAuth 2.0 指南](https://developers.google.com/identity/protocols/oauth2/scopes)
* **Token**：預設（POST）
* **Privacy Policy**：[https://policies.google.com/privacy?hl=en-US](https://policies.google.com/privacy?hl=en-US)


### **Action 之後的步驟**

在 ChatGPT 設定好驗證之後，照下面的步驟在應用那邊完成這個 Action。



* 從 GPT Action 複製 callback URL


![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_callbackurl_from_gpt_action.png "callback")




* 在 “Authorized redirect URIs” 裡加入你的 callback URL


![alt_text](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_gd_authorized_redirect_uris.png "image_tooltip")



### **常見問題與疑難排解**



* _Callback URL 錯誤：_ 如果在 ChatGPT 裡遇到 callback URL 錯誤，仔細看上面的截圖。你需要把 callback URL 直接加到 GCP，action 才能正確驗證。

_有沒有想要我們優先處理的整合？我們的整合有錯誤嗎？到我們的 GitHub 提 PR 或 issue，我們會看看。_




<!-- watermark --><div style="background-color:#FFFFFF"><p style="color:#FFFFFF; font-size: 1px">gd2md-html: xyzzy Mon Aug 12 2024</p></div>


## 重點整理

- GPT Action 是由三塊組成：Instructions 告訴 GPT 怎麼用，OpenAPI schema 定義有哪些 function，OAuth 設定負責授權。
- 列檔用 List Files，List 不行時用 Get Metadata 當備案，取內容用 Export，因為 get 會讓模型嘗試下載檔案。
- 這組 action 適合讀會議記錄、設計文件這類小檔案，長文件或大型表格建議做專門的 Docs 或 Sheets GPT。
- OAuth 要兩邊對接：Google Cloud 給 Client ID 和 Secret，ChatGPT 給 callback URL，要回填到 Authorized redirect URIs。

## 練習

1. 把 OAuth 的 Scope 改成唯讀範圍，確認 GPT 還能列出和匯出檔案。
2. 在 Instructions 裡加一句，要求回答時一律列出參考的檔名，再問一個問題看看效果。
3. 參考 Google Drive API 文件，在 OpenAPI schema 裡新增一個 action（例如依資料夾列檔），並在 Instructions 說明什麼時候該用它。
