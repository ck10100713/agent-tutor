---
translated: true
source: examples/vector_databases/qdrant/QA_with_Langchain_Qdrant_and_OpenAI.ipynb
---

# 用 Langchain、Qdrant 和 OpenAI 做問答

> 原文：[examples/vector_databases/qdrant/QA_with_Langchain_Qdrant_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/qdrant/QA_with_Langchain_Qdrant_and_OpenAI.ipynb)



## 這篇在做什麼
用 Langchain 搭配 Qdrant 當知識庫、OpenAI embeddings 做向量化，建一個問答系統。所有步驟都簡化成呼叫 Langchain 的對應方法，Qdrant 跑在本機 Docker 裡。

## 學完你會
- 用 Docker 啟動本機 Qdrant，並把問答資料的 embedding 存進去
- 用 Langchain 的 `stuff` chain 做檢索加回答
- 自訂 prompt template 改變 LLM 的回答行為

## 開跑前
需要 OpenAI API key（設成環境變數 `OPENAI_API_KEY`），以及本機的 Docker，用來啟動 Qdrant server。

這份 notebook 示範怎麼用 Langchain、以 Qdrant 當知識庫，加上 OpenAI embeddings 實作一個問答系統。如果你不熟 Qdrant，建議先看 [Getting_started_with_Qdrant_and_OpenAI.ipynb](Getting_started_with_Qdrant_and_OpenAI.md)。

這份 notebook 呈現的是端到端流程：
1. 用 OpenAI API 計算 embedding。
2. 把 embedding 存進本機的 Qdrant 實例，建立知識庫。
3. 用 OpenAI API 把原始文字問題轉成 embedding。
4. 用 Qdrant 在建好的 collection 裡做最近鄰搜尋，找到一些 context。
5. 請 LLM 在給定的 context 裡找出答案。

所有步驟都會簡化成呼叫對應的 Langchain 方法。

## 前置條件

要做這個練習，需要先準備幾樣東西：

1. Qdrant server 實例。我們用的是本機的 Docker container。
2. [qdrant-client](https://github.com/qdrant/qdrant_client) 函式庫，用來跟向量資料庫互動。
3. [Langchain](https://github.com/hwchase17/langchain) 當框架。
3. 一組 [OpenAI API key](https://beta.openai.com/account/api-keys)。

### 啟動 Qdrant server

我們用跑在 Docker container 裡的本機 Qdrant 實例。最簡單的啟動方式，是用附帶的 [docker-compose.yaml] 檔案，並執行下面的指令：

```python
! docker-compose up -d
```

??? note "輸出"

    ```text
    Starting qdrant_qdrant_1 ... 
    [1Bting qdrant_qdrant_1 ... done
    ```

可以用簡單的 curl 指令確認 server 有沒有成功啟動：

```python
! curl http://localhost:6333
```

??? note "輸出"

    ```text
    {"title":"qdrant - vector search engine","version":"1.0.1"}
    ```

### 安裝需求套件

這份 notebook 需要 `openai`、`langchain` 和 `qdrant-client` 這幾個套件。


```python
! pip install openai qdrant-client "langchain==0.0.100" wget
```

### 準備 OpenAI API key

OpenAI API key 用來把文件和查詢向量化。

如果還沒有 OpenAI API key，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，請執行下面的指令，把它加到環境變數 `OPENAI_API_KEY`：

```python
! export OPENAI_API_KEY="your API key"
```

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

if os.getenv("OPENAI_API_KEY") is not None:
    print("OPENAI_API_KEY is ready")
else:
    print("OPENAI_API_KEY environment variable not found")
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is ready
    ```

## 載入資料

這一段要載入一份資料，內容是一些 natural questions 和它們的答案。這些資料全部用來建立一個以 Qdrant 當知識庫的 Langchain 應用。

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
    'answers.json'
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

Langchain 已經整合 Qdrant，會為給定的文件清單做完所有索引。在我們的例子裡，要存的是手上這一組答案。

```python
from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain import VectorDBQA, OpenAI

embeddings = OpenAIEmbeddings()
doc_store = Qdrant.from_texts(
    answers, embeddings, host="localhost" 
)
```

到這一步，所有可能的答案都已經存進 Qdrant，所以可以定義完整的 QA chain。

```python
llm = OpenAI()
qa = VectorDBQA.from_chain_type(
    llm=llm, 
    chain_type="stuff", 
    vectorstore=doc_store,
    return_source_documents=False,
)
```

## 搜尋資料

資料放進 Qdrant 之後，就可以開始問問題。問題會被 OpenAI 模型自動向量化，產生的向量用來在 Qdrant 裡找可能符合的答案。檢索回來之後，最相似的答案會被放進 prompt 送給 OpenAI 大型語言模型。各服務之間的溝通如下圖：

![](https://qdrant.tech/articles_data/langchain-integration/flow-diagram.png)


```python
import random

random.seed(52)
selected_questions = random.choices(questions, k=5)
```

```python
for question in selected_questions:
    print(">", question)
    print(qa.run(question), end="\n\n")
```

??? note "輸出"

    ```text
    > where do frankenstein and the monster first meet
     Victor and the Creature first meet in the mountains.

    > who are the actors in fast and furious
     The actors in the Fast and Furious films are Vin Diesel, Paul Walker, Michelle Rodriguez, Jordana Brewster, Tyrese Gibson, Ludacris, Lucas Black, Sung Kang, Gal Gadot, Dwayne Johnson, Matt Schulze, Chad Lindberg, Johnny Strong, Eva Mendes, Devon Aoki, Nathalie Kelley, Bow Wow, Tego Calderón, Don Omar, Elsa Pataky, Kurt Russell, Nathalie Emmanuel, Scott Eastwood, Noel Gugliemi, Ja Rule, Thom Barry, Ted Levine, Minka Kelly, James Remar, Amaury Nolasco, Michael Ealy, MC Jin, Brian Goodman, Lynda Boyd, Jason Tobin, Neela, Liza Lapira, Alimi Ballard, Yorgo Constantine, Geoff Meed, Jeimy Osorio, Max William Crane, Charlie & Miller Kimsey, Eden Estrella, Romeo Santos, John Brotherton, Helen Mirren, Celestino Cornielle, Janmarco Santiago, Carlos De La Hoz, James Ayoub, Rick Yune, Cole Hauser, Brian Tee, John Ortiz, Luke Evans, Jason Statham, Charlize Theron, Reggie Lee, Mo Gallini, Roberto Sanchez, Leonardo

    > properties of red black tree in data structure
     Red black trees are a type of binary tree with a special set of properties. Each node is either red or black, the root is black, and if a node is red, then both its children are black. Every path from a given node to any of its descendant NIL nodes contains the same number of black nodes. The number of black nodes from the root to a node is the node's black depth, and the uniform number of black nodes in all paths from root to the leaves is called the black-height of the red-black tree.

    > who designed the national coat of arms of south africa
     Iaan Bekker

    > caravaggio's death of the virgin pamela askew
     I don't know.
    ```

### 自訂 prompt template

Langchain 的 `stuff` chain type 使用一個特定的 prompt，裡面包含問題和 context 文件。預設的 prompt 長這樣：

```text
Use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer.
{context}
Question: {question}
Helpful Answer:
```

不過我們可以提供自己的 prompt template，改變 OpenAI LLM 的行為，同時仍然使用 `stuff` chain type。重要的是 `{context}` 和 `{question}` 這兩個 placeholder 要保留。

#### 試試自訂 prompt

我們可以換一個 prompt template，讓模型：
1. 知道答案的話，用一句話回答。
2. 不知道問題答案的話，建議一個隨機的歌名。

```python
from langchain.prompts import PromptTemplate
```

```python
custom_prompt = """
Use the following pieces of context to answer the question at the end. Please provide
a short single-sentence summary answer only. If you don't know the answer or if it's 
not present in given context, don't try to make up an answer, but suggest me a random 
unrelated song title I could listen to. 
Context: {context}
Question: {question}
Helpful Answer:
"""
```

```python
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
```

??? note "輸出"

    ```text
    > what was uncle jesse's original last name on full house
    Uncle Jesse's original last name on Full House was Cochran.

    > when did the volcano erupt in indonesia 2018
    No volcanic eruption is mentioned in the given context. Suggested Song: "Ring of Fire" by Johnny Cash.

    > what does a dualist way of thinking mean
    Dualist way of thinking means that the mind and body are separate entities, with the mind being a non-physical substance.

    > the first civil service commission in india was set up on the basis of recommendation of
    The first Civil Service Commission in India was not set up on the basis of a recommendation.

    > how old do you have to be to get a tattoo in utah
    In Utah, you must be at least 18 years old to get a tattoo.
    ```

## 重點整理
- 向量資料庫（這裡是本機 Qdrant）當知識庫，問題向量化後做最近鄰搜尋找 context。
- Langchain 把 embedding、索引、檢索、呼叫 LLM 包成幾個方法，少寫很多膠水程式。
- `stuff` chain 會把檢索到的文件全部塞進同一個 prompt。
- 改 prompt template 就能改變 LLM 的回答行為，但 `{context}` 和 `{question}` 要保留。

## 練習
1. 換幾個不同的問題，看檢索回來的答案是不是合理。
2. 改自訂 prompt，讓模型不知道答案時回答「我不知道」，而不是建議歌名。
3. 調整檢索回來的文件數量（例如改成只取最相似的 1 筆或多取幾筆），比較回答的差異。
