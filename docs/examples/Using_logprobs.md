---
translated: true
source: examples/Using_logprobs.ipynb
---
# 使用 logprobs

> 原文：[examples/Using_logprobs.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Using_logprobs.ipynb)



## 這篇在做什麼
示範 Chat Completions API 的 `logprobs` 參數。開啟後 API 會回傳每個輸出 token 的對數機率，你可以用它量模型有多有把握，拿來做分類、檢索問答的自我評估、autocomplete 等應用。

## 學完你會
- 開啟 `logprobs` 和 `top_logprobs`，把 log probability 轉成 0 到 100% 的信心分數，替分類器設定門檻。
- 用 `has_sufficient_context_for_answer` 這類布林欄位的機率，替 RAG 問答做自我評估，並用 `bytes` 欄位重組 token 和算 joint probability。
- 算出 perplexity，比較不同 prompt 輸出的信心高低。

## 開跑前
需要設好環境變數 `OPENAI_API_KEY`。範例使用 `gpt-4o-mini`，會產生少量 API 費用。


這個 notebook 示範 Chat Completions API 的 `logprobs` 參數。開啟 `logprobs` 後，API 會回傳每個輸出 token 的 log probability，同時附上每個 token 位置上最有可能的幾個 token 和它們的 log probability。相關的請求參數有：
* `logprobs`：是否回傳輸出 token 的 log probability。設為 `true` 的話，回應會在訊息內容中包含每個 token 的 log probability。
* `top_logprobs`：0 到 5 之間的整數，指定每個 token 位置要回傳幾個最有可能的 token，每個都附上 log probability。使用這個參數時，`logprobs` 必須設為 `true`。

輸出 token 的 log probability 代表這個 token 在前面內容的條件下出現的可能性。簡單講，logprob 就是 `log(p)`，其中 `p` 是某個 token 在特定位置、根據前面的 context 出現的機率。關於 `logprobs` 的幾個重點：
* log probability 越高，代表這個 token 在該 context 下越有可能出現。你可以藉此判斷模型對輸出的信心，或看看模型考慮過哪些其他回答。
* logprob 可以是任何負數或 `0.0`，`0.0` 對應 100% 的機率。
* 把一個序列裡每個 token 的 logprob 加起來，就是整個序列的 joint log probability，取指數後就是 joint probability。這可以用來替模型輸出打分數和排序。另一種常見做法是取一個句子每個 token logprob 的平均，來挑最好的生成結果。
* 看不同候選 token 的 `logprobs`，可以了解模型覺得哪些選項合理、哪些不合理。

`logprobs` 的用途很廣，這個 notebook 聚焦在：

1. **分類任務：** 大型語言模型很擅長很多分類任務，但要準確量測模型對輸出的信心不容易。`logprobs` 提供每個類別預測對應的機率，讓你可以設定分類或信心門檻。
2. **檢索（Q&A）評估：** `logprobs` 可以幫檢索應用做自我評估。在 Q&A 範例裡，模型會輸出一個人為設計的布林值 `has_sufficient_context_for_answer`，當作「答案是否包含在檢索內容裡」的信心分數。這類評估可以減少檢索式應用的 hallucination，提高準確度。
3. **Autocomplete：** `logprobs` 可以幫我們決定使用者打字時，什麼時候該建議下一個字。
4. **Token highlighting 與輸出 bytes：** 開啟 `logprobs` 就有內建的 tokenization，可以拿來做 token highlighter。`bytes` 欄位還包含每個輸出 token 的 UTF-8 byte 值，對重現 emoji 和特殊字元特別有用。
5. **計算 perplexity：** `logprobs` 可以幫我們評估模型對整個結果的信心，並比較不同 prompt 結果的信心。

## 0. Import 與工具函式

執行這個 notebook 前，請先設定 `OPENAI_API_KEY` 環境變數。

```python
from openai import OpenAI
from math import exp
import numpy as np
from IPython.display import display, HTML
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

```python
def get_completion(
    messages: list[dict[str, str]],
    model: str = "gpt-4",
    max_tokens=500,
    temperature=0,
    stop=None,
    seed=123,
    tools=None,
    logprobs=None,  # whether to return log probabilities of the output tokens or not. If true, returns the log probabilities of each output token returned in the content of message..
    top_logprobs=None,
) -> str:
    params = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stop": stop,
        "seed": seed,
        "logprobs": logprobs,
        "top_logprobs": top_logprobs,
    }
    if tools:
        params["tools"] = tools

    completion = client.chat.completions.create(**params)
    return completion
```

## 1. 用 `logprobs` 評估分類任務的信心

假設我們要做一個系統，把新聞文章分到幾個預先定義的類別。沒有 `logprobs` 的話，也可以用 Chat Completions 做到，但要評估模型分類時有多確定就困難多了。

開啟 `logprobs` 後，我們可以看到模型對預測有多有把握，這對做出準確又可信的分類器很重要。例如，選出的類別 log probability 很高，代表模型很有信心；很低就代表信心不足。這在分類結果不如預期，或模型輸出需要人工審查驗證時特別有用。

我們先從一個 prompt 開始，裡面給模型四個類別：**Technology、Politics、Sports 和 Arts**。模型要只根據標題，把文章分到這些類別。

```python
CLASSIFICATION_PROMPT = """You will be given a headline of a news article.
Classify the article into one of the following categories: Technology, Politics, Sports, and Art.
Return only the name of the category, and nothing else.
MAKE SURE your output is one of the four categories stated.
Article headline: {headline}"""
```

看三個範例標題，先用一般的 Chat Completions 輸出，不開 `logprobs`

```python
headlines = [
    "Tech Giant Unveils Latest Smartphone Model with Advanced Photo-Editing Features.",
    "Local Mayor Launches Initiative to Enhance Urban Public Transport.",
    "Tennis Champion Showcases Hidden Talents in Symphony Orchestra Debut",
]
```

```python
for headline in headlines:
    print(f"\nHeadline: {headline}")
    API_RESPONSE = get_completion(
        [{"role": "user", "content": CLASSIFICATION_PROMPT.format(headline=headline)}],
        model="gpt-4o",
    )
    print(f"Category: {API_RESPONSE.choices[0].message.content}\n")
```

??? note "輸出"

    ```text

    Headline: Tech Giant Unveils Latest Smartphone Model with Advanced Photo-Editing Features.
    Category: Technology


    Headline: Local Mayor Launches Initiative to Enhance Urban Public Transport.
    Category: Politics


    Headline: Tennis Champion Showcases Hidden Talents in Symphony Orchestra Debut
    Category: Art
    ```

這裡可以看到每個標題選出的類別，但看不出模型對預測有多有信心。我們用同一個 prompt，開啟 `logprobs` 並把 `top_logprobs` 設為 2 再跑一次，這樣每個位置會顯示最有可能的兩個輸出 token。我們也可以把每個 log probability 轉成比較好懂的 0 到 100% 線性機率。

```python
for headline in headlines:
    print(f"\nHeadline: {headline}")
    API_RESPONSE = get_completion(
        [{"role": "user", "content": CLASSIFICATION_PROMPT.format(headline=headline)}],
        model="gpt-4o-mini",
        logprobs=True,
        top_logprobs=2,
    )
    top_two_logprobs = API_RESPONSE.choices[0].logprobs.content[0].top_logprobs
    html_content = ""
    for i, logprob in enumerate(top_two_logprobs, start=1):
        html_content += (
            f"<span style='color: cyan'>Output token {i}:</span> {logprob.token}, "
            f"<span style='color: darkorange'>logprobs:</span> {logprob.logprob}, "
            f"<span style='color: magenta'>linear probability:</span> {np.round(np.exp(logprob.logprob)*100,2)}%<br>"
        )
    display(HTML(html_content))
    print("\n")
```

??? note "輸出"

    ```text

    Headline: Tech Giant Unveils Latest Smartphone Model with Advanced Photo-Editing Features.
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text



    Headline: Local Mayor Launches Initiative to Enhance Urban Public Transport.
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text



    Headline: Tennis Champion Showcases Hidden Talents in Symphony Orchestra Debut
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

跟前兩個標題的預期一樣，gpt-4o-mini 對分類有 100% 的信心，因為內容分別明顯偏向科技和政治。第三個標題同時結合了運動和藝術的主題，信心稍微降到 97%，但仍然很確定。

`logprobs` 對分類任務很有用。你可以設定信心門檻，或在選出的輸出 log probability 不夠高時輸出多個候選 token。例如做文章標籤的推薦引擎時，可以自動分類超過某個門檻的標題，把比較不確定的送去人工審查。

## 2. 用檢索信心分數減少 hallucination

為了減少 hallucination、改善 RAG 式的 Q&A 系統，我們可以用 `logprobs` 評估模型是否認為檢索到的 context 足夠。

假設我們用 RAG 做了一個 Q&A 的檢索系統，但被答案 hallucination 的問題困擾。*注意：*這個範例用寫死的文章，其他 RAG 做 Q&A 的教學請看 cookbook 的其他篇。

```python
# Article retrieved
ada_lovelace_article = """Augusta Ada King, Countess of Lovelace (née Byron; 10 December 1815 – 27 November 1852) was an English mathematician and writer, chiefly known for her work on Charles Babbage's proposed mechanical general-purpose computer, the Analytical Engine. She was the first to recognise that the machine had applications beyond pure calculation.
Ada Byron was the only legitimate child of poet Lord Byron and reformer Lady Byron. All Lovelace's half-siblings, Lord Byron's other children, were born out of wedlock to other women. Byron separated from his wife a month after Ada was born and left England forever. He died in Greece when Ada was eight. Her mother was anxious about her upbringing and promoted Ada's interest in mathematics and logic in an effort to prevent her from developing her father's perceived insanity. Despite this, Ada remained interested in him, naming her two sons Byron and Gordon. Upon her death, she was buried next to him at her request. Although often ill in her childhood, Ada pursued her studies assiduously. She married William King in 1835. King was made Earl of Lovelace in 1838, Ada thereby becoming Countess of Lovelace.
Her educational and social exploits brought her into contact with scientists such as Andrew Crosse, Charles Babbage, Sir David Brewster, Charles Wheatstone, Michael Faraday, and the author Charles Dickens, contacts which she used to further her education. Ada described her approach as "poetical science" and herself as an "Analyst (& Metaphysician)".
When she was eighteen, her mathematical talents led her to a long working relationship and friendship with fellow British mathematician Charles Babbage, who is known as "the father of computers". She was in particular interested in Babbage's work on the Analytical Engine. Lovelace first met him in June 1833, through their mutual friend, and her private tutor, Mary Somerville.
Between 1842 and 1843, Ada translated an article by the military engineer Luigi Menabrea (later Prime Minister of Italy) about the Analytical Engine, supplementing it with an elaborate set of seven notes, simply called "Notes".
Lovelace's notes are important in the early history of computers, especially since the seventh one contained what many consider to be the first computer program—that is, an algorithm designed to be carried out by a machine. Other historians reject this perspective and point out that Babbage's personal notes from the years 1836/1837 contain the first programs for the engine. She also developed a vision of the capability of computers to go beyond mere calculating or number-crunching, while many others, including Babbage himself, focused only on those capabilities. Her mindset of "poetical science" led her to ask questions about the Analytical Engine (as shown in her notes) examining how individuals and society relate to technology as a collaborative tool.
"""

# Questions that can be easily answered given the article
easy_questions = [
    "What nationality was Ada Lovelace?",
    "What was an important finding from Lovelace's seventh note?",
]

# Questions that are not fully covered in the article
medium_questions = [
    "Did Lovelace collaborate with Charles Dickens",
    "What concepts did Lovelace build with Charles Babbage",
]
```

現在可以請模型評估提供的 context 對某個問題夠不夠。具體來說，我們請模型輸出一個布林值 `has_sufficient_context_for_answer`，再用 `logprobs` 看模型對這個判斷有多有把握。

```python
PROMPT = """You retrieved this article: {article}. The question is: {question}.
Before even answering the question, consider whether you have sufficient information in the article to answer the question fully.
Your output should JUST be the boolean true or false, of if you have sufficient information in the article to answer the question.
Respond with just one word, the boolean true or false. You must output the word 'True', or the word 'False', nothing else.
"""
```

```python
html_output = ""
html_output += "Questions clearly answered in article"

for question in easy_questions:
    API_RESPONSE = get_completion(
        [
            {
                "role": "user",
                "content": PROMPT.format(
                    article=ada_lovelace_article, question=question
                ),
            }
        ],
        model="gpt-4o-mini",
        logprobs=True,
    )
    html_output += f'<p style="color:green">Question: {question}</p>'
    for logprob in API_RESPONSE.choices[0].logprobs.content:
        html_output += f'<p style="color:cyan">has_sufficient_context_for_answer: {logprob.token}, <span style="color:darkorange">logprobs: {logprob.logprob}, <span style="color:magenta">linear probability: {np.round(np.exp(logprob.logprob)*100,2)}%</span></p>'

html_output += "Questions only partially covered in the article"

for question in medium_questions:
    API_RESPONSE = get_completion(
        [
            {
                "role": "user",
                "content": PROMPT.format(
                    article=ada_lovelace_article, question=question
                ),
            }
        ],
        model="gpt-4o",
        logprobs=True,
        top_logprobs=3,
    )
    html_output += f'<p style="color:green">Question: {question}</p>'
    for logprob in API_RESPONSE.choices[0].logprobs.content:
        html_output += f'<p style="color:cyan">has_sufficient_context_for_answer: {logprob.token}, <span style="color:darkorange">logprobs: {logprob.logprob}, <span style="color:magenta">linear probability: {np.round(np.exp(logprob.logprob)*100,2)}%</span></p>'

display(HTML(html_output))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

前兩個問題，模型以接近 100% 的信心回傳 `True`，表示文章的 context 足夠。

對於只涵蓋一部分的問題，模型也非常有把握：Charles Dickens 的問題以 99.14% 的機率回傳 `False`，Charles Babbage 的問題以 99.59% 的機率回傳 `True`。這說明信心代表的是分類的確定程度，不代表分類本身正確。

這種自我評估可以當作 guardrail，但在用它來限制回答或要求補充問題之前，請先用針對任務設計的 eval 驗證它的分類和門檻。相關做法的例子可以參考 [How we cut the rate of GPT hallucinations](https://jfan001.medium.com/how-we-cut-the-rate-of-gpt-hallucinations-from-20-to-less-than-2-f3bfcc10e4ec)。

## 3. Autocomplete

`logprobs` 的另一個用途是 autocomplete。不必做出完整的 autocomplete 系統，我們來示範 `logprobs` 怎麼幫忙決定使用者打字時什麼時候該建議字詞。

先想一個範例句子：`"My least favorite TV show is Breaking Bad."`。假設我們希望在打字時動態推薦下一個字或 token，但*只有*在模型很確定下一個字是什麼的時候才推薦。為了示範，我們把句子拆成一段一段的前綴。

```python
sentence_list = [
    "My",
    "My least",
    "My least favorite",
    "My least favorite TV",
    "My least favorite TV show",
    "My least favorite TV show is",
    "My least favorite TV show is Breaking Bad",
]
```

現在可以請 `gpt-4o-mini` 扮演 autocomplete 引擎，根據拿到的 context 來補字。我們開啟 `logprobs`，就能看到模型對預測有多有信心。

```python
high_prob_completions = {}
low_prob_completions = {}
html_output = ""

for sentence in sentence_list:
    PROMPT = """Complete this sentence. You are acting as auto-complete. Simply complete the sentence to the best of your ability, make sure it is just ONE sentence: {sentence}"""
    API_RESPONSE = get_completion(
        [{"role": "user", "content": PROMPT.format(sentence=sentence)}],
        model="gpt-4o-mini",
        logprobs=True,
        top_logprobs=3,
    )
    html_output += f'<p>Sentence: {sentence}</p>'
    first_token = True
    for token in API_RESPONSE.choices[0].logprobs.content[0].top_logprobs:
        html_output += f'<p style="color:cyan">Predicted next token: {token.token}, <span style="color:darkorange">logprobs: {token.logprob}, <span style="color:magenta">linear probability: {np.round(np.exp(token.logprob)*100,2)}%</span></p>'
        if first_token:
            if np.exp(token.logprob) > 0.95:
                high_prob_completions[sentence] = token.token
            if np.exp(token.logprob) < 0.60:
                low_prob_completions[sentence] = token.token
        first_token = False
    html_output += "<br>"

display(HTML(html_output))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

先看高信心的 autocomplete：

```python
high_prob_completions
```

??? note "輸出"

    ```text
    {'My least favorite TV show is Breaking Bad': 'because'}
    ```

看起來都很合理！這些建議可以放心用。寫完 'My least favorite TV' 後，接 'show' 的機率非常高！再來看模型比較沒把握的建議：

```python
low_prob_completions
```

??? note "輸出"

    ```text
    {'My least favorite TV': 'show', 'My least favorite TV show': 'is'}
    ```

這些也合乎邏輯。只有 'my least favorite' 這個前綴，很難知道使用者接下來要寫什麼，而作者最喜歡的電視節目是什麼，更是沒人猜得準。<br><br>
所以，用 `gpt-4o-mini` 加上 `logprobs`，我們就能做出動態 autocomplete 引擎的雛形！

## 4. Highlighter 與 bytes 參數

我們用 `logprobs` 做一個簡單的 token highlighter，並用到 `bytes` 欄位。先寫一個函式，計算並標示每個 token。這個函式沒用到 log probability，只用到開啟 `logprobs` 後內建的 tokenization。

```python
PROMPT = """What's the longest word in the English language?"""

API_RESPONSE = get_completion(
    [{"role": "user", "content": PROMPT}], model="gpt-4o", logprobs=True, top_logprobs=5
)


def highlight_text(api_response):
    colors = [
        "#FF00FF",  # Magenta
        "#008000",  # Green
        "#FF8C00",  # Dark Orange
        "#FF0000",  # Red
        "#0000FF",  # Blue
    ]
    tokens = api_response.choices[0].logprobs.content

    color_idx = 0  # Initialize color index
    html_output = ""  # Initialize HTML output
    for t in tokens:
        token_str = bytes(t.bytes).decode("utf-8")  # Decode bytes to string

        # Add colored token to HTML output
        html_output += f"<span style='color: {colors[color_idx]}'>{token_str}</span>"

        # Move to the next color
        color_idx = (color_idx + 1) % len(colors)
    display(HTML(html_output))  # Display HTML output
    print(f"Total number of tokens: {len(tokens)}")
```

```python
highlight_text(API_RESPONSE)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Total number of tokens: 95
    ```

接著用 `bytes` 欄位重組句子。開啟 `logprobs` 後，回應會包含每個 token 和它文字的 UTF-8 byte 值。當 token 含有 emoji 或其他特殊字元時，這些 byte 值很有幫助。

```python
PROMPT = """Output the blue heart emoji and its name."""
API_RESPONSE = get_completion(
    [{"role": "user", "content": PROMPT}], model="gpt-4o", logprobs=True
)

aggregated_bytes = []
joint_logprob = 0.0

# Iterate over tokens, aggregate bytes and calculate joint logprob
for token in API_RESPONSE.choices[0].logprobs.content:
    print("Token:", token.token)
    print("Log prob:", token.logprob)
    print("Linear prob:", np.round(exp(token.logprob) * 100, 2), "%")
    print("Bytes:", token.bytes, "\n")
    aggregated_bytes += token.bytes
    joint_logprob += token.logprob

# Decode the aggregated bytes to text
aggregated_text = bytes(aggregated_bytes).decode("utf-8")

# Assert that the decoded text is the same as the message content
assert API_RESPONSE.choices[0].message.content == aggregated_text

# Print the results
print("Bytes array:", aggregated_bytes)
print(f"Decoded bytes: {aggregated_text}")
print("Joint prob:", np.round(exp(joint_logprob) * 100, 2), "%")
```

??? note "輸出"

    ```text
    Token: Here
    Log prob: -0.054242473
    Linear prob: 94.72 %
    Bytes: [72, 101, 114, 101] 

    Token:  is
    Log prob: -0.0044352207
    Linear prob: 99.56 %
    Bytes: [32, 105, 115] 

    Token:  the
    Log prob: -2.1008714e-06
    Linear prob: 100.0 %
    Bytes: [32, 116, 104, 101] 

    Token:  blue
    Log prob: -0.0013290489
    Linear prob: 99.87 %
    Bytes: [32, 98, 108, 117, 101] 

    Token:  heart
    Log prob: 0.0
    Linear prob: 100.0 %
    Bytes: [32, 104, 101, 97, 114, 116] 

    Token:  emoji
    Log prob: 0.0
    Linear prob: 100.0 %
    Bytes: [32, 101, 109, 111, 106, 105] 

    Token:  and
    Log prob: -0.038287632
    Linear prob: 96.24 %
    Bytes: [32, 97, 110, 100] 

    Token:  its
    Log prob: 0.0
    Linear prob: 100.0 %
    Bytes: [32, 105, 116, 115] 

    ... (省略 37 行)
    ```

這裡 emoji 被拆成兩個 token，它們的 byte 值合起來才是它的 UTF-8 序列。把所有 token 的 bytes 加進一個陣列，就能把陣列解碼成完整的句子，並 assert 它跟 completion 訊息一致。

我們也可以把每個 token 的 log probability 加總再取指數，算出這個 completion 的 joint probability，代表在這個 prompt 下整段 completion 出現的可能性。因為這個 prompt 很明確（要求特定的 emoji 和它的名稱），joint probability 很高。限制比較少的 prompt 可能得到比較低的 joint probability，這在 prompt engineering 時可以當作有用的訊號。

## 5. 計算 perplexity

想評估模型對結果的信心時，可以算 perplexity，它是不確定性的指標。perplexity 的算法是把 logprobs 平均後取負號再取指數。一般來說，perplexity 越高，結果越不確定；越低，結果越有信心。所以 perplexity 既能評估單次模型執行的結果，也能比較不同次執行結果的相對信心。高信心不保證結果正確，但它是個有用的訊號，可以搭配其他評估指標，更了解 prompt 的行為。

例如，我想用 `gpt-4o-mini` 多了解人工智慧。我可以問一個關於近代歷史的問題，和一個關於未來的問題：

```python
prompts = [
    "In a short sentence, has artifical intelligence grown in the last decade?",
    "In a short sentence, what are your thoughts on the future of artificial intelligence?",
]

for prompt in prompts:
    API_RESPONSE = get_completion(
        [{"role": "user", "content": prompt}],
        model="gpt-4o-mini",
        logprobs=True,
    )

    logprobs = [token.logprob for token in API_RESPONSE.choices[0].logprobs.content]
    response_text = API_RESPONSE.choices[0].message.content
    response_text_tokens = [token.token for token in API_RESPONSE.choices[0].logprobs.content]
    max_starter_length = max(len(s) for s in ["Prompt:", "Response:", "Tokens:", "Logprobs:", "Perplexity:"])
    max_token_length = max(len(s) for s in response_text_tokens)
    

    formatted_response_tokens = [s.rjust(max_token_length) for s in response_text_tokens]
    formatted_lps = [f"{lp:.2f}".rjust(max_token_length) for lp in logprobs]

    perplexity_score = np.exp(-np.mean(logprobs))
    print("Prompt:".ljust(max_starter_length), prompt)
    print("Response:".ljust(max_starter_length), response_text, "\n")
    print("Tokens:".ljust(max_starter_length), " ".join(formatted_response_tokens))
    print("Logprobs:".ljust(max_starter_length), " ".join(formatted_lps))
    print("Perplexity:".ljust(max_starter_length), perplexity_score, "\n")
```

??? note "輸出"

    ```text
    Prompt:     In a short sentence, has artifical intelligence grown in the last decade?
    Response:   Yes, artificial intelligence has grown significantly in the last decade, advancing in capabilities and applications across various fields. 

    Tokens:                Yes              ,     artificial   intelligence            has          grown  significantly             in            the           last         decade              ,      advancing             in   capabilities            and   applications         across        various         fields              .
    Logprobs:            -0.00           0.00          -0.00           0.00          -0.00          -0.73          -0.00          -0.01          -0.02          -0.00           0.00          -0.02          -0.66          -0.03          -0.62          -0.47          -0.02          -0.39          -0.01          -0.20          -0.00
    Perplexity: 1.1644170003987546 

    Prompt:     In a short sentence, what are your thoughts on the future of artificial intelligence?
    Response:   The future of artificial intelligence holds immense potential for transformative advancements across various sectors, but it also requires careful consideration of ethical and societal impacts. 

    Tokens:                 The          future              of      artificial    intelligence           holds         immense       potential             for  transformative    advancements          across         various         sectors               ,             but              it            also        requires         careful   consideration              of         ethical             and        societal         impacts               .
    Logprobs:             -0.02           -0.00            0.00           -0.00            0.00           -0.05           -0.35           -0.01           -0.02           -0.64           -0.43           -0.25           -0.16           -0.51           -0.02           -0.43           -0.08           -0.07           -0.97           -0.02           -0.48           -0.00           -0.00           -0.48           -0.01           -0.58           -0.00
    Perplexity: 1.2292170270768858
    ```

這個例子裡，`gpt-4o-mini` 對比較確定的近代歷史問題回傳較低的 perplexity，對比較偏推測的近期未來評估回傳較高的 perplexity。同樣地，這些差異不保證準確，但它們能幫我們解讀模型的結果，也能指引後續怎麼使用這些結果。

## 6. 結論

我們用 `logprobs` 參數做出了更穩健的分類器、評估了 Q&A 系統的檢索，還對 token 的每個 'byte' 做了編碼與解碼。`logprobs` 替 completion 輸出增加了有用的資訊和訊號，期待看到開發者怎麼用它改善應用。

## 7. 可能的延伸

`logprobs` 還有很多這個 cookbook 沒涵蓋的用途，例如：
  - Moderation
  - Keyword selection
  - 改善 prompt 與輸出的可解釋性
  - Token healing
  - 還有更多！

## 重點整理
- `logprobs` 回傳每個輸出 token 的 `log(p)`，取指數就是 0 到 100% 的機率，是量測模型信心最直接的訊號。
- 分類時可以用機率設門檻，高信心自動處理，低信心送人工審查。
- 信心代表模型對判斷有多確定，不代表判斷是對的，所以自我評估的 guardrail 要用 eval 驗證。
- 把 token 的 logprob 加總取指數是 joint probability，平均後取負再取指數是 perplexity，兩者都能比較不同輸出或 prompt 的信心。
- `bytes` 欄位提供每個 token 的 UTF-8 byte，可以正確重組被拆成多個 token 的 emoji 或特殊字元。

## 練習
1. 把分類範例的 `top_logprobs` 從 2 改成 5，印出每個標題前五名候選 token 的機率，看除了選中的類別外還有哪些候選。
2. 在分類範例新增一個刻意模糊的標題（例如同時談政治和科技），設一個 90% 的信心門檻，寫出「低於門檻就標記為需人工審查」的判斷。
3. 在 perplexity 範例新增第三個問題（例如要求寫一首詩），算出它的 perplexity，跟原本兩個問題比較，說明哪種問題的不確定性最高。
