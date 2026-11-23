---
translated: true
source: articles/gpt-oss/build-your-own-fact-checker-cerebras.ipynb
---

# 用 gpt-oss-120B、Cerebras 和 Parallel 打造你自己的內容事實查核器

> 原文：[articles/gpt-oss/build-your-own-fact-checker-cerebras.ipynb](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/build-your-own-fact-checker-cerebras.ipynb)

用 Parallel 在 Cerebras 上以 gpt-oss-120B 打造內容事實查核器的 cookbook。

## 這篇在做什麼
做一個自動事實查核器：從文字或 URL 抽出 claims，用 Parallel 搜尋網路證據，再讓 Cerebras 上的 gpt-oss-120B 判斷每個 claim 是 True、False 或 Uncertain，並附上引用的 URL。

## 學完你會
- 用 Cerebras 呼叫 gpt-oss-120B，並串接 Parallel 搜尋當作 LLM 的網路證據來源。
- 把一段文字拆成可獨立查證的 claims，再對每個 claim 回傳結構化的判定和說明。
- 把整套流程包成可以直接吃文字或 URL 的函式。

## 開跑前
- 需要 Cerebras API key（環境變數 `CEREBRAS_API_KEY`）。
- 需要 Parallel API key（環境變數 `PARALLEL_API_KEY`）。
- 兩個服務都有免費額度可以開始。


有沒有讀完一篇文章，後來才發現其中一些「事實」是捏造的？資訊越來越多，要驗證它是否正確也越來越難。

這份指南提供一個實用的自動化做法，可以大規模評估事實正確性。它會從任何文字或 URL 抽出 claims，取得真實世界的證據，並用 Cerebras 超低延遲推論驅動的 gpt-oss-120B 評估每個 claim。

Demo 在這裡：[Content Fact-Checker](https://oss.parallel.ai/agents/cerebras-fact-checker)。

這份指南需要先設定下面的帳號： 

- Cerebras API：最快的推論服務商，[在這裡免費開始。](https://cloud.cerebras.ai/?utm_source=DevX&utm_campaign=parallel)

- Parallel API：為 AI 打造的搜尋引擎，[在這裡免費開始。](https://platform.parallel.ai/)

想了解 gpt-oss-120B 的最佳實務，看[這裡](https://openai.com/index/introducing-gpt-oss/)。

### **Step 1：環境設定（Colab 或本機）**

這份指南同時支援本機 Jupyter 環境和 Google Colab。設定下面的環境變數：
- CEREBRAS_API_KEY
- PARALLEL_API_KEY

```python
python3 -m pip install -U cerebras_cloud_sdk parallel-web
```

```python
import os
from cerebras.cloud.sdk import Cerebras
from parallel import Parallel

# API keys: Colab userdata (if available) -> env vars fallback
try:
    from google.colab import userdata  # type: ignore
    CEREBRAS_API_KEY = userdata.get("CEREBRAS_API_KEY") or os.getenv("CEREBRAS_API_KEY")
    PARALLEL_API_KEY = userdata.get("PARALLEL_API_KEY") or os.getenv("PARALLEL_API_KEY")
except ImportError:
    CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
    PARALLEL_API_KEY = os.getenv("PARALLEL_API_KEY")

if not CEREBRAS_API_KEY or not PARALLEL_API_KEY:
    raise RuntimeError("Set CEREBRAS_API_KEY and PARALLEL_API_KEY as environment variables.")

cerebras_client = Cerebras(
    api_key=CEREBRAS_API_KEY,
    default_headers={
        "X-Cerebras-3rd-Party-Integration": "parallel-ai-workshop"
    }
)

parallel_client = Parallel(api_key=PARALLEL_API_KEY)

CEREBRAS_MODEL_NAME = "gpt-oss-120B"

print("Clients initialized, model:", CEREBRAS_MODEL_NAME)
```

??? note "輸出"

    ```text
    Clients initialized, model: gpt-oss-120b
    ```

### **Step 2：設定 LLM**

環境準備好之後，建立呼叫 LLM 的函式。


```python
def call_cerebras_chat(
    user_content: str,
    system_content: str | None = None,
    model: str = CEREBRAS_MODEL_NAME,
    temperature: float = 1.0,
    top_p= 1.0,
    max_tokens: int = 4096,
    reasoning_effort: str = "medium"
):
    """
    Calls the Cerebras chat completion API.

    Args:
        user_content (str): The user's message.
        system_content (str | None): Optional system message to guide the LLM.
        model (str): The Cerebras model to use.
        temperature (float): Controls the randomness of the output.
        max_tokens (int): The maximum number of tokens in the response.

    Returns:
        str: The content of the LLM's response.
    """
    messages = []
    # Add a system message to guide the model's behavior
    if system_content:
        messages.append({"role": "system", "content": system_content})

    messages.append({"role": "user", "content": user_content})

    # Make the API call to Cerebras chat completions
    resp = cerebras_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
    )
    return resp.choices[0].message.content
```

### **Step 3：把 LLM 連到網路**

要查核一個 claim，模型需要在網路上找證據，這一步建立把 LLM 連到網路的函式。

注意幾個欄位：

- `objective` 欄位：Bold text 用自然語言描述意圖，而不是關鍵字。

- `one-shot` 模式：為了簡單和速度，這份指南採用 one-shot 設定，一次呼叫就能得到高品質的摘錄。

```python
def search_web(query: str, num: int = 5, mode: str = "one-shot"):
    """
    Search the web using Parallel's Search API.

    Returns a list of dicts with:
      - url
      - title
      - publish_date
      - excerpts (list of strings)
    """

    # Instruct the LLM find quality sources.
    objective = (
        f"Find high-quality, up-to-date sources that answer the question:\n\n{query}\n\n"
        "Prefer authoritative sites (e.g., .gov, .edu, major news, or official org websites)."
    )

    # Initiatiate the LLM for web search
    search = parallel_client.beta.search(
        objective=objective,
        search_queries=[query],
        mode=mode,
        max_results=num,
        excerpts={
            "max_chars_per_result": 8000,
        },
    )

    results = []
    # Process the search results and extract information like URL, title, and excerpts.
    for r in search.results:
        results.append(
            {
                "url": r.url,
                "title": getattr(r, "title", None),
                "publish_date": getattr(r, "publish_date", None),
                "excerpts": list(r.excerpts or []),
            }
        )
    return results
```

### **Step 4：整理並摘要網路結果**

從網路取得資訊後，把它整理成乾淨易讀的格式。這一步會把搜尋結果的關鍵摘錄彙整成簡單的摘要，方便評估。

```python
import textwrap
from typing import List, Dict, Any

def build_evidence_context(results: List[Dict[str, Any]], max_chars: int = 8000) -> str:

    blocks = []
    for idx, r in enumerate(results):
        excerpts_text = "\n\n".join(r["excerpts"][:2])
        block = textwrap.dedent(f"""
        [Source {idx+1}]
        Title: {r['title'] or r['url']}
        URL: {r['url']}
        Publish date: {r['publish_date']}

        Excerpts:
        {excerpts_text}
        """).strip()
        blocks.append(block)

    context = "\n\n".join(blocks)

    if len(context) > max_chars:
        context = context[:max_chars] + "\n\n[Context truncated for length]"
    return context
```

### **Step 5：找出要查證的 claims**

接下來，找出文字裡要查證的具體陳述。不要一次分析整篇文章，而是讓 LLM 把它拆成多個清楚、獨立、可以逐字判斷的 claims。

例如，一小段文字：「The unemployment rate fell to 3.5% in March 2024, and Company X announced a $10B merger the same week.」

LLM 應該抽出個別的事實陳述，像是：

*  “The unemployment rate fell to 3.5% in March 2024.”
*  “Company X announced a $10 billion merger.”

每一個都可以獨立查核，讓整個事實查核流程精準又可靠。

````python
import json
import re
import time

def extract_claims_from_text(text: str, max_claims: int = 8) -> list[str]:
    """
    Use Cerebras LLM to extract atomic factual claims from text.
    Output format (strict JSON):
    {
      "claims": ["...", "."...]
    }
    """
    # Instruct the LLM to extract factual claims
    system_prompt_content = (
        "You are an information extraction assistant.\n"
        "From the user's text, extract up to {max_claims} atomic factual claims.\n"
        "Each claim should:\n"
        "- Be checkable against external sources (dates, numbers, named entities)\n"
        "- Be concrete and not an opinion.\n\n"
        "Return STRICT JSON:\n"
        "{{\n"
        '  "claims": ["...", "..."]\n'
        "}}\n"
    ).format(max_claims=max_claims)

    # Prompt the LLM for claim extraction
    user_prompt_content = f"Text:\n\n{text}\n\nExtract up to {max_claims} factual claims."

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    start_time = time.time()
    # Call Cerebras LLM (gpt-oss-120B) for claim extraction
    resp = cerebras_client.chat.completions.create(
        model=CEREBRAS_MODEL_NAME,
        messages=messages,
        temperature=1.0,
        top_p=1.0,
        max_tokens=4096,
        reasoning_effort="medium",
    )
    raw = resp.choices[0].message.content.strip()
    end_time = time.time()
    print(f"Cerebras LLM claim extraction took {end_time - start_time:.2f} seconds")

    # Clean up the raw JSON output
    raw = re.sub(r"^\s*```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        data = json.loads(raw)
        claims = data.get("claims", [])
        claims = [c.strip() for c in claims if isinstance(c, str) and c.strip()]
        return claims[:max_claims]
    except Exception as e:
        print("Error parsing claims JSON:", e)
        print("Raw model output:\n", raw)
        return []

print("Claim extraction ready")
````

??? note "輸出"

    ```text
    Claim extraction ready
    ```

### **Step 6：用證據檢查 claims（true / false / uncertain）**

收集完 claims 並抽成獨立的事實 claims 之後，LLM 就可以評估每個 claim 並給出判定。流程分兩步：

1) **用 Parallel 取得證據：**
先用 Parallel 查詢和 claim 相關的權威來源。

2) **用 Cerebras 判斷 claim：**
然後把證據和原始 claims 送給 Cerebras 評估。這裡 Cerebras 超快的推論就很關鍵，LLM 可以分析多份證據、權衡互相矛盾的地方，並產生判定。 

模型會回傳三種結構化判定之一：
- **True**：證據支持這個 claim
- **False**：證據反駁這個 claim
- **Uncertain**：證據不足，或來源互相衝突

每個判定都附上說明和引用的 URL，讓模型的推理過程透明。

````python
from typing import Dict, Any
import textwrap
import re
import time

def fact_check_single_claim(claim: str) -> Dict[str, Any]:
    """
    Fact-check a single claim using:
      - Parallel Search for evidence
      - Cerebras LLM for verdict

    Args:
        claim (str): The factual claim to be checked.

    Returns:
        Dict[str, Any]: A dictionary containing the claim, verdict, reason, and sources.
        {
          "claim": str,
          "verdict": "true" | "false" | "uncertain",
          "reason": str,
          "sources": [url, ...]
        }
    """
    print(f"\nFact-checking claim: {claim}")

    # Search the web for evidence relevant to the claim
    results = search_web(query=claim, num=6, mode="one-shot")
    print(f"Retrieved {len(results)} evidence sources")

    # Compile the search results into a clean, readable context for the LLM
    evidence_context = build_evidence_context(results)

    # Define the system prompt to instruct the Cerebras LLM (gpt-oss-120B) on how to evaluate each claim
    system_prompt_content = (
        "You are a careful, skeptical fact-checking assistant.\n"
        "You get a factual claim and web search excerpts.\n"
        "Decide if the evidence supports, contradicts, or does not clearly resolve the claim.\n\n"
        "Respond with STRICT JSON:\n"
        "{\n"
        '  "verdict": "true" | "false" | "uncertain",\n'
        '  "reason": "short explanation",\n'
        '  "top_sources": ["url1", "url2", ...]\n'
        "}\n"
        "Use 'true' only when the evidence strongly supports the claim.\n"
        "Use 'false' only when it clearly contradicts the claim.\n"
        "Otherwise use 'uncertain'."
    )

    # Construct the user prompt
    user_prompt_content = textwrap.dedent(f"""
    Claim:
    {claim}

    Evidence (web search excerpts):
    {evidence_context}
    """)

    messages = [
        {"role": "system", "content": system_prompt_content},
        {"role": "user", "content": user_prompt_content}
    ]

    start_time = time.time()
    # Call the Cerebras LLM (gpt-oss-120B) to get a structured verdict
    resp = cerebras_client.chat.completions.create(
        model=CEREBRAS_MODEL_NAME,
        messages=messages,
        temperature=1.0,
        top_p=1.0,
        max_tokens=4096,    
        reasoning_effort="medium"
    )
    raw = resp.choices[0].message.content.strip()
    end_time = time.time()
    print(f"Cerebras LLM judgment for this claim took {end_time - start_time:.2f} seconds")

    # Clean up the raw JSON output from the LLM
    raw = re.sub(r"^\s*```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        data = json.loads(raw)
    except Exception as e:
        print("Error parsing judgment JSON:", e)
        print("Raw model output:\n", raw)
        data = {
            "verdict": "uncertain",
            "reason": "Could not parse model output.",
            "top_sources": [],
        }

    # Extract and normalize the verdict (true, false, or uncertain)
    verdict = str(data.get("verdict", "uncertain")).lower()
    if verdict not in {"true", "false", "uncertain"}:
        verdict = "uncertain"

    # Extract and format the top sources cited by the LLM
    top_sources = data.get("top_sources") or []
    if not isinstance(top_sources, list):
        top_sources = [str(top_sources)]
    top_sources = [str(u) for u in top_sources][:5]

    # Consolidate all the fact-checking results into a single dictionary
    result = {
        "claim": claim,
        "verdict": verdict,
        "reason": data.get("reason", ""),
        "sources": top_sources,
    }

    # Print the detailed fact-checking result for clarity
    print("Verdict:", result["verdict"].upper())
    print("Reason:", result["reason"])
    if result["sources"]:
        print("Sources:")
        for s in result["sources"]:
            print("  •", s)

    return result

print("Single-claim fact-checker ready")
````

??? note "輸出"

    ```text
    Single-claim fact checker ready
    ```

### **Step 7：對整段文字做事實查核**

這最後一步把所有東西串起來。拿任何一段文字，讓每個 claim 都跑過你建好的完整事實查核流程。

```python
def fact_check_text(text: str, max_claims: int = 6):
    # First, extract factual claims from the input text
    claims = extract_claims_from_text(text, max_claims=max_claims)

    print(f"Extracted {len(claims)} claims:")
    for i, c in enumerate(claims, 1):
        print(f"  {i}. {c}")

    all_results = []
    # Iterate through each extracted claim and perform a single fact-check
    for i, claim in enumerate(claims):
        print(f"\n{'='*50}\nFact-checking Claim {i+1} of {len(claims)}: '{claim}'")
        single_claim_result = fact_check_single_claim(claim)
        all_results.append(single_claim_result)
        print(f"{'='*50}")

    # After all claims are checked, print a summary of all results
    print("\n\n--- Summary of All Fact-Checking Results ---\n")
    for result in all_results:
        print(f"Claim: {result['claim']}")
        print(f"Verdict: {result['verdict'].upper()}")
        print(f"Reason: {result['reason']}")
        if result['sources']:
            print("Sources:")
            for s in result['sources']:
                print(f"  • {s}")
        print("\n" + "-"*50 + "\n")

    return all_results

print("Full fact-checking pipeline ready")
```

??? note "輸出"

    ```text
    Full fact-checking pipeline ready
    ```

### **Step 8：直接從 URL 做事實查核**
最後，為了讓查核器更好用，加一個直接接受 URL 的函式。

```python
import requests
from bs4 import BeautifulSoup

def extract_claims_from_url(url: str, max_claims: int = 8) -> list[str]:
    """
    Extracts atomic factual claims from the main content of a given URL.
    Fetches content using requests/BeautifulSoup and uses Cerebras LLM for claim extraction.
    """
    print(f"Fetching content from URL: {url}")
    try:
        # Fetch the content of the URL
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Attempt to find the main content by looking for 'article' or 'main' tags
        main_content_div = soup.find('article') or soup.find('main')
        if main_content_div:
            main_text = ' '.join([p.get_text() for p in main_content_div.find_all('p')])
        else:
            main_text_elements = soup.find_all(['p', 'h1', 'h2', 'h3'])
            main_text = ' '.join([elem.get_text() for elem in main_text_elements])

        # Check if enough text was extracted
        if not main_text or len(main_text.strip()) < 100:
            print(f"Warning: Not enough main text found for URL: {url}")
            return []

        print(f"Extracted {len(main_text)} characters from the URL. Now extracting claims...")
        # Use the LLM to extract claims from the cleaned text
        claims = extract_claims_from_text(main_text, max_claims=max_claims)
        return claims
    except requests.exceptions.RequestException as e:
        print(f"Error fetching content from URL {url}: {e}")
        return []
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        return []

print("URL claim extraction function ready")
```

??? note "輸出"

    ```text
    URL claim extraction function ready
    ```

### **範例**

先從一小段範例文字開始。

```python
sample_text = """\nThe Earth is flat and the moon is made of cheese. Humans landed on Mars in 1969. Albert Einstein was born in Germany in 1879.\n"""

print("Fact-checking the following text:\n")
print(sample_text)

fact_check_results = fact_check_text(sample_text)

display(fact_check_results)
```

??? note "輸出"

    ```text
    Fact-checking the following text:


    The Earth is flat and the moon is made of cheese. Humans landed on Mars in 1969. Albert Einstein was born in Germany in 1879.

    Cerebras LLM claim extraction took 0.34 seconds
    Extracted 5 claims:
      1. The Earth is flat.
      2. The moon is made of cheese.
      3. Humans landed on Mars in 1969.
      4. Albert Einstein was born in Germany.
      5. Albert Einstein was born in 1879.

    ==================================================
    Fact-checking Claim 1 of 5: 'The Earth is flat.'

    Fact-checking claim: The Earth is flat.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 0.39 seconds
    Verdict: FALSE
    Reason: The provided sources explain that scientific evidence demonstrates the Earth is a sphere and that flat‑Earth beliefs are a debunked conspiracy, directly contradicting the claim.
    Sources:
      • https://pursuit.unimelb.edu.au/articles/why-do-some-people-believe-the-earth-is-flat
    ==================================================

    ==================================================
    Fact-checking Claim 2 of 5: 'The moon is made of cheese.'

    Fact-checking claim: The moon is made of cheese.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 0.30 seconds
    Verdict: FALSE
    Reason: NASA scientific sources describe the Moon's composition as layered rock, iron, silicon, magnesium, etc., with no indication of cheese, directly contradicting the claim.
    Sources:
      • https://science.nasa.gov/moon/composition/
    ==================================================

    ==================================================
    Fact-checking Claim 3 of 5: 'Humans landed on Mars in 1969.'

    ... (省略 79 行)
    ```

    ```text
    [{'claim': 'The Earth is flat.',
      'verdict': 'false',
      'reason': 'The provided sources explain that scientific evidence demonstrates the Earth is a sphere and that flat‑Earth beliefs are a debunked conspiracy, directly contradicting the claim.',
      'sources': ['https://pursuit.unimelb.edu.au/articles/why-do-some-people-believe-the-earth-is-flat']},
     {'claim': 'The moon is made of cheese.',
      'verdict': 'false',
      'reason': "NASA scientific sources describe the Moon's composition as layered rock, iron, silicon, magnesium, etc., with no indication of cheese, directly contradicting the claim.",
      'sources': ['https://science.nasa.gov/moon/composition/']},
     {'claim': 'Humans landed on Mars in 1969.',
      'verdict': 'false',
      'reason': 'The evidence shows that in 1969 NASA conducted unmanned Mars flyby missions (Mariner 6 and 7) and a manned Moon landing, with no indication of humans landing on Mars.',
      'sources': ['https://www.facebook.com/groups/jameswebbtelescopecosmicexplorations/posts/762176293540444/',
       'https://www.jpl.nasa.gov/missions/mariner-7/']},
     {'claim': 'Albert Einstein was born in Germany.',
      'verdict': 'true',
      'reason': 'Wikipedia describes Einstein as a German-born theoretical physicist, confirming he was born in Germany.',
      'sources': ['https://en.wikipedia.org/wiki/Albert_Einstein',
       'https://www.nobelprize.org/prizes/physics/1921/einstein/biographical/']},
     {'claim': 'Albert Einstein was born in 1879.',
      'verdict': 'true',
      'reason': "The Wikipedia entry lists Einstein's birthdate as 14 March 1879, confirming the claim.",
      'sources': ['https://en.wikipedia.org/wiki/Albert_Einstein']}]
    ```

現在貼上一段 400 字的陳述，看看查核器怎麼說。 

[注意：這是一段為了測試內容查核器而設計的綜合文字範例，裡面有看似合理但其實捏造的 claims。]

```python
long_sample_text = """
In recent months, a number of widely shared posts and articles have circulated online making bold claims about technology, science, and public health. One viral thread asserted that Apple released the world’s first smartphone in 1992, long before the launch of the iPhone. The post claimed the device had a touchscreen, mobile internet capabilities, and even early forms of voice control. In reality, Apple did not release a smartphone in 1992, and the first widely recognized smartphone, the IBM Simon, was introduced in 1994 with far more limited features. The iPhone, launched in 2007, is credited with defining the modern smartphone era.

Another widely repeated claim stated that Mount Everest has shrunk by more than 500 meters due to rapid climate change. Several posts argued that melting ice and tectonic shifts had dramatically reduced the mountain’s height, supposedly confirmed by new satellite imagery. Geologists and survey data contradict this, showing that Everest’s height has changed only minimally over time. Recent revisions to Everest’s official height reflect improved measurement technology—not catastrophic geological change or the environmental collapse suggested online.

A sensational article suggested that NASA announced Earth will experience 15 days of complete darkness in November 2025 because of a rare planetary alignment. This claim resurfaces every few years in slightly different forms, yet NASA has consistently debunked every version of it. Astronomers explain that no known configuration of planets could block sunlight from reaching Earth for even a single day, let alone two weeks.

Another persistent piece of misinformation claimed that COVID-19 vaccines contain microchips designed for government tracking. Public health organizations worldwide have addressed this rumor repeatedly, stating unequivocally that no such technology exists in vaccines and that microelectronics cannot function or survive in biological environments in the way conspiracy theories suggest. Despite extensive scientific communication, this claim continues to spread across certain corners of the internet.

More recently, a trending health blog claimed that drinking eight cups of coffee per day reduces the risk of heart disease by 70%. While moderate coffee consumption has been studied for potential health benefits, no reputable research supports the exaggerated 70% figure promoted in the article. Excessive caffeine intake can create health concerns for many individuals, including increased heart rate, anxiety, and disrupted sleep.

In the tech sector, several posts gained traction by asserting that electric vehicles routinely explode in temperatures above 80 degrees Fahrenheit. Critics use this claim to argue that EVs pose unique safety threats. However, investigations by fire departments, insurance groups, and automotive engineers show no evidence of spontaneous combustion linked to moderate ambient temperatures. Vehicle fires—when they do occur—typically result from accidents, mechanical failures, or battery punctures, not temperature alone.

Another claim circulating widely suggests that major tech companies are secretly restricting home Wi-Fi speeds to force consumers into new subscription tiers. Internet service providers and independent network analysts have found no support for this, noting that slowdowns are far more commonly caused by outdated hardware, overcrowded networks, or poor signal placement within the home.

"""

print("Fact-checking the following longer text:\n")
print(long_sample_text[:500] + ('...' if len(long_sample_text) > 500 else ''))

long_fact_check_results = fact_check_text(long_sample_text)

display(long_fact_check_results)
```

??? note "輸出"

    ```text
    Fact-checking the following longer text:


    In recent months, a number of widely shared posts and articles have circulated online making bold claims about technology, science, and public health. One viral thread asserted that Apple released the world’s first smartphone in 1992, long before the launch of the iPhone. The post claimed the device had a touchscreen, mobile internet capabilities, and even early forms of voice control. In reality, Apple did not release a smartphone in 1992, and the first widely recognized smartphone, the IBM Si...
    Cerebras LLM claim extraction took 0.56 seconds
    Extracted 6 claims:
      1. Apple did not release a smartphone in 1992; the first widely recognized smartphone, the IBM Simon, was introduced in 1994.
      2. The iPhone was launched in 2007 and is credited with defining the modern smartphone era.
      3. Mount Everest has not shrunk by more than 500 meters; its height has changed only minimally and recent revisions reflect improved measurement technology.
      4. NASA has debunked claims that Earth will experience 15 days of complete darkness in November 2025 due to a planetary alignment, stating no known configuration can block sunlight for that duration.
      5. COVID‑19 vaccines do not contain microchips for government tracking; no such microelectronics are present in any authorized vaccine.
      6. Drinking eight cups of coffee per day does not reduce the risk of heart disease by 70%; no reputable research supports that specific reduction figure.

    ==================================================
    Fact-checking Claim 1 of 6: 'Apple did not release a smartphone in 1992; the first widely recognized smartphone, the IBM Simon, was introduced in 1994.'

    Fact-checking claim: Apple did not release a smartphone in 1992; the first widely recognized smartphone, the IBM Simon, was introduced in 1994.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 0.40 seconds
    Verdict: UNCERTAIN
    Reason: The evidence clearly shows IBM Simon was first released in 1994, supporting that part of the claim. However, there is no explicit evidence provided about Apple not releasing a smartphone in 1992, so the claim cannot be fully verified.
    Sources:
      • https://en.wikipedia.org/wiki/IBM_Simon
      • https://en.wikipedia.org/wiki/Smartphone
    ==================================================

    ==================================================
    Fact-checking Claim 2 of 6: 'The iPhone was launched in 2007 and is credited with defining the modern smartphone era.'

    Fact-checking claim: The iPhone was launched in 2007 and is credited with defining the modern smartphone era.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 0.35 seconds
    Verdict: TRUE
    Reason: The evidence confirms the iPhone was first released on June 29 2007 and describes it as a revolutionary device that "reinvented" the phone, indicating it is widely credited with defining the modern smartphone era.
    Sources:
      • https://en.wikipedia.org/wiki/IPhone_(1st_generation)
      • https://theprint.in/features/brandma/iphone-1-a-revolutionary-smartphone-that-debuted-at-the-2007-oscars/889755/
    ==================================================

    ==================================================
    ... (省略 107 行)
    ```

    ```text
    [{'claim': 'Apple did not release a smartphone in 1992; the first widely recognized smartphone, the IBM Simon, was introduced in 1994.',
      'verdict': 'uncertain',
      'reason': 'The evidence clearly shows IBM Simon was first released in 1994, supporting that part of the claim. However, there is no explicit evidence provided about Apple not releasing a smartphone in 1992, so the claim cannot be fully verified.',
      'sources': ['https://en.wikipedia.org/wiki/IBM_Simon',
       'https://en.wikipedia.org/wiki/Smartphone']},
     {'claim': 'The iPhone was launched in 2007 and is credited with defining the modern smartphone era.',
      'verdict': 'true',
      'reason': 'The evidence confirms the iPhone was first released on June\u202f29\u202f2007 and describes it as a revolutionary device that "reinvented" the phone, indicating it is widely credited with defining the modern smartphone era.',
      'sources': ['https://en.wikipedia.org/wiki/IPhone_(1st_generation)',
       'https://theprint.in/features/brandma/iphone-1-a-revolutionary-smartphone-that-debuted-at-the-2007-oscars/889755/']},
     {'claim': 'Mount Everest has not shrunk by more than 500\u202fmeters; its height has changed only minimally and recent revisions reflect improved measurement technology.',
      'verdict': 'true',
      'reason': 'The sources state that Everest’s height is now 8,848.86\u202fm, noting only slight adjustments from earlier measurements due to better technology and minor natural effects, with no indication of a shrinkage anywhere near 500\u202fm.',
      'sources': ['https://www.himalayanrecreation.com/blog/the-height-of-mount-everest',
       'https://www.britannica.com/place/Mount-Everest']},
     {'claim': 'NASA has debunked claims that Earth will experience 15\u202fdays of complete darkness in November\u202f2025 due to a planetary alignment, stating no known configuration can block sunlight for that duration.',
      'verdict': 'uncertain',
      'reason': 'The provided sources debunk similar 15‑day darkness hoaxes for 2015/2017 and state NASA never confirmed such an event, but none specifically address a claimed November\u202f2025 event, so the claim is not directly supported or contradicted.',
      'sources': ['https://www.snopes.com/fact-check/15-days-darkness-november/',
       'https://www.space.com/31118-earth-darkness-hoax-debunked.html']},
     {'claim': 'COVID‑19 vaccines do not contain microchips for government tracking; no such microelectronics are present in any authorized vaccine.',
      'verdict': 'true',
      'reason': 'Multiple reputable sources explicitly state that COVID‑19 vaccines contain no microchips or any tracking hardware, directly confirming the claim.',
      'sources': ['https://revealnews.org/article/where-did-the-microchip-vaccine-conspiracy-theory-come-from-anyway/',
       'https://www.mayoclinic.org/diseases-conditions/coronavirus/in']},
     {'claim': 'Drinking eight cups of coffee per day does not reduce the risk of heart disease by 70%; no reputable research supports that specific reduction figure.',
      'verdict': 'true',
      'reason': 'The cited review shows mixed or even increased risk with heavy coffee consumption and does not report a 70% reduction in heart disease risk for eight cups per day, indicating no reputable research supports that specific figure.',
      'sources': ['https://pmc.ncbi.nlm.nih.gov/articles/PMC10262944/',
       'https://www.escardio.org/The-ESC/Press-Office/Press-releases/morning-coffee-may-protect-the-heart-better-than-all-day-coffee-drinking']}]
    ```

直接貼一個 URL 連結。

```python
current_doc_url = "https://www.snopes.com/fact-check/drinking-at-disney-world/"
print(f"Extracting and fact-checking claims from: {current_doc_url}")

url_extracted_claims = extract_claims_from_url(current_doc_url)

if url_extracted_claims:
    print(f"\nSuccessfully extracted {len(url_extracted_claims)} claims from the URL. Now fact-checking them...")
    claims_text_for_fact_check = "\n".join(url_extracted_claims)
    url_fact_check_results = fact_check_text(claims_text_for_fact_check)
    display(url_fact_check_results)
else:
    print("Could not extract claims from the URL to fact-check.")
```

??? note "輸出"

    ```text
    Extracting and fact-checking claims from: https://www.snopes.com/fact-check/drinking-at-disney-world/
    Fetching content from URL: https://www.snopes.com/fact-check/drinking-at-disney-world/
    Extracted 1820 characters from the URL. Now extracting claims...
    Cerebras LLM claim extraction took 0.57 seconds

    Successfully extracted 8 claims from the URL. Now fact-checking them...
    Cerebras LLM claim extraction took 0.67 seconds
    Extracted 6 claims:
      1. On September 9, 2023, Mouse Trap News published an article claiming that the Walt Disney World Resort had officially removed the drinking age.
      2. The TikTok video posted by @mousetrapnews had 8.8 million views at the time of this check.
      3. Mouse Trap News states on its About page that every story on its website is fake and that it is a satire site.
      4. The Pensacola News Journal reported that Disney World was still allowed to sell alcohol only to adults aged 21 or older at the time of the writing.
      5. Mouse Trap News previously made a claim that Disney World was supposedly lobbying to lower the drinking age at the resort to 18.
      6. Disney World’s policy permits the sale of alcohol only to guests who are 21 years of age or older.

    ==================================================
    Fact-checking Claim 1 of 6: 'On September 9, 2023, Mouse Trap News published an article claiming that the Walt Disney World Resort had officially removed the drinking age.'

    Fact-checking claim: On September 9, 2023, Mouse Trap News published an article claiming that the Walt Disney World Resort had officially removed the drinking age.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 2.21 seconds
    Verdict: UNCERTAIN
    Reason: The available sources discuss rumors about Disney lowering its drinking age and debunk them, but they do not directly confirm that Mouse Trap News published an article on September 9, 2023 making that claim.
    Sources:
      • https://www.pnj.com/story/news/2023/09/11/disney-world-remove-legal-drinking-age-requirement-florida-debunked/70822543007/
      • https://www.aol.com/news/fact-fiction-disney-world-lobbying-040148528.html
    ==================================================

    ==================================================
    Fact-checking Claim 2 of 6: 'The TikTok video posted by @mousetrapnews had 8.8 million views at the time of this check.'

    Fact-checking claim: The TikTok video posted by @mousetrapnews had 8.8 million views at the time of this check.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 0.34 seconds
    Verdict: UNCERTAIN
    Reason: The provided excerpts do not include any view count for the specific TikTok video, so they neither confirm nor refute the claim of 8.8 million views.
    Sources:
      • https://www.tiktok.com/@mousetrapnews/video/7590889191806995743
      • https://www.tiktok.com/@mousetrapnews/video/7485897545890336046
    ==================================================
    ... (省略 109 行)
    ```

    ```text
    [{'claim': 'On September 9, 2023, Mouse Trap News published an article claiming that the Walt Disney World Resort had officially removed the drinking age.',
      'verdict': 'uncertain',
      'reason': 'The available sources discuss rumors about Disney lowering its drinking age and debunk them, but they do not directly confirm that Mouse Trap News published an article on September 9, 2023 making that claim.',
      'sources': ['https://www.pnj.com/story/news/2023/09/11/disney-world-remove-legal-drinking-age-requirement-florida-debunked/70822543007/',
       'https://www.aol.com/news/fact-fiction-disney-world-lobbying-040148528.html']},
     {'claim': 'The TikTok video posted by @mousetrapnews had 8.8 million views at the time of this check.',
      'verdict': 'uncertain',
      'reason': 'The provided excerpts do not include any view count for the specific TikTok video, so they neither confirm nor refute the claim of 8.8\u202fmillion views.',
      'sources': ['https://www.tiktok.com/@mousetrapnews/video/7590889191806995743',
       'https://www.tiktok.com/@mousetrapnews/video/7485897545890336046']},
     {'claim': 'Mouse Trap News states on its About page that every story on its website is fake and that it is a satire site.',
      'verdict': 'true',
      'reason': 'The About page explicitly describes Mouse Trap News as a satire/parody site and states that its stories are made‑up and not true, confirming that the site claims all its content is fake. A Facebook post also refers to it as a satirical site.',
      'sources': ['https://mousetrapnews.com/about/',
       'https://www.facebook.com/groups/276199024736470/posts/358951296461242/']},
     {'claim': 'The Pensacola News Journal reported that Disney World was still allowed to sell alcohol only to adults aged 21 or older at the time of the writing.',
      'verdict': 'true',
      'reason': 'The Pensacola News Journal article explicitly states Disney World’s alcohol policy limits sales to guests 21 years old or older, confirming the claim.',
      'sources': ['https://www.pnj.com/story/news/2023/09/11/disney-world-remove-legal-drinking-age-requirement-florida-debunked/70822543007/',
       'https://disneyworld.disney.go.com/faq/restaurants/required-id-for-alcohol/']},
     {'claim': 'Mouse Trap News previously made a claim that Disney World was supposedly lobbying to lower the drinking age at the resort to 18.',
      'verdict': 'true',
      'reason': 'The Mouse Trap News article titled “Drinking Age at Disney World May be Lowered to 18” explicitly states that Disney World is lobbying to lower the drinking age, confirming that Mouse Trap News made this claim.',
      'sources': ['https://mousetrapnews.com/drinking-age-at-disney-world-may-be-lowered-to-18/',
       'https://www.10news.com/news/fact-or-fiction/fact-or-fiction-disney-world-lobbying-to-lower-drinking-age-on-florida-property']},
     {'claim': 'Disney World’s policy permits the sale of alcohol only to guests who are 21 years of age or older.',
      'verdict': 'true',
      'reason': 'Official Disney World FAQ states alcoholic beverages can be purchased only by guests 21\u202fyears or older, confirming the policy.',
      'sources': ['https://disneyworld.disney.go.com/faq/restaurants/required-id-for-alcohol/',
       'https://www.disneyfoodblog.com/2023/10/08/the-one-rule-about-drinking-in-disney-world-you-need-to-know/']}]
    ```

這是另一個 URL 的範例。

```python
article_url = "https://theonion.com/shedeur-sanders-confident-he-can-deliver-everything-browns-fans-have-come-to-expect/"

print(f"Extracting and fact-checking claims from: {article_url}")

claims_from_url = extract_claims_from_url(article_url)

if claims_from_url:
    print(f"\nSuccessfully extracted {len(claims_from_url)} claims from the URL. Now fact-checking them...")

    claims_text_for_fact_check = "\n".join(claims_from_url)

    fact_check_results = fact_check_text(claims_text_for_fact_check)

    display(fact_check_results)
else:
    print("Could not extract claims from the URL to fact-check.")
```

??? note "輸出"

    ```text
    Extracting and fact-checking claims from: https://theonion.com/shedeur-sanders-confident-he-can-deliver-everything-browns-fans-have-come-to-expect/
    Fetching content from URL: https://theonion.com/shedeur-sanders-confident-he-can-deliver-everything-browns-fans-have-come-to-expect/
    Extracted 1224 characters from the URL. Now extracting claims...
    Cerebras LLM claim extraction took 0.45 seconds

    Successfully extracted 8 claims from the URL. Now fact-checking them...
    Cerebras LLM claim extraction took 0.28 seconds
    Extracted 6 claims:
      1. Shedeur Sanders is a rookie quarterback for the Cleveland Browns.
      2. Shedeur Sanders was selected in the fifth round of the NFL Draft.
      3. He is the 42nd starting quarterback for the Browns since 1999.
      4. The Browns had a 2–8 record at the time of the interview.
      5. Dillon Gabriel previously started as quarterback for the Browns.
      6. Shedeur Sanders expects to lose the starting quarterback job to Bailey Zappe after two weeks.

    ==================================================
    Fact-checking Claim 1 of 6: 'Shedeur Sanders is a rookie quarterback for the Cleveland Browns.'

    Fact-checking claim: Shedeur Sanders is a rookie quarterback for the Cleveland Browns.
    Retrieved 5 evidence sources
    Cerebras LLM judgment for this claim took 0.42 seconds
    Verdict: TRUE
    Reason: The Browns roster page lists Shedeur Sanders with experience marked as 'R' (rookie) and notes he was drafted in 2025, confirming he is a rookie quarterback for Cleveland.
    Sources:
      • https://www.clevelandbrowns.com/team/players-roster/shedeur-sanders/
    ==================================================

    ==================================================
    Fact-checking Claim 2 of 6: 'Shedeur Sanders was selected in the fifth round of the NFL Draft.'

    Fact-checking claim: Shedeur Sanders was selected in the fifth round of the NFL Draft.
    Retrieved 6 evidence sources
    Cerebras LLM judgment for this claim took 0.84 seconds
    Verdict: TRUE
    Reason: Both sources state Shedeur Sanders was chosen with the 144th overall pick, which corresponds to the fifth round of the 2025 NFL Draft.
    Sources:
      • https://www.clevelandbrowns.com/video/browns-select-shedeur-sanders-with-no-144-pick-in-2025-draft
      • https://www.clevelandbrowns.com/news/browns-select-qb-shedeur-sanders-with-the-no-144-pick-in-the-2025-nfl-draft
    ==================================================

    ... (省略 103 行)
    ```

    ```text
    [{'claim': 'Shedeur Sanders is a rookie quarterback for the Cleveland Browns.',
      'verdict': 'true',
      'reason': "The Browns roster page lists Shedeur Sanders with experience marked as 'R' (rookie) and notes he was drafted in 2025, confirming he is a rookie quarterback for Cleveland.",
      'sources': ['https://www.clevelandbrowns.com/team/players-roster/shedeur-sanders/']},
     {'claim': 'Shedeur Sanders was selected in the fifth round of the NFL Draft.',
      'verdict': 'true',
      'reason': 'Both sources state Shedeur Sanders was chosen with the 144th overall pick, which corresponds to the fifth round of the 2025 NFL Draft.',
      'sources': ['https://www.clevelandbrowns.com/video/browns-select-shedeur-sanders-with-no-144-pick-in-2025-draft',
       'https://www.clevelandbrowns.com/news/browns-select-qb-shedeur-sanders-with-the-no-144-pick-in-the-2025-nfl-draft']},
     {'claim': 'He is the 42nd starting quarterback for the Browns since 1999.',
      'verdict': 'true',
      'reason': 'The Wikipedia article states that from 1999 through mid‑2025 the Browns have had 42 players start at quarterback, confirming that the most recent starter is indeed the 42nd.',
      'sources': ['https://en.wikipedia.org/wiki/List_of_Cleveland_Browns_starting_quarterbacks']},
     {'claim': 'The Browns had a 2–8 record at the time of the interview.',
      'verdict': 'true',
      'reason': 'A news article from November 22, 2015 explicitly states the Browns were 2‑8 at that time, which aligns with the claim about the interview timing.',
      'sources': ['https://www.tribtoday.com/uncategorized/2015/11/browns-2-8-record-has-been-a-team-effort/']},
     {'claim': 'Dillon Gabriel previously started as quarterback for the Browns.',
      'verdict': 'true',
      'reason': "The evidence shows Gabriel was named the Browns' starter for a game on October 5, 2025, indicating he has previously started as quarterback for Cleveland.",
      'sources': ['https://en.wikipedia.org/wiki/Dillon_Gabriel',
       'https://www.sports-reference.com/cfb/players/dillon-gabriel-1.html']},
     {'claim': 'Shedeur Sanders expects to lose the starting quarterback job to Bailey Zappe after two weeks.',
      'verdict': 'uncertain',
      'reason': "The provided sources show Bailey Zappe being elevated as a backup to Shedeur Sanders and discuss uncertainty about Sanders' future, but none mention Sanders expecting to lose his starting job within two weeks.",
      'sources': ['https://www.nbcsports.com/nfl/profootballtalk/rumor-mill/news/browns-elevate-bailey-zappe-to-back-up-shedeur-sanders',
       'https://sports.yahoo.com/nfl/article/what-does-browns-firing-kevin-stefanski-mean-for-shedeur-sanders-062323054.html']}]
    ```

這樣你就成功用 gpt-oss-120B、Cerebras 和 Parallel 做出一個事實查核器了！



**⚠️ 免責聲明：**


這份指南純粹是教學用的起點。為了簡單，這裡的程式碼略過了幾個 production 要考慮的問題，像是 prompt injection、輸入清理和更嚴格的輸出驗證。如果你要把它做成真正的應用程式，要加上這些保護。 

**貢獻者**

這份指南是 OpenAI、[Cerebras Systems](https://www.cerebras.ai/) 和 [Parallel Web Systems](https://parallel.ai/) 共同合作的成果，感謝下列人員寶貴的回饋與支持。 

- Vaibhav Srivastav
- Dominik Kundel
- Sarah Chieng
- Sebastian Duerr
- Matt Harris 
- Lukas Levert
- Joyce Er
- Kevin Taylor
- Khushi Shelat

## 重點整理
- 事實查核的關鍵是先把文章拆成獨立、可驗證的 claims，再逐一查。
- 搜尋用 `objective` 這種自然語言意圖，比關鍵字更能找到好證據。
- 證據檢索（Parallel）和判斷（Cerebras 上的 LLM）分開，各做擅長的事。
- 判定限制成 True / False / Uncertain 並附 URL，輸出才好檢查。
- 這份範例沒處理 prompt injection 等問題，上 production 前要補。

## 練習
1. 修改 Step 5 抽 claims 的 prompt，限制每段文字最多抽 5 個 claims，觀察結果變化。
2. 在 Step 6 的判定輸出加一個 confidence 欄位（0 到 1），並顯示在最後結果裡。
3. 對 Step 7 的逐個 claim 查核改成平行執行（例如 `ThreadPoolExecutor`），比較總耗時。
