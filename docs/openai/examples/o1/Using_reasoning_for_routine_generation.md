---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/o1/Using_reasoning_for_routine_generation.ipynb
---
# 用 reasoning 產生 routine

> 原文：[examples/o1/Using_reasoning_for_routine_generation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/o1/Using_reasoning_for_routine_generation.ipynb)



## 這篇在做什麼
示範怎麼用 o1-preview 把客服知識庫文章（OpenAI Help Center）轉成 LLM 可以逐步執行的內部 routine，同時讓模型產生需要的 function 定義。文章會平行丟給模型處理，再把結果放進 dataframe 檢視。

## 學完你會
- 解釋什麼是 routine，以及為什麼把給人看的文件轉成逐步指令，LLM 比較不會出錯。
- 寫一個 prompt，用 o1-preview zero-shot 把 policy 轉成含條件分支和 function call 的 SOP。
- 平行處理多篇文章，並檢視產出的 routine。

## 開跑前
- 需要 OpenAI API key，並有 o1-preview 的使用權限（會產生 API 費用）。



開發客服解決方案時，第一步通常是把知識庫文章轉成 LLM 能理解並遵循的一組 routine。這裡的 routine 指的是專為 LLM 設計、可以有效執行的一套逐步指令。每個 routine 都精心結構化，讓每一步對應一個明確的動作。動作可以是回覆使用者、觸發 function call，或是取得其他相關知識。

多數內部知識庫文章很複雜，是為了人類閱讀而寫的。它們常包含複雜的圖表、多步驟流程和決策樹，讓 LLM 方案很難有意義地推理。把這些文件拆成 routine，就能把每個指令簡化、整理成適合引導 LLM 完成一連串小而可管理任務的格式。這種細粒度的做法能降低歧義，讓 LLM 有條理地處理資訊，也降低 hallucination 或偏離預期路徑的風險。

把這些知識庫文章轉成 routine 既耗時又有挑戰，尤其是想建自動化 pipeline 的公司。每個 routine 都要涵蓋各種使用者情境，動作也要定義清楚。例如需要 function call 時，routine 必須指明要取得的確切資訊或要執行的動作，不管是觸發 API、取得外部資料，還是拉進額外的 context。用傳統 GPT 類模型自動化這個流程可以大幅減少人工，但常常帶來新問題，例如：要設計夠具體、讓 LLM 能穩定遵循的指令，要涵蓋客戶互動中可能出現的獨特邊界情況，要提供高品質的 few-shot 範例來引導模型行為，有時還要 fine-tuning 模型才能得到更可靠或更專門的結果。

o1 已經展現出能有效拆解這些文章，並以 zero-shot 的方式轉成一組 routine 的能力。zero-shot 的意思是 LLM 不需要大量範例，或事先在類似任務上訓練，就能理解並遵循指令。這減少了需要的 prompt 工作，因為 routine 本身的結構就提供了完成每一步所需的引導。o1 的做法把任務拆成具體動作，並在需要時整合 function call，確保 LLM 連複雜的工作流程也能順暢處理，帶來更有效、更可擴展的客服方案。

## 選擇知識庫文章

這個範例用 OpenAI 網站上公開的一組 Help Center 文章，把它們轉成 LLM 可以執行的內部 routine。除了把 policy 轉成 routine，也讓模型產生 function，讓 LLM 可以代替使用者執行動作。這是必要的，這樣 LLM 才能做人工客服做得到的事，並取得光看 policy 文件無法立即得到的額外資訊。

一開始用下面這幾篇 Help Center 文章轉成 routine：
- [How do I delete my payment method](https://help.openai.com/en/articles/8156070-how-do-i-delete-my-payment-method)
- [How can I get a Business Associate Agreement (BAA) with OpenAI?](https://help.openai.com/en/articles/8660679-how-can-i-get-a-business-associate-agreement-baa-with-openai)
- [How can I set up prepaid billing?](https://help.openai.com/en/articles/8264644-how-can-i-set-up-prepaid-billing)
- [How do I submit a VAT exemption request](https://help.openai.com/en/articles/7232908-how-do-i-submit-a-vat-exemption-request)

```python
from openai import OpenAI
from IPython.display import display, HTML
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import csv

client = OpenAI()
MODEL = 'o1-preview'
```

文章存在一個可以讀取的 csv 裡。我們把文章平行丟給 o1-preview，產生最初的 routine。

把 policy 轉成 routine 的指令包括：
- 把 policy 從對外的文件轉成內部的 SOP routine
- 把 policy 拆成具體的動作和子動作
- 列出在步驟之間移動的具體條件
- 判斷哪些地方可能需要外部知識/動作，並定義可以用來取得那些資訊的 function

```python
articles = []

with open('../data/helpcenter_articles.csv', mode='r', encoding='utf-8') as file:
    reader = csv.DictReader(file)
    for row in reader:
        articles.append({
            "policy": row["policy"],
            "content": row["content"]
        })
```

```python
CONVERSION_PROMPT = """
You are a helpful assistant tasked with taking an external facing help center article and converting it into a internal-facing programmatically executable routine optimized for an LLM. 
The LLM using this routine will be tasked with reading the policy, answering incoming questions from customers, and helping drive the case toward resolution.

Please follow these instructions:
1. **Review the customer service policy carefully** to ensure every step is accounted for. It is crucial not to skip any steps or policies.
2. **Organize the instructions into a logical, step-by-step order**, using the specified format.
3. **Use the following format**:
   - **Main actions are numbered** (e.g., 1, 2, 3).
   - **Sub-actions are lettered** under their relevant main actions (e.g., 1a, 1b).
      **Sub-actions should start on new lines**
   - **Specify conditions using clear 'if...then...else' statements** (e.g., 'If the product was purchased within 30 days, then...').
   - **For instructions that require more information from the customer**, provide polite and professional prompts to ask for additional information.
   - **For actions that require data from external systems**, write a step to call a function using backticks for the function name (e.g., `call the check_delivery_date function`).
      - **If a step requires the customer service agent to take an action** (e.g., process a refund), generate a function call for this action (e.g., `call the process_refund function`).
      - **Define any new functions** by providing a brief description of their purpose and required parameters.
   - **If there is an action an assistant can performon behalf of the user**, include a function call for this action (e.g., `call the change_email_address function`), and ensure the function is defined with its purpose and required parameters.
      - This action may not be explicitly defined in the help center article, but can be done to help the user resolve their inquiry faster
   - **The step prior to case resolution should always be to ask if there is anything more you can assist with**.
   - **End with a final action for case resolution**: calling the `case_resolution` function should always be the final step.
4. **Ensure compliance** by making sure all steps adhere to company policies, privacy regulations, and legal requirements.
5. **Handle exceptions or escalations** by specifying steps for scenarios that fall outside the standard policy.

**Important**: If at any point you are uncertain, respond with "I don't know."

Please convert the customer service policy into the formatted routine, ensuring it is easy to follow and execute programmatically.

"""
```

```python
def generate_routine(policy):
    try:
        messages = [
            {
                "role": "user",
                "content": f"""
                    {CONVERSION_PROMPT}

                    POLICY:
                    {policy}
                """
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages
        )
        

        return response.choices[0].message.content 
    except Exception as e:
        print(f"An error occurred: {e}")
```

```python
def process_article(article):
    routine = generate_routine(article['content'])
    return {"policy": article['policy'], "content": article['content'], "routine": routine}


with ThreadPoolExecutor() as executor:
    results = list(executor.map(process_article, articles))
```

把 routine 的結果存進 dataframe 並印出來，先看個大概。

```python
df = pd.DataFrame(results)

# Set display options to show all text in the dataframe cells
pd.set_option('display.max_colwidth', None)

# Function to display formatted text in HTML
def display_formatted_dataframe(df):
    def format_text(text):
        return text.replace('\n', '<br>')

    df_formatted = df.copy()
    df_formatted['content'] = df_formatted['content'].apply(format_text)
    df_formatted['routine'] = df_formatted['routine'].apply(format_text)
    
    display(HTML(df_formatted.to_html(escape=False, justify='left')))

display_formatted_dataframe(df)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 結果

檢視產生的 routine 後，可以得到幾個觀察：
- 範例回應：模型能有效產生 LLM 執行 policy 時可以使用的範例回應（例如 “Instruct the user: ‘Confirm and purchase your initial amount of credits.’”）。
- 離散的步驟：模型很擅長把問題拆成 LLM 需要執行的離散動作。每個指令都定義清楚、容易理解。
- Function 定義：routine 的輸出包含明確定義的 function，用來取得外部資訊或觸發動作（例如 `review_and_apply_tax_exemption`、`get_billing_plan`、`update_payment_method`）。
    - 這對任何成功的 routine 都很關鍵，因為 LLM 常常需要跟外部系統互動。用 function call 是跟這些系統互動並執行動作的有效方式。
- IFTTT 邏輯：模型有效運用了 IFTTT (If This, Then That) 邏輯，這很適合 LLM（例如 “If the customer requests assistance, proceed to step 3f.”）。
    - 當原始知識庫文章含有複雜的工作流程和圖表時，這種轉換特別有價值。這種複雜度人類不一定看得懂，LLM 更難。IFTTT 邏輯容易理解，很適合客服方案

## 接下來呢？

這些 routine 現在可以整合進 agentic 系統，處理特定的客戶問題。當客戶請求協助設定 prepaid billing 之類的事情時，我們可以用 classifier 判斷該用哪個 routine，取出來交給 LLM 直接跟客戶互動。系統不只可以告訴使用者「怎麼」設定帳單，還可以代替他們執行這個動作。

在把這些 routine 部署到正式環境之前，應該建立完整的 eval 來測試並驗證模型回應的品質。這個過程可能需要調整 routine，以確保合規性和有效性。

## 重點整理
- Routine 是把給人看的 policy 拆成 LLM 可逐步執行的動作，每一步對應一個明確動作。
- o1 可以 zero-shot 做這個轉換，不需要大量範例或 fine-tuning。
- 好的 routine 要有範例回應、離散步驟、function 定義和 IFTTT 條件分支。
- Function 定義讓 LLM 能跟外部系統互動，代替使用者執行動作。
- 上線前要先建 eval 驗證品質，再回頭調整 routine。

## 練習
1. 在頁面的 csv 裡多加一篇 Help Center 文章，一起丟給 o1-preview 產生 routine。
2. 修改轉換指令，要求每個 routine 的每一步都附上一句範例回應，看輸出有什麼變化。
3. 挑一個產生出來的 routine，手動檢查每個 function 的參數是否足夠，把缺的補進指令後重跑。
