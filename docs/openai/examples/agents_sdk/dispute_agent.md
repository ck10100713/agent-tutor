---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/agents_sdk/dispute_agent.ipynb
---
# 用 Agents SDK 和 Stripe API 自動處理交易爭議

> 原文：[examples/agents_sdk/dispute_agent.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/dispute_agent.ipynb)



## 這篇在做什麼

用 Agents SDK 搭配 Stripe API，做一套自動處理 dispute（交易爭議）的流程。三個 agent 分工：triage agent 判斷要接受還是升級調查，acceptance agent 負責接受爭議，investigator agent 蒐集證據。

## 學完你會

- 用 `function_tool` 把 Python 函式（查訂單、查 Stripe payment intent、關閉 dispute）變成 agent 能呼叫的 tool。
- 用 handoff 讓 triage agent 把案子轉給不同的專責 agent。
- 跑兩種情境（公司出錯、客人對 final sale 提爭議），看 agent 怎麼走不同路線。

## 開跑前

- OpenAI API key。
- Stripe 帳號，使用 Test Secret Key。
- 把兩把 key 放進 `.env` 檔。


我們最近發表了開源的 **Agents SDK**，用來打造 agentic AI 應用，套件輕量、抽象層很少。

這篇示範怎麼把 Agents SDK 跟 Stripe API 搭起來處理 dispute management，這是很多公司都會碰到的營運問題。我們看兩個實際情境：

1. **公司出錯：**  
   公司明顯有錯，例如沒出貨，這時合理的做法是直接接受爭議。

2. **客人提出爭議（final sale）：**  
   客人明明收到正確商品，也知道這筆是 final sale，卻還是提爭議，這時要進一步調查、蒐集佐證。

為了處理這兩種情境，我們會用三個 agent：

- **Triage Agent：**  
  根據訂單的出貨狀態，決定接受還是升級處理。

- **Acceptance Agent：**  
  處理明確的案子，自動接受爭議並簡短說明理由。

- **Investigator Agent：**  
  分析通訊紀錄和訂單資訊，蒐集必要的證據，做完整調查。

接下來一步步看自訂的 agentic workflow 怎麼自動化爭議處理。


## 事前準備

跑這篇之前要先準備下面幾個帳號並做好設定，不然後面的 API 都呼叫不了。

#### 1. OpenAI 帳號

- **用途：**  
  需要 OpenAI 帳號才能用語言模型和 Agents SDK。

- **要做的事：**  
  還沒有帳號的話先[註冊 OpenAI 帳號](https://openai.com)，再到 [OpenAI API Keys 頁面](https://platform.openai.com/api-keys)建立 API key。

#### 2. Stripe 帳號

- **用途：**  
  用 Stripe 帳號來模擬付款、管理 dispute，並在 demo 流程裡呼叫 Stripe API。

- **要做的事：**  
  到 [Stripe 註冊頁](https://dashboard.stripe.com/register)建立免費帳號。

- **找到 API keys：**  
  登入 Stripe dashboard，進到 **Developers > API keys**。

- **用 Test Mode：**  
  開發和測試一律用 **Test Secret Key**。


#### 3. 建立 .env 檔，放 OpenAI 和 Stripe 的 API key

```
OPENAI_API_KEY=
STRIPE_SECRET_KEY=
```

### 環境設定
先裝需要的套件，再 import 函式庫，並寫幾個後面會用到的工具函式。

```python
%pip install python-dotenv --quiet
%pip install openai-agents --quiet
%pip install stripe --quiet
%pip install typing_extensions --quiet
```

```python
import os
import logging
import json
from dotenv import load_dotenv
from agents import Agent, Runner, function_tool  # Only import what you need
import stripe
from typing_extensions import TypedDict, Any
# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set Stripe API key from environment variables
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
```

#### 定義 Function Tools
這段定義幾個支援爭議處理流程的 function tool。
<br>
 
- `get_order`、`get_phone_logs`、`get_emails` 用傳入的識別碼回傳訂單詳情和 email/電話紀錄，模擬外部資料查詢。
- `retrieve_payment_intent` 呼叫 Stripe API 取得 payment intent 的詳細資料。
- `close_dispute` 用 dispute ID 自動關閉 Stripe 上的爭議，確保爭議有被正確處理並留下紀錄。


```python
@function_tool
def get_phone_logs(phone_number: str) -> list:
    """
    Return a list of phone call records for the given phone number.
    Each record might include call timestamps, durations, notes, 
    and an associated order_id if applicable.
    """
    phone_logs = [
        {
            "phone_number": "+15551234567",
            "timestamp": "2023-03-14 15:24:00",
            "duration_minutes": 5,
            "notes": "Asked about status of order #1121",
            "order_id": 1121
        },
        {
            "phone_number": "+15551234567",
            "timestamp": "2023-02-28 10:10:00",
            "duration_minutes": 7,
            "notes": "Requested refund for order #1121, I told him we were unable to refund the order because it was final sale",
            "order_id": 1121
        },
        {
            "phone_number": "+15559876543",
            "timestamp": "2023-01-05 09:00:00",
            "duration_minutes": 2,
            "notes": "General inquiry; no specific order mentioned",
            "order_id": None
        },
    ]
    return [
        log for log in phone_logs if log["phone_number"] == phone_number
    ]


@function_tool
def get_order(order_id: int) -> str:
    """
    Retrieve an order by ID from a predefined list of orders.
    Returns the corresponding order object or 'No order found'.
    """
    orders = [
        {
            "order_id": 1234,
            "fulfillment_details": "not_shipped"
        },
        {
            "order_id": 9101,
            "fulfillment_details": "shipped",
            "tracking_info": {
                "carrier": "FedEx",
                "tracking_number": "123456789012"
            },
            "delivery_status": "out for delivery"
        },
        {
            "order_id": 1121,
            "fulfillment_details": "delivered",
            "customer_id": "cus_PZ1234567890",
            "customer_phone": "+15551234567",
            "order_date": "2023-01-01",
            "customer_email": "customer1@example.com",
            "tracking_info": {
                "carrier": "UPS",
                "tracking_number": "1Z999AA10123456784",
                "delivery_status": "delivered"
            },
            "shipping_address": {
                "zip": "10001"
            },
            "tos_acceptance": {
                "date": "2023-01-01",
                "ip": "192.168.1.1"
            }
        }
    ]
    for order in orders:
        if order["order_id"] == order_id:
            return order
    return "No order found"


@function_tool
def get_emails(email: str) -> list:
    """
    Return a list of email records for the given email address.
    """
    emails = [
        {
            "email": "customer1@example.com",
            "subject": "Order #1121",
            "body": "Hey, I know you don't accept refunds but the sneakers don't fit and I'd like a refund"
        },
        {
            "email": "customer2@example.com",
            "subject": "Inquiry about product availability",
            "body": "Hello, I wanted to check if the new model of the smartphone is available in stock."
        },
        {
            "email": "customer3@example.com",
            "subject": "Feedback on recent purchase",
            "body": "Hi, I recently purchased a laptop from your store and I am very satisfied with the product. Keep up the good work!"
        }
    ]
    return [email_data for email_data in emails if email_data["email"] == email]


@function_tool
async def retrieve_payment_intent(payment_intent_id: str) -> dict:
    """
    Retrieve a Stripe payment intent by ID.
    Returns the payment intent object on success or an empty dictionary on failure.
    """
    try:
        return stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error occurred while retrieving payment intent: {e}")
        return {}

@function_tool
async def close_dispute(dispute_id: str) -> dict:
    """
    Close a Stripe dispute by ID. 
    Returns the dispute object on success or an empty dictionary on failure.
    """
    try:
        return stripe.Dispute.close(dispute_id)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error occurred while closing dispute: {e}")
        return {}
```

### 定義 Agents

- **Dispute Intake Agent（investigator_agent）** 負責調查爭議，蒐集所有相關證據並產出報告。
- **Accept a Dispute Agent（accept_dispute_agent）** 處理被判定有理的爭議，自動關閉並簡短說明決定的原因。
- **Triage Agent（triage_agent）** 是決策者：從 payment intent 的 metadata 取出 order ID，查詳細訂單資訊，再決定要升級給 investigator，還是交給 accept dispute agent。
- 這幾個 agent 組成模組化的 workflow，把各項工作分給專責的 agent，讓爭議處理流程自動化、更順。


```python
investigator_agent = Agent(
    name="Dispute Intake Agent",
    instructions=(
        "As a dispute investigator, please compile the following details in your final output:\n\n"
        "Dispute Details:\n"
        "- Dispute ID\n"
        "- Amount\n"
        "- Reason for Dispute\n"
        "- Card Brand\n\n"
        "Payment & Order Details:\n"
        "- Fulfillment status of the order\n"
        "- Shipping carrier and tracking number\n"
        "- Confirmation of TOS acceptance\n\n"
        "Email and Phone Records:\n"
        "- Any relevant email threads (include the full body text)\n"
        "- Any relevant phone logs\n"
    ),
    model="o3-mini",
    tools=[get_emails, get_phone_logs]
)


accept_dispute_agent = Agent(
    name="Accept Dispute Agent",
    instructions=(
        "You are an agent responsible for accepting disputes. Please do the following:\n"
        "1. Use the provided dispute ID to close the dispute.\n"
        "2. Provide a short explanation of why the dispute is being accepted.\n"
        "3. Reference any relevant order details (e.g., unfulfilled order, etc.) retrieved from the database.\n\n"
        "Then, produce your final output in this exact format:\n\n"
        "Dispute Details:\n"
        "- Dispute ID\n"
        "- Amount\n"
        "- Reason for Dispute\n\n"
        "Order Details:\n"
        "- Fulfillment status of the order\n\n"
        "Reasoning for closing the dispute\n"
    ),
    model="gpt-4o",
    tools=[close_dispute]
)

triage_agent = Agent(
    name="Triage Agent",
    instructions=(
        "Please do the following:\n"
        "1. Find the order ID from the payment intent's metadata.\n"
        "2. Retrieve detailed information about the order (e.g., shipping status).\n"
        "3. If the order has shipped, escalate this dispute to the investigator agent.\n"
        "4. If the order has not shipped, accept the dispute.\n"
    ),
    model="gpt-4o",
    tools=[retrieve_payment_intent, get_order],
    handoffs=[accept_dispute_agent, investigator_agent],
)
```

#### 取得 Dispute 並啟動 Agentic Workflow
這個函式用傳入的 `payment_intent_id` 從 Stripe 取得 dispute 詳情，再把資料交給指定的 `triage_agent`，啟動爭議處理流程。


```python
async def process_dispute(payment_intent_id, triage_agent):
    """Retrieve and process dispute data for a given PaymentIntent."""
    disputes_list = stripe.Dispute.list(payment_intent=payment_intent_id)
    if not disputes_list.data:
        logger.warning("No dispute data found for PaymentIntent: %s", payment_intent_id)
        return None
    
    dispute_data = disputes_list.data[0]
    
    relevant_data = {
        "dispute_id": dispute_data.get("id"),
        "amount": dispute_data.get("amount"),
        "due_by": dispute_data.get("evidence_details", {}).get("due_by"),
        "payment_intent": dispute_data.get("payment_intent"),
        "reason": dispute_data.get("reason"),
        "status": dispute_data.get("status"),
        "card_brand": dispute_data.get("payment_method_details", {}).get("card", {}).get("brand")
    }
    
    event_str = json.dumps(relevant_data)
    # Pass the dispute data to the triage agent
    result = await Runner.run(triage_agent, input=event_str)
    logger.info("WORKFLOW RESULT: %s", result.final_output)
    
    return relevant_data, result.final_output
```

#### 情境 1：公司出錯（商品沒收到）
這個情境是公司明顯有錯，例如沒出貨。這種情況通常直接接受爭議比較合理，不用去抗辯。

```python
payment = stripe.PaymentIntent.create(
  amount=2000,
  currency="usd",
  payment_method = "pm_card_createDisputeProductNotReceived",
  confirm=True,
  metadata={"order_id": "1234"},
  off_session=True,
  automatic_payment_methods={"enabled": True},
)
relevant_data, triage_result = await process_dispute(payment.id, triage_agent)
```

#### 情境 2：客人提出爭議（Final Sale）
這個情境是客人故意提爭議，但他其實收到正確商品，也清楚知道這筆明確標示為「final sale」（不退貨不退款）。這類爭議通常要進一步調查、蒐集證據，才能有效抗辯。

```python
payment = stripe.PaymentIntent.create(
  amount=2000,
  currency="usd",
  payment_method = "pm_card_createDispute",
  confirm=True,
  metadata={"order_id": "1121"},
  off_session=True,
  automatic_payment_methods={"enabled": True},
)
relevant_data, triage_result = await process_dispute(payment.id, triage_agent)
```

## 結論

這份 notebook 用 Python 優先的簡單做法，示範了怎麼用 **OpenAI Agents SDK** 建立 agent 應用。用到的 SDK 功能有：

- **Agent Loop**：處理 tool 呼叫、把結果回傳給 LLM，一直迴圈到完成。
- **Handoffs**：讓多個專責 agent 之間協調、分派工作。
- **Function Tools**：把 Python 函式轉成 tool，自動產生 schema 並驗證。

另外 SDK 內建 **Tracing**，可以在 OpenAI dashboard 看到，開發和上線時都能用來視覺化、除錯、監控 agent workflow，也能和 OpenAI 的 eval、fine-tuning、distillation 工具整合。

這份 notebook 沒有直接示範 **Guardrails**，但正式上線的應用強烈建議加上，用來驗證輸入並提早抓出錯誤。

整體來說，這份 notebook 打了個基礎，讓你看到 OpenAI Agents SDK 怎麼做出直覺又有效的 agent workflow。

## 重點整理

- Agent loop 會自動處理 tool 呼叫和結果回傳，直到任務完成，你不用自己寫迴圈。
- 把一個大流程拆成 triage、acceptance、investigator 三個專責 agent，每個的 instructions 都可以寫得很單純。
- Handoff 讓 triage agent 依訂單狀態決定下一棒交給誰。
- Function tool 的 schema 是從 Python 函式簽名自動產生，所以型別和 docstring 要寫清楚。
- 正式上線要加 guardrails，tracing 則幫你除錯和監控。

## 練習

1. 改 triage agent 的 instructions，讓它在訂單已出貨但追蹤顯示未送達時也走 investigator，再跑一次情境 1 看路線有沒有變。
2. 在 `get_order` 的模擬資料裡新增一筆訂單（例如部分退款），寫一個情境 3，觀察 triage agent 怎麼判斷。
3. 給 `close_dispute` 加一個 guardrail 或簡單的檢查（例如 dispute ID 格式不對就拒絕），確認 accept agent 遇到錯誤時的反應。
