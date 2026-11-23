---
translated: true
source: examples/agents_sdk/app_assistant_voice_agents.ipynb
---

# 用 Agents SDK 打造語音助理

> 原文：[examples/agents_sdk/app_assistant_voice_agents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/app_assistant_voice_agents.ipynb)



## 這篇在做什麼

用 Agents SDK 做一個 app 內的語音助理：一個 Triage Agent 判斷使用者意圖，再 handoff 給搜尋、知識庫、帳號三個專門的 agent。先用文字跑通流程，再用 Voice pipeline 轉成語音，最後調整 prompt 和 TTS 指令讓聲音更自然。

## 學完你會

- 用 `WebSearchTool`、`FileSearchTool` 和 `function_tool` 組出三個 agent，並用 triage agent 做 handoff。
- 用 `VoicePipeline` 和 `SingleAgentVoiceWorkflow` 把同一套文字 workflow 變成語音版。
- 用 `gpt-4o-mini-tts` 的 `instructions` 控制語氣、個性和語速，並用 tracing 除錯。

## 開跑前

- 需要 `OPENAI_API_KEY`。
- Knowledge Agent 需要一個 OpenAI 管理的 vector store（網頁上建或用 API 建都行）。
- 語音部分用 `sounddevice` 收發音訊，需要本機有麥克風和喇叭。


假設你是一家消費性科技公司的 AI 負責人，想做一個單一入口的數位語音助理，不管使用者是要操作帳號、查產品資訊，還是要即時指引，它都能幫忙。

但要實現這個願景很難：你得先用文字把每個使用情境都做出來並測試好，接上各種需要的工具和系統，再想辦法把它們編排成連貫的體驗。好不容易品質夠了（光是評估就很吃力），還得把整個 workflow 重構成語音互動。

好在 OpenAI 最近有三個發布，讓你可以用很少的設定，透過語音來建構和編排模組化的 agent workflow：

- [**Responses API**](https://platform.openai.com/docs/api-reference/responses)：agent 導向的 API，用託管的有狀態對話跟前沿模型互動，能追蹤 response 方便做 eval，還內建 file search、web search、computer use 等 tool
- [**Agents SDK**](https://openai.github.io/openai-agents-python/quickstart/)：輕量、可自訂的開源框架，用來建構和編排多個 agent 的 workflow，讓助理能把輸入導到合適的 agent，也容易擴充支援更多使用情境
- [**Voice agents**](https://openai.github.io/openai-agents-python/voice/quickstart/)：Agents SDK 的延伸，加入 voice pipeline，幾行程式碼就能讓 agent 從文字變成能聽也能說

這份 cookbook 用上面這些工具，為一個虛構的消費性 app 做簡單的 app 內語音助理。我們會建立一個 **Triage Agent**，負責打招呼、判斷使用者意圖，並把請求導到三個專門 agent 之一：

- **Search Agent**：用 Responses API 內建的 web search 提供使用者問題的即時資訊
- **Knowledge Agent**：用 Responses API 的 file search，從 OpenAI 託管的向量資料庫取得資訊
- **Account Agent**：用 function calling 透過 API 觸發自訂動作

最後，我們用 Agents SDK 的 Voice 功能把 workflow 變成即時語音助理：收麥克風輸入、做 speech-to-text、經過各個 agent 路由，再用 text-to-speech 回覆。

# 環境設定

要執行這份 cookbook，需要安裝能使用 OpenAI API、Agents SDK 和音訊處理的套件。另外可以用 `set_default_openai_key` 函式設定 agent 要用的 OpenAI API key。

```python
%pip install openai
%pip install openai-agents 'openai-agents[voice]'
%pip install numpy
%pip install sounddevice
%pip install os
```

```python
from agents import Agent, function_tool, WebSearchTool, FileSearchTool, set_default_openai_key
from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

set_default_openai_key("YOUR_API_KEY")
```

# 定義 agent 和 tool

我們要為虛構的消費性 app「ACME shop」做助理，一開始支援三個主要情境：

- 用 web search 回答即時問題，輔助購買決策
- 提供產品組合裡有哪些選項的資訊
- 提供帳號資訊，讓使用者了解自己的預算和花費

為此我們用 agent 架構，把每個情境的功能拆到獨立的 agent，降低單一 agent 要處理的任務複雜度和範圍，準確度也會比較高。目前的架構很簡單，只針對上面三個情境，但 Agents SDK 的好處是之後想加新功能，很容易就能在 workflow 裡加 agent：

![Agent Architecture](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/app_assistant_voice_agents_arch.png)



## Search Agent

第一個 agent 是簡單的 web search agent，用 Responses API 提供的 `WebSearchTool` 找使用者問題的即時資訊。每個範例的 instruction prompt 都先保持簡單，後面會再迭代，示範怎麼針對你的情境優化回應格式。

```python
# --- Agent: Search Agent ---
search_agent = Agent(
    name="SearchAgent",
    instructions=(
        "You immediately provide an input to the WebSearchTool to find up-to-date information on the user's query."
    ),
    tools=[WebSearchTool()],
)
```

*更多 web search 和 Responses API 的資訊，可以看 [Web Search and States with Responses API](https://cookbook.openai.com/examples/responses_api/responses_example) 這份 cookbook*

## Knowledge Agent

第二個 agent 要能回答產品組合的問題。我們用 `FileSearchTool`，從 OpenAI 管理的 vector store 取得公司專屬的產品資訊。有兩種做法：

1. 用 OpenAI Platform 網站：到 [platform.openai.com/storage](https://platform.openai.com/storage) 建立 vector store 並上傳你的文件，再把 vector store ID 填進下面 `FileSearchTool` 的初始化。

2. 用 OpenAI API：用 OpenAI Python client 的 `vector_stores.create` 建立 vector store，再用 `vector_stores.files.create` 加入檔案。完成後同樣用 `FileSearchTool` 搜尋這個 vector store。下面的程式碼示範做法，可以用範例檔，也可以換成你自己的本機檔案路徑：

```python
from openai import OpenAI
import os

client = OpenAI(api_key='YOUR_API_KEY')

def upload_file(file_path: str, vector_store_id: str):
    file_name = os.path.basename(file_path)
    try:
        file_response = client.files.create(file=open(file_path, 'rb'), purpose="assistants")
        attach_response = client.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=file_response.id
        )
        return {"file": file_name, "status": "success"}
    except Exception as e:
        print(f"Error with {file_name}: {str(e)}")
        return {"file": file_name, "status": "failed", "error": str(e)}

def create_vector_store(store_name: str) -> dict:
    try:
        vector_store = client.vector_stores.create(name=store_name)
        details = {
            "id": vector_store.id,
            "name": vector_store.name,
            "created_at": vector_store.created_at,
            "file_count": vector_store.file_counts.completed
        }
        print("Vector store created:", details)
        return details
    except Exception as e:
        print(f"Error creating vector store: {e}")
        return {}
    
vector_store_id = create_vector_store("ACME Shop Product Knowledge Base")
upload_file("voice_agents_knowledge/acme_product_catalogue.pdf", vector_store_id["id"])
```

vector store 建好後，就可以讓 knowledge agent 用 `FileSearchTool` 搜尋指定的 store ID。

```python
# --- Agent: Knowledge Agent ---
knowledge_agent = Agent(
    name="KnowledgeAgent",
    instructions=(
        "You answer user questions on our product portfolio with concise, helpful responses using the FileSearchTool."
    ),
    tools=[FileSearchTool(
            max_num_results=3,
            vector_store_ids=["VECTOR_STORE_ID"],
        ),],
)
```

*想更了解 file search 搭配 Responses API 的威力，上面的範例程式碼取自這篇很棒的 cookbook：[Doing RAG on PDFs using File Search in the Responses API](https://cookbook.openai.com/examples/file_search_responses)*

## Account Agent

前面用的都是 Agents SDK 內建的 tool，你也可以用 `function_tool` decorator 定義自己的 tool，接上自己的系統。這裡我們為 account agent 寫一個簡單的假函式，依 user ID 回傳帳號資訊。

```python
# --- Tool 1: Fetch account information (dummy) ---
@function_tool
def get_account_info(user_id: str) -> dict:
    """Return dummy account info for a given user."""
    return {
        "user_id": user_id,
        "name": "Bugs Bunny",
        "account_balance": "£72.50",
        "membership_status": "Gold Executive"
    }

# --- Agent: Account Agent ---
account_agent = Agent(
    name="AccountAgent",
    instructions=(
        "You provide account information based on a user ID using the get_account_info tool."
    ),
    tools=[get_account_info],
)
```

*更多 Agents SDK 的 function calling 資訊，請看 [Agents SDK 文件](https://openai.github.io/openai-agents-python/tools/#function-tools)*

最後是 triage agent，它會依使用者意圖把問題導到合適的 agent。這裡用 `prompt_with_handoff_instructions` 函式，它提供如何處理 handoff 的額外指引，建議給任何有一組固定 handoff 的 agent 使用。

```python
# --- Agent: Triage Agent ---
triage_agent = Agent(
    name="Assistant",
    instructions=prompt_with_handoff_instructions("""
You are the virtual assistant for Acme Shop. Welcome the user and ask how you can help.
Based on the user's intent, route to:
- AccountAgent for account-related queries
- KnowledgeAgent for product FAQs
- SearchAgent for anything requiring real-time web search
"""),
    handoffs=[account_agent, knowledge_agent, search_agent],
)
```

# 執行 workflow

agent 定義好之後，就可以拿幾個範例問題跑跑看效果。

```python
# %%
from agents import Runner, trace

async def test_queries():
    examples = [
        "What's my ACME account balance doc? My user ID is 1234567890", # Account Agent test
        "Ooh i've got money to spend! How big is the input and how fast is the output of the dynamite dispenser?", # Knowledge Agent test
        "Hmmm, what about duck hunting gear - what's trending right now?", # Search Agent test

    ]
    with trace("ACME App Assistant"):
        for query in examples:
            result = await Runner.run(triage_agent, query)
            print(f"User: {query}")
            print(result.final_output)
            print("---")
# Run the tests
await test_queries()
```

??? note "輸出"

    ```text
    User: What's my ACME account balance doc? My user ID is 1234567890
    Your ACME account balance is £72.50. You have a Gold Executive membership.
    ---
    User: Ooh i've got money to spend! How big is the input and how fast is the output of the dynamite dispenser?
    The Automated Dynamite Dispenser can hold up to 10 sticks of dynamite and dispenses them at a speed of 1 stick every 2 seconds.
    ---
    User: Hmmm, what about duck hunting gear - what's trending right now?
    Staying updated with the latest trends in duck hunting gear can significantly enhance your hunting experience. Here are some of the top trending items for the 2025 season:



    **Banded Aspire Catalyst Waders**  
    These all-season waders feature waterproof-breathable technology, ensuring comfort in various conditions. They boast a minimal-stitch design for enhanced mobility and include PrimaLoft Aerogel insulation for thermal protection. Additional features like an over-the-boot protective pant and an integrated LED light in the chest pocket make them a standout choice. ([blog.gritroutdoors.com](https://blog.gritroutdoors.com/must-have-duck-hunting-gear-for-a-winning-season/?utm_source=openai))




    **Sitka Delta Zip Waders**  
    Known for their durability, these waders have reinforced shins and knees with rugged foam pads, ideal for challenging terrains. Made with GORE-TEX material, they ensure dryness throughout the season. ([blog.gritroutdoors.com](https://blog.gritroutdoors.com/must-have-duck-hunting-gear-for-a-winning-season/?utm_source=openai))




    **MOmarsh InvisiMan Blind**  
    This one-person, low-profile blind is praised for its sturdiness and ease of setup. Hunters have reported that even late-season, cautious ducks approach without hesitation, making it a valuable addition to your gear. ([bornhunting.com](https://bornhunting.com/top-duck-hunting-gear/?utm_source=openai))




    **Slayer Calls Ranger Duck Call**  
    This double reed call produces crisp and loud sounds, effectively attracting distant ducks in harsh weather conditions. Its performance has been noted for turning the heads of ducks even at extreme distances. ([bornhunting.com](https://bornhunting.com/top-duck-hunting-gear/?utm_source=openai))




    **Sitka Full Choke Pack**  
    A favorite among hunters, this backpack-style blind bag offers comfort and efficiency. It has proven to keep gear dry during heavy downpours and is durable enough to withstand over 60 hunts in a season. ([bornhunting.com](https://bornhunting.com/top-duck-hunting-gear/?utm_source=openai))


    Incorporating these trending items into your gear can enhance your comfort, efficiency, and success during the hunting season. 
    ... (省略 1 行)
    ```

# Tracing

上面的輸出看起來符合預期，不過 Agents SDK 有個重要好處是內建 tracing，可以追蹤一次 agent 執行中的事件流程，包括 LLM 呼叫、handoff 和 tool。

用 [Traces dashboard](https://platform.openai.com/traces)，我們能在開發和正式環境中除錯、視覺化和監控 workflow。如下圖所示，每個測試問題都被正確導到對應的 agent。

![Traces Dashboard](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/app_assistant_voice_agents.png)

# 啟用語音

workflow 設計好之後，實務上我們會花時間檢視 trace 並迭代，讓 workflow 盡量有效。不過這裡假設我們已經滿意了，可以開始想怎麼把 app 內的助理從文字互動變成語音互動。

做法很簡單，用 [Agents SDK](https://openai.github.io/openai-agents-python/voice/quickstart/) 提供的 class 就能把文字 workflow 轉成語音版。`VoicePipeline` class 提供介面，負責把音訊輸入轉成文字、執行指定的 agent workflow，再產生 text-to-speech 回應播給使用者；`SingleAgentVoiceWorkflow` class 則讓我們沿用先前文字版的同一套 agent workflow。音訊的輸入輸出用 `sounddevice` 套件。

整個流程變成這樣：

![Agent Architecture 2](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/app_assistant_voice_agents_arch_2.png)


實作的程式碼如下：

```python
# %%
import numpy as np
import sounddevice as sd
from agents.voice import AudioInput, SingleAgentVoiceWorkflow, VoicePipeline

async def voice_assistant():
    samplerate = sd.query_devices(kind='input')['default_samplerate']

    while True:
        pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(triage_agent))

        # Check for input to either provide voice or exit
        cmd = input("Press Enter to speak your query (or type 'esc' to exit): ")
        if cmd.lower() == "esc":
            print("Exiting...")
            break      
        print("Listening...")
        recorded_chunks = []

         # Start streaming from microphone until Enter is pressed
        with sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', callback=lambda indata, frames, time, status: recorded_chunks.append(indata.copy())):
            input()

        # Concatenate chunks into single buffer
        recording = np.concatenate(recorded_chunks, axis=0)

        # Input the buffer and await the result
        audio_input = AudioInput(buffer=recording)

        with trace("ACME App Voice Assistant"):
            result = await pipeline.run(audio_input)

         # Transfer the streamed result into chunks of audio
        response_chunks = []
        async for event in result.stream():
            if event.type == "voice_stream_event_audio":
                response_chunks.append(event.data)

        response_audio = np.concatenate(response_chunks, axis=0)

        # Play response
        print("Assistant is responding...")
        sd.play(response_audio, samplerate=samplerate)
        sd.wait()
        print("---")

# Run the voice assistant
await voice_assistant()
```

??? note "輸出"

    ```text
    Listening...
    Assistant is responding...
    ---
    Exiting...
    ```

執行上面的程式碼會得到下面的回應，功能和文字版 workflow 一致。

```python
from IPython.display import display, Audio
display(Audio("voice_agents_audio/account_balance_response_base.mp3"))
display(Audio("voice_agents_audio/product_info_response_base.mp3"))
display(Audio("voice_agents_audio/trending_items_response_base.mp3"))
```

??? note "輸出"

    ```text
    <IPython.lib.display.Audio object>
    ```

*提示：voice agent 搭配 tracing 時，可以在 traces dashboard 直接播放音訊*

![Audio trace](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/app_assistant_voice_agents_trace.png)


# 優化語音

這是個好的開始，但還能更好。我們只是把文字 agent 直接轉成語音 agent，輸出的語氣和格式都沒有針對語音調整，所以聽起來很機械、不自然。

要改善的話，需要調整幾個 prompt。

首先，可以讓現有的 agent 都加入一段共用的 system prompt，指示它們怎麼優化文字回應，以便之後轉成語音




```python
# Common system prompt for voice output best practices:
voice_system_prompt = """
[Output Structure]
Your output will be delivered in an audio voice response, please ensure that every response meets these guidelines:
1. Use a friendly, human tone that will sound natural when spoken aloud.
2. Keep responses short and segmented—ideally one to two concise sentences per step.
3. Avoid technical jargon; use plain language so that instructions are easy to understand.
4. Provide only essential details so as not to overwhelm the listener.
"""

# --- Agent: Search Agent ---
search_voice_agent = Agent(
    name="SearchVoiceAgent",
    instructions=voice_system_prompt + (
        "You immediately provide an input to the WebSearchTool to find up-to-date information on the user's query."
    ),
    tools=[WebSearchTool()],
)

# --- Agent: Knowledge Agent ---
knowledge_voice_agent = Agent(
    name="KnowledgeVoiceAgent",
    instructions=voice_system_prompt + (
        "You answer user questions on our product portfolio with concise, helpful responses using the FileSearchTool."
    ),
    tools=[FileSearchTool(
            max_num_results=3,
            vector_store_ids=["VECTOR_STORE_ID"],
        ),],
)

# --- Agent: Account Agent ---
account_voice_agent = Agent(
    name="AccountVoiceAgent",
    instructions=voice_system_prompt + (
        "You provide account information based on a user ID using the get_account_info tool."
    ),
    tools=[get_account_info],
)

# --- Agent: Triage Agent ---
triage_voice_agent = Agent(
    name="VoiceAssistant",
    instructions=prompt_with_handoff_instructions("""
You are the virtual assistant for Acme Shop. Welcome the user and ask how you can help.
Based on the user's intent, route to:
- AccountAgent for account-related queries
- KnowledgeAgent for product FAQs
- SearchAgent for anything requiring real-time web search
"""),
    handoffs=[account_voice_agent, knowledge_voice_agent, search_voice_agent],
)
```

接著，我們可以用 `instructions` 欄位，指示 Agents SDK 預設的 OpenAI TTS 模型 `gpt-4o-mini-tts` 該怎麼說出 agent 產生的文字。

這裡能控制的範圍很大，包括指定輸出的個性、發音、速度和情緒。

下面列了幾個例子，示範針對不同應用怎麼寫 prompt。

```python
health_assistant= "Voice Affect: Calm, composed, and reassuring; project quiet authority and confidence."
"Tone: Sincere, empathetic, and gently authoritative—express genuine apology while conveying competence."
"Pacing: Steady and moderate; unhurried enough to communicate care, yet efficient enough to demonstrate professionalism."

coach_assistant="Voice: High-energy, upbeat, and encouraging, projecting enthusiasm and motivation."
"Punctuation: Short, punchy sentences with strategic pauses to maintain excitement and clarity."
"Delivery: Fast-paced and dynamic, with rising intonation to build momentum and keep engagement high."

themed_character_assistant="Affect: Deep, commanding, and slightly dramatic, with an archaic and reverent quality that reflects the grandeur of Olde English storytelling."
"Tone: Noble, heroic, and formal, capturing the essence of medieval knights and epic quests, while reflecting the antiquated charm of Olde English."    
"Emotion: Excitement, anticipation, and a sense of mystery, combined with the seriousness of fate and duty."
"Pronunciation: Clear, deliberate, and with a slightly formal cadence."
"Pause: Pauses after important Olde English phrases such as \"Lo!\" or \"Hark!\" and between clauses like \"Choose thy path\" to add weight to the decision-making process and allow the listener to reflect on the seriousness of the quest."
```

我們的設定會著重在友善、溫暖、支持的語氣，聽起來自然，也能引導使用者完成對話。

```python
from agents.voice import TTSModelSettings, VoicePipeline, VoicePipelineConfig, SingleAgentVoiceWorkflow, AudioInput
import sounddevice as sd
import numpy as np

# Define custom TTS model settings with the desired instructions
custom_tts_settings = TTSModelSettings(
    instructions="Personality: upbeat, friendly, persuasive guide"
    "Tone: Friendly, clear, and reassuring, creating a calm atmosphere and making the listener feel confident and comfortable."
    "Pronunciation: Clear, articulate, and steady, ensuring each instruction is easily understood while maintaining a natural, conversational flow."
    "Tempo: Speak relatively fast, include brief pauses and after before questions"
    "Emotion: Warm and supportive, conveying empathy and care, ensuring the listener feels guided and safe throughout the journey."
)

async def voice_assistant_optimized():
    samplerate = sd.query_devices(kind='input')['default_samplerate']
    voice_pipeline_config = VoicePipelineConfig(tts_settings=custom_tts_settings)

    while True:
        pipeline = VoicePipeline(workflow=SingleAgentVoiceWorkflow(triage_voice_agent), config=voice_pipeline_config)

        # Check for input to either provide voice or exit
        cmd = input("Press Enter to speak your query (or type 'esc' to exit): ")
        if cmd.lower() == "esc":
            print("Exiting...")
            break       
        print("Listening...")
        recorded_chunks = []

         # Start streaming from microphone until Enter is pressed
        with sd.InputStream(samplerate=samplerate, channels=1, dtype='int16', callback=lambda indata, frames, time, status: recorded_chunks.append(indata.copy())):
            input()

        # Concatenate chunks into single buffer
        recording = np.concatenate(recorded_chunks, axis=0)

        # Input the buffer and await the result
        audio_input = AudioInput(buffer=recording)

        with trace("ACME App Optimized Voice Assistant"):
            result = await pipeline.run(audio_input)

         # Transfer the streamed result into chunks of audio
        response_chunks = []
        async for event in result.stream():
            if event.type == "voice_stream_event_audio":
                response_chunks.append(event.data)
        response_audio = np.concatenate(response_chunks, axis=0)

        # Play response
        print("Assistant is responding...")
        sd.play(response_audio, samplerate=samplerate)
        sd.wait()
        print("---")

# Run the voice assistant
await voice_assistant_optimized()
```

??? note "輸出"

    ```text
    Listening...
    Assistant is responding...
    ---
    Listening...
    Assistant is responding...
    ---
    Listening...
    Assistant is responding...
    ---
    Listening...
    Assistant is responding...
    ```

執行上面的程式碼會得到下面的回應，用字自然很多，語音表現也更有吸引力。

```python
display(Audio("voice_agents_audio/account_balance_response_opti.mp3"))
display(Audio("voice_agents_audio/product_info_response_opti.mp3"))
display(Audio("voice_agents_audio/trending_items_response_opti.mp3"))
```

??? note "輸出"

    ```text
    <IPython.lib.display.Audio object>
    ```

...如果想要更誇張的效果，可以換成 `themed_character_assistant` 的 instructions，會得到下面的回應：

```python
display(Audio("voice_agents_audio/product_info_character.wav"))
display(Audio("voice_agents_audio/product_info_character_2.wav"))
```

# 結論

大功告成！

這份 cookbook 示範了怎麼：

- 定義 agent，為 app 內語音助理提供特定情境的功能
- 搭配 Responses API 的內建和自訂 tool，給 agent 各種功能，並用 tracing 評估表現
- 用 Agents SDK 編排這些 agent
- 用 Agents SDK 的 Voice 功能把 agent 從文字互動轉成語音互動

Agents SDK 讓你能用模組化的方式打造語音助理：一個情境一個情境地做，各自評估和迭代，做完再做下一個，準備好了再把 workflow 從文字轉成語音。

希望這份 cookbook 對你開始打造自己的 app 內語音助理有幫助！

## 重點整理

- 把不同情境拆成專門的 agent，再用 triage agent 做 handoff，每個 agent 的任務比較單純，準確度也比較高。
- 內建 tool（web search、file search）和自訂的 `function_tool` 可以混著用，接自己的系統。
- 先用文字把 workflow 調好、用 tracing 檢查路由，再轉語音，因為 `VoicePipeline` 可以直接沿用同一套 workflow。
- 直接轉語音聽起來會很機械，要另外調整文字回應的 prompt，並用 TTS 的 `instructions` 控制語氣。

## 練習

1. 改 Account Agent 那個假函式，多回傳一個欄位（例如會員等級），再問助理相關問題，看 triage 有沒有正確 handoff。
2. 把 TTS 的 `instructions` 改成你自己的風格（例如冷靜的客服口吻、加快語速），比較聽起來的差別。
3. 新增第四個 agent（例如處理退貨政策），加進 triage agent 的 handoff 清單，並到 Traces dashboard 確認測試問題有被導到它。
