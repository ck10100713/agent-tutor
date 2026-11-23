---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/multimodal/image-gen-models-prompting-guide.ipynb
---
# GPT 圖像生成模型 Prompting 指南

> 原文：[examples/multimodal/image-gen-models-prompting-guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/image-gen-models-prompting-guide.ipynb)

教你怎麼下 prompt，讓 gpt-image 系列模型穩定產出想要的圖。

## 這篇在做什麼

這篇是 gpt-image 模型的 prompting 手冊，整理了模型參數、寫 prompt 的基本原則，還有文字生圖、改圖兩大類共二十多種實際案例。每個案例都附完整程式碼和輸出的圖，可以直接拿去改。

## 學完你會

- 看得懂 `gpt-image-2` 跟舊模型的差別，知道 quality、size、透明背景這些參數怎麼選
- 用「場景 → 主體 → 細節 → 限制」的結構寫 prompt，並且用引號、ALL CAPS 讓圖裡的文字更準
- 用 `images.edit` 做風格轉換、換裝、去物件、多圖合成，並靠「只改 X、其他維持不變」避免畫面跑掉

## 開跑前

- 需要 OpenAI API key，圖像生成會產生 API 費用
- 改圖範例需要把參考圖放進 `input_images/` 資料夾

## 1. 簡介

OpenAI 的 gpt-image 生成模型是為了正式上線等級的視覺內容和高度可控的創作流程設計的。專業設計工作和反覆修改的內容製作都適合，而且依需求可以選高品質輸出，也可以選低延遲。

主要能力：

- **高擬真的照片級畫面**，光線自然、材質準確、色彩豐富
- **彈性的品質與延遲取捨**，用較低的設定可以更快生成，畫質仍然超過上一代圖像模型
- **穩定的臉部與身分保留**，適合改圖、角色一致性和多步驟流程
- **透明背景的 PNG 和 WebP 素材（preview）**，`gpt-image-2` 支援，可用在可重複使用的 logo、商品去背圖、貼圖和簡報圖形
- **可靠的文字渲染**，字體清晰、版面一致、圖內對比度夠強
- **複雜的結構化視覺**，包括資訊圖表、流程圖和多格構圖
- **精準的風格控制與風格轉換**，只要很少的 prompt，從品牌設計系統到藝術風格都做得到
- **對真實世界的知識與推理**，能正確畫出各種物件、環境和情境

這份指南整理了 `gpt-image-2` 的 prompting 模式、最佳實踐和來自真實 production 案例的範例 prompt。`gpt-image-2` 是目前最強的圖像模型，畫質更好、改圖能力更強，也支援更多 production 流程。`low` quality 特別適合對延遲敏感的情境，要最高保真度時 `medium` 和 `high` 仍然適用。


## 1.1 OpenAI 圖像模型參數

這一節是本指南涵蓋的圖像模型參考資料，內容包括：

- 模型名稱
- 支援的 `outputQuality` 值
- 支援的 `input_fidelity` 值
- 支援的 `size` / 解析度規則
- 產生透明素材所需的 `background` 和 `output_format`
- 各種工作流程的建議用法

## 模型總覽
截至 2026 年 4 月 21 日，OpenAI 提供以下圖像模型。

| Model | `outputQuality` | `input_fidelity` | Resolutions | Recommended use |
| --- | --- | --- | --- | --- |
| `gpt-image-2` | `low`, `medium`, `high` | Disabled. `input_fidelity` does not work for this model because output is already high fidelity by default | Any resolution that satisfies the constraints below | Recommended default for new builds. Use for highest-quality generation and editing, text-heavy images, photorealism, compositing, identity-sensitive edits, and workflows where fewer retries matter more than the lowest possible cost. |
| `gpt-image-1.5` | `low`, `medium`, `high` | `low`, `high` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | Keep for existing validated workflows during migration. For new work, prefer `gpt-image-2`, especially when quality, editing reliability, or flexible sizing matter. |
| `gpt-image-1` | `low`, `medium`, `high` | `low`, `high` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | Legacy compatibility only. If you are starting a new workflow or refreshing prompts, move to `gpt-image-2`; keep `gpt-image-1` only when you need short-term stability while validating the upgrade. |
| `gpt-image-1-mini` | `low`, `medium`, `high` | `low`, `high` | `1024x1024`, `1024x1536`, `1536x1024`, `auto` | Use when cost and throughput are the main constraint: large batch variant generation, rapid ideation, previews, lightweight personalization, and draft assets that do not require the strongest generation or editing performance. |

### 用 `gpt-image-2` 產生透明背景（preview）

`gpt-image-2` 的透明背景目前是 preview。要生成或編輯透明背景的圖：

- 設定 `background="transparent"`。
- 設定 `output_format="png"`（預設）或 `output_format="webp"`。兩者都支援透明，`jpeg` 不支援。
- PNG 輸出請不要帶 `output_compression`，WebP 可以選擇性壓縮。
- 在 prompt 裡明確要求主體獨立在完全透明的背景上，不要有場景、純色底、棋盤格或多餘的陰影。
- 編輯時，每個 prompt 都要明確要求保留透明背景，後面的步驟才不會又生出新背景。
- 回傳的圖請維持 PNG 或 WebP 格式，後續處理過程都要保留 alpha channel。

### `gpt-image-2` 的 size 選項

`size` 參數可以傳任意解析度，只要同時滿足這些限制：

- 最長邊必須小於 `3840px`
- 兩個邊都必須是 `16` 的倍數
- 長邊和短邊的比例不能大於 `3:1`
- 總像素不能超過 `8,294,400`
- 總像素不能少於 `655,360`

如果輸出超過 `2560x1440`（`3,686,400` 總像素，一般稱 2K），請當成實驗性質，因為超過這個大小結果會比較不穩定。

### 常用的 `gpt-image-2` 尺寸

這些是符合上述限制的常用參考值：

| Label | Resolution | Notes |
| --- | --- | --- |
| HD portrait | `1024x1536` | Standard portrait option |
| HD landscape | `1536x1024` | Standard landscape option |
| Square | `1024x1024` | Good general-purpose default |
| 2K / QHD | `2560x1440` | Popular widescreen format and recommended upper reliability boundary for `gpt-image-2` |
| 4K / UHD | `3840x2160` | Experimental upper-end target. If the max-edge rule is enforced literally as `< 3840`, round down to the nearest valid size such as `3824x2144` |

### 該用哪個模型

- 大多數 production 流程直接用 `gpt-image-2`。它整體最強，目前用 `gpt-image-1.5` 或 `gpt-image-1` 跑高品質輸出的團隊也該升級到它。
- 速度和單位成本最重要時，用 `gpt-image-2` 搭配 quality: low。這個設定對很多用途畫質已經夠好，很適合大量生成和實驗。你也可以試 `gpt-image-1-mini`，不過我們發現 quality: low 的效果一樣好。
- `gpt-image-1.5` 或 `gpt-image-1` 只在向下相容時保留，例如還在驗證 prompt 遷移、做輸出的 regression 測試，或維護還沒準備好升級的舊流程。

### 從 `gpt-image-1.5` 和 `gpt-image-1` 升級的建議路徑

目前用 `gpt-image-1.5` 或 `gpt-image-1` 的流程，建議這樣做：

- 面向客戶的素材、照片級生成、大量編輯的流程、對品牌敏感的創意、圖內文字，還有任何「第一次生成品質好就能少人工檢查、少重跑」的流程，都升級到 `gpt-image-2`。
- 只有主要目標是壓低大量探索性、低風險圖片的成本時，才考慮用 `gpt-image-1-mini` 取代舊模型。
- 遷移時先讓 prompt 大致維持不變，等在真實工作量上比較過輸出品質、延遲和重試率之後，再微調。

## 2. Prompting 基本原則

下面這些原則適用於 GPT 圖像生成模型，來自 alpha 測試中反覆出現的模式，涵蓋生成、編輯、資訊圖表、廣告、人像、UI mockup 和合成流程。

* **結構 + 目標：** prompt 用固定順序寫（背景/場景 → 主體 → 關鍵細節 → 限制），並寫明用途（廣告、UI mock、資訊圖表），這樣可以設定「模式」和精緻程度。需求複雜時，用簡短的標籤段落或換行，不要塞成一大段。

* **Prompt 格式：** 選最好維護的格式。極簡 prompt、描述性段落、類 JSON 結構、指令式 prompt、標籤式 prompt 都可以，只要意圖和限制講清楚。production 系統優先選好掃讀的模板，不要追求花俏的語法。

* **具體程度 + 品質提示：** 材質、形狀、質感和視覺媒介（照片、水彩、3D render）要具體，只有需要時才加針對性的「品質調味料」（例如 *film grain*、*textured brushstrokes*、*macro detail*）。要照片級擬真，直接在 prompt 裡寫 “photorealistic”，會強烈啟動模型的擬真模式。“real photograph”、“taken on a real camera”、“professional photography”、“iPhone photo” 這類說法也有幫助，但詳細的相機規格會被模型鬆散解讀，所以主要用在整體風格和構圖，不要期待精確的物理模擬。

* **延遲 vs 保真度：** 對延遲敏感或大量生成的情境，先從 `quality="low"` 開始，看符不符合視覺需求。很多時候它的保真度已經夠用，生成快很多。小字或密集文字、細節多的資訊圖表、人像特寫、重視身分的編輯和高解析度輸出，上線前請比較 `medium` 或 `high`。

* **構圖：** 指定取景和視角（特寫、廣角、俯視）、角度（平視、低角度）和光線氛圍（柔和漫射、黃金時刻、高對比）來控制畫面。版面重要的話，要寫出位置（例如 “logo top-right”、“subject centered with negative space on left”）。寬幅、電影感、低光、下雨或霓虹場景，要多描述尺度、氛圍和色彩，模型才不會為了表面的真實感犧牲氣氛。

* **人物、姿勢與動作：** 畫面有人時，描述比例、身體取景、視線和跟物件的互動。例如 “full body visible, feet included”、“child-sized relative to the table”、“looking down at the open book, not at the camera”、“hands naturally gripping the handlebars”。這些細節能改善身體比例、動作幾何和視線方向。

* **限制（改什麼 vs 保留什麼）：** 明確寫出排除項目和不能變的東西（例如 “no watermark”、“no extra text”、“no logos/trademarks”、“preserve identity/geometry/layout/brand elements”）。編輯時用 “change only X” + “keep everything else the same”，並且每次迭代都重複保留清單，減少漂移。如果要做精準修改，也要說明不要改飽和度、對比、版面、箭頭、標籤、鏡頭角度或周圍物件。

* **透明背景：** `gpt-image-2` 的透明背景是 preview。`background="transparent"` 要搭配 `output_format="png"`（預設）或 `output_format="webp"`，`jpeg` 不支援透明。把主體描述成獨立在完全透明的背景上，並明確排除場景、純色底、棋盤格和多餘陰影。編輯時重複寫 “preserve the transparent background”，流程才不會產生或保留不透明的場景。PNG 不要帶 `output_compression`，WebP 可以選擇性壓縮。

* **圖內文字：** 要出現的文字放在**引號**裡或用 **ALL CAPS**，並把字體細節（字型風格、大小、顏色、位置）當成限制寫出來。冷僻的字（品牌名、少見拼法）可以逐字母拼出來，提高字元準確度。小字、密集資訊面板和多字型版面請用 `medium` 或 `high` quality。
* **多圖輸入：** 用**編號加描述**來指稱每張輸入圖（“Image 1: product photo… Image 2: style reference…”），並說明它們怎麼互動（“apply Image 2’s style to Image 1”）。做合成時，要明確說哪個元素移到哪裡（“put the bird from Image 1 on the elephant in Image 2”）。

* **逐步迭代，不要一次塞太多：** 長 prompt 也可以有好結果，但先從乾淨的基礎 prompt 開始，再用小而單一的修改來調整（“make lighting warmer”、“remove the extra tree”、“restore the original background”），debug 會容易很多。可以用 “same style as before” 或 “the subject” 這類說法利用上下文，但關鍵細節開始漂移時要重新寫清楚。

## 3. 環境設定

只要跑一次。它會：
- 建立 API client
- 在 images 資料夾裡建立 `output_images/`
- 加一個小 helper 來存 base64 圖片

改圖用的參考圖請放進 `input_images/`（或自己改範例裡的路徑）。存透明輸出時，副檔名要用 `.png` 或 `.webp`，跟選的 output format 一致，並且保留回傳的圖片 bytes。把 RGBA 圖轉成 RGB 會丟掉透明背景。

```python
import os
import base64
from openai import OpenAI

client = OpenAI()

os.makedirs("../../images/input_images", exist_ok=True)
os.makedirs("../../images/output_images", exist_ok=True)

def save_image(result, filename: str) -> None:
    """
    Saves the first returned image to the given filename inside the output_images folder.
    """
    image_base64 = result.data[0].b64_json
    out_path = os.path.join("../../images/output_images", filename)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(image_base64))

from IPython.display import HTML, Image, display

def display_image_grid(items, width=240):
    cards = []
    for item in items:
        title = item.get("title", "")
        label = f'<div style="font-weight:600;margin-bottom:8px">{title}</div>' if title else ""
        cards.append(
            '<div style="text-align:center">'
            + label
            + f'<img src="{item["path"]}" width="{width}" style="max-width:100%;height:auto;" />'
            + '</div>'
        )
    display(HTML('<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start">' + ''.join(cards) + '</div>'))
```

以下範例都使用最強的圖像模型 `gpt-image-2`。

## 4. 使用案例：生成（文字 → 圖片）

## 4.1 資訊圖表
資訊圖表用來向特定對象（學生、主管、客戶或一般大眾）說明結構化資訊，例如解說圖、海報、標註圖、時間軸和「視覺化 wiki」素材。版面密集或圖內文字很多時，建議把輸出品質設為 "high"。

```python
prompt = """
Create a detailed Infographic of the functioning and flow of an automatic coffee machine like a Jura. 
From bean basket, to grinding, to scale, water tank, boiler, etc. 
I'd like to understand technically and visually the flow.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "infographic_coffee_machine_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/infographic_coffee_machine_gpt-image-2.png)

## 4.2 圖片內文字翻譯

用來把現有設計（廣告、UI 截圖、包裝、資訊圖表）在地化成另一種語言，不用從頭重做版面。重點是除了文字之外全部保留：字體風格、位置、間距和層級都要一致，翻譯要逐字準確，不多加字，非必要不重排，也不能動到 logo、圖示或圖像。

```python
prompt = """
Translate the text in the infographic to Spanish. Do not change any other aspect of the image.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/output_images/infographic_coffee_machine_gpt-image-2.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)


save_image(result, "infographic_coffee_machine_sp_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/infographic_coffee_machine_sp_gpt-image-2.png)

## 4.3 看起來「自然」的照片級圖片

要得到可信的擬真效果，prompt 要寫得像是在當下拍一張真實照片。用攝影的語言（鏡頭、光線、取景），並明確要求真實的質感（毛孔、皺紋、衣物磨損、瑕疵）。避免暗示棚拍精修或刻意擺拍的字眼。細節重要時，設定 quality="high"。

```python
prompt = """
Create a photorealistic candid photograph of an elderly sailor standing on a small fishing boat. 
He has weathered skin with visible wrinkles, pores, and sun texture, and a few faded traditional sailor tattoos on his arms. 
He is calmly adjusting a net while his dog sits nearby on the deck. Shot like a 35mm film photograph, medium close-up at eye level, using a 50mm lens. 
Soft coastal daylight, shallow depth of field, subtle film grain, natural color balance. 
The image should feel honest and unposed, with real skin texture, worn materials, and everyday detail. No glamorization, no heavy retouching. 
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "photorealism-gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/photorealism-gpt-image-2.png)

## 4.4 世界知識

GPT 圖像生成模型能結合強大的推理和世界知識。例如要它生成 1969 年 8 月紐約 Bethel 的場景，它能推斷出是 Woodstock，畫出正確且符合情境的圖，不需要你明說這個活動。

```python
prompt = """
Create a realistic outdoor crowd scene in Bethel, New York on August 16, 1969.
Photorealistic, period-accurate clothing, staging, and environment.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "world_knowledge-gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/world_knowledge-gpt-image-2.png)

## 4.5 Logo 生成

好的 logo 來自清楚的品牌限制和簡潔。描述品牌個性和使用情境，然後要求乾淨、原創的標誌，形狀強、留白平衡、各種尺寸都能縮放。logo 需要放在不同網站、活動或簡報背景上重複使用時，用透明背景的 PNG 或 WebP。

你可以用參數 "n" 指定要生成幾個變體。

```python
prompt = """
Create an original, non-infringing logo for a company called Field & Flour, a local bakery. 
The logo should feel warm, simple, and timeless. Use clean, vector-like shapes, a strong silhouette, and balanced negative space. 
Favor simplicity over detail so it reads clearly at small and large sizes. Flat design, minimal strokes, no gradients unless essential. 
Fully transparent background. Deliver a single centered logo with generous padding, clean alpha edges, and no solid backdrop, scenery, checkerboard, or watermark.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
    background="transparent",
    output_format="png",
    n=4,    # Generate 4 versions of the logo
)

# Save all 4 images to separate files
for i, item in enumerate(result.data, start=1):
    image_base64 = item.b64_json
    image_bytes = base64.b64decode(image_base64)
    with open(f"../../images/output_images/logo_generation_{i}_gpt-image-2.png", "wb") as f:
        f.write(image_bytes)
```

輸出圖片：

| Option 1 | Option 2 | Option 3 | Option 4 |
|:--------:|:--------:|:--------:|:--------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_1_gpt-image-2.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_2_gpt-image-2.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_3_gpt-image-2.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_4_gpt-image-2.png)|

## 4.6 廣告生成

廣告生成的 prompt 寫得像創意 brief 效果最好，不要只是技術性的圖像規格。描述品牌、受眾、文化、概念、構圖和確切文案，然後讓模型在這些邊界內做有品味的創意決定。這很適合早期的活動探索，因為模型會解讀受眾線索、推斷美術方向，並提出細節，讓廣告看起來有被用心設計，而不只是被渲染出來。

要更好的結果，把品牌定位、想要的氛圍、目標受眾、場景和標語寫在同一個 prompt 裡。文字必須出現在圖裡的話，要精確引用，並要求乾淨好讀的字體。

```python
prompt = """
Give me a cool in culture ad / fashion shot for a brand called Thread. 
It's a hip young street brand. The ad shows a group of friends hanging out together with the tagline "Yours to Create."
Make it feel like a polished campaign image for a youth streetwear audience: stylish, contemporary, energetic, and tasteful.
Use clean composition, strong color direction, natural poses, and premium fashion photography cues.
Render the tagline exactly once, clearly and legibly, integrated into the ad layout.
No extra text, no watermarks, no unrelated logos.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "thread_ad_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/thread_ad_gpt-image-2.png)


## 4.7 故事轉漫畫

故事轉漫畫時，把劇情定義成一連串清楚的視覺節拍，一格一個。描述要具體、聚焦在動作，模型才能把故事轉成好讀、節奏好的分格。

```python
prompt = """
Create a short vertical comic-style reel with 4 equal-sized panels.
Panel 1: The owner leaves through the front door. The pet is framed in the window behind them, small against the glass, eyes wide, paws pressed high, the house suddenly quiet.
Panel 2: The door clicks shut. Silence breaks. The pet slowly turns toward the empty house, posture shifting, eyes sharp with possibility.
Panel 3: The house transformed. The pet sprawls across the couch like it owns the place, crumbs nearby, sunlight cutting across the room like a spotlight.
Panel 4: The door opens. The pet is seated perfectly by the entrance, alert and composed, as if nothing happened.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "comic_reel-gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/comic_reel-gpt-image-2.png)

## 4.8 UI Mockup

UI mockup 的 prompt 要把產品寫得像已經存在。重點放在版面、層級、間距和真實的介面元素，避免概念藝術的語言，這樣結果看起來才像可用、已上線的介面，而不是設計草圖。

```python
prompt = """
Create a realistic mobile app UI mockup for a local farmers market. 
Show today’s market with a simple header, a short list of vendors with small photos and categories, a small “Today’s specials” section, and basic information for location and hours. 
Design it to be practical, and easy to use. White background, subtle natural accent colors, clear typography, and minimal decoration. 
It should look like a real, well-designed, beautiful app for a small local market. 
Place the UI mockup in an iPhone frame.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "ui_farmers_market_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/ui_farmers_market_gpt-image-2.png)

## 4.9 科學 / 教育圖像

科學和教育圖像很適合生物、化學、課堂講解、扁平科學圖示系統、圖解和學習素材。prompt 寫得像教學設計 brief：定義受眾、教學目標、視覺格式、必要的標籤和科學上的限制。要好結果的話，要求乾淨的扁平視覺系統，圖示風格一致、箭頭清楚、標籤好讀，並留足空白讓學生快速掃過概念。

準確度重要時，明確列出必要的元件，並說明哪些不該出現。標籤密集的圖、圖解，或要用在簡報和課程教材的素材，請用 `quality="high"`。

```python
prompt = """
Create a simple biology diagram titled "Cellular Respiration at a Glance" for high school students.

Show how glucose turns into energy inside a cell. Include glycolysis, the Krebs cycle, and the electron transport chain.
Use arrows to connect the steps, and label the main molecules: glucose, pyruvate, ATP, NADH, FADH2, CO2, O2, and H2O.
Make it look like a clean classroom handout or slide, with a white background, simple icons, clear labels, and easy-to-read text.

Avoid tiny text, extra decoration, or anything that makes the diagram hard to understand.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1536x1024",
    quality="high",
)

save_image(result, "scientific_educational_cellular_respiration_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/scientific_educational_cellular_respiration_gpt-image-2.png)

## 4.10 簡報、圖表、流程圖與生產力圖像

生產力類的視覺，prompt 要寫得像「產出物規格」，不要像插畫需求。指名確切的交付物（簡報頁、流程圖、圖表、頁面圖片），定義畫布和層級，提供真實的文字或數據，並描述視覺語言。這類 prompt 要包含實際的限制：字體好讀、間距精緻、沒有多餘裝飾、不要一般圖庫照片的感覺。

簡報、圖表和圖解類素材，要把數字和標籤直接寫進 prompt。簡報風格的輸出用橫向尺寸，圖裡有小字、圖例、座標軸或註腳時用 `quality="high"`。

```python
prompt = """
Create one pitch-deck slide titled **"Market Opportunity"** that feels like a real Series A fundraising slide from a YC-backed startup.

Use a clean white background, modern sans-serif typography like Inter, and a crisp, minimal layout. The slide should include:

* A TAM/SAM/SOM concentric-circle diagram in muted blues and grays
* Specific, believable market sizing numbers:

  * **TAM:** $42B
  * **SAM:** $8.7B
  * **SOM:** $340M
* A clean bar chart below showing market growth from **2021 to 2026**, with a subtle upward trend
* Small footnotes: **"AGI Research, 2024"** and **"Internal analysis"**
* A company logo placeholder in the bottom-right corner

The design should look like it belongs in a deck that actually raised money: highly readable text, clear data hierarchy, polished spacing, and professional startup-style visual language.

Avoid clip art, stock photography, gradients, shadows, decorative elements, or anything that feels generic or overdesigned.
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1536x864",
    quality="high",
)

save_image(result, "market_opportunity_slide_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/market_opportunity_slide_gpt-image-2.png)

## 5. 使用案例：編輯（文字 + 圖片 → 圖片）

## 5.1 風格轉換

想保留參考圖的*視覺語言*（色調、質感、筆觸、film grain 等），同時換掉主體或場景時，就用風格轉換。要有好結果，描述哪些必須維持一致（風格線索）、哪些要改（新內容），再加上背景、取景和 “no extra elements” 這類硬限制，防止畫面漂移。

```python
prompt = """
Use the same style from the input image and generate a man riding a motorcycle on a white background.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/input_images/pixels.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "motorcycle_gpt-image-2.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pixels.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/motorcycle_gpt-image-2.png)

## 5.2 虛擬試穿

虛擬試穿很適合電商預覽，身分保留是關鍵。重點是明確鎖定人物（臉、體型、姿勢、髮型、表情），只允許改動衣物，再要求合理的穿著效果（垂墜、褶皺、遮擋），以及一致的光線和陰影，讓衣服看起來是自然穿上去的，不是貼上去的。

```python
prompt = """
Edit the image to dress the woman using the provided clothing images. Do not change her face, facial features, skin tone, body shape, pose, or identity in any way. Preserve her exact likeness, expression, hairstyle, and proportions. Replace only the clothing, fitting the garments naturally to her existing pose and body geometry with realistic fabric behavior. Match lighting, shadows, and color temperature to the original photo so the outfit integrates photorealistically, without looking pasted on. Do not change the background, camera angle, framing, or image quality, and do not add accessories, text, logos, or watermarks.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/input_images/woman_in_museum.png", "rb"),
        open("../../images/input_images/tank_top.png", "rb"),
        open("../../images/input_images/jacket.png", "rb"),
        open("../../images/input_images/tank_top.png", "rb"),
        open("../../images/input_images/boots.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "outfit_gpt-image-2.png")
```

輸入圖片：

| Full Body | Item 1 |
|:------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/woman_in_museum.png)  | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jacket.png) |
| Item 2 | Item 3 |
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/tank_top.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/boots.png) |

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/outfit_gpt-image-2.png)

## 5.3 草圖 → 擬真圖（Rendering）

草圖轉擬真圖，很適合把粗略的手繪變成照片級概念圖，同時保留原本的意圖。prompt 當成規格來寫：保留版面和透視，再用合理的材質、光線和環境來*增加真實感*。加上 “do not add new elements/text” 避免模型自己創意重新詮釋。

```python
prompt = """
Turn this drawing into a photorealistic image.
Preserve the exact layout, proportions, and perspective.
Choose realistic materials and lighting consistent with the sketch intent.
Do not add new elements or text.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/input_images/drawings.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "realistic_valley_gpt-image-2.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/drawings.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realistic_valley_gpt-image-2.png)

## 5.4 商品 Mockup（透明背景 + 標籤完整性）

商品去背和 mockup 前置處理常用在型錄、電商平台和設計系統。成功的關鍵是邊緣品質（輪廓乾淨、沒有毛邊或光暈）和標籤完整性（文字維持清晰、不被改動）。`gpt-image-2` 的透明背景是 preview，請求 `background="transparent"` 搭配 `output_format="png"`（預設）或 `output_format="webp"`，就能直接產出可重複使用的商品去背圖。`jpeg` 不支援透明背景。要求獨立主體，保留現有商品的形狀和標籤，並且不要純色底、棋盤格和不必要的陰影。PNG 不要帶 `output_compression`，WebP 可以選擇性壓縮。

```python
prompt = """
Extract the product from the input image and isolate it on a fully transparent background.
Output: centered product, crisp silhouette, no halos/fringing.
Preserve product geometry and label legibility exactly.
Add only light polishing. Do not add a solid backdrop, checkerboard, scenery, or shadow.
Do not restyle the product; remove the background and preserve clean alpha transparency.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/input_images/shampoo.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
    background="transparent",
    output_format="png",
)

save_image(result, "extract_product_gpt-image-2.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/shampoo.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/extract_product_gpt-image-2.png)

## 5.5 圖內有真實文字的行銷素材

圖內有真實文字的行銷素材很適合快速做廣告概念，但字體需要明確的限制。確切文案放在引號裡，要求逐字呈現（不多出字元），並描述位置和字型風格。文字保真度不完美的話，維持嚴格的 prompt 再迭代，小幅調整用字或版面通常就能改善易讀性。

```python
prompt = """
Create a realistic billboard mockup of the shampoo on a highway scene during sunset.
Billboard text (EXACT, verbatim, no extra characters):
"Fresh and clean"
Typography: bold sans-serif, high contrast, centered, clean kerning.
Ensure text appears once and is perfectly legible.
No watermarks, no logos.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/input_images/shampoo.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "billboard_gpt-image-2.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/shampoo.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/billboard_gpt-image-2.png)

## 5.6 光線與天氣轉換

用來把一張照片重新佈置成不同的氛圍、季節或時段版本（例如晴天 → 陰天、白天 → 黃昏、晴朗 → 下雪），同時保持場景構圖不變。重點是只改環境條件，包括光線方向和品質、陰影、大氣、降水和地面濕度，並保留人物身分、幾何、鏡頭角度和物件位置，讓它看起來還是同一張原始照片。

```python
prompt = """
Make it look like a winter evening with snowfall.
"""

result = client.images.edit(
    model="gpt-image-2",
    input_fidelity="high", 
    image=[
        open("../../images/output_images/billboard_gpt-image-2.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "billboard_winter_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/billboard_winter_gpt-image-2.png)


## 5.7 物件移除

人物融入場景的合成，很適合分鏡、活動和「如果⋯會怎樣」的情境，臉部和身分保留是重點。用寫實的攝影風格（自然光線、可信的細節、不要電影調色）來鞏固真實感，並鎖定主體不能變的部分。如果有提供的話，較高的 input fidelity 有助於在大幅度場景編輯時維持長相。

```python
prompt = """
Remove the flower from man's hand. Do not change anything else.
"""


result = client.images.edit(
    model="gpt-image-2",
    input_fidelity="high", 
    image=[
        open("../../images/output_images/man_with_blue_hat.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "man_with_no_flower_gpt-image-2.png")
```

輸入與輸出圖片：

| Original Input | Output Image |
|:------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/man_with_blue_hat.png)  |  ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/man_with_no_flower_gpt-image-2.png) |


## 5.8 把人物放進場景


人物融入場景的合成，很適合分鏡、活動和「如果⋯會怎樣」的情境，臉部和身分保留是重點。用寫實的攝影風格（自然光線、可信的細節、不要電影調色）來鞏固真實感，並鎖定主體不能變的部分。如果有提供的話，較高的 input fidelity 有助於在大幅度場景編輯時維持長相。

```python
prompt = """
Generate a highly realistic action scene where this person is running away from a large, realistic brown bear attacking a campsite. The image should look like a real photograph someone could have taken, not an overly enhanced or cinematic movie-poster image.
She is centered in the image but looking away from the camera, wearing outdoorsy camping attire, with dirt on her face and tears in her clothing. She is clearly afraid but focused on escaping, running away from the bear as it destroys the campsite behind her.
The campsite is in Yosemite National Park, with believable natural details. The time of day is dusk, with natural lighting and realistic colors. Everything should feel grounded, authentic, and unstyled, as if captured in a real moment. Avoid cinematic lighting, dramatic color grading, or stylized composition.
"""

result = client.images.edit(
    model="gpt-image-2",
    input_fidelity="high", 
    image=[
        open("../../images/input_images/woman_in_museum.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "scene_gpt-image-2.png")
```

輸出圖片：


```python
from IPython.display import Image, display
display(Image(filename="../../images/output_images/scene_gpt-image-2.png", width=500))
```

## 5.9 多圖參照與合成


用來把多張輸入圖的元素合成一張可信的圖，很適合「把這個物件/人物放進那個場景」的流程，不用整張重新生成。重點是清楚指定要移植什麼（圖 2 的狗）、放在哪裡（圖 1 女子的旁邊）、什麼必須維持不變（場景、背景、取景），同時匹配光線、透視、比例和陰影，讓合成結果看起來像在原始照片裡自然拍到的。

```python
prompt = """
Place the dog from the second image into the setting of image 1, right next to the woman, use the same style of lighting, composition and background. Do not change anything else.
"""

result = client.images.edit(
    model="gpt-image-2",
    input_fidelity="high", 
    image=[
        open("../../images/output_images/test_woman.png", "rb"),
        open("../../images/output_images/test_woman_2.png", "rb"),
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)


save_image(result, "test_woman_with_dog_gpt-image-2.png")
```

輸入與輸出圖片：

| Original Input | Remove Red Stripes | Change Hat Color |
|:--------------:|:------------------:|:----------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/test_woman.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/test_woman_2.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/test_woman_with_dog_gpt-image-2.png) |

## 6. 其他高價值使用案例

## 6.1 室內設計「換物」（精準編輯）
用來預覽真實空間裡家具或擺設的改變，不用重新渲染整個場景。目標是手術刀等級的真實感：只換一個物件，同時保留鏡頭角度、光線、陰影和周圍環境，讓編輯結果像真實照片，不像重新設計。

```python
prompt = """
In this room photo, replace ONLY white with chairs made of wood.
Preserve camera angle, room lighting, floor shadows, and surrounding objects.
Keep all other aspects of the image unchanged.
Photorealistic contact shadows and fabric texture.
"""

result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/input_images/kitchen.jpeg", "rb"),
    ],
    prompt=prompt,
    size="1536x1024",
    quality="medium",
)

save_image(result, "kitchen-chairs_gpt-image-2.png")
```

輸入與輸出圖片：

| Input Image | Output Image |
|------------|--------------|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/kitchen.jpeg) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/kitchen-chairs_gpt-image-2.png) |

## 6.2 3D 立體節慶賀卡（產品風格 mock）
適合季節性行銷概念和印刷預覽。強調觸感的真實：紙層、纖維、摺痕和柔和的攝影棚光線，讓結果看起來像拍下來的實體商品，不像平面插畫。

```python
scene_description = (
    "a cozy Christmas scene with an old teddy bear sitting inside a keepsake box, "
    "slightly worn fur, soft stitching repairs, placed near a window with falling snow outside. "
    "The scene suggests the child has grown up, but the memories remain."
)

short_copy = "Merry Christmas — some memories never fade."

prompt = f"""
Create a Christmas holiday card illustration.

Scene:
{scene_description}

Mood:
Warm, nostalgic, gentle, emotional.

Style:
Premium holiday card photography, soft cinematic lighting,
realistic textures, shallow depth of field,
tasteful bokeh lights, high print-quality composition.

Constraints:
- Original artwork only
- No trademarks
- No watermarks
- No logos

Include ONLY this card text (verbatim):
"{short_copy}"
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "christmas_holiday_card_teddy_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/christmas_holiday_card_teddy_gpt-image-2.png)

## 6.3 收藏公仔 / 絨毛鑰匙圈（周邊概念）

用在早期的周邊發想和提案視覺。著重高質感商品攝影的線索（材質、包裝、印刷清晰度），同時保持設計原創、不侵權。很適合快速測試多種角色或包裝變體。


```python
# ---- Inputs ----
character_description = (
    "a vintage-style toy propeller airplane with rounded wings, "
    "a front-mounted spinning propeller, slightly worn paint edges, "
    "classic childhood proportions, designed as a nostalgic holiday collectible"
)

short_copy = "Christmas Memories Edition"

# ---- Prompt ----
prompt = f"""
Create a collectible action figure of {character_description}, in blister packaging.

Concept:
A nostalgic holiday collectible inspired by the simple toy airplanes
children used to play with during winter holidays.
Evokes warmth, imagination, and childhood wonder.

Style:
Premium toy photography, realistic plastic and painted metal textures,
studio lighting, shallow depth of field,
sharp label printing, high-end retail presentation.

Constraints:
- Original design only
- No trademarks
- No watermarks
- No logos

Include ONLY this packaging text (verbatim):
"{short_copy}"
"""

result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "christmas_collectible_toy_airplane_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/christmas_collectible_toy_airplane_gpt-image-2.png)

## 6.4 角色一致的兒童繪本（多圖流程）
為多頁插畫流程設計，角色不能走樣的情況。可重複使用的「角色錨點」讓角色在不同場景、姿勢和頁面之間視覺連貫，同時允許環境和劇情變化。


1️⃣ 角色錨點：建立可重複使用的主角

目標：鎖定角色的外觀、比例、服裝和調性。

```python
# ---- Inputs ----
prompt = """
Create a children’s book illustration introducing a main character.

Character:
A young, storybook-style hero inspired by a little forest outlaw,
wearing a simple green hooded tunic, soft brown boots, and a small belt pouch.
The character has a kind expression, gentle eyes, and a brave but warm demeanor.
Carries a small wooden bow used only for helping, never harming.

Theme:
The character protects and rescues small forest animals like squirrels, birds, and rabbits.

Style:
Children’s book illustration, hand-painted watercolor look,
soft outlines, warm earthy colors, whimsical and friendly.
Proportions suitable for picture books (slightly oversized head, expressive face).

Constraints:
- Original character (no copyrighted characters)
- No text
- No watermarks
- Plain forest background to clearly showcase the character
"""

# ---- Image generation ----
result = client.images.generate(
    model="gpt-image-2",
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "childrens_book_illustration_1_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/childrens_book_illustration_1_gpt-image-2.png)

2️⃣ 劇情延續：重用角色，推進故事

目標：同一個角色，新的場景和動作。
角色外觀必須維持不變。

```python
# ---- Inputs ----
prompt = """
Continue the children’s book story using the same character.

Scene:
The same young forest hero is gently helping a frightened squirrel
out of a fallen tree after a winter storm.
The character kneels beside the squirrel, offering reassurance.

Character Consistency:
- Same green hooded tunic
- Same facial features, proportions, and color palette
- Same gentle, heroic personality

Style:
Children’s book watercolor illustration,
soft lighting, snowy forest environment,
warm and comforting mood.

Constraints:
- Do not redesign the character
- No text
- No watermarks
"""
# ---- Image generation ----
result = client.images.edit(
    model="gpt-image-2",
    image=[
        open("../../images/output_images/childrens_book_illustration_1_gpt-image-2.png", "rb"),  # use image from step 1
    ],
    prompt=prompt,
    size="1024x1536",
    quality="medium",
)

save_image(result, "childrens_book_illustration_2_gpt-image-2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/childrens_book_illustration_2_gpt-image-2.png)

## 結論

這份 notebook 示範了怎麼用 gpt-image 生成模型，建立在真實 production 環境撐得住的高品質、可控的圖像生成與編輯流程。重點是 prompt 結構、明確的限制和小幅迭代，這三個是控制真實感、版面、文字準確度和身分保留的主要工具。內容涵蓋生成和編輯兩類模式，從資訊圖表、擬真照片、UI mockup、logo，到翻譯、風格轉換、虛擬試穿、合成和光線轉換。每個範例都在強調：把「要改的」和「必須不變的」清楚分開，並在每次迭代重述不變項目，防止漂移。我們也說明了 quality 和 input fidelity 設定怎麼讓你依用途在延遲和視覺精準度之間取捨。這些範例合起來，就是一套可重複使用、可實際套用在 production 圖像流程的 gpt-image 做法。

## 重點整理

- Prompt 用固定結構寫（場景 → 主體 → 細節 → 限制），並寫明用途，模型會抓到對應的精緻程度。
- 改圖時要明確分開「只改 X」和「其他維持不變」，而且每次迭代都重複保留清單，才不會漂移。
- 先用 `quality="low"` 評估，小字、密集版面、人像特寫和高解析度再比較 `medium` / `high`。
- 圖內文字用引號或 ALL CAPS 指定，冷僻字逐字母拼出來。
- 透明背景要 `background="transparent"` 搭配 PNG 或 WebP，並且全程保留 alpha channel。

## 練習

1. 把 4.3 照片級圖片的 `quality` 從原本的值改成 `low`，跑一次，再改成 `high` 跑一次，比較細節和生成時間差多少。
2. 4.5 的 logo 範例改成加上透明背景（`background="transparent"`、`output_format="png"`），並把 `n` 改成 2，確認輸出的圖真的是去背的。
3. 5.1 風格轉換的 prompt，改成只換主體但在 prompt 裡加上完整的保留清單（背景、取景、色調），然後故意拿掉清單再跑一次，看看畫面漂移的程度。
