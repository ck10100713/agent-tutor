---
translated: true
source: examples/Enhance_your_prompts_with_meta_prompting.ipynb
---

# 用 Meta Prompting 強化你的 Prompt

> 原文：[examples/Enhance_your_prompts_with_meta_prompting.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Enhance_your_prompts_with_meta_prompting.ipynb)



## 這篇在做什麼
拿一個很簡單的新聞摘要 prompt，請更強的模型（`o1-preview`）幫忙改寫成更詳細的版本，再給 `gpt-4o` 用。最後用 LLM as a judge 評分，比較兩個 prompt 產出的摘要差在哪。

## 學完你會
- 用強模型去生成或優化給較弱模型用的 prompt（meta prompting）。
- 用同一批 BBC 新聞資料，並排產生簡單版和強化版 prompt 的摘要。
- 設計 LLM as a judge 的評分 prompt，量化兩個 prompt 在分類、關鍵字、情感分析、完整度上的差異。

## 開跑前
- 需要 OpenAI API key，而且帳號要能用 `o1-preview`。
- 資料來自 HuggingFace 的 `bbc_news_alltime`，需要能連網下載。

歡迎來到 meta prompting 的教學！這份指南會示範怎麼把一個基本的 prompt 改進，提升語言模型的輸出品質。我們用新聞報導摘要當例子來說明整個過程。


Meta-prompting 是用 LLM 來生成或改進 prompt 的技巧。通常做法是用比較聰明的模型，替比較不聰明的模型優化 prompt。這是用 prompt 來引導、組織和優化其他 prompt，讓它們更能引導 LLM 產出高品質、相關的結果。我們會用推理能力更強的 `o1-preview`，來改進給 `gpt-4o` 用的 prompt。

我們希望靠這個技巧讓你用 LLM 開發更順手、更容易上手。別忘了看看 playground 裡的 [Generate Anything](https://platform.openai.com/docs/guides/prompt-generation) 功能，它是入門 meta prompting 的好起點。

這個例子會從一個簡單的新聞摘要 prompt 開始，再強化它，看輸出怎麼進步。我們用 `o1-preview` 分析並改進 prompt，補上更多細節和清楚度。最後系統化地評估輸出，了解改進帶來的影響。

```python
import pandas as pd
import openai 
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from pydantic import BaseModel
from datasets import load_dataset

client = openai.Client()
```

??? note "輸出"

    ```text
    /Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/tqdm/auto.py:21: TqdmWarning: IProgress not found. Please update jupyter and ipywidgets. See https://ipywidgets.readthedocs.io/en/stable/user_install.html
      from .autonotebook import tqdm as notebook_tqdm
    ```

## 匯入資料

先從 [HuggingFace](https://huggingface.co/datasets/RealTimeData/bbc_news_alltime) 匯入 `bbc_news_alltime` 資料集。這份資料集收錄 BBC News 的所有文章，涵蓋 2017 年起到最近一個完整月份、每個月發布的內容。實驗只用最近一個月（2024 年 8 月）的樣本，這樣資料夠新、量也剛好。


```python
ds = load_dataset("RealTimeData/bbc_news_alltime", "2024-08")
df = pd.DataFrame(ds['train']).sample(n=100, random_state=1)
df.head()
```

??? note "輸出"

    ```text
                                                      title published_date  \
    2662  Laura Whitmore: I was gaslighted after raising...     2024-08-04   
    1865  Errollyn Wallen appointed as Master of the Kin...     2024-08-25   
    2554  SDLP: Matthew O'Toole endorses Claire Hanna fo...     2024-08-30   
    1338   Rotherham rioters among those jailed  - BBC News     2024-08-20   
    1232                             BBC News - BBC iPlayer     2024-08-02   

                                   authors  \
    2662  https://www.facebook.com/bbcnews   
    1865  https://www.facebook.com/bbcnews   
    2554  https://www.facebook.com/bbcnews   
    1338  https://www.facebook.com/bbcnews   
    1232                              None   

                                                description  \
    2662  The former Love Island host said that things s...   
    1865  She is best known for her work on the 2012 Par...   
    2554  Matthew O'Toole had been named by some as a po...   
    1338  Two men who were part of a mob targeting a Hol...   
    1232                                               None   

                            section  \
    2662                    Culture   
    1865                    Culture   
    2554  Northern Ireland Politics   
    1338            South Yorkshire   
    1232                       None   

                                                    content  \
    2662  Television presenter Laura Whitmore has said t...   
    1865  Celebrated composer and singer-songwriter Erro...   
    2554  Matthew O'Toole leads his party's official opp...   
    1338  Rotherham pair among those jailed for UK rioti...   
    1232  JavaScript seems to be disabled. Please enable...   

                                                     link  \
    2662  http://www.bbc.co.uk/news/articles/c9wvwvzm7x7o   
    1865  http://www.bbc.co.uk/news/articles/c4gl758g7zgo   
    2554  http://www.bbc.co.uk/news/articles/cvg41j7xrzdo   
    1338  http://www.bbc.co.uk/news/articles/cwywggd7qw6o   
    ... (省略 8 行)
    ```

## 迭代 Prompt


先從一個直白的 prompt 開始，再用 `o1-preview` 把它改得更好。我們要摘要新聞文章，所以先這樣請模型做。 

```python
simple_prompt = "Summarize this news article: {article}"
```

要改進 prompt，需要先把背景和目標告訴 `o1-preview`，再請它產生更詳細的 prompt，讓摘要更豐富、更完整。

```python
meta_prompt = """
Improve the following prompt to generate a more detailed summary. 
Adhere to prompt engineering best practices. 
Make sure the structure is clear and intuitive and contains the type of news, tags and sentiment analysis.

{simple_prompt}

Only return the prompt.
"""
```

```python
def get_model_response(messages, model="o1-preview"):
    response = client.chat.completions.create(
        messages=messages,
        model=model,
    )
    return response.choices[0].message.content


complex_prompt = get_model_response([{"role": "user", "content": meta_prompt.format(simple_prompt=simple_prompt)}])
complex_prompt
```

??? note "輸出"

    ```text
    'Please read the following news article and provide a comprehensive summary that includes:\n\n1. **Type of News**: Specify the category of the news article (e.g., Politics, Technology, Health, Sports, etc.).\n2. **Summary**: Write a concise and clear summary of the main points, ensuring the structure is logical and intuitive.\n3. **Tags**: List relevant keywords or tags associated with the article.\n4. **Sentiment Analysis**: Analyze the overall sentiment of the article (positive, negative, or neutral) and briefly explain your reasoning.\n\n**Article:**\n\n{article}'
    ```

## 產生摘要

現在兩個 prompt 都有了，來產生摘要！資料集的每一筆都用簡單版和強化版 prompt 各跑一次，比較結果。這樣就能親眼看到 `o1-preview` 的改進怎麼讓摘要更豐富、更詳細。來看看差別！

```python
def generate_response(prompt): 
    messages = [{"role": "user", "content": prompt}]
    response = get_model_response(messages, model="gpt-4o-mini")
    return response

def generate_summaries(row):
    simple_itinerary = generate_response(simple_prompt.format(article=row["content"]))
    complex_itinerary = generate_response(complex_prompt + row["content"])
    return simple_itinerary, complex_itinerary
```

先確認一切正常，並替第一篇新聞產生摘要。 

```python
generate_summaries(df.iloc[0])
```

??? note "輸出"

    ```text
    ('Television presenter Laura Whitmore has shared that the issues she attempted to address during her time on *Strictly Come Dancing* eight years ago are now surfacing, stating that she experienced "gaslighting" that made her concerns seem normalized. In a recent interview, she expressed the difficulties she faced, including being portrayed negatively and feeling "broken" during the competition. Whitmore indicated that she raised concerns about inappropriate behavior and is currently providing evidence for a BBC investigation, although she has not made an official complaint herself. The BBC is facing allegations of mistreatment towards contestants, prompting them to announce new welfare measures, including the presence of a chaperone during rehearsals. Other celebrities participating in the show have also made allegations against professional dancers, leading to growing scrutiny around conditions on the show. The BBC emphasized that it takes complaints very seriously and is committed to updating its support processes.',
     '1. **Type of News**: Entertainment\n\n2. **Summary**: Laura Whitmore, a television presenter, has spoken out about her experiences on Strictly Come Dancing, revealing that issues she attempted to address during her tenure on the show are now coming to light. In an interview with The Irish Times, she described feeling "gaslit" and suggested that her concerns, which she raised eight years ago, were not taken seriously at the time. Whitmore recalled that her participation left her feeling "broken" and criticized how she was portrayed during the show. She mentioned contributing evidence to an ongoing review involving incidents of alleged inappropriate behavior during her time on the show, although she did not make an official complaint. The BBC, which has been navigating its own controversy related to the treatment of contestants, stated it is taking these claims seriously and plans to enhance welfare measures on the show, including the introduction of a chaperone at rehearsals. Recent allegations from other contestants have further intensified the scrutiny of Strictly Come Dancing.\n\n3. **Tags**: Laura Whitmore, Strictly Come Dancing, BBC, allegations, inappropriate behavior, gaslighting, welfare measures, entertainment controversy\n\n4. **Sentiment Analysis**: The overall sentiment of the article is negative. It highlights serious allegations of mistreatment and inappropriate behavior associated with a popular television show, along with personal accounts from Whitmore that reflect emotional distress and professional struggles. The tone conveys a sense of urgency and seriousness regarding the issues raised, indicating a critical atmosphere within the entertainment industry related to contestant treatment.')
    ```

比較兩個 prompt 產生的摘要，就能看出明顯的進步。最初的摘要只給文章的大致概覽，強化版則更深入：不只有詳細摘要，還會分類新聞類型、列出相關標籤，甚至附上情感分析。

現在對整個資料集測試！ 

```python
# Add new columns to the dataframe for storing itineraries
df['simple_summary'] = None
df['complex_summary'] = None

# Use ThreadPoolExecutor to generate itineraries concurrently
with ThreadPoolExecutor() as executor:
    futures = {executor.submit(generate_summaries, row): index for index, row in df.iterrows()}
    for future in tqdm(as_completed(futures), total=len(futures), desc="Generating Itineraries"):
        index = futures[future]
        simple_itinerary, complex_itinerary = future.result()
        df.at[index, 'simple_summary'] = simple_itinerary
        df.at[index, 'complex_summary'] = complex_itinerary

df.head()
```

??? note "輸出"

    ```text
    Generating Itineraries: 100%|██████████| 100/100 [00:50<00:00,  1.98it/s]
    ```

    ```text
                                                      title published_date  \
    2662  Laura Whitmore: I was gaslighted after raising...     2024-08-04   
    1865  Errollyn Wallen appointed as Master of the Kin...     2024-08-25   
    2554  SDLP: Matthew O'Toole endorses Claire Hanna fo...     2024-08-30   
    1338   Rotherham rioters among those jailed  - BBC News     2024-08-20   
    1232                             BBC News - BBC iPlayer     2024-08-02   

                                   authors  \
    2662  https://www.facebook.com/bbcnews   
    1865  https://www.facebook.com/bbcnews   
    2554  https://www.facebook.com/bbcnews   
    1338  https://www.facebook.com/bbcnews   
    1232                              None   

                                                description  \
    2662  The former Love Island host said that things s...   
    1865  She is best known for her work on the 2012 Par...   
    2554  Matthew O'Toole had been named by some as a po...   
    1338  Two men who were part of a mob targeting a Hol...   
    1232                                               None   

                            section  \
    2662                    Culture   
    1865                    Culture   
    2554  Northern Ireland Politics   
    1338            South Yorkshire   
    1232                       None   

                                                    content  \
    2662  Television presenter Laura Whitmore has said t...   
    1865  Celebrated composer and singer-songwriter Erro...   
    2554  Matthew O'Toole leads his party's official opp...   
    1338  Rotherham pair among those jailed for UK rioti...   
    1232  JavaScript seems to be disabled. Please enable...   

                                                     link  \
    2662  http://www.bbc.co.uk/news/articles/c9wvwvzm7x7o   
    1865  http://www.bbc.co.uk/news/articles/c4gl758g7zgo   
    2554  http://www.bbc.co.uk/news/articles/cvg41j7xrzdo   
    1338  http://www.bbc.co.uk/news/articles/cwywggd7qw6o   
    ... (省略 22 行)
    ```

## 評估結果

要評估兩個 prompt 的表現差異，我們用結構化的評估方法，讓 LLM 當評審。也就是利用語言模型本身，依特定標準評估並比較輸出。

**"LLM as a Judge" 是什麼意思？**

讓 LLM 當評審，是指請語言模型評估自己或另一個模型的輸出，依預先定義的標準檢視準確度、清楚度和相關性等面向。這樣能得到客觀、一致、沒有人為偏見的評估，更容易看出不同 prompt 之間的進步。我們的 [Getting Started with OpenAI Evals](https://cookbook.openai.com/examples/evaluation/getting_started_with_openai_evals) 教學可以讓你一窺怎麼開始用這個方法。


這是我們用來評估的 prompt：

```python
evaluation_prompt = """
You are an expert editor tasked with evaluating the quality of a news article summary. Below is the original article and the summary to be evaluated:

**Original Article**:  
{original_article}

**Summary**:  
{summary}

Please evaluate the summary based on the following criteria, using a scale of 1 to 5 (1 being the lowest and 5 being the highest). Be critical in your evaluation and only give high scores for exceptional summaries:

1. **Categorization and Context**: Does the summary clearly identify the type or category of news (e.g., Politics, Technology, Sports) and provide appropriate context?  
2. **Keyword and Tag Extraction**: Does the summary include relevant keywords or tags that accurately capture the main topics and themes of the article?  
3. **Sentiment Analysis**: Does the summary accurately identify the overall sentiment of the article and provide a clear, well-supported explanation for this sentiment?  
4. **Clarity and Structure**: Is the summary clear, well-organized, and structured in a way that makes it easy to understand the main points?  
5. **Detail and Completeness**: Does the summary provide a detailed account that includes all necessary components (type of news, tags, sentiment) comprehensively?  


Provide your scores and justifications for each criterion, ensuring a rigorous and detailed evaluation.
"""

class ScoreCard(BaseModel):
    justification: str
    categorization: int
    keyword_extraction: int
    sentiment_analysis: int
    clarity_structure: int
    detail_completeness: int
```

給你一個小撇步：你也可以用 meta prompting 來改進評估用的 prompt！對指示 LLM 當評審的 prompt 做同樣的迭代強化，評估就能更精準、更有洞察力。 

來用這個 prompt 評估我們的摘要！

```python
def evaluate_summaries(row):
    simple_messages = [{"role": "user", "content": evaluation_prompt.format(original_article=row["content"], summary=row['simple_summary'])}]
    complex_messages = [{"role": "user", "content": evaluation_prompt.format(original_article=row["content"], summary=row['complex_summary'])}]
    
    simple_summary = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=simple_messages,
        response_format=ScoreCard)
    simple_summary = simple_summary.choices[0].message.parsed
    
    complex_summary = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=complex_messages,
        response_format=ScoreCard)
    complex_summary = complex_summary.choices[0].message.parsed
    
    return simple_summary, complex_summary

# Add new columns to the dataframe for storing evaluations
df['simple_evaluation'] = None
df['complex_evaluation'] = None

# Use ThreadPoolExecutor to evaluate itineraries concurrently
with ThreadPoolExecutor() as executor:
    futures = {executor.submit(evaluate_summaries, row): index for index, row in df.iterrows()}
    for future in tqdm(as_completed(futures), total=len(futures), desc="Evaluating Summaries"):
        index = futures[future]
        simple_evaluation, complex_evaluation = future.result()
        df.at[index, 'simple_evaluation'] = simple_evaluation
        df.at[index, 'complex_evaluation'] = complex_evaluation

df.head()
```

??? note "輸出"

    ```text
    Evaluating Summaries: 100%|██████████| 100/100 [01:42<00:00,  1.02s/it]
    ```

    ```text
                                                      title published_date  \
    2662  Laura Whitmore: I was gaslighted after raising...     2024-08-04   
    1865  Errollyn Wallen appointed as Master of the Kin...     2024-08-25   
    2554  SDLP: Matthew O'Toole endorses Claire Hanna fo...     2024-08-30   
    1338   Rotherham rioters among those jailed  - BBC News     2024-08-20   
    1232                             BBC News - BBC iPlayer     2024-08-02   

                                   authors  \
    2662  https://www.facebook.com/bbcnews   
    1865  https://www.facebook.com/bbcnews   
    2554  https://www.facebook.com/bbcnews   
    1338  https://www.facebook.com/bbcnews   
    1232                              None   

                                                description  \
    2662  The former Love Island host said that things s...   
    1865  She is best known for her work on the 2012 Par...   
    2554  Matthew O'Toole had been named by some as a po...   
    1338  Two men who were part of a mob targeting a Hol...   
    1232                                               None   

                            section  \
    2662                    Culture   
    1865                    Culture   
    2554  Northern Ireland Politics   
    1338            South Yorkshire   
    1232                       None   

                                                    content  \
    2662  Television presenter Laura Whitmore has said t...   
    1865  Celebrated composer and singer-songwriter Erro...   
    2554  Matthew O'Toole leads his party's official opp...   
    1338  Rotherham pair among those jailed for UK rioti...   
    1232  JavaScript seems to be disabled. Please enable...   

                                                     link  \
    2662  http://www.bbc.co.uk/news/articles/c9wvwvzm7x7o   
    1865  http://www.bbc.co.uk/news/articles/c4gl758g7zgo   
    2554  http://www.bbc.co.uk/news/articles/cvg41j7xrzdo   
    1338  http://www.bbc.co.uk/news/articles/cwywggd7qw6o   
    ... (省略 36 行)
    ```

```python
import matplotlib.pyplot as plt

df["simple_scores"] = df["simple_evaluation"].apply(lambda x: [score for key, score in x.model_dump().items() if key != 'justification'])
df["complex_scores"] = df["complex_evaluation"].apply(lambda x: [score for key, score in x.model_dump().items() if key != 'justification'])


# Calculate average scores for each criterion
criteria = [
    'Categorisation',
    'Keywords and Tags',
    'Sentiment Analysis',
    'Clarity and Structure',
    'Detail and Completeness'
]

# Calculate average scores for each criterion by model
simple_avg_scores = df['simple_scores'].apply(pd.Series).mean()
complex_avg_scores = df['complex_scores'].apply(pd.Series).mean()


# Prepare data for plotting
avg_scores_df = pd.DataFrame({
    'Criteria': criteria,
    'Original Prompt': simple_avg_scores,
    'Improved Prompt': complex_avg_scores
})

# Plotting
ax = avg_scores_df.plot(x='Criteria', kind='bar', figsize=(6, 4))
plt.ylabel('Average Score')
plt.title('Comparison of Simple vs Complex Prompt Performance by Model')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.legend(loc='upper left', bbox_to_anchor=(1, 1))
plt.show()
```

評估後發現，基本 prompt 在清楚度和結構上表現不錯，但強化版 prompt 在其他幾個關鍵項目上大幅進步：分類（Categorization）、關鍵字與標籤（Keywords and Tags）、情感分析（Sentiment Analysis），以及細節與完整度（Detail and Completeness）。複雜的 prompt 讓摘要更有資訊量、組織更好、內容更豐富。

這證明改進 prompt 能大幅提升產出摘要的品質。雖然這是簡化的例子，但在真實的正式環境裡，prompt 優化的效益預期會更明顯，輸出會更貼近特定目標和使用者需求。

## 結論

Meta prompting 是很強的技巧，能大幅提升語言模型的輸出品質。這次的探索顯示，從簡單的 prompt 開始，再用 `o1-preview` 改進，摘要變得更有資訊量、組織更好、內容更豐富，在分類、關鍵字與標籤、情感分析和完整度等關鍵標準上都有進步。這個練習凸顯了 prompt 優化的價值，即使是簡化的例子，好處也很明顯。在真實應用裡，善用 meta prompting 和 `o1-preview` 這類工具，可以讓語言模型的表現更貼近你的特定目標和使用者需求。

## 重點整理
- Meta prompting 是用較強的模型替較弱的模型寫或改 prompt，你只要說明背景和目標。
- 先有簡單的 baseline prompt，再迭代改進，才看得出改進的效果。
- 強化版 prompt 的摘要多了分類、標籤、情感分析和更完整的細節，簡單版只有大致概覽。
- LLM as a judge 可以用固定標準量化比較，而評估 prompt 本身也能用 meta prompting 來改。

## 練習
1. 換一個月份的資料（改掉 2024 年 8 月的篩選），重跑兩個 prompt，看強化版優勢是否還在。
2. 在給 `o1-preview` 的目標說明裡加一個新需求（例如摘要要限制在 100 字內），重新產生強化版 prompt 並比較。
3. 用 meta prompting 改寫評估用的 judge prompt，加入一項新的評分標準（例如事實正確性），再重跑評估。
