---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/mcp/mcp_tool_guide.ipynb
---
# Responses API 的 MCP tool 使用指南

> 原文：[examples/mcp/mcp_tool_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/mcp_tool_guide.ipynb)

用 Responses API 的 MCP tool 連接外部服務的 cookbook。

## 這篇在做什麼

介紹 Responses API 內建的 hosted MCP tool：模型直接跟 MCP server 溝通，不用再自己寫 function calling 的中繼層。內容包含運作流程、用 `allowed_tools` 和快取降低 token 與延遲的做法，以及怎麼搭配其他 tool 和寫 prompt 讓呼叫更有效率。

## 學完你會

- 說明 MCP tool 從宣告 server、匯入 tool 清單到呼叫與核准的完整流程。
- 用 `allowed_tools` 和 `previous_response_id` 減少 token 與延遲。
- 把 MCP 和 `code_interpreter`、web search 組合成多服務的 agent，並用 prompt 限制 MCP 呼叫次數。

## 開跑前

需要 `OPENAI_API_KEY`。範例會連到第三方的遠端 MCP server（例如 Alo Yoga），有些 server 需要自己的 API key 或 OAuth token。



開發 agent 應用常常要連外部服務。傳統做法是 function calling：每個動作都要從模型回到你的後端，再到外部服務，等回應後再把結果送回模型。這樣會多好幾個網路來回，延遲很高，也不好擴充和管理。

Responses API 的 hosted Model Context Protocol (MCP) tool 讓這件事簡單許多。你不用手動把每個 function call 接到特定服務，只要設定模型指向一個（或多個）MCP server。那個 server 就是集中的 tool host，提供像「搜尋商品目錄」「加入購物車」這樣的標準指令。這樣編排更簡單，tool 也能集中管理。有了 MCP，模型直接跟 MCP server 互動，延遲更低，也不需要後端協調。

## MCP tool 簡化了哪些使用情境

MCP 大幅降低了做出串接外部服務的產品的門檻，讓不同服務能順暢地串在一起。下面列幾個例子，這些情境以前很麻煩，現在模型能直接跟遠端 MCP server 溝通，就簡單多了。

| **領域**                 | **MCP tool 帶來的使用情境**                                                                                                                                                  | **以前的麻煩**                                                                                                      |
|---------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| **電商 / 支付**   | - 一輪對話內把商品加進 Shopify 購物車並回傳結帳連結：`"Add the Allbirds Men’s Tree Dasher 2 in size 10"` → 購物車連結  <br> - 產生 Stripe 付款連結 | 用 function calling 得自己寫 `cart_add` 或 `create_payment_link` 的包裝，還要架自己的 relay server。 |
| **開發維運 & 程式品質**| - 請 Sentry 查某個檔案最新的錯誤，再在同一段對話裡開一個附修正建議的 GitHub issue                                                    | 在同一個輔助迴圈裡串兩個不同的第三方 API，得用 webhook 黏起來，還要自己管狀態。                |
| **訊息 / 通知** | - 用 web search 抓早上的足球頭條，再讓 Twilio 把摘要簡訊傳到手機，一次呼叫完成                                                 | 得在後端把兩個 tool call 串起來，並自己組最後的簡訊 payload。                             |


## 這個 tool 怎麼運作

大致流程如下：

1. 宣告 server：在 `tools` 陣列加入 MCP 區塊後，Responses API runtime 會先偵測 server 使用的 transport，是較新的 "streamable HTTP" 還是舊的 HTTP-over-SSE，然後用該協定溝通。
2. 匯入 tool 清單：runtime 會呼叫 server 的 `tools/list`，並帶上你提供的 header（API key、OAuth token 等），再把結果寫成模型 context 裡的 `mcp_list_tools` item。只要這個 item 還在，就不會重新抓清單。你可以用 `allowed_tools` 限制模型看得到哪些 tool。
    
    每次 request 結束後，OpenAI 會丟棄 header 的值，也會丟棄 MCP `server_url` 除了 schema、domain 和 subdomain 以外的部分。所以授權金鑰和 server URL 每次 API 呼叫都要帶，這些值也不會出現在 response 物件裡。Schema 能用 "strict" 模式就用，否則照原樣載入。
    
3. 呼叫並核准 tool：模型知道有哪些動作後，就能呼叫其中一個。每次呼叫會產生一個 `mcp_tool_call` item，預設 stream 會暫停等你明確核准，等你信任這個 server 之後可以關掉。
    
    核准後，runtime 執行呼叫並把結果串流回來，模型再決定要接著呼叫別的 tool，還是回最終答案。

## 用 MCP 開發的最佳實務

MCP 還在早期階段，下面這些最佳實務能在開發時改善模型的表現和行為。

### 過濾 tool，避免 payload 膨脹

遠端 server 常常提供一大堆 tool，卻沒考慮模型會怎麼理解和使用。預設情況下，可能一次帶進幾十個 endpoint，每個都有冗長的名稱、描述和 JSON schema，為模型 context 增加數百個 token，也拉高延遲。更糟的是，很多 server 會回傳整個資料物件（例如完整的 Stripe 發票記錄），即使模型的任務只需要幾個欄位。要在正式環境優化效能，可以用 Responses API 的 `allowed_tools` 參數，限制 server 的 `mcp_list_tools` 裡哪些 tool 會被帶進來。這樣能減少 token 開銷、加快回應，也縮小模型的決策空間。你也可能想完全排除某些 tool，例如能做寫入動作或牽涉金流、安全的 tool。

```python
curl https://api.openai.com/v1/responses -i \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4.1",
    "tools": [
        {
            "type": "mcp",
            "server_label": "gitmcp",
            "server_url": "https://gitmcp.io/openai/tiktoken",
            "allowed_tools": ["search_tiktoken_documentation", "fetch_tiktoken_documentation"],
            "require_approval": "never"
        }
    ],
    "input": "how does tiktoken work?"
}'
```

### 用快取降低延遲與 token，reasoning model 留給高複雜度的任務

模型第一次連到 server 時，每個你加入的 MCP server 都會建立一個 `mcp_list_tools` 類型的 item。只要這個 item 還在模型的 context 裡，就不會再呼叫 server 的 `tools/list`，有點像對話層級的快取。如果 `mcp_list_tools` 不在，就會重新從 MCP server 匯入 tool 清單。後續 API request 帶 `previous_response_id`，是確保追問時 `mcp_list_tools` 還在 context 的一種方式，你也可以手動把 item 傳給新的 response。另一個影響延遲和輸出 token 數的因素是有沒有用 reasoning model，因為 reasoning model 會產生多得多的輸出 token 和 reasoning token。下面兩個 curl 範例比較有無 reasoning model 時產生的 token 數：

情境 1：非 reasoning model

```python
curl https://api.openai.com/v1/responses \   
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4.1",
    "tools": [
      {
        "type": "mcp",
        "server_label": "gitmcp",
        "server_url": "https://gitmcp.io/openai/tiktoken",
        "require_approval": "never"
      }
    ],
    "input": "how does tiktoken work?" 
  }'
```

```python
  "usage": {
    "input_tokens": 280,
    "input_tokens_details": {
      "cached_tokens": 0
    },
    "output_tokens": 665,
    "output_tokens_details": {
      "reasoning_tokens": 0
    },
    "total_tokens": 945
  }
```

情境 2：reasoning model，沒有帶 `previous_response_id`

```python
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "o4-mini",
    "tools": [
      {
        "type": "mcp",
        "server_label": "gitmcp",
        "server_url": "https://gitmcp.io/openai/tiktoken",
        "require_approval": "never"
      }
    ],
    "input": "how does tiktoken work?",
    "reasoning": {
      "effort": "medium",
      "summary": "auto"
    } 
  }'
```

```python
  "usage": {
    "input_tokens": 36436,
    "input_tokens_details": {
      "cached_tokens": 22964
    },
    "output_tokens": 1586,
    "output_tokens_details": {
      "reasoning_tokens": 576
    },
    "total_tokens": 38022 
    }
```

### 搭配其他 tool 使用 MCP

MCP tool 只是 tools 陣列裡的另一個項目，所以模型可以順暢地搭配其他 hosted tool，像 `code_interpreter`、`web_search_preview,` 或 `image_generation`，也能搭配你自訂的 tool。你也可以同時使用多個遠端 MCP server。

這個例子要建立一個 agent，扮演虛構瑜珈服飾店的定價分析師：先從 Alo Yoga MCP server 抓競爭對手女短褲、瑜珈褲、背心的現價，再用 hosted web search tool 查 Uniqlo 同樣三個類別的價格。接著用 Code Interpreter 分析上週的銷售 CSV（先用 Files endpoint 上傳），算出每項商品的營收和平均訂單金額，再比較每項商品跟剛抓到的 Uniqlo 與 Alo Yoga 基準之間的價差。任何價格比市場高或低 15% 以上的商品都會被標記，最後 agent 交出一份精簡的文字報告，摘要價差和主要營收數字。

```python
system_prompt= """You are a pricing analyst for my clothing company. Please use the MCP tool 
to fetch prices from the Alo Yoga MCP server for the categories of women's 
shorts, yoga pants, and  tank tops. Use only the MCP server for Alo yoga data, don't search the web. 

Next, use the web search tool to search for Uniqlo prices for women's shorts, yoga pants, and tank tops. 

In each case for Alo Yoga and Uniqlo, extract the
price for the top result in each category. Also provide the full URLs
 
Using the uploaded CSV file of sales data from my store, and with the 
code interpreter tool calculate revenue by product item, compute average order-value on a transaction level, and calculate the percentage price gap between the CSV data and Uniqlo/Alo Yoga prices. 
Flag products priced 15% or more above or below the market. 
Create and output a short report including the findings.

# Steps

1. **Fetch Alo Yoga Prices:**
   - Use the Alo Yoga MCP server to fetch prices for the following products:
High-Waist Airlift Legging
Sway Bra Tank
 5" Airlift Energy Short

- Ensure you find prices for each. 
- Extract the price of the top result for each category.
- include  URL links 


2. **Query Uniqlo Prices:**
   - Use the Web-Search tool to search non-sale prices for the following Uniqlo products: 
Women's AIRism Soft Biker Shorts
Women's AIRism Soft Leggings
Women's AIRism Bra Sleeveless Top
- Ensure you find non-sale prices for each. 
- Extract the price for the top result in each category.
- include  URL links 

3. **Sales Data Analysis:**
   - Use the uploaded CSV sales data to calculate revenue across each 
   product item.
   - Determine the average order-value on a transaction level.
   - For each SKU, compute the percentage price gap between the 
   CSV data and Uniqlo/Alo Yoga prices.
   - Flag products priced ≥ 15% above or below the market.

4. **Report:**
   - Compile and output a report including the flagging results

# Output Format
- A short text report explaining:
  - Any products that are priced ≥ 15% above or below the market, 
  with specific details. """
```

下面是個 curl 範例，其中用 placeholder 代表上面的 system prompt。

```python
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4.1",
    "input": [
      {
        "role": "system",
        "content": [
          {
            "type": "input_text",
            "text": "ABOVE_SYSTEM_PROMPT"
          }
        ]
      }
    ],
    "tools": [
      {
        "type": "web_search_preview",
        "user_location": {
          "type": "approximate",
          "country": "US"
        },
        "search_context_size": "medium"
      },
      {
        "type": "code_interpreter",
        "container": {
          "type": "auto",
          "file_ids": [
            "file-WTiyGcZySaU6n218gj4XxR"
          ]
        }
      },
      {
        "type": "mcp",
        "server_url": "https://www.aloyoga.com/api/mcp",
        "server_label": "aloyoga",
        "allowed_tools": [
          "search_shop_catalog",
          "get_product_details"
        ],
        "require_approval": "never"
      }
    ],
    "temperature": 1,
    "max_output_tokens": 2048,
    "top_p": 1,
    "store": true
  }'
```

模型能把 MCP tool 和 web search 的結果帶進 code interpreter 的步驟，產出格式清楚、好讀的報告，內容如下：

---
#### **價格比較與營收分析報告**

**你的店的銷售與價格分析**

- **各商品營收：**
    - 短褲：$6,060
    - 背心：$6,150
    - 瑜珈褲：$12,210
- **平均訂單金額：** $872.14
- **你的店各類別平均售價：**
    - 短褲：$60.00
    - 背心：$75.00
    - 瑜珈褲：$110.00

#### **與市場的價差**

| 類別 | 本店平均價 | 對 Alo Yoga 價差 (%) | 標記 (≥15%) | 對 Uniqlo 價差 (%) | 標記 (≥15%) |
| --- | --- | --- | --- | --- | --- |
| 短褲 | $60.00 | -31.8% | **是** | +100.7% | **是** |
| 背心 | $75.00 | -14.8% |  | +114.9% | **是** |
| 瑜珈褲 | $110.00 | -14.1% |  | +267.9% | **是** |

#### **建議與標記**

**被標記的商品（價差 ≥15%）：**

- **短褲：** 比 Alo Yoga 低 31.8%，但比 Uniqlo 高 100.7%。
- **背心：** 比 Uniqlo 高 114.9%。
- **瑜珈褲：** 比 Uniqlo 高 267.9%。

短褲的定價明顯低於高階競爭對手（Alo Yoga），卻遠高於平價選擇（Uniqlo）。如果想進攻高階市場，可以考慮調漲；如果想鎖定平價客群，降價就有道理。大部分背心和瑜珈褲的定位也類似，遠低於 Alo，但明顯高於 Uniqlo。

___

### 改善 MCP tool 呼叫的 prompt 技巧

視使用情境而定，你可能會發現模型呼叫了很多次 MCP，例如用商品目錄搜尋 tool 的時候。為了避免在大量商品庫存上無限迭代，可以在 prompt 指示模型只搜尋前 N 個項目，使用者明確要求更多時才提議繼續。這樣回應會集中又俐落。

如果你用的 MCP server 帶有很龐大的 `mcp_list_tools`，建議也放幾個有針對性的 few-shot 範例，示範模型怎麼選對 server，並在拿到需要的資訊後就停手，不要重複呼叫。

最後，在 prompt 裡提醒模型：如果使用者的問題缺少關鍵資訊（尺寸、顏色、產品線等），要先追問，不要直接發起大範圍搜尋。這個小小的提示能減少不必要的 tool call，也提升回答品質。下面的範例 prompt 把這些原則整合在一起：

```python
system_prompt= """You are an AI assistant that can call the following MCP servers:

1. allbirds_store
2. gitmcp

Steps
1. Use the MCP servers above to answer the user query, not every MCP server will relevant for a given query so you can choose which ones to invoke.  
2. If the user’s request lacks essential details (size, color, etc.), ask a follow-up question first rather than guessing and using the MCP server tool prematurely. 
3. If searching for products in a catalog, only return 4 results at a time before asking the user whether they want to see more. 

### Few-shot examples

# EX1 — Direct product search, then fetch variant details
user: Do you have the Allbirds Tree Runner in men’s size 10?  
assistant: {"name":"allbirds_store.search_shop_catalog",
            "arguments":{"query":"Tree Runner",
                         "context":"Men’s size 10 shoes"}}
# (assume the search returns product_id "gid://shopify/Product/987")  
assistant: {"name":"allbirds_store.get_product_details",
            "arguments":{"product_id":"gid://shopify/Product/987",
                         "options":{"Size":"10"}}}

# EX2 — Clarify missing size, then two-step color variant lookup
user: I want the Tree Runner in blue.  
assistant: Sure — what size do you need?  
user: Size 10.  
assistant: {"name":"allbirds_store.search_shop_catalog",
            "arguments":{"query":"Tree Runner",
                         "context":"Blue variant, size 10"}}
# (assume the search returns product_id "gid://shopify/Product/987")  
assistant: {"name":"allbirds_store.get_product_details",
            "arguments":{"product_id":"gid://shopify/Product/987",
                         "options":{"Size":"10","Color":"Blue"}}}

# EX3 — Git docs: search then fetch specific file
user: Can you show me how tiktoken does byte-pair encoding?  
assistant: {"name":"gitmcp.search_website_documentation",
            "arguments":{"query":"tiktoken byte-pair encoding"}}
# (assume the search returns document_id "docs/ENCODING.md")  
assistant: {"name":"gitmcp.fetch_website_documentation",
            "arguments":{"document_id":"docs/ENCODING.md"}} """
```

```python
curl https://api.openai.com/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{
    "model": "gpt-4.1",
    "input": [
      {
        "role": "system",
        "content": [
          {
            "type": "input_text",
            "text": "ABOVE_SYSTEM_PROMPT"
          }
        ]
      },
      {
        "role": "user",
        "content": [
          {
            "type": "input_text",
            "text": "find me womens tree loungers in size 8"
          }
        ]
      }
    ],
    "tools": [
      {
        "type": "mcp",
        "server_url": "https://www.allbirds.com/api/mcp",
        "server_label": "allbirds",
        "allowed_tools": [
          "search_shop_catalog",
          "get_cart",
          "update_cart",
          "search_shop_policies_and_faqs",
          "get_product_details"
        ],
        "require_approval": "never"
      },
      {
        "type": "mcp",
        "server_label": "gitmcp",
        "server_url": "https://gitmcp.io/openai/tiktoken",
        "allowed_tools": [
          "fetch_tiktoken_documentation",
          "search_tiktoken_documentation",
          "search_tiktoken_code",
          "fetch_generic_url_content"
        ],
        "require_approval": "never"
      }
    ],
    "temperature": 1,
    "max_output_tokens": 2048
  }'
```

## 結論

hosted MCP tool 讓外部服務能透過 Responses API 使用。連上遠端 server 並讓 runtime 快取它的 tool 清單，就不用在應用程式碼裡處理那段網路來回。用 `allowed_tools` 可以降低 token 開銷，也讓模型有一組精簡、好找的動作可選。你還能把 MCP 跟 `code_interpreter`、`web_search_preview` 或 `image_gen` 這些內建 tool 組合，做出跨多個服務的 workflow。

## 重點整理

- MCP tool 讓模型直接跟 MCP server 溝通，省掉 function calling 在你後端繞一圈的延遲和膠水程式。
- 流程是宣告 server、匯入 `mcp_list_tools`、呼叫並核准；授權金鑰和 server URL 每次 request 都要帶。
- `allowed_tools` 縮小 tool 清單，`previous_response_id` 保留 `mcp_list_tools`，兩者都是在省 token 和延遲。
- reasoning model 會多出大量輸出 token，簡單任務不一定值得用。
- 在 prompt 裡限制搜尋筆數、給 few-shot、缺資訊先追問，可以減少多餘的 MCP 呼叫。

## 練習

1. 在範例的 MCP 設定裡加上 `allowed_tools`，只留一兩個唯讀的 tool，比較前後 response 的 token 用量。
2. 分別用帶和不帶 `previous_response_id` 的方式送追問，觀察 response 的 output 裡有沒有再次出現 `mcp_list_tools`。
3. 改範例的 system prompt，把標記門檻從 15% 改成 5%，並加上「最多搜尋 3 個商品」的限制，看報告和 tool 呼叫次數怎麼變。
