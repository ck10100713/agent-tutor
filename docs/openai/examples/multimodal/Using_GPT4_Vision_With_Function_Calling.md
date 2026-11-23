---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/multimodal/Using_GPT4_Vision_With_Function_Calling.ipynb
---

# 用 GPT-4 Vision 搭配 Function Calling

> 原文：[examples/multimodal/Using_GPT4_Vision_With_Function_Calling.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/Using_GPT4_Vision_With_Function_Calling.ipynb)

## 這篇在做什麼
把圖片丟給 GPT-4o，再讓它透過 function calling 決定要呼叫哪個函式。範例有兩個：看包裹照片決定退款、換貨還是轉人工，以及讀組織圖抽出員工與主管的結構化資料。重點是這樣能做到的事超過單純 OCR 或圖片描述。

## 學完你會
- 把圖片編成 base64，連同 tool 定義一起送給 GPT-4o
- 用 Pydantic 定義 tool 的參數結構，讓模型依圖片內容選對 tool
- 把模型回傳的 tool call 解析成 DataFrame，處理組織圖這類結構化資料

## 開跑前
需要 OpenAI API key。

最新版的 GPT-4o（`gpt-4o-2024-11-20`，2024 年 11 月）支援帶圖片的 function calling，推理能力更好，知識截止日是 2023 年 10 月。圖片加上 function calling 可以開出多模態的應用，也能用上模型的推理，不只是 OCR 和圖片描述。

下面有兩個範例：

1. 模擬客服助理，處理配送異常
2. 分析組織圖，抽出員工資訊

### 安裝與設定

```python
!pip install pymupdf --quiet
!pip install openai --quiet
!pip install matplotlib --quiet
# instructor makes it easy to work with function calling
!pip install instructor --quiet
```

```python
import base64
import os
from enum import Enum
from io import BytesIO
from typing import Iterable
from typing import List
from typing import Literal, Optional

import fitz
# Instructor is powered by Pydantic, which is powered by type hints. Schema validation, prompting is controlled by type annotations
import instructor
import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import display
from PIL import Image
from openai import OpenAI
from pydantic import BaseModel, Field
```

??? note "輸出"

    ```text
    Matplotlib is building the font cache; this may take a moment.
    ```

## 1. 模擬客服助理處理配送異常
我們模擬一個配送服務的客服助理，它會看包裹照片，依照影像分析結果做事：
- 包裹看起來損壞，就依政策自動退款。
- 包裹看起來是濕的，就安排換貨。
- 包裹看起來正常沒損壞，就轉給真人客服。

先看看助理要分析的範例包裹圖片。我們會把圖片編成 base64 字串給模型處理。

```python
# Function to encode the image as base64
def encode_image(image_path: str):
    # check if the image exists
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Sample images for testing
image_dir = "images"

# encode all images within the directory
image_files = os.listdir(image_dir)
image_data = {}
for image_file in image_files:
    image_path = os.path.join(image_dir, image_file)
    # encode the image with key as the image file name
    image_data[image_file.split('.')[0]] = encode_image(image_path)
    print(f"Encoded image: {image_file}")


def display_images(image_data: dict):
    fig, axs = plt.subplots(1, 3, figsize=(18, 6))
    for i, (key, value) in enumerate(image_data.items()):
        img = Image.open(BytesIO(base64.b64decode(value)))
        ax = axs[i]
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(key)
    plt.tight_layout()
    plt.show()


display_images(image_data)
```

??? note "輸出"

    ```text
    Encoded image: wet_package.jpg
    Encoded image: damaged_package.jpg
    Encoded image: normal_package.jpg
    ```

圖片已經成功編成 base64 並顯示出來。助理會根據這些圖片判斷包裹狀況，決定該做什麼。

接著定義訂單處理用的函式 / tool：轉給客服、退款、換貨。這裡用 placeholder 函式模擬這些動作，資料結構用 Pydantic model 定義。


```python
MODEL = "gpt-4o-2024-11-20"

class Order(BaseModel):
    """Represents an order with details such as order ID, customer name, product name, price, status, and delivery date."""
    order_id: str = Field(..., description="The unique identifier of the order")
    product_name: str = Field(..., description="The name of the product")
    price: float = Field(..., description="The price of the product")
    status: str = Field(..., description="The status of the order")
    delivery_date: str = Field(..., description="The delivery date of the order")
# Placeholder functions for order processing

def get_order_details(order_id):
    # Placeholder function to retrieve order details based on the order ID
    return Order(
        order_id=order_id,
        product_name="Product X",
        price=100.0,
        status="Delivered",
        delivery_date="2024-04-10",
    )

def escalate_to_agent(order: Order, message: str):
    # Placeholder function to escalate the order to a human agent
    return f"Order {order.order_id} has been escalated to an agent with message: `{message}`"

def refund_order(order: Order):
    # Placeholder function to process a refund for the order
    return f"Order {order.order_id} has been refunded successfully."

def replace_order(order: Order):
    # Placeholder function to replace the order with a new one
    return f"Order {order.order_id} has been replaced with a new order."

class FunctionCallBase(BaseModel):
    rationale: Optional[str] = Field(..., description="The reason for the action.")
    image_description: Optional[str] = Field(
        ..., description="The detailed description of the package image."
    )
    action: Literal["escalate_to_agent", "replace_order", "refund_order"]
    message: Optional[str] = Field(
        ...,
        description="The message to be escalated to the agent if action is escalate_to_agent",
    )
    # Placeholder functions to process the action based on the order ID
    def __call__(self, order_id):
        order: Order = get_order_details(order_id=order_id)
        if self.action == "escalate_to_agent":
            return escalate_to_agent(order, self.message)
        if self.action == "replace_order":
            return replace_order(order)
        if self.action == "refund_order":
            return refund_order(order)

class EscalateToAgent(FunctionCallBase):
    """Escalate to an agent for further assistance."""
    pass

class OrderActionBase(FunctionCallBase):
    pass

class ReplaceOrder(OrderActionBase):
    """Tool call to replace an order."""
    pass

class RefundOrder(OrderActionBase):
    """Tool call to refund an order."""
    pass
```

### 模擬使用者訊息並處理包裹圖片

我們模擬帶有包裹圖片的使用者訊息，交給 GPT-4o with Vision 處理。模型會依圖片分析結果，對應到損壞、潮濕或正常這三種預先定義的動作，選出該呼叫的 tool。之後我們再依訂單 ID 執行這個動作並顯示結果。

```python
# extract the tool call from the response
ORDER_ID = "12345"  # Placeholder order ID for testing
INSTRUCTION_PROMPT = "You are a customer service assistant for a delivery service, equipped to analyze images of packages. If a package appears damaged in the image, automatically process a refund according to policy. If the package looks wet, initiate a replacement. If the package appears normal and not damaged, escalate to agent. For any other issues or unclear images, escalate to agent. You must always use tools!"

def delivery_exception_support_handler(test_image: str):
    payload = {
        "model": MODEL,
        "response_model": Iterable[RefundOrder | ReplaceOrder | EscalateToAgent],
        "tool_choice": "auto",  # automatically select the tool based on the context
        "temperature": 0.0,  # for less diversity in responses
        "seed": 123,  # Set a seed for reproducibility
    }
    payload["messages"] = [
        {
            "role": "user",
            "content": INSTRUCTION_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data[test_image]}"
                    }
                },
            ],
        }
    ]
    function_calls = instructor.from_openai(
        OpenAI(), mode=instructor.Mode.PARALLEL_TOOLS
    ).chat.completions.create(**payload)

    for tool in function_calls:
        print(f"- Tool call: {tool.action} for provided img: {test_image}")
        print(f"- Parameters: {tool}")
        print(f">> Action result: {tool(ORDER_ID)}")
        return tool


print("Processing delivery exception support for different package images...")

print("\n===================== Simulating user message 1 =====================")
assert delivery_exception_support_handler("damaged_package").action == "refund_order"

print("\n===================== Simulating user message 2 =====================")
assert delivery_exception_support_handler("normal_package").action == "escalate_to_agent"

print("\n===================== Simulating user message 3 =====================")
assert delivery_exception_support_handler("wet_package").action == "replace_order"
```

??? note "輸出"

    ```text
    Processing delivery exception support for different package images...

    ===================== Simulating user message 1 =====================
    - Tool call: refund_order for provided img: damaged_package
    - Parameters: rationale='The package appears damaged as it is visibly crushed and deformed.' image_description='A package that is visibly crushed and deformed, with torn and wrinkled packaging material.' action='refund_order' message=None
    >> Action result: Order 12345 has been refunded successfully.

    ===================== Simulating user message 2 =====================
    - Tool call: escalate_to_agent for provided img: normal_package
    - Parameters: rationale='The package appears normal and undamaged in the image.' image_description='A cardboard box placed on a wooden floor, showing no visible signs of damage or wetness.' action='escalate_to_agent' message='The package appears normal and undamaged. Please review further.'
    >> Action result: Order 12345 has been escalated to an agent with message: `The package appears normal and undamaged. Please review further.`

    ===================== Simulating user message 3 =====================
    - Tool call: replace_order for provided img: wet_package
    - Parameters: rationale='The package appears wet, which may compromise its contents.' image_description="A cardboard box labeled 'Fragile' with visible wet spots on its surface." action='replace_order' message=None
    >> Action result: Order 12345 has been replaced with a new order.
    ```

## 2. 分析組織圖，抽出員工資訊

第二個範例要分析一張組織圖，抽出員工姓名、職稱、主管和主管職稱。我們用 GPT-4o with Vision 處理組織圖，抽出組織裡員工的結構化資料。function calling 讓我們不只是做 OCR，而是真的推論並轉換圖裡的階層關係。

先拿一份 PDF 格式的組織圖範例，把第一頁轉成 JPEG 圖片來分析。

```python
# Function to convert a single page PDF page to a JPEG image
def convert_pdf_page_to_jpg(pdf_path: str, output_path: str, page_number=0):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_number)  # 0 is the first page
    pix = page.get_pixmap()
    # Save the pixmap as a JPEG
    pix.save(output_path)


def display_img_local(image_path: str):
    img = Image.open(image_path)
    display(img)


pdf_path = 'data/org-chart-sample.pdf'
output_path = 'org-chart-sample.jpg'

convert_pdf_page_to_jpg(pdf_path, output_path)
display_img_local(output_path)
```

組織圖已經從 PDF 抽出並顯示。接下來定義一個函式，用 GPT-4o with Vision 分析這張圖，抽出員工、職稱、主管的資訊。我們用 function / tool calling 指定組織結構的輸入參數，像是員工姓名、職稱、主管姓名和主管職稱，資料結構一樣用 Pydantic model 定義。


```python
base64_img = encode_image(output_path)

class RoleEnum(str, Enum):
    """Defines possible roles within an organization."""
    CEO = "CEO"
    CTO = "CTO"
    CFO = "CFO"
    COO = "COO"
    EMPLOYEE = "Employee"
    MANAGER = "Manager"
    INTERN = "Intern"
    OTHER = "Other"

class Employee(BaseModel):
    """Represents an employee, including their name, role, and optional manager information."""
    employee_name: str = Field(..., description="The name of the employee")
    role: RoleEnum = Field(..., description="The role of the employee")
    manager_name: Optional[str] = Field(None, description="The manager's name, if applicable")
    manager_role: Optional[RoleEnum] = Field(None, description="The manager's role, if applicable")


class EmployeeList(BaseModel):
    """A list of employees within the organizational structure."""
    employees: List[Employee] = Field(..., description="A list of employees")

def parse_orgchart(base64_img: str) -> EmployeeList:
    response = instructor.from_openai(OpenAI()).chat.completions.create(
        model=MODEL,
        response_model=EmployeeList,
        messages=[
            {
                "role": "user",
                "content": 'Analyze the given organizational chart and very carefully extract the information.',
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_img}"
                        }
                    },
                ],
            }
        ],
    )
    return response
```

再來定義一個函式，解析 GPT-4o 的回應、取出員工資料，並整理成表格方便檢視。注意抽出資料的準確度會受圖片複雜度和清晰度影響。

```python
# call the functions to analyze the organizational chart and parse the response
result = parse_orgchart(base64_img)

# tabulate the extracted data
df = pd.DataFrame([{
    'employee_name': employee.employee_name,
    'role': employee.role.value,
    'manager_name': employee.manager_name,
    'manager_role': employee.manager_role.value if employee.manager_role else None
} for employee in result.employees])

display(df)
```

??? note "輸出"

    ```text
          employee_name      role   manager_name manager_role
    0     Juliana Silva       CEO           None         None
    1      Kim Chun Hei       CFO  Juliana Silva          CEO
    2       Cahaya Dewi   Manager   Kim Chun Hei          CFO
    3         Drew Feig  Employee    Cahaya Dewi      Manager
    4   Richard Sanchez  Employee    Cahaya Dewi      Manager
    5      Sacha Dubois    Intern    Cahaya Dewi      Manager
    6      Chad Gibbons       CTO  Juliana Silva          CEO
    7      Shawn Garcia   Manager   Chad Gibbons          CTO
    8     Olivia Wilson  Employee   Shawn Garcia      Manager
    9        Matt Zhang    Intern   Shawn Garcia      Manager
    10      Chiaki Sato       COO  Juliana Silva          CEO
    11       Aaron Loeb   Manager    Chiaki Sato          COO
    12      Avery Davis  Employee     Aaron Loeb      Manager
    13     Harper Russo  Employee     Aaron Loeb      Manager
    14    Taylor Alonso    Intern     Aaron Loeb      Manager
    ```

組織圖的資料已經解析完成，顯示在 DataFrame 裡。這個做法讓我們用 GPT-4o 的視覺能力從圖片（像組織圖、流程圖）抽出結構化資訊，再拿去做後續分析。靠 function calling，多模態模型可以擴充去做特定任務或呼叫外部函式。

## 重點整理
- GPT-4o 可以在同一個請求裡同時吃圖片和 tool 定義，讓模型依圖片內容選 tool。
- 圖片要以 base64 等形式編碼後放進 message。
- 用 Pydantic 定義 tool 參數，能讓抽出的資料結構穩定，後面好處理。
- function calling 讓視覺模型做的事超過 OCR，能推論圖裡的關係，例如組織階層。
- 抽取準確度會受圖片品質影響，重要場景要驗證結果。

## 練習
1. 在客服範例裡多加一個 tool，例如「通知物流重新配送」，並用一張新圖測試模型會不會選到它。
2. 把組織圖範例的 Pydantic model 加一個欄位（例如部門），看抽出的 DataFrame 有沒有多一欄。
3. 把兩個範例合併：先用組織圖抽出的資料，決定退款案件該轉給哪位主管。
