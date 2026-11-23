---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/partners/eval_driven_system_design/receipt_inspection.ipynb
---
# Eval Driven System Design - 從原型到上線

> 原文：[examples/partners/eval_driven_system_design/receipt_inspection.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/eval_driven_system_design/receipt_inspection.ipynb)

用 eval 驅動設計，打造一個自動解析收據的工作流程。

## 這篇在做什麼

用一個「收據審核」的例子，示範怎麼把 eval 當成核心流程，從只有一小撮資料的原型，一路做到可上線的自動化系統。過程中會串起 eval、商業指標（成本、漏審損失）和系統改進，告訴你哪些指標值得花時間改。

## 學完你會

- 用兩段式 LLM pipeline（抽取收據資訊、再判斷要不要稽核）做出 V0 系統
- 設計 grader 和 eval，並用簡單的成本模型把 eval 分數換算成金額
- 依商業影響決定先改哪個問題，再用 eval 驗證 prompt 與換模型的效果

## 開跑前

需要 OpenAI API key（會呼叫模型和 Evals），跑 eval 會有費用。

## Overview

### 這本 Cookbook 的目的

這本 cookbook 提供一份**實務**、端到端的指南，說明怎麼把 eval 當成核心流程，打造一個能上線的自主系統，取代耗費人力的人工流程。內容來自實際專案的合作經驗，這些專案的使用者往往一開始沒有乾淨的標註資料，也沒完全搞懂問題，而大多數教學都略過這兩點，實務上卻幾乎一定會碰到。

把 eval 當核心，就不會憑感覺亂試、靠印象判斷準確度，而是用工程的標準做事。這樣我們才能針對成本取捨和投資做有根據的決定。

### 目標讀者

這份指南寫給 ML/AI 工程師和 Solution Architect，適合想看入門教學之外實務做法的人。這個 notebook 可以完整執行，也盡量模組化，方便你直接把程式碼拿去用在自己的應用。

### 主軸：從小種子長成上線系統

我們會跟著一個很實際的故事走：取代一個人工審核費用收據的服務。

* **從小開始：** 只用一小批標註好的資料（零售收據）起步。很多公司手上並沒有好的 ground truth 資料集。
* **逐步建構：** 先做出最小可行系統，建立第一批 eval。
* **對齊商業目標：** 把 eval 的表現放到商業 KPI 和金額影響下來看，避免把力氣花在影響很小的改進上。
* **Eval 驅動迭代：** 用 eval 分數推動模型改進，再用更好的模型處理更多資料，擴充 eval 並找出更多可改進的地方。

### 怎麼使用這本 Cookbook

這本 cookbook 以 eval 為主線，走過 LLM 應用的整個生命週期。

1. 如果你只對概念有興趣，讀文字、快速掃過程式碼就好。
2. 如果你是因為手上有別的專案才來，可以直接跳到相關章節，看裡面的程式碼，複製後改成自己需要的樣子。
3. 如果你想真的搞懂整個運作，就下載這個 notebook，邊讀邊執行 cell，改程式、驗證自己的假設，確定自己真的理解各部分怎麼串在一起。

> Note：如果你的 OpenAI organization 有 Zero Data Retention (ZDR) 政策，Evals 還是能用，但會保留資料來維持應用狀態。

## 使用情境：收據解析

為了讓篇幅精簡，我們用一個小型的假想問題，但它還是複雜到值得做多面向的 eval。重點放在資料量有限時怎麼解決問題，所以資料集很小。

### 問題定義

假設我們現在有一個審核並歸檔收據的流程。這類問題已經有很多成熟的解法，但它跟其他沒什麼前人經驗的問題很像；而且就算有不錯的企業方案，通常還是有「最後一哩路」需要人來處理。

我們假設現有的流程是：

* 使用者上傳收據照片
* 會計團隊逐張審核，分類並決定核准或稽核這筆費用

訪談會計團隊後，他們的判斷依據是

1. 商家
2. 地理位置
3. 費用金額
4. 購買的品項或服務
5. 手寫的備註或標記

我們的系統要能在沒有人工介入下處理大部分收據，信心不足的決定則交給人工 QA。目標是降低整個會計流程的總成本，這取決於

1. 以前或現在的系統每張收據的處理成本
2. 新系統會把多少收據送去 QA
3. 新系統每張收據的執行成本，加上固定成本
4. 犯錯的商業影響，不論是被退回審核的收據，還是漏掉的錯誤
5. 開發與整合系統的工程成本

### 資料集概覽

收據圖片來自 Roboflow 發布、CC by 4.0 授權的
[Receipt Handwriting Detection Computer Vision Project](https://universe.roboflow.com/newreceipts/receipt-handwriting-detection)
資料集。我們加上自己的標註和故事設定，用少量範例來講一個完整的流程。

## 專案生命週期

每個專案的走法不盡相同，但通常都有一些重要的共通環節。

![Project Lifecycle](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_project_lifecycle.png)

實線箭頭是主要的進展步驟，虛線代表對問題的理解是持續進行的，對客戶領域了解越多，就會影響流程中的每一步。下面會詳細看其中幾個反覆精進的循環。

### 1. 理解問題

通常是由理解商業影響、但不需要知道流程細節的主管決定啟動工程。在我們的例子裡，要做的系統是取代一個非 AI 的工作流程，這算是理想狀況：我們有一群領域專家，也就是*現在正在做這件事的人*，可以訪談他們了解任務細節，也能請他們協助設計合適的 eval。

這一步不會在開始做系統之前就結束。我們最初的評估一定不完整，越接近解法，對問題的理解就會越深。

### 2. 蒐集範例（收集資料）

真實專案很少一開始就有足夠的資料能做出令人滿意的解法，更別說建立信心了。

在我們的情況，假設手上有不錯的系統*輸入*樣本，也就是收據圖片，但一開始沒有任何完整標註的資料。要自動化既有流程時，這種狀況很常見。我們會和領域專家合作，一邊做一邊逐步擴充測試集和訓練集，讓 eval 越來越完整。

### 3. 建立端到端的 V0 系統

要盡快把系統骨架做出來。不需要表現好，只要能接收正確的輸入、產出正確型別的輸出就行。通常做法很簡單：在 prompt 裡描述任務、加上輸入，用單一模型（通常搭配 structured outputs）做一次盡力的初步嘗試。

### 4. 標註資料並建立初始 eval

沒有既定 ground truth 時，常見的做法是用系統的早期版本產生「草稿」答案，再交給領域專家標註或修正。

端到端系統建好後，就能拿手上的輸入跑出合理的輸出，送給領域專家評分並修正。我們會用這些修正，以及和專家討論他們怎麼做決定的內容，來設計更多 eval，並把專業知識放進系統裡。

### 5. 把 eval 對應到商業指標

在開始逐一修正錯誤之前，要先確定時間花得有效率。這個階段最重要的工作，是檢視 eval，搞清楚它們跟我們的主要目標有什麼關係。

- 退一步評估系統可能帶來的成本和效益
- 找出哪些 eval 量測直接對應到這些成本和效益
- 例如：某個 eval 失敗一次要付出多少成本？我們量的東西值得量嗎？
- 建立一個（非 LLM 的）模型，用 eval 指標算出金額
- 在效能（準確度或速度）和開發、執行成本之間取得平衡

### 6. 逐步改進系統和 eval

知道哪些努力最值得之後，就可以開始迭代改進系統。eval 是客觀的指引，讓我們知道系統何時夠好，也能避免或發現退步。

### 7. 整合 QA 流程與持續改進

eval 不只用在開發階段。在正式服務中全部或部分埋點，會隨著時間浮現更多有用的測試和訓練樣本，找出錯誤的假設或覆蓋不足的地方。這也是確保模型在初期開發結束很久之後仍然表現良好的唯一辦法。

## V0 系統建構

實務上我們可能會做一個透過 REST API 運作的系統，也許搭配一個能存取一組元件與資源的網頁前端。這本 cookbook 把它簡化成兩個函式，`extract_receipt_details` 和 `evaluate_receipt_for_audit`，合起來決定一張收據該怎麼處理。

- `extract_receipt_details` 以圖片為輸入，產出包含收據重要資訊的 structured output。
- `evaluate_receipt_for_audit` 以那個結構為輸入，決定這張收據該不該稽核。

> 把流程拆成這樣的步驟有好有壞。步驟小又獨立，比較容易檢查和開發，但資訊可能一路流失，等於讓 agent 在玩「傳話遊戲」。這個 notebook 刻意拆開步驟，也不讓稽核端看到真正的收據，因為這樣更適合講解我們要談的 eval。

先從第一步，也就是實際的資料抽取開始。這是*中間*資料：人其實會在腦中看過這些資訊，但通常不會記錄下來，所以我們往往沒有標註資料可用。

```python
%pip install --upgrade openai pydantic python-dotenv rich persist-cache -qqq
%load_ext dotenv
%dotenv

# Place your API key in a file called .env
# OPENAI_API_KEY=sk-...
```

### Structured Output Model

用 structured output 擷取有意義的資訊。

```python
from pydantic import BaseModel


class Location(BaseModel):
    city: str | None
    state: str | None
    zipcode: str | None


class LineItem(BaseModel):
    description: str | None
    product_code: str | None
    category: str | None
    item_price: str | None
    sale_price: str | None
    quantity: str | None
    total: str | None


class ReceiptDetails(BaseModel):
    merchant: str | None
    location: Location
    time: str | None
    items: list[LineItem]
    subtotal: str | None
    tax: str | None
    total: str | None
    handwritten_notes: list[str]
```

> *Note*：正常情況下，上面的數字應該用 `decimal.Decimal`，`time` 欄位應該用 `datetime.datetime`，但這兩種型別反序列化的效果都不好。這本 cookbook 先用字串處理，實務上你會需要再多一層轉換，來驗證出正確的輸出。

### 基本資訊抽取

來建立 `extract_receipt_details` 函式。

第一次嘗試通常是把手上已有的文件直接餵給 ChatGPT，請它產生一個 prompt。在還沒有 benchmark 可以對照之前，不值得花太多時間調 prompt！下面這個 prompt 是 o4-mini 根據上面的問題描述產生的。

```python
BASIC_PROMPT = """
Given an image of a retail receipt, extract all relevant information and format it as a structured response.

# Task Description

Carefully examine the receipt image and identify the following key information:

1. Merchant name and any relevant store identification
2. Location information (city, state, ZIP code)
3. Date and time of purchase
4. All purchased items with their:
   * Item description/name
   * Item code/SKU (if present)
   * Category (infer from context if not explicit)
   * Regular price per item (if available)
   * Sale price per item (if discounted)
   * Quantity purchased
   * Total price for the line item
5. Financial summary:
   * Subtotal before tax
   * Tax amount
   * Final total
6. Any handwritten notes or annotations on the receipt (list each separately)

## Important Guidelines

* If information is unclear or missing, return null for that field
* Format dates as ISO format (YYYY-MM-DDTHH:MM:SS)
* Format all monetary values as decimal numbers
* Distinguish between printed text and handwritten notes
* Be precise with amounts and totals
* For ambiguous items, use your best judgment based on context

Your response should be structured and complete, capturing all available information
from the receipt.
"""
```

```python
import base64
import mimetypes
from pathlib import Path

from openai import AsyncOpenAI

client = AsyncOpenAI()


async def extract_receipt_details(
    image_path: str, model: str = "o4-mini"
) -> ReceiptDetails:
    """Extract structured details from a receipt image."""
    # Determine image type for data URI.
    mime_type, _ = mimetypes.guess_type(image_path)

    # Read and base64 encode the image.
    b64_image = base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")
    image_data_url = f"data:{mime_type};base64,{b64_image}"

    response = await client.responses.parse(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": BASIC_PROMPT},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
        text_format=ReceiptDetails,
    )

    return response.output_parsed
```

### 測試單張收據

先只評估一張收據，手動檢查，看看聰明的模型搭配陽春的 prompt 能做到什麼程度。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/Supplies_20240322_220858_Raven_Scan_3_jpeg.rf.50852940734939c8838819d7795e1756.jpg" alt="Walmart_image" width="400"/>

```python
from rich import print

receipt_image_dir = Path("data/test")
ground_truth_dir = Path("data/ground_truth")

example_receipt = Path(
    "data/train/Supplies_20240322_220858_Raven_Scan_3_jpeg.rf.50852940734939c8838819d7795e1756.jpg"
)
result = await extract_receipt_details(example_receipt)
```

重跑一次會得到不同的答案，但通常大部分都對，只有少數錯誤。這是一個具體的例子：

```python
walmart_receipt = ReceiptDetails(
    merchant="Walmart",
    location=Location(city="Vista", state="CA", zipcode="92083"),
    time="2023-06-30T16:40:45",
    items=[
        LineItem(
            description="SPRAY 90",
            product_code="001920056201",
            category=None,
            item_price=None,
            sale_price=None,
            quantity="2",
            total="28.28",
        ),
        LineItem(
            description="LINT ROLLER 70",
            product_code="007098200355",
            category=None,
            item_price=None,
            sale_price=None,
            quantity="1",
            total="6.67",
        ),
        LineItem(
            description="SCRUBBER",
            product_code="003444193232",
            category=None,
            item_price=None,
            sale_price=None,
            quantity="2",
            total="12.70",
        ),
        LineItem(
            description="FLOUR SACK 10",
            product_code="003444194263",
            category=None,
            item_price=None,
            sale_price=None,
            quantity="1",
            total="0.77",
        ),
    ],
    subtotal="50.77",
    tax="4.19",
    total="54.96",
    handwritten_notes=[],
)
```

模型抽對了很多東西，但把部分品項改了名稱，而且改錯了。更重要的是，有些價格抽錯，也決定不替任何品項分類。

這沒關係，我們現在本來就不期待有完美的答案！目標是先做出一個可以評估的基本系統。這樣開始迭代時，就不是憑「感覺」把東西弄得*看起來*更好，而是在打造可靠的解法。不過在那之前，先加上稽核決策，把草稿系統補完整。

### Action Decision

接著要把流程收尾，根據收據做出實際的決定。寫法跟前面很像，所以直接給程式碼，不多做說明。

一般會先用最強的模型（目前是 `o3`）做第一版，確認正確性之後，再試不同的模型，分析各種取捨對業務的影響，並考慮這些落差能不能靠迭代補救。客戶可能願意為了更低的延遲或成本犧牲一點準確度，也可能改架構比較能同時達成成本、延遲和準確度目標。後面會說明怎麼明確、客觀地做這些取捨。

對這本 cookbook 來說，`o3` 可能太強了。我們第一版用 `o4-mini`，這樣會出現一些 reasoning 錯誤，正好拿來示範發生時怎麼處理。

接著要把流程收尾，根據收據做出實際的決定。寫法跟前面很像，所以直接給程式碼，不多做說明。

```python
from pydantic import BaseModel, Field

audit_prompt = """
Evaluate this receipt data to determine if it need to be audited based on the following
criteria:

1. NOT_TRAVEL_RELATED:
   - IMPORTANT: For this criterion, travel-related expenses include but are not limited
   to: gas, hotel, airfare, or car rental.
   - If the receipt IS for a travel-related expense, set this to FALSE.
   - If the receipt is NOT for a travel-related expense (like office supplies), set this
   to TRUE.
   - In other words, if the receipt shows FUEL/GAS, this would be FALSE because gas IS
   travel-related.

2. AMOUNT_OVER_LIMIT: The total amount exceeds $50

3. MATH_ERROR: The math for computing the total doesn't add up (line items don't sum to
   total)

4. HANDWRITTEN_X: There is an "X" in the handwritten notes

For each criterion, determine if it is violated (true) or not (false). Provide your
reasoning for each decision, and make a final determination on whether the receipt needs
auditing. A receipt needs auditing if ANY of the criteria are violated.

Return a structured response with your evaluation.
"""


class AuditDecision(BaseModel):
    not_travel_related: bool = Field(
        description="True if the receipt is not travel-related"
    )
    amount_over_limit: bool = Field(description="True if the total amount exceeds $50")
    math_error: bool = Field(description="True if there are math errors in the receipt")
    handwritten_x: bool = Field(
        description="True if there is an 'X' in the handwritten notes"
    )
    reasoning: str = Field(description="Explanation for the audit decision")
    needs_audit: bool = Field(
        description="Final determination if receipt needs auditing"
    )


async def evaluate_receipt_for_audit(
    receipt_details: ReceiptDetails, model: str = "o4-mini"
) -> AuditDecision:
    """Determine if a receipt needs to be audited based on defined criteria."""
    # Convert receipt details to JSON for the prompt
    receipt_json = receipt_details.model_dump_json(indent=2)

    response = await client.responses.parse(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": audit_prompt},
                    {"type": "input_text", "text": f"Receipt details:\n{receipt_json}"},
                ],
            }
        ],
        text_format=AuditDecision,
    )

    return response.output_parsed
```

整個流程的示意圖，包含兩次 LLM 呼叫：

![Process Flowchart](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_process_flowchart.png)

把上面的範例丟進這個流程，會得到下面的結果。一樣只是範例結果，你自己跑可能會有些微不同。

```python
audit_decision = await evaluate_receipt_for_audit(result)
print(audit_decision)
```

```python
audit_decision = AuditDecision(
    not_travel_related=True,
    amount_over_limit=True,
    math_error=False,
    handwritten_x=False,
    reasoning="""
    The receipt from Walmart is for office supplies, which are not travel-related, thus NOT_TRAVEL_RELATED is TRUE.
    The total amount of the receipt is $54.96, which exceeds the limit of $50, making AMOUNT_OVER_LIMIT TRUE.
    The subtotal ($50.77) plus tax ($4.19) correctly sums to the total ($54.96), so there is no MATH_ERROR.
    There are no handwritten notes, so HANDWRITTEN_X is FALSE.
    Since two criteria (amount over limit and travel-related) are violated, the receipt
    needs auditing.
    """,
    needs_audit=True,
)
```

這個例子說明了為什麼我們需要端到端的 eval，也說明它不能單獨使用。這裡一開始的抽取有 OCR 錯誤，把加起來跟總額對不上的價格傳給稽核端，稽核端沒發現，還說沒有計算錯誤。不過漏掉這點並不會改變稽核決定，因為它抓到了另外兩個需要稽核這張收據的理由。

所以 `AuditDecision` 本身事實上是錯的，但我們在意的那個決定是對的。這給了我們可以改進的切入點，也引導我們判斷工程力氣該放在哪裡、什麼時候放。

接下來，來建立 eval 吧！

## 初始 Eval

有了最基本能運作的系統之後，就該處理更多輸入，請領域專家協助建立 ground-truth 資料。做專業工作的領域專家能花在我們專案上的時間不多，所以要有效率，先求廣、不求深。

> 如果你的資料*不需要*領域專業知識，就該用標註工具（例如 [Label Studio](https://labelstud.io/)），在政策、預算和資料可用性的限制內盡量多標註資料。
> 這裡我們假設標註資源很稀缺，每週只能仰賴一小段時間，這些人還有其他工作，時間和意願都有限。和這些專家坐下來一起標註範例，也有助於之後更有效率地挑選範例。

因為我們有兩步的鏈，要收集的是型別為 `[FilePath, ReceiptDetails, AuditDecision]` 的 tuple。一般做法是拿未標註的樣本，跑過我們的模型，再讓專家修正輸出。在這個 notebook 裡，`data/test` 下所有收據圖片都已經做完這個流程。

### 其他考量

事情還不只這樣，因為評估多步驟流程時，除了端到端的表現，也要知道每個步驟*在前一步輸出的條件下*各自的表現。

這裡我們要評估：

1. 給定輸入圖片，我們抽取所需資訊的能力有多好？
2. 給定收據資訊，我們對稽核決定的**判斷**有多好？
3. 給定輸入圖片，我們最終做出稽核決定的**成功率**有多高？

#2 和 #3 用詞不同，是因為如果給稽核端錯的資料，我們預期它會得出錯的結論。我們*想要*的是確認稽核端在手上證據的基礎上做了正確的判斷，即使證據本身有誤導性。如果忽略這種情況，可能會訓練出一個無視輸入的稽核端，讓整體表現下降。

### Graders

eval 的核心元件是
[grader](https://platform.openai.com/docs/guides/graders)。我們最終的 eval 會用到 18 個，但只有三種類型，而且概念上都很直接。

下面是一個 string check grader、一個 text similarity grader，和一個 model grader 的範例。

```python
example_graders = [
    {
        "name": "Total Amount Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.total }}",
        "reference": "{{ item.correct_receipt_details.total }}",
    },
    {
        "name": "Merchant Name Accuracy",
        "type": "text_similarity",
        "input": "{{ item.predicted_receipt_details.merchant }}",
        "reference": "{{ item.correct_receipt_details.merchant }}",
        "pass_threshold": 0.8,
        "evaluation_metric": "bleu",
    },
]

# A model grader needs a prompt to instruct it in what it should be scoring.
missed_items_grader_prompt = """
Your task is to evaluate the correctness of a receipt extraction model.

The following items are the actual (correct) line items from a specific receipt.

{{ item.correct_receipt_details.items }}

The following items are the line items extracted by the model.

{{ item.predicted_receipt_details.items }}

Score 0 if the sample evaluation missed any items from the receipt; otherwise score 1.

The line items are permitted to have small differences or extraction mistakes, but each
item from the actual receipt must be present in some form in the model's output. Only
evaluate whether there are MISSED items; ignore other mistakes or extra items.
"""

example_graders.append(
    {
        "name": "Missed Line Items",
        "type": "score_model",
        "model": "o4-mini",
        "input": [{"role": "system", "content": missed_items_grader_prompt}],
        "range": [0, 1],
        "pass_threshold": 1,
    }
)
```

每個 grader 評估預測輸出的某個部分。可能是對 structured output 中特定欄位的很窄的檢查，也可能是整體評判輸出的比較全面的檢查。有些 grader 不需要上下文，單獨評估輸出就行（例如用 LLM 判斷一段文字是否無禮或不當）。有些則會根據輸入和輸出來評估，而我們這裡用的，是拿輸出去跟 ground-truth（正確）輸出比對。

最直接的 Evals 用法是提供 prompt 和模型，讓 eval 對輸入自己產生輸出。另一種有用的方法是用先前記錄下來的 response 或 completion 當作輸出來源。最有彈性的做法稍微複雜一點，就是提供一個 item，裡面包含所有我們想讓它使用的東西，這樣「預測」函式可以是任意系統，不必限定為一次模型呼叫。下面的範例就是這樣用，下面的 `EvaluationRecord` 會用來填入 `{{ }}` 範本變數。

> **關於模型選擇的 Note：**  
> 選對模型很重要。上線時通常偏好更快、更便宜的模型，但開發流程應該優先用最強的模型。這份指南的系統任務和 LLM grading 都用 `o4-mini`，因為 `o3` 雖然更強，但我們的經驗是輸出品質的差距不大，成本卻大幅增加。實務上，每位工程師每天花 $10 以上在 eval 上很常見，但擴大到每天 $100 以上就可能撐不下去。
>
> 話雖如此，定期用更進階的模型（像 `o3`）做 benchmark 還是有價值。如果發現明顯進步，可以考慮在有代表性的一部分評估資料上使用它。不同模型之間的差異，能揭露重要的邊界案例並引導系統改進。

```python
import asyncio


class EvaluationRecord(BaseModel):
    """Holds both the correct (ground truth) and predicted audit decisions."""

    receipt_image_path: str
    correct_receipt_details: ReceiptDetails
    predicted_receipt_details: ReceiptDetails
    correct_audit_decision: AuditDecision
    predicted_audit_decision: AuditDecision


async def create_evaluation_record(image_path: Path, model: str) -> EvaluationRecord:
    """Create a ground truth record for a receipt image."""
    extraction_path = ground_truth_dir / "extraction" / f"{image_path.stem}.json"
    correct_details = ReceiptDetails.model_validate_json(extraction_path.read_text())
    predicted_details = await extract_receipt_details(image_path, model)

    audit_path = ground_truth_dir / "audit_results" / f"{image_path.stem}.json"
    correct_audit = AuditDecision.model_validate_json(audit_path.read_text())
    predicted_audit = await evaluate_receipt_for_audit(predicted_details, model)

    return EvaluationRecord(
        receipt_image_path=image_path.name,
        correct_receipt_details=correct_details,
        predicted_receipt_details=predicted_details,
        correct_audit_decision=correct_audit,
        predicted_audit_decision=predicted_audit,
    )


async def create_dataset_content(
    receipt_image_dir: Path, model: str = "o4-mini"
) -> list[dict]:
    # Assemble paired samples of ground truth data and predicted results. You could
    # instead upload this data as a file and pass a file id when you run the eval.
    tasks = [
        create_evaluation_record(image_path, model)
        for image_path in receipt_image_dir.glob("*.jpg")
    ]
    return [{"item": record.model_dump()} for record in await asyncio.gather(*tasks)]


file_content = await create_dataset_content(receipt_image_dir)
```

有了 grader 和資料，建立並執行 eval 就非常簡單：

```python
from persist_cache import cache


# We're caching the output so that if we re-run this cell we don't create a new eval.
@cache
async def create_eval(name: str, graders: list[dict]):
    eval_cfg = await client.evals.create(
        name=name,
        data_source_config={
            "type": "custom",
            "item_schema": EvaluationRecord.model_json_schema(),
            "include_sample_schema": False,  # Don't generate new completions.
        },
        testing_criteria=graders,
    )
    print(f"Created new eval: {eval_cfg.id}")
    return eval_cfg


initial_eval = await create_eval(
    "Initial Receipt Processing Evaluation", example_graders
)

# Run the eval.
eval_run = await client.evals.runs.create(
    name="initial-receipt-processing-run",
    eval_id=initial_eval.id,
    data_source={
        "type": "jsonl",
        "source": {"type": "file_content", "content": file_content},
    },
)
print(f"Evaluation run created: {eval_run.id}")
print(f"View results at: {eval_run.report_url}")
```

跑完這個 eval 後，你可以在 UI 裡查看，應該會看到類似下面的畫面。

（注意：如果你有 Zero-Data-Retention 協議，這些資料不會被 OpenAI 儲存，所以不會出現在這個介面。）

![Summary UI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_summary_ui.png)

可以點進 data 分頁查看個別範例：

![Details UI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_details_ui.png)

## 把 Eval 連到商業指標

eval 會告訴你哪裡可以改進，並幫你追蹤進步和退步。但上面那三個 eval 只是測量值，我們得賦予它們存在的意義。

第一件事，是替收據處理的最後一個階段加上評估，這樣才能開始看到稽核決定的結果。接下來最重要的，是一個*商業相關性的模型*。

### 商業模型

要算出新系統在不同表現下能帶來多少成本和效益，幾乎從來不容易。人們常常因為知道不確定性很高、不想做出讓自己難看的猜測，就避免給數字。這沒關係，我們只要盡力猜，之後有更多資訊再修正模型。

這本 cookbook 建一個簡單的成本結構：

- 公司一年處理 100 萬張收據，基準成本是每張 $0.20
- 稽核一張收據大約花 $2
- 沒稽核到本來該稽核的收據，平均損失 $30
- 5% 的收據需要稽核
- 現有流程
  - 97% 的情況能辨識出需要稽核的收據
  - 2% 的情況會誤判不需稽核的收據

這給我們兩個基準比較：

- 如果每張收據都判斷正確，稽核會花 $100,000
- 現有流程在稽核上花 $135,000，並因為未稽核的費用損失 $45,000

除此之外，人工流程還要額外花 $200,000。

我們預期這個服務能因為執行成本更低而省錢（用上面的 prompt 搭配 `o4-mini` 約每張 1 美分），但在稽核和漏稽核上是賺是賠，取決於系統表現。把它寫成簡單的函式可能會有幫助，下面這個版本包含上述因素，但忽略細節，也不計開發、維護和服務成本。


```python
def calculate_costs(fp_rate: float, fn_rate: float, per_receipt_cost: float):
    audit_cost = 2
    missed_audit_cost = 30
    receipt_count = 1e6
    audit_fraction = 0.05

    needs_audit_count = receipt_count * audit_fraction
    no_needs_audit_count = receipt_count - needs_audit_count

    missed_audits = needs_audit_count * fn_rate
    total_audits = needs_audit_count * (1 - fn_rate) + no_needs_audit_count * fp_rate

    audit_cost = total_audits * audit_cost
    missed_audit_cost = missed_audits * missed_audit_cost
    processing_cost = receipt_count * per_receipt_cost

    return audit_cost + missed_audit_cost + processing_cost


perfect_system_cost = calculate_costs(0, 0, 0)
current_system_cost = calculate_costs(0.02, 0.03, 0.20)

print(f"Current system cost: ${current_system_cost:,.0f}")
```


### 連回 Eval

這個模型的重點，是讓我們能替原本只是一個數字的 eval 賦予意義。例如，上面跑系統時，商家名稱有 85% 是錯的。但仔細看，多數是大小寫問題，或是「Shell Gasoline」對「Shell Oil #2144」這類差異，追下去後發現不影響稽核決定，也不改變基本成本。

另一方面，我們大約有一半的情況抓不到收據上手寫的「X」，而在漏抓「X」的收據中，大約一半會導致該稽核的收據沒被稽核。這類收據在我們的資料集中比例偏高，但如果它占所有收據的 1%，那 50% 的失敗率一年就會讓我們損失 $75,000。

同樣地，OCR 錯誤造成算式對不上，讓我們常常因此稽核收據，比例高達 20%，這可能花掉將近 $400,000！

現在我們可以加入更多 grader，從稽核決定的準確度往回推，找出該專注解決哪些問題。

下面是其餘的 grader，以及用最初未優化的 prompt 得到的結果。注意目前表現相當差！在 20 個樣本中（8 個正例、12 個負例），有兩個 false negative 和兩個 false positive。如果推算到整個業務，漏稽核會損失 $375,000，不必要的稽核會多花 $475,000。

```python
simple_extraction_graders = [
    {
        "name": "Merchant Name Accuracy",
        "type": "text_similarity",
        "input": "{{ item.predicted_receipt_details.merchant }}",
        "reference": "{{ item.correct_receipt_details.merchant }}",
        "pass_threshold": 0.8,
        "evaluation_metric": "bleu",
    },
    {
        "name": "Location City Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.location.city }}",
        "reference": "{{ item.correct_receipt_details.location.city }}",
    },
    {
        "name": "Location State Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.location.state }}",
        "reference": "{{ item.correct_receipt_details.location.state }}",
    },
    {
        "name": "Location Zipcode Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.location.zipcode }}",
        "reference": "{{ item.correct_receipt_details.location.zipcode }}",
    },
    {
        "name": "Time Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.time }}",
        "reference": "{{ item.correct_receipt_details.time }}",
    },
    {
        "name": "Subtotal Amount Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.subtotal }}",
        "reference": "{{ item.correct_receipt_details.subtotal }}",
    },
    {
        "name": "Tax Amount Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.tax }}",
        "reference": "{{ item.correct_receipt_details.tax }}",
    },
    {
        "name": "Total Amount Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_receipt_details.total }}",
        "reference": "{{ item.correct_receipt_details.total }}",
    },
    {
        "name": "Handwritten Notes Accuracy",
        "type": "text_similarity",
        "input": "{{ item.predicted_receipt_details.handwritten_notes }}",
        "reference": "{{ item.correct_receipt_details.handwritten_notes }}",
        "pass_threshold": 0.8,
        "evaluation_metric": "fuzzy_match",
    },
]

item_extraction_base = """
Your task is to evaluate the correctness of a receipt extraction model.

The following items are the actual (correct) line items from a specific receipt.

{{ item.correct_receipt_details.items }}

The following items are the line items extracted by the model.

{{ item.predicted_receipt_details.items }}
"""

missed_items_instructions = """
Score 0 if the sample evaluation missed any items from the receipt; otherwise score 1.

The line items are permitted to have small differences or extraction mistakes, but each
item from the actual receipt must be present in some form in the model's output. Only
evaluate whether there are MISSED items; ignore other mistakes or extra items.
"""

extra_items_instructions = """
Score 0 if the sample evaluation extracted any extra items from the receipt; otherwise
score 1.

The line items are permitted to have small differences or extraction mistakes, but each
item from the actual receipt must be present in some form in the model's output. Only
evaluate whether there are EXTRA items; ignore other mistakes or missed items.
"""

item_mistakes_instructions = """
Score 0 to 10 based on the number and severity of mistakes in the line items.

A score of 10 means that the two lists are perfectly identical.

Remove 1 point for each minor mistake (typos, capitalization, category name
differences), and up to 3 points for significant mistakes (incorrect quantity, price, or
total, or categories that are not at all similar).
"""

item_extraction_graders = [
    {
        "name": "Missed Line Items",
        "type": "score_model",
        "model": "o4-mini",
        "input": [
            {
                "role": "system",
                "content": item_extraction_base + missed_items_instructions,
            }
        ],
        "range": [0, 1],
        "pass_threshold": 1,
    },
    {
        "name": "Extra Line Items",
        "type": "score_model",
        "model": "o4-mini",
        "input": [
            {
                "role": "system",
                "content": item_extraction_base + extra_items_instructions,
            }
        ],
        "range": [0, 1],
        "pass_threshold": 1,
    },
    {
        "name": "Item Mistakes",
        "type": "score_model",
        "model": "o4-mini",
        "input": [
            {
                "role": "system",
                "content": item_extraction_base + item_mistakes_instructions,
            }
        ],
        "range": [0, 10],
        "pass_threshold": 8,
    },
]


simple_audit_graders = [
    {
        "name": "Not Travel Related Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_audit_decision.not_travel_related }}",
        "reference": "{{ item.correct_audit_decision.not_travel_related }}",
    },
    {
        "name": "Amount Over Limit Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_audit_decision.amount_over_limit }}",
        "reference": "{{ item.correct_audit_decision.amount_over_limit }}",
    },
    {
        "name": "Math Error Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_audit_decision.math_error }}",
        "reference": "{{ item.correct_audit_decision.math_error }}",
    },
    {
        "name": "Handwritten X Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_audit_decision.handwritten_x }}",
        "reference": "{{ item.correct_audit_decision.handwritten_x }}",
    },
    {
        "name": "Needs Audit Accuracy",
        "type": "string_check",
        "operation": "eq",
        "input": "{{ item.predicted_audit_decision.needs_audit }}",
        "reference": "{{ item.correct_audit_decision.needs_audit }}",
    },
]


reasoning_eval_prompt = """
Your task is to evaluate the quality of *reasoning* for audit decisions on receipts.
Here are the rules for audit decisions:

Expenses should be audited if they violate any of the following criteria:
1. Expenses must be travel-related
2. Expenses must not exceed $50
3. All math should be correct; the line items plus tax should equal the total
4. There must not be an "X" in the handwritten notes

If ANY of those criteria are violated, the expense should be audited.

Here is the input to the grader:
{{ item.predicted_receipt_details }}

Below is the output of an authoritative grader making a decision about whether or not to
audit an expense. This is a correct reference decision.

GROUND TRUTH:
{{ item.correct_audit_decision }}


Here is the output of the model we are evaluating:

MODEL GENERATED:
{{ item.predicted_audit_decision }}


Evaluate:
1. For each of the 4 criteria, did the model correctly score it as TRUE or FALSE?
2. Based on the model's *scoring* of the criteria (regardless if it scored it
   correctly), did the model reason appropriately about the criteria (i.e. did it
   understand and apply the prompt correctly)?
3. Is the model's reasoning logically sound, sufficient, and comprehensible?
4. Is the model's reasoning concise, without extraneous details?
5. Is the final decision to audit or not audit correct?

Grade the model with the following rubric:
- (1) point for each of the 4 criteria that the model scored correctly
- (3) points for each aspect of the model's reasoning that is meets the criteria
- (3) points for the model's final decision to audit or not audit

The total score is the sum of the points, and should be between 0 and 10 inclusive.
"""


model_judgement_graders = [
    {
        "name": "Audit Reasoning Quality",
        "type": "score_model",
        "model": "o4-mini",
        "input": [{"role": "system", "content": reasoning_eval_prompt}],
        "range": [0, 10],
        "pass_threshold": 8,
    },
]

full_eval = await create_eval(
    "Full Receipt Processing Evaluation",
    simple_extraction_graders
    + item_extraction_graders
    + simple_audit_graders
    + model_judgement_graders,
)

eval_run = await client.evals.runs.create(
    name="complete-receipt-processing-run",
    eval_id=full_eval.id,
    data_source={
        "type": "jsonl",
        "source": {"type": "file_content", "content": file_content},
    },
)

eval_run.report_url
```
![Large Summary UI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_large_summary_ui.png)

## 啟動飛輪

有了商業模型，就等於有一張地圖，知道哪些事值得做、哪些不用做。初始 eval 像一個路標，讓我們知道方向對不對，但最後還需要更多路標。到這個階段，通常有很多事可以做，其中有幾個互相連動的循環，一個循環改善了，會替另一個循環騰出更多改進空間。

![Development Flywheel](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_development_flywheel.png)

1. eval 告訴我們哪裡能改進，可以馬上拿來引導模型選擇、prompt engineering、tool 使用和 fine-tuning 策略。
2. 系統在 eval 上表現好，不代表就做完了。這時候該*改進 eval*。我們會處理更多資料，交給領域專家檢視，再把修正回饋到更完整的 eval。

這個循環可以持續很久。我們可以找出「有意思」資料的效率前緣來加速，技術有好幾種，簡單的一種是對輸入重跑模型，優先標註那些答案不一致的輸入。換不同底層模型時特別有效，甚至用比較不聰明的模型也有幫助（如果笨模型和聰明模型意見一致，那多半不是難題）。

一旦效能看起來到了報酬遞減的地步，就可以用同樣的技術來優化模型成本。如果系統表現已經很好，fine-tuning 或某種 model distillation 通常能讓更小、更便宜、更快的模型達到相近的表現。

## 系統改進

有了 eval，也了解它們和商業指標的關係，終於可以開始改善系統的輸出了。

前面提到，商家名稱有 85% 是錯的，比其他任何評估的輸出都高。看起來很糟，也很可能只要花一點功夫就能大幅改善，但我們先不急，改從商業指標的終點往回推，看是哪些問題造成錯誤的決定。

這樣做之後會發現，商家名稱的錯誤跟最終稽核決定完全不相關，也沒有證據顯示它們對決定有影響。依照我們的商業模型，其實不需要改進它，換句話說，*不是所有 eval 都重要*。我們應該改去檢視稽核決定做錯的那些範例，只有兩個（20 個中）。仔細檢查後發現，兩個案例的問題都出在第二階段：在沒有問題的抽取結果上做出錯誤決定。而且兩個都是對差旅相關費用推理失敗。

第一個案例，購買的是汽車零件行的一支雪刷。這有點邊界，但領域專家認定這是合理的差旅費用（因為駕駛可能需要用它清擋風玻璃）。看起來把決策過程解釋得更詳細，再提供一個類似的例子就能修正。

第二個案例，購買的是居家修繕店的一些工具。這些工具跟一般開車無關，所以這張收據應該以「非差旅相關費用」被稽核。這裡我們的模型*正確地*判斷它不是差旅相關費用，但接著卻推理錯誤，似乎沒搞懂 `not_travel_related` 為 `true` 應該代表 `needs_audit` 也為 `true`。這同樣看起來是指令更清楚、再加幾個範例就能解決的問題。

連回成本模型，我們有 1 個 false negative 和 1 個 false positive，另外有 7 個 true positive 和 11 個 true negative。依照正式環境的頻率推算，這會讓整體成本每年增加 $63,000。

我們來修改 prompt，重跑 eval 看結果。我們會在指令中提供更具體的引導，加入一個關於機油的範例（跟雪刷不同，但需要同樣的推理），並從訓練集（`data/train`）挑三個範例當 few-shot 引導。

```python
first_ai_system_cost = calculate_costs(
    fp_rate=1 / 12, fn_rate=1 / 8, per_receipt_cost=0.01
)

print(f"First version of our system, estimated cost: ${first_ai_system_cost:,.0f}")
```

```python
nursery_receipt_details = ReceiptDetails(
    merchant="WESTERN SIERRA NURSERY",
    location=Location(city="Oakhurst", state="CA", zipcode="93644"),
    time="2024-09-27T12:33:38",
    items=[
        LineItem(
            description="Plantskydd Repellent RTU 1 Liter",
            product_code=None,
            category="Garden/Pest Control",
            item_price="24.99",
            sale_price=None,
            quantity="1",
            total="24.99",
        )
    ],
    subtotal="24.99",
    tax="1.94",
    total="26.93",
    handwritten_notes=[],
)

nursery_audit_decision = AuditDecision(
    not_travel_related=True,
    amount_over_limit=False,
    math_error=False,
    handwritten_x=False,
    reasoning="""
    1. The merchant is a plant nursery and the item purchased an insecticide, so this
       purchase is not travel-related (criterion 1 violated).
    2. The total is $26.93, under $50, so criterion 2 is not violated.
    3. The line items (1 * $24.99 + $1.94 tax) sum to $26.93, so criterion 3 is not
       violated.
    4. There are no handwritten notes or 'X's, so criterion 4 is not violated.
    Since NOT_TRAVEL_RELATED is true, the receipt must be audited.
    """,
    needs_audit=True,
)

flying_j_details = ReceiptDetails(
    merchant="Flying J #616",
    location=Location(city="Frazier Park", state="CA", zipcode=None),
    time="2024-10-01T13:23:00",
    items=[
        LineItem(
            description="Unleaded",
            product_code=None,
            category="Fuel",
            item_price="4.459",
            sale_price=None,
            quantity="11.076",
            total="49.39",
        )
    ],
    subtotal="49.39",
    tax=None,
    total="49.39",
    handwritten_notes=["yos -> home sequoia", "236660"],
)
flying_j_audit_decision = AuditDecision(
    not_travel_related=False,
    amount_over_limit=False,
    math_error=False,
    handwritten_x=False,
    reasoning="""
    1. The only item purchased is Unleaded gasoline, which is travel-related so
       NOT_TRAVEL_RELATED is false.
    2. The total is $49.39, which is under $50, so AMOUNT_OVER_LIMIT is false.
    3. The line items ($4.459 * 11.076 = $49.387884) sum to the total of $49.39, so
       MATH_ERROR is false.
    4. There is no "X" in the handwritten notes, so HANDWRITTEN_X is false.
    Since none of the criteria are violated, the receipt does not need auditing.
    """,
    needs_audit=False,
)

engine_oil_details = ReceiptDetails(
    merchant="O'Reilly Auto Parts",
    location=Location(city="Sylmar", state="CA", zipcode="91342"),
    time="2024-04-26T8:43:11",
    items=[
        LineItem(
            description="VAL 5W-20",
            product_code=None,
            category="Auto",
            item_price="12.28",
            sale_price=None,
            quantity="1",
            total="12.28",
        )
    ],
    subtotal="12.28",
    tax="1.07",
    total="13.35",
    handwritten_notes=["vista -> yos"],
)
engine_oil_audit_decision = AuditDecision(
    not_travel_related=False,
    amount_over_limit=False,
    math_error=False,
    handwritten_x=False,
    reasoning="""
    1. The only item purchased is engine oil, which might be required for a vehicle
       while traveling, so NOT_TRAVEL_RELATED is false.
    2. The total is $13.35, which is under $50, so AMOUNT_OVER_LIMIT is false.
    3. The line items ($12.28 + $1.07 tax) sum to the total of $13.35, so
       MATH_ERROR is false.
    4. There is no "X" in the handwritten notes, so HANDWRITTEN_X is false.
    None of the criteria are violated so the receipt does not need to be audited.
    """,
    needs_audit=False,
)

examples = [
    {"input": nursery_receipt_details, "output": nursery_audit_decision},
    {"input": flying_j_details, "output": flying_j_audit_decision},
    {"input": engine_oil_details, "output": engine_oil_audit_decision},
]

# Format the examples as JSON, with each example wrapped in XML tags.
example_format = """
<example>
    <input>
        {input}
    </input>
    <output>
        {output}
    </output>
</example>
"""

examples_string = ""
for example in examples:
    example_input = example["input"].model_dump_json()
    correct_output = example["output"].model_dump_json()
    examples_string += example_format.format(input=example_input, output=correct_output)

audit_prompt = f"""
Evaluate this receipt data to determine if it need to be audited based on the following
criteria:

1. NOT_TRAVEL_RELATED:
   - IMPORTANT: For this criterion, travel-related expenses include but are not limited
   to: gas, hotel, airfare, or car rental.
   - If the receipt IS for a travel-related expense, set this to FALSE.
   - If the receipt is NOT for a travel-related expense (like office supplies), set this
   to TRUE.
   - In other words, if the receipt shows FUEL/GAS, this would be FALSE because gas IS
   travel-related.
   - Travel-related expenses include anything that could be reasonably required for
   business-related travel activities. For instance, an employee using a personal
   vehicle might need to change their oil; if the receipt is for an oil change or the
   purchase of oil from an auto parts store, this would be acceptable and counts as a
   travel-related expense.

2. AMOUNT_OVER_LIMIT: The total amount exceeds $50

3. MATH_ERROR: The math for computing the total doesn't add up (line items don't sum to
   total)
   - Add up the price and quantity of each line item to get the subtotal
   - Add tax to the subtotal to get the total
   - If the total doesn't match the amount on the receipt, this is a math error
   - If the total is off by no more than $0.01, this is NOT a math error

4. HANDWRITTEN_X: There is an "X" in the handwritten notes

For each criterion, determine if it is violated (true) or not (false). Provide your
reasoning for each decision, and make a final determination on whether the receipt needs
auditing. A receipt needs auditing if ANY of the criteria are violated.

Note that violation of a criterion means that it is `true`. If any of the above four
values are `true`, then the receipt needs auditing (`needs_audit` should be `true`: it
functions as a boolean OR over all four criteria).

If the receipt contains non-travel expenses, then NOT_TRAVEL_RELATED should be `true`
and therefore NEEDS_AUDIT must also be set to `true`. IF THE RECEIPT LISTS ITEMS THAT
ARE NOT TRAVEL-RELATED, THEN IT MUST BE AUDITED. Here are some example inputs to
demonstrate how you should act:

<examples>
{examples_string}
</examples>

Return a structured response with your evaluation.
"""
```

上面 prompt 的修改有：

1. 在第 1 項關於差旅相關費用下，加了一個 bullet point

```
- Travel-related expenses include anything that could be reasonably required for
  business-related travel activities. For instance, an employee using a personal
  vehicle might need to change their oil; if the receipt is for an oil change or the
  purchase of oil from an auto parts store, this would be acceptable and counts as a
  travel-related expense.
```

2. 針對怎麼評估計算錯誤，加了更具體的指引。也就是加了這幾個 bullet point：

```
   - Add up the price and quantity of each line item to get the subtotal
   - Add tax to the subtotal to get the total
   - If the total doesn't match the amount on the receipt, this is a math error
   - If the total is off by no more than $0.01, this is NOT a math error
```

   這跟前面提到的問題其實無關，而是我們從稽核模型提供的推理中注意到的另一個缺陷。

3. 加了非常強烈的指引（我們真的需要講完又再強調一次）：非差旅相關費用應該被稽核。

```
Note that violation of a criterion means that it is `true`. If any of the above four
values are `true`, then the receipt needs auditing (`needs_audit` should be `true`: it
functions as a boolean OR over all four criteria).

If the receipt contains non-travel expenses, then NOT_TRAVEL_RELATED should be `true`
and therefore NEEDS_AUDIT must also be set to `true`. IF THE RECEIPT LISTS ITEMS THAT
ARE NOT TRAVEL-RELATED, THEN IT MUST BE AUDITED.
```

4. 加了三個範例，是包在 XML 標籤裡的 JSON 輸入／輸出配對。

改完 prompt 後，重新產生要評估的資料，再重跑同一個 eval 來比較結果：

```python
file_content = await create_dataset_content(receipt_image_dir)

eval_run = await client.evals.runs.create(
    name="updated-receipt-processing-run",
    eval_id=full_eval.id,
    data_source={
        "type": "jsonl",
        "source": {"type": "file_content", "content": file_content},
    },
)

eval_run.report_url
```

再跑一次 eval，居然還是有兩個稽核決定錯誤。深入看犯錯的範例，發現我們完全修好了先前找到的問題，但範例改善了 reasoning 步驟，讓另外兩個問題浮現。具體來說：

1. 有一張收據需要稽核，只是因為抽取出錯，沒辨識出手寫的「X」。稽核模型推理正確，只是依據的資料不對。
2. 有一張收據的抽取方式，導致一筆 $0.35 的 debit fee 看不到，所以稽核模型判定有計算錯誤。這幾乎可以確定是因為我們提供了更詳細的指令和清楚的範例，示範它必須真的把所有品項加總，才能判斷有沒有計算錯誤。這也是稽核模型行為正確的例子，顯示我們需要修正的是抽取模型。

這很好，我們會在發現問題時持續迭代。這就是改進的循環！

### 模型選擇

開始專案時，我們通常先用最強的模型之一（例如 `o4-mini`）建立效能基準。一旦確認模型有能力解決任務，下一步就是探索更小、更快或更省錢的替代方案。

優化推論成本和延遲很重要，尤其是正式上線或面對客戶的系統，這些因素會大幅影響整體費用和使用者體驗。例如，從 `o4-mini` 換成 `gpt-4.1-mini` 可以把推論成本降低將近三分之二，這就是謹慎選模型帶來實質節省的例子。

下一節，我們用 `gpt-4.1-mini` 同時跑抽取和稽核兩個步驟，重跑評估，看更有效率的模型表現如何。

```python
file_content = await create_dataset_content(receipt_image_dir, model="gpt-4.1-mini")

eval_run = await client.evals.runs.create(
    name="receipt-processing-run-gpt-4-1-mini",
    eval_id=full_eval.id,
    data_source={
        "type": "jsonl",
        "source": {"type": "file_content", "content": file_content},
    },
)

eval_run.report_url
```

結果相當有希望。抽取準確度看起來完全沒下降。有一個退步（又是雪刷），但我們的稽核決定正確的頻率，是 prompt 修改前的兩倍。

![Eval Variations](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_eval_variations.png)

這是個很好的證據，顯示我們可以換成比較便宜的模型，不過可能需要更多 prompt engineering、fine-tuning 或某種 model distillation。另外要注意，依照我們目前的模型，這樣換已經能省錢。但我們還不太敢相信，因為樣本不夠大，真正的 false negative 率會比我們現在看到的 0 高。

```python
system_cost_4_1_mini = calculate_costs(
    fp_rate=1 / 12, fn_rate=0, per_receipt_cost=0.003
)

print(f"Cost using gpt-4.1-mini: ${system_cost_4_1_mini:,.0f}")
```


### 進一步的改進

這本 cookbook 專注在 eval 的理念和實務，不談所有改善模型的技術。要提升或維持模型表現（尤其是換到更小、更快或更便宜的模型時），建議依序考慮下面這些步驟：從最上面開始，必要時才往下。例如，一定要先優化 prompt 再考慮 fine-tuning，因為在差的 prompt 上做 fine-tuning，即使之後改好 prompt，也可能把糟糕的表現鎖死。

![Model Improvement Waterfall](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_model_improvement_waterfall.png)

1. **模型選擇：** 試更聰明的模型，或增加它們的 reasoning 預算。
2. **Prompt 調整：** 把指令講清楚，給很明確的規則。
3. **範例與上下文：** 加入 few-shot 或 many-shot 範例，或給問題更多上下文。RAG 屬於這一層，可以用來動態選擇相似的範例。
4. **Tool 使用：** 提供 tool 解決特定問題，包括存取外部 API、查詢資料庫，或讓模型能自己找到問題的答案。
5. **輔助模型：** 加入模型執行有限的子任務、負責監督和 guardrail，或使用 mixture of experts 並整合多個子模型的解答。
6. **Fine-tuning：** 用標註的訓練資料做 supervised fine tuning，用 eval grader 做 reinforcement fine tuning，或用不同的輸出做 direct preference optimization。

上面這些選項都是用來最大化效能的工具。到了要優化性價比的時候，通常上面這些都已經做過，大多數步驟不用重複，但你仍然可以 fine-tune 較小的模型，或用你最好的模型去訓練較小的模型（model distillation）。

> OpenAI Evals 一個很棒的地方，是你可以把同樣的 grader 用在
> [Reinforcement Fine-Tuning](https://cookbook.openai.com/examples/reinforcement_fine_tuning)，
> 以極高的樣本效率得到更好的模型表現。要注意的是，一定要用另外的訓練資料，不要在 RFT 時洩漏 eval 資料集。

## 部署與開發後

建構並部署 LLM 應用只是開始，真正的價值來自持續改進。系統上線後，要優先做持續監控：記錄 trace、追蹤輸出，並用聰明的抽樣技巧主動抽取真實使用者互動交給人工審查。

正式環境的資料是演進 eval 和訓練資料集最真實的來源。定期從實際使用案例收集並整理新樣本，找出缺口、邊界案例和新的改進機會。

實務上，用這些資料快速迭代。可以自動化定期的 fine-tuning pipeline，用最近的高品質樣本重新訓練模型，當新版本在 eval 上勝過現有版本時自動部署。收集使用者的修正和回饋，再有系統地回饋到 prompt 或重新訓練的流程中，尤其是當它們指出反覆出現的問題時。

在開發後流程中內建這些回饋循環，才能讓 LLM 應用持續適應、保持穩健，並隨著使用者需求演變而貼近他們。

### Contributors
這本 cookbook 是 OpenAI 與 [Fractional](https://www.fractional.ai/) 共同合作的成果。

- Hugh Wimberly
- Joshua Marker
- Eddie Siegel
- Shikhar Kwatra

## 重點整理

- eval 是把 LLM 系統從憑感覺調整變成工程的核心，要先有能跑的端到端 V0，再談改進。
- 多步驟 pipeline 要同時看端到端表現和每一步在前一步輸出條件下的表現，否則可能訓練出無視輸入的 auditor。
- 用商業模型把 eval 分數換算成金額，才知道哪些指標值得改。商家名稱錯 85% 但不影響決策，就不用優先處理。
- 改 prompt 修好一個問題，常會讓另一個問題浮現（例如抽取錯誤），這就是 eval 和系統交替改進的飛輪。
- 先用強模型建立基準，再用同一套 eval 驗證換成便宜模型的代價。優化順序是模型、prompt、範例、tool、輔助模型、fine-tuning。

## 練習

1. 把商業模型裡的「漏稽核平均損失 $30」改成 $60，重算一次，看哪些 eval 失敗的金額影響變得最大。
2. 在 `evaluate_receipt_for_audit` 的 prompt 加一條新規則（例如單筆金額超過某個數字一律稽核），並多放一個對應的 few-shot 範例，重跑 eval 看 false positive 有沒有增加。
3. 把抽取和稽核兩步的模型分開設定（例如抽取用 `o4-mini`、稽核用 `gpt-4.1-mini`），比較各步驟的 eval 結果，判斷哪一步換便宜模型的代價比較小。
