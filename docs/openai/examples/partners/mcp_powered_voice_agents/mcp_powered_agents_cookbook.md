---
translated: true
source: examples/partners/mcp_powered_voice_agents/mcp_powered_agents_cookbook.ipynb
---
# 用 MCP 驅動的語音 Agent 框架

> 原文：[examples/partners/mcp_powered_voice_agents/mcp_powered_agents_cookbook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/mcp_powered_voice_agents/mcp_powered_agents_cookbook.ipynb)

## 這篇在做什麼

用 OpenAI Agents SDK 搭一個語音 agent，背後的 tool 全部透過 MCP 提供：自建的 MCP server 負責 RAG 檢索和 web search，現成的 SQLite MCP server 負責資料庫查詢。流程是語音轉文字、Planner agent 決定呼叫哪些 tool、再把回答轉成語音，範例情境是保險問答。

## 學完你會

- 用 `FastMCP` 寫自己的 MCP server，並用 `MCPServerSse` 和 `MCPServerStdio` 把它和現成的 SQLite server 接到 agent 上。
- 設計 Planner agent 的 instructions，讓它知道什麼時候該用檢索、資料庫或網路搜尋。
- 串起 STT、agent、TTS 的語音流程，並用 Traces 看每一步的延遲。

## 開跑前

- 需要 `OPENAI_API_KEY`。
- 本機要裝 `ffmpeg`，mac 用 `brew install ffmpeg`。
- 需要同目錄的 `search_server.py` 和 `database.db`，RAG 索引會建立在 OpenAI 的 vector store 上。

### Agents
Agent 已經成為協調各種（通常是專門化的）LLM 應用彼此合作的主流框架。許多實際應用需要外部 tool，才能為 LLM 型 agent 建出複雜的工作流程。

Model Context Protocol（MCP）很快成為建構 agent 系統的開放標準。這個協定讓常見的 tool 服務容易整合，也讓 AI 生態系中不同模型之間可以互通。

### 什麼是 MCP？
Model Context Protocol（MCP）是一個開放協定，目的是用安全、模組化、可組合的方式，標準化 AI 模型（尤其是 LLM）和外部 tool、資料來源、context 提供者之間的介面。MCP 提供統一的框架，讓 agent 或應用把結構化的請求送給一組「tool 服務」，例如資料庫、API 或自訂的邏輯模組。採用 MCP 之後，開發者可以：
* 把 agent 邏輯和 tool 實作分開：agent 用標準協定呼叫 tool（像資料庫或搜尋服務），不用依賴寫死的整合。
* 落實一致的安全與治理：MCP 定義了模型和外部資源之間的認證、授權和資料邊界控制。
* 支援模組化、可重用的 agent 架構：tool 可以抽換、更新或擴充，不用改 agent 程式碼，複雜的工作流程容易演進。
* 在本機或遠端執行 tool：不管 tool 跑在客戶的環境還是雲端，都是同一套協定，能滿足隱私和資料所在地的要求。

MCP 就是連接 AI 模型和外部世界的「middleware」，讓真實世界的 context 和能力，能安全、有彈性、好維護地整合進對話式或自主的 agent。

### 企業裡的 Agent
在現在的企業環境，對話式 agent（尤其是語音 agent）正快速成為客服、內部 helpdesk 和任務自動化的標配。但要建出穩健、可擴展的語音 agent 並不容易，原因是工具零散、整合複雜，還需要可靠地協調後端系統。企業裡常見的做法，是開發以知識庫（結構化和非結構化都有）為後盾的 agent。這類機器人分成幾種：
 - 內部使用的 copilot，以及
 - 面向客戶的助理。
後者對準確度、易用性和設計的要求比較高。另外，面向客戶的聊天機器人常見的需求，是加上語音作為使用者介面的一種形式（例如電話自動化）。

這類問答機器人適用很多產業，包括醫療、政府和法律服務，這些產業都需要簡單的知識檢索方式。

保險就是其中一個產業，我們在這個領域的客戶身上看到很大的價值。保單很複雜，保戶不容易看懂這套制度。

### 這份 Cookbook 有什麼？
這份 cookbook 提供一套端到端、模組化的做法，用 MCP 搭配 [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) 建立語音 agent。我們特別示範如何做動態的 context 管理和 agent 式的 tool calling，並以前面提到的保險情境展示這種系統的能力。範例中用 MCP 提供應用可能需要的各種 tool：自訂的 MCP server（文字檢索和 web search），以及預先定義好的 MCP server（SQLite）。

### 端到端流程

這一節說明一個簡單的設定，把 tool 部署成 MCP 框架下的微服務，主要是 RAG、資料庫查詢和 web search。MCP server 除了託管這些服務，也負責做 RAG 索引來支援後端運作。

整個系統的語音輸入輸出採用「串接式」做法。推論時，流程從擷取使用者的語音開始，用語音轉文字系統轉成文字。這段文字送給 Planner agent，由它決定要呼叫哪些 tool，並向對應的微服務發出請求。取得 tool 輸出之後，Planner agent 會整合成一個連貫、符合情境的回答。這個文字回答再用文字轉語音系統轉成音訊，把最後的語音回應交給使用者。

端到端流程如下圖：


![Cookbook_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partner_mcp_Cookbook.svg)

### 安裝相依套件
先安裝專案需要的函式庫。

> 注意：你的機器可能需要另外安裝 `ffmpeg`。如果用 mac，要自己用 `brew install ffmpeg` 安裝。


```python
#install dependencies
%pip install asyncio ffmpeg ffprobe mcp openai openai-agents pydub scipy sounddevice uv --quiet
%pip install "openai-agents[voice]" --quiet
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 24.0 -> 25.1.1
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.

    [notice] A new release of pip is available: 24.0 -> 25.1.1
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

### 設定

要執行這份 cookbook，需要安裝下列套件，它們提供 OpenAI API、Agents SDK、MCP 和音訊處理的函式庫。另外，你可以用 `set_default_openai_key` 函式設定 agent 要用的 OpenAI API key。

```python
import socket
import time
import warnings
from typing import List, Optional, AsyncGenerator

from numpy.typing import NDArray



warnings.filterwarnings("ignore", category=SyntaxWarning)


async def wait_for_server_ready(port: int = 8000, timeout: float = 10) -> None:
    """Wait for SSE server to be ready"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                print("✅ SSE server TCP port is accepting connections.")
                return
        except OSError as e:
            if time.time() - start > timeout - 1:  # Only print on last attempt
                print(f"Waiting for server... ({e})")
            time.sleep(0.5)
    raise RuntimeError("❌ SSE server did not become ready in time.")
```

### 透過自訂 MCP 服務定義會用 tool 的 Agent

首先，用 `FastMCP` 介面定義一個自訂的 MCP 服務，託管 RAG 和 web search 這兩個 tool。具體來說，我們加上 `@mcp.tool` 函式來做：

1.   從 RAG 服務檢索資訊
2.   用 OpenAI 的 `web_search` 搜尋更廣的網路資訊


這份 cookbook 裡，兩個 tool 都跑在同一個服務下。

下面的程式碼已經放在同目錄的 `search_server.py`。執行它來啟動 server。server 執行時，你的檔案會被建索引並存進 vector store。

可以用下面的指令執行 `search_server.py`：

    ```bash
    uv run python search_server.py         
    ```

server 跑起來之後，你可以到 https://platform.openai.com/storage/files 和 https://platform.openai.com/storage/vector_stores 看檔案和 vector store，然後繼續執行 notebook 後面的 cell。

```python
# search_server.py
import os
from mcp.server.fastmcp import FastMCP
from openai import OpenAI
from agents import set_tracing_export_api_key

# Create server
mcp = FastMCP("Search Server")
_vector_store_id = ""

def _run_rag(query: str) -> str:
    """Do a search for answers within the knowledge base and internal documents of the user.
    Args:
        query: The user query
    """
    results = client.vector_stores.search(
        vector_store_id=_vector_store_id,
        query=query,
        rewrite_query=True,  # Query rewriting generally improves results
    )
    return results.data[0].content[0].text


def _summarize_rag_response(rag_output: str) -> str:
    """Summarize the RAG response using GPT-4
    Args:
        rag_output: The RAG response
    """
    response = client.responses.create(
        model="gpt-4.1-mini",
        tools=[{"type": "web_search_preview"}],
        input="Summarize the following text concisely: \n\n" + rag_output,
    )
    return response.output_text


@mcp.tool()
def generate_rag_output(query: str) -> str:
    """Generate a summarized RAG output for a given query.
    Args:
        query: The user query
    """
    print("[debug-server] generate_rag_output: ", query)
    rag_output = _run_rag(query)
    return _summarize_rag_response(rag_output)


@mcp.tool()
def run_web_search(query: str) -> str:
    """Run a web search for the given query.
    Args:
        query: The user query
    """
    print("[debug-server] run_web_search:", query)
    response = client.responses.create(
        model="gpt-4.1-mini",
        tools=[{"type": "web_search_preview"}],
        input=query,
    )
    return response.output_text


def index_documents(directory: str):
    """Index the documents in the given directory to the vector store
    Args:
        directory: The directory to index the documents from
    """
    # OpenAI supported file extensions for retrieval (see docs)
    SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.docx', '.pptx', '.csv', '.rtf', '.html', '.json', '.xml'}
    # Collect all files in the specified directory
    files = [os.path.join(directory, f) for f in os.listdir(directory)]
    # Filter files for supported extensions only
    supported_files = []
    for file_path in files:
        _, ext = os.path.splitext(file_path)
        if ext.lower() in SUPPORTED_EXTENSIONS:
            supported_files.append(file_path)
        else:
            print(f"[warning] Skipping unsupported file for retrieval: {file_path}")

    vector_store = client.vector_stores.create( # Create vector store
        name="Support FAQ",
    )
    global _vector_store_id
    _vector_store_id = vector_store.id

    for file_path in supported_files:
        # Upload each file to the vector store, ensuring the file handle is closed
        with open(file_path, "rb") as fp:
            client.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store.id,
                file=fp
            )
        print(f"[debug-server] uploading file: {file_path}")


if __name__ == "__main__":
    oai_api_key = os.environ.get("OPENAI_API_KEY")
    if not oai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    set_tracing_export_api_key(oai_api_key)
    client = OpenAI(api_key=oai_api_key)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(current_dir, "sample_files")
    index_documents(samples_dir)

    mcp.run(transport="sse")
```

如上所示，我們把 RAG 索引也放進這個流程。實際應用中不需要每次執行都做，如果資料量很大，可以把它放到獨立的程序。

除了單純的 RAG 檢索，我們還多加一個步驟來摘要 RAG 的輸出。這一步不一定需要，不過我們發現它能讓給 planner 的回應更精簡。要不要做，取決於你的系統和延遲要求。


### 使用預先定義的 MCP Server

自己實作 MCP server 其實不難，但 MCP 的威力在於可以用別人建好並維護的現成 server。用現有的實作能加快開發、跟其他 tool 保持一致的介面，資料整合也更順暢。

資料庫查詢的 tool 用的是預先建好的 [SQLite server](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite) 實作。你會看到，只要一行命令列指令，再給它一個放資料的 `*.db` 檔就能用。

### 定義 Planner Agent

接下來定義 MCP server 怎麼產生有意義的回應。Planner agent 是 MCP agent 協調流程裡的關鍵元件，主要工作是把使用者的請求拆成可執行的步驟，並決定每個階段要呼叫哪些 tool、API 或 agent。拿到文字輸入後，planner 會解析請求，並在多輪對話之間維持 context。依照對話狀態，它透過 MCP server 的協調層派送 tool call，呼叫 MCP tool 服務。agent 接著收集中間結果、整合回應，並引導對話走向解決。

設計 planner 時有個關鍵考量是模型的選擇。`4.1` 這種較大的模型推理能力比較強，但語音應用要求端到端延遲很低，所以我們選 `4.1-mini`，它在推理能力和回應速度之間取得不錯的平衡。

```python
from agents import Agent, trace
from agents.mcp import MCPServer, MCPServerSse, MCPServerStdio
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

voice_system_prompt = """[Voice Output Guidelines]
Your responses will be delivered via voice, so please:
1. Use conversational, natural language that sounds good when spoken
2. Keep responses concise - ideally 1-2 sentences per point
3. Avoid technical jargon unless necessary, and explain terms simply
4. Pause naturally between topics using brief sentences
5. Be warm and personable in tone
"""


async def create_insurance_agents(mcp_servers: list[MCPServer]) -> Agent:
    """Create the insurance agent workflow with voice optimization"""
    
    # Main insurance agent with MCP tools
    insurance_agent = Agent(
        name="InsuranceAssistant",
        instructions=voice_system_prompt + prompt_with_handoff_instructions("""
            #Identity
            You an a helpful chatbot that answers questions about our insurance plans. 
            #Task
            Use the tools provided to answer the questions. 
            #Instructions
            * Information about plans and policies are best answered with sqlite or rag_output tools.
            * web_search should be used for answering generic health questions that are not directly related to our insurance plans.
            * Evaluate the quality of the answer after the tool call. 
            * Assess whether you are confident in the answer generated.
            * If your confidence is low, try use another tool.
        """),
        mcp_servers=mcp_servers,
        model="gpt-4.1-mini",
    )
    
    return insurance_agent
```

??? note "輸出"

    ```text
    [non-fatal] Tracing client error 400: {
      "error": {
        "message": "Invalid type for 'data[2].span_data.result': expected an array of strings, but got null instead.",
        "type": "invalid_request_error",
        "param": "data[2].span_data.result",
        "code": "invalid_type"
      }
    }
    ```

在 agent 的定義裡，我們清楚指定每個 tool 該在什麼時候使用。這樣回應比較好控制，答案也更切題。我們也給 Voice Agent 一些準則，設定回覆想要的語氣和精確程度。

### 定義語音設定

接下來定義語音模組的設定，包括語音轉文字（STT）和文字轉語音（TTS）。我們用 OpenAI Agent Voice 函式庫處理語音的輸入和輸出。預設情況下，這個 API 的 STT 用 `gpt-4o-transcribe`，TTS 用 `gpt-4o-mini-tts`。

更多定義語音助理的內容，請看[這份 Cookbook](https://cookbook.openai.com/examples/agents_sdk/app_assistant_voice_agents)。

```python
import numpy as np
import sounddevice as sd


from agents.voice import (
    AudioInput,
    SingleAgentVoiceWorkflow,
    VoicePipeline,
    VoicePipelineConfig,
    TTSModelSettings
)

AudioBuffer = List[NDArray[np.int16]]

AUDIO_CONFIG = {
    "samplerate": 24000,
    "channels": 1,
    "dtype": "int16",
    "blocksize": 2400,
    "silence_threshold": 500,
    "silence_duration": 1.5,
    "min_speech_duration": 0.5,
}

insurance_tts_settings = TTSModelSettings(
    instructions=(
        "Personality: Professional, knowledgeable, and helpful insurance advisor"
        "Tone: Friendly, clear, and reassuring, making customers feel confident about their insurance choices"
        "Pronunciation: Clear and articulate, ensuring insurance terms are easily understood"
        "Tempo: Moderate pace with natural pauses, especially when explaining complex insurance concepts"
        "Emotion: Warm and supportive, conveying trust and expertise in insurance matters"
    )
)

class AudioStreamManager:
    """Context manager for handling audio streams"""
    def __init__(self, input_stream: sd.InputStream, output_stream: sd.OutputStream):
        self.input_stream = input_stream
        self.output_stream = output_stream

    async def __aenter__(self):
        try:
            self.input_stream.start()
            self.output_stream.start()
            return self
        except sd.PortAudioError as e:
            raise RuntimeError(f"Failed to start audio streams: {e}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.input_stream:
                self.input_stream.stop()
                self.input_stream.close()
            if self.output_stream:
                self.output_stream.stop()
                self.output_stream.close()
        except Exception as e:
            print(f"Warning: Error during audio stream cleanup: {e}")
```

在企業情境裡，語音回應的語氣和風格對系統好不好用很關鍵。語音輸出應該一致地展現專業，並符合公司的品牌形象。對大多數應用來說，這代表要產生真實的聲音，反映客服人員那種有禮貌、親切的態度。有了 TTS，我們可以用 prompt engineering 引導模型，產生更符合特定客戶使用情境和品牌價值的音訊。

### 處理語音 I/O

設定好語音之後，下一步是實作處理傳入音訊和產生語音回應的函式。要特別留意設定裡的 `silence_threshold` 參數，它在判斷使用者是否說完話上很關鍵，對語音端點偵測有幫助。

```python
import asyncio

async def continuous_voice_conversation(agent: Agent):
    """Run a continuous voice conversation with automatic speech detection"""
    
    voice_config = VoicePipelineConfig(
        tts_settings=insurance_tts_settings,
    )
    
    pipeline = VoicePipeline(
        workflow=SingleAgentVoiceWorkflow(agent),
        config=voice_config
    )
    
    audio_queue: asyncio.Queue[NDArray[np.int16]] = asyncio.Queue()
    is_agent_speaking = False
    
    def audio_callback(indata: NDArray[np.int16], frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
        """Callback for continuous audio input"""
        if status:
            print(f"Audio input status: {status}")
        if not is_agent_speaking:  # Only record when agent isn't speaking
            audio_queue.put_nowait(indata.copy())
    
    input_stream = sd.InputStream(
        samplerate=AUDIO_CONFIG["samplerate"],
        channels=AUDIO_CONFIG["channels"],
        dtype=AUDIO_CONFIG["dtype"],
        callback=audio_callback,
        blocksize=AUDIO_CONFIG["blocksize"]
    )
    
    output_stream = sd.OutputStream(
        samplerate=AUDIO_CONFIG["samplerate"],
        channels=AUDIO_CONFIG["channels"],
        dtype=AUDIO_CONFIG["dtype"]
    )
    
    print("🎙️ Insurance Voice Assistant Ready!")
    print("Start speaking at any time. Say 'goodbye' to exit.")
    print("-" * 50)
    
    async with AudioStreamManager(input_stream, output_stream):
        silence_threshold = AUDIO_CONFIG["silence_threshold"]
        silence_duration = 0
        max_silence = AUDIO_CONFIG["silence_duration"]
        audio_buffer: AudioBuffer = []
        
        while True:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                
                if np.abs(chunk).mean() > silence_threshold:
                    audio_buffer.append(chunk)
                    silence_duration = 0
                elif audio_buffer:
                    silence_duration += 0.1
                    audio_buffer.append(chunk)
                    
                    if silence_duration >= max_silence:
                        try:
                            full_audio = np.concatenate(audio_buffer, axis=0)
                            
                            if len(full_audio) > AUDIO_CONFIG["samplerate"] * AUDIO_CONFIG["min_speech_duration"]:
                                print("\n🤔 Processing speech...")
                                
                                is_agent_speaking = True
                                
                                audio_input = AudioInput(buffer=full_audio)
                                
                                with trace("Insurance Voice Query"):
                                    result = await pipeline.run(audio_input)
                                    
                                    print("💬 Assistant responding...")
                                    async for event in result.stream():
                                        if event.type == "voice_stream_event_audio":
                                            output_stream.write(event.data)
                                        elif event.type == "voice_stream_event_transcript":
                                            print(f"   > {event.text}", end="", flush=True)
                                    
                                    print("\n")
                                
                        except Exception as e:
                            print(f"\n❌ Error processing speech: {e}")
                        finally:
                            is_agent_speaking = False
                            audio_buffer = []
                            silence_duration = 0
                            
            except asyncio.TimeoutError:
                continue
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Unexpected error: {e}")
                if isinstance(e, (sd.PortAudioError, RuntimeError)):
                    raise
```

### 設定 server 程序

接著加一個方便的函式，用來在本機啟動 server：

```python
import shutil
import subprocess
import nest_asyncio


class ServerProcess:
    """Context manager for handling the SSE server process"""
    def __init__(self, server_file: str):
        self.server_file = server_file
        self.process: Optional[subprocess.Popen] = None

    async def __aenter__(self):
        if not shutil.which("uv"):
            raise RuntimeError(
                "uv is not installed. Please install it: https://docs.astral.sh/uv/getting-started/installation/"
            )

        print("Starting SSE server at http://localhost:8000/sse ...")
        self.process = subprocess.Popen(["uv", "run", self.server_file])
        try:
            await wait_for_server_ready()
            nest_asyncio.apply()
            print("SSE server started. Starting voice assistant...\n")
            return self
        except Exception as e:
            if self.process:
                self.process.terminate()
            raise RuntimeError(f"Failed to start SSE server: {e}")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception as e:
                print(f"Warning: Error during server shutdown: {e}")
```

### 指定 MCP tool 服務

在 `main` 函式裡，我們啟動需要的各個 tool 服務。

自訂的 server（RAG 和 web search）用 `MCPServerSse` 啟動（這裡是跑在本機）。標準的 MCP SQLite 服務則呼叫 `MCPServerStdio`，給一些簡單的參數，這裡是本機的 `database.db` 檔。

```python
import os

async def main():
    """Main function to run the voice assistant"""
    this_dir=os.getcwd()
    #this_dir = os.path.dirname(os.path.abspath(__file__))
    server_file= os.path.join(this_dir, "search_server.py")
    #server_file = os.path.join(this_dir, "search_server.py")

    async with ServerProcess(server_file):
        # Initialize MCP servers
        async with MCPServerSse(
            name="SSE Python Server",
            params={
                "url": "http://localhost:8000/sse",
                "timeout": 15.0,
            },
            client_session_timeout_seconds=15.0,
        ) as search_server:
            async with MCPServerStdio(
                cache_tools_list=True,
                params={"command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "./database.db"]},
            ) as sql_server:
                # Create insurance agent with MCP tools
                agent = await create_insurance_agents([search_server, sql_server])
                
                # Run the voice assistant
                try:
                    await continuous_voice_conversation(agent)
                except Exception as e:
                    print(f"\nError in voice conversation: {e}")
                    raise
```

## 整個流程總結

各個元件都就位之後，我們退一步看整個系統的工作流程：

![Cookbook_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/System_flow_partner_mcp.png)

### 全部串起來
最後，建立自訂的 tool server 實例並啟動服務：

```python
import asyncio

try:
    asyncio.get_running_loop().create_task(main())
except RuntimeError:
    # For Jupyter, use nest_asyncio and run main as a task
    import nest_asyncio
    nest_asyncio.apply()
    task = asyncio.create_task(main())
    try:
        await task
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
    except Exception as e:
        print(f"\nFatal error: {e}")
        raise
```

## 範例輸出

整個系統端到端建好之後，就可以拿來回答問題。這裡我們用它回答幾個常見的保險問題，答案根據保單資訊文件。下面是 agent 針對使用者常問問題給出的一些語音輸出範例：

**這個方案怎麼給付處方藥？**（用檢索）

```python
from IPython.display import display, Audio
import os

# Get the absolute path to the audio file
audio_path = os.path.join(os.getcwd(), "sample_output", "rag.mp3")

# Check if the file exists before trying to play it
if os.path.exists(audio_path):
    display(Audio(audio_path))
else:
    print(f"Audio file not found at: {audio_path}")
```

**哪些保單的月保費低於 $300？**（用資料庫查詢和 SQL）

```python
display(Audio("sample_output/sqlite.mp3"))
```

**有哪些有效的糖尿病治療方式？**（用 Web Search）

```python
display(Audio("sample_output/web_search.mp3"))
```

## 檢視 Traces
預設情況下，應用裡用到的模型和 tool call 會直接加進 [Traces](https://platform.openai.com/traces) 儀表板。這些 trace 能讓你看到使用者使用 agent 時實際的體驗。

![Cookbook_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/trace-sk1_partner.png)

除了 agent 的表現，建語音 agent 還有一個關鍵是回應延遲。Traces 儀表板可以看到每個步驟的 wall time 分解，幫你 debug 並找出延遲可以改善的地方：

![Cookbook_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/Traces-2_partner.png)

也可以點進個別的 trace，看每次 function call 和它的輸出，如下所示。

![image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/traces_partner_granular.png)

Traces 讓你細看 function call 和執行時間，很容易找出延遲的來源（例如上面的 web search tool）。分析每個 tool 呼叫的回應時間變化，能幫你找出正式環境中的瓶頸和可優化的地方。

## 結論

這份 cookbook 帶你建了一套完整的 agent 方案，運用 MCP 平台的彈性和能力。透過整合 Voice Agents SDK，我們示範了如何開發由這些技術驅動、可交付給消費者的產品。也展示了 OpenAI 的 tool 和 Agents API 如何有效結合 MCP，做出有影響力的應用。

希望這份指南既有實作教學，也能帶來啟發，幫你依自己的需求建出 MCP 驅動的語音 agent。

### 貢獻者

這份 cookbook 是 OpenAI 和 [Brain Co](https://www.braincompany.ai/en/) 共同完成的。

- [Cece Z](https://www.linkedin.com/in/cecez/)
- [Sibon Li](https://www.linkedin.com/in/sibon-li-9a9bba34/)
- [Shikhar Kwatra](https://www.linkedin.com/in/shikharkwatra/)

## 重點整理

- MCP 讓 agent 邏輯和 tool 實作分開，tool 可以抽換，也可以跑在本機或遠端。
- 自訂 tool 用 `FastMCP` 加 `@mcp.tool` 寫成 server，現成的 server（如 SQLite）只要一行指令就能掛上。
- Planner agent 負責拆解請求、決定呼叫哪個 tool，instructions 要清楚寫出每個 tool 的使用時機。
- 語音 agent 對延遲敏感，所以 planner 選 `4.1-mini` 這類速度和推理平衡的模型。
- Traces 能看到每個 tool call 的耗時，是找延遲瓶頸的主要工具。

## 練習

1. 改 `silence_threshold` 的值，觀察語音端點偵測的變化。
2. 把 Planner agent 的模型從 `4.1-mini` 換成別的模型，用 Traces 比較整體延遲。
3. 在 `search_server.py` 用 `@mcp.tool` 再加一個 tool（例如查詢目前時間），並在 Planner agent 的 instructions 寫明什麼時候用它。
