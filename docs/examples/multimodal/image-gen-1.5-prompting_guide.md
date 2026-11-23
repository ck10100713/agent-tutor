---
translated: true
source: examples/multimodal/image-gen-1.5-prompting_guide.ipynb
---
# gpt-image-1.5 Prompting 指南

> 原文：[examples/multimodal/image-gen-1.5-prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/image-gen-1.5-prompting_guide.ipynb)

這份 cookbook 教你怎麼寫 prompt，讓 gpt-image-1.5 穩定產出好圖。

## 這篇在做什麼

這篇整理了 gpt-image-1.5 的 prompting 技巧，從基本寫法到十幾種實際場景，包含文字生圖和圖片編輯。每個場景都有可以直接跑的 prompt 和輸出範例。

## 學完你會

- 用「場景 → 主體 → 細節 → 限制」的順序寫出結構清楚的 image prompt
- 用 `quality` 參數在速度和畫質之間取捨，並用 `n` 一次產生多個版本
- 做圖片編輯（風格轉換、虛擬試穿、物件移除、多圖合成），並明確寫出「改什麼、保留什麼」

## 開跑前

需要 OpenAI API key。編輯類的範例要把參考圖放進 `input_images/`，或自己改路徑。

## 1. 簡介

`gpt-image-1.5` 是目前最新的圖像生成模型，針對可上線的視覺品質和高度可控的創作流程設計。跟上一代比，寫實度、準確度和可編輯性都進步很多，既能高品質輸出，也能低延遲使用。

主要能力：

- **高擬真的照片寫實感**：自然光線、準確材質、豐富色彩
- **品質與延遲可以取捨**：設定調低可以更快產圖，畫質仍然超過上一代模型
- **臉部與身分保留很穩**：適合編輯、角色一致性和多步驟流程
- **文字渲染可靠**：字體清晰、版面一致、對比夠強
- **複雜的結構化視覺**：資訊圖表、圖解、多格構圖
- **精準的風格控制與風格轉換**：只要少少的 prompt，從品牌設計系統到藝術風格都行
- **對真實世界的知識與推理很強**：能正確畫出物件、環境和情境

這份指南整理了從真實 production 案例來的 prompting 模式、最佳實務和範例 prompt。


## 2. Prompting 基本功

* **結構 + 目標**：prompt 照固定順序寫（背景/場景 → 主體 → 關鍵細節 → 限制），並說明用途（廣告、UI mockup、資訊圖表），這樣模型知道要多精緻。需求複雜時，用簡短的標籤段落或換行，不要塞成一大段。

* **具體 + 品質提示**：把材質、形狀、質感、媒介（照片、水彩、3D render）講具體，品質加強詞只在需要時才加（例如 *film grain*、*textured brushstrokes*、*macro detail*）。要照片寫實的話，鏡頭、光圈感、打光這類攝影用語，通常比籠統的「8K/ultra-detailed」更能帶出寫實感。

* **延遲 vs 擬真度**：在意延遲或量很大的情境，先把 quality="low" 設起來，看看畫質夠不夠用。很多時候它的品質已經足夠，而且快很多。

* **構圖**：指定取景和視角（特寫、廣角、俯拍）、角度（平視、低角度）、光線與氛圍（柔和漫射、黃金時刻、高對比）。版面位置重要的話要點明（例如「logo 放右上角」「主體置中，左側留白」）。

* **限制（改什麼 vs 保留什麼）**：明確寫出排除項和不能變的部分（例如「no watermark」「no extra text」「no logos/trademarks」「保留人物身分/幾何/版面/品牌元素」）。編輯時用「只改 X」加「其他全部維持不變」，而且每一輪都重複寫一次保留清單，才不會越改越偏。

* **圖片裡的文字**：要出現的字用**引號**或**全大寫**框起來，並把字體細節（風格、大小、顏色、位置）當限制寫清楚。遇到難字（品牌名、罕見拼法），可以一個字母一個字母拆開寫，提高字元正確率。

* **多圖輸入**：用**編號加描述**指稱每張圖（「Image 1：商品照… Image 2：風格參考…」），並說明它們怎麼互動（「把 Image 2 的風格套到 Image 1」）。合成時要講清楚哪個元素移到哪裡（「把 Image 1 的鳥放到 Image 2 的大象上」）。

* **分次迭代，不要一次塞太多**：先從乾淨的基礎 prompt 開始，再用小而單一的追加指令微調（「光線再暖一點」「拿掉多的那棵樹」「還原原本的背景」）。可以用「跟剛才一樣的風格」「那個主體」這類說法借用上下文，但關鍵細節開始跑掉時要重新寫明。

## 3. 設定

只要跑一次。它會：
- 建立 API client
- 在 images 資料夾下建立 `output_images/`
- 加一個把 base64 圖片存檔的小 helper

編輯用的參考圖放進 `input_images/`（或自己改範例裡的路徑）。

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
```

## 4. 使用情境：生成（文字 → 圖片）

## 4.1 資訊圖表

資訊圖表用來對特定對象（學生、主管、客戶、一般大眾）說明有結構的資訊。常見的有說明圖、海報、標註圖解、時間軸和「視覺 wiki」素材。版面密或圖內文字很多時，建議把輸出品質設成 "high"。

```python
prompt = """
Create a detailed Infographic of the functioning and flow of an automatic coffee machine like a Jura. 
From bean basket, to grinding, to scale, water tank, boiler, etc. 
I'd like to understand technically and visually the flow.
"""

result = client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt
)

save_image(result, "infographic_coffee_machine.png")
```

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/infographic_coffee_machine.png)

## 4.2 圖片內文字翻譯

用來把現有設計（廣告、UI 截圖、包裝、資訊圖表）在地化成另一種語言，不用重做版面。重點是除了文字以外全部保留：字體風格、位置、間距、層級都要一致，翻譯要逐字準確、不多加字、非必要不重排，也不能動到 logo、icon 或圖像。

```python
prompt = """
Translate the text in the infographic to Spanish. Do not change any other aspect of the image.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    image=[
        open("../../images/output_images/infographic_coffee_machine.png", "rb"),
    ],
    prompt=prompt
)


save_image(result, "infographic_coffee_machine_sp.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/infographic_coffee_machine_sp.png)

## 4.3 看起來「自然」的寫實照片

要有可信的照片寫實感，prompt 要像是在現場拍下一張真實照片。用攝影語言（鏡頭、光線、取景），並明確要求真實的質感（毛孔、皺紋、衣物磨損、瑕疵）。避免暗示攝影棚精修或擺拍的字眼。細節重要時，設 quality="high"。

```python
prompt = """
Create a photorealistic candid photograph of an elderly sailor standing on a small fishing boat. 
He has weathered skin with visible wrinkles, pores, and sun texture, and a few faded traditional sailor tattoos on his arms. 
He is calmly adjusting a net while his dog sits nearby on the deck. Shot like a 35mm film photograph, medium close-up at eye level, using a 50mm lens. 
Soft coastal daylight, shallow depth of field, subtle film grain, natural color balance. 
The image should feel honest and unposed, with real skin texture, worn materials, and everyday detail. No glamorization, no heavy retouching. 
"""

result = client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt,
    quality="high"
)

save_image(result, "photorealism.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/photorealism.png)

## 4.4 世界知識

GPT-image-1.5 內建推理能力，世界知識也很強。例如要它畫 1969 年 8 月紐約 Bethel 的場景，它能推斷出那是 Woodstock，畫出符合情境的準確畫面，不需要你明講是哪個活動。

```python
prompt = """
Create a realistic outdoor crowd scene in Bethel, New York on August 16, 1969.
Photorealistic, period-accurate clothing, staging, and environment.
"""

result = client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt
)

save_image(result, "world_knowledge.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/world_knowledge.png)

## 4.5 Logo 生成

好的 logo 來自清楚的品牌限制和簡潔。描述品牌個性和使用情境，然後要求一個乾淨、原創、形狀強烈、留白平衡、各種尺寸都能縮放的標誌。

可以用參數 "n" 指定要產生幾個版本。

```python
prompt = """
Create an original, non-infringing logo for a company called Field & Flour, a local bakery. 
The logo should feel warm, simple, and timeless. Use clean, vector-like shapes, a strong silhouette, and balanced negative space. 
Favor simplicity over detail so it reads clearly at small and large sizes. Flat design, minimal strokes, no gradients unless essential. 
Plain background. Deliver a single centered logo with generous padding. No watermark.
"""

result = client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt,
    n=4     # Generate 4 versions of the logo
)

# Save all 4 images to separate files
for i, item in enumerate(result.data, start=1):
    image_base64 = item.b64_json
    image_bytes = base64.b64decode(image_base64)
    with open(f"../../images/output_images/logo_generation_{i}.png", "wb") as f:
        f.write(image_bytes)
```

輸出圖片：

| Option 1 | Option 2 | Option 3 | Option 4 |
|:--------:|:--------:|:--------:|:--------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_1.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_2.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_3.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_generation_4.png)|

## 4.6 故事轉漫畫

故事轉漫畫時，把劇情拆成一連串清楚的畫面節點，一格一個。描述要具體、聚焦在動作上，模型才能把故事轉成好讀、節奏順的分格。

```python
prompt = """
Create a short vertical comic-style reel with 4 equal-sized panels.
Panel 1: The owner leaves through the front door. The pet is framed in the window behind them, small against the glass, eyes wide, paws pressed high, the house suddenly quiet.
Panel 2: The door clicks shut. Silence breaks. The pet slowly turns toward the empty house, posture shifting, eyes sharp with possibility.
Panel 3: The house transformed. The pet sprawls across the couch like it owns the place, crumbs nearby, sunlight cutting across the room like a spotlight.
Panel 4: The door opens. The pet is seated perfectly by the entrance, alert and composed, as if nothing happened.
"""

result = client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt
)

save_image(result, "comic_reel.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/comic-reel.png)

## 4.7 UI Mockup

UI mockup 最有效的寫法，是把產品當成已經存在的東西來描述。聚焦在版面、層級、間距和真實的介面元件，避開概念圖的用語，結果才會像可用、已上線的介面，而不是設計草圖。

```python
prompt = """
Create a realistic mobile app UI mockup for a local farmers market. 
Show today’s market with a simple header, a short list of vendors with small photos and categories, a small “Today’s specials” section, and basic information for location and hours. 
Design it to be practical, and easy to use. White background, subtle natural accent colors, clear typography, and minimal decoration. 
It should look like a real, well-designed, beautiful app for a small local market. 
Place the UI mockup in an iPhone frame.
"""

result = client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt
)

save_image(result, "ui_farmers_market.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/ui_farmers_market.png)

## 5. 使用情境：編輯（文字 + 圖片 → 圖片）

## 5.1 風格轉換

想保留參考圖的*視覺語言*（色盤、質感、筆觸、膠片顆粒等），同時換掉主體或場景時，就用風格轉換。要有好結果，要寫清楚什麼必須一致（風格線索）、什麼要改（新內容），再加上背景、取景、「不要多餘元素」這類硬性限制，避免跑偏。

```python
prompt = """
Use the same style from the input image and generate a man riding a motorcycle on a white background.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    image=[
        open("../../images/input_images/pixels.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "motorcycle.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pixels.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/motorcycle.png)

## 5.2 虛擬試穿

虛擬試穿很適合電商預覽，這種情境一定要保留人物身分。做法是明確鎖住人物（臉、體型、姿勢、髮型、表情），只允許改衣物，再要求合身的真實感（垂墜、皺褶、遮擋）和一致的光影，讓衣服看起來是穿在身上，不是貼上去的。

```python
prompt = """
Edit the image to dress the woman using the provided clothing images. Do not change her face, facial features, skin tone, body shape, pose, or identity in any way. Preserve her exact likeness, expression, hairstyle, and proportions. Replace only the clothing, fitting the garments naturally to her existing pose and body geometry with realistic fabric behavior. Match lighting, shadows, and color temperature to the original photo so the outfit integrates photorealistically, without looking pasted on. Do not change the background, camera angle, framing, or image quality, and do not add accessories, text, logos, or watermarks.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    image=[
        open("../../images/input_images/woman_in_museum.png", "rb"),
        open("../../images/input_images/tank_top.png", "rb"),
        open("../../images/input_images/jacket.png", "rb"),
        open("../../images/input_images/tank_top.png", "rb"),
        open("../../images/input_images/boots.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "outfit.png")
```

輸入圖片：

| Full Body | Item 1 |
|:------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/woman_in_museum.png)  | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jacket.png) |
| Item 2 | Item 3 |
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/tank_top.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/boots.png) |

輸出圖片：

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/outfit.png" width="400"/> 

## 5.3 手繪稿 → 寫實圖（Rendering）

草圖轉渲染的流程，適合把粗略的手繪變成寫實的概念圖，同時保留原本的意圖。把 prompt 當規格書寫：保留版面和透視，再用合理的材質、光線和環境來*加上真實感*。記得寫上「不要加新元素/文字」，避免模型自行發揮。

```python
prompt = """
Turn this drawing into a photorealistic image.
Preserve the exact layout, proportions, and perspective.
Choose realistic materials and lighting consistent with the sketch intent.
Do not add new elements or text.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    image=[
        open("../../images/input_images/drawings.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "realistic_valley.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/drawings.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realistic_valley.png)

## 5.4 商品 Mockup（透明背景 + 標籤完整）

商品去背和 mockup 前置處理常用在型錄、電商平台和設計系統。成功的關鍵是邊緣品質（輪廓乾淨、沒有毛邊/光暈）和標籤完整（文字維持清楚、不被改動）。想要寫實但不要換風格的話，只要求輕微修飾，需要的話再加一個尊重 alpha 的淡淡接觸陰影。

```python
prompt = """
Extract the product from the input image.
Output: transparent background (RGBA PNG), crisp silhouette, no halos/fringing.
Preserve product geometry and label legibility exactly.
Optional: subtle, realistic contact shadow in the alpha (no hard cut line).
Do not restyle the product; only remove background and lightly polish.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    image=[
        open("../../images/input_images/shampoo.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "extract_product.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/shampoo.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/extract_product.png)

## 5.5 圖內有真實文字的行銷素材

圖內有真實文字的行銷素材很適合快速發想廣告，但字體需要明確的限制。把確切的文案放在引號裡，要求逐字呈現（不多任何字元），並描述位置和字體風格。文字不完美的話，prompt 維持嚴格，慢慢迭代，小幅調整用字或版面通常就能改善可讀性。

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
    model="gpt-image-1.5",
    image=[
        open("../../images/input_images/shampoo.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "billboard.png")
```

輸入圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/shampoo.png)

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/billboard.png)

## 5.6 光線與天氣轉換

用來替同一張照片換氣氛、季節或時段（例如晴天 → 陰天、白天 → 黃昏、晴朗 → 下雪），同時保持場景構圖不變。重點是只改環境條件（光線方向和品質、陰影、氣氛、降水、地面濕度），並保留人物身分、幾何、相機角度和物件位置，讓它看起來還是同一張原始照片。

```python
prompt = """
Make it look like a winter evening with snowfall.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    input_fidelity="high", 
    quality="high",
    image=[
        open("../../images/output_images/billboard.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "billboard_winter.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/billboard_winter.png)

## 5.7 物件移除

人物入景合成很適合分鏡、廣告活動和「如果…會怎樣」的情境，這時臉部和身分的保留很重要。要靠指定有根據的攝影質感（自然光、可信的細節、不要電影調色）來撐住真實感，並鎖住主體不能變的部分。如果有高 input fidelity 可用，在大幅度的場景編輯中比較能維持相似度。

```python
prompt = """
Remove the tree logo from the white t-shirt of the man. Do not change anything else.
"""

prompt = """
Remove the red stripes from the white t-shirt of the man. Do not change anything else.
"""

prompt = """
Change the color of thered hat to light blue as velvet. Do not change anything else.
"""


result = client.images.edit(
    model="gpt-image-1.5",
    input_fidelity="high", 
    quality="high",
    image=[
        open("../../images/output_images/man_with_blue_hat.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "man_with_no_flower.png")
```

| Original Input | Remove Red Stripes | Change Hat Color |
|:------------:|:--------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/man_with_flower.png)  | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/man_with_flower_no_stripes.png) |  ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/man_with_blue_hat.png) |

## 5.8 把人物放進場景

人物入景合成很適合分鏡、廣告活動和「如果…會怎樣」的情境，這時臉部和身分的保留很重要。要靠指定有根據的攝影質感（自然光、可信的細節、不要電影調色）來撐住真實感，並鎖住主體不能變的部分。如果有高 input fidelity 可用，在大幅度的場景編輯中比較能維持相似度。

```python
prompt = """
Generate a highly realistic action scene where this person is running away from a large, realistic brown bear attacking a campsite. The image should look like a real photograph someone could have taken, not an overly enhanced or cinematic movie-poster image.
She is centered in the image but looking away from the camera, wearing outdoorsy camping attire, with dirt on her face and tears in her clothing. She is clearly afraid but focused on escaping, running away from the bear as it destroys the campsite behind her.
The campsite is in Yosemite National Park, with believable natural details. The time of day is dusk, with natural lighting and realistic colors. Everything should feel grounded, authentic, and unstyled, as if captured in a real moment. Avoid cinematic lighting, dramatic color grading, or stylized composition.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    input_fidelity="high", 
    quality="high",
    image=[
        open("../../images/input_images/woman_in_museum.png", "rb"),
    ],
    prompt=prompt
)

save_image(result, "scene.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/scene.png)

## 5.9 多圖參照與合成

用來把多張輸入圖的元素合成一張可信的圖，很適合「把這個物件/人放進那個場景」的流程，不用整張重新生成。關鍵是講清楚要移植什麼（圖 2 的狗）、放哪裡（圖 1 那位女士旁邊）、什麼要維持不變（場景、背景、取景），並讓光線、透視、比例和陰影都對得上，合成結果才像原本就拍在同一張照片裡。

```python
prompt = """
Place the dog from the second image into the setting of image 1, right next to the woman, use the same style of lighting, composition and background. Do not change anything else.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    input_fidelity="high", 
    quality="high",
    image=[
        open("../../images/output_images/test_woman.png", "rb"),
        open("../../images/output_images/test_woman_2.png", "rb"),
    ],
    prompt=prompt
)


save_image(result, "test_woman_with_dog.png")
```

| Image Input 1 | Image Input 2 | Output |
|:------------:|:--------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/test_woman.png)  | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/test_woman_2.png) |  ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/test_woman_with_dog.png) |

## 6. 其他高價值情境

## 6.1 室內設計「換件」（精準編輯）

用來預覽真實空間裡的家具或擺設變化，不用重新渲染整個場景。目標是外科手術式的真實感：只換一件物品，保留相機角度、光線、陰影和周遭脈絡，讓結果像真的照片，而不是重新設計。

```python
prompt = """
In this room photo, replace ONLY white with chairs made of wood.
Preserve camera angle, room lighting, floor shadows, and surrounding objects.
Keep all other aspects of the image unchanged.
Photorealistic contact shadows and fabric texture.
"""

result = client.images.edit(
    model="gpt-image-1.5",
    image=[
        open("../../images/input_images/kitchen.jpeg", "rb"),
    ],
    prompt=prompt
)

save_image(result, "kitchen-chairs.png")
```

| Input Image | Output Image |
|------------|--------------|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/kitchen.jpeg) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/kitchen-chairs.png) |

## 6.2 3D 立體節慶卡片（產品風 mock）

適合季節性行銷概念和印刷預覽。強調觸感的真實：紙層、纖維、摺痕和柔和的攝影棚光線，讓結果看起來是拍下來的實體產品，而不是平面插畫。

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
    model="gpt-image-1.5",
    prompt=prompt,
)

save_image(result, "christmas_holiday_card_teddy.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/christmas_holiday_card_teddy.png)

## 6.3 收藏公仔 / 毛絨鑰匙圈（周邊概念）

用在早期周邊發想和提案視覺。著重高級商品攝影的線索（材質、包裝、印刷清晰度），同時保持設計原創、不侵權。很適合快速測試多種角色或包裝版本。

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
    model="gpt-image-1.5",
    prompt=prompt,
)

save_image(result, "christmas_collectible_toy_airplane.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/christmas_collectible_toy_airplane.png)

## 6.4 角色一致的兒童繪本（多圖流程）

為多頁插畫流程設計，不能接受角色走樣。用一個可重複使用的「角色錨點」，讓角色在不同場景、姿勢和頁面間保持視覺連貫，同時環境和劇情可以變化。

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
    model="gpt-image-1.5",
    prompt=prompt,
)

save_image(result, "childrens_book_illustration_1.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/childrens_book_illustration_1.png)

2️⃣ 故事延續：重用角色，推進劇情

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
    model="gpt-image-1.5",
    image=[
        open("../../images/output_images/childrens_book_illustration_1.png", "rb"),  # ← use image from step 1
    ],
    prompt=prompt,
)

save_image(result, "childrens_book_illustration_2.png")
```

輸出圖片：

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/childrens_book_illustration_2.png)

## 結論

這份 notebook 示範怎麼用 gpt-image-1.5 建立高品質、可控的圖像生成和編輯流程，能撐得住真實的 production 環境。cookbook 強調：prompt 結構、明確的限制、小步迭代，是控制寫實度、版面、文字準確度和身分保留的主要工具。內容涵蓋生成和編輯兩類模式，從資訊圖表、寫實照片、UI mockup、logo，到翻譯、風格轉換、虛擬試穿、合成和光線變化。所有範例反覆強調：要清楚區分「什麼要改」和「什麼必須不變」，並在每一輪迭代都重寫不變的部分來防止走樣。另外也說明 quality 和 input-fidelity 設定可以依情境，在延遲和畫面精準度之間做取捨。整體來看，這些範例構成一套實用、可重複的 gpt-image-1.5 production 圖像流程手冊。

## 重點整理

- prompt 照「場景 → 主體 → 細節 → 限制」的固定順序寫，並說明用途，模型會抓到對的精緻度。
- 編輯圖片的核心是講清楚「只改 X、其他不變」，而且每一輪迭代都重複一次保留清單。
- 圖內文字用引號或全大寫、指定字體細節，難字可以逐字母拼出來。
- 一次只做一個小改動，比一個超長 prompt 更容易收斂。
- `quality` 是延遲和畫質的旋鈕：量大先試 "low"，版面密或文字多再用 "high"。

## 練習

1. 把 4.5 的 logo prompt 裡的 `n` 改成不同數字，看一次出幾個版本，順便改品牌個性描述，比較差異。
2. 把 4.3 寫實照片的 prompt 的 quality 從 "high" 改成 "low"，比較速度和細節差多少。
3. 拿 5.1 的風格轉換範例，在 prompt 裡加上「保留清單」（背景、取景、不要多餘元素），連續迭代兩輪，看圖有沒有比不加時更穩定。
