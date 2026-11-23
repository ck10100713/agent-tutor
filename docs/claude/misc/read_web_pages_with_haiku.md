---
translated: true
source: misc/read_web_pages_with_haiku.ipynb
---

# 用 Claude Haiku 摘要網頁內容

> 原文：[misc/read_web_pages_with_haiku.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/read_web_pages_with_haiku.ipynb)

用 URL 抓取網頁內容，再交給 Claude Haiku 做摘要。

## 這篇在做什麼

給定一個網頁 URL，先抓取頁面內容，再用 Claude API 產生內容摘要。

## 學完你會

- 用 `requests` 抓取網頁內容
- 把頁面內容和摘要指示組成給 Claude 的訊息
- 用 Haiku 產生網頁摘要

## 開跑前

需要 Anthropic API key。

這份教學要學怎麼根據 URL 抓取網頁內容，再用 Anthropic 的 Claude API 產生頁面內容的摘要。

先安裝 Anthropic 套件。

## 設定
先安裝需要的套件，並用 API key 設定 Anthropic client。

```python
# Install the necessary libraries
%pip install anthropic
```

```python
# Import the required libraries
from anthropic import Anthropic

# Set up the Claude API client
client = Anthropic()
MODEL_NAME = "claude-haiku-5-5"
```

## Step 1：抓取網頁內容
首先我們要用給定的 URL 抓取網頁內容，這裡使用 requests 套件。

```python
import requests

url = "https://en.wikipedia.org/wiki/96th_Academy_Awards"
# Wikimedia asks clients to send an identifying User-Agent; the default python-requests one is refused (403)
headers = {
    "User-Agent": "claude-cookbook-example/1.0 (https://github.com/anthropics/claude-cookbooks)"
}
response = requests.get(url, headers=headers, timeout=30)

if response.status_code == 200:
    page_content = response.text
else:
    print(f"Failed to fetch the web page. Status code: {response.status_code}")
    exit(1)
```

## Step 2：準備給 Claude 的輸入
接著準備 Claude API 的輸入。我們建立一則訊息，包含頁面內容和請 Claude 摘要的 prompt。

```python
prompt = (
    f"<content>{page_content}</content>Please produce a concise summary of the web page content."
)

messages = [{"role": "user", "content": prompt}]
```

## Step 3：產生摘要
現在呼叫 Haiku 來產生網頁內容的摘要。

```python
response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=messages)

# Read the text block by type: the response may start with a thinking block
summary = "".join(block.text for block in response.content if block.type == "text")
print(summary)
```

??? note "輸出"

    ```text
    **96th Academy Awards (Wikipedia article)**

    The 96th Academy Awards ceremony, presented by the Academy of Motion Picture Arts and Sciences, was held on March 10, 2024, at the Dolby Theatre in Hollywood, Los Angeles. It honored films released in 2023 and was hosted by Jimmy Kimmel, his fourth time hosting. The telecast was produced by Raj Kapoor and Katy Mullan, directed by Hamish Hamilton, and aired on ABC.

    Key points:

    - **Top winners:** *Oppenheimer* won seven awards, including Best Picture and Best Director (Christopher Nolan). *Poor Things* won four, and *The Zone of Interest* won two. *Oppenheimer* also led in nominations with 13, ahead of *Poor Things* (11).
    - **Acting:** Cillian Murphy (Best Actor, *Oppenheimer*), Emma Stone (Best Actress, *Poor Things*), Robert Downey Jr. (Best Supporting Actor, *Oppenheimer*), and Da'Vine Joy Randolph (Best Supporting Actress, *The Holdovers*).
    - **Other notable wins:** Billie Eilish and Finneas O'Connell won Best Original Song for "What Was I Made For?" from *Barbie*, and *The Zone of Interest* won Best International Feature Film. *Godzilla Minus One* won Best Visual Effects.
    - **Records and firsts:** Martin Scorsese became the oldest Best Director nominee, and three Best Picture nominees were directed by women.
    - **Ceremony details:** The show started an hour earlier than usual. Presenters and performers included Ryan Gosling performing "I'm Just Ken." The "In Memoriam" segment featured Andrea Bocelli.
    - **Controversy:** Jonathan Glazer's acceptance speech about the Israel–Gaza conflict drew praise and criticism, and led to open letters from both supporters and critics.
    - **Reception:** The telecast drew about 19.49 million U.S. viewers, a 4% increase over the previous year. It later won four Primetime Emmys.

    The page also covers the Governors Awards (held January 9, 2024), the Academy's new Best Picture diversity standards, and box office performance of the nominees.
    ```

## 重點整理

- 模型本身不會上網，要自己先抓內容再塞進 prompt。
- 小而快的模型（Haiku）很適合摘要這種單純任務。
- 網頁內容可能很長或有雜訊，實務上通常要先清理再送。

## 練習

1. 換成另一個網頁 URL 測試摘要。
2. 修改 prompt，要求輸出三點重點和一句結論。
3. 用 `BeautifulSoup` 先抽出純文字再送給 Claude，比較結果。
