---
translated: true
source: examples/gpt-5/gpt-5_frontend.ipynb
---
# 用 GPT-5 寫前端

> 原文：[examples/gpt-5/gpt-5_frontend.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/gpt-5_frontend.ipynb)



## 這篇在做什麼

用 GPT-5 一次生成完整的前端網站，從零開始做、換風格、參考既有設計稿加頁面，到做出會動的小遊戲。每個範例都只靠一行 prompt 打一次 API，再把產出的 HTML 直接渲染出來看。

## 學完你會

- 寫一個 helper，把 GPT-5 生成的網頁存下來並在 notebook 裡預覽
- 用一行 prompt 改整個網站的主題與風格
- 把設計稿截圖丟給模型，讓新頁面跟既有介面風格一致

## 開跑前

需要 OpenAI API key，並設定好環境變數。


GPT-5 在前端開發上進步很多。我們看到它能一次生成完整的 full stack 應用、讓複雜的重構變得簡單，也能在大型 codebase 裡做精準的小修改。

這篇會用幾個範例，分享用 GPT-5 開發前端應用的一些心得。

## 簡介
有幾個原則在做出好的前端應用時很有效，我們整理在 [prompt guide](https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide) 裡。下面是做前端時值得考慮的重點。

建議一開始用這些函式庫和套件來引導模型：
- Frameworks：Next.js (TypeScript)、React、HTML
- Styling / UI：Tailwind CSS、shadcn/ui、Radix Themes
- Icons：Material Symbols、Heroicons、Lucide
- Animation：Motion
- Fonts：San Serif、Inter、Geist、Mona Sans、IBM Plex Sans、Manrope

這份清單沒有涵蓋所有選擇，我們也看過很多不同風格的應用。

下面提供一個簡單的方式，讓你透過 API 反覆調整前端的各種抽象。期待看到大家用 GPT-5 發揮創意。


## 互動範例

我們從零開始做幾個前端。先寫幾個 helper function，用來查看 GPT-5 生成的網站。

````python
import os
import re
import webbrowser
from pathlib import Path

import openai
from openai.types.responses import ResponseInputParam

client = openai.OpenAI()


def get_response_output_text(input: str | ResponseInputParam):
    
    response = client.responses.create(
        model="gpt-5",
        input=input,
    )
    return response.output_text


def extract_html_from_text(text: str):
    """Extract an HTML code block from text; fallback to first code block, else full text."""
    html_block = re.search(r"```html\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if html_block:
        result = html_block.group(1)
        return result
    any_block = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if any_block:
        result = any_block.group(1)
        return result
    return text


def save_html(html: str, filename: str) -> Path:
    """Save HTML to outputs/ directory and return the path."""
    try:
        base_dir = Path(__file__).parent
    except NameError:
        base_dir = Path.cwd()

    folder = "outputs"
    outputs_dir = base_dir / folder
    outputs_dir.mkdir(parents=True, exist_ok=True)

    output_path = outputs_dir / filename
    output_path.write_text(html, encoding="utf-8")
    return output_path

def open_in_browser(path: Path) -> None:
    """Open a file in the default browser (macOS compatible)."""
    try:
        webbrowser.open(path.as_uri())
    except Exception:
        os.system(f'open "{path}"')
````

接著把上面的東西合成一個 helper function。

```python
def make_website_and_open_in_browser(*, website_input: str | ResponseInputParam, filename: str = "website.html"):
    response_text = get_response_output_text(website_input)
    html = extract_html_from_text(response_text)
    output_path = save_html(html, filename)
    open_in_browser(output_path)
```

先從簡單的開始：一次生成一個主題正確的復古遊戲商店。

```python
make_website_and_open_in_browser(
    website_input="Make me landing page for a retro-games store. Retro-arcade noir some might say",
    filename="retro_dark.html",
)
```

??? note "輸出"

    ```text
    get_response: finished
    extract_html_from_text: finished (raw text)
    save_html: finished -> outputs/retro_dark.html
    open_in_browser: finished
    ```

一行 prompt、一次生成，結果不錯。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retro_dark.png" style="width:60vw; display:block; margin:auto;">


現在引導它改成比較亮、比較柔和的風格。

```python
make_website_and_open_in_browser(
    website_input="Make me landing page for a retro-games store. Make it light, more pastel coloured & flowery (think Mario, not cyberpunk)", 
    filename="retro_light.html"
)
```

??? note "輸出"

    ```text
    get_response: finished
    extract_html_from_text: finished (raw text)
    save_html: finished -> outputs/retro_light.html
    open_in_browser: finished
    ```

可以看到 GPT-5 很好引導，一行字就能輕鬆改掉整個應用的樣子。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retro_light.png" style="width:60vw; display:block; margin:auto;">

那如果你已經有網站設計，想在上面加東西呢？例如我們已經有這個 dashboard。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/input_image.png" style="width:60vw; display:block; margin:auto;">

GPT-5 原生支援多模態，可以同時吃圖片和文字輸入，所以生成前端時可以用圖片輸入來提升效果。

```python
import base64
from openai.types.responses import ResponseInputImageParam

# Function to encode the image
def encode_image(image_path: str):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

image_path="../../images/input_image.png"
encoded_image = encode_image(image_path)
input_image: ResponseInputImageParam = {"type": "input_image", "image_url": f"data:image/png;base64,{encoded_image}", "detail": "auto"}
input: ResponseInputParam = [
    {
        "role": "user",
        "content": [
            {"type": "input_text", "text": "Can you make a login page for this website that maintains the same theme"},
            input_image,
        ],
    }
]

make_website_and_open_in_browser(
    website_input=input, 
    filename="login_page.html"
)
```

??? note "輸出"

    ```text
    get_response: finished
    extract_html_from_text: finished (raw text)
    save_html: finished -> outputs/login_page.html
    open_in_browser: finished
    ```

可以看到 GPT-5 把既有應用的風格和氛圍抓得很準。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/login_page.png" style="width:60vw; display:block; margin:auto;">

到目前為止都是靜態的，來試一個互動性更高的任務。

```python
make_website_and_open_in_browser(
    website_input="Make me a snake game. It should be futuristic, neon, cyberpunk style. Make sure the typography is suitably cool.", 
    filename="snake_game.html"
)
```

??? note "輸出"

    ```text
    get_response: finished
    extract_html_from_text: finished (raw text)
    save_html: finished -> outputs/snake_game.html
    open_in_browser: finished
    ```

我們得到一個主題一致的貪食蛇遊戲：配色、字體，連音效都對得上。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/snake_game.png" style="width:60vw; display:block; margin:auto;">

一個沒寫清楚的 prompt 就能在一次 API call 生成前端程式碼，但要上 production 還是得 review 和反覆調整。

現在換你了，期待看到你做出什麼。

```python
your_prompt = "[edit this! what website would you like to build?]"

make_website_and_open_in_browser(
    website_input=your_prompt, 
    filename="your_website.html"
)
```

??? note "輸出"

    ```text
    get_response: finished
    extract_html_from_text: finished (raw text)
    save_html: finished -> outputs/your_website.html
    open_in_browser: finished
    ```

## 重點整理

- GPT-5 一行 prompt 就能生成整個前端，改風格也只要改那一行。
- 在 prompt 裡指定框架、樣式、icon、字型，可以讓產出更穩定。
- 提供設計稿圖片能讓新頁面貼近既有風格，因為模型是原生多模態。
- 生成的程式碼只是起點，上線前仍需要 review 與迭代。

## 練習

1. 把復古遊戲商店的 prompt 主題換成別的（例如咖啡店），看生成結果有什麼變化。
2. 在 prompt 裡明確指定用 Tailwind CSS 和 Lucide icons，對比有沒有指定的差別。
3. 換一張你自己的 dashboard 截圖當輸入，請它多加一個設定頁，檢查風格是否一致。
