---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Using_tool_required_for_customer_service.ipynb
---
# 用 tool_choice required 做客服 agent

> 原文：[examples/Using_tool_required_for_customer_service.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Using_tool_required_for_customer_service.ipynb)



## 這篇在做什麼
這篇示範在 Chat Completions 加上 `tool_choice='required'`，強制模型每次都要呼叫某個 tool，用它建出一個有明確出口的客服流程。最後再用另一個 GPT 扮演客戶，跟客服 agent 多輪對話，當作自動化測試。

## 學完你會
- 用 `tool_choice='required'` 讓每次呼叫都保證拿到 tool call，寫出更可預期的外層程式
- 定義 `tools` 和 `instructions`，讓客服 agent 依客戶問題取得對應的處理指示
- 寫一個 `execute_conversation`，用客戶 GPT 跟客服 agent 多輪對話來評測

## 開跑前
需要 OpenAI API key。

`ChatCompletion` endpoint 現在可以指定每次都**必須**呼叫 tool，做法是加上 `tool_choice='required'` 這個參數。

這讓你的外層應用程式更有確定性，因為你可以確定每次呼叫都會拿到 tool。這裡我們會示範，在客服這種範圍明確的流程中，這有什麼用處：能定義明確的出口，就多一分掌控。

notebook 最後是一個多輪評測：我們啟動一個客戶 GPT 來模仿客戶，測試我們設定好的 LLM 客服 agent。

```python
import json
from openai import OpenAI
import os

client = OpenAI()
GPT_MODEL = 'gpt-4-turbo'
```

## 設定定義

我們會定義客服 LLM agent 要用的 `tools` 和 `instructions`。它會針對客戶遇到的問題找出對應的指示，並用這些指示回答客戶的問題。

這只是示範範例，所以在沒有外部系統可以取得資訊的地方，我們會請模型自己編出數值。

```python
# The tools our customer service LLM will use to communicate
tools = [
{
  "type": "function",
  "function": {
    "name": "speak_to_user",
    "description": "Use this to speak to the user to give them information and to ask for anything required for their case.",
    "parameters": {
      "type": "object",
      "properties": {
        "message": {
          "type": "string",
          "description": "Text of message to send to user. Can cover multiple topics."
        }
      },
      "required": ["message"]
    }
  }
},
{
  "type": "function",
  "function": {
    "name": "get_instructions",
    "description": "Used to get instructions to deal with the user's problem.",
    "parameters": {
      "type": "object",
      "properties": {
        "problem": {
          "type": "string",
          "enum": ["fraud","refund","information"],
          "description": """The type of problem the customer has. Can be one of:
          - fraud: Required to report and resolve fraud.
          - refund: Required to submit a refund request.
          - information: Used for any other informational queries."""
        }
      },
      "required": [
        "problem"
      ]
    }
  }
}
]

# Example instructions that the customer service assistant can consult for relevant customer problems
INSTRUCTIONS = [ {"type": "fraud",
                  "instructions": """• Ask the customer to describe the fraudulent activity, including the the date and items involved in the suspected fraud.
• Offer the customer a refund.
• Report the fraud to the security team for further investigation.
• Thank the customer for contacting support and invite them to reach out with any future queries."""},
                {"type": "refund",
                 "instructions": """• Confirm the customer's purchase details and verify the transaction in the system.
• Check the company's refund policy to ensure the request meets the criteria.
• Ask the customer to provide a reason for the refund.
• Submit the refund request to the accounting department.
• Inform the customer of the expected time frame for the refund processing.
• Thank the customer for contacting support and invite them to reach out with any future queries."""},
                {"type": "information",
                 "instructions": """• Greet the customer and ask how you can assist them today.
• Listen carefully to the customer's query and clarify if necessary.
• Provide accurate and clear information based on the customer's questions.
• Offer to assist with any additional questions or provide further details if needed.
• Ensure the customer is satisfied with the information provided.
• Thank the customer for contacting support and invite them to reach out with any future queries.""" }]
```

```python
assistant_system_prompt = """You are a customer service assistant. Your role is to answer user questions politely and competently.
You should follow these instructions to solve the case:
- Understand their problem and get the relevant instructions.
- Follow the instructions to solve the customer's problem. Get their confirmation before performing a permanent operation like a refund or similar.
- Help them with any other problems or close the case.

Only call a tool once in a single message.
If you need to fetch a piece of information from a system or document that you don't have access to, give a clear, confident answer with some dummy values."""

def submit_user_message(user_query,conversation_messages=[]):
    """Message handling function which loops through tool calls until it reaches one that requires a response.
    Once it receives respond=True it returns the conversation_messages to the user."""

    # Initiate a respond object. This will be set to True by our functions when a response is required
    respond = False
    
    user_message = {"role":"user","content": user_query}
    conversation_messages.append(user_message)

    print(f"User: {user_query}")

    while respond is False:

        # Build a transient messages object to add the conversation messages to
        messages = [
            {
                "role": "system",
                "content": assistant_system_prompt
            }
        ]

        # Add the conversation messages to our messages call to the API
        [messages.append(x) for x in conversation_messages]

        # Make the ChatCompletion call with tool_choice='required' so we can guarantee tools will be used
        response = client.chat.completions.create(model=GPT_MODEL
                                                  ,messages=messages
                                                  ,temperature=0
                                                  ,tools=tools
                                                  ,tool_choice='required'
                                                 )

        conversation_messages.append(response.choices[0].message)

        # Execute the function and get an updated conversation_messages object back
        # If it doesn't require a response, it will ask the assistant again. 
        # If not the results are returned to the user.
        respond, conversation_messages = execute_function(response.choices[0].message,conversation_messages)
    
    return conversation_messages

def execute_function(function_calls,messages):
    """Wrapper function to execute the tool calls"""

    for function_call in function_calls.tool_calls:
    
        function_id = function_call.id
        function_name = function_call.function.name
        print(f"Calling function {function_name}")
        function_arguments = json.loads(function_call.function.arguments)
    
        if function_name == 'get_instructions':

            respond = False
    
            instruction_name = function_arguments['problem']
            instructions = INSTRUCTIONS['type' == instruction_name]
    
            messages.append(
                                {
                                    "tool_call_id": function_id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": instructions['instructions'],
                                }
                            )
    
        elif function_name != 'get_instructions':

            respond = True
    
            messages.append(
                                {
                                    "tool_call_id": function_id,
                                    "role": "tool",
                                    "name": function_name,
                                    "content": function_arguments['message'],
                                }
                            )
    
            print(f"Assistant: {function_arguments['message']}")
    
    return (respond, messages)
```

## 範例

為了測試，我們會用一位遇到詐騙的客戶當例子，看模型怎麼處理。

請你扮演使用者，提供合理的下一步，讓對話持續下去。

```python
messages = submit_user_message("Hi, I have had an item stolen that was supposed to be delivered to me yesterday.")
```

??? note "輸出"

    ```text
    User: Hi, I have had an item stolen that was supposed to be delivered to me yesterday.
    Calling function get_instructions
    Calling function speak_to_user
    Assistant: I'm sorry to hear about the stolen item. Could you please provide me with more details about the fraudulent activity, including the date and the items involved? This information will help us to investigate the issue further and proceed with the necessary actions, including offering you a refund.
    ```

```python
messages = submit_user_message("For sure, it was a shirt, it was supposed to be delivered yesterday but it never arrived.",messages)
```

??? note "輸出"

    ```text
    User: For sure, it was a shirt, it was supposed to be delivered yesterday but it never arrived.
    Calling function speak_to_user
    Assistant: Thank you for providing the details. I will now proceed to report this incident to our security team for further investigation and arrange a refund for the stolen shirt. Please confirm if you would like me to go ahead with the refund.
    Calling function speak_to_user
    Assistant: Thank you for contacting us about this issue. Please don't hesitate to reach out if you have any more questions or need further assistance in the future.
    ```

```python
messages = submit_user_message("Yes I would like to proceed with the refund.",messages)
```

??? note "輸出"

    ```text
    User: Yes I would like to proceed with the refund.
    Calling function get_instructions
    Calling function speak_to_user
    Assistant: Thank you for confirming. I have processed the refund for the stolen shirt. The amount should be reflected in your account within 5-7 business days. If you have any more questions or need further assistance, please feel free to contact us.
    ```

```python
messages = submit_user_message("Thanks very much.",messages)
```

??? note "輸出"

    ```text
    User: Thanks very much.
    Calling function speak_to_user
    Assistant: You're welcome! If you need any more help in the future, don't hesitate to reach out. Have a great day!
    ```

## 評測

現在做一個簡單的評測：由一個 GPT 假裝成我們的客戶。兩邊來回對話，直到問題解決。

我們會重用上面的函式，並加上一個 `execute_conversation` 函式，讓客戶 GPT 繼續回答。

```python
customer_system_prompt = """You are a user calling in to customer service.
You will talk to the agent until you have a resolution to your query.
Your query is {query}.
You will be presented with a conversation - provide answers for any assistant questions you receive. 
Here is the conversation - you are the "user" and you are speaking with the "assistant":
{chat_history}

If you don't know the details, respond with dummy values.
Once your query is resolved, respond with "DONE" """

# Initiate a bank of questions run through
questions = ['I want to get a refund for the suit I ordered last Friday.',
            'Can you tell me what your policy is for returning damaged goods?',
            'Please tell me what your complaint policy is']
```

```python
def execute_conversation(objective):

    conversation_messages = []

    done = False

    user_query = objective

    while done is False:

        conversation_messages = submit_user_message(user_query,conversation_messages)

        messages_string = ''
        for x in conversation_messages:
            if isinstance(x,dict):
                if x['role'] == 'user':
                    messages_string += 'User: ' + x['content'] + '\n'
                elif x['role'] == 'tool':
                    if x['name'] == 'speak_to_user':
                        messages_string += 'Assistant: ' + x['content'] + '\n'
            else:
                continue

        messages = [
            {
            "role": "system",
            "content": customer_system_prompt.format(query=objective,chat_history=messages_string)
            },
            {
            "role": "user",
            "content": "Continue the chat to solve your query. Remember, you are in the user in this exchange. Do not provide User: or Assistant: in your response"
            }
        ]

        user_response = client.chat.completions.create(model=GPT_MODEL,messages=messages,temperature=0.5)

        conversation_messages.append({
            "role": "user",
            "content": user_response.choices[0].message.content
            })

        if 'DONE' in user_response.choices[0].message.content:
            done = True
            print("Achieved objective, closing conversation\n\n")

        else:
            user_query = user_response.choices[0].message.content
```

```python
for x in questions:

    execute_conversation(x)
```

??? note "輸出"

    ```text
    User: I want to get a refund for the suit I ordered last Friday.
    Calling function get_instructions
    Calling function speak_to_user
    Assistant: I understand you'd like a refund for the suit you ordered last Friday. Could you please provide more details about the issue with the suit? This will help us process your refund request accurately.
    User: The suit I received is not the color I ordered. I ordered a navy blue suit, but the one I received is black.
    Calling function speak_to_user
    Assistant: Thank you for providing the details. I will proceed with the refund for the navy blue suit that was incorrectly sent as black. Please confirm if you would like me to go ahead with the refund.
    User: Yes, please go ahead with the refund.
    Calling function speak_to_user
    Assistant: The refund for the incorrectly colored suit has been processed. You should see the amount credited back to your original payment method within 5-7 business days. Thank you for contacting us, and if you have any more questions or need further assistance, please feel free to reach out.
    Achieved objective, closing conversation


    User: Can you tell me what your policy is for returning damaged goods?
    Calling function get_instructions
    Calling function speak_to_user
    Assistant: It seems there was a misunderstanding in my previous request. I'm looking for information on our policy for returning damaged goods. Could you please provide me with the details on how to handle returns for damaged items?
    User: Yes, I'd appreciate that. Could you please tell me the steps I need to follow to return a damaged item?
    Calling function get_instructions
    Calling function speak_to_user
    Assistant: I apologize for the confusion earlier. Here's the correct information regarding our policy for returning damaged goods:

    1. Please provide a description of the damage and the item involved.
    2. Include the date of purchase and your order number if available.
    3. You can choose to return the item by mail or in person at one of our stores. Please let us know which method you prefer, and we will provide the necessary details for the return process.
    4. Once we receive the item, we will inspect it and process a refund or exchange based on your preference and our return policy guidelines.

    Please let me know if you need further assistance with this process or if there's anything else I can help you with!
    User: I would like to return the item by mail. Could you please provide me with the details on how to do that?
    Calling function speak_to_user
    Assistant: Certainly! To return the damaged item by mail, please follow these steps:

    1. Pack the item securely in its original packaging, if possible.
    2. Include all original materials such as manuals, accessories, and receipts.
    3. Address the package to our returns department at the following address:
       [Your Company's Return Address]
    4. Use a trackable shipping service and keep the tracking number for your records.
    5. Once we receive and inspect the item, we will process your refund or exchange as per your request.

    Please let me know if you need a prepaid shipping label or any other assistance with your return!
    ... (省略 30 行)
    ```

## 結論

現在你可以讓 tool 使用變成必要，明確控制 LLM 的行為，也可以啟動 GPT 測試員來挑戰你的 LLM，當作自動化的測試案例。

希望這份內容讓你體會到 tool use 的一個很好的應用情境，也期待看到你做出什麼。

## 重點整理
- `tool_choice='required'` 保證每次回應都包含 tool call，外層程式不用處理「模型沒呼叫 tool」的情況。
- 把「結束對話」之類的出口也做成 tool，流程的終點就由 tool call 明確決定。
- 用 instructions 查詢 tool 取得對應問題的處理步驟，可以讓 agent 依情境切換行為。
- 用另一個 GPT 扮演客戶，是低成本的多輪自動化測試做法。

## 練習
1. 把 `tool_choice` 改成 `'auto'` 跑同一段對話，觀察模型什麼時候不呼叫 tool。
2. 在 `tools` 裡新增一個處理「退款」問題的 instructions 項目，並用客戶 GPT 測試它會不會被正確選到。
3. 修改客戶 GPT 的 system prompt，讓它扮演更不配合的客戶，看客服 agent 能否仍然走到結束 tool。
