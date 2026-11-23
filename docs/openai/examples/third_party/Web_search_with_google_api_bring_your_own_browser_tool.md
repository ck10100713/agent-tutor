---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/third_party/Web_search_with_google_api_bring_your_own_browser_tool.ipynb
---
# 打造自帶瀏覽器（BYOB）tool：網頁搜尋與摘要

> 原文：[examples/third_party/Web_search_with_google_api_bring_your_own_browser_tool.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/Web_search_with_google_api_bring_your_own_browser_tool.ipynb)

## 這篇在做什麼

LLM 有知識截止日期，不知道之後發生的事。這篇用 Python 自己做一個「Bring Your Own Browser」的流程：用 Google Custom Search API 搜尋、抓網頁並請模型摘要，最後把整理好的資料丟給模型，用 RAG 的方式產生有最新資訊的回答。

## 學完你會

- 串 Google Custom Search API，用 `site_filter` 把搜尋限制在特定網域
- 用 query expansion 把使用者的長問題改寫成適合搜尋引擎的短詞，再抓網頁內容並請 LLM 針對搜尋意圖做摘要
- 把標題、連結、摘要整理成結構化資料，丟給模型產生附引用的 RAG 回答

## 開跑前

- Python 3.12 以上，並安裝 `requests`、`beautifulsoup4`、`openai`
- 需要 Google Custom Search API key 和 Custom Search Engine ID（CSE ID）
- 需要把 `OPENAI_API_KEY` 設成環境變數

## 打造自帶瀏覽器（BYOB）tool：網頁搜尋與摘要

**免責聲明：這份 cookbook 僅供教育用途。使用網頁搜尋和爬取技術時，請確定你遵守所有適用的法律和服務條款。這份 cookbook 會把搜尋限制在 openai.com 網域，只取得公開資訊來說明概念。**

像 GPT-4o 這樣的大型語言模型（LLM）有知識截止日期，也就是說它們不知道那之後發生的事。需要最新資料的情境，就得讓 LLM 能取得目前的網頁資訊，回答才會準確、切題。

這份指南用 Python 打造一個自帶瀏覽器（BYOB）tool 來解決這個限制。目標是做出一套系統，讓你的應用程式能提供最新的答案，包含最近的發展，例如 OpenAI 最新的產品發表。把網頁搜尋接上 LLM，模型就能根據網路上最新的資訊產生回應。

搜尋 API 你可以用任何公開的，這裡用的是 Google 的 Custom Search API。搜尋結果取得的資訊會經過處理，再傳給 LLM，透過檢索增強生成（Retrieval-Augmented Generation，RAG）產生最終回應。

**Bring Your Own Browser（BYOB）** tool 讓使用者能用程式執行網頁瀏覽的工作。在這份 notebook 裡，我們會做一個 BYOB tool，它會：

**#1. 設定搜尋引擎：** 用公開的搜尋 API（例如 Google 的 Custom Search API）執行網頁搜尋，取得相關搜尋結果的清單。  

**#2. 建立搜尋字典：** 從搜尋結果收集每個網頁的標題、URL 和摘要，建立結構化的資訊字典。  

**#3. 產生 RAG 回應：** 實作 RAG，把收集到的資訊傳給 LLM，由它產生對使用者查詢的最終回應。



### 使用情境 
這份 cookbook 的例子是：使用者想依時間順序列出 OpenAI 最近的產品發表。因為目前的 GPT-4o 模型有知識截止日期，預期它不會知道最近的產品發表，例如 2024 年 9 月推出的 o1-preview 模型。 


```python
from openai import OpenAI

client = OpenAI()

search_query = "List the latest OpenAI product launches in chronological order from latest to oldest in the past 2 years"


response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful agent."},
        {"role": "user", "content": search_query}]
).choices[0].message.content

print(response)
```

??? note "輸出"

    ```text
    OpenAI has had several notable product launches and updates in the past couple of years. Here’s a chronological list of some significant ones:

    1. **ChatGPT (November 2022)**: OpenAI launched an AI chatbot called ChatGPT, which is based on GPT-3.5. This chatbot became widely popular due to its impressive capabilities in understanding and generating human-like text.

    2. **GPT-4 (March 2023)**: OpenAI released GPT-4, the latest version of their Generative Pre-trained Transformer model. It brought improvements in both performance and accuracy over its predecessors.

    3. **DALL-E 2 (April 2022)**: The second version of DALL-E, an AI model that can generate images from textual descriptions, was launched with enhanced image resolution and more robust capabilities.

    4. **Whisper (September 2022)**: Whisper, an automatic speech recognition (ASR) system, was introduced. This model can handle multiple languages and is useful for transcribing and understanding spoken language.

    These are some of the key product launches from OpenAI in the past couple of years. Keep in mind the technology landscape is continually evolving, and new developments can occur.
    ```

因為知識截止日期的關係，模型果然不知道 OpenAI 最近的產品發表。

### 設定 BYOB tool
為了讓模型取得近期事件的資訊，我們照下面的步驟做：

##### 步驟 1：設定搜尋引擎，提供網頁搜尋結果
##### 步驟 2：建立搜尋字典，包含網頁的標題、URL 和摘要
##### 步驟 3：把資訊傳給模型，對使用者的查詢產生 RAG 回應  


開始前，先確認你有：機器上裝了 **Python 3.12 或以上**。還需要 Google Custom Search API key 和 Custom Search Engine ID（CSE ID）。需要安裝的 Python 套件有 `requests`、`beautifulsoup4`、`openai`。並確定 OPENAI_API_KEY 已經設成環境變數。

#### 步驟 1：設定搜尋引擎，提供網頁搜尋結果
這個工作可以用任何公開的網頁搜尋 API。我們用 Google 的 Custom Search API 設定一個自訂搜尋引擎。它會依使用者的查詢抓出相關網頁的清單，重點放在取得最新且最相關的結果。  

**a. 設定搜尋 API key 和函式：** 到 Google Developers Console 取得 Google API key 和 Custom Search Engine ID（CSE ID）。你可以到這個 [Programmable Search Engine Link](https://developers.google.com/custom-search/v1/overview) 設定 API key 和 Custom Search Engine ID（CSE ID）。 

下面的 `search` 函式依搜尋詞、API 和 CSE ID 的 key，以及要回傳的搜尋結果數量來進行搜尋。我們加了一個參數 `site_filter`，把輸出限制在 `openai.com`
  

```python
import requests  # For making HTTP requests to APIs and websites

def search(search_item, api_key, cse_id, search_depth=10, site_filter=None):
    service_url = 'https://www.googleapis.com/customsearch/v1'

    params = {
        'q': search_item,
        'key': api_key,
        'cx': cse_id,
        'num': search_depth
    }

    try:
        response = requests.get(service_url, params=params)
        response.raise_for_status()
        results = response.json()

        # Check if 'items' exists in the results
        if 'items' in results:
            if site_filter is not None:
                
                # Filter results to include only those with site_filter in the link
                filtered_results = [result for result in results['items'] if site_filter in result['link']]

                if filtered_results:
                    return filtered_results
                else:
                    print(f"No results with {site_filter} found.")
                    return []
            else:
                if 'items' in results:
                    return results['items']
                else:
                    print("No search results found.")
                    return []

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the search: {e}")
        return []
```

**b. 決定搜尋引擎要用的搜尋詞：** 在從第三方 API 取得特定結果之前，我們可能需要用 query expansion（查詢擴展）來決定瀏覽器搜尋 API 該檢索哪些詞。**Query expansion** 是把原本的使用者查詢加上相關詞、同義詞或變體來擴大範圍的過程。這個技巧很重要，因為搜尋引擎（例如 Google 的 Custom Search API）通常比較擅長比對一組相關的詞，而不是使用者用的自然語言 prompt。 

舉例來說，只用原始查詢 `"List the latest OpenAI product launches in chronological order from latest to oldest in the past 2 years"` 搜尋，可能比用簡短直接的詞組 `"Latest OpenAI product launches"` 得到更少、更不相關的結果。下面的程式碼會用使用者原本的 `search_query` 產生更具體的搜尋詞，拿去給 Google API 取得結果。 

```python
search_term = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Provide a google search term based on search query provided below in 3-4 words"},
        {"role": "user", "content": search_query}]
).choices[0].message.content

print(search_term)
```

??? note "輸出"

    ```text
    Latest OpenAI product launches
    ```

**c. 呼叫搜尋函式：** 現在有了搜尋詞，就呼叫搜尋函式從 Google search API 取得結果。這時候的結果只有網頁連結和一段 snippet。下一步我們會從網頁取得更多資訊並做摘要，放進字典傳給模型。

```python
from dotenv import load_dotenv
import os

load_dotenv('.env')

api_key = os.getenv('API_KEY')
cse_id = os.getenv('CSE_ID')

search_items = search(search_item=search_term, api_key=api_key, cse_id=cse_id, search_depth=10, site_filter="https://openai.com")
```

```python
for item in search_items:
    print(f"Link: {item['link']}")
    print(f"Snippet: {item['snippet']}\n")
```

??? note "輸出"

    ```text
    Link: https://openai.com/news/
    Snippet: Overview ; Product. Sep 12, 2024. Introducing OpenAI o1 ; Product. Jul 25, 2024. SearchGPT is a prototype of new AI search features ; Research. Jul 18, 2024. GPT- ...

    Link: https://openai.com/index/new-models-and-developer-products-announced-at-devday/
    Snippet: Nov 6, 2023 ... GPT-4 Turbo with 128K context · We released the first version of GPT-4 in March and made GPT-4 generally available to all developers in July.

    Link: https://openai.com/news/product/
    Snippet: Discover the latest product advancements from OpenAI and the ways they're being used by individuals and businesses.

    Link: https://openai.com/
    Snippet: A new series of AI models designed to spend more time thinking before they respond. Learn more · (opens in a new window) ...

    Link: https://openai.com/index/sora/
    Snippet: Feb 15, 2024 ... We plan to include C2PA metadata(opens in a new window) in the future if we deploy the model in an OpenAI product. In addition to us developing ...

    Link: https://openai.com/o1/
    Snippet: We've developed a new series of AI models designed to spend more time thinking before they respond. Here is the latest news on o1 research, product and ...

    Link: https://openai.com/index/introducing-gpts/
    Snippet: Nov 6, 2023 ... We plan to offer GPTs to more users soon. Learn more about our OpenAI DevDay announcements for new models and developer products.

    Link: https://openai.com/api/
    Snippet: The most powerful platform for building AI products ... Build and scale AI experiences powered by industry-leading models and tools. Start building (opens in a ...
    ```

#### 步驟 2：建立搜尋字典，包含網頁的標題、URL 和摘要
取得搜尋結果後，我們要擷取並整理相關資訊，好傳給 LLM 產生最終輸出。 

**a. 爬取網頁內容：** 對搜尋結果裡的每個 URL，抓取網頁並擷取文字內容，同時濾掉腳本和廣告這類不相關的資料，做法見 `retrieve_content` 函式。 

**b. 摘要內容：** 用 LLM 對爬到的內容產生精簡的摘要，重點放在跟使用者查詢相關的資訊。可以把原始搜尋文字提供給模型，讓它針對搜尋意圖做摘要，做法見 `summarize_content` 函式。 
  
**c. 建立結構化字典：** 把資料整理成字典或 DataFrame，包含每個網頁的標題、連結和摘要。這個結構可以傳給 LLM，產生附適當引用的摘要。    


```python
import requests
from bs4 import BeautifulSoup

TRUNCATE_SCRAPED_TEXT = 50000  # Adjust based on your model's context window
SEARCH_DEPTH = 5

def retrieve_content(url, max_tokens=TRUNCATE_SCRAPED_TEXT):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            for script_or_style in soup(['script', 'style']):
                script_or_style.decompose()

            text = soup.get_text(separator=' ', strip=True)
            characters = max_tokens * 4  # Approximate conversion
            text = text[:characters]
            return text
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve {url}: {e}")
            return None
        
def summarize_content(content, search_term, character_limit=500):
        prompt = (
            f"You are an AI assistant tasked with summarizing content relevant to '{search_term}'. "
            f"Please provide a concise summary in {character_limit} characters or less."
        )
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content}]
            )
            summary = response.choices[0].message.content
            return summary
        except Exception as e:
            print(f"An error occurred during summarization: {e}")
            return None

def get_search_results(search_items, character_limit=500):
    # Generate a summary of search results for the given search term
    results_list = []
    for idx, item in enumerate(search_items, start=1):
        url = item.get('link')
        
        snippet = item.get('snippet', '')
        web_content = retrieve_content(url, TRUNCATE_SCRAPED_TEXT)
        
        if web_content is None:
            print(f"Error: skipped URL: {url}")
        else:
            summary = summarize_content(web_content, search_term, character_limit)
            result_dict = {
                'order': idx,
                'link': url,
                'title': snippet,
                'Summary': summary
            }
            results_list.append(result_dict)
    return results_list
```

```python
results = get_search_results(search_items)

for result in results:
    print(f"Search order: {result['order']}")
    print(f"Link: {result['link']}")
    print(f"Snippet: {result['title']}")
    print(f"Summary: {result['Summary']}")
    print('-' * 80)
```

??? note "輸出"

    ```text
    Search order: 1
    Link: https://openai.com/news/
    Snippet: Overview ; Product. Sep 12, 2024. Introducing OpenAI o1 ; Product. Jul 25, 2024. SearchGPT is a prototype of new AI search features ; Research. Jul 18, 2024. GPT- ...
    Summary: OpenAI recently launched several notable products in 2024, including OpenAI o1 and SearchGPT, a prototype for enhanced AI search capabilities. Additionally, GPT-4o mini was introduced, enhancing cost-efficient intelligence. The organization also rolled out OpenAI for Nonprofits and ChatGPT Edu to support various sectors. Improvements in data analysis within ChatGPT and enhancements to the fine-tuning API were also announced. These updates reflect OpenAI's ongoing commitment to advancing AI technologies across different fields.
    --------------------------------------------------------------------------------
    Search order: 2
    Link: https://openai.com/index/new-models-and-developer-products-announced-at-devday/
    Snippet: Nov 6, 2023 ... GPT-4 Turbo with 128K context · We released the first version of GPT-4 in March and made GPT-4 generally available to all developers in July.
    Summary: OpenAI's recent DevDay revealed several new products and model updates, including the launch of GPT-4 Turbo with a 128K context window, new pricing, and enhanced multimodal capabilities. Key features include the new Assistants API for developing specialized AI applications, improved function calling, and advanced capabilities like text-to-speech and DALL·E 3 integration. Additionally, OpenAI introduced a Copyright Shield for legal protection and Whisper v3 for improved speech recognition. Pricing reductions and rate limit increases were also announced across several models.
    --------------------------------------------------------------------------------
    Search order: 3
    Link: https://openai.com/news/product/
    Snippet: Discover the latest product advancements from OpenAI and the ways they're being used by individuals and businesses.
    Summary: As of September 2024, OpenAI has launched several significant products, including OpenAI o1, a versatile AI tool, and SearchGPT, a prototype aimed at enhancing AI-driven search capabilities. Earlier, in May 2024, they introduced OpenAI for Education, emphasizing AI's integration into educational settings. Upcoming enhancements to existing products like GPT-4, DALL·E 3, and ChatGPT are also in focus, continuing OpenAI's mission to innovate across various sectors with cutting-edge AI technologies.
    --------------------------------------------------------------------------------
    Search order: 4
    Link: https://openai.com/
    Snippet: A new series of AI models designed to spend more time thinking before they respond. Learn more · (opens in a new window) ...
    Summary: OpenAI has recently launched several innovative products, including the OpenAI o1 and o1-mini models which focus on enhanced reasoning capabilities. The partnership with Apple aims to integrate ChatGPT into Apple’s user experience. OpenAI also debuted "Sora," a video generation tool from text prompts, and made significant upgrades to the ChatGPT Enterprise with new compliance tools. The introduction of structured outputs in the API and enhanced data analysis features are also notable advancements, further expanding the utility of AI in various domains.
    --------------------------------------------------------------------------------
    Search order: 5
    Link: https://openai.com/index/sora/
    Snippet: Feb 15, 2024 ... We plan to include C2PA metadata(opens in a new window) in the future if we deploy the model in an OpenAI product. In addition to us developing ...
    Summary: OpenAI has launched Sora, an innovative AI model capable of generating high-quality text-to-video content. Sora can create videos up to one minute long, simulating complex scenes with motion and character interactions based on user prompts. The model uses advanced diffusion techniques, akin to its predecessors in the GPT and DALL·E families, enabling it to understand and animate real-world physics and nuances. OpenAI is working with external artists and domain experts to ensure safety and accuracy, while gathering feedback for future enhancements before wider release.
    --------------------------------------------------------------------------------
    Search order: 6
    Link: https://openai.com/o1/
    Snippet: We've developed a new series of AI models designed to spend more time thinking before they respond. Here is the latest news on o1 research, product and ...
    Summary: OpenAI has introduced the o1 series, a new set of AI models aimed at improving response deliberation. This innovation allows models to "think" more before generating replies. The o1 models can be accessed via ChatGPT Plus and through APIs. Other recent advancements include updates to GPT-4, GPT-4o mini, and DALL·E 3. OpenAI continues to focus on enhancing product offerings for individual, team, and enterprise use, reflecting its commitment to research and safety in AI technologies.
    --------------------------------------------------------------------------------
    Search order: 7
    Link: https://openai.com/index/introducing-gpts/
    Snippet: Nov 6, 2023 ... We plan to offer GPTs to more users soon. Learn more about our OpenAI DevDay announcements for new models and developer products.
    Summary: On November 6, 2023, OpenAI launched "GPTs," allowing users to create customized versions of ChatGPT tailored to specific tasks without needing coding skills. These custom GPTs can assist in various activities, from learning games to workplace tasks. The upcoming GPT Store will feature creations from users, making them searchable and shareable. Enterprise users can develop internal-only versions, enhancing workplace productivity. Additionally, ChatGPT Plus users benefit from an improved interface that consolidates features like DALL·E and data analysis.
    --------------------------------------------------------------------------------
    Search order: 8
    Link: https://openai.com/api/
    Snippet: The most powerful platform for building AI products ... Build and scale AI experiences powered by industry-leading models and tools. Start building (opens in a ...
    Summary: OpenAI has launched several notable products, including GPT-4o and GPT-4o mini, designed for complex and lightweight tasks respectively, both featuring a 128k context length. New models like OpenAI o1-preview and o1-mini enhance reasoning capabilities. The API platform offers various tools for building AI applications, including Chat Completions, Assistants, and Batch APIs. Enhanced customization options include Fine-tuning and a Custom Model Program. OpenAI's enterprise features emphasize security, compliance, and dedicated support, facilitating widespread innovative applications across sectors.
    --------------------------------------------------------------------------------
    ```

我們取得了最新的結果。（注意：結果會依你執行腳本的時間而不同。） 

#### 步驟 3：把資訊傳給模型，對使用者的查詢產生 RAG 回應
搜尋資料整理成 JSON 資料結構後，我們把它和原本的使用者查詢一起傳給 LLM，產生最終回應。這時候 LLM 的回應就包含超出它原始知識截止日期的資訊，提供最新的內容。

```python
import json 

final_prompt = (
    f"The user will provide a dictionary of search results in JSON format for search query {search_term} Based on on the search results provided by the user, provide a detailed response to this query: **'{search_query}'**. Make sure to cite all the sources at the end of your answer."
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": final_prompt},
        {"role": "user", "content": json.dumps(results)}],
    temperature=0

)
summary = response.choices[0].message.content

print(summary)
```

??? note "輸出"

    ```text
    Based on the search results provided, here is a chronological list of the latest OpenAI product launches from the past two years, ordered from the most recent to the oldest:

    1. **September 12, 2024**: **OpenAI o1**
       - A versatile AI tool designed to enhance reasoning capabilities.
       - Source: [OpenAI News](https://openai.com/news/)

    2. **July 25, 2024**: **SearchGPT**
       - A prototype aimed at enhancing AI-driven search capabilities.
       - Source: [OpenAI News](https://openai.com/news/)

    3. **July 18, 2024**: **GPT-4o mini**
       - A cost-efficient intelligence model.
       - Source: [OpenAI News](https://openai.com/news/)

    4. **May 2024**: **OpenAI for Education**
       - Focuses on integrating AI into educational settings.
       - Source: [OpenAI News](https://openai.com/news/product/)

    5. **February 15, 2024**: **Sora**
       - An AI model capable of generating high-quality text-to-video content.
       - Source: [OpenAI Sora](https://openai.com/index/sora/)

    6. **November 6, 2023**: **GPT-4 Turbo**
       - Features a 128K context window and enhanced multimodal capabilities.
       - Source: [OpenAI DevDay](https://openai.com/index/new-models-and-developer-products-announced-at-devday/)

    7. **November 6, 2023**: **GPTs**
       - Allows users to create customized versions of ChatGPT tailored to specific tasks.
       - Source: [OpenAI DevDay](https://openai.com/index/introducing-gpts/)

    8. **March 2023**: **GPT-4**
       - The first version of GPT-4 was released.
       - Source: [OpenAI DevDay](https://openai.com/index/new-models-and-developer-products-announced-at-devday/)

    9. **July 2023**: **GPT-4 General Availability**
       - GPT-4 was made generally available to all developers.
       - Source: [OpenAI DevDay](https://openai.com/index/new-models-and-developer-products-announced-at-devday/)

    10. **2023**: **Whisper v3**
        - An improved speech recognition model.
    ... (省略 48 行)
    ```

### 結論
 
大型語言模型（LLM）有知識截止日期，可能不知道最近發生的事。要提供它們最新的資訊，你可以用 Python 打造自帶瀏覽器（BYOB）tool。這個 tool 會取得目前的網頁資料並餵給 LLM，讓它能給出最新的回應。

整個流程有三個主要步驟：

**#1 設定搜尋引擎：** 用公開的搜尋 API（像 Google 的 Custom Search API）執行網頁搜尋，取得相關搜尋結果的清單。  

**#2 建立搜尋字典：** 從搜尋結果收集每個網頁的標題、URL 和摘要，建立結構化的資訊字典。  

**#3. 產生 RAG 回應：** 實作 RAG，把收集到的資訊傳給 LLM，由它產生對使用者查詢的最終回應。

照著這些步驟做，你就能讓 LLM 在你的應用程式裡提供最新的答案，包含最近的發展，例如 OpenAI 最新的產品發表。

## 重點整理

- LLM 有知識截止日期，需要最新資訊時得自己接搜尋，再把結果當上下文餵給模型。
- 流程是搜尋、抓網頁並摘要、整理成結構化資料、交給模型做 RAG 回答。
- 使用者的自然語言問題常常不適合直接拿去搜尋，先做 query expansion 改成簡短的搜尋詞，結果通常比較好。
- 摘要時把原始搜尋意圖也給模型，摘要會更聚焦；整理成含標題與連結的結構，回答才能附引用。

## 練習

1. 把 `search` 的 `site_filter` 換成另一個你想查的網域，看看回答有什麼變化。
2. 改掉 query expansion 的 prompt，比較直接用原始長問題搜尋和用擴展後的短詞，回來的結果有什麼差別。
3. 在搜尋字典裡多加一個欄位（例如抓取時間），並修改最後的 prompt，要求模型依這個欄位排序並附上引用。
