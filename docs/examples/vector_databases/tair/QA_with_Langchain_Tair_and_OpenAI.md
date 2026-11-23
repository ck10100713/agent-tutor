---
translated: true
source: examples/vector_databases/tair/QA_with_Langchain_Tair_and_OpenAI.ipynb
---

# 用 Langchain、Tair 和 OpenAI 做問答

> 原文：[examples/vector_databases/tair/QA_with_Langchain_Tair_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/tair/QA_with_Langchain_Tair_and_OpenAI.ipynb)



## 這篇在做什麼
用 Langchain 搭配 Tair（當知識庫）和 OpenAI embedding，做出一個問答系統。從存資料、檢索相關內容到讓 LLM 根據內容回答，全部簡化成呼叫 Langchain 的方法。

## 學完你會
- 用 Langchain 把一批答案存進 Tair，建立知識庫
- 建立 `stuff` 類型的 QA chain，讓問題自動 embed、檢索，再交給 LLM 回答
- 自訂 prompt template 改變 LLM 的回答行為

## 開跑前
- 一個 Tair 雲端實例，以及它的 `TAIR_URL`
- OpenAI API key

這個 notebook 說明如何用 Langchain、以 Tair 當知識庫，加上 OpenAI embedding，實作一個問答系統。如果你不熟悉 Tair，建議先看 [Getting_started_with_Tair_and_OpenAI.ipynb](Getting_started_with_Tair_and_OpenAI.md)。

這個 notebook 呈現一個端到端的流程：
- 用 OpenAI API 計算 embedding。
- 把 embedding 存進 Tair 實例，建立知識庫。
- 用 OpenAI API 把原始文字 query 轉成 embedding。
- 用 Tair 在建好的 collection 裡做最近鄰搜尋，找出一些上下文。
- 請 LLM 在給定的上下文中找出答案。

所有步驟都會簡化成呼叫相應的 Langchain 方法。

## 前置條件
要做這個練習，需要準備幾樣東西：
[Tair 雲端實例](https://www.alibabacloud.com/help/en/tair/latest/what-is-tair)。
[Langchain](https://github.com/hwchase17/langchain) 當框架。
一把 OpenAI API key。

### 安裝需求套件
這個 notebook 需要以下 Python 套件：`openai`、`tiktoken`、`langchain` 和 `tair`。
- `openai` 提供方便的 OpenAI API 存取方式。
- `tiktoken` 是給 OpenAI 模型用的快速 BPE tokeniser。
- `langchain` 幫助我們更容易地建立 LLM 應用。
- `tair` 函式庫用來跟 tair vector database 互動。

```python
! pip install openai tiktoken langchain tair
```

??? note "輸出"

    ```text
    Looking in indexes: http://sg.mirrors.cloud.aliyuncs.com/pypi/simple/
    Requirement already satisfied: openai in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (0.28.0)
    Requirement already satisfied: tiktoken in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (0.4.0)
    Requirement already satisfied: langchain in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (0.0.281)
    Requirement already satisfied: tair in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (1.3.6)
    Requirement already satisfied: requests>=2.20 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from openai) (2.31.0)
    Requirement already satisfied: tqdm in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from openai) (4.66.1)
    Requirement already satisfied: aiohttp in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from openai) (3.8.5)
    Requirement already satisfied: regex>=2022.1.18 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from tiktoken) (2023.8.8)
    Requirement already satisfied: PyYAML>=5.3 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (6.0.1)
    Requirement already satisfied: SQLAlchemy<3,>=1.4 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (2.0.20)
    Requirement already satisfied: async-timeout<5.0.0,>=4.0.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (4.0.3)
    Requirement already satisfied: dataclasses-json<0.6.0,>=0.5.7 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (0.5.14)
    Requirement already satisfied: langsmith<0.1.0,>=0.0.21 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (0.0.33)
    Requirement already satisfied: numexpr<3.0.0,>=2.8.4 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (2.8.5)
    Requirement already satisfied: numpy<2,>=1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (1.25.2)
    Requirement already satisfied: pydantic<3,>=1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (1.10.12)
    Requirement already satisfied: tenacity<9.0.0,>=8.1.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from langchain) (8.2.3)
    Requirement already satisfied: redis>=4.4.4 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from tair) (5.0.0)
    Requirement already satisfied: attrs>=17.3.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (22.1.0)
    Requirement already satisfied: charset-normalizer<4.0,>=2.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (3.2.0)
    Requirement already satisfied: multidict<7.0,>=4.5 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (6.0.4)
    Requirement already satisfied: yarl<2.0,>=1.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (1.9.2)
    Requirement already satisfied: frozenlist>=1.1.1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (1.4.0)
    Requirement already satisfied: aiosignal>=1.1.2 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (1.3.1)
    Requirement already satisfied: marshmallow<4.0.0,>=3.18.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from dataclasses-json<0.6.0,>=0.5.7->langchain) (3.20.1)
    Requirement already satisfied: typing-inspect<1,>=0.4.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from dataclasses-json<0.6.0,>=0.5.7->langchain) (0.9.0)
    Requirement already satisfied: typing-extensions>=4.2.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from pydantic<3,>=1->langchain) (4.7.1)
    Requirement already satisfied: idna<4,>=2.5 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (3.4)
    Requirement already satisfied: urllib3<3,>=1.21.1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (2.0.4)
    Requirement already satisfied: certifi>=2017.4.17 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (2023.7.22)
    Requirement already satisfied: greenlet!=0.4.17 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from SQLAlchemy<3,>=1.4->langchain) (2.0.2)
    Requirement already satisfied: packaging>=17.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from marshmallow<4.0.0,>=3.18.0->dataclasses-json<0.6.0,>=0.5.7->langchain) (23.1)
    Requirement already satisfied: mypy-extensions>=0.3.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from typing-inspect<1,>=0.4.0->dataclasses-json<0.6.0,>=0.5.7->langchain) (1.0.0)
    WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
    ```

### 準備 OpenAI API key
OpenAI API key 用於文件和 query 的向量化。

如果你還沒有 OpenAI API key，可以到 [https://platform.openai.com/account/api-keys ) 取得。

拿到 key 後，請用 getpass 加入。

```python
import getpass

openai_api_key = getpass.getpass("Input your OpenAI API key:")
```

??? note "輸出"

    ```text
    Input your OpenAI API key:········
    ```

### 準備 Tair URL
要建立 Tair 連線，你需要 `TAIR_URL`。

```python
# The format of url: redis://[[username]:[password]]@localhost:6379/0
TAIR_URL = getpass.getpass("Input your tair url:")
```

??? note "輸出"

    ```text
    Input your tair url:········
    ```

## 載入資料
這一段會載入一批自然語言問題與答案的資料。所有資料都會用來建立以 Tair 當知識庫的 Langchain 應用。

```python
import wget

# All the examples come from https://ai.google.com/research/NaturalQuestions
# This is a sample of the training set that we download and extract for some
# further processing.
wget.download("https://storage.googleapis.com/dataset-natural-questions/questions.json")
wget.download("https://storage.googleapis.com/dataset-natural-questions/answers.json")
```

??? note "輸出"

    ```text
    100% [..............................................................................] 95372 / 95372
    ```

    ```text
    'answers (2).json'
    ```

```python
import json

with open("questions.json", "r") as fp:
    questions = json.load(fp)

with open("answers.json", "r") as fp:
    answers = json.load(fp)
```

```python
print(questions[0])
```

??? note "輸出"

    ```text
    when is the last episode of season 8 of the walking dead
    ```

```python
print(answers[0])
```

??? note "輸出"

    ```text
    No . overall No. in season Title Directed by Written by Original air date U.S. viewers ( millions ) 100 `` Mercy '' Greg Nicotero Scott M. Gimple October 22 , 2017 ( 2017 - 10 - 22 ) 11.44 Rick , Maggie , and Ezekiel rally their communities together to take down Negan . Gregory attempts to have the Hilltop residents side with Negan , but they all firmly stand behind Maggie . The group attacks the Sanctuary , taking down its fences and flooding the compound with walkers . With the Sanctuary defaced , everyone leaves except Gabriel , who reluctantly stays to save Gregory , but is left behind when Gregory abandons him . Surrounded by walkers , Gabriel hides in a trailer , where he is trapped inside with Negan . 101 `` The Damned '' Rosemary Rodriguez Matthew Negrete & Channing Powell October 29 , 2017 ( 2017 - 10 - 29 ) 8.92 Rick 's forces split into separate parties to attack several of the Saviors ' outposts , during which many members of the group are killed ; Eric is critically injured and rushed away by Aaron . Jesus stops Tara and Morgan from executing a group of surrendered Saviors . While clearing an outpost with Daryl , Rick is confronted and held at gunpoint by Morales , a survivor he met in the initial Atlanta camp , who is now with the Saviors . 102 `` Monsters '' Greg Nicotero Matthew Negrete & Channing Powell November 5 , 2017 ( 2017 - 11 - 05 ) 8.52 Daryl finds Morales threatening Rick and kills him ; the duo then pursue a group of Saviors who are transporting weapons to another outpost . Gregory returns to Hilltop , and after a heated argument , Maggie ultimately allows him back in the community . Eric dies from his injuries , leaving Aaron distraught . Despite Tara and Morgan 's objections , Jesus leads the group of surrendered Saviors to Hilltop . Ezekiel 's group attacks another Savior compound , during which several Kingdommers are shot while protecting Ezekiel . 103 `` Some Guy '' Dan Liu David Leslie Johnson November 12 , 2017 ( 2017 - 11 - 12 ) 8.69 Ezekiel 's group is overwhelmed by the Saviors , who kill all of them except for Ezekiel himself and Jerry . Carol clears the inside of the compound , killing all but two Saviors , who almost escape but are eventually caught by Rick and Daryl . En route to the Kingdom , Ezekiel , Jerry , and Carol are surrounded by walkers , but Shiva sacrifices herself to save them . The trio returns to the Kingdom , where Ezekiel 's confidence in himself as a leader has diminished . 104 5 `` The Big Scary U '' Michael E. Satrazemis Story by : Scott M. Gimple & David Leslie Johnson & Angela Kang Teleplay by : David Leslie Johnson & Angela Kang November 19 , 2017 ( 2017 - 11 - 19 ) 7.85 After confessing their sins to each other , Gabriel and Negan manage to escape from the trailer . Simon and the other lieutenants grow suspicious of each other , knowing that Rick 's forces must have inside information . The workers in the Sanctuary become increasingly frustrated with their living conditions , and a riot nearly ensues , until Negan returns and restores order . Gabriel is locked in a cell , where Eugene discovers him sick and suffering . Meanwhile , Rick and Daryl argue over how to take out the Saviors , leading Daryl to abandon Rick . 105 6 `` The King , the Widow , and Rick '' John Polson Angela Kang & Corey Reed November 26 , 2017 ( 2017 - 11 - 26 ) 8.28 Rick visits Jadis in hopes of convincing her to turn against Negan ; Jadis refuses , and locks Rick in a shipping container . Carl encounters Siddiq in the woods and recruits him to Alexandria . Daryl and Tara plot to deviate from Rick 's plans by destroying the Sanctuary . Ezekiel isolates himself at the Kingdom , where Carol tries to encourage him to be the leader his people need . Maggie has the group of captured Saviors placed in a holding area and forces Gregory to join them as punishment for betraying Hilltop . 106 7 `` Time for After '' Larry Teng Matthew Negrete & Corey Reed December 3 , 2017 ( 2017 - 12 - 03 ) 7.47 After learning of Dwight 's association with Rick 's group , Eugene affirms his loyalty to Negan and outlines a plan to get rid of the walkers surrounding the Sanctuary . With help from Morgan and Tara , Daryl drives a truck through the Sanctuary 's walls , flooding its interior with walkers , killing many Saviors . Rick finally convinces Jadis and the Scavengers to align with him , and they plan to force the Saviors to surrender . However , when they arrive at the Sanctuary , Rick is horrified to see the breached walls and no sign of the walker herd . 107 8 `` How It 's Gotta Be '' Michael E. Satrazemis David Leslie Johnson & Angela Kang December 10 , 2017 ( 2017 - 12 - 10 ) 7.89 Eugene 's plan allows the Saviors to escape , and separately , the Saviors waylay the Alexandria , Hilltop , and Kingdom forces . The Scavengers abandon Rick , after which he returns to Alexandria . Ezekiel ensures that the Kingdom residents are able to escape before locking himself in the community with the Saviors . Eugene aids Gabriel and Doctor Carson in escaping the Sanctuary in order to ease his conscience . Negan attacks Alexandria , but Carl devises a plan to allow the Alexandria residents to escape into the sewers . Carl reveals he was bitten by a walker while escorting Siddiq to Alexandria . 108 9 `` Honor '' Greg Nicotero Matthew Negrete & Channing Powell February 25 , 2018 ( 2018 - 02 - 25 ) 8.28 After the Saviors leave Alexandria , the survivors make for the Hilltop while Rick and Michonne stay behind to say their final goodbyes to a dying Carl , who pleads with Rick to build a better future alongside the Saviors before killing himself . In the Kingdom , Morgan and Carol launch a rescue mission for Ezekiel . Although they are successful and retake the Kingdom , the Saviors ' lieutenant Gavin is killed by Benjamin 's vengeful brother Henry . 109 10 `` The Lost and the Plunderers '' TBA TBA March 4 , 2018 ( 2018 - 03 - 04 ) TBD 110 11 `` Dead or Alive Or '' TBA TBA March 11 , 2018 ( 2018 - 03 - 11 ) TBD 111 12 `` The Key '' TBA TBA March 18 , 2018 ( 2018 - 03 - 18 ) TBD
    ```

## 定義 Chain

Langchain 已經整合了 Tair，並會替給定的文件清單做完所有 indexing。這裡我們要存的是手上的那組答案。

```python
from langchain.vectorstores import Tair
from langchain.embeddings import OpenAIEmbeddings
from langchain import VectorDBQA, OpenAI

embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
doc_store = Tair.from_texts(
    texts=answers, embedding=embeddings, tair_url=TAIR_URL,
)
```

到這個階段，所有可能的答案都已經存進 Tair，所以可以定義整個 QA chain。

```python
llm = OpenAI(openai_api_key=openai_api_key)
qa = VectorDBQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    vectorstore=doc_store,
    return_source_documents=False,
)
```

??? note "輸出"

    ```text
    /root/anaconda3/envs/notebook/lib/python3.10/site-packages/langchain/chains/retrieval_qa/base.py:251: UserWarning: `VectorDBQA` is deprecated - please use `from langchain.chains import RetrievalQA`
      warnings.warn(
    ```

## 搜尋資料

資料放進 Tair 之後，就可以開始問問題了。問題會自動被 OpenAI 模型向量化，產生的向量會用來在 Tair 找出可能符合的答案。取回之後，最相似的答案會被放進送給 OpenAI 大型語言模型的 prompt 裡。


```python
import random

random.seed(52)
selected_questions = random.choices(questions, k=5)
```

```python
import time
for question in selected_questions:
    print(">", question)
    print(qa.run(question), end="\n\n")
    # wait 20seconds because of the rate limit
    time.sleep(20)
```

??? note "輸出"

    ```text
    > where do frankenstein and the monster first meet
     Frankenstein and the monster first meet in the mountains.

    > who are the actors in fast and furious
     The actors in Fast & Furious are Vin Diesel ( Dominic Toretto ), Paul Walker ( Brian O'Conner ), Michelle Rodriguez ( Letty Ortiz ), Jordana Brewster ( Mia Toretto ), Tyrese Gibson ( Roman Pearce ), Ludacris ( Tej Parker ), Lucas Black ( Sean Boswell ), Sung Kang ( Han Lue ), Gal Gadot ( Gisele Yashar ), and Dwayne Johnson ( Luke Hobbs ).

    > properties of red black tree in data structure
     The properties of a red-black tree in data structure are that each node is either red or black, the root is black, if a node is red then both its children must be black, and every path from a given node to any of its descendant NIL nodes contains the same number of black nodes.

    > who designed the national coat of arms of south africa
     Iaan Bekker

    > caravaggio's death of the virgin pamela askew
     I don't know.
    ```

### 自訂 prompt template

Langchain 的 `stuff` chain type 使用一個特定的 prompt，裡面放入問題和上下文文件。預設的 prompt 長這樣：

```text
Use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer.
{context}
Question: {question}
Helpful Answer:
```

不過我們可以提供自己的 prompt template，改變 OpenAI LLM 的行為，同時仍然使用 `stuff` chain type。重要的是要保留 `{context}` 和 `{question}` 這兩個 placeholder。

#### 試試自訂 prompt

我們可以試試不同的 prompt template，讓模型：
1. 如果知道答案，就用一句話回答。
2. 如果不知道我們問題的答案，就推薦一個隨機的歌名。

```python
from langchain.prompts import PromptTemplate
custom_prompt = """
Use the following pieces of context to answer the question at the end. Please provide
a short single-sentence summary answer only. If you don't know the answer or if it's
not present in given context, don't try to make up an answer, but suggest me a random
unrelated song title I could listen to.
Context: {context}
Question: {question}
Helpful Answer:
"""

custom_prompt_template = PromptTemplate(
    template=custom_prompt, input_variables=["context", "question"]
)
```

```python
custom_qa = VectorDBQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    vectorstore=doc_store,
    return_source_documents=False,
    chain_type_kwargs={"prompt": custom_prompt_template},
)
```

```python
random.seed(41)
for question in random.choices(questions, k=5):
    print(">", question)
    print(custom_qa.run(question), end="\n\n")
    # wait 20seconds because of the rate limit
    time.sleep(20)
```

??? note "輸出"

    ```text
    > what was uncle jesse's original last name on full house
    Uncle Jesse's original last name on Full House was Cochran.

    > when did the volcano erupt in indonesia 2018
    The given context does not mention any volcanic eruption in Indonesia in 2018. Suggested song title: "The Heat Is On" by Glenn Frey.

    > what does a dualist way of thinking mean
    Dualism means the belief that there is a distinction between the mind and the body, and that the mind is a non-extended, non-physical substance.

    > the first civil service commission in india was set up on the basis of recommendation of
    The first Civil Service Commission in India was not set up on the basis of the recommendation of the Election Commission of India's Model Code of Conduct.

    > how old do you have to be to get a tattoo in utah
    You must be at least 18 years old to get a tattoo in Utah.
    ```

## 重點整理
- RAG 問答的流程是：embed、存進向量庫、embed query、檢索最相近內容、讓 LLM 根據內容回答。
- Langchain 把這些步驟包起來，你只要建 vector store 和 chain。
- `stuff` chain 就是把檢索到的文件全部塞進同一個 prompt。
- 自訂 prompt 可以改變回答風格，但一定要保留 `{context}` 和 `{question}`。

## 練習
1. 換幾個自己的問題丟給 QA chain，看它是否能從知識庫找到答案。
2. 修改自訂 prompt，讓模型不知道時回答「我不知道」，而不是推薦歌名。
3. 調整檢索時回傳的文件數量（retriever 的 k），觀察答案品質和 prompt 長度怎麼變。
