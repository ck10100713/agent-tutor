---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Embedding_Wikipedia_articles_for_search.ipynb
---

# 為搜尋做 Wikipedia 文章的 embedding

> 原文：[examples/Embedding_Wikipedia_articles_for_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Embedding_Wikipedia_articles_for_search.ipynb)



## 這篇在做什麼
示範怎麼把一批 Wikipedia 文章處理成可搜尋的資料集：下載、切 chunk、做 embedding，最後存成 CSV。這份資料集就是 [Question_answering_using_embeddings.ipynb](Question_answering_using_embeddings.md) 用的那份。

## 學完你會
- 把長文章清理後切成帶有標題脈絡的短 section
- 遞迴地把太長的 section 沿段落邊界切小，並理解切 chunk 的取捨
- 對每個 chunk 呼叫 embedding API，並存成 CSV

## 開跑前
需要 OpenAI API key（環境變數 `OPENAI_API_KEY`）。embedding 會產生 API 費用。

這個 notebook 示範我們怎麼為搜尋準備 Wikipedia 文章資料集，這份資料集用在 [Question_answering_using_embeddings.ipynb](Question_answering_using_embeddings.md)。

步驟：

0. 前置準備：匯入函式庫，設定 API key（如果需要）
1. 蒐集：下載幾百篇關於 2022 年奧運的 Wikipedia 文章
2. 切 chunk：把文件切成短的、大致自成一格的 section 以便 embedding
3. Embed：用 OpenAI API 對每個 section 做 embedding
4. 儲存：把 embedding 存進 CSV 檔（資料量大時請用 vector database）

## 0. 前置準備

### 匯入函式庫

```python
# imports
import mwclient  # for downloading example Wikipedia articles
import mwparserfromhell  # for splitting Wikipedia articles into sections
from openai import OpenAI  # for generating embeddings
import os  # for environment variables
import pandas as pd  # for DataFrames to store article sections and embeddings
import re  # for cutting <ref> links out of Wikipedia articles
import tiktoken  # for counting tokens

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

缺少的函式庫，可以在終端機用 `pip install` 安裝。例如：

```zsh
pip install openai
```

（你也可以在 notebook cell 裡用 `!pip install openai` 安裝。）

如果有安裝新的函式庫，記得重啟 notebook kernel。

### 設定 API key（如果需要）

注意 OpenAI 函式庫會嘗試從 `OPENAI_API_KEY` 環境變數讀取 API key。如果還沒設定，請照[這份說明](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety)設定這個環境變數。

## 1. 蒐集文件

這個例子會下載幾百篇跟 2022 冬季奧運相關的 Wikipedia 文章。

```python
# get Wikipedia pages about the 2022 Winter Olympics

CATEGORY_TITLE = "Category:2022 Winter Olympics"
WIKI_SITE = "en.wikipedia.org"


def titles_from_category(
    category: mwclient.listing.Category, max_depth: int
) -> set[str]:
    """Return a set of page titles in a given Wiki category and its subcategories."""
    titles = set()
    for cm in category.members():
        if type(cm) == mwclient.page.Page:
            # ^type() used instead of isinstance() to catch match w/ no inheritance
            titles.add(cm.name)
        elif isinstance(cm, mwclient.listing.Category) and max_depth > 0:
            deeper_titles = titles_from_category(cm, max_depth=max_depth - 1)
            titles.update(deeper_titles)
    return titles


site = mwclient.Site(WIKI_SITE)
category_page = site.pages[CATEGORY_TITLE]
titles = titles_from_category(category_page, max_depth=1)
# ^note: max_depth=1 means we go one level deep in the category tree
print(f"Found {len(titles)} article titles in {CATEGORY_TITLE}.")
```

??? note "輸出"

    ```text
    Found 179 article titles in Category:2022 Winter Olympics.
    ```

## 2. 切分文件

有了參考文件之後，要先準備好才能拿來搜尋。

因為 GPT 一次只能讀有限的文字量，所以我們要把每份文件切成夠短、讀得完的 chunk。

針對這個 Wikipedia 文章的例子，我們會：
- 丟掉看起來比較不相關的段落，像是外部連結和註腳
- 清理文字，移除 reference 標籤（例如 <ref>）、空白，以及超短的段落
- 把每篇文章切成多個 section
- 在每個 section 的文字前面加上標題和子標題，幫助 GPT 理解上下文
- 如果某個 section 太長（例如 > 1,600 tokens），就遞迴地切成更小的 section，盡量沿著段落這類語意邊界來切

```python
# define functions to split Wikipedia pages into sections

SECTIONS_TO_IGNORE = [
    "See also",
    "References",
    "External links",
    "Further reading",
    "Footnotes",
    "Bibliography",
    "Sources",
    "Citations",
    "Literature",
    "Footnotes",
    "Notes and references",
    "Photo gallery",
    "Works cited",
    "Photos",
    "Gallery",
    "Notes",
    "References and sources",
    "References and notes",
]


def all_subsections_from_section(
    section: mwparserfromhell.wikicode.Wikicode,
    parent_titles: list[str],
    sections_to_ignore: set[str],
) -> list[tuple[list[str], str]]:
    """
    From a Wikipedia section, return a flattened list of all nested subsections.
    Each subsection is a tuple, where:
        - the first element is a list of parent subtitles, starting with the page title
        - the second element is the text of the subsection (but not any children)
    """
    headings = [str(h) for h in section.filter_headings()]
    title = headings[0]
    if title.strip("=" + " ") in sections_to_ignore:
        # ^wiki headings are wrapped like "== Heading =="
        return []
    titles = parent_titles + [title]
    full_text = str(section)
    section_text = full_text.split(title)[1]
    if len(headings) == 1:
        return [(titles, section_text)]
    else:
        first_subtitle = headings[1]
        section_text = section_text.split(first_subtitle)[0]
        results = [(titles, section_text)]
        for subsection in section.get_sections(levels=[len(titles) + 1]):
            results.extend(all_subsections_from_section(subsection, titles, sections_to_ignore))
        return results


def all_subsections_from_title(
    title: str,
    sections_to_ignore: set[str] = SECTIONS_TO_IGNORE,
    site_name: str = WIKI_SITE,
) -> list[tuple[list[str], str]]:
    """From a Wikipedia page title, return a flattened list of all nested subsections.
    Each subsection is a tuple, where:
        - the first element is a list of parent subtitles, starting with the page title
        - the second element is the text of the subsection (but not any children)
    """
    site = mwclient.Site(site_name)
    page = site.pages[title]
    text = page.text()
    parsed_text = mwparserfromhell.parse(text)
    headings = [str(h) for h in parsed_text.filter_headings()]
    if headings:
        summary_text = str(parsed_text).split(headings[0])[0]
    else:
        summary_text = str(parsed_text)
    results = [([title], summary_text)]
    for subsection in parsed_text.get_sections(levels=[2]):
        results.extend(all_subsections_from_section(subsection, [title], sections_to_ignore))
    return results
```

```python
# split pages into sections
# may take ~1 minute per 100 articles
wikipedia_sections = []
for title in titles:
    wikipedia_sections.extend(all_subsections_from_title(title))
print(f"Found {len(wikipedia_sections)} sections in {len(titles)} pages.")
```

??? note "輸出"

    ```text
    Found 1838 sections in 179 pages.
    ```

```python
# clean text
def clean_section(section: tuple[list[str], str]) -> tuple[list[str], str]:
    """
    Return a cleaned up section with:
        - <ref>xyz</ref> patterns removed
        - leading/trailing whitespace removed
    """
    titles, text = section
    text = re.sub(r"<ref.*?</ref>", "", text)
    text = text.strip()
    return (titles, text)


wikipedia_sections = [clean_section(ws) for ws in wikipedia_sections]

# filter out short/blank sections
def keep_section(section: tuple[list[str], str]) -> bool:
    """Return True if the section should be kept, False otherwise."""
    titles, text = section
    if len(text) < 16:
        return False
    else:
        return True


original_num_sections = len(wikipedia_sections)
wikipedia_sections = [ws for ws in wikipedia_sections if keep_section(ws)]
print(f"Filtered out {original_num_sections-len(wikipedia_sections)} sections, leaving {len(wikipedia_sections)} sections.")
```

??? note "輸出"

    ```text
    Filtered out 89 sections, leaving 1749 sections.
    ```

```python
# print example data
for ws in wikipedia_sections[:5]:
    print(ws[0])
    display(ws[1][:77] + "...")
    print()
```

??? note "輸出"

    ```text
    ['Concerns and controversies at the 2022 Winter Olympics']
    ```

    ```text
    '{{Short description|Overview of concerns and controversies surrounding the Ga...'
    ```

    ```text

    ['Concerns and controversies at the 2022 Winter Olympics', '==Criticism of host selection==']
    ```

    ```text
    'American sportscaster [[Bob Costas]] criticized the [[International Olympic C...'
    ```

    ```text

    ['Concerns and controversies at the 2022 Winter Olympics', '==Organizing concerns and controversies==', '===Cost and climate===']
    ```

    ```text
    'Several cities withdrew their applications during [[Bids for the 2022 Winter ...'
    ```

    ```text

    ['Concerns and controversies at the 2022 Winter Olympics', '==Organizing concerns and controversies==', '===Promotional song===']
    ```

    ```text
    'Some commentators alleged that one of the early promotional songs for the [[2...'
    ```

    ```text

    ['Concerns and controversies at the 2022 Winter Olympics', '== Diplomatic boycotts or non-attendance ==']
    ```

    ```text
    '<section begin=boycotts />\n[[File:2022 Winter Olympics (Beijing) diplomatic b...'
    ```

接下來，把太長的 section 遞迴切小。

切文字沒有完美的做法。

要考慮的取捨包括：
- 較長的 section 對需要更多上下文的問題可能比較好
- 較長的 section 對檢索可能比較差，因為可能混了更多主題
- 較短的 section 比較省成本（成本和 token 數成正比）
- 較短的 section 可以檢索更多段，可能有助於 recall
- section 之間有重疊，可以避免答案被 section 邊界切斷

這裡我們用簡單的做法，每個 section 限制在 1,600 tokens，太長的就遞迴對半切。為了避免把有用的句子從中間切斷，可以的話會沿著段落邊界切。

```python
GPT_MODEL = "gpt-4o-mini"  # only matters insofar as it selects which tokenizer to use


def num_tokens(text: str, model: str = GPT_MODEL) -> int:
    """Return the number of tokens in a string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def halved_by_delimiter(string: str, delimiter: str = "\n") -> list[str, str]:
    """Split a string in two, on a delimiter, trying to balance tokens on each side."""
    chunks = string.split(delimiter)
    if len(chunks) == 1:
        return [string, ""]  # no delimiter found
    elif len(chunks) == 2:
        return chunks  # no need to search for halfway point
    else:
        total_tokens = num_tokens(string)
        halfway = total_tokens // 2
        best_diff = halfway
        for i, chunk in enumerate(chunks):
            left = delimiter.join(chunks[: i + 1])
            left_tokens = num_tokens(left)
            diff = abs(halfway - left_tokens)
            if diff >= best_diff:
                break
            else:
                best_diff = diff
        left = delimiter.join(chunks[:i])
        right = delimiter.join(chunks[i:])
        return [left, right]


def truncated_string(
    string: str,
    model: str,
    max_tokens: int,
    print_warning: bool = True,
) -> str:
    """Truncate a string to a maximum number of tokens."""
    encoding = tiktoken.encoding_for_model(model)
    encoded_string = encoding.encode(string)
    truncated_string = encoding.decode(encoded_string[:max_tokens])
    if print_warning and len(encoded_string) > max_tokens:
        print(f"Warning: Truncated string from {len(encoded_string)} tokens to {max_tokens} tokens.")
    return truncated_string


def split_strings_from_subsection(
    subsection: tuple[list[str], str],
    max_tokens: int = 1000,
    model: str = GPT_MODEL,
    max_recursion: int = 5,
) -> list[str]:
    """
    Split a subsection into a list of subsections, each with no more than max_tokens.
    Each subsection is a tuple of parent titles [H1, H2, ...] and text (str).
    """
    titles, text = subsection
    string = "\n\n".join(titles + [text])
    num_tokens_in_string = num_tokens(string)
    # if length is fine, return string
    if num_tokens_in_string <= max_tokens:
        return [string]
    # if recursion hasn't found a split after X iterations, just truncate
    elif max_recursion == 0:
        return [truncated_string(string, model=model, max_tokens=max_tokens)]
    # otherwise, split in half and recurse
    else:
        titles, text = subsection
        for delimiter in ["\n\n", "\n", ". "]:
            left, right = halved_by_delimiter(text, delimiter=delimiter)
            if left == "" or right == "":
                # if either half is empty, retry with a more fine-grained delimiter
                continue
            else:
                # recurse on each half
                results = []
                for half in [left, right]:
                    half_subsection = (titles, half)
                    half_strings = split_strings_from_subsection(
                        half_subsection,
                        max_tokens=max_tokens,
                        model=model,
                        max_recursion=max_recursion - 1,
                    )
                    results.extend(half_strings)
                return results
    # otherwise no split was found, so just truncate (should be very rare)
    return [truncated_string(string, model=model, max_tokens=max_tokens)]
```

```python
# split sections into chunks
MAX_TOKENS = 1600
wikipedia_strings = []
for section in wikipedia_sections:
    wikipedia_strings.extend(split_strings_from_subsection(section, max_tokens=MAX_TOKENS))

print(f"{len(wikipedia_sections)} Wikipedia sections split into {len(wikipedia_strings)} strings.")
```

??? note "輸出"

    ```text
    1749 Wikipedia sections split into 2052 strings.
    ```

```python
# print example data
print(wikipedia_strings[1])
```

??? note "輸出"

    ```text
    Concerns and controversies at the 2022 Winter Olympics

    ==Criticism of host selection==

    American sportscaster [[Bob Costas]] criticized the [[International Olympic Committee]]'s (IOC) decision to award the games to China saying "The IOC deserves all of the disdain and disgust that comes their way for going back to China yet again" referencing China's human rights record.

    After winning two gold medals and returning to his home country of Sweden skater [[Nils van der Poel]] criticized the IOC's selection of China as the host saying "I think it is extremely irresponsible to give it to a country that violates human rights as blatantly as the Chinese regime is doing." He had declined to criticize China before leaving for the games saying "I don't think it would be particularly wise for me to criticize the system I'm about to transition to, if I want to live a long and productive life."
    ```

## 3. 對文件 chunk 做 embedding

現在已經把資料庫切成較短、自成一格的字串，可以對每一個計算 embedding。

（大量 embedding 的工作，可以用 [api_request_parallel_processor.py](https://github.com/openai/openai-cookbook/blob/main/examples/api_request_parallel_processor.py) 這類腳本，平行送出請求，同時節流以避免超過 rate limit。）

```python
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 1000  # you can submit up to 2048 embedding inputs per request

embeddings = []
for batch_start in range(0, len(wikipedia_strings), BATCH_SIZE):
    batch_end = batch_start + BATCH_SIZE
    batch = wikipedia_strings[batch_start:batch_end]
    print(f"Batch {batch_start} to {batch_end-1}")
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
    for i, be in enumerate(response.data):
        assert i == be.index  # double check embeddings are in same order as input
    batch_embeddings = [e.embedding for e in response.data]
    embeddings.extend(batch_embeddings)

df = pd.DataFrame({"text": wikipedia_strings, "embedding": embeddings})
```

??? note "輸出"

    ```text
    Batch 0 to 999
    Batch 1000 to 1999
    Batch 2000 to 2999
    ```

## 4. 儲存文件 chunk 與 embedding

因為這個例子只有幾千個字串，所以我們把它們存成 CSV 檔。

（資料集更大時，請用 vector database，效能會更好。）

```python
# save document chunks and embeddings

SAVE_PATH = "data/winter_olympics_2022.csv"

df.to_csv(SAVE_PATH, index=False)
```

## 重點整理
- 搜尋用的資料集流程是：蒐集、清理、切 chunk、embed、儲存。
- 切 chunk 沒有標準答案，長度在上下文完整、檢索精準和成本之間取捨。
- 在每個 section 前加上標題和子標題，能讓 chunk 脫離原文後仍有脈絡。
- 資料量小時 CSV 夠用，大了就該換 vector database。
- 大量 embedding 要平行處理，並控制 rate limit。

## 練習
1. 把 section 的 token 上限從 1,600 改成 800，看切出來的 chunk 數量增加多少。
2. 修改清理步驟，多丟掉一個你覺得不相關的段落標題（例如 "See also"），重新看 chunk 數量。
3. 讓遞迴切分在相鄰 chunk 之間保留一段重疊內容，並比較重疊前後的 chunk 數量與 embedding 成本。
