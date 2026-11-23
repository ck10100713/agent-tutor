---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Question_answering_using_a_search_API.ipynb
---

# 用搜尋 API 加 Re-ranking 做問答

> 原文：[examples/Question_answering_using_a_search_API.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_a_search_API.ipynb)



## 這篇在做什麼
在現有的搜尋系統（例如 News API）上，加一層 GPT 產生多組查詢，再用 embedding 對結果 re-rank，最後讓模型根據排名最高的結果回答問題。不用另外維護 vector database。

## 學完你會
- 讓 GPT 根據使用者問題產生多組查詢，並平行執行搜尋。
- 先產生一個假設的理想答案（HyDE），再用 embedding 的相似度替搜尋結果 re-rank 和過濾。
- 把排名最高的結果交給模型，產生附參考來源與連結的最終答案。

## 開跑前
- 需要 `OPENAI_API_KEY`。
- 需要 `NEWS_API_KEY`（到 newsapi.org 申請）。

要找到相關資訊有時像大海撈針，不過別擔心，GPT 其實能幫我們做很多這類工作。這份指南探討怎麼用各種 AI 技巧擴充現有的搜尋系統，幫我們從雜訊中篩選出需要的內容。

讓 GPT 取得資訊有兩種方式：

1. **模擬人類瀏覽：** [GPT 觸發搜尋](https://openai.com/blog/chatgpt-plugins#browsing)、評估結果，必要時調整搜尋 query。它也可以跟進特定的搜尋結果形成思路，就像人類使用者會做的那樣。
2. **用 Embedding 檢索：** 為你的內容和使用者 query 計算 [embedding](https://platform.openai.com/docs/guides/embeddings)，再依 cosine similarity [取回](Question_answering_using_embeddings.md)最相關的內容。Google 這類搜尋引擎[大量使用](https://blog.google/products/search/search-language-understanding-bert/)這個技術。

這兩種方法都很有前景，但各有缺點：第一種因為是迭代的，可能很慢；第二種需要事先對整個知識庫做 embedding、持續對新內容做 embedding，還要維護 vector database。

結合這兩種方法，並從 [re-ranking](https://www.sbert.net/examples/applications/retrieve_rerank/README.html) 方法得到靈感，我們找到一個介於中間的做法。**這個做法可以建在任何現有的搜尋系統之上，像是 Slack search API，或是放私有資料的內部 ElasticSearch。** 運作方式如下：

![search_augmented_by_query_generation_and_embeddings_reranking.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/search_rerank_answer.png)

**步驟 1：搜尋**

1.  使用者提出問題。
2.  GPT 產生一組可能的 query。
3.  平行執行這些搜尋 query。

**步驟 2：Re-rank**

1.  用每筆結果的 embedding，計算它和「針對使用者問題產生的假設理想答案」的語意相似度。
2.  依這個相似度指標對結果排名並過濾。

**步驟 3：回答**

1.  根據排名最高的搜尋結果，模型產生使用者問題的答案，並附上參考來源和連結。

這種混合式做法延遲相對低，可以整合進任何現有的搜尋 endpoint，也不用維護 vector database。來看看怎麼做！我們用 [News API](https://newsapi.org/) 當作搜尋的範例領域。

## 設定

除了 `OPENAI_API_KEY`，你還需要在環境變數加入 `NEWS_API_KEY`。可以在[這裡](https://newsapi.org/)取得 API key。


```python
%%capture
%env NEWS_API_KEY = YOUR_NEWS_API_KEY
```

```python
# Dependencies
from datetime import date, timedelta  # date handling for fetching recent news
from IPython import display  # for pretty printing
import json  # for parsing the JSON api responses and model outputs
from numpy import dot  # for cosine similarity
from openai import OpenAI
import os  # for loading environment variables
import requests  # for making the API requests
from tqdm.notebook import tqdm  # for printing progress bars

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

# Load environment variables
news_api_key = os.getenv("NEWS_API_KEY")

GPT_MODEL = "gpt-3.5-turbo"


# Helper functions
def json_gpt(input: str):
    completion = client.chat.completions.create(model=GPT_MODEL,
    messages=[
        {"role": "system", "content": "Output only valid JSON"},
        {"role": "user", "content": input},
    ],
    temperature=0.5)

    text = completion.choices[0].message.content
    parsed = json.loads(text)

    return parsed


def embeddings(input: list[str]) -> list[list[str]]:
    response = client.embeddings.create(model="text-embedding-3-small", input=input)
    return [data.embedding for data in response.data]
```

## 1. 搜尋

一切從使用者的問題開始。


```python
# User asks a question
USER_QUESTION = "Who won the NBA championship? And who was the MVP? Tell me a bit about the last game."
```

為了盡可能完整，我們用模型根據這個問題產生一組多樣化的 query。


```python
QUERIES_INPUT = f"""
You have access to a search API that returns recent news articles.
Generate an array of search queries that are relevant to this question.
Use a variation of related keywords for the queries, trying to be as general as possible.
Include as many queries as you can think of, including and excluding terms.
For example, include queries like ['keyword_1 keyword_2', 'keyword_1', 'keyword_2'].
Be creative. The more queries you include, the more likely you are to find relevant results.

User question: {USER_QUESTION}

Format: {{"queries": ["query_1", "query_2", "query_3"]}}
"""

queries = json_gpt(QUERIES_INPUT)["queries"]

# Let's include the original question as well for good measure
queries.append(USER_QUESTION)

queries
```

??? note "輸出"

    ```text
    ['NBA championship winner',
     'MVP of NBA championship',
     'Last game of NBA championship',
     'NBA finals winner',
     'Most valuable player of NBA championship',
     'Finals game of NBA',
     'Who won the NBA finals',
     'NBA championship game summary',
     'NBA finals MVP',
     'Champion of NBA playoffs',
     'NBA finals last game highlights',
     'NBA championship series result',
     'NBA finals game score',
     'NBA finals game recap',
     'NBA champion team and player',
     'NBA finals statistics',
     'NBA championship final score',
     'NBA finals best player',
     'NBA playoffs champion and MVP',
     'NBA finals game analysis',
     'Who won the NBA championship? And who was the MVP? Tell me a bit about the last game.']
    ```

這些 query 看起來不錯，來執行搜尋。


```python
def search_news(
    query: str,
    news_api_key: str = news_api_key,
    num_articles: int = 50,
    from_datetime: str = "2023-06-01",  # the 2023 NBA finals were played in June 2023
    to_datetime: str = "2023-06-30",
) -> dict:
    response = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": query,
            "apiKey": news_api_key,
            "pageSize": num_articles,
            "sortBy": "relevancy",
            "from": from_datetime,
            "to": to_datetime,
        },
    )

    return response.json()


articles = []

for query in tqdm(queries):
    result = search_news(query)
    if result["status"] == "ok":
        articles = articles + result["articles"]
    else:
        raise Exception(result["message"])

# remove duplicates
articles = list({article["url"]: article for article in articles}.values())

print("Total number of articles:", len(articles))
print("Top 5 articles of query 1:", "\n")

for article in articles[0:5]:
    print("Title:", article["title"])
    print("Description:", article["description"])
    print("Content:", article["content"][0:100] + "...")
    print()
```

??? note "輸出"

    ```text
      0%|          | 0/21 [00:00<?, ?it/s]
    ```

    ```text
    Total number of articles: 554
    Top 5 articles of query 1: 

    Title: Nascar takes on Le Mans as LeBron James gets centenary race under way
    Description: <ul><li>Nascar has presence at iconic race for first time since 1976</li><li>NBA superstar LeBron James waves flag as honorary starter</li></ul>The crowd chanted “U-S-A! U-S-A!” as Nascar driver lineup for the 24 Hours of Le Mans passed through the city cente…
    Content: The crowd chanted U-S-A! U-S-A! as Nascar driver lineup for the 24 Hours of Le Mans passed through t...

    Title: NBA finals predictions: Nuggets or Heat? Our writers share their picks
    Description: Denver or Miami? Our contributors pick the winner, key players and dark horses before the NBA’s grand finale tips offA lot has been made of the importance of a balanced roster with continuity, but, somehow, still not enough. The Nuggets are the prime example …
    Content: The Nuggets are here because 
    A lot has been made of the importance of a balanced roster with conti...

    Title: Unboxing: Michelob ULTRA and Artist Futura Enshrine the NBA Championship In Custom Hand-Painted Bottles
    Description: As the 2022-2023 NBA Championship nears the end, Michelob ULTRA brings joy to sports fans who will gather to watch the showdown between the Denver Nuggets and Miami Heat. The beermaker teamed up with artist Futura to remix its newly-designed 2023 Champ Bottle…
    Content: As the 2022-2023 NBA Championship nears the end, Michelob ULTRA brings joy to sports fans who will g...

    Title: Futura and Michelob ULTRA Toast to the NBA Finals With Abstract Artwork Crafted From the Brand’s 2023 Limited-Edition Championship Bottles
    Description: The sun is out to play, and so is Michelob ULTRA. With the 2022-2023 NBA Finals underway, the beermaker is back with its celebratory NBA Champ Bottles. This year, the self-proclaimed MVP of joy is dropping a limited-edition bottle made in collaboration with a…
    Content: The sun is out to play, and so is Michelob ULTRA. With the 2022-2023 NBA Finals underway, the beerma...

    Title: Signed and Delivered, Futura and Michelob ULTRA Will Gift Hand-Painted Bottles to This Year’s NBA Championship Team
    Description: Michelob ULTRA, the MVP of joy and official beer sponsor of the NBA is back to celebrate with basketball lovers and sports fans around the globe as the NBA 2022-2023 season comes to a nail-biting close. In collaboration with artist Futura, Michelob ULTRA will…
    Content: Michelob ULTRA, the MVP of joy and official beer sponsor of the NBA is back to celebrate with basket...
    ```

可以看到，搜尋 query 常常會回傳大量結果，其中很多跟使用者原本的問題無關。為了提升最終答案的品質，我們用 embedding 對結果 re-rank 並過濾。

## 2. Re-rank

受 [HyDE (Gao et al.)](https://arxiv.org/abs/2212.10496) 啟發，我們先產生一個假設的理想答案，作為 re-rank 時比較結果的對象。這樣能優先挑出看起來像好答案的結果，而不是只跟問題相似的結果。下面是我們用來產生假設答案的 prompt。


```python
HA_INPUT = f"""
Generate a hypothetical answer to the user's question. This answer will be used to rank search results. 
Pretend you have all the information you need to answer, but don't use any actual facts. Instead, use placeholders
like NAME did something, or NAME said something at PLACE. 

User question: {USER_QUESTION}

Format: {{"hypotheticalAnswer": "hypothetical answer text"}}
"""

hypothetical_answer = json_gpt(HA_INPUT)["hypotheticalAnswer"]

hypothetical_answer
```

??? note "輸出"

    ```text
    'The NBA championship was won by TEAM NAME. The MVP was awarded to PLAYER NAME. The last game was held at STADIUM NAME, where both teams played with great energy and enthusiasm. It was a close game, but in the end, TEAM NAME emerged victorious.'
    ```

現在替搜尋結果和假設答案產生 embedding，再計算這些 embedding 之間的 cosine distance，得到語意相似度指標。注意，因為 OpenAI API 回傳的 embedding 已經正規化，我們可以直接算 dot product，不用做完整的 cosine similarity 計算。


```python
hypothetical_answer_embedding = embeddings(hypothetical_answer)[0]
article_embeddings = embeddings(
    [
        f"{article['title']} {article['description']} {article['content'][0:100]}"
        for article in articles
    ]
)

# Calculate cosine similarity
cosine_similarities = []
for article_embedding in article_embeddings:
    cosine_similarities.append(dot(hypothetical_answer_embedding, article_embedding))

cosine_similarities[0:10]
```

??? note "輸出"

    ```text
    [0.7854456526852069,
     0.8086023500072106,
     0.8002998147018501,
     0.7961229569526956,
     0.798354506673743,
     0.758216458795653,
     0.7753754083127359,
     0.7494958338411927,
     0.804733946801739,
     0.8405965885235218]
    ```

最後用這些相似度分數排序並過濾結果。


```python
scored_articles = zip(articles, cosine_similarities)

# Sort articles by cosine similarity
sorted_articles = sorted(scored_articles, key=lambda x: x[1], reverse=True)

# Print top 5 articles
print("Top 5 articles:", "\n")

for article, score in sorted_articles[0:5]:
    print("Title:", article["title"])
    print("Description:", article["description"])
    print("Content:", article["content"][0:100] + "...")
    print("Score:", score)
    print()
```

??? note "輸出"

    ```text
    Top 5 articles: 

    Title: NBA Finals: Denver Nuggets beat Miami Hea, lift thier first-ever NBA title
    Description: Denver Nuggets won their maiden NBA Championship trophy defeating Miami Heat 94-89 in Game 5 of the NBA Final held on Tuesday at the Ball Arena in Denver
    Content: Denver Nuggets won their maiden NBA Championship trophy defeating Miami Heat 94-89 in Game 5 of the ...
    Score: 0.8445817523602124

    Title: Photos: Denver Nuggets celebrate their first NBA title
    Description: The Nuggets capped off an impressive postseason by beating the Miami Heat in the NBA Finals.
    Content: Thousands of supporters watched along the streets of Denver, Colorado as the US National Basketball ...
    Score: 0.842070667753606

    Title: Denver Nuggets win first NBA championship title in Game 5 victory over Miami Heat
    Description: The Denver Nuggets won their first NBA championship Monday night, downing the Miami Heat 94-89 at Ball Arena in Denver to take Game 5 of the NBA Finals.
    Content: The Denver Nuggets won their first NBA championship Monday night, downing the Miami Heat 94-89 at Ba...
    Score: 0.8409346078172385

    Title: Denver Nuggets Capture Their First NBA Championship Behind Unbreakable Chemistry
    Description: After 47 years of waiting, the Denver Nuggets are NBA champions. Led by Nikola Jokic and Jamal Murray, they reached the mountain top by staying true to themselves.
    Content: DENVER, CO - JUNE 12: Jamal Murray (27) of the Denver Nuggets celebrates as he leaves the court ... ...
    Score: 0.8405965885235218

    Title: NBA Finals: Nikola Jokic, Denver Nuggets survive Miami Heat to secure franchise's first NBA championship
    Description: In a rock-fight of a Game 5, the Denver Nuggets reached the NBA mountaintop from the foothills of the Rockies, winning their first-ever championship and setting Nikola Jokic's legacy as an all-timer in stone.
    Content: DENVER, COLORADO - JUNE 12: Jamal Murray #27 of the Denver Nuggets reacts during the fourth quarter ...
    Score: 0.8389716330890262
    ```

太好了！這些結果跟我們原本的 query 相關多了。現在用前 5 筆結果產生最終答案。

## 3. 回答


```python
formatted_top_results = [
    {
        "title": article["title"],
        "description": article["description"],
        "url": article["url"],
    }
    for article, _score in sorted_articles[0:5]
]

ANSWER_INPUT = f"""
Generate an answer to the user's question based on the given search results. 
TOP_RESULTS: {formatted_top_results}
USER_QUESTION: {USER_QUESTION}

Include as much information as possible in the answer. Reference the relevant search result urls as markdown links.
"""

completion = client.chat.completions.create(
    model=GPT_MODEL,
    messages=[{"role": "user", "content": ANSWER_INPUT}],
    temperature=0.5,
    stream=True,
)

text = ""
for chunk in completion:
    text += chunk.choices[0].delta.content
    display.clear_output(wait=True)
    display.display(display.Markdown(text))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 重點整理
- 這是介於「GPT 自己反覆搜尋」和「全庫 embedding」之間的做法，可以疊在任何現有搜尋系統上，不用維護 vector database。
- 先讓 GPT 產生多組不同角度的 query，可以提高搜尋涵蓋面。
- HyDE 的概念是拿「假設的理想答案」當比較對象，這樣挑出的是像答案的內容，而不是像問題的內容。
- OpenAI 的 embedding 已經正規化，所以 dot product 就等於 cosine similarity，算起來更快。

## 練習
1. 把產生 query 的數量改成 3 組和 8 組，比較最終排名前 5 的結果有什麼不同。
2. 把 re-rank 的比較對象從假設答案換成原始問題本身，看排名結果和答案品質有什麼變化。
3. 把最終回答用的結果數量從 5 改成 3，並在 prompt 要求每個論點都標註來源連結，檢查模型有沒有照做。
