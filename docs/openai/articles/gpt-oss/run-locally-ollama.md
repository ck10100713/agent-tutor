---
translated: true
source: articles/gpt-oss/run-locally-ollama.md
---

# 用 Ollama 在本機執行 gpt-oss

> 原文：[articles/gpt-oss/run-locally-ollama.md](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/run-locally-ollama.md)



## 這篇在做什麼
教你用 Ollama 在自己的電腦跑 gpt-oss-20b 或 gpt-oss-120b，可以離線聊天、用 API 呼叫，也能接到 Agents SDK。

## 學完你會
- 用 Ollama 拉下 gpt-oss 模型並在終端機聊天
- 把 OpenAI SDK 指到 Ollama 的 Chat Completions 相容 API，並做 function calling
- 透過 LiteLLM 讓 Agents SDK 使用本機的 gpt-oss

## 開跑前
- 安裝 Ollama
- 20b 建議至少 16GB VRAM 或 unified memory，120b 建議 60GB 以上

想在自己的硬體上跑 [**OpenAI gpt-oss**](https://openai.com/open-models) 嗎？這份教學帶你用 [Ollama](https://ollama.ai) 在本機設定 **gpt-oss-20b** 或 **gpt-oss-120b**，可以離線聊天、透過 API 使用，甚至接到 Agents SDK。

這份教學針對一般消費級硬體，例如在 PC 或 Mac 上跑模型。如果是用 NVIDIA H100 這類專用 GPU 的伺服器，請看 [vLLM 教學](https://cookbook.openai.com/articles/gpt-oss/run-vllm)。

## 選模型

Ollama 兩種大小的 gpt-oss 都支援：

- **`gpt-oss-20b`**
  - 較小的模型
  - 最好有 **≥16GB VRAM** 或 **unified memory**
  - 適合高階消費級 GPU 或 Apple Silicon Mac
- **`gpt-oss-120b`**
  - 完整大小的較大模型
  - 最好有 **≥60GB VRAM** 或 **unified memory**
  - 適合多 GPU 或高規格工作站

**幾點說明：**

- 這些模型出廠就是 **MXFP4 量化**，目前沒有其他量化版本
- VRAM 不夠時 _可以_ offload 到 CPU，但會跑得比較慢

## 快速設定

1. **安裝 Ollama** → [到這裡下載](https://ollama.com/download)
2. **拉你要的模型：**

```shell
# For 20B
ollama pull gpt-oss:20b

# For 120B
ollama pull gpt-oss:120b
```

## 跟 gpt-oss 聊天

準備好跟模型對話了嗎？可以在 app 或終端機開始聊天：

```shell
ollama run gpt-oss:20b
```

Ollama 預設套用一個 **chat template**，模仿 [OpenAI harmony format](https://cookbook.openai.com/articles/openai-harmony)。輸入訊息就能開始對話。

## 使用 API

Ollama 提供 **相容 Chat Completions 的 API**，所以你幾乎不用改什麼就能用 OpenAI SDK。下面是 Python 範例：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",  # Local Ollama API
    api_key="ollama"                       # Dummy key
)

response = client.chat.completions.create(
    model="gpt-oss:20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what MXFP4 quantization is."}
    ]
)

print(response.choices[0].message.content)
```

如果你以前用過 OpenAI SDK，這會很眼熟。

你也可以直接用 Ollama 的 SDK，有 [Python](https://github.com/ollama/ollama-python) 和 [JavaScript](https://github.com/ollama/ollama-js) 版本。

## 使用 tool（function calling）

Ollama 可以：

- 呼叫函式
- 使用 **內建的 browser tool**（在 app 裡）

透過 Chat Completions 呼叫函式的範例：

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather in a given city",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            },
        },
    }
]

response = client.chat.completions.create(
    model="gpt-oss:20b",
    messages=[{"role": "user", "content": "What's the weather in Berlin right now?"}],
    tools=tools
)

print(response.choices[0].message)
```

因為模型的 tool calling 是在 chain-of-thought (CoT) 過程中發生的，所以你必須把 API 回傳的 reasoning 一起帶回後續的 tool call 請求，在那裡提供 tool 的結果，一直到模型給出最終答案為止。

## Responses API 的替代做法

Ollama 目前還沒有原生支援 **Responses API**。

如果你一定要用 Responses API，可以用 [**Hugging Face 的 `Responses.js` proxy**](https://github.com/huggingface/responses.js)，把 Chat Completions 轉成 Responses API。

基本使用情境下，你也可以[**用 Ollama 當後端，跑我們的範例 Python server。**](https://github.com/openai/gpt-oss?tab=readme-ov-file#responses-api)這個 server 只是基本的範例，並沒有

```shell
pip install gpt-oss
python -m gpt_oss.responses_api.serve \
    --inference_backend=ollama \
    --checkpoint gpt-oss:20b
```

## 整合 Agents SDK

想把 gpt-oss 用在 OpenAI 的 **Agents SDK** 嗎？

兩個版本的 Agents SDK 都可以覆寫 OpenAI base client，指到 Ollama（用 Chat Completions），或指到你的 Responses.js proxy 來用本機模型。你也可以用內建功能，讓 Agents SDK 指向第三方模型。

- **Python：** 用 [LiteLLM](https://openai.github.io/openai-agents-python/models/litellm/)，透過 LiteLLM proxy 到 Ollama
- **TypeScript：** 用 [AI SDK](https://openai.github.io/openai-agents-js/extensions/ai-sdk/) 搭配 [ollama adapter](https://ai-sdk.dev/providers/community-providers/ollama)

下面是用 LiteLLM 的 Python Agents SDK 範例：

```python
import asyncio
from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel

set_tracing_disabled(True)

@function_tool
def get_weather(city: str):
    print(f"[debug] getting weather for {city}")
    return f"The weather in {city} is sunny."


async def main(model: str, api_key: str):
    agent = Agent(
        name="Assistant",
        instructions="You only respond in haikus.",
        model=LitellmModel(model="ollama/gpt-oss:120b", api_key=api_key),
        tools=[get_weather],
    )

    result = await Runner.run(agent, "What's the weather in Tokyo?")
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(main())
```

## 重點整理
- Ollama 提供 Chat Completions 相容 API，換 base URL 就能沿用 OpenAI SDK 程式。
- gpt-oss 是 MXFP4 量化發布，VRAM 不夠可 offload 到 CPU，但會變慢。
- 模型在 CoT 中做 tool calling，多輪呼叫時要把 reasoning 一併帶回去。
- Ollama 沒有原生 Responses API，要靠 proxy 或範例 server 轉接。
- Agents SDK 可透過 LiteLLM（Python）或 AI SDK（TypeScript）接本機模型。

## 練習
1. 把 Python 範例裡的模型從 20b 換成你機器跑得動的版本，確認回應正常。
2. 修改 function calling 範例，加入一個新的函式（例如查詢時間），看模型是否會選對函式。
3. 在 Agents SDK 範例裡替 agent 加一個自訂 tool，並改 instructions，觀察本機模型如何呼叫它。
