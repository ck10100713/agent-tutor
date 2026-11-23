---
translated: true
source: examples/Prompt_Caching101.ipynb
---

# Prompt Caching 101

> 原文：[examples/Prompt_Caching101.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Prompt_Caching101.ipynb)

用 OpenAI 的 prompt caching 降低延遲和成本。

## 這篇在做什麼

說明 OpenAI 的 prompt caching 怎麼運作，並用兩個例子實測：快取 tools 加多輪對話，以及快取圖片。重點是看 `cached_tokens` 欄位，確認哪些請求有命中快取、哪些沒有。

## 學完你會

- 知道 prompt caching 的觸發條件（超過 1024 token 的 prefix）和作用範圍
- 把 prompt 排成靜態內容在前、動態內容在後，讓 tools 和多輪對話命中快取
- 從 `usage.prompt_tokens_details.cached_tokens` 判斷快取有沒有生效，並理解圖片的 URL 順序為什麼會影響命中

## 開跑前

- 需要 `OPENAI_API_KEY`
- 範例會多次呼叫模型（含延遲等待），會產生少量費用


OpenAI 對超過 1024 token 的 prompt 提供折扣的 prompt caching，對超過 10,000 token 的長 prompt，延遲最多可降低 80%。把 LLM API 請求之間重複的資訊快取起來，可以大幅降低延遲和成本。Prompt caching 的範圍在組織層級，也就是只有同一組織的成員能存取共用的快取。此外，caching 符合 zero data retention，因為過程中不會儲存任何資料。

Prompt caching 會對超過 1024 token 的 prompt 自動啟用，你的 completions 請求不用做任何改動。發出 API 請求時，系統會先檢查 prompt 開頭的部分（prefix）是否已經被快取。如果有符合（cache hit），就使用快取的 prompt，延遲和成本都會降低。如果沒有符合，系統會從頭處理整個 prompt，並把 prefix 快取起來供之後使用。

了解這些好處後，prompt caching 特別有利的幾個主要使用情境是：


- **使用 tools 和 structured outputs 的 agent**：快取很長的 tools 清單和 schema。
- **程式與寫作助手**：把大段程式碼或工作區的摘要直接放進 prompt。
- **聊天機器人**：快取多輪對話中固定的部分，在長時間對話中有效維持 context。

這份 cookbook 會用幾個例子示範快取 tools 和圖片。一般來說，要把指令、範例這類靜態內容放在 prompt 開頭，把使用者專屬資訊這類會變的內容放在結尾。這個原則也適用於圖片和 tools，它們在請求之間必須完全相同，連順序都要一致。所有請求，包括少於 1024 token 的，都會在 chat completions 物件的 `usage.prompt_tokens_details` 裡顯示 cached_tokens 欄位，表示 prompt token 中有多少命中快取。少於 1024 token 的請求，cached_tokens 會是零。快取折扣是依實際處理的 token 數計算，包括圖片用掉的 token，這些也會算進你的 rate limit。

## 範例 1：快取 tools 與多輪對話

這個例子裡，我們為客服助手定義 tools 和互動，它能處理查詢送達日期、取消訂單、更新付款方式等任務。助手處理兩則獨立的訊息，先回應第一個查詢，再延遲一段時間後回應後續的查詢。

快取 tools 時，tool 定義和它們的順序必須完全相同，才會被納入 prompt prefix。要在多輪對話中快取訊息歷史，就把新元素加到 messages 陣列的結尾。在回應物件和下面的輸出裡，第二次 completion `run2` 的 `cached_tokens` 大於零，表示快取成功。

```python
from openai import OpenAI
import os
import json 
import time


api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(organization='org-l89177bnhkme4a44292n5r3j', api_key=api_key)
```

```python
import time
import json

# Define tools
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_delivery_date",
            "description": "Get the delivery date for a customer's order. Call this whenever you need to know the delivery date, for example when a customer asks 'Where is my package'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID.",
                    },
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancel an order that has not yet been shipped. Use this when a customer requests order cancellation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID."
                    },
                    "reason": {
                        "type": "string",
                        "description": "The reason for cancelling the order."
                    }
                },
                "required": ["order_id", "reason"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "return_item",
            "description": "Process a return for an order. This should be called when a customer wants to return an item and the order has already been delivered.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID."
                    },
                    "item_id": {
                        "type": "string",
                        "description": "The specific item ID the customer wants to return."
                    },
                    "reason": {
                        "type": "string",
                        "description": "The reason for returning the item."
                    }
                },
                "required": ["order_id", "item_id", "reason"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_shipping_address",
            "description": "Update the shipping address for an order that hasn't been shipped yet. Use this if the customer wants to change their delivery address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID."
                    },
                    "new_address": {
                        "type": "object",
                        "properties": {
                            "street": {
                                "type": "string",
                                "description": "The new street address."
                            },
                            "city": {
                                "type": "string",
                                "description": "The new city."
                            },
                            "state": {
                                "type": "string",
                                "description": "The new state."
                            },
                            "zip": {
                                "type": "string",
                                "description": "The new zip code."
                            },
                            "country": {
                                "type": "string",
                                "description": "The new country."
                            }
                        },
                        "required": ["street", "city", "state", "zip", "country"],
                        "additionalProperties": False
                    }
                },
                "required": ["order_id", "new_address"],
                "additionalProperties": False
            }
        }
    },
    # New tool: Update payment method
    {
        "type": "function",
        "function": {
            "name": "update_payment_method",
            "description": "Update the payment method for an order that hasn't been completed yet. Use this if the customer wants to change their payment details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order ID."
                    },
                    "payment_method": {
                        "type": "object",
                        "properties": {
                            "card_number": {
                                "type": "string",
                                "description": "The new credit card number."
                            },
                            "expiry_date": {
                                "type": "string",
                                "description": "The new credit card expiry date in MM/YY format."
                            },
                            "cvv": {
                                "type": "string",
                                "description": "The new credit card CVV code."
                            }
                        },
                        "required": ["card_number", "expiry_date", "cvv"],
                        "additionalProperties": False
                    }
                },
                "required": ["order_id", "payment_method"],
                "additionalProperties": False
            }
        }
    }
]

# Enhanced system message with guardrails
messages = [
    {
        "role": "system", 
        "content": (
            "You are a professional, empathetic, and efficient customer support assistant. Your mission is to provide fast, clear, "
            "and comprehensive assistance to customers while maintaining a warm and approachable tone. "
            "Always express empathy, especially when the user seems frustrated or concerned, and ensure that your language is polite and professional. "
            "Use simple and clear communication to avoid any misunderstanding, and confirm actions with the user before proceeding. "
            "In more complex or time-sensitive cases, assure the user that you're taking swift action and provide regular updates. "
            "Adapt to the user’s tone: remain calm, friendly, and understanding, even in stressful or difficult situations."
            "\n\n"
            "Additionally, there are several important guardrails that you must adhere to while assisting users:"
            "\n\n"
            "1. **Confidentiality and Data Privacy**: Do not share any sensitive information about the company or other users. When handling personal details such as order IDs, addresses, or payment methods, ensure that the information is treated with the highest confidentiality. If a user requests access to their data, only provide the necessary information relevant to their request, ensuring no other user's information is accidentally revealed."
            "\n\n"
            "2. **Secure Payment Handling**: When updating payment details or processing refunds, always ensure that payment data such as credit card numbers, CVVs, and expiration dates are transmitted and stored securely. Never display or log full credit card numbers. Confirm with the user before processing any payment changes or refunds."
            "\n\n"
            "3. **Respect Boundaries**: If a user expresses frustration or dissatisfaction, remain calm and empathetic but avoid overstepping professional boundaries. Do not make personal judgments, and refrain from using language that might escalate the situation. Stick to factual information and clear solutions to resolve the user's concerns."
            "\n\n"
            "4. **Legal Compliance**: Ensure that all actions you take comply with legal and regulatory standards. For example, if the user requests a refund, cancellation, or return, follow the company’s refund policies strictly. If the order cannot be canceled due to being shipped or another restriction, explain the policy clearly but sympathetically."
            "\n\n"
            "5. **Consistency**: Always provide consistent information that aligns with company policies. If unsure about a company policy, communicate clearly with the user, letting them know that you are verifying the information, and avoid providing false promises. If escalating an issue to another team, inform the user and provide a realistic timeline for when they can expect a resolution."
            "\n\n"
            "6. **User Empowerment**: Whenever possible, empower the user to make informed decisions. Provide them with relevant options and explain each clearly, ensuring that they understand the consequences of each choice (e.g., canceling an order may result in loss of loyalty points, etc.). Ensure that your assistance supports their autonomy."
            "\n\n"
            "7. **No Speculative Information**: Do not speculate about outcomes or provide information that you are not certain of. Always stick to verified facts when discussing order statuses, policies, or potential resolutions. If something is unclear, tell the user you will investigate further before making any commitments."
            "\n\n"
            "8. **Respectful and Inclusive Language**: Ensure that your language remains inclusive and respectful, regardless of the user’s tone. Avoid making assumptions based on limited information and be mindful of diverse user needs and backgrounds."
        )
    },
    {
        "role": "user", 
        "content": (
            "Hi, I placed an order three days ago and haven’t received any updates on when it’s going to be delivered. "
            "Could you help me check the delivery date? My order number is #9876543210. I’m a little worried because I need this item urgently."
        )
    }
]

# Enhanced user_query2
user_query2 = {
    "role": "user", 
    "content": (
        "Since my order hasn't actually shipped yet, I would like to cancel it. "
        "The order number is #9876543210, and I need to cancel because I’ve decided to purchase it locally to get it faster. "
        "Can you help me with that? Thank you!"
    )
}

# Function to run completion with the provided message history and tools
def completion_run(messages, tools):
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        tools=tools,
        messages=messages,
        tool_choice="required"
    )
    usage_data = json.dumps(completion.to_dict(), indent=4)
    return usage_data

# Main function to handle the two runs
def main(messages, tools, user_query2):
    # Run 1: Initial query
    print("Run 1:")
    run1 = completion_run(messages, tools)
    print(run1)

    # Delay for 7 seconds
    time.sleep(7)

    # Append user_query2 to the message history
    messages.append(user_query2)

    # Run 2: With appended query
    print("\nRun 2:")
    run2 = completion_run(messages, tools)
    print(run2)


# Run the main function
main(messages, tools, user_query2)
```

??? note "輸出"

    ```text
    Run 1:
    {
        "id": "chatcmpl-ADeOueQSi2DIUMdLXnZIv9caVfnro",
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "logprobs": null,
                "message": {
                    "content": null,
                    "refusal": null,
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_5TnLcdD9tyVMVbzNGdejlJJa",
                            "function": {
                                "arguments": "{\"order_id\":\"9876543210\"}",
                                "name": "get_delivery_date"
                            },
                            "type": "function"
                        }
                    ]
                }
            }
        ],
        "created": 1727816928,
        "model": "gpt-4o-mini-2024-07-18",
        "object": "chat.completion",
        "system_fingerprint": "fp_f85bea6784",
        "usage": {
            "completion_tokens": 17,
            "prompt_tokens": 1079,
            "total_tokens": 1096,
            "prompt_tokens_details": {
                "cached_tokens": 0
            },
            "completion_tokens_details": {
                "reasoning_tokens": 0
            }
        }
    ... (省略 51 行)
    ```

## 範例 2：圖片

第二個例子，我們在 messages 陣列裡放入多個雜貨商品的圖片 URL，加上一個使用者查詢，並加上延遲跑三次。圖片不論是連結還是以 base64 編碼放在 user message 裡，都符合快取條件。要確保 detail 參數保持一致，因為它會影響圖片怎麼被 tokenize。注意 GPT-4o-mini 雖然文字用的是低成本的 token 模型，但會多加一些 token 來涵蓋圖片處理的成本。快取折扣是依實際處理的 token 數計算，包括圖片用掉的 token，這些也會算進你的 rate limit。

這個例子的輸出顯示，第二次執行命中了快取，但第三次沒有命中，原因是第一個 URL 不同（eggs_url 而不是 veggie_url），即使使用者查詢相同。

```python
sauce_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/97/12-04-20-saucen-by-RalfR-15.jpg/800px-12-04-20-saucen-by-RalfR-15.jpg"
veggie_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Veggies.jpg/800px-Veggies.jpg"
eggs_url= "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Egg_shelf.jpg/450px-Egg_shelf.jpg"
milk_url= "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/Lactaid_brand.jpg/800px-Lactaid_brand.jpg"

def multiimage_completion(url1, url2, user_query):
    completion = client.chat.completions.create(
    model="gpt-4o-2024-08-06",
    messages=[
        {
        "role": "user",
        "content": [
            {
            "type": "image_url",
            "image_url": {
                "url": url1,
                "detail": "high"
            },
            },
            {
            "type": "image_url",
            "image_url": {
                "url": url2,
                "detail": "high"
            },
            },
            {"type": "text", "text": user_query}
        ],
        }
    ],
    max_tokens=300,
    )
    print(json.dumps(completion.to_dict(), indent=4))
    

def main(sauce_url, veggie_url):
    multiimage_completion(sauce_url, veggie_url, "Please list the types of sauces are shown in these images")
    #delay for 20 seconds
    time.sleep(20)
    multiimage_completion(sauce_url, veggie_url, "Please list the types of vegetables are shown in these images")
    time.sleep(20)
    multiimage_completion(milk_url, sauce_url, "Please list the types of sauces are shown in these images")

if __name__ == "__main__":
    main(sauce_url, veggie_url)
```

??? note "輸出"

    ```text
    {
        "id": "chatcmpl-ADeV3IrUqhpjMXEgv29BFHtTQ0Pzt",
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "logprobs": null,
                "message": {
                    "content": "The images show the following types of sauces:\n\n1. **Soy Sauce** - Kikkoman brand.\n2. **Worcester Sauce** - Appel brand, listed as \"Dresdner Art.\"\n3. **Tabasco Sauce** - Original pepper sauce.\n\nThe second image shows various vegetables, not sauces.",
                    "refusal": null,
                    "role": "assistant"
                }
            }
        ],
        "created": 1727817309,
        "model": "gpt-4o-2024-08-06",
        "object": "chat.completion",
        "system_fingerprint": "fp_2f406b9113",
        "usage": {
            "completion_tokens": 65,
            "prompt_tokens": 1548,
            "total_tokens": 1613,
            "prompt_tokens_details": {
                "cached_tokens": 0
            },
            "completion_tokens_details": {
                "reasoning_tokens": 0
            }
        }
    }
    {
        "id": "chatcmpl-ADeVRSI6zFINkx99k7V6ux1v5iF5f",
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "logprobs": null,
                "message": {
                    "content": "The images show different types of items. In the first image, you'll see bottles of sauces like soy sauce, Worcester sauce, and Tabasco. The second image features various vegetables, including:\n\n1. Napa cabbage\n2. Kale\n3. Carrots\n4. Bok choy\n5. Swiss chard\n6. Leeks\n7. Parsley\n\nThese vegetables are arranged on shelves in a grocery store setting.",
                    "refusal": null,
    ... (省略 50 行)
    ```


## 整體建議

要充分利用 prompt caching，可以參考這些最佳做法：

- 把靜態或常重複使用的內容放在 prompt 開頭：把動態資料放在 prompt 結尾，快取效率會比較好。

- 保持一致的使用模式：不常使用的 prompt 會被自動從快取移除。要避免被逐出，就要穩定地使用 prompt。

- 監控關鍵指標：定期追蹤快取命中率、延遲和被快取 token 的比例，用這些資訊調整快取策略，把效能發揮到最大。

做到這些，就能充分利用 prompt caching，讓應用程式反應快又省成本。管理得當的快取策略能明顯縮短處理時間、降低成本，也讓使用者體驗更順暢。

## 重點整理

- prompt caching 對超過 1024 token 的 prompt 自動啟用，不用改請求，範圍是組織層級。
- 命中靠的是 prefix 完全相同，所以靜態內容放前面，動態內容放後面。
- tools 和圖片的內容與順序都要一致，連 URL 順序不同都會 miss。
- 多輪對話的做法是把新訊息只往 messages 結尾追加。
- 用 `cached_tokens` 監控命中，並維持穩定的呼叫頻率避免快取被逐出。

## 練習

1. 把範例 1 的 tools 清單順序對調，重跑 `run2`，觀察 `cached_tokens` 是否變成 0。
2. 範例 2 裡，把第三次的圖片 URL 順序改回跟前兩次一樣，確認這次有命中快取。
3. 寫一個小函式，每次呼叫後印出 `cached_tokens / prompt_tokens` 的命中比例，並套用到前面所有請求。
