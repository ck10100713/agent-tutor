---
translated: true
source: articles/gpt-oss/run-locally-lmstudio.md
---

# 用 LM Studio 在本機執行 gpt-oss

> 原文：[articles/gpt-oss/run-locally-lmstudio.md](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/run-locally-lmstudio.md)



## 這篇在做什麼
教你用 LM Studio 這個桌面應用，在自己的電腦上跑 gpt-oss-20b 或 gpt-oss-120b。包含聊天、接 MCP server，以及透過 LM Studio 的本機 API 和 SDK 呼叫模型。

## 學完你會
- 用 `lms` 指令下載並載入 gpt-oss 模型
- 把 OpenAI SDK 的 base URL 指到本機，直接用 Chat Completions 跟模型對話
- 用 LM Studio SDK 的 `.act()` 讓模型自己呼叫 tool（例如建立檔案）

## 開跑前
- 安裝 LM Studio
- 20b 模型至少要 16GB VRAM，120b 建議 60GB 以上

[LM Studio](https://lmstudio.ai) 是一個效能好又好上手的桌面應用，可以在本機硬體跑大型語言模型 (LLM)。這份教學帶你用 LM Studio 設定並執行 **gpt-oss-20b** 或 **gpt-oss-120b**，包含怎麼聊天、使用 MCP server，或是透過 LM Studio 的本機開發 API 跟模型互動。

這份教學針對一般消費級硬體，例如在 PC 或 Mac 上跑 gpt-oss。如果是用 NVIDIA H100 這類專用 GPU 的伺服器，請看 [vLLM 教學](https://cookbook.openai.com/articles/gpt-oss/run-vllm)。

## 選模型

LM Studio 兩種大小的 gpt-oss 都支援：

- [**`openai/gpt-oss-20b`**](https://lmstudio.ai/models/openai/gpt-oss-20b)
  - 較小的模型
  - 至少需要 **16GB VRAM**
  - 適合高階消費級 GPU 或 Apple Silicon Mac
- [**`openai/gpt-oss-120b`**](https://lmstudio.ai/models/openai/gpt-oss-120b)
  - 完整大小的較大模型
  - 建議 **≥60GB VRAM**
  - 適合多 GPU 或高規格工作站

LM Studio 內建 [llama.cpp](https://github.com/ggml-org/llama.cpp) 推論引擎（跑 GGUF 格式模型），也有給 Apple Silicon Mac 用的 [Apple MLX](https://github.com/ml-explore/mlx) 引擎。

## 快速設定

1. **安裝 LM Studio**
   LM Studio 支援 Windows、macOS 和 Linux。[到這裡下載](https://lmstudio.ai/download)。

2. **下載 gpt-oss 模型** → 

```shell
# For 20B
lms get openai/gpt-oss-20b
# or for 120B
lms get openai/gpt-oss-120b
``` 

3. **在 LM Studio 載入模型** 
  → 打開 LM Studio，用模型載入介面載入剛下載的 gpt-oss 模型。也可以用指令列：

```shell
# For 20B
lms load openai/gpt-oss-20b
# or for 120B
lms load openai/gpt-oss-120b
```

4. **開始使用** → 載入後，你可以直接在 LM Studio 的聊天介面使用，或透過 API 呼叫。

## 跟 gpt-oss 聊天

用 LM Studio 的聊天介面開始對話，或在終端機用 `chat` 指令：

```shell
lms chat openai/gpt-oss-20b
```

關於 prompt 格式：不管是用 llama.cpp 還是 MLX 跑，LM Studio 都是用 OpenAI 的 [Harmony](https://cookbook.openai.com/articles/openai-harmony) 函式庫來組出 gpt-oss 模型的輸入。

## 用本機的 /v1/chat/completions endpoint 呼叫 gpt-oss

LM Studio 提供 **相容 Chat Completions 的 API**，所以你幾乎不用改什麼就能用 OpenAI SDK。下面是 Python 範例：

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="not-needed"  # LM Studio does not require an API key
)

result = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what MXFP4 quantization is."}
    ]
)

print(result.choices[0].message.content)
```

如果你以前用過 OpenAI SDK，這會很眼熟，現有的程式碼只要換 base URL 就能跑。

## 在聊天介面使用 MCP

LM Studio 是一個 [MCP client](https://lmstudio.ai/docs/app/plugins/mcp)，可以連接 MCP server，替 gpt-oss 模型提供外部 tool。

LM Studio 的 mcp.json 檔案位置在：

```shell
~/.lmstudio/mcp.json
```

## 用 Python 或 TypeScript 做本機 tool use

LM Studio 的 SDK 有 [Python](https://github.com/lmstudio-ai/lmstudio-python) 和 [TypeScript](https://github.com/lmstudio-ai/lmstudio-js) 兩個版本。你可以用 SDK 讓 gpt-oss 做 tool calling 和本機函式執行。

做法是呼叫 `.act()`，把 tool 交給 gpt-oss，它會在呼叫 tool 和 reasoning 之間來回，直到完成你的任務。

下面的範例給模型一個 tool，可以在本機檔案系統建立檔案。你可以拿它當起點，再加更多 tool。tool 定義的說明文件在這裡：[Python](https://lmstudio.ai/docs/python/agent/tools) 和 [TypeScript](https://lmstudio.ai/docs/typescript/agent/tools)。

```shell
uv pip install lmstudio
```

```python
import readline # Enables input line editing
from pathlib import Path

import lmstudio as lms

# Define a function that can be called by the model and provide them as tools to the model.
# Tools are just regular Python functions. They can be anything at all.
def create_file(name: str, content: str):
    """Create a file with the given name and content."""
    dest_path = Path(name)
    if dest_path.exists():
        return "Error: File already exists."
    try:
        dest_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        return "Error: {exc!r}"
    return "File created."

def print_fragment(fragment, round_index=0):
    # .act() supplies the round index as the second parameter
    # Setting a default value means the callback is also
    # compatible with .complete() and .respond().
    print(fragment.content, end="", flush=True)

model = lms.llm("openai/gpt-oss-20b")
chat = lms.Chat("You are a helpful assistant running on the user's computer.")

while True:
    try:
        user_input = input("User (leave blank to exit): ")
    except EOFError:
        print()
        break
    if not user_input:
        break
    chat.add_user_message(user_input)
    print("Assistant: ", end="", flush=True)
    model.act(
        chat,
        [create_file],
        on_message=chat.append,
        on_prediction_fragment=print_fragment,
    )
    print()
```

想在本機用 TypeScript 的開發者，這裡有用 `lmstudio-js` 寫的類似範例：

```shell
npm install @lmstudio/sdk
```

```typescript
import { Chat, LMStudioClient, tool } from "@lmstudio/sdk";
import { existsSync } from "fs";
import { writeFile } from "fs/promises";
import { createInterface } from "readline/promises";
import { z } from "zod";

const rl = createInterface({ input: process.stdin, output: process.stdout });
const client = new LMStudioClient();
const model = await client.llm.model("openai/gpt-oss-20b");
const chat = Chat.empty();

const createFileTool = tool({
  name: "createFile",
  description: "Create a file with the given name and content.",
  parameters: { name: z.string(), content: z.string() },
  implementation: async ({ name, content }) => {
    if (existsSync(name)) {
      return "Error: File already exists.";
    }
    await writeFile(name, content, "utf-8");
    return "File created.";
  },
});

while (true) {
  const input = await rl.question("User: ");
  // Append the user input to the chat
  chat.append("user", input);

  process.stdout.write("Assistant: ");
  await model.act(chat, [createFileTool], {
    // When the model finish the entire message, push it to the chat
    onMessage: (message) => chat.append(message),
    onPredictionFragment: ({ content }) => {
      process.stdout.write(content);
    },
  });
  process.stdout.write("\n");
}
```

## 重點整理
- LM Studio 把本機模型包成 Chat Completions 相容的 API，換 base URL 就能沿用現有程式。
- 20b 適合一般高階消費級硬體，120b 需要大量 VRAM。
- LM Studio 用 Harmony 格式組 gpt-oss 的輸入，你不用自己處理。
- `.act()` 讓模型在 tool 呼叫和 reasoning 之間自動循環，直到任務完成。
- LM Studio 本身是 MCP client，用 mcp.json 就能接外部 tool。

## 練習
1. 改 Python 範例的 prompt 內容，確認本機 endpoint 真的回應你的新問題。
2. 在 `.act()` 範例裡，把建立檔案的 tool 改成只允許寫進某個固定資料夾。
3. 再加一個 tool（例如讀取檔案內容），然後請模型「先建立檔案、再讀出來確認」，觀察它怎麼串接兩個 tool。
