---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_box.ipynb
---

# GPT Actions 範例庫：Box

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_box.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_box.ipynb)



## 這篇在做什麼
教你把 ChatGPT 接到 Box.com 帳號。Custom GPT 用兩個 action：一個直接呼叫 Box API 查資料，另一個是 Azure Function，負責把 Box 的回應整理成 ChatGPT 能下載、讀取檔案內容的格式。

## 學完你會
- 在 Box 建立 OAuth 2.0 的 custom app，並把 Client ID、Secret 和 redirect URI 跟 ChatGPT 對起來
- 在 Custom GPT 裡貼上 instructions 和 OpenAPI schema，設定 Box API action
- 部署 Azure Function 當 middleware，讓 GPT 讀得到檔案內容，不只是檔案的 metadata

## 開跑前
- Box developer 帳號，以及一個 OAuth 2.0 的 custom app
- Azure Portal 權限，要能建立 Function App 和 Entra App Registration
- 能建立 Custom GPT 和 Actions 的 ChatGPT 帳號

## 簡介

這頁是給開發者的教學，說明怎麼為特定應用程式做 GPT Action。開始之前，請先看過下面這些資料：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這份指南說明怎麼把 ChatGPT 連到 Box.com 帳號。這個 GPT 用兩個 action 從 Box 拉資料。它直接跟 Box API 互動，但需要像 Azure Function 這樣的 middleware 來整理回應格式，ChatGPT 才能下載並讀取檔案內容。Azure Function 這個 action 對使用者是透明的，使用者不用明確去呼叫它。

- Action 1：Box API action，用 Box API 查詢 Box 裡的資料
- Action 2：Azure Function，整理 Box 的回應，讓 ChatGPT 可以直接從 Box 下載檔案

### 價值與商業使用情境

現有的 Box 客戶可以照這些指引，查詢檔案細節、檔案內容和相關 metadata。這樣就能用 OpenAI 分析 Box 裡的任何內容，例如把資料集視覺化、跨多個資料夾和檔案做摘要。這個 GPT 可以存取資料夾、檔案，以及 Box 裡 metadata 這類業務流程資料。另外，Box 管理員也能用這個 GPT action 查看稽核紀錄和健康檢查。

## 應用程式資訊

### 重要連結

開始之前，先看看 Box 和 Azure 的這些連結：

**Box Action**
- Application Website: https://app.box.com 
- Application API Documentation: https://developer.box.com/reference/

</br>

**Azure Function**
- Application Website: https://learn.microsoft.com/en-us/azure/azure-functions/
- Application API Documentation: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference/
 

### 應用程式前置條件

開始之前，要先在 Box 環境完成下面這些步驟：
- 需要 Box developer 帳號才能開始：https://developer.box.com/
- 照 Box Developer 網站的說明，建立 OAuth 2.0 驗證類型的 custom app：https://developer.box.com/guides/getting-started/first-application/  
- 到 **Configuration** 分頁取得下面這些值
    - OAuth 2.0 憑證（**Client ID** / **Client Secret**），這兩個值都要填進 ChatGPT 的設定
    - OAuth 2.0 **Redirect URIs**：這個值要等 ChatGPT action 設定好之後再回來填
    - Application scopes（**Read all files and folders in Box**、**Manage Enterprise properties**） 

這個視窗先不要關，Redirect URIs 要從 GPT 的設定複製過來填。



![gpt_actions_box_boxconfig1.png.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_box_boxconfig1.png)

</br>


### Middleware 資訊：Action 2 需要

在 Azure 環境要先完成這些：
- 有權限建立 Azure Function App 和 Azure Entra App Registration 的 Azure Portal
- 這份指南後面有一個詳細的段落，講怎麼部署和設計這個 function，用來包裝 Box 的回應，才看得到檔案內容。沒有這個 function，GPT 只能查檔案的資料，看不到內容。建完第一個 action 之後，記得讀那個段落。


## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
**context** 

This GPT will connect to your Box.com account to search files and folders, providing accurate and helpful responses based on the user's queries. It will assist with finding, organizing, and retrieving information stored in Box.com. Ensure secure and private handling of any accessed data. Avoid performing any actions that could modify or delete files unless explicitly instructed. Prioritize clarity and efficiency in responses. Use simple language for ease of understanding. Ask for clarification if a request is ambiguous or if additional details are needed to perform a search. Maintain a professional and friendly tone, ensuring users feel comfortable and supported.


Please use this website for instructions using the box API : https://developer.box.com/reference/ each endpoint can be found from this reference documentation

Users can search with the Box search endpoint or Box metadata search endpoint

**instructions**
When retrieving file information from Box provide as much details as possible and format into a table when more than one file is returned, include the modified date, created date and any other headers you might find valuable

Provide insights to files and suggest patterns for users, gives example queries and suggestions when appropriate

When a user wants to compare files retrieve the file for the user with out asking
```

### Action 1：Box API Action

建好 Custom GPT 之後，需要建立 2 個 action。把下面的文字複製到第 1 個 Actions 面板，這個是 Box action。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
{
  "openapi": "3.1.0",
  "info": {
    "title": "Box.com API",
    "description": "API for Box.com services",
    "version": "v1.0.0"
  },
  "servers": [
    {
      "url": "https://api.box.com/2.0"
    }
  ],
  "paths": {
    "/folders/{folder_id}": {
      "get": {
        "summary": "Get Folder Items",
        "operationId": "getFolderItems",
        "parameters": [
          {
            "name": "folder_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "The ID of the folder"
          }
        ],
        "responses": {
          "200": {
            "description": "A list of items in the folder",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/FolderItems"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:folders"
            ]
          }
        ]
      }
    },
    "/files/{file_id}": {
      "get": {
        "summary": "Get File Information",
        "operationId": "getFileInfo",
        "parameters": [
          {
            "name": "file_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "The ID of the file"
          }
        ],
        "responses": {
          "200": {
            "description": "File information",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/FileInfo"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:files"
            ]
          }
        ]
      }
    },
    "/folders": {
      "get": {
        "summary": "List All Folders",
        "operationId": "listAllFolders",
        "responses": {
          "200": {
            "description": "A list of all folders",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/FoldersList"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:folders"
            ]
          }
        ]
      }
    },
    "/events": {
      "get": {
        "summary": "Get User Events",
        "operationId": "getUserEvents",
        "parameters": [
          {
            "name": "stream_type",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "The type of stream"
          }
        ],
        "responses": {
          "200": {
            "description": "User events",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/UserEvents"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:events"
            ]
          }
        ]
      }
    },
    "/admin_events": {
      "get": {
        "summary": "Get Admin Events",
        "operationId": "getAdminEvents",
        "responses": {
          "200": {
            "description": "Admin events",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/AdminEvents"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:events"
            ]
          }
        ]
      }
    },
    "/search": {
      "get": {
        "summary": "Search",
        "operationId": "search",
        "parameters": [
          {
            "name": "query",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "Search query"
          }
        ],
        "responses": {
          "200": {
            "description": "Search results",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/SearchResults"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "search:items"
            ]
          }
        ]
      }
    },
    "/metadata_templates": {
      "get": {
        "summary": "Get Metadata Templates",
        "operationId": "getMetadataTemplates",
        "responses": {
          "200": {
            "description": "Metadata templates",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MetadataTemplates"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:metadata_templates"
            ]
          }
        ]
      }
    },
    "/metadata_templates/enterprise": {
      "get": {
        "summary": "Get Enterprise Metadata Templates",
        "operationId": "getEnterpriseMetadataTemplates",
        "responses": {
          "200": {
            "description": "Enterprise metadata templates",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MetadataTemplates"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:metadata_templates"
            ]
          }
        ]
      }
    },
    "/files/{file_id}/metadata": {
      "get": {
        "summary": "Get All Metadata for a File",
        "operationId": "getAllMetadataForFile",
        "parameters": [
          {
            "name": "file_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "The ID of the file"
          }
        ],
        "responses": {
          "200": {
            "description": "All metadata instances for the file",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/MetadataInstances"
                }
              }
            }
          }
        },
        "security": [
          {
            "OAuth2": [
              "read:metadata"
            ]
          }
        ]
      }
    }
  },
  "components": {
    "schemas": {
      "FolderItems": {
        "type": "object",
        "properties": {
          "total_count": {
            "type": "integer",
            "description": "The total number of items in the folder"
          },
          "entries": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "description": "The type of the item (e.g., file, folder)"
                },
                "id": {
                  "type": "string",
                  "description": "The ID of the item"
                },
                "name": {
                  "type": "string",
                  "description": "The name of the item"
                }
              }
            }
          }
        }
      },
      "FileInfo": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "The ID of the file"
          },
          "name": {
            "type": "string",
            "description": "The name of the file"
          },
          "size": {
            "type": "integer",
            "description": "The size of the file in bytes"
          },
          "created_at": {
            "type": "string",
            "format": "date-time",
            "description": "The creation time of the file"
          },
          "modified_at": {
            "type": "string",
            "format": "date-time",
            "description": "The last modification time of the file"
          }
        }
      },
      "FoldersList": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {
              "type": "string",
              "description": "The ID of the folder"
            },
            "name": {
              "type": "string",
              "description": "The name of the folder"
            }
          }
        }
      },
      "UserEvents": {
        "type": "object",
        "properties": {
          "entries": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "event_id": {
                  "type": "string",
                  "description": "The ID of the event"
                },
                "event_type": {
                  "type": "string",
                  "description": "The type of the event"
                },
                "created_at": {
                  "type": "string",
                  "format": "date-time",
                  "description": "The time the event occurred"
                }
              }
            }
          }
        }
      },
      "AdminEvents": {
        "type": "object",
        "properties": {
          "entries": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "event_id": {
                  "type": "string",
                  "description": "The ID of the event"
                },
                "event_type": {
                  "type": "string",
                  "description": "The type of the event"
                },
                "created_at": {
                  "type": "string",
                  "format": "date-time",
                  "description": "The time the event occurred"
                }
              }
            }
          }
        }
      },
      "SearchResults": {
        "type": "object",
        "properties": {
          "total_count": {
            "type": "integer",
            "description": "The total number of search results"
          },
          "entries": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "type": {
                  "type": "string",
                  "description": "The type of the item (e.g., file, folder)"
                },
                "id": {
                  "type": "string",
                  "description": "The ID of the item"
                },
                "name": {
                  "type": "string",
                  "description": "The name of the item"
                }
              }
            }
          }
        }
      },
      "MetadataTemplates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "templateKey": {
              "type": "string",
              "description": "The key of the metadata template"
            },
            "displayName": {
              "type": "string",
              "description": "The display name of the metadata template"
            },
            "scope": {
              "type": "string",
              "description": "The scope of the metadata template"
            }
          }
        }
      },
      "MetadataInstances": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "templateKey": {
              "type": "string",
              "description": "The key of the metadata template"
            },
            "type": {
              "type": "string",
              "description": "The type of the metadata instance"
            },
            "attributes": {
              "type": "object",
              "additionalProperties": {
                "type": "string"
              },
              "description": "Attributes of the metadata instance"
            }
          }
        }
      }
    },
    "securitySchemes": {
      "OAuth2": {
        "type": "oauth2",
        "flows": {
          "authorizationCode": {
            "authorizationUrl": "https://account.box.com/api/oauth2/authorize",
            "tokenUrl": "https://api.box.com/oauth2/token",
            "scopes": {
              "read:folders": "Read folders",
              "read:files": "Read files",
              "search:items": "Search items",
              "read:metadata": "Read metadata",
              "read:metadata_templates": "Read metadata templates",
              "read:events": "Read events"
            }
          }
        }
      }
    }
  }
}
```

**注意：上面的 schema 沒有包含所有可能的 API endpoint，記得照 [Box Developer documentation](https://developer.box.com) 修改 schema，產生你需要的 action。**

## 驗證設定

下面是跟這個第三方應用程式設定驗證的步驟。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

### 在 ChatGPT 裡

在 ChatGPT 點 "Authentication"，選 OAuth 


<br> ![gptactions_box_gptauth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_box_gptauth.png)

**OAuth 連線**

- Client ID：前面建立的 Box custom app 的值
- Client Secret：前面建立的 Box custom app 的值 
- Authorization URL：https://account.box.com/api/oauth2/authorize?response_type=code&client_id=[client ID from above]&redirect_uri=[use a placeholder like chat.openai.com/aip//oauth/callback for now, you’ll update this later when you create the Action in ChatGPT]
- Token URL：https:api.box.com/oauth2/token
</br>
</br>
你要先儲存設定，再回到 GPT 的 Configuration 分頁複製 Callback URL，然後編輯 Box action 的 Authorization URL，格式改成 https://account.box.com/api/oauth2/authorize?response_type=code&client_id=[client_ID]&redirect_uri=[callBack URL]

### Action 設定後的步驟

更新 Box.com 的 custom application
</br>
- 從 GPT 複製 CallBack URL，到 Box.com 加上一筆 OAuth 2.0 Redirect URIs
</br>
</br>
![gpt_actions_box_boxconfig1.png.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_box_boxconfig1.png)

</br>


### Action 2：Azure Function

現在 GPT 已經建好，也能對 Box.com 做驗證了，接下來可以建立 Azure Function 來處理回應格式，讓 GPT 能從 Box 下載檔案。 

部署 Azure Function 的細節，請看這份 [Azure Cookbook Guide](https://cookbook.openai.com/examples/azure/functions)。下面是要加進 function 的範例程式碼。 

這段程式碼只是示意用，雖然應該可以直接跑，但設計上是讓你依需求客製化。</br>

</br>

**資料流程**

![gpt_actions_box_azureflow.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_box_azuredataflow.png)

</br></br>



Azure function 建好之後，加入下面的範例程式碼：

function_app.py

```python
import azure.functions as func
from boxsdk import Client, JWTAuth

import requests
import base64
import json
import jwt
import logging

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@app.route(route="box_retrieval")
def box_retrieval(req: func.HttpRequest) -> func.HttpResponse:
    logger.info('Starting box_retrieval function')
    file_ids = req.params.get('file_ids')
    auth_header = req.headers.get('Authorization')

    if not file_ids or not auth_header:
        logger.error('Missing file_ids or Authorization header')
        return func.HttpResponse(
            "Missing file_id or Authorization header.",
            status_code=400
        )
    
    file_ids = file_ids.split(",")  # Assuming file_ids are passed as a comma-separated string
    if len(file_ids) == 0 or len(file_ids) > 10:
        logger.error('file_ids list is empty or contains more than 10 IDs')
        return func.HttpResponse(
            "file_ids list is empty or contains more than 10 IDs.",
            status_code=400
        )

    try:
        # Decode JWT to extract the email
        token = auth_header.split(" ")[1]
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        upn = decoded_token['upn']
        user_email = get_user_mapping(upn)
        logger.info(f'User email extracted: {user_email}')

        config = JWTAuth.from_settings_file('jwt_config.json')
        sdk = Client(config)
        logger.info('Authenticated with Box API')

        # Use the user email to get the user ID
        users = sdk.users(filter_term=user_email)
        user = next(users)
        user_id = user.id
        logger.info(f'User ID obtained: {user_id}')

        openai_file_responses = []
        for file_id in file_ids:
            # Perform as_user call to get the file representation
            my_file = sdk.as_user(user).file(file_id).get()
            file_url = my_file.get_download_url()
            openai_file_responses.append(file_url)
        
        response_body = json.dumps({'openaiFileResponse': openai_file_responses})

        return func.HttpResponse(
            response_body,
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        return func.HttpResponse(
            f"An error occurred: {str(e)}",
            status_code=500
        )
    
def get_user_mapping(upn):
    # In our case, the user's authentication email into Azure AD is the same as their email in Box
    # If that is not the case, map the email in Box to the email in Azure AD
    return upn
```

jwt_config.json.sample

```python
{
    "boxAppSettings": {
      "clientID": "12345",
      "clientSecret": "abcde",
      "appAuth": {
        "publicKeyID": "123",
        "privateKey": "-----BEGIN ENCRYPTED PRIVATE KEY-----\nvwxyz==\n-----END ENCRYPTED PRIVATE KEY-----\n",
        "passphrase": "lmnop"
      }
    },
    "enterpriseID": "09876"
  }
```

requirements.txt

```python
boxsdk[jwt]
azure-functions
requests
pyjwt
```

記得照 Azure 指南做完剩下的驗證後步驟和 ChatGPT 設定：[Azure Cookbook Guide](https://cookbook.openai.com/examples/azure/functions)

### FAQ 與疑難排解

- *Schema 呼叫到錯的 project 或 dataset：* 如果 ChatGPT 呼叫到錯的 project 或 dataset，可以修改 instructions，寫得更明確：(a) 該呼叫哪個 project / dataset，或 (b) 要求使用者在執行查詢前先提供這些確切資訊
- Box 可能在 event stream 裡回傳大量資料，這會造成錯誤。 

*有沒有哪些整合你希望我們優先做？我們的整合有錯誤嗎？歡迎到我們的 github 提 PR 或 issue，我們會處理。*


## 重點整理
- 這個整合由兩個 action 組成：Box API action 查資料，Azure Function 負責讓檔案內容可被下載讀取
- 沒有 middleware 的話，GPT 只能查到檔案的 metadata，讀不到內容
- OAuth 設定要在 ChatGPT 和 Box 之間來回一趟：先用暫時的 redirect URI，儲存後再把正式的 Callback URL 填回兩邊
- 範例 schema 只涵蓋部分 endpoint，要依需求照 Box 文件擴充
- GPT 呼叫錯的 project 或 dataset 時，改 instructions 讓範圍更明確

## 練習
1. 在 Custom GPT 的 instructions 裡，加一句限制，讓 GPT 只在指定的 Box 資料夾下查詢。
2. 在 Box action 的 schema 裡，照 Box 文件新增一個 endpoint（例如取得資料夾內容的 endpoint），然後在 GPT 裡測試它會不會用到。
3. 修改 `function_app.py`，讓它在檔案太大時回傳明確的錯誤訊息，而不是整份送出去。
