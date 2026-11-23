---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_googleads_adzviser.ipynb
---

# GPT Actions 範例庫：透過 Adzviser 連 Google Ads

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_googleads_adzviser.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_googleads_adzviser.ipynb)



## 這篇在做什麼
示範怎麼用 Adzviser 當中介，把 Google Ads 的報表資料（曝光、點擊、花費等）接到 ChatGPT。你用自然語言問問題，Adzviser 會去查 Google Ads，把結果轉成 CSV 回傳給 ChatGPT 的 Data Analysis 分析。

## 學完你會
- 了解 Adzviser 怎麼把 Google Ads Query Language 的結果轉成 CSV 並回傳給 GPT。
- 把 Custom GPT 的 Instructions 和 OpenAPI schema 設好，讓 GPT 能查 campaign、ad group、ad 層級的指標。
- 用 Adzviser 提供的 URL 在 ChatGPT 設好 OAuth，並排解 Google Ads 帳號清單是空的問題。

## 開跑前
- 需要一個 Google Ads 帳號，且有唯讀、Standard 或 Admin 權限。
- 需要註冊 Adzviser 並啟用訂閱（$0.99 起），並建立 workspace 連接 Google Ads 帳號。

## 簡介

這一頁是給開發者的說明，教你替特定應用程式做 GPT Action。開始之前，建議先看過下面這些資料：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零打造 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這份指南說明怎麼把 **Google Ads** 的報表資料接到 ChatGPT，取得 campaign、ad group 或 ad 層級的曝光、點擊和花費等關鍵績效指標。為了簡化流程，你會用 [Adzviser](https://adzviser.com) 當中介，確保 Google Ads API 回傳的資料格式正確，可以直接在 ChatGPT 的 [Data Analysis](https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt) 環境分析。

**Adzviser 的運作方式：** 首先，透過 [OAuth](https://docs.adzviser.com/getStarted/workspace) 把你的 Google Ads 帳號連到 [Adzviser](https://adzviser.com/set-up)。當你在 ChatGPT 問「上個月每個 campaign 花了多少？」這類問題，Adzviser 會送出 [Google Ads Query Language](https://developers.google.com/google-ads/api/docs/query/overview) 請求，並把回應轉成 CSV 檔（小於 10MB）。這個檔案接著會[回傳給 ChatGPT](https://platform.openai.com/docs/actions/sending-files/returning-files) 做分析。有了 Adzviser，你可以輕鬆檢視和分析 campaign 的表現，同時根據歷史資料的洞察一起想優化策略。


### 價值與商業情境範例

**價值**：Google Ads 行銷人員現在可以用 ChatGPT 的自然語言能力，輕鬆查詢績效指標和帳號設定，不用進 Google Ads 介面操作。整個過程不需要上傳或下載任何檔案。

**情境範例**： 
- 電商老闆想快速查看 Google Ads campaign 上個月的廣告投資報酬率（ROAS）
- 品牌行銷人員想用過去 3 個月的報表資料做關鍵字和搜尋字詞分析，找出哪些關鍵字該暫停或加碼，哪些搜尋字詞該加入否定關鍵字。
- 代理商行銷人員需要產生月報，包含每次點擊費用（CPC）、每次轉換費用（CPA）、搜尋曝光占比等關鍵指標，並做月對月比較。
- 自由工作者在接新客戶時，需要稽核對方的 Google Ads 帳號，評估績效並找出優化機會。

## Demo / 範例

![GPT Search Term Analysis Part 1](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_googleads_search_term_analysis_1.png)![GPT Search Term Analysis Part 2](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_googleads_search_term_analysis_2.png)

## 應用程式資訊

### 應用程式重要連結

開始前先看看這些連結：
- 如何在 Adzviser 建立 workspace：https://docs.adzviser.com/getStarted/workspace
- Adzviser Custom GPT 文件：https://docs.adzviser.com/chatgpt/expert
- Google Ads prompt 範本庫：https://docs.adzviser.com/chatgpt/googleAdsPromptTemplates

### 應用程式前置條件

開始前，請先在應用程式環境完成下面的事：
- 確認你對某個 Google Ads 帳號有[唯讀、Standard 或 Admin 權限](https://support.google.com/google-ads/answer/9978556?hl=en)。
- 在 Adzviser [註冊](https://adzviser.com/signup)帳號並啟用訂閱（$0.99 起）。
- 建立 workspace，把你的 Google Ads 帳號連到 Adzviser

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有疑問可以看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
***Context***:
You are a Google Ads specialist who audits account health, retrieves real-time reporting data, and optimizes performances for marketers. When asked for an audit on account health, collect the relevant account settings, provide recommendations to adjust account structures. When asked about reporting data insights, gather relevant metrics and breakdowns, thoroughly analyze the reporting data, and then provide tailored recommendations to optimize performance.

***Instructions for Retrieval of Reporting Data***:
- Workflow to fetch real-time reporting data
Step 1. Calculate the date range with Python and Code Interpreter based on user input, such as "last week", "last month", "yesterday", "last 28 days", "last quarter" or "last year" etc. If no specific timeframe is provided, ask the user to clarify. Adjust for calendar variations. For example, "last week" should cover Monday to Sunday of the previous week. 
Step 2. Retrieve workspace information using the 'getWorkspace' function. 
Step 3. Fetch the relevant metrics and breakdowns for the inquired data source using functions like 'getGoogleAdsMetricsList' and 'getGoogleAdsBreakdownsList'.
Step 4. Use 'searchQuery' function with the data gathered from the previous steps like available workspace_name and metrics/breakdowns as well as calculated date range to retrieve real-time reporting data.
- Time Granularity: If the user asks for daily/weekly/quarterly/monthly data, please reflect such info in the field time_granularity in searchQueryRequest. No need to add time_granularity if the user did not ask for it explicitly.
- Returned Files: If multiple files are returned, make sure to read all of them. Each file contains data from a segment in a data source or a data source. 
- Necessary Breakdowns Only: Add important breakdowns only. Less is more. For example, if the user asks for "which ad is performing the best in Google Ads?", then you only add "Ad Name" in the breakdown list for the google_ads_request. No need to add breakdowns such as "Device" or "Campaign Name". 

***Instruction for Auditing****:
- Workflow to audit Google Ads account
Step 1. Retrieve workspace information using the 'getWorkspace' function.
Step 2. Use '/google_ads_audit/<specfic_section_to_check>' function to retrieve account settings.
- Comprehensive Audit: When asked for an comprehensive audit, don't call all the /google_ads_audit/<specfic_section_to_check> all at once. Show the users what you're planning to do next first. Then audit two sections from the Google Ads Audit GPT Knowledge at a time, then proceed to the next two sections following users consent. For the line items in the tables in the Audit Knowledge doc that don't have automation enabled, it is very normal and expected that no relevant data is seen in the retrieved response. Please highlight what needs to be checked by the user manually because these non-automated steps are important too. For example, when checking connections, adzviser only checks if the google ads account is connected with Google Merchant Center. For other connections such as YT channels, please politely ask the user to check them manually. 

***Additional Notes***:
- Always calculate the date range please with Code Interpreter and Python. It often is the case that you get the date range 1 year before when the user asks for last week, last month, etc. 
- If there is an ApiSyntaxError: Could not parse API call kwargs as JSON, please politely tell the user that this is due to the recent update in OpenAI models and it can be solved by starting a new conversation on ChatGPT.
- If the users asks for Google Ads data, for example, and there is only one workspace that has connected to Google Ads, then use this workspace name in the searchQueryRequest or googleAdsAuditRequest.
- During auditing, part of the process is to retrieve the performance metrics at account, campaign, ad group, keyword, and product levels, remember to also run Python to calculate the date range for last month and the previous period. For retrieving performance metrics at these 5 levels, please send 5 distinct requests with different breakdowns list for each level. More can be found in the audit knowledge doc.
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有疑問可以看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
{
  "openapi": "3.1.0",
  "info": {
    "title": "Adzviser Actions for GPT",
    "description": "Equip GPTs with the ability to retrieve real-time reporting data and account settings from Google Ads",
    "version": "v0.0.1"
  },
  "servers": [
    {
      "url": "https://copter.adzviser.com"
    }
  ],
  "paths": {
    "/google_ads/get_metrics_list": {
      "get": {
        "description": "Get the list of seletable Google Ads metrics, such as Cost, Roas, Impressions, etc.",
        "operationId": "getGoogleAdsMetricsList",
        "parameters": [],
        "deprecated": false,
        "security": [],
        "x-openai-isConsequential": false
      }
    },
    "/google_ads/get_breakdowns_list": {
      "get": {
        "description": "Get the list of seletable Google Ads breakdowns such as Device, Keyword Text, Campaign Name etc.",
        "operationId": "getGoogleAdsBreakdownsList",
        "parameters": [],
        "deprecated": false,
        "security": [],
        "x-openai-isConsequential": false
      }
    },
    "/search_bar": {
      "post": {
        "description": "Retrieve real-time reporting data such as impressions, cpc, etc. from marketing channels such as Google Ads, Fb Ads, Fb Insights, Bing Ads, etc.",
        "operationId": "searchQuery",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/searchQueryRequest"
              }
            }
          },
          "required": true
        },
        "deprecated": false,
        "security": [
          {
            "oauth2": []
          }
        ],
        "x-openai-isConsequential": false
      }
    },
    "/workspace/get": {
      "get": {
        "description": "Retrieve a list of workspaces that have been created by the user and their data sources, such as Google Ads, Facebook Ads accounts connected with each.",
        "operationId": "getWorkspace",
        "parameters": [],
        "deprecated": false,
        "security": [
          {
            "oauth2": []
          }
        ],
        "responses": {
          "200": {
            "description": "OK",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/getWorkspaceResponse"
                }
              }
            }
          }
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_merchant_center_connection": {
      "post": {
        "description": "Retrieve whether the Google Merchant Center is connected to the Google Ads account.",
        "operationId": "checkGoogleAdsMerchantCenterConnection",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_account_settings": {
      "post": {
        "description": "Retrieve the Google Ads account settings such as whether auto tagging is enabled, inventory type, etc.",
        "operationId": "checkGoogleAdsAccountSettings",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_negative_keywords_and_placements": {
      "post": {
        "description": "Retrieve the negative keywords and placements set in the Google Ads account.",
        "operationId": "checkGoogleAdsNegativeKeywordsAndPlacements",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_remarketing_list": {
      "post": {
        "description": "Retrieve the remarketing list set in the Google Ads account.",
        "operationId": "checkGoogleAdsRemarketingList",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_conversion_tracking": {
      "post": {
        "description": "Retrieve the conversion tracking status in the Google Ads account.",
        "operationId": "checkGoogleAdsConversionTracking",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_bidding_strategy": {
      "post": {
        "description": "Retrieve the bidding strategy set for each active campaigns in the Google Ads account.",
        "operationId": "checkGoogleAdsBiddingStrategy",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_search_campaign_basic": {
      "post": {
        "description": "Retrieve the basic information of the search campaigns such as campaign structure, language targeting, country targeting, etc.",
        "operationId": "checkSearchCampaignBasic",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_search_campaign_detailed": {
      "post": {
        "description": "Retrieve the detailed information of the search campaigns such as best performing keywords, ad copies, ad extentions, pinned descriptions/headlines etc.",
        "operationId": "checkSearchCampaignDetailed",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_dynamic_search_ads": {
      "post": {
        "description": "Retrieve the dynamic search ads information such as dynamic ad targets, negative ad targets, best performing search terms etc.",
        "operationId": "checkDynamicSearchAds",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    },
    "/google_ads_audit/check_pmax_campaign": {
      "post": {
        "description": "Retrieve the performance of the pmax campaigns such as search themes, country/language targeting, final url expansions, excluded urls.",
        "operationId": "checkPmaxCampaign",
        "parameters": [],
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "$ref": "#/components/schemas/googleAdsAuditRequest"
              }
            }
          },
          "required": true
        },
        "x-openai-isConsequential": false
      }
    }
  },
  "components": {
    "schemas": {
      "getWorkspaceResponse": {
        "title": "getWorkspaceResponse",
        "type": "array",
        "description": "The list of workspaces created by the user on adzviser.com/main. A workspace can include multiple data sources",
        "items": {
          "type": "object",
          "properties": {
            "name": {
              "title": "name",
              "type": "string",
              "description": "The name of a workspace"
            },
            "data_connections_accounts": {
              "title": "data_connections_accounts",
              "type": "array",
              "description": "The list of data sources that the workspace is connected. The name can be an account name and type can be Google Ads/Facebook Ads/Bing Ads",
              "items": {
                "type": "object",
                "properties": {
                  "name": {
                    "title": "name",
                    "type": "string",
                    "description": "The name of a data connection account"
                  }
                }
              }
            }
          }
        }
      },
      "googleAdsAuditRequest": {
        "description": "Contains details about the Google Ads account audit request.",
        "type": "object",
        "required": [
          "workspace_name"
        ],
        "title": "googleAdsAuditRequest",
        "properties": {
          "workspace_name": {
            "type": "string",
            "title": "workspace_name",
            "description": "Call API getWorkspace first to get a list of available workspaces"
          }
        }
      },
      "searchQueryRequest": {
        "description": "Contains details about queried data source, metrics, breakdowns, time ranges and time granularity, etc.",
        "type": "object",
        "required": [
          "assorted_requests",
          "workspace_name",
          "date_ranges"
        ],
        "title": "searchQueryRequest",
        "properties": {
          "assorted_requests": {
            "type": "object",
            "title": "assorted_requests",
            "description": "For example, if the user asks for \"cost on Google ads last month\", then call getGoogleAdsMetricsList and getGoogleAdsBreakdownsList to retrieve the latest up-to-date info about how to compose a google_ads_request. A metric is a quantitative measurement. It represents data that can be measured and expressed in numbers. Metrics are used to track performance or behavior. Examples include clicks, impressions, conversions, revenue, etc. A breakdown is a qualitative attribute or descriptor. It provides context for metrics by categorizing or segmenting them. Breakdowns are text. Examples include country, channel, campaign name, etc. DO NOT include Date, Month, Quarter or Year in the list of breakdowns in any of the requests below. The breakdowns should be NOT mixed up with metrics, meaning that the selected breakdowns should be passed into the property \"breakdowns\", not \"metrics\", and vice versa.",
            "properties": {
              "google_ads_request": {
                "type": "object",
                "description": "DO NOT come up with metrics and breakdowns on your own. You MUST call API getGoogleAdsMetricsList and getGoogleAdsBreakdownsList to be better informed prior of composing a googleAdsRequest.",
                "required": [
                  "metrics",
                  "breakdowns"
                ],
                "properties": {
                  "breakdowns": {
                    "type": "array",
                    "items": {
                      "type": "string"
                    },
                    "description": "Must call API getGoogleAdsBreakdownsList to retrieve a list of selectable breakdowns."
                  },
                  "metrics": {
                    "type": "array",
                    "items": {
                      "type": "string"
                    },
                    "description": "Must call API getGoogleAdsMetricsList to retrieve a list of selectable metrics."
                  }
                }
              }
            }
          },
          "workspace_name": {
            "type": "string",
            "title": "workspace_name",
            "description": "Call API getWorkspace first to get a list of available workspaces. Multiple data sources (such as Google ads, Bing ads) can be stored in one workspace. If the user does not specify a workspace name, then use the available workspace name from the retrieved list and see which one has Google Ads. If the user has not yet created one, then ask them to go to adzviser.com/main to create a new workspace."
          },
          "date_ranges": {
            "type": "array",
            "description": "A list of date ranges requested from the user. They needs to be calculated seperately with Code Interpreter and Python every single time for accuracy. For example, if the user requests \"Google Ads search impression share in May and August\", then this array should be [[\"2024-05-01\", \"2024-05-31\"], [\"2024-08-01\", \"2024-08-31\"]].",
            "items": {
              "type": "array",
              "items": {
                "type": "string"
              },
              "description": "A 2-element array. The first represents the start date and the second the end date. Both are in YYYY-MM-DD format."
            }
          },
          "time_granularity": {
            "type": "string",
            "title": "time_granularity",
            "default": "",
            "description": "Describes how granularity you wish the date_ranges to be. For example, If the user asks \"weekly cost on Google Ads\" this year, then this value should be \"Week\". If the user does not specify, then leave it as empty.",
            "enum": [
              "Date",
              "Week",
              "Month",
              "Quarter"
            ]
          }
        }
      }
    },
    "securitySchemes": {
      "oauth2": {
        "type": "oauth2"
      }
    }
  }
}
```

## 驗證設定說明

下面是跟這個第三方應用程式設定驗證的步驟。有疑問可以看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started)。

![GPT OAuth Settings](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_adzviser_oauth.png)

### 在 ChatGPT 裡設定

在 ChatGPT 點 "Authentication"，選 **"OAuth"**，填入下面的資訊。 

- **Client ID**：（留空）
- **Client Secret**：（留空）
- **Authorization URL**：https://adzviser.com/authorize-gpt
- **Token URL**：https://adzviser.com/api/oauth-exchange-token-gpt
- **Scope**：（留空）
- **Token Exchange Method**：Default (POST)

### FAQ 與疑難排解

- *Google Ads 帳號清單是空的*：如果連接 Google Ads 帳號時看到空的帳號清單，很可能是你的 Google Ads 帳號還沒命名。解法是到 ads.google.com 登入，再照[這裡](https://support.google.com/google-ads/answer/7519527?hl=en)的說明幫帳號命名。

*有想要我們優先支援的整合嗎？整合有錯誤嗎？歡迎到 GitHub 開 PR 或 issue，我們會看。*


## 重點整理
- Adzviser 是中介層：接 Google Ads API，把結果轉成小於 10MB 的 CSV，讓 ChatGPT 的 Data Analysis 直接讀。
- 使用者不用手動上傳或下載檔案，用自然語言問就好。
- 驗證走 OAuth，但 Client ID、Secret 和 Scope 都留空，授權流程由 Adzviser 的兩個 URL 處理。
- 帳號清單空的，多半是 Google Ads 帳號沒命名。

## 練習
1. 在 Custom GPT 的 Instructions 加一句，要求每次回答前先確認使用者要看的時間範圍。
2. 參考 Adzviser 的 prompt 範本庫，設計一個 prompt 問「過去 3 個月哪些搜尋字詞該加為否定關鍵字」，看 GPT 的分析結果。
3. 在 Instructions 裡要求 GPT 產出月報時，固定包含 CPC、CPA、搜尋曝光占比三個指標和月對月比較。
