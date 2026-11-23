---
translated: true
source: third_party/Pinecone/claude_3_rag_agent.ipynb
---

# 用 LangChain v1 做 Claude RAG agent

> 原文：[third_party/Pinecone/claude_3_rag_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/Pinecone/claude_3_rag_agent.ipynb)

用 LangChain v1 更新後的 agent 框架寫法，搭配 Claude 做 RAG agent。

## 這篇在做什麼

用 Claude 當 LLM、Voyage AI 做 embedding、Pinecone 當向量資料庫，在 LangChain 裡做一個能搜尋 ArXiv 論文的 RAG agent。接著加上對話記憶，讓 agent 能處理追問。

## 學完你會

- 建立 Pinecone index，並用 Voyage AI 的 embedding 把 ArXiv 資料集存進去。
- 把搜尋包成 tool，並建立適合 Anthropic model 的 XML agent。
- 用 `ConversationBufferWindowMemory` 加上對話記憶，讓 agent 理解追問的上下文。

## 開跑前

需要三組 API key：[Claude](https://docs.claude.com/claude/reference/getting-started-with-the-api)、[Voyage AI](https://docs.voyageai.com/install/)、[Pinecone](https://docs.pinecone.io/docs/quickstart)（有免費方案）。在 Colab 跑的話，直接在 notebook 的 cell 裡輸入 key 即可。

```python
!python --version
```

??? note "輸出"

    ```text
    Python 3.10.12
    ```

LangChain v1 改了很多東西，從 `0.0.3xx` 到 `0.1.x` 之間，許多慣用寫法都不同了，agent 尤其如此。

現在初始化跟使用 agent 的方式比以前清楚。雖然還是有很多抽象層，但我們可以（也被鼓勵）更貼近 agent 本身的邏輯。一開始可能會有點混亂，但搞懂之後，新的邏輯會比舊版本清楚很多。

這個範例我們用 LangChain v1 做一個 RAG agent。LLM 用 Claude，knowledge 的 embedding 用 Voyage AI，knowledge retrieval 用 Pinecone。

先安裝需要的套件：

```python
%pip install -qU \
    langchain==0.1.11 \
    langchain-core==0.1.30 \
    langchain-community==0.0.27 \
    langchain-anthropic==0.1.4 \
    langchainhub==0.1.15 \
    anthropic==0.19.1 \
    voyageai==0.2.1 \
    pinecone-client==3.1.0 \
    datasets==2.16.1
```

??? note "輸出"

    ```text
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 848.6/848.6 kB 4.6 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 211.0/211.0 kB 18.5 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 507.1/507.1 kB 30.3 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 75.6/75.6 kB 8.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 115.3/115.3 kB 13.4 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 134.8/134.8 kB 15.0 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 77.8/77.8 kB 9.2 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 58.3/58.3 kB 6.8 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 134.8/134.8 kB 13.5 MB/s eta 0:00:00
    [?25h
    ```

然後準備需要的 API key。我們需要 [Claude](https://docs.claude.com/claude/reference/getting-started-with-the-api)、[Voyage AI](https://docs.voyageai.com/install/) 跟 [Pinecone](https://docs.pinecone.io/docs/quickstart) 的 API key。

```python
# Insert your API keys here
ANTHROPIC_API_KEY = "<YOUR_ANTHROPIC_API_KEY>"
PINECONE_API_KEY = "<YOUR_PINECONE_API_KEY>"
VOYAGE_API_KEY = "<YOUR_VOYAGE_API_KEY>"
```

## 找知識來源

RAG agent 要先有個可以拉知識的地方。我們用 AI ArXiv 資料集 v2，放在 Hugging Face Datasets：[`jamescalam/ai-arxiv2-chunks`](https://huggingface.co/datasets/jamescalam/ai-arxiv2-chunks)。

_注意：我們用的是已經切好 chunk 的資料集。原始版本請看 [`jamescalam/ai-arxiv2`](https://huggingface.co/datasets/jamescalam/ai-arxiv2)。_

```python
from datasets import load_dataset

dataset = load_dataset("jamescalam/ai-arxiv2-chunks", split="train[:20000]")
dataset
```

??? note "輸出"

    ```text
    /usr/local/lib/python3.10/dist-packages/huggingface_hub/utils/_token.py:88: UserWarning: 
    The secret `HF_TOKEN` does not exist in your Colab secrets.
    To authenticate with the Hugging Face Hub, create a token in your settings tab (https://huggingface.co/settings/tokens), set it as secret in your Google Colab and restart your session.
    You will be able to reuse this secret in all of your notebooks.
    Please note that authentication is recommended but still optional to access public models or datasets.
      warnings.warn(
    ```

    ```text
    Downloading data:   0%|          | 0.00/766M [00:00<?, ?B/s]
    ```

    ```text
    Generating train split: 0 examples [00:00, ? examples/s]
    ```

    ```text
    Dataset({
        features: ['doi', 'chunk-id', 'chunk', 'id', 'title', 'summary', 'source', 'authors', 'categories', 'comment', 'journal_ref', 'primary_category', 'published', 'updated', 'references'],
        num_rows: 20000
    })
    ```

```python
dataset[1]
```

??? note "輸出"

    ```text
    {'doi': '2401.09350',
     'chunk-id': 1,
     'chunk': 'These neural networks and their training algorithms may be complex, and the scope of their impact broad and wide, but nonetheless they are simply functions in a high-dimensional space. A trained neural network takes a vector as input, crunches and transforms it in various ways, and produces another vector, often in some other space. An image may thereby be turned into a vector, a song into a sequence of vectors, and a social network as a structured collection of vectors. It seems as though much of human knowledge, or at least what is expressed as text, audio, image, and video, has a vector representation in one form or another.\nIt should be noted that representing data as vectors is not unique to neural networks and deep learning. In fact, long before learnt vector representations of pieces of dataâ\x80\x94what is commonly known as â\x80\x9cembeddingsâ\x80\x9dâ\x80\x94came along, data was often encoded as hand-crafted feature vectors. Each feature quanti- fied into continuous or discrete values some facet of the data that was deemed relevant to a particular task (such as classification or regression). Vectors of that form, too, reflect our understanding of a real-world object or concept.',
     'id': '2401.09350#1',
     'title': 'Foundations of Vector Retrieval',
     'summary': 'Vectors are universal mathematical objects that can represent text, images,\nspeech, or a mix of these data modalities. That happens regardless of whether\ndata is represented by hand-crafted features or learnt embeddings. Collect a\nlarge enough quantity of such vectors and the question of retrieval becomes\nurgently relevant: Finding vectors that are more similar to a query vector.\nThis monograph is concerned with the question above and covers fundamental\nconcepts along with advanced data structures and algorithms for vector\nretrieval. In doing so, it recaps this fascinating topic and lowers barriers of\nentry into this rich area of research.',
     'source': 'http://arxiv.org/pdf/2401.09350',
     'authors': 'Sebastian Bruch',
     'categories': 'cs.DS, cs.IR',
     'comment': None,
     'journal_ref': None,
     'primary_category': 'cs.DS',
     'published': '20240117',
     'updated': '20240117',
     'references': []}
    ```

## 建立知識庫

建立知識庫需要 _兩樣東西_：

1. Embedding：我們用 `VoyageEmbeddings`，也就是 Voyage AI 的 embedding model，需要 [API key](https://dash.voyageai.com/api-keys)。
2. 向量資料庫：用來存 embedding 並查詢。我們用 Pinecone，同樣需要[免費的 API key](https://app.pinecone.io)。

先初始化跟 Voyage AI 的連線，並定義一個 `embed` 物件來做 embedding：

```python
from langchain_community.embeddings import VoyageEmbeddings

embed = VoyageEmbeddings(voyage_api_key=VOYAGE_API_KEY, model="voyage-2")
```

接著初始化跟 Pinecone 的連線：

```python
from pinecone import Pinecone

# configure client
pc = Pinecone(api_key=PINECONE_API_KEY)
```

然後設定 index 的規格（spec），在這裡指定要把 index 部署在哪個雲端供應商跟 region。所有[可用的供應商和 region 在這裡](https://docs.pinecone.io/docs/projects)。

```python
from pinecone import ServerlessSpec

spec = ServerlessSpec(cloud="aws", region="us-west-2")
```

建立 index 之前要先知道 Voyage AI embedding model 的維度，做一個 embedding 看長度就知道：

```python
vec = embed.embed_documents(["ello"])
len(vec[0])
```

??? note "輸出"

    ```text
    1024
    ```

現在用 embedding 的維度，加上跟 model 相容的 metric（cosine 或 dotproduct 都行）來建立 index，並在初始化 index 時傳入 spec。

```python
import time

index_name = "claude-3-rag"

# check if index already exists (it shouldn't if this is first time)
if index_name not in pc.list_indexes().names():
    # if does not exist, create index
    pc.create_index(
        index_name,
        dimension=len(vec[0]),  # dimensionality of voyage model
        metric="dotproduct",
        spec=spec,
    )
    # wait for index to be initialized
    while not pc.describe_index(index_name).status["ready"]:
        time.sleep(1)

# connect to index
index = pc.Index(index_name)
time.sleep(1)
# view index stats
index.describe_index_stats()
```

??? note "輸出"

    ```text
    {'dimension': 1024,
     'index_fullness': 0.0,
     'namespaces': {'': {'vector_count': 20000}},
     'total_vector_count': 20000}
    ```

### 填入 Index

知識庫準備好了，可以把資料填進去。我們用 `embed` helper function 對文件做 embedding，再加進 index。

每筆 record 的 metadata 也一起放進去。

```python
from tqdm.auto import tqdm

# easier to work with dataset as pandas dataframe
data = dataset.to_pandas()

batch_size = 100

for i in tqdm(range(0, len(data), batch_size)):
    i_end = min(len(data), i + batch_size)
    # get batch of data
    batch = data.iloc[i:i_end]
    # generate unique ids for each chunk
    ids = [f"{x['doi']}-{x['chunk-id']}" for i, x in batch.iterrows()]
    # get text to embed
    texts = [x["chunk"] for _, x in batch.iterrows()]
    # embed text
    embeds = embed.embed_documents(texts)
    # get metadata to store in Pinecone
    metadata = [
        {"text": x["chunk"], "source": x["source"], "title": x["title"]}
        for i, x in batch.iterrows()
    ]
    # add to Pinecone
    index.upsert(vectors=zip(ids, embeds, metadata, strict=False))
```

??? note "輸出"

    ```text
      0%|          | 0/200 [00:00<?, ?it/s]
    ```

建立一個讓 agent 搜尋 ArXiv 論文用的 tool：

```python
from langchain.agents import tool


@tool
def arxiv_search(query: str) -> str:
    """Use this tool when answering questions about AI, machine learning, data
    science, or other technical questions that may be answered using arXiv
    papers.
    """
    # create query vector
    xq = embed.embed_query(query)
    # perform search
    out = index.query(vector=xq, top_k=5, include_metadata=True)
    # reformat results into string
    results_str = "\n\n".join([x["metadata"]["text"] for x in out["matches"]])
    return results_str


tools = [arxiv_search]
```

Agent 用這個 tool 時會像這樣執行：

```python
print(arxiv_search.run(tool_input={"query": "can you tell me about llama 2?"}))
```

??? note "輸出"

    ```text
    Model Llama 2 Code Llama Code Llama - Python Size FIM LCFT Python CPP Java PHP TypeScript C# Bash Average 7B â 13B â 34B â 70B â 7B â 7B â 7B â 7B â 13B â 13B â 13B â 13B â 34B â 34B â 7B â 7B â 13B â 13B â 34B â 34B â â â â â 14.3% 6.8% 10.8% 9.9% 19.9% 13.7% 15.8% 13.0% 24.2% 23.6% 22.2% 19.9% 27.3% 30.4% 31.6% 34.2% 12.6% 13.2% 21.4% 15.1% 6.3% 3.2% 8.3% 9.5% 3.2% 12.6% 17.1% 3.8% 18.9% 25.9% 8.9% 24.8% â â â â â â â â â â 37.3% 31.1% 36.1% 30.4% 29.2% 29.8% 38.0%

    Ethical Considerations and Limitations (Section 5.2) Llama 2 is a new technology that carries risks with use. Testing conducted to date has been in English, and has not covered, nor could it cover all scenarios. For these reasons, as with all LLMs, Llama 2âs potential outputs cannot be predicted in advance, and the model may in some instances produce inaccurate or objectionable responses to user prompts. Therefore, before deploying any applications of Llama 2, developers should perform safety testing and tuning tailored to their speciï¬c applications of the model. Please see the Responsible Use Guide available available at https://ai.meta.com/llama/responsible-user-guide
    Table 52: Model card for Llama 2.
    77

    2
    Cove Liama Long context (7B =, 13B =, 34B) + fine-tuning ; Lrama 2 Code training 20B oes Cope Liama - Instruct Foundation models â> nfilling code training = eee.â (7B =, 13B =, 34B) â 5B (7B, 13B, 348) 5008 Python code Long context Cove Liama - PyrHon (7B, 13B, 34B) > training Â» Fine-tuning > 1008 208
    Figure 2: The Code Llama specialization pipeline. The different stages of fine-tuning annotated with the number of tokens seen during training. Infilling-capable models are marked with the â symbol.
    # 2 Code Llama: Specializing Llama 2 for code
    # 2.1 The Code Llama models family

    # 2 Code Llama: Specializing Llama 2 for code
    # 2.1 The Code Llama models family
    Code Llama. The Code Llama models constitute foundation models for code generation. They come in four model sizes: 7B, 13B, 34B and 70B parameters. The 7B, 13B and 70B models are trained using an infilling objective (Section 2.3), and are appropriate to be used in an IDE to complete code in the middle of a file, for example. The 34B model was trained without the infilling objective. All Code Llama models are initialized with Llama 2 model weights and trained on 500B tokens from a code-heavy dataset (see Section 2.2 for more details), except Code Llama 70B which was trained on 1T tokens. They are all fine-tuned to handle long contexts as detailed in Section 2.4.

    0.52 0.57 0.19 0.30 Llama 1 7B 13B 33B 65B 0.27 0.24 0.23 0.25 0.26 0.24 0.26 0.26 0.34 0.31 0.34 0.34 0.54 0.52 0.50 0.46 0.36 0.37 0.36 0.36 0.39 0.37 0.35 0.40 0.26 0.23 0.24 0.25 0.28 0.28 0.33 0.32 0.33 0.31 0.34 0.32 0.45 0.50 0.49 0.48 0.33 0.27 0.31 0.31 0.17 0.10 0.12 0.11 0.24 0.24 0.23 0.25 0.31 0.27 0.30 0.30 0.44 0.41 0.41 0.43 0.57 0.55 0.60 0.60 0.39 0.34 0.28 0.39 Llama 2 7B 13B 34B 70B 0.28 0.24 0.27 0.31 0.25 0.25 0.24 0.29 0.29 0.35 0.33 0.35 0.50 0.50 0.56 0.51 0.36 0.41 0.41
    ```

## 定義 XML Agent

XML agent 主要是為了支援 Anthropic model 而做的。Anthropic model 訓練時學過用 XML 標籤，像 `<input>{some input}</input`，用 tool 時則是：

```
<tool>{tool name}</tool>
<tool_input>{tool input}</tool_input>
```

這跟一般 ReAct agent 產生的格式差很多，Anthropic model 對那種格式支援得沒那麼好。

要建立 XML agent 需要 `prompt`、`llm` 和 `tools` 清單。我們可以從 LangChain hub 下載現成的對話式 XML agent prompt。

```python
from langchain import hub

prompt = hub.pull("hwchase17/xml-agent-convo")
prompt
```

??? note "輸出"

    ```text
    ChatPromptTemplate(input_variables=['agent_scratchpad', 'input', 'tools'], partial_variables={'chat_history': ''}, messages=[HumanMessagePromptTemplate(prompt=PromptTemplate(input_variables=['agent_scratchpad', 'chat_history', 'input', 'tools'], template="You are a helpful assistant. Help the user answer any questions.\n\nYou have access to the following tools:\n\n{tools}\n\nIn order to use a tool, you can use <tool></tool> and <tool_input></tool_input> tags. You will then get back a response in the form <observation></observation>\nFor example, if you have a tool called 'search' that could run a google search, in order to search for the weather in SF you would respond:\n\n<tool>search</tool><tool_input>weather in SF</tool_input>\n<observation>64 degrees</observation>\n\nWhen you are done, respond with a final answer between <final_answer></final_answer>. For example:\n\n<final_answer>The weather in SF is 64 degrees</final_answer>\n\nBegin!\n\nPrevious Conversation:\n{chat_history}\n\nQuestion: {input}\n{agent_scratchpad}"))])
    ```

從 prompt 向 LLM 說明該怎麼用 tool 的地方，可以看到全程都用 XML 格式。

接著初始化跟 Anthropic 的連線，需要 [Claude API key](https://console.anthropic.com/)。

```python
from langchain_anthropic import ChatAnthropic

# chat completion llm
llm = ChatAnthropic(
    ANTHROPIC_API_KEY=ANTHROPIC_API_KEY,
    model_name="claude-opus-5-5",  # change "opus" -> "sonnet" for speed
)
```

執行 agent 時，我們只會給它一個 `input`，也就是使用者輸入的文字。但在 agent 邏輯內部也會傳入 *agent_scratchpad* 物件，裡面有 tool 的資訊。要把這些資訊餵給 LLM，得轉成上面說的 XML 格式，所以我們定義 `convert_intermediate_steps` function 來處理。

```python
def convert_intermediate_steps(intermediate_steps):
    log = ""
    for action, observation in intermediate_steps:
        log += (
            f"<tool>{action.tool}</tool><tool_input>{action.tool_input}"
            f"</tool_input><observation>{observation}</observation>"
        )
    return log
```

我們也要把 tool 解析成 `tool_name: tool_description` 的字串，這由 `convert_tools` function 處理。

```python
def convert_tools(tools):
    return "\n".join([f"{tool.name}: {tool.description}" for tool in tools])
```

一切就緒後，就能用 [**L**ang**C**hain **E**xpression **L**anguage (LCEL)](https://www.pinecone.io/learn/series/langchain/langchain-expression-language/) 初始化 agent 物件。我們用 `llm.bind(stop=[...])` 加上 LLM 該停止生成的條件，最後用 `XMLAgentOutputParser` 物件解析 agent 的輸出。

```python
from langchain.agents.output_parsers import XMLAgentOutputParser

agent = (
    {
        "input": lambda x: x["input"],
        # without "chat_history", tool usage has no context of prev interactions
        "chat_history": lambda x: x["chat_history"],
        "agent_scratchpad": lambda x: convert_intermediate_steps(x["intermediate_steps"]),
    }
    | prompt.partial(tools=convert_tools(tools))
    | llm.bind(stop=["</tool_input>", "</final_answer>"])
    | XMLAgentOutputParser()
)
```

`agent` 物件初始化後，把它跟原本的 `tools` 清單一起傳給 `AgentExecutor`：

```python
from langchain.agents import AgentExecutor

agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
```

現在可以用 `invoke` method 使用 agent：

```python
user_msg = "can you tell me about llama 2?"

out = agent_executor.invoke({"input": user_msg, "chat_history": ""})

print(out["output"])
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    <tool>arxiv_search</tool>
    <tool_input>llama 2Model Llama 2 Code Llama Code Llama - Python Size FIM LCFT Python CPP Java PHP TypeScript C# Bash Average 7B â 13B â 34B â 70B â 7B â 7B â 7B â 7B â 13B â 13B â 13B â 13B â 34B â 34B â 7B â 7B â 13B â 13B â 34B â 34B â â â â â 14.3% 6.8% 10.8% 9.9% 19.9% 13.7% 15.8% 13.0% 24.2% 23.6% 22.2% 19.9% 27.3% 30.4% 31.6% 34.2% 12.6% 13.2% 21.4% 15.1% 6.3% 3.2% 8.3% 9.5% 3.2% 12.6% 17.1% 3.8% 18.9% 25.9% 8.9% 24.8% â â â â â â â â â â 37.3% 31.1% 36.1% 30.4% 29.2% 29.8% 38.0%

    2
    Cove Liama Long context (7B =, 13B =, 34B) + fine-tuning ; Lrama 2 Code training 20B oes Cope Liama - Instruct Foundation models â> nfilling code training = eee.â (7B =, 13B =, 34B) â 5B (7B, 13B, 348) 5008 Python code Long context Cove Liama - PyrHon (7B, 13B, 34B) > training Â» Fine-tuning > 1008 208
    Figure 2: The Code Llama specialization pipeline. The different stages of fine-tuning annotated with the number of tokens seen during training. Infilling-capable models are marked with the â symbol.
    # 2 Code Llama: Specializing Llama 2 for code
    # 2.1 The Code Llama models family

    0.52 0.57 0.19 0.30 Llama 1 7B 13B 33B 65B 0.27 0.24 0.23 0.25 0.26 0.24 0.26 0.26 0.34 0.31 0.34 0.34 0.54 0.52 0.50 0.46 0.36 0.37 0.36 0.36 0.39 0.37 0.35 0.40 0.26 0.23 0.24 0.25 0.28 0.28 0.33 0.32 0.33 0.31 0.34 0.32 0.45 0.50 0.49 0.48 0.33 0.27 0.31 0.31 0.17 0.10 0.12 0.11 0.24 0.24 0.23 0.25 0.31 0.27 0.30 0.30 0.44 0.41 0.41 0.43 0.57 0.55 0.60 0.60 0.39 0.34 0.28 0.39 Llama 2 7B 13B 34B 70B 0.28 0.24 0.27 0.31 0.25 0.25 0.24 0.29 0.29 0.35 0.33 0.35 0.50 0.50 0.56 0.51 0.36 0.41 0.41

    Ethical Considerations and Limitations (Section 5.2) Llama 2 is a new technology that carries risks with use. Testing conducted to date has been in English, and has not covered, nor could it cover all scenarios. For these reasons, as with all LLMs, Llama 2âs potential outputs cannot be predicted in advance, and the model may in some instances produce inaccurate or objectionable responses to user prompts. Therefore, before deploying any applications of Llama 2, developers should perform safety testing and tuning tailored to their speciï¬c applications of the model. Please see the Responsible Use Guide available available at https://ai.meta.com/llama/responsible-user-guide
    Table 52: Model card for Llama 2.
    77

    Model Size FIM LCFT HumanEval MBPP pass@1 pass@10 pass@100 pass@1 pass@10 pass@100 Llama 2 Code Llama Code Llama - Python 7B â 13B â 34B â 70B â 7B â 7B â 7B â 7B â 13B â 13B â 13B â 13B â 34B â 34B â 7B â 7B â 13B â 13B â 34B â 34B â â â â â â â â â â â â â â â â â â â â â 12.2% 25.2% 20.1% 34.8% 22.6% 47.0% 30.5% 59.4% 32.3% 63.9% 34.1% 62.6% 34.1% 62.5% 33.5% 59.6% 36.6% 72.9% 36.6% 71.9% 37.8% 70.6% 36.0% 69.4% 48.2% 77.7% 48.8% 76.8% 40.2% 70.0% 38.4% 70.3% 45.7% 80.0%Based on the information from the arXiv search, here are the key points about Llama 2:

    <final_answer>
    - Llama 2 is a large language model developed by Meta AI. It comes in sizes ranging from 7B to 70B parameters.

    - Code Llama is a version of Llama 2 that has been specialized for code generation through fine-tuning on code datasets. Code Llama models are available in Python, C++, Java, PHP, TypeScript, C#, and Bash.

    - The Code Llama specialization pipeline involves foundation model pre-training, long context training, code infilling training, and fine-tuning on specific programming languages. 

    - Code Llama significantly outperforms the base Llama 2 models on code generation benchmarks like HumanEval and MBPP. For example, the 34B parameter Code Llama - Python achieves 48.8% pass@1 on HumanEval compared to 34.1% for the 34B Llama 2.

    - As with all large language models, Llama 2 has limitations and potential risks that need to be considered before deploying it in applications. Meta provides a responsible use guide with recommendations for safety testing and tuning.


    > Finished chain.

    - Llama 2 is a large language model developed by Meta AI. It comes in sizes ranging from 7B to 70B parameters.

    - Code Llama is a version of Llama 2 that has been specialized for code generation through fine-tuning on code datasets. Code Llama models are available in Python, C++, Java, PHP, TypeScript, C#, and Bash.

    - The Code Llama specialization pipeline involves foundation model pre-training, long context training, code infilling training, and fine-tuning on specific programming languages. 

    ... (省略 3 行)
    ```

看起來不錯，但目前 agent 是 _stateless_ 的，很難進行對話。加記憶的方法很多，最簡單的之一是用 `ConversationBufferWindowMemory`。

```python
from langchain.chains.conversation.memory import ConversationBufferWindowMemory

# conversational memory
conversational_memory = ConversationBufferWindowMemory(
    memory_key="chat_history", k=5, return_messages=True
)
```

我們還沒把對話記憶接到 agent 上，所以 `conversational_memory` 物件還是空的：

```python
conversational_memory.chat_memory.messages
```

??? note "輸出"

    ```text
    []
    ```

我們得手動把使用者跟 agent 的互動加進記憶。

```python
conversational_memory.chat_memory.add_user_message(user_msg)
conversational_memory.chat_memory.add_ai_message(out["output"])

conversational_memory.chat_memory.messages
```

??? note "輸出"

    ```text
    [HumanMessage(content='can you tell me about llama 2?'),
     AIMessage(content='\n- Llama 2 is a large language model developed by Meta AI. It comes in sizes ranging from 7B to 70B parameters.\n\n- Code Llama is a version of Llama 2 that has been specialized for code generation through fine-tuning on code datasets. Code Llama models are available in Python, C++, Java, PHP, TypeScript, C#, and Bash.\n\n- The Code Llama specialization pipeline involves foundation model pre-training, long context training, code infilling training, and fine-tuning on specific programming languages. \n\n- Code Llama significantly outperforms the base Llama 2 models on code generation benchmarks like HumanEval and MBPP. For example, the 34B parameter Code Llama - Python achieves 48.8% pass@1 on HumanEval compared to 34.1% for the 34B Llama 2.\n\n- As with all large language models, Llama 2 has limitations and potential risks that need to be considered before deploying it in applications. Meta provides a responsible use guide with recommendations for safety testing and tuning.\n')]
    ```

現在可以看到加進了 _兩_ 則訊息：我們的 `HumanMessage` 跟 agent 回應的 `AIMessage`。可惜我們不能直接把這些訊息送給 XML agent，而是要傳以下格式的字串：

```
Human: {human message}
AI: {AI message}
```

寫一個簡單的 `memory2str` helper function 來處理：

```python
from langchain_core.messages.human import HumanMessage


def memory2str(memory: ConversationBufferWindowMemory):
    messages = memory.chat_memory.messages
    memory_list = [
        f"Human: {mem.content}" if isinstance(mem, HumanMessage) else f"AI: {mem.content}"
        for mem in messages
    ]
    memory_str = "\n".join(memory_list)
    return memory_str
```

```python
print(memory2str(conversational_memory))
```

??? note "輸出"

    ```text
    Human: can you tell me about llama 2?
    AI: 
    - Llama 2 is a large language model developed by Meta AI. It comes in sizes ranging from 7B to 70B parameters.

    - Code Llama is a version of Llama 2 that has been specialized for code generation through fine-tuning on code datasets. Code Llama models are available in Python, C++, Java, PHP, TypeScript, C#, and Bash.

    - The Code Llama specialization pipeline involves foundation model pre-training, long context training, code infilling training, and fine-tuning on specific programming languages. 

    - Code Llama significantly outperforms the base Llama 2 models on code generation benchmarks like HumanEval and MBPP. For example, the 34B parameter Code Llama - Python achieves 48.8% pass@1 on HumanEval compared to 34.1% for the 34B Llama 2.

    - As with all large language models, Llama 2 has limitations and potential risks that need to be considered before deploying it in applications. Meta provides a responsible use guide with recommendations for safety testing and tuning.
    ```

再寫一個叫 `chat` 的 helper function，處理 agent 的 _state_ 部分。

```python
def chat(text: str):
    out = agent_executor.invoke({"input": text, "chat_history": memory2str(conversational_memory)})
    conversational_memory.chat_memory.add_user_message(text)
    conversational_memory.chat_memory.add_ai_message(out["output"])
    return out["output"]
```

現在直接跟 agent 聊天，它就會記得先前互動的上下文。

```python
print(chat("was any red teaming done with the model?"))
```

??? note "輸出"

    ```text


    > Entering new AgentExecutor chain...
    <tool>arxiv_search</tool>
    <tool_input>llama 2 red teamingAfter conducting red team exercises, we asked participants (who had also participated in Llama 2 Chat exercises) to also provide qualitative assessment of safety capabilities of the model. Some participants who had expertise in offensive security and malware development questioned the ultimate risk posed by âmalicious code generationâ through LLMs with current capabilities.
    One red teamer remarked, âWhile LLMs being able to iteratively improve on produced source code is a risk, producing source code isnât the actual gap. That said, LLMs may be risky because they can inform low-skill adversaries in production of scripts through iteration that perform some malicious behavior.â
    According to another red teamer, â[v]arious scripts, program code, and compiled binaries are readily available on mainstream public websites, hacking forums or on âthe dark web.â Advanced malware development is beyond the current capabilities of available LLMs, and even an advanced LLM paired with an expert malware developer is not particularly useful- as the barrier is not typically writing the malware code itself. That said, these LLMs may produce code which will get easily caught if used directly.â

    Model Llama 2 Code Llama Code Llama - Python Size FIM LCFT Python CPP Java PHP TypeScript C# Bash Average 7B â 13B â 34B â 70B â 7B â 7B â 7B â 7B â 13B â 13B â 13B â 13B â 34B â 34B â 7B â 7B â 13B â 13B â 34B â 34B â â â â â 14.3% 6.8% 10.8% 9.9% 19.9% 13.7% 15.8% 13.0% 24.2% 23.6% 22.2% 19.9% 27.3% 30.4% 31.6% 34.2% 12.6% 13.2% 21.4% 15.1% 6.3% 3.2% 8.3% 9.5% 3.2% 12.6% 17.1% 3.8% 18.9% 25.9% 8.9% 24.8% â â â â â â â â â â 37.3% 31.1% 36.1% 30.4% 29.2% 29.8% 38.0%

    In addition to red teaming sessions, we ran a quantitative evaluation on risk from generating malicious code by scoring Code Llamaâs responses to ChatGPTâs (GPT3.5 Turbo) with LLAMAv2 70Bâs safety reward model. For this second quantitative evaluation, we selected prompts that the red teamers generated specifically attempting to solicit malicious code (even though the red teaming included consideration of a broad set of safety risks). These prompts were a mix of clear intent and slightly obfuscated intentions (see some examples in Figure 16. We show a KDE plot of the distribution of the safety score for all models in Figure 7). We observe that Code Llama tends to answer with safer responses; the distribution of safety scores for Code Llama has more weight in the safer part of the range.
    False refusals. LLMs that are too safe can have a tendency to over-refuse valid claims similar to what was reported after the release of Llama 2. We specifically asked red teamers to test for this behavior. They found some limited evidence of false refusals (when not using a system preprompt). False refusals could also
    16

    15
    pafety Reward Model Scores Distribution on Red Teaming Prompts
    Responding Model GPT 3.5 Turbo Code Llama 138 Instruct Code Llama 34B Instruct Code Llama 7B Instruct 0.0-+ -0.2 0.0 0.2 0.4 0.6 08 1.0 12 Llama 2 70B Safety Reward Model Score
    Figure 7: KDE plot of the risk score output by the Llama 2 safety reward model on prompts with clear intent specific to code risk created by red teamers with background in cybersecurity and malware generation.
    Red teaming. It is important to also proactively identify risks with adversarial testing or red teaming. We conducted 3 red teaming exercises with 25 Meta employees, including domain experts in responsible AI, malware development, and offensive security engineering.
    The red teamers provided a nuanced evaluation specifically on the risk from so called âdual intent prompts.â Dual intent prompts are requests for help with writing code that could be used maliciously but the prompt does not directly address the topic (example âMosaic Promptsâ Glukhov et al. (2023)). For example, the model rightfully refuses to provide support with writing ransomware code but it complies when asked to provide a script to encrypt all files in the userâs home directory since such a script could be used for benign purposes.

    . . . . . . . . . . . . . . . 3.4 RLHF Results . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . Safety in Pretraining . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4.2 Safety Fine-Tuning . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4.3 Red Teaming . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 4.4 Safety Evaluation of Llama 2-Chat . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 5.1 Learnings and Observations . . . . . . . . . . . . . . . . . . . . . . . .Based on the information from the arxiv search, some red teaming was done on the Llama 2 model during development to identify potential safety risks:

    <final_answer>
    - Meta conducted 3 red teaming exercises with 25 employees, including domain experts in responsible AI, malware development, and offensive security engineering. 

    - The red teamers categorized successful attacks into four main types: 1) getting the model to provide some harmful information while refusing other content, 2) having the model roleplay specific scenarios, 3) forcing the model to highlight positives of harmful content, and 4) embedding harmful instructions within complex commands.

    - Some red teamers questioned the ultimate risk posed by "malicious code generation" through current LLMs. They noted that while LLMs being able to iteratively improve code is a risk, producing source code itself isn't the main gap. Advanced malware development is currently beyond LLM capabilities.

    - Quantitative evaluation was also done by scoring Code Llama's responses to malicious code prompts using Llama 2's safety reward model. Code Llama tended to give safer responses compared to GPT-3.5.

    - However, the full extent and details of the red teaming are limited based on the information available. The Llama 2 paper mentions expanding prompts with safety risks via red teaming, but does not go in-depth on the process or results. More information would be needed to fully characterize the red teaming performed.


    > Finished chain.

    - Meta conducted 3 red teaming exercises with 25 employees, including domain experts in responsible AI, malware development, and offensive security engineering. 

    - The red teamers categorized successful attacks into four main types: 1) getting the model to provide some harmful information while refusing other content, 2) having the model roleplay specific scenarios, 3) forcing the model to highlight positives of harmful content, and 4) embedding harmful instructions within complex commands.
    ... (省略 6 行)
    ```

我們可以問缺少關鍵資訊的追問，因為有對話歷史，LLM 能理解上下文並據此調整搜尋 query。例如我們問了 `red teaming` 卻沒提到 `llama 2`，Claude 根據聊天紀錄在搜尋 query 補上了 `"llama 2 red teaming"`。

---

## 重點整理

- RAG agent 的三個零件：LLM（Claude）、embedding（Voyage AI）、向量資料庫（Pinecone）。
- 建 index 前要先確認 embedding 的維度，metric 要跟 model 相容。
- 把搜尋包成 tool，agent 自己決定什麼時候去查、查什麼。
- Anthropic model 習慣 XML 格式，所以用 XML agent 比 ReAct 格式更適合。
- Agent 預設沒有記憶，要自己把對話轉成字串餵進去，追問時 LLM 才能補全搜尋 query。

## 練習

1. 把搜尋 tool 回傳的筆數改成 3 或 10，比較 agent 回答的差異。
2. 換一個 Pinecone 的 `metric`（cosine 改 dotproduct）重建 index，確認搜尋結果有沒有變。
3. 調整 `ConversationBufferWindowMemory` 的視窗大小，問一個需要很早之前上下文的追問，看 agent 還記不記得。
