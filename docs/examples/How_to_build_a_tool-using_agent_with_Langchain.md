---
translated: true
source: examples/How_to_build_a_tool-using_agent_with_Langchain.ipynb
---

# 用 LangChain 打造會使用 tool 的 agent

> 原文：[examples/How_to_build_a_tool-using_agent_with_Langchain.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_build_a_tool-using_agent_with_Langchain.ipynb)



## 這篇在做什麼
用 LangChain 讓 OpenAI 模型可以使用外部 tool。範例先做一個用搜尋 tool 的 agent，再加上對話記憶，最後用 Pinecone 建一個 podcast 逐字稿的知識庫，讓 agent 也能查它。

## 學完你會
- 用 prompt template、output parser、LLM chain 組出一個 ReAct 風格的 LangChain agent
- 用 `ConversationBufferWindowMemory` 讓 agent 記得最近幾輪對話
- 把 Pinecone 向量資料庫包成 RetrievalQA tool，讓 agent 一起使用多個 tool

## 開跑前
- OpenAI API key
- Pinecone 帳號和 API key（可以註冊免費帳號，放在 `PINECONE_API_KEY` 環境變數）
- SerpAPI 的 API key，放在 `SERPAPI_API_KEY` 環境變數

這個 notebook 帶你用 LangChain，讓 OpenAI 模型可以使用外部 tool。具體來說，你會做出用自訂 tool 回答使用者問題的 LLM agent。


## 什麼是 LangChain？
[LangChain](https://python.langchain.com/en/latest/index.html) 是開發語言模型應用程式的框架。它讓你可以組出分層的 LLM 應用，能理解 context，並以 agent 的身份跟環境動態互動，既簡化你的程式碼，也讓客戶有更動態的使用體驗。

## 為什麼 LLM 需要用 tool？
LLM 最常見的挑戰之一，是訓練資料不夠新、不夠具體：答案可能過時，而且知識庫太龐雜，很容易 hallucination。Tool 讓 LLM 在受控的 context 裡回答，這個 context 來自你現有的知識庫和內部 API。與其費盡心思用 prompt engineering 把 LLM 推到你要的答案，不如讓它能存取 tool，動態取得資訊、解析之後再交給客戶。 

讓 LLM 能用 tool，就能讓它帶著來自搜尋引擎、API 或你自己資料庫的 context 來回答問題。有 tool 的 LLM 不會直接回答，而是先做中間步驟去蒐集相關資訊。Tool 也可以組合使用。[例如](https://python.langchain.com/en/latest/modules/agents/agents/examples/mrkl_chat.html)，可以讓語言模型用搜尋 tool 查數據，再用計算機 tool 做計算。

## Notebook 章節

- **Setup：** 匯入套件，連接 Pinecone 向量資料庫。
- **LLM Agent：** 用修改過的 [ReAct](https://react-lm.github.io/) 框架做 chain-of-thought 推理，建立 agent。
- **LLM Agent with History：** 讓 LLM 能存取對話中先前的步驟。
- **Knowledge Base：** 建立「Stuff You Should Know」podcast 單集的知識庫，用 tool 的方式存取。
- **LLM Agent with Tools：** 讓 agent 能用多個 tool，並測試它會不會用 tool 回答問題。

```python
%load_ext autoreload
%autoreload 2
```

??? note "輸出"

    ```text
    The autoreload extension is already loaded. To reload it, use:
      %reload_ext autoreload
    ```

# Setup

匯入套件，並建立到 [Pinecone](https://www.pinecone.io) 向量資料庫的連線。

Pinecone 可以換成任何其他向量資料庫。LangChain 原生支援[不少種類](https://python.langchain.com/en/latest/modules/indexes/vectorstores.html)，其他的連接器就要自己開發。

```python
!pip install openai
!pip install pinecone-client
!pip install pandas
!pip install typing
!pip install tqdm
!pip install langchain
!pip install wget
```

```python
import datetime
import json
import openai
import os
import pandas as pd
import pinecone
import re
from tqdm.auto import tqdm
from typing import List, Union
import zipfile

# Langchain imports
from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent, AgentOutputParser
from langchain.prompts import BaseChatPromptTemplate, ChatPromptTemplate
from langchain import SerpAPIWrapper, LLMChain
from langchain.schema import AgentAction, AgentFinish, HumanMessage, SystemMessage
# LLM wrapper
from langchain.chat_models import ChatOpenAI
from langchain import OpenAI
# Conversational memory
from langchain.memory import ConversationBufferWindowMemory
# Embeddings and vectorstore
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import Pinecone

# Vectorstore Index
index_name = 'podcasts'
```

要取得連接 Pinecone 的 API key，可以註冊[免費帳號](https://app.pinecone.io/)，把 key 放在下面的 `api_key` 變數，或是放在環境變數 `PINECONE_API_KEY`

```python
api_key = os.getenv("PINECONE_API_KEY") or "PINECONE_API_KEY"

# find environment next to your API key in the Pinecone console
env = os.getenv("PINECONE_ENVIRONMENT") or "PINECONE_ENVIRONMENT"

pinecone.init(api_key=api_key, environment=env)
pinecone.whoami()
```

```python
pinecone.list_indexes()
```

??? note "輸出"

    ```text
    ['podcasts']
    ```

如果你想清空 index，或是 index 還不存在，就執行這個程式區塊

```
# Check whether the index with the same name already exists - if so, delete it
if index_name in pinecone.list_indexes():
    pinecone.delete_index(index_name)
    
# Creates new index
pinecone.create_index(name=index_name, dimension=1536)
index = pinecone.Index(index_name=index_name)

# Confirm our index was created
pinecone.list_indexes()
```

## LLM Agent

LangChain 的 [LLM agent](https://python.langchain.com/docs/modules/agents/) 有很多可設定的元件，細節在 LangChain 文件裡。

我們會用幾個核心概念，做出一個說話方式符合我們要求、能用 tool 回答問題，並用適當語言模型驅動對話的 agent。
- **Prompt Template：** 輸入的模板，控制 LLM 的行為，以及它怎麼接收輸入、產生輸出，是驅動你應用程式的大腦（[docs](https://python.langchain.com/en/latest/modules/prompts/prompt_templates.html)）。
- **Output Parser：** 解析 prompt 輸出的方法。如果 LLM 用特定標頭產生輸出，就能做出複雜的互動：變數由 LLM 在回應中產生，再傳進 chain 的下一步（[docs](https://python.langchain.com/en/latest/modules/prompts/output_parsers.html)）。
- **LLM Chain：** Chain 把 prompt template 和執行它的 LLM 結合在一起。這裡我們用 ```gpt-3.5-turbo```，但這個框架也能搭配 OpenAI completions 模型，或完全不同的 LLM（[docs](https://python.langchain.com/en/latest/modules/chains.html)）。
- **Tool：** 外部服務，LLM 在使用者需要時可以用它取得資訊或執行指令（[docs](https://python.langchain.com/en/latest/modules/agents/tools.html)）。
- **Agent：** 把這一切黏在一起的角色。Agent 可以呼叫多個 LLM Chain，每個都有自己的 tool。你也可以用自己的邏輯擴充 agent，加入重試、錯誤處理，以及其他讓應用更可靠的方法（[docs](https://python.langchain.com/en/latest/modules/agents.html)）。

**注意：** 要用 Search tool 跑這份 cookbook 之前，需要先到 https://serpapi.com/ 註冊並產生 API key。拿到之後，存在名為 ```SERPAPI_API_KEY``` 的環境變數裡

```python
# Initiate a Search tool - note you'll need to have set SERPAPI_API_KEY as an environment variable as per the above instructions
search = SerpAPIWrapper()

# Define a list of tools
tools = [
    Tool(
        name = "Search",
        func=search.run,
        description="useful for when you need to answer questions about current events"
    )
]
```

```python
# Set up the prompt with input variables for tools, user input and a scratchpad for the model to record its workings
template = """Answer the following questions as best you can, but speaking as a pirate might speak. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin! Remember to speak as a pirate when giving your final answer. Use lots of "Arg"s

Question: {input}
{agent_scratchpad}"""
```

```python
# Set up a prompt template
class CustomPromptTemplate(BaseChatPromptTemplate):
    # The template to use
    template: str
    # The list of tools available
    tools: List[Tool]
    
    def format_messages(self, **kwargs) -> str:
        # Get the intermediate steps (AgentAction, Observation tuples)
        
        # Format them in a particular way
        intermediate_steps = kwargs.pop("intermediate_steps")
        thoughts = ""
        for action, observation in intermediate_steps:
            thoughts += action.log
            thoughts += f"\nObservation: {observation}\nThought: "
            
        # Set the agent_scratchpad variable to that value
        kwargs["agent_scratchpad"] = thoughts
        
        # Create a tools variable from the list of tools provided
        kwargs["tools"] = "\n".join([f"{tool.name}: {tool.description}" for tool in self.tools])
        
        # Create a list of tool names for the tools provided
        kwargs["tool_names"] = ", ".join([tool.name for tool in self.tools])
        formatted = self.template.format(**kwargs)
        return [HumanMessage(content=formatted)]
    
prompt = CustomPromptTemplate(
    template=template,
    tools=tools,
    # This omits the `agent_scratchpad`, `tools`, and `tool_names` variables because those are generated dynamically
    # This includes the `intermediate_steps` variable because that is needed
    input_variables=["input", "intermediate_steps"]
)
```

```python
class CustomOutputParser(AgentOutputParser):
    
    def parse(self, llm_output: str) -> Union[AgentAction, AgentFinish]:
        
        # Check if agent should finish
        if "Final Answer:" in llm_output:
            return AgentFinish(
                # Return values is generally always a dictionary with a single `output` key
                # It is not recommended to try anything else at the moment :)
                return_values={"output": llm_output.split("Final Answer:")[-1].strip()},
                log=llm_output,
            )
        
        # Parse out the action and action input
        regex = r"Action: (.*?)[\n]*Action Input:[\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        
        # If it can't parse the output it raises an error
        # You can add your own logic here to handle errors in a different way i.e. pass to a human, give a canned response
        if not match:
            raise ValueError(f"Could not parse LLM output: `{llm_output}`")
        action = match.group(1).strip()
        action_input = match.group(2)
        
        # Return the action and action input
        return AgentAction(tool=action, tool_input=action_input.strip(" ").strip('"'), log=llm_output)
    
output_parser = CustomOutputParser()
```

```python
# Initiate our LLM - default is 'gpt-3.5-turbo'
llm = ChatOpenAI(temperature=0)

# LLM chain consisting of the LLM and a prompt
llm_chain = LLMChain(llm=llm, prompt=prompt)

# Using tools, the LLM chain and output_parser to make an agent
tool_names = [tool.name for tool in tools]

agent = LLMSingleActionAgent(
    llm_chain=llm_chain, 
    output_parser=output_parser,
    # We use "Observation" as our stop sequence so it will stop when it receives Tool output
    # If you change your prompt template you'll need to adjust this as well
    stop=["\nObservation:"], 
    allowed_tools=tool_names
)
```

```python
# Initiate the agent that will respond to our queries
# Set verbose=True to share the CoT reasoning the LLM goes through
agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True)
```

```python
agent_executor.run("How many people live in canada as of 2023?")
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    Thought: Hmm, I be not sure of the answer to that one. Let me think.
    Action: Search
    Action Input: "Canada population 2023"

    Observation:39,566,248Ahoy, that be a lot of people! But I need to make sure this be true.
    Action: Search
    Action Input: "Canada population 2023 official source"

    Observation:The current population of Canada is 38,664,637 as of Wednesday, April 19, 2023, based on Worldometer elaboration of the latest United Nations data.Arrr, that be the official number! I be confident in me answer now.
    Final Answer: The population of Canada as of 2023 is 38,664,637. Arg!

    > Finished chain.
    ```

    ```text
    'The population of Canada as of 2023 is 38,664,637. Arg!'
    ```

```python
agent_executor.run("How many in 2022?")
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    Thought: Hmm, I'm not sure what this question is asking about. I better use the search tool.
    Action: Search
    Action Input: "2022 events"

    Observation:8. Humanitarian Crises Deepen · 7. Latin America Moves Left. · 6. Iranians Protest. · 5. COVID Eases. · 4. Inflation Returns. · 3. Climate Change ...Ahoy, it looks like this be a question about what be happenin' in 2022. Let me search again.
    Action: Search
    Action Input: "2022 calendar"

    Observation:United States 2022 – Calendar with American holidays. Yearly calendar showing months for the year 2022. Calendars – online and print friendly – for any year ...Shiver me timbers, it looks like this be a question about the year 2022. Let me search one more time.
    Action: Search
    Action Input: "What be happenin' in 2022?"

    Observation:8. Humanitarian Crises Deepen · 7. Latin America Moves Left. · 6. Iranians Protest. · 5. COVID Eases. · 4. Inflation Returns. · 3. Climate Change ...Avast ye, it looks like the same results be comin' up. I reckon there be no clear answer to this question.
    Final Answer: Arg, I be sorry matey, but I can't give ye a clear answer to that question.

    > Finished chain.
    ```

    ```text
    "Arg, I be sorry matey, but I can't give ye a clear answer to that question."
    ```

## LLM Agent with History

讓 LLM Agent 具備保留[記憶](https://python.langchain.com/en/latest/modules/agents/agents/custom_llm_agent.html#adding-memory)的能力，並在繼續對話時把記憶當作 context。

這個範例用簡單的 ```ConversationBufferWindowMemory```，它保留最近兩輪對話的滾動視窗。LangChain 還有其他[記憶選項](https://python.langchain.com/en/latest/modules/memory.html)，各有取捨，適合不同的使用情境。

```python
# Set up a prompt template which can interpolate the history
template_with_history = """You are SearchGPT, a professional search engine who provides informative answers to users. Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin! Remember to give detailed, informative answers

Previous conversation history:
{history}

New question: {input}
{agent_scratchpad}"""
```

```python
prompt_with_history = CustomPromptTemplate(
    template=template_with_history,
    tools=tools,
    # The history template includes "history" as an input variable so we can interpolate it into the prompt
    input_variables=["input", "intermediate_steps", "history"]
)

llm_chain = LLMChain(llm=llm, prompt=prompt_with_history)
tool_names = [tool.name for tool in tools]
agent = LLMSingleActionAgent(
    llm_chain=llm_chain, 
    output_parser=output_parser,
    stop=["\nObservation:"], 
    allowed_tools=tool_names
)
```

```python
# Initiate the memory with k=2 to keep the last two turns
# Provide the memory to the agent
memory = ConversationBufferWindowMemory(k=2)
agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True, memory=memory)
```

```python
agent_executor.run("How many people live in canada as of 2023?")
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    Thought: I need to find the most recent population data for Canada.
    Action: Search
    Action Input: "Canada population 2023"

    Observation:39,566,248This data seems reliable, but I should double-check the source.
    Action: Search
    Action Input: "Source of Canada population 2023"

    Observation:The current population of Canada is 38,664,637 as of Wednesday, April 19, 2023, based on Worldometer elaboration of the latest United Nations data. Canada 2020 population is estimated at 37,742,154 people at mid year according to UN data. Canada population is equivalent to 0.48% of the total world population.I now know the final answer
    Final Answer: As of April 19, 2023, the population of Canada is 38,664,637.

    > Finished chain.
    ```

    ```text
    'As of April 19, 2023, the population of Canada is 38,664,637.'
    ```

```python
agent_executor.run("how about in mexico?")
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    Thought: I need to search for the current population of Mexico.
    Action: Search
    Action Input: "current population of Mexico"

    Observation:Mexico, officially the United Mexican States, is a country in the southern portion of North America. It is bordered to the north by the United States; to the south and west by the Pacific Ocean; to the southeast by Guatemala, Belize, and the Caribbean Sea; and to the east by the Gulf of Mexico.That's not the answer to the question, I need to refine my search.
    Action: Search
    Action Input: "population of Mexico 2023"

    Observation:132,709,512I now know the final answer.
    Final Answer: As of 2023, the population of Mexico is 132,709,512.

    > Finished chain.
    ```

    ```text
    'As of 2023, the population of Mexico is 132,709,512.'
    ```

## Knowledge base

建立一個自訂的 vectorstore，讓 Agent 把它當 tool 來回答問題。我們把結果存在 [Pinecone](https://docs.pinecone.io/docs/quickstart)，LangChain 有支援（[Docs](https://python.langchain.com/en/latest/modules/indexes/vectorstores/examples/pinecone.html)、[API reference](https://python.langchain.com/en/latest/reference/modules/vectorstore.html)）。想了解怎麼開始用 Pinecone 或其他向量資料庫，我們有一份 [cookbook](https://github.com/openai/openai-cookbook/blob/colin/examples/vector_databases/Using_vector_databases_for_embeddings_search.ipynb) 可以參考。

可以到 LangChain 文件看還有哪些 [vectorstores](https://python.langchain.com/en/latest/modules/indexes/vectorstores.html) 和[資料庫](https://python.langchain.com/en/latest/modules/chains/examples/sqlite.html)可用。

這個範例用 Stuff You Should Know podcast 的逐字稿，資料由 OSF DOI [10.17605/OSF.IO/VM9NT](https://doi.org/10.17605/OSF.IO/VM9NT) 提供

```python
import wget

# Here is a URL to a zip archive containing the transcribed podcasts
# Note that this data has already been split into chunks and embeddings from OpenAI's `text-embedding-3-small` embedding model are included
content_url = 'https://cdn.openai.com/API/examples/data/sysk_podcast_transcripts_embedded.json.zip'

# Download the file (it is ~541 MB so this will take some time)
wget.download(content_url)
```

??? note "輸出"

    ```text
    100% [......................................................................] 571275039 / 571275039
    ```

    ```text
    'sysk_podcast_transcripts_embedded.json.zip'
    ```

```python
# Load podcasts
with zipfile.ZipFile("sysk_podcast_transcripts_embedded.json.zip","r") as zip_ref:
    zip_ref.extractall("./data")
f = open('./data/sysk_podcast_transcripts_embedded.json')
processed_podcasts = json.load(f)
```

```python
# Have a look at the contents
pd.DataFrame(processed_podcasts).head()
```

??? note "輸出"

    ```text
                                                      id  \
    0  sysk_with_transcripts_SYSK Selects How Crime S...   
    1  sysk_with_transcripts_SYSK Selects How Crime S...   
    2  sysk_with_transcripts_SYSK Selects How Crime S...   
    3  sysk_with_transcripts_SYSK Selects How Crime S...   
    4  sysk_with_transcripts_SYSK Selects How Crime S...   

                                                filename  \
    0  sysk_with_transcripts_SYSK Selects How Crime S...   
    1  sysk_with_transcripts_SYSK Selects How Crime S...   
    2  sysk_with_transcripts_SYSK Selects How Crime S...   
    3  sysk_with_transcripts_SYSK Selects How Crime S...   
    4  sysk_with_transcripts_SYSK Selects How Crime S...   

                                                title  \
    0  \n\nSYSK Selects How Crime Scene Cleanup Works   
    1  \n\nSYSK Selects How Crime Scene Cleanup Works   
    2  \n\nSYSK Selects How Crime Scene Cleanup Works   
    3  \n\nSYSK Selects How Crime Scene Cleanup Works   
    4  \n\nSYSK Selects How Crime Scene Cleanup Works   

                                                     url  \
    0  https://chtbl.com/track/5899E/podtrac.com/pts/...   
    1  https://chtbl.com/track/5899E/podtrac.com/pts/...   
    2  https://chtbl.com/track/5899E/podtrac.com/pts/...   
    3  https://chtbl.com/track/5899E/podtrac.com/pts/...   
    4  https://chtbl.com/track/5899E/podtrac.com/pts/...   

                                              text_chunk  \
    0  Title: sysk_with_transcripts_SYSK Selects How ...   
    1  Title: sysk_with_transcripts_SYSK Selects How ...   
    2  Title: sysk_with_transcripts_SYSK Selects How ...   
    3  Title: sysk_with_transcripts_SYSK Selects How ...   
    4  Title: sysk_with_transcripts_SYSK Selects How ...   

                                               embedding  \
    0  [0.021279960870742798, -0.005817972123622894, ...   
    1  [0.013859338127076626, 0.00857278611510992, 0....   
    2  [0.015242221765220165, 0.016030369326472282, 0...   
    3  [0.004371842369437218, -0.003036574460566044, ...   
    ... (省略 8 行)
    ```

```python
# Add the text embeddings to Pinecone

batch_size = 100  # how many embeddings we create and insert at once

for i in tqdm(range(0, len(processed_podcasts), batch_size)):
    # find end of batch
    i_end = min(len(processed_podcasts), i+batch_size)
    meta_batch = processed_podcasts[i:i_end]
    # get ids
    ids_batch = [x['cleaned_id'] for x in meta_batch]
    # get texts to encode
    texts = [x['text_chunk'] for x in meta_batch]
    # add embeddings
    embeds = [x['embedding'] for x in meta_batch]
    # cleanup metadata
    meta_batch = [{
        'filename': x['filename'],
        'title': x['title'],
        'text_chunk': x['text_chunk'],
        'url': x['url']
    } for x in meta_batch]
    to_upsert = list(zip(ids_batch, embeds, meta_batch))
    # upsert to Pinecone
    index.upsert(vectors=to_upsert)
```

```python
# Configuring the embeddings to be used by our retriever to be OpenAI Embeddings, matching our embedded corpus
embeddings = OpenAIEmbeddings()


# Loads a docsearch object from an existing Pinecone index so we can retrieve from it
docsearch = Pinecone.from_existing_index(index_name,embeddings,text_key='text_chunk')
```

```python
retriever = docsearch.as_retriever()
```

```python
query_docs = retriever.get_relevant_documents("can you live without a bank account")
```

```python
# Print out the title and content for the most relevant retrieved documents
print("\n".join(['Title: ' + x.metadata['title'].strip() + '\n\n' + x.page_content + '\n\n' for x in query_docs]))
```

??? note "輸出"

    ```text
    Title: sysk: Can You Live Without a Bank Account?

    Title: sysk_with_transcripts_Can you live without a bank account.json;  And if you had a life, you didn't necessarily rectify your bank checkbook every day. Oh, wait, what is balancing a checkbook mean? Seriously? Yeah. Thank God for my wife. So another reason you might avoid a bank is philosophically. There may be a longstanding distrust of banks in your family that you don't want to put your money in, or you may just want to be like, you know what? I don't want to take part in this modern society. I want to kind of drop out a bit. And a really good first move is to shut your bank account down. That's a big statement. Oh, yeah, it is. But a lot of people that are underbanked and don't have accounts aren't there on purpose. It's not some philosophical statement. A lot of times it's simply because they are poor and they don't have a lot of alternatives. Yeah. And the other thing about not having a bank account, not only do you not have a bank account, you also are, like, basically just avoiding banks altogether. There's plenty of other things that banks offer, like loans and mortgage, lollipops, stuff like that. Yeah. Maybe some free nasty coffee. So when you don't have a banking account, that's like the most basic unit of the banking world. Right. If you don't have that, you obviously aren't going to be exposed to all these other things that can help. Things like build your credit history through like a revolving loan or a mortgage or a car loan or something like that that you can build up your credit for and ultimately save money. So when you don't have a bank account, for whatever reason, you are effectively out of the banking system. The problem is you can live parallel to the banking system outside of it, but it can be really dangerous, especially if you're just dealing with cash, because that cash has to stay somewhere, whether it's on you or in your mattress or in a coffee can in your backyard. You're exposed for having that readily available to anybody who finds it or comes into your house with a gun to get it. Yes.


    Title: sysk: Can You Live Without a Bank Account?

    Title: sysk_with_transcripts_Can you live without a bank account.json;  And it doesn't have to be an everyday thing. You can host when you want. Like, let's say you're taking a week's vacation. Why not host your home? Because that money could go toward paying for your current vacation or towards your retirement fund or even towards your kids college fund. Yeah. For anything. And listen, if you're worried about your stuff, don't be. Air cover for hosts. Let hosts welcome guests into their home without having to worry. You get $1 million in damage protection anytime you're hosting. Plus pet damage protection and income loss protection, too. And are you ready for this? Air cover for host is completely free every time you host on airbnb. Free with a capital F, with air cover for Host. It makes hosting a no brainer, and the benefits really start adding up. So learn more and host with peace of mind at Airbnb comaircoverforhosts. Capital One offers commercial solutions you can bank on. Now more than ever, your business faces specific challenges and unique opportunities. That's why Capital One offers a comprehensive suite of financial services custom tailored to your short and long term goals, backed by the expertise, strategy and resources of a top ten commercial bank, a dedicated team works with you to support your success and help you achieve your goals. Explore the possibilities at CapitalOne. comCOMMERCIAL all right, so if you live in modern society today, it is pretty tough to get by without a bank. Most cases these days you have well, I don't know about most cases, but in many cases you have automatic deposits of your work checks. Sure. A lot of people pay their bills wirelessly, online, directly from their bank. You might have a student loan, you might have a car loan, you might have your house mortgage, you might pay your credit card bills. All this stuff is running through a bank, most likely. And you would think it's probably impossible to not have a bank account these days. And I would say pretty much all Americans have them. Not true. Well, pretty much all Americans do. Like 93% do. Yeah, but that's not all. No, it's true.


    Title: sysk: Can You Live Without a Bank Account?

    Title: sysk_with_transcripts_Can you live without a bank account.json;  Yeah. 7% of Americans do not have bank accounts. About 9 million people last year in 2015 did not have bank accounts. 9 million people is a lot of people. No, it really is. And apparently that's household sorry, not people. Yeah, right. You're that is a big distinction, too. And the FDIC said, man, that's the lowest since we've been tracking this by far. And someone said, well, how long have you been tracking this? They said, well, the last six years. Really? Yeah, which I'm like. Really? That's when they started tracking it, but apparently so 2009. So if you want another number, the 9 million American households don't have bank accounts at all, then there are 25 million households in addition to that. So that makes almost like 34 million households, which that's a substantial number at this point. Sure. The 25 million are what's called underbanked, meaning they may have a bank account, but they don't use the bank account. Yeah. They don't use it because they are probably afraid of overdraft fees. Or they have maybe a bank account that got grandfathered in so that they don't have to pay minimum amount fees. And who knows? There's all sorts of reasons for people to not use a bank account that they have, but probably cheap among them is overdressed, which you'll talk more about. Yeah. And the majority of these underbank people in the United States are poor, usually. A lot of times they're minorities, a lot of times they're less educated. And these communities, there's a few reasons why they may not want to use a bank one. Maybe they don't trust banks. And if you look in the history of the United States or certainly even we're just talking about the Wells Fargo scandal, when you see stuff like that on the news, it should be upsetting to everyone. But obviously if you're poor and you don't have a lot of money, that may scare you into not wanting to use a bank at all. Right? Yeah.


    Title: sysk: Can You Live Without a Bank Account?

    Title: sysk_with_transcripts_Can you live without a bank account.json;  Maybe at the time, I might be making it up. I seem to remember them saying that, and I was like, I don't want that. Just let the check bounce and I'll take it up with them. Yes. The way it was marketed, though, was like, hey, we value you. We want to make sure that you can pay all your bills. So if something happens and you're overdrafted we'll cover it. We're just going to charge you a fee. And it sounds good, but again, when you go from high to low and all of a sudden your overdraft fees go from one to four or five or however many, that's a huge problem. Well, and the people that are overdrafting and the people that are at least able to afford those fees. Exactly. So it's a disproportionate burden on the poor, which makes it, as a scam, one of the more evil scams around. Yes. It's just wrong, then the idea that if you open an account, you should not opt in for overdraft protection. And it's easy to say when you're talking about checks for, like you're writing a check for a Mountain Dew and some cheetos. Yeah, who cares if you're short for that? You can go without that. But when you're talking about your rent check or like an actual grocery bill or something like that, it sucks that you can't get that stuff. But it's better to have to put a couple of things back than to pay $35 for one $2 item that you went over by, right? Yeah, that's a good point. And this was in my case, too. This is also back in the day when you I mean, a lot of times it was a mystery how much you had in your account. Right. Like, you couldn't just get on your phone before you write the check and be like, oh, well, no, I don't have enough money to cover this. Yeah, because even if you balanced your checkbook, sometimes you forgot to carry the one, it wasn't always 100% accurate.
    ```

## LLM Agent with Tools

建立一個用我們 Pinecone 知識庫的 [RetrievalQA](https://python.langchain.com/en/latest/modules/chains/index_examples/vector_db_qa.html) chain，來擴充 tool 清單。

```python
from langchain.chains import RetrievalQA

retrieval_llm = OpenAI(temperature=0)

podcast_retriever = RetrievalQA.from_chain_type(llm=retrieval_llm, chain_type="stuff", retriever=docsearch.as_retriever())
```

```python
expanded_tools = [
    Tool(
        name = "Search",
        func=search.run,
        description="useful for when you need to answer questions about current events"
    ),
    Tool(
        name = 'Knowledge Base',
        func=podcast_retriever.run,
        description="Useful for general questions about how to do things and for details on interesting topics. Input should be a fully formed question."
    )
]
```

```python
# Re-initialize the agent with our new list of tools
prompt_with_history = CustomPromptTemplate(
    template=template_with_history,
    tools=expanded_tools,
    input_variables=["input", "intermediate_steps", "history"]
)
llm_chain = LLMChain(llm=llm, prompt=prompt_with_history)
multi_tool_names = [tool.name for tool in expanded_tools]
multi_tool_agent = LLMSingleActionAgent(
    llm_chain=llm_chain, 
    output_parser=output_parser,
    stop=["\nObservation:"], 
    allowed_tools=multi_tool_names
)
```

```python
multi_tool_memory = ConversationBufferWindowMemory(k=2)
multi_tool_executor = AgentExecutor.from_agent_and_tools(agent=multi_tool_agent, tools=expanded_tools, verbose=True, memory=multi_tool_memory)
```

```python
multi_tool_executor.run("Hi, I'd like to know how you can live without a bank account")
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    Thought: This is an interesting question. I'm not sure if I have the answer in my knowledge base, so I might need to search for it.
    Action: Search
    Action Input: "How to live without a bank account"

    Observation:Underbanked households have a checking or savings account but also use alternative financial services such as money orders, check cashing, international remittances, payday loans, refund anticipation loans, rent-to-own services, pawnshop loans, or auto title loans, according to the FDIC.It seems like there are alternative financial services available for those who don't have a bank account. I should look into this further to provide a more comprehensive answer.
    Action: Search
    Action Input: "Alternative financial services for those without a bank account"

    Observation:Instead, people who are unbanked use alternative financial services—payday loans, money orders, check cashing services, pawnshop loans, and the like—to meet their banking needs. These financial services fill an important role for unbanked individuals, but they can also cause further financial hardship.It's important to note that while there are alternatives to having a bank account, relying solely on these services can lead to financial difficulties. I should provide some information on the potential drawbacks of not having a bank account.
    Action: Knowledge Base
    Action Input: "What are the drawbacks of not having a bank account?"

    Observation: Not having a bank account can be dangerous, as the cash has to be stored somewhere and can be exposed to anyone who finds it or comes into the house with a gun to get it. Additionally, not having a bank account means not being exposed to other things that can help, such as building credit history through loans or mortgages, which can ultimately save money. Finally, not having a bank account can be a disproportionate burden on the poor, as overdraft fees can be expensive.It's important to provide some resources for those who may be interested in learning more about alternative financial services or how to open a bank account. 
    Action: Knowledge Base
    Action Input: "Resources for alternative financial services or opening a bank account"

    Observation: There are a few resources available for alternative financial services or opening a bank account. Prepaid credit cards are becoming more popular and can be found at convenience stores. Capital One offers commercial solutions and a comprehensive suite of financial services tailored to short and long term goals. Airbnb also offers Air Cover for Hosts, which provides $1 million in damage protection, pet damage protection, and income loss protection.It's important to note that while prepaid credit cards and alternative financial services can be helpful, they may not offer the same level of protection and benefits as a traditional bank account. It's also important to do research and compare options before making a decision. 
    Final Answer: While it is possible to live without a bank account by using alternative financial services, it may come with potential drawbacks and limitations. It's important to do research and compare options before making a decision, and there are resources available for those who may be interested in opening a bank account or exploring alternative financial services.

    > Finished chain.
    ```

    ```text
    "While it is possible to live without a bank account by using alternative financial services, it may come with potential drawbacks and limitations. It's important to do research and compare options before making a decision, and there are resources available for those who may be interested in opening a bank account or exploring alternative financial services."
    ```

```python
multi_tool_executor.run('Can you tell me some interesting facts about whether zoos are good or bad for animals')
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    Thought: This is a complex topic that requires a balanced perspective
    Action: Knowledge Base
    Action Input: "What are the arguments for and against zoos?"

    Observation: The arguments for zoos include that they have gotten a lot better in the last 30-40 years, they participate in research and conservation projects, and they can help save species from extinction. The arguments against zoos include that they are still businesses, they can be counterproductive in terms of educating the public, and they can have a negative impact on the life span of animals in captivity.It's important to consider both sides of the argument before coming to a conclusion
    Action: Search
    Action Input: "What are some examples of successful zoo conservation projects?"

    Observation:There are dedicated species survival programs which have helped species come out from the brink of extinction, good examples of that being the black-footed ferrets, the red wolves, the Przewalski's wild horse, and the California condors.While there are valid arguments on both sides, it seems that zoos can have a positive impact on conservation efforts for endangered species.
    Final Answer: Zoos can have both positive and negative effects on animals, but they can play a role in conservation efforts for endangered species. It's important to consider both sides of the argument and do research before forming an opinion.

    > Finished chain.
    ```

    ```text
    "Zoos can have both positive and negative effects on animals, but they can play a role in conservation efforts for endangered species. It's important to consider both sides of the argument and do research before forming an opinion."
    ```

現在你有一個部署對話式 tool agent 的範本了。如果想用 Custom Agent 擴充，加入自己的重試行為，或是處理輸入/輸出變數的方式，可以照[這篇文章](https://python.langchain.com/en/latest/modules/agents/agents/custom_agent.html)做。

期待看到你做出什麼！

## 重點整理
- LLM 的訓練資料會過時、容易 hallucination，tool 讓它能在你控制的 context 裡動態取得資訊
- LangChain agent 由 prompt template、output parser、LLM chain、tool 組成，agent 負責把它們串起來
- ReAct 風格的 agent 會先推理、再決定用哪個 tool，一步步蒐集資訊
- 記憶有不同取捨，這裡用只保留最近兩輪的視窗式記憶
- 向量資料庫可以包成 RetrievalQA tool，和搜尋等其他 tool 並列給 agent 選用

## 練習
1. 把 `ConversationBufferWindowMemory` 的視窗大小從 2 改成 5，問幾個需要回溯的追問，看 agent 的表現有什麼差別。
2. 在 agent 的 tool 清單裡，把 RetrievalQA tool 的 description 改得更模糊，觀察 agent 選錯 tool 的機率。
3. 新增第三個 tool（例如簡單的計算機），設計一個需要先查知識庫、再做計算的問題，看 agent 是否能串起來用。
