---
translated: true
source: patterns/agents/basic_workflows.ipynb
---

# 基本 workflow

> 原文：[patterns/agents/basic_workflows.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/basic_workflows.ipynb)

三種簡單的 multi-LLM workflow pattern，用成本或延遲換取更好的表現。

## 這篇在做什麼

示範三種簡單的 multi-LLM workflow：prompt chaining、parallelization、routing，各自搭配一個實際範例。這些是示範核心概念的範例實作，不是 production 程式碼。

## 學完你會

- 用 prompt chaining 把任務拆成循序步驟，做結構化資料擷取和格式化
- 用 parallelization 把獨立子任務同時交給多個 LLM
- 用 routing 依輸入特性選擇不同的專門處理路徑

## 基本 Multi-LLM Workflow

這份 notebook 示範三種簡單的 multi-LLM workflow。它們用成本或延遲，換取可能更好的任務表現：

1. **Prompt-Chaining**：把任務拆成循序的子任務，每一步都建立在前一步的結果上
2. **Parallelization**：把獨立的子任務分給多個 LLM 同時處理
3. **Routing**：依輸入的特性動態選擇專門的 LLM 路徑

注意：這些是示範核心概念的範例實作，不是 production 程式碼。

```python
from concurrent.futures import ThreadPoolExecutor

from util import extract_xml, llm_call
```

```python
def chain(input: str, prompts: list[str]) -> str:
    """Chain multiple LLM calls sequentially, passing results between steps."""
    result = input
    for i, prompt in enumerate(prompts, 1):
        print(f"\nStep {i}:")
        result = llm_call(f"{prompt}\nInput: {result}")
        print(result)
    return result


def parallel(prompt: str, inputs: list[str], n_workers: int = 3) -> list[str]:
    """Process multiple inputs concurrently with the same prompt."""
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(llm_call, f"{prompt}\nInput: {x}") for x in inputs]
        return [f.result() for f in futures]


def route(input: str, routes: dict[str, str]) -> str:
    """Route input to specialized prompt using content classification."""
    # First determine appropriate route using LLM with chain-of-thought
    print(f"\nAvailable routes: {list(routes.keys())}")
    selector_prompt = f"""
    Analyze the input and select the most appropriate support team from these options: {list(routes.keys())}
    First explain your reasoning, then provide your selection in this XML format:

    <reasoning>
    Brief explanation of why this ticket should be routed to a specific team.
    Consider key terms, user intent, and urgency level.
    </reasoning>

    <selection>
    The chosen team name
    </selection>

    Input: {input}""".strip()

    route_response = llm_call(selector_prompt)
    reasoning = extract_xml(route_response, "reasoning")
    route_key = extract_xml(route_response, "selection").strip().lower()

    print("Routing Analysis:")
    print(reasoning)
    print(f"\nSelected route: {route_key}")

    # Process input with selected specialized prompt
    selected_prompt = routes[route_key]
    return llm_call(f"{selected_prompt}\nInput: {input}")
```

## 使用範例

下面是示範每種 workflow 的實際例子：
1. 用 chain workflow 做結構化資料擷取與格式化
2. 用 parallelization workflow 做利害關係人影響分析
3. 用 route workflow 處理客服 ticket

```python
# Example 1: Chain workflow for structured data extraction and formatting
# Each step progressively transforms raw text into a formatted table

data_processing_steps = [
    """Extract only the numerical values and their associated metrics from the text.
    Format each as 'value: metric' on a new line.
    Example format:
    92: customer satisfaction
    45%: revenue growth""",
    """Convert all numerical values to percentages where possible.
    If not a percentage or points, convert to decimal (e.g., 92 points -> 92%).
    Keep one number per line.
    Example format:
    92%: customer satisfaction
    45%: revenue growth""",
    """Sort all lines in descending order by numerical value.
    Keep the format 'value: metric' on each line.
    Example:
    92%: customer satisfaction
    87%: employee satisfaction""",
    """Format the sorted data as a markdown table with columns:
    | Metric | Value |
    |:--|--:|
    | Customer Satisfaction | 92% |""",
]

report = """
Q3 Performance Summary:
Our customer satisfaction score rose to 92 points this quarter.
Revenue grew by 45% compared to last year.
Market share is now at 23% in our primary market.
Customer churn decreased to 5% from 8%.
New user acquisition cost is $43 per user.
Product adoption rate increased to 78%.
Employee satisfaction is at 87 points.
Operating margin improved to 34%.
"""

print("\nInput text:")
print(report)
formatted_result = chain(report, data_processing_steps)
```

??? note "輸出"

    ```text

    Input text:

    Q3 Performance Summary:
    Our customer satisfaction score rose to 92 points this quarter.
    Revenue grew by 45% compared to last year.
    Market share is now at 23% in our primary market.
    Customer churn decreased to 5% from 8%.
    New user acquisition cost is $43 per user.
    Product adoption rate increased to 78%.
    Employee satisfaction is at 87 points.
    Operating margin improved to 34%.


    Step 1:
    92: customer satisfaction points
    45%: revenue growth
    23%: market share
    5%: customer churn
    8%: previous customer churn
    $43: user acquisition cost
    78%: product adoption rate
    87: employee satisfaction points
    34%: operating margin

    Step 2:
    92%: customer satisfaction
    45%: revenue growth
    23%: market share
    5%: customer churn
    8%: previous customer churn
    43.0: user acquisition cost
    78%: product adoption rate
    87%: employee satisfaction
    34%: operating margin

    Step 3:
    Here are the lines sorted in descending order by numerical value:

    92%: customer satisfaction
    ... (省略 21 行)
    ```

```python
# Example 2: Parallelization workflow for stakeholder impact analysis
# Process impact analysis for multiple stakeholder groups concurrently

stakeholders = [
    """Customers:
    - Price sensitive
    - Want better tech
    - Environmental concerns""",
    """Employees:
    - Job security worries
    - Need new skills
    - Want clear direction""",
    """Investors:
    - Expect growth
    - Want cost control
    - Risk concerns""",
    """Suppliers:
    - Capacity constraints
    - Price pressures
    - Tech transitions""",
]

impact_results = parallel(
    """Analyze how market changes will impact this stakeholder group.
    Provide specific impacts and recommended actions.
    Format with clear sections and priorities.""",
    stakeholders,
)

for result in impact_results:
    print(result)
    print("+" * 80)
```

??? note "輸出"

    ```text
    MARKET IMPACT ANALYSIS FOR CUSTOMERS
    ==================================

    HIGH PRIORITY IMPACTS
    -------------------
    1. Price Sensitivity
    - Rising inflation and costs likely to reduce purchasing power
    - Increased competition for value-oriented products
    - Risk of trading down to lower-cost alternatives

    Recommended Actions:
    • Introduce tiered pricing options
    • Develop value-focused product lines
    • Create loyalty programs with price benefits
    • Highlight total cost of ownership benefits

    2. Technology Demands
    - Accelerating tech advancement creating higher expectations
    - Integration of AI and smart features becoming standard
    - Mobile/digital-first experience requirements

    Recommended Actions:
    • Accelerate digital transformation initiatives
    • Invest in user experience improvements
    • Develop smart product features
    • Provide tech education and support

    MEDIUM PRIORITY IMPACTS
    ----------------------
    3. Environmental Consciousness
    - Growing demand for sustainable products
    - Increased scrutiny of environmental practices
    - Willingness to pay premium for eco-friendly options

    Recommended Actions:
    • Develop eco-friendly product lines
    • Improve packaging sustainability
    • Communicate environmental initiatives
    • Create recycling programs

    ... (省略 211 行)
    ```

```python
# Example 3: Route workflow for customer support ticket handling
# Route support tickets to appropriate teams based on content analysis

support_routes = {
    "billing": """You are a billing support specialist. Follow these guidelines:
    1. Always start with "Billing Support Response:"
    2. First acknowledge the specific billing issue
    3. Explain any charges or discrepancies clearly
    4. List concrete next steps with timeline
    5. End with payment options if relevant

    Keep responses professional but friendly.

    Input: """,
    "technical": """You are a technical support engineer. Follow these guidelines:
    1. Always start with "Technical Support Response:"
    2. List exact steps to resolve the issue
    3. Include system requirements if relevant
    4. Provide workarounds for common problems
    5. End with escalation path if needed

    Use clear, numbered steps and technical details.

    Input: """,
    "account": """You are an account security specialist. Follow these guidelines:
    1. Always start with "Account Support Response:"
    2. Prioritize account security and verification
    3. Provide clear steps for account recovery/changes
    4. Include security tips and warnings
    5. Set clear expectations for resolution time

    Maintain a serious, security-focused tone.

    Input: """,
    "product": """You are a product specialist. Follow these guidelines:
    1. Always start with "Product Support Response:"
    2. Focus on feature education and best practices
    3. Include specific examples of usage
    4. Link to relevant documentation sections
    5. Suggest related features that might help

    Be educational and encouraging in tone.

    Input: """,
}

# Test with different support tickets
tickets = [
    """Subject: Can't access my account
    Message: Hi, I've been trying to log in for the past hour but keep getting an 'invalid password' error.
    I'm sure I'm using the right password. Can you help me regain access? This is urgent as I need to
    submit a report by end of day.
    - John""",
    """Subject: Unexpected charge on my card
    Message: Hello, I just noticed a charge of $49.99 on my credit card from your company, but I thought
    I was on the $29.99 plan. Can you explain this charge and adjust it if it's a mistake?
    Thanks,
    Sarah""",
    """Subject: How to export data?
    Message: I need to export all my project data to Excel. I've looked through the docs but can't
    figure out how to do a bulk export. Is this possible? If so, could you walk me through the steps?
    Best regards,
    Mike""",
]

print("Processing support tickets...\n")
for i, ticket in enumerate(tickets, 1):
    print(f"\nTicket {i}:")
    print("-" * 40)
    print(ticket)
    print("\nResponse:")
    print("-" * 40)
    response = route(ticket, support_routes)
    print(response)
    print("+" * 80)
```

??? note "輸出"

    ```text
    Processing support tickets...


    Ticket 1:
    ----------------------------------------
    Subject: Can't access my account
        Message: Hi, I've been trying to log in for the past hour but keep getting an 'invalid password' error. 
        I'm sure I'm using the right password. Can you help me regain access? This is urgent as I need to 
        submit a report by end of day.
        - John

    Response:
    ----------------------------------------

    Available routes: ['billing', 'technical', 'account', 'product']
    Routing Analysis:

    This issue is clearly related to account access and authentication problems. The user is experiencing login difficulties with their password, which is a core account security and access issue. While there might be technical aspects involved, the primary concern is account access restoration. The urgency mentioned by the user and the nature of the problem (password/login issues) makes this a typical account support case. Account team specialists are best equipped to handle password resets, account verification, and access restoration procedures.


    Selected route: account
    Account Support Response:

    Dear John,

    I understand your urgency regarding account access. Before proceeding with account recovery, we must verify your identity to maintain security protocols.

    Immediate Steps for Account Recovery:
    1. Visit our secure password reset page at [secure portal URL]
    2. Click "Forgot Password"
    3. Enter your email address associated with the account
    4. Follow the verification instructions sent to your email

    Important Security Notes:
    • The reset link expires in 30 minutes
    • Do not share reset links or verification codes with anyone
    • Ensure you're on our official website (check for https:// and correct domain)

    WARNING: If you're unable to access your email or receive the reset link, additional verification will be required through our identity verification process.

    ... (省略 134 行)
    ```

## 重點整理

- 三種 pattern 都是用額外的 LLM 呼叫換品質，代價是成本或延遲。
- chaining 適合能拆成固定順序的任務，每步輸入是上一步輸出。
- parallelization 適合彼此獨立的子任務，能降低總延遲。
- routing 先分類再交給專門的 prompt，讓每條路徑都更精準。

## 練習

1. 在 chain 範例多加一個步驟（例如最後翻譯成英文）。
2. 在 parallelization 範例多加一個利害關係人，看結果如何。
3. 在 routing 範例新增一種 ticket 類別和對應的 prompt。
