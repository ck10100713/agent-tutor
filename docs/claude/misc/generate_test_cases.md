---
translated: true
source: misc/generate_test_cases.ipynb
---

# 為你的 prompt template 產生合成測試資料

> 原文：[misc/generate_test_cases.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/generate_test_cases.ipynb)

產生合成測試案例，有效地評估並改善你的 Claude prompt template。

## 這篇在做什麼

你有一個帶變數的 prompt template，但手上沒有真實資料可以測。這篇教你讓 Claude 幫你編出逼真的變數值，並且可以改它的規劃邏輯、反覆調整結果。

## 學完你會

- 從 prompt template 裡抽出變數，組成讓 Claude 產生測試資料的 prompt。
- 看懂並修改 Claude 產生測試案例前的規劃文字，讓資料更貼近你要的樣子。
- 把產生的測試資料拿來做 prompt 評估，或當作 multishot 範例。

## 開跑前

需要 Anthropic API key。

想像你有一個大概長這樣的 prompt：

"""Here's some things I want you to analyze:

<thing>
{{thing1}}
</thing>
<thing>
{{thing2}}
</thing>

These things are [description of things]. Please read them carefully and [do some task]."""

這裡 thing1 和 thing2 叫做「變數」，你希望這個 prompt 對 thing1 和 thing2 的各種可能值都表現良好。

要怎麼測試這個 prompt template？也許你有真實的值可以代入。但也許沒有，或是因為隱私不能拿手上的資料來測。沒關係，Claude 可以幫你編。這份 cookbook 示範怎麼用 Claude 和 Claude API 為 prompt 產生合成測試資料。裡面有幾個 function，負責從 template 抽出變數、組出範例區塊、產生測試案例，以及反覆修正結果。好處有兩個：

1. Prompt 評估
你可以用這些測試案例，看 Claude 在逼真的範例上表現如何。

2. 用 multishot 範例改善 prompt
給 Claude 範例大概是改善表現最好的方法。這個 notebook 可以幫你產生逼真的輸入，而這就是拿到理想輸入/輸出配對的一半功夫。

```python
%pip install -q anthropic IPython python-dotenv
```

```python
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()  # reads ANTHROPIC_API_KEY from .env if present

CLIENT = anthropic.Anthropic()
MODEL_NAME = "claude-sonnet-5-5"
```

先定義幾個整份 notebook 會用到的 helper function。

```python
# First, we have the `extract_variables` function,
# It takes in a prompt template and extracts the double-mustache-bracketed "variables" contained.
def extract_variables(prompt_template):
    """Extract variables from a prompt template."""
    pattern = r"{{([^}]+)}}"
    variables = re.findall(pattern, prompt_template)
    return set(variables)


# Next, we have `construct_variables_names`, which just joins them together connected by newlines.
def construct_variables_names(prompt_template):
    """Construct a string of variable names from a prompt template."""
    variables = extract_variables(prompt_template)
    return "\n".join(variables)


# The `construct_variables_block` function takes in the list of variables, and constructs a "variables block"
# The variables block might look like this, if the variables were 'animal' and 'topic':
"""
<animal>
[a full, complete, value for the variable "animal"]
</animal>
<topic>
[a full, complete, value for the variable "topic"]
</topic>
"""


def construct_variables_block(prompt_template):
    """Construct a variables block for the synthetic test data prompt."""
    variables = extract_variables(prompt_template)
    output = ""
    for v in variables:
        output += f"<{v}>\n"
        output += f'[a full, complete, value for the variable "{v}". (You do not need to repeat the variable name inside the tags.)]\n'
        output += f"</{v}>\n"
    return output.strip()


# `construct_examples` takes a dictionary of {variable: value} and constructs an XML-formatted example.
# E.g. if the dict is
# {'animal': 'cat', 'topic': 'movement patterns'}, then the example would be
"""
<example>
<variables>
<animal>
cat
</animal>
<topic>
movement patterns
</topic>
</variables>
</example>
"""


def construct_example_block(variable_dict):
    """Construct an example block from a dictionary of variables."""
    output = "<example>\n<variables>\n"
    for k, v in variable_dict.items():
        output += f"<{k}>\n{v}\n</{k}>\n"
    output = output.strip()
    output += "\n</variables>\n</example>"
    return output
```

## 產生資料用的 Prompt Template

這些 prompt template 的概念是，拿使用者提交的帶變數 prompt template，建構出一些變數值來填入 template。

下面其實有兩個 prompt template，一個假設使用者已經提供範例變數值，另一個不假設。

它們的共通點是，兩個 template 一開始都先給 Claude 情境脈絡，並要求 Claude 在輸出測試案例之前，仔細思考每個變數各自的規格，以及使用者提供的整個 prompt template。

```python
# Formatting Prompt Templates for Synthetic Evaluations

# This function prepares the prompt template for generating synthetic test data.


def format_prompt_template_for_synth_evals(prompt_template, examples=None):
    """Format a prompt template for synthetic evaluations."""
    synth_test_data_prompt_template_with_example = """<Prompt Template>
{{PROMPT_TEMPLATE}}
</Prompt Template>

Your job is to construct a test case for the prompt template above. This template contains "variables", which are placeholders to be filled in later. In this case, the variables are:

<variables>
{{CONSTRUCT_VARIABLES_NAMES}}
</variables>

Here are the example test cases provided by the user.
<examples>
{{EXAMPLES}}
</examples>

First, in <planning> tags, do the following:

1. Summarize the prompt template. What is the goal of the user who created it?
2. For each variable in <variables>, carefully consider what a paradigmatic, realistic example of that variable would look like. You'll want to note who will be responsible "in prod" for supplying values. Written by a human "end user"? Downloaded from a website? Extracted from a database? Think about things like length, format, and tone in addition to semantic content. Use the examples provided by the user to guide this exercise. The goal is to acquire a sense of the statistical distribution the examples are being drawn from. The example you write should be drawn from that same distribution, but sufficiently different from the examples that it provides additional signal. A tricky balancing act, but I have faith in you.

Once you're done, output a test case for this prompt template with a full, complete, value for each variable. The output format should consist of a tagged block for each variable, with the value inside the block, like the below:

<variables>
{{CONSTRUCT_VARIABLES_BLOCK}}
</variables>"""

    synth_test_data_prompt_template_without_example = """<Prompt Template>
{{PROMPT_TEMPLATE}}
</Prompt Template>

Your job is to construct a test case for the prompt template above. This template contains "variables", which are placeholders to be filled in later. In this case, the variables are:

<variables>
{{CONSTRUCT_VARIABLES_NAMES}}
</variables>

First, in <planning> tags, do the following:

1. Summarize the prompt template. What is the goal of the user who created it?
2. For each variable in <variables>, carefully consider what a paradigmatic, realistic example of that variable would look like. You'll want to note who will be responsible "in prod" for supplying values. Written by a human "end user"? Downloaded from a website? Extracted from a database? Think about things like length, format, and tone in addition to semantic content.

Then, output a test case for this prompt template with a full, complete, value for each variable. The output format should consist of a tagged block for each variable, with the value inside the block, like the below:
<variables>
{{CONSTRUCT_VARIABLES_BLOCK}}
</variables>"""

    if examples:
        examples_block = "\n".join([construct_example_block(example) for example in examples])
        return (
            synth_test_data_prompt_template_with_example.replace(
                "{{PROMPT_TEMPLATE}}", prompt_template
            )
            .replace("{{CONSTRUCT_VARIABLES_NAMES}}", construct_variables_names(prompt_template))
            .replace("{{CONSTRUCT_VARIABLES_BLOCK}}", construct_variables_block(prompt_template))
            .replace("{{EXAMPLES}}", examples_block)
        )
    else:
        return (
            synth_test_data_prompt_template_without_example.replace(
                "{{PROMPT_TEMPLATE}}", prompt_template
            )
            .replace("{{CONSTRUCT_VARIABLES_NAMES}}", construct_variables_names(prompt_template))
            .replace("{{CONSTRUCT_VARIABLES_BLOCK}}", construct_variables_block(prompt_template))
        )
```

接著再寫一個小 helper function，負責填入適當的 prompt template 並呼叫 Claude。

```python
def get_test_data(prompt_template, examples, custom_planning=None):
    """Generate test data using the Claude API."""
    synth_eval_prompt_ready = format_prompt_template_for_synth_evals(prompt_template, examples)

    if custom_planning:
        # Hand Claude an edited plan in the user turn so it follows that plan instead of writing
        # its own. (custom_planning already includes the <planning></planning> tags.)
        synth_eval_prompt_ready += (
            "\n\nUse exactly this plan instead of writing your own <planning>:\n"
            + custom_planning
            + "\n\nThen output the <variables> block."
        )

    messages = [
        {
            "role": "user",
            "content": synth_eval_prompt_ready,
        }
    ]

    response = CLIENT.messages.create(
        max_tokens=8000,
        messages=messages,
        model=MODEL_NAME,
    )
    # The response can start with a thinking block, so read the text block rather than content[0].
    message = next(block.text for block in response.content if block.type == "text")

    return message
```

```python
# We'll use this function to sample Claude's response to the filled-in template,
# once we have our example values/test case.


def call_claude_with_template(prompt_template, variables):
    """Call Claude with a filled prompt template."""
    filled_template = prompt_template
    for var, value in variables.items():
        filled_template = filled_template.replace(f"{{{{{var}}}}}", value)

    response = CLIENT.messages.create(
        max_tokens=8000,
        messages=[
            {
                "role": "user",
                "content": filled_template,
            }
        ],
        model=MODEL_NAME,
    )
    # The response can start with a thinking block, so read the text block rather than content[0].
    message = next(block.text for block in response.content if block.type == "text")

    return message
```

現在可以開始把各部分組起來了。首先，在這裡輸入你的 prompt template。

```python
# Replace this with your prompt template!
# Use double-brackets to indicate variables
# Here's an example:
prompt_template = """You are a customer support bot for Acme Corporation.
Here is an FAQ with Acme's relevant policies:

<documents>
{{DOCUMENTS}}
</documents>

Please respond to this customer support question using details from the policies:

<question>
{{QUESTION}}
</question>"""

variables = extract_variables(prompt_template)
print("\nIdentified variables:")
for var in variables:
    print(f"- {var}")
```

??? note "輸出"

    ```text

    Identified variables:
    - DOCUMENTS
    - QUESTION
    ```

接下來，如果你有「golden examples」（輸入跟理想輸出），可以在這裡輸入。這段程式碼目前先註解掉。

```python
planning_text = None
USER_EXAMPLES = []

# if input("\nDo you want to provide an example value for your variables? (y/n): ").lower() == 'y':
#     example = {}
#     for var in variables:
#         example[var] = input(f"Enter an example value for {var}: ")
#     USER_EXAMPLES.append(example)
```

接著把產生測試案例的 prompt template 填入這些資訊，拿到一個測試案例！

```python
result = get_test_data(prompt_template, USER_EXAMPLES, planning_text)
```

現在來看看這個測試案例，以及 Claude 產生它時做的規劃。

```python
planning_match = re.search(r"<planning>(.*?)</planning>", result, re.DOTALL)
if planning_match and not planning_text:
    planning_text = "<planning>\n" + planning_match.group(1).strip() + "\n</planning>"

extracted_variables = {}
for var in variables:
    var_match = re.search(f"<{var}>(.*?)</{var}>", result[result.index("<variables>") :], re.DOTALL)
    if var_match:
        extracted_variables[var] = var_match.group(1).strip()

USER_EXAMPLES.append(extracted_variables)

print("~~~~~~~~~~~\nGenerated test case:\n~~~~~~~~~~~")
for var, value in extracted_variables.items():
    print(f"{var}:\n{value}\n")

print("~~~~~~~~~~~\nPlanning:\n~~~~~~~~~~~")
print(planning_text)
```

??? note "輸出"

    ```text
    ~~~~~~~~~~~
    Generated test case:
    ~~~~~~~~~~~
    DOCUMENTS:
    **Acme Corporation Customer Policies (Last updated: January 2025)**

    **1. Returns and Refunds**
    - Most items may be returned within 30 days of delivery for a full refund to the original payment method, provided they are unused and in their original packaging.
    - Items marked "Final Sale" or "Clearance" cannot be returned or exchanged, but are still covered by our warranty if defective (see Section 3).
    - Customers are responsible for return shipping costs unless the item arrived damaged or defective, or we sent the wrong item. In those cases, Acme will provide a prepaid return label.
    - Refunds are processed within 5-7 business days after we receive the returned item. Your bank may take an additional 3-5 business days to post the credit.
    - Original shipping fees are non-refundable unless the return is due to an Acme error.
    - Opened software, digital downloads, and gift cards are not eligible for return.

    **2. Shipping**
    - Standard shipping (5-8 business days) is free on orders over $50. Orders under $50 have a flat $5.99 shipping fee.
    - Expedited shipping (2-3 business days) costs $14.99. Overnight shipping costs $29.99 and must be ordered before 2:00 PM Eastern Time.
    - Acme currently ships to the United States and Canada only. International orders are not available at this time.
    - Once your order ships, you will receive a confirmation email with a tracking number. Orders typically ship within 1-2 business days of being placed.
    - Acme is not responsible for delays caused by carriers, weather, or incorrect shipping addresses provided by the customer.

    **3. Warranty**
    - All Acme-branded products include a 1-year limited warranty covering defects in materials and workmanship, starting from the date of delivery.
    - The warranty does not cover damage from misuse, accidents, unauthorized modifications, or normal wear and tear.
    - To make a warranty claim, contact Customer Support with your order number and a description or photo of the issue. Approved claims will be repaired or replaced at Acme's discretion.
    - Extended warranties (2 additional years) can be purchased within 30 days of the original purchase for 15% of the item's price.

    **4. Order Changes and Cancellations**
    - Orders can be modified or canceled within 1 hour of being placed by visiting the "My Orders" page in your account.
    - After 1 hour, orders enter processing and can no longer be changed. If the order has not yet shipped, you may contact Customer Support to request a cancellation, but we cannot guarantee it will be successful.
    - Once an order has shipped, it cannot be canceled. You may return it according to our Returns policy.

    **5. Contact Information**
    - Customer Support is available Monday-Friday, 9:00 AM to 8:00 PM Eastern Time, and Saturday, 10:00 AM to 4:00 PM Eastern Time.
    - Email: support@acmecorp.example | Phone: 1-800-555-0142 | Live chat available on acmecorp.example during business hours.
    - Please have your order number ready when contacting us. Response time for emails is typically within 24 hours.

    QUESTION:
    Hi, I bought a Roadrunner Blender from you guys about 3 weeks ago during the clearance sale and now the motor makes a burning smell whenever I turn it on. I'd like to send it back for a refund. Also, who pays for the shipping if I send it back? Thanks

    ... (省略 12 行)
    ```

接下來有好幾條路可以走。可以產生更多測試案例，也可以編輯 Claude 的規劃邏輯。我們稍微改一下規劃邏輯。比方說我們知道 ACME 的文件用編號行。其他合理的改法還有：

- 讓 Claude 告訴自己，把文件寫得更長、更詳細。
- 讓 Claude 告訴自己，把客服問題寫得更正式或更不正式。

```python
planning_text = planning_text.replace(
    "each with a question and answer format",
    "each with a question and answer format and associated number.",
)
# You might have slightly different planning text and therefore need to rewrite the replace.
```

我們重設範例，但把編輯過的規劃文字傳回給 Claude。`get_test_data` 會把它附加到 prompt，並叫 Claude 照這個規劃走，而不是自己重寫一份。

```python
USER_EXAMPLES = []
result = get_test_data(prompt_template, USER_EXAMPLES, planning_text)
```

現在來看新的結果。

```python
# Copied and pasted from a cell above.
planning_match = re.search(r"<planning>(.*?)</planning>", result, re.DOTALL)
if planning_match and not planning_text:
    planning_text = "<planning>\n" + planning_match.group(1).strip() + "\n</planning>"

extracted_variables = {}
for var in variables:
    var_match = re.search(f"<{var}>(.*?)</{var}>", result[result.index("<variables>") :], re.DOTALL)
    if var_match:
        extracted_variables[var] = var_match.group(1).strip()

USER_EXAMPLES.append(extracted_variables)

print("~~~~~~~~~~~\nGenerated test case:\n~~~~~~~~~~~")
for var, value in extracted_variables.items():
    print(f"{var}:\n{value}\n")

print("~~~~~~~~~~~\nPlanning:\n~~~~~~~~~~~")
print(planning_text)
```

??? note "輸出"

    ```text
    ~~~~~~~~~~~
    Generated test case:
    ~~~~~~~~~~~
    DOCUMENTS:
    ACME CORPORATION CUSTOMER POLICIES (Last updated: January 2024)

    SECTION 1: RETURNS AND REFUNDS

    Q: What is Acme's standard return policy?
    A: Most items purchased from Acme.com may be returned within 30 days of the delivery date for a full refund, provided they are unused, in their original packaging, and accompanied by proof of purchase. Refunds are issued to the original form of payment within 5-7 business days after we receive and inspect the returned item.

    Q: Are there items that cannot be returned?
    A: Yes. The following items are final sale and cannot be returned or exchanged: items marked "Clearance" or "Final Sale" at the time of purchase, custom or personalized products, perishable goods, and any product containing explosives (including the Acme Rocket Skates and Acme Dehydrated Boulders when opened). Gift cards are also non-refundable.

    Q: Who pays for return shipping?
    A: Customers are responsible for return shipping costs unless the item arrived damaged or defective, or we sent the wrong item. In those cases, Acme will email you a prepaid return label. A flat $7.95 restocking fee applies to returns of items over 50 lbs that are not defective.

    Q: Can I exchange an item instead of returning it?
    A: Yes. Exchanges for a different size, color, or model can be requested within 30 days of delivery. If the new item costs more, you will be charged the difference. If it costs less, the difference will be refunded to your original payment method.

    SECTION 2: SHIPPING

    Q: What shipping options are available?
    A: Standard Shipping (5-8 business days) is $5.99 on orders under $50 and free on orders of $50 or more. Expedited Shipping (2-3 business days) is $14.99. Overnight Shipping is $29.99 and must be ordered before 12:00 PM Pacific Time. We currently ship to the United States and Canada only.

    Q: How can I track my order?
    A: Once your order ships, you will receive an email with a tracking number and a link to the carrier's website. You can also view tracking information by logging in to your Acme account and selecting "Order History."

    Q: What if my package arrives damaged?
    A: Contact Customer Support within 14 days of delivery with your order number and photos of the damaged item and packaging. We will send a replacement or issue a full refund, at your choice.

    SECTION 3: WARRANTY

    Q: Does Acme offer a warranty?
    A: All Acme products come with a 90-day limited warranty covering defects in materials and workmanship. The warranty does not cover damage caused by misuse, unauthorized modifications, or normal wear and tear. It also does not cover damage resulting from use near cliffs, canyons, or desert highways. To make a warranty claim, contact Customer Support with your order number and a description of the problem.

    Q: Can I extend my warranty?
    A: Yes. Acme Protect extends your warranty to 2 years and is available for purchase within 30 days of your original order. Pricing varies by product.

    SECTION 4: ACCOUNT AND PAYMENT
    ... (省略 29 行)
    ```

太好了，它做出了編號的 Q 和 A！

再做一個例子。這個會用到我們已經有的範例，所以應該會有不一樣的有趣結果。

```python
result = get_test_data(prompt_template, USER_EXAMPLES, planning_text)
```

```python
# Copied and pasted from a cell above.
planning_match = re.search(r"<planning>(.*?)</planning>", result, re.DOTALL)
if planning_match and not planning_text:
    planning_text = "<planning>\n" + planning_match.group(1).strip() + "\n</planning>"

extracted_variables = {}
for var in variables:
    var_match = re.search(f"<{var}>(.*?)</{var}>", result[result.index("<variables>") :], re.DOTALL)
    if var_match:
        extracted_variables[var] = var_match.group(1).strip()

USER_EXAMPLES.append(extracted_variables)

print("~~~~~~~~~~~\nGenerated test case:\n~~~~~~~~~~~")
for var, value in extracted_variables.items():
    print(f"{var}:\n{value}\n")

print("~~~~~~~~~~~\nPlanning:\n~~~~~~~~~~~")
print(planning_text)
```

??? note "輸出"

    ```text
    ~~~~~~~~~~~
    Generated test case:
    ~~~~~~~~~~~
    DOCUMENTS:
    ACME CORPORATION CUSTOMER POLICIES (Last updated: March 2024)

    SECTION 1: ORDERS AND PAYMENT

    Q: What payment methods does Acme accept?
    A: We accept Visa, Mastercard, American Express, Discover, PayPal, and Acme Gift Cards. We do not accept personal checks, money orders, or cryptocurrency. Sales tax is calculated at checkout based on your shipping address.

    Q: Can I change or cancel my order after placing it?
    A: Orders can be changed or canceled within 1 hour of placement by logging in to your Acme account, opening "Order History," and selecting "Edit Order" or "Cancel Order." After 1 hour, orders enter our fulfillment process and can no longer be modified. If you no longer want the item, you may refuse delivery or return it once it arrives, subject to our return policy.

    Q: Can I use more than one promo code on an order?
    A: No. Only one promotional code may be applied per order. Promo codes cannot be applied to gift cards, Acme Protect plans, or items marked "Clearance."

    SECTION 2: SHIPPING AND DELIVERY

    Q: What are the shipping options and costs?
    A: Standard Shipping (5-8 business days) costs $6.49 for orders under $75 and is free for orders of $75 or more. Two-Day Shipping is $15.99. Overnight Shipping is $31.99 and must be ordered by 11:00 AM Pacific Time on a business day. Orders placed after the cutoff or on weekends ship the next business day.

    Q: Do you ship internationally?
    A: We currently ship to all 50 U.S. states, Puerto Rico, and Canada. We do not ship to P.O. boxes for orders containing oversized items. International shipping outside these regions is not available at this time.

    Q: My tracking says "Delivered" but I don't have my package. What should I do?
    A: First, check around your property and with neighbors, as carriers sometimes leave packages in unexpected places. Wait 24 hours, as tracking updates can occasionally be early. If the package has still not arrived, contact Customer Support within 7 days of the "Delivered" date and we will open an investigation with the carrier.

    Q: What should I do if my item arrives damaged or incorrect?
    A: Contact Customer Support within 10 days of delivery with your order number and photos of the item and its packaging. We will send a replacement at no cost or issue a full refund, whichever you prefer. We will email you a prepaid return label if a return is needed.

    SECTION 3: RETURNS AND REFUNDS

    Q: What is the standard return policy?
    A: Most items may be returned within 45 days of the delivery date for a full refund, provided they are unused, in their original packaging, and accompanied by proof of purchase. Refunds are issued to the original form of payment within 7-10 business days after we receive and inspect the item.

    Q: Which items are not eligible for return?
    A: The following are final sale: items marked "Clearance" or "Final Sale" at the time of purchase, custom-made or engraved products, perishable items, opened software or digital downloads, and gift cards. Items that have been used or damaged by the customer are also ineligible for refund.

    Q: Who pays for return shipping?
    ... (省略 38 行)
    ```

還是關於 ACME 公司，但問題不同，知識庫也不同。

從這裡開始，你想怎麼玩都行：可以用迴圈跑程式碼產生更多測試案例、繼續編輯規劃、用這些測試案例評估 Claude，或把你做出的測試案例連同 golden answer 放進 prompt 當 multishot 範例。

要拿到 golden answer，可以自己從頭寫，或讓 Claude 先寫一個答案再依你的喜好修改。現在有了 prompt caching，在 prompt 裡塞大量範例來改善表現，比以前划算很多。

## 重點整理

- 沒有真實資料可測時，可以讓 Claude 依 prompt template 的變數規格編出合成測試資料。
- 先讓 Claude 規劃再產生，規劃文字可以人工編輯，是控制資料樣貌的好槓桿。
- 有 golden example 時放進去，生成的資料會更貼近真實分布。
- 測試資料可以做 prompt 評估，也可以搭配 golden answer 當 multishot 範例。
- 搭配 prompt caching，塞很多範例進 prompt 的成本更低。

## 練習

1. 把你自己的 prompt template 填進去，只改變數名稱與描述，產生一筆測試案例。
2. 修改規劃文字，要求文件更長或客服問題更正式，比較前後產生的資料差異。
3. 寫個迴圈，連續產生 5 筆測試案例並存成 JSON，再各自丟進原本的 prompt 看輸出是否穩定。
