---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/agents_sdk/evaluate_agents.ipynb
---
# 用 Langfuse 評估 Agent

> 原文：[examples/agents_sdk/evaluate_agents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/evaluate_agents.ipynb)



## 這篇在做什麼
用 Langfuse 追蹤 OpenAI Agents SDK 跑 agent 時的每個內部步驟（trace），再用線上和離線兩種方式評估 agent 表現。線上看成本、延遲、使用者回饋、LLM-as-a-Judge，離線用資料集批次跑 agent 並比較不同設定。

## 學完你會
- 用 Pydantic Logfire 的 instrumentation，把 OpenAI Agents SDK 的 trace 送到 Langfuse 的 OpenTelemetry backend。
- 替 trace 加上 `user_id`、`session_id`、tags，收集使用者 thumbs up/down，並設定 LLM-as-a-Judge 自動打分。
- 把 Hugging Face 的資料集匯入 Langfuse，批次跑 agent，並比較不同 `WebSearchTool` context 大小的正確率。

## 開跑前
- 需要 Langfuse 帳號和 API keys（cloud 版有免費額度）。
- 需要 `OPENAI_API_KEY`，範例會呼叫 `gpt-4o` 和 `gpt-4o-mini`。


在這份 cookbook 裡，我們要學會如何用 [Langfuse](https://langfuse.com/docs) **監控 [OpenAI agent SDK](https://github.com/openai/openai-agents-python) 的內部步驟（traces）**，並**評估它的表現**。

這份指南涵蓋**線上**和**離線評估**指標，是團隊用來快速又穩當地把 agent 推上 production 的做法。想進一步了解評估策略，可以看這篇 [blog post](https://langfuse.com/blog/2025-03-04-llm-evaluation-101-best-practices-and-challenges)。

**為什麼 AI agent 評估很重要：**
- 任務失敗或結果不理想時，方便 debug
- 即時監控成本和效能
- 透過持續的回饋，提高可靠度和安全性

<br>

<div style="position: relative; padding-top: 69.85769728331177%;">
  <iframe
    src="https://customer-xnej9vqjtgxpafyk.cloudflarestream.com/e335d35a0a762b76055f3e0b977f3380/iframe?muted=true&loop=true&autoplay=true&poster=https%3A%2F%2Fcustomer-xnej9vqjtgxpafyk.cloudflarestream.com%2Fe335d35a0a762b76055f3e0b977f3380%2Fthumbnails%2Fthumbnail.jpg%3Ftime%3D%26height%3D600&controls=false"
    loading="lazy"
    style="border: white; position: absolute; top: 0; left: 0; height: 100%; width: 100%; border-radius: 10px;"
    allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture;"
    allowfullscreen="true"
  ></iframe>
</div>

## Step 0：安裝需要的函式庫

下面安裝 `openai-agents` 函式庫（[OpenAI Agents SDK](https://github.com/openai/openai-agents-python)）、`pydantic-ai[logfire]` 的 OpenTelemetry instrumentation、`langfuse`，以及 Hugging Face 的 `datasets` 函式庫

```python
%pip install openai-agents nest_asyncio "pydantic-ai[logfire]" langfuse datasets
```

## Step 1：替你的 Agent 加上 Instrumentation

這個 notebook 用 [Langfuse](https://langfuse.com/) 來 trace、debug 和評估我們的 agent。

**注意：** 如果你用的是 LlamaIndex 或 LangGraph，可以在[這裡](https://langfuse.com/docs/integrations/llama-index/workflows)和[這裡](https://langfuse.com/docs/integrations/langchain/example-python-langgraph)找到對應的 instrumentation 文件。

```python
import os
import base64

# Get keys for your project from the project settings page: https://cloud.langfuse.com
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-..." 
os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-..." 
os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com" # 🇪🇺 EU region
# os.environ["LANGFUSE_HOST"] = "https://us.cloud.langfuse.com" # 🇺🇸 US region

# Build Basic Auth header.
LANGFUSE_AUTH = base64.b64encode(
    f"{os.environ.get('LANGFUSE_PUBLIC_KEY')}:{os.environ.get('LANGFUSE_SECRET_KEY')}".encode()
).decode()
 
# Configure OpenTelemetry endpoint & headers
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = os.environ.get("LANGFUSE_HOST") + "/api/public/otel"
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

# Your openai key
os.environ["OPENAI_API_KEY"] = "sk-proj-..."
```

環境變數設好後，就可以初始化 Langfuse client。`get_client()` 會用環境變數裡提供的憑證初始化 Langfuse client。

```python
from langfuse import get_client
 
langfuse = get_client()
 
# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")
```

Pydantic Logfire 提供了 OpenAI Agents SDK 的 instrumentation。我們用它把 trace 送到 [Langfuse OpenTelemetry Backend](https://langfuse.com/docs/opentelemetry/get-started)。

```python
import nest_asyncio
nest_asyncio.apply()
```

```python
import logfire

# Configure logfire instrumentation.
logfire.configure(
    service_name='my_agent_service',

    send_to_logfire=False,
)
# This method automatically patches the OpenAI Agents SDK to send logs via OTLP to Langfuse.
logfire.instrument_openai_agents()
```

## Step 2：測試你的 Instrumentation

這是一個簡單的 Q&A agent。我們跑它來確認 instrumentation 有正常運作。如果一切設定正確，你會在 observability dashboard 看到 logs / spans。

```python
import asyncio
from agents import Agent, Runner

async def main():
    agent = Agent(
        name="Assistant",
        instructions="You are a senior software engineer",
    )

    result = await Runner.run(agent, "Tell me why it is important to evaluate AI agents.")
    print(result.final_output)

loop = asyncio.get_running_loop()
await loop.create_task(main())

langfuse.flush()
```

??? note "輸出"

    ```text
    13:00:52.784 OpenAI Agents trace: Agent workflow
    13:00:52.787   Agent run: 'Assistant'
    13:00:52.797     Responses API with 'gpt-4o'
    Evaluating AI agents is crucial for several reasons:

    1. **Performance Assessment**: It helps determine if the agent meets the desired goals and performs tasks effectively. By evaluating, we can assess accuracy, speed, and overall performance.

    2. **Reliability and Consistency**: Regular evaluation ensures that the AI behaves consistently under different conditions and is reliable in production environments.

    3. **Bias and Fairness**: Identifying and mitigating biases is essential for fair and ethical AI. Evaluation helps uncover any discriminatory patterns in the agent's behavior.

    4. **Safety**: Evaluating AI agents ensures they operate safely and do not cause harm or unintended side effects, especially in critical applications.

    5. **User Trust**: Proper evaluation builds trust with users and stakeholders by demonstrating that the AI is effective and aligned with expectations.

    6. **Regulatory Compliance**: It ensures adherence to legal and ethical standards, which is increasingly important as regulations around AI evolve.

    7. **Continuous Improvement**: Ongoing evaluation provides insights that can be used to improve the agent over time, optimizing performance and adapting to new challenges.

    8. **Resource Efficiency**: Evaluating helps ensure that the AI agent uses resources effectively, which can reduce costs and improve scalability.

    In summary, evaluation is essential to ensure AI agents are effective, ethical, and aligned with user needs and societal norms.
    ```

到你的 [Langfuse Traces Dashboard](https://cloud.langfuse.com/traces) 確認 spans 和 logs 都有被記錄下來。

Langfuse 裡的 trace 範例：

![Example trace in Langfuse](https://langfuse.com/images/cookbook/integration_openai-agents/first-example-trace.png)

_[Link to the trace](https://cloud.langfuse.com/project/cloramnkj0002jz088vzn1ja4/traces/0195948781a9f0d78fd5e067154aa508?timestamp=2025-03-14T12%3A01%3A03.401Z&observation=64bcac3cb82d04e9)_

## Step 3：觀察並評估比較複雜的 Agent

確認 instrumentation 可以用之後，我們試一個比較複雜的查詢，看看進階指標（token 用量、延遲、成本等）是怎麼被追蹤的。

```python
import asyncio
from agents import Agent, Runner, function_tool

# Example function tool.
@function_tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny."

agent = Agent(
    name="Hello world",
    instructions="You are a helpful agent.",
    tools=[get_weather],
)

async def main():
    result = await Runner.run(agent, input="What's the weather in Berlin?")
    print(result.final_output)

loop = asyncio.get_running_loop()
await loop.create_task(main())
```

??? note "輸出"

    ```text
    13:01:15.351 OpenAI Agents trace: Agent workflow
    13:01:15.355   Agent run: 'Hello world'
    13:01:15.364     Responses API with 'gpt-4o'
    13:01:15.999     Function: get_weather
    13:01:16.000     Responses API with 'gpt-4o'
    The weather in Berlin is currently sunny.
    ```

### Trace 結構

Langfuse 會記錄一個 **trace**，裡面包含 **spans**，每個 span 代表 agent 邏輯的一個步驟。這裡的 trace 包含整個 agent 執行，以及下面幾個子 span：
- tool call（get_weather）
- LLM 呼叫（用 'gpt-4o' 的 Responses API）

你可以檢視這些 span，精確看到時間花在哪、用了多少 token 等等：

![Trace tree in Langfuse](https://langfuse.com/images/cookbook/integration_openai-agents/trace-tree.png)

_[Link to the trace](https://cloud.langfuse.com/project/cloramnkj0002jz088vzn1ja4/traces/019594b5b9a27c5d497b13be71e7f255?timestamp=2025-03-14T12%3A51%3A32.386Z&display=preview&observation=6374a3c96baf831d)_

## 線上評估

線上評估指的是在真實的線上環境評估 agent，也就是 production 的實際使用過程。這包括監控 agent 在真實使用者互動上的表現，並持續分析結果。

我們寫了一份不同評估技術的指南，在[這裡](https://langfuse.com/blog/2025-03-04-llm-evaluation-101-best-practices-and-challenges)。

### Production 常追蹤的指標

1. **成本**：instrumentation 會記錄 token 用量，你再給每個 token 設定價格，就能換算成大約的成本。
2. **延遲**：觀察每個步驟或整次執行完成需要多久。
3. **使用者回饋**：使用者可以直接給回饋（thumbs up/down），幫助改進或修正 agent。
4. **LLM-as-a-Judge**：用另一個 LLM 近乎即時地評估 agent 的輸出（例如檢查是否有毒性或正確性）。

下面示範這些指標的例子。

#### 1. 成本

下面的截圖顯示 `gpt-4o` 呼叫的用量。這有助於找出花費高的步驟，優化你的 agent。

![Costs](https://langfuse.com/images/cookbook/integration_openai-agents/gpt-4o-costs.png)

_[Link to the trace](https://cloud.langfuse.com/project/cloramnkj0002jz088vzn1ja4/traces/019594b5b9a27c5d497b13be71e7f255?timestamp=2025-03-14T12%3A51%3A32.386Z&display=preview&observation=6374a3c96baf831d)_

#### 2. 延遲

我們也能看到每個步驟花了多久。下面的例子裡，整次執行花了 7 秒，可以再依步驟拆解。這有助於找出瓶頸，優化你的 agent。

![Latency](https://langfuse.com/images/cookbook/integration_openai-agents/openai-agent-latency.png)

_[Link to the trace](https://cloud.langfuse.com/project/cloramnkj0002jz088vzn1ja4/traces/019594b5b9a27c5d497b13be71e7f255?timestamp=2025-03-14T12%3A51%3A32.386Z&display=timeline&observation=b12967a01b3f8bcb)_

#### 3. 額外屬性

Langfuse 讓你可以替 span 傳入額外屬性，包括 `user_id`、`tags`、`session_id` 和自訂的 `metadata`。用這些資訊豐富 trace，對分析、debug，以及監控應用在不同使用者或 session 的行為很重要。

這個例子裡，我們傳了 [user_id](https://langfuse.com/docs/tracing-features/users)、[session_id](https://langfuse.com/docs/tracing-features/sessions) 和 [trace_tags](https://langfuse.com/docs/tracing-features/tags) 給 Langfuse。 

```python
input_query = "Why is AI agent evaluation important?"

with langfuse.start_as_current_span(
    name="OpenAI-Agent-Trace",
    ) as span:
    
    # Run your application here
    async def main(input_query):
            agent = Agent(
                name = "Assistant",
                instructions = "You are a helpful assistant.",
            )

            result = await Runner.run(agent, input_query)
            print(result.final_output)
            return result

    result = await main(input_query)
 
    # Pass additional attributes to the span
    span.update_trace(
        input=input_query,
        output=result,
        user_id="user_123",
        session_id="my-agent-session",
        tags=["staging", "demo", "OpenAI Agent SDK"],
        metadata={"email": "user@langfuse.com"},
        version="1.0.0"
        )
 
# Flush events in short-lived applications
langfuse.flush()
```

??? note "輸出"

    ```text
    13:02:41.552 OpenAI Agents trace: Agent workflow
    13:02:41.553   Agent run: 'Assistant'
    13:02:41.554     Responses API with 'gpt-4o'
    AI agent evaluation is crucial for several reasons:

    1. **Performance Metrics**: It helps determine how well an AI agent performs its tasks, ensuring it meets the desired standards and objectives.

    2. **Reliability and Safety**: Evaluation ensures the agent behaves consistently and safely in different scenarios, reducing risks of unintended consequences.

    3. **Bias Detection**: By evaluating AI agents, developers can identify and mitigate biases, ensuring fair and equitable outcomes for all users.

    4. **Benchmarking and Comparison**: Evaluation allows for the comparison of different AI models or versions, facilitating improvements and advancements.

    5. **User Trust**: Demonstrating the effectiveness and reliability of an AI agent builds trust with users, encouraging adoption and usage.

    6. **Regulatory Compliance**: Proper evaluation helps ensure AI systems meet legal and regulatory requirements, which is especially important in sensitive domains like healthcare or finance.

    7. **Scalability and Deployment**: Evaluation helps determine if an AI agent can scale effectively and function accurately in real-world environments.

    Overall, AI agent evaluation is key to developing effective, trustworthy, and ethical AI systems.
    ```

![Example trace in Langfuse](https://langfuse.com/images/cookbook/integration_openai-agents/openai-agent-sdk-custom-attributes.png)

#### 4. 使用者回饋

如果你的 agent 嵌在使用者介面裡，可以記錄使用者的直接回饋（例如聊天介面的 thumbs up/down）。下面用 `IPython.display` 做一個簡單的回饋機制。

下面的程式碼裡，使用者送出聊天訊息時，我們會抓取 OpenTelemetry trace ID。如果使用者對上一則回答按讚或倒讚，我們就把一個分數附加到那個 trace 上。

```python
from agents import Agent, Runner, WebSearchTool
from opentelemetry.trace import format_trace_id
import ipywidgets as widgets
from IPython.display import display
from langfuse import get_client
 
langfuse = get_client()

# Define your agent with the web search tool
agent = Agent(
    name="WebSearchAgent",
    instructions="You are an agent that can search the web.",
    tools=[WebSearchTool()]
)

def on_feedback(button):
    if button.icon == "thumbs-up":
      langfuse.create_score(
            value=1,
            name="user-feedback",
            comment="The user gave this response a thumbs up",
            trace_id=trace_id
        )
    elif button.icon == "thumbs-down":
      langfuse.create_score(
            value=0,
            name="user-feedback",
            comment="The user gave this response a thumbs down",
            trace_id=trace_id
        )
    print("Scored the trace in Langfuse")

user_input = input("Enter your question: ")

# Run agent
with langfuse.start_as_current_span(
    name="OpenAI-Agent-Trace",
    ) as span:
    
    # Run your application here
    result = Runner.run_sync(agent, user_input)
    print(result.final_output)

    result = await main(user_input)
    trace_id = langfuse.get_current_trace_id()

    span.update_trace(
        input=user_input,
        output=result.final_output,
    )

# Get feedback
print("How did you like the agent response?")

thumbs_up = widgets.Button(description="👍", icon="thumbs-up")
thumbs_down = widgets.Button(description="👎", icon="thumbs-down")

thumbs_up.on_click(on_feedback)
thumbs_down.on_click(on_feedback)

display(widgets.HBox([thumbs_up, thumbs_down]))

# Flush events in short-lived applications
langfuse.flush()
```

??? note "輸出"

    ```text
    Enter your question: What is Langfuse?
    13:54:41.574 OpenAI Agents trace: Agent workflow
    13:54:41.575   Agent run: 'WebSearchAgent'
    13:54:41.577     Responses API with 'gpt-4o'
    Langfuse is an open-source engineering platform designed to enhance the development, monitoring, and optimization of Large Language Model (LLM) applications. It offers a suite of tools that provide observability, prompt management, evaluations, and metrics, facilitating the debugging and improvement of LLM-based solutions. ([toolkitly.com](https://www.toolkitly.com/langfuse?utm_source=openai))

    **Key Features of Langfuse:**

    - **LLM Observability:** Langfuse enables developers to monitor and analyze the performance of language models by tracking API calls, user inputs, prompts, and outputs. This observability aids in understanding model behavior and identifying areas for improvement. ([toolkitly.com](https://www.toolkitly.com/langfuse?utm_source=openai))

    - **Prompt Management:** The platform provides tools for managing, versioning, and deploying prompts directly within Langfuse. This feature allows for efficient organization and refinement of prompts to optimize model responses. ([toolkitly.com](https://www.toolkitly.com/langfuse?utm_source=openai))

    - **Evaluations and Metrics:** Langfuse offers capabilities to collect and calculate scores for LLM completions, run model-based evaluations, and gather user feedback. It also tracks key metrics such as cost, latency, and quality, providing insights through dashboards and data exports. ([toolkitly.com](https://www.toolkitly.com/langfuse?utm_source=openai))

    - **Playground Environment:** The platform includes a playground where users can interactively experiment with different models and prompts, facilitating prompt engineering and testing. ([toolkitly.com](https://www.toolkitly.com/langfuse?utm_source=openai))

    - **Integration Capabilities:** Langfuse integrates seamlessly with various tools and frameworks, including LlamaIndex, LangChain, OpenAI SDK, LiteLLM, and more, enhancing its functionality and allowing for the development of complex applications. ([toolerific.ai](https://toolerific.ai/ai-tools/opensource/langfuse-langfuse?utm_source=openai))

    - **Open Source and Self-Hosting:** Being open-source, Langfuse allows developers to customize and extend the platform according to their specific needs. It can be self-hosted, providing full control over infrastructure and data. ([vafion.com](https://www.vafion.com/blog/unlocking-power-language-models-langfuse/?utm_source=openai))

    Langfuse is particularly valuable for developers and researchers working with LLMs, offering a comprehensive set of tools to improve the performance and reliability of LLM applications. Its flexibility, integration capabilities, and open-source nature make it a robust choice for those seeking to enhance their LLM projects. 
    How did you like the agent response?
    ```

    ```text
    HBox(children=(Button(description='👍', icon='thumbs-up', style=ButtonStyle()), Button(description='👎', icon='t…
    ```

    ```text
    Scored the trace in Langfuse
    ```

使用者回饋就會被記錄在 Langfuse：

![User feedback is being captured in Langfuse](https://langfuse.com/images/cookbook/integration_openai-agents/open-ai-agent-user-feedback.png)

#### 5. LLM-as-a-Judge

LLM-as-a-Judge 是另一種自動評估 agent 輸出的方式。你可以另外設一個 LLM 呼叫，來判斷輸出的正確性、毒性、風格，或任何你在意的標準。

**流程**：
1. 你定義一個 **Evaluation Template**，例如「檢查這段文字是否有毒」。
2. 你指定一個模型當 judge model，這裡用 `gpt-4o-mini`。
3. 每次 agent 產生輸出，就把輸出連同 template 交給你的「judge」LLM。
4. judge LLM 回覆一個評分或標籤，你再把它記錄到 observability 工具。

Langfuse 的範例：

![LLM-as-a-Judge Evaluation Template](https://langfuse.com/images/cookbook/integration_openai-agents/evaluator-template.png)
![LLM-as-a-Judge Evaluator](https://langfuse.com/images/cookbook/integration_openai-agents/evaluator.png)

```python
# Example: Checking if the agent’s output is toxic or not.
from agents import Agent, Runner, WebSearchTool

# Define your agent with the web search tool
agent = Agent(
    name="WebSearchAgent",
    instructions="You are an agent that can search the web.",
    tools=[WebSearchTool()]
)

input_query = "Is eating carrots good for the eyes?"

# Run agent
with langfuse.start_as_current_span(name="OpenAI-Agent-Trace") as span:
    # Run your agent with a query
    result = Runner.run_sync(agent, input_query)

    # Add input and output values to parent trace
    span.update_trace(
        input=input_query,
        output=result.final_output,
    )
```

??? note "輸出"

    ```text
    14:05:34.735 OpenAI Agents trace: Agent workflow
    14:05:34.736   Agent run: 'WebSearchAgent'
    14:05:34.738     Responses API with 'gpt-4o'
    ```

可以看到這個例子的回答被判定為 "not toxic"。

![LLM-as-a-Judge Evaluation Score](https://langfuse.com/images/cookbook/integration_openai-agents/llm-as-a-judge-score.png)

#### 6. Observability 指標總覽

所有這些指標都可以一起放在 dashboard 上視覺化。這樣你能很快看到 agent 在大量 session 中的表現，也能追蹤品質指標隨時間的變化。

![Observability metrics overview](https://langfuse.com/images/cookbook/integration_openai-agents/dashboard-dark.png)

## 離線評估

線上評估對即時回饋很重要，但你也需要**離線評估**，也就是在開發前或開發中做系統性的檢查。這有助於在改動上線前維持品質和可靠度。

### 資料集評估

離線評估通常會做這幾件事：
1. 準備一個 benchmark 資料集（有 prompt 和預期輸出的配對）
2. 在這個資料集上跑你的 agent
3. 把輸出跟預期結果比對，或用額外的評分機制

下面用 [search-dataset](https://huggingface.co/datasets/junzhang1207/search-dataset) 示範這個做法，它包含可以透過 web search tool 回答的問題，和預期答案。

```python
import pandas as pd
from datasets import load_dataset

# Fetch search-dataset from Hugging Face
dataset = load_dataset("junzhang1207/search-dataset", split = "train")
df = pd.DataFrame(dataset)
print("First few rows of search-dataset:")
print(df.head())
```

??? note "輸出"

    ```text
    README.md:   0%|          | 0.00/2.12k [00:00<?, ?B/s]
    ```

    ```text
    data-samples.json:   0%|          | 0.00/2.48k [00:00<?, ?B/s]
    ```

    ```text
    data.jsonl:   0%|          | 0.00/316k [00:00<?, ?B/s]
    ```

    ```text
    Generating train split:   0%|          | 0/934 [00:00<?, ? examples/s]
    ```

    ```text
    First few rows of GSM8K dataset:
                                         id  \
    0  20caf138-0c81-4ef9-be60-fe919e0d68d4   
    1  1f37d9fd-1bcc-4f79-b004-bc0e1e944033   
    2  76173a7f-d645-4e3e-8e0d-cca139e00ebe   
    3  5f5ef4ca-91fe-4610-a8a9-e15b12e3c803   
    4  64dbed0d-d91b-4acd-9a9c-0a7aa83115ec   

                                                question  \
    0                 steve jobs statue location budapst   
    1  Why is the Battle of Stalingrad considered a t...   
    2  In what year did 'The Birth of a Nation' surpa...   
    3  How many Russian soldiers surrendered to AFU i...   
    4   What event led to the creation of Google Images?   

                                         expected_answer       category       area  
    0  The Steve Jobs statue is located in Budapest, ...           Arts  Knowledge  
    1  The Battle of Stalingrad is considered a turni...   General News       News  
    2  This question is based on a false premise. 'Th...  Entertainment       News  
    3  About 300 Russian soldiers surrendered to the ...   General News       News  
    4  Jennifer Lopez's appearance in a green Versace...     Technology       News
    ```

接著在 Langfuse 建立一個 dataset 實體來追蹤執行，再把資料集裡的每一筆加進系統。

```python
from langfuse import get_client
langfuse = get_client()

langfuse_dataset_name = "search-dataset_huggingface_openai-agent"

# Create a dataset in Langfuse
langfuse.create_dataset(
    name=langfuse_dataset_name,
    description="search-dataset uploaded from Huggingface",
    metadata={
        "date": "2025-03-14",
        "type": "benchmark"
    }
)
```

??? note "輸出"

    ```text
    Dataset(id='cm88w66t102qpad07xhgeyaej', name='search-dataset_huggingface_openai-agent', description='search-dataset uploaded from Huggingface', metadata={'date': '2025-03-14', 'type': 'benchmark'}, project_id='cloramnkj0002jz088vzn1ja4', created_at=datetime.datetime(2025, 3, 14, 14, 47, 14, 676000, tzinfo=datetime.timezone.utc), updated_at=datetime.datetime(2025, 3, 14, 14, 47, 14, 676000, tzinfo=datetime.timezone.utc))
    ```

```python
for idx, row in df.iterrows():
    langfuse.create_dataset_item(
        dataset_name=langfuse_dataset_name,
        input={"text": row["question"]},
        expected_output={"text": row["expected_answer"]}
    )
    if idx >= 49: # For this example, we upload only the first 50 items
        break
```

![Dataset items in Langfuse](https://langfuse.com/images/cookbook/integration_openai-agents/example-dataset.png)

#### 在資料集上執行 Agent

我們定義一個 helper 函式 `run_openai_agent()`，它會：
1. 開始一個 Langfuse span
2. 用 prompt 執行我們的 agent
3. 把 trace ID 記錄到 Langfuse

然後我們對資料集每一筆跑一次 agent，並把 trace 連結到該筆資料。需要的話，也可以附加一個快速的評估分數。

```python
from agents import Agent, Runner, WebSearchTool
from langfuse import get_client
 
langfuse = get_client()
dataset_name = "search-dataset_huggingface_openai-agent"
current_run_name = "qna_model_v3_run_05_20" # Identifies this specific evaluation run

agent = Agent(
    name="WebSearchAgent",
    instructions="You are an agent that can search the web.",
    tools=[WebSearchTool(search_context_size= "high")]
)
 
# Assume 'run_openai_agent' is your instrumented application function
def run_openai_agent(question):
    with langfuse.start_as_current_generation(name="qna-llm-call") as generation:
        # Simulate LLM call
        result = Runner.run_sync(agent, question)
 
        # Update the trace with the input and output
        generation.update_trace(
            input= question,
            output=result.final_output,
        )

        return result.final_output
 
dataset = langfuse.get_dataset(name=dataset_name) # Fetch your pre-populated dataset
 
for item in dataset.items:
 
    # Use the item.run() context manager
    with item.run(
        run_name=current_run_name,
        run_metadata={"model_provider": "OpenAI", "temperature_setting": 0.7},
        run_description="Evaluation run for Q&A model v3 on May 20th"
    ) as root_span: # root_span is the root span of the new trace for this item and run.
        # All subsequent langfuse operations within this block are part of this trace.
 
        # Call your application logic
        generated_answer = run_openai_agent(question=item.input["text"])

        print(item.input)
```

你可以用不同的設定重複這個流程：
- 搜尋 tool（例如 OpenAI `WebSearchTool` 的不同 context 大小）
- 模型（gpt-4o-mini、o1 等）
- Tools（有搜尋 vs. 沒搜尋）

然後在 Langfuse 並排比較。這個例子裡，我對 50 個資料集問題跑了 3 次 agent。每次執行用不同的 `WebSearchTool` context 大小設定。可以看到 context 加大後，答案正確率也小幅從 `0.89` 提升到 `0.92`。`correct_answer` 分數是由一個 [LLM-as-a-Judge Evaluator](https://langfuse.com/docs/scores/model-based-evals) 產生的，它依資料集裡的範例答案來判斷問題回答得對不對。

![Dataset run overview](https://langfuse.com/images/cookbook/integration_openai-agents/dataset_runs.png)
![Dataset run comparison](https://langfuse.com/images/cookbook/integration_openai-agents/dataset-run-comparison.png)


## 重點整理
- trace 是由 span 組成的樹，每個 span 對應 agent 的一個步驟（tool call、LLM 呼叫），用它能看出時間和 token 花在哪。
- 線上評估看真實使用：成本、延遲、使用者回饋、LLM-as-a-Judge，加上 `user_id`、`session_id`、tags 方便切分分析。
- 離線評估用有預期答案的資料集，在改動上線前批次跑 agent 並打分。
- 同一份資料集可以用不同模型、tool、設定重跑並並排比較，才知道改動有沒有真的變好。
- LLM-as-a-Judge 的分數來自另一個模型，判斷標準要靠 template 定義清楚。

## 練習
1. 把簡單 Q&A agent 的問題換成別的，到 Langfuse dashboard 找到對應的 trace，確認 span 結構和 token 用量。
2. 在「額外屬性」的範例裡，改 `user_id`、加一個自訂 tag，再到 Langfuse 用它們篩選 trace。
3. 在資料集評估中，把 agent 的模型從 `gpt-4o` 換成 `gpt-4o-mini`（或調整 `WebSearchTool` 的 context 大小），重跑 50 題，比較 `correct_answer` 分數的差異。
