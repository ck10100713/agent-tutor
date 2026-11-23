---
translated: true
source: examples/multimodal/transparent-image-assets-for-campaigns-and-presentations.ipynb
---
# 為行銷活動與簡報產生透明背景圖片素材

> 原文：[examples/multimodal/transparent-image-assets-for-campaigns-and-presentations.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/transparent-image-assets-for-campaigns-and-presentations.ipynb)

為季節性電商活動和品牌 PowerPoint 簡報，產生可重複使用的透明 PNG 素材。

## 這篇在做什麼

用圖片模型直接產生帶 alpha channel 的透明 PNG，不用再手動去背。同一批素材可以放到不同的活動背景、簡報主題、設計模板和商品 mockup 上。

## 學完你會

- 用 `background="transparent"` 和 `output_format="png"` 產生透明 PNG，並檢查 alpha channel 是否真的存在。
- 寫出只描述主體、不帶背景的 prompt，避免模型把背景畫出來。
- 把同一份透明素材套到網站、簡報和服飾 mockup 上重複使用。

## 開跑前

- 需要 `OPENAI_API_KEY`，並有支援透明背景的圖片模型權限。
- 建網站和簡報的部分會用到 Codex。

A great image should work on any background. Transparent image assets make it easy to reuse the same visuals across campaigns, websites, presentations, and product catalogs without white boxes or manual background removal.

好的圖片應該放在任何背景上都能用。透明素材讓你把同一批視覺資產重複用在活動、網站、簡報和商品目錄，不會有白框，也不用手動去背。

這份 cookbook 涵蓋四種客戶情境：

- **季節性電商活動：** 只產生一次透明商品圖，就能放到不同的店面背景、季節 banner 和行銷版型上。
- **品牌企業簡報：** 產生透明圖表，直接融入指定的 PowerPoint 主題和漸層投影片背景。
- **設計模板素材：** 產生 app icon、貼紙和裝飾元素，使用者可以放在任何模板或背景上。
- **隨需列印商品：** 把同一份透明印花設計套到不同的空白衣物和商品 mockup 上。

## 環境設定

用 `pip install openai pillow` 安裝 Python 套件，並在環境變數設定 `OPENAI_API_KEY`。你還需要支援透明背景的圖片模型，以及用來建網站的 Codex。

這個範例用 `gpt-image-2.5-flare`，並以 `background="transparent"` 要求 PNG 輸出。如果想比較偏重高品質需求的模型，把 `IMAGE_MODEL` 設成 `"gpt-image-2.5-sunburst"`，兩個模型都支援透明背景。第一次比較時，prompt、尺寸和 `quality="high"` 都先不要動，先檢查透明度、細緻邊緣和文字，再去調品質或延遲。

下面的圖片和截圖沿用這份 cookbook 原本 GPT Image 2 版本的成果。它們是用來說明流程，不是 GPT Image 2.5 的實測結果。重跑產生圖片的 cell 之前，先備份這些素材，因為重跑會寫到同樣的檔名。

更多背景可以看 [image prompting guide](https://developers.openai.com/api/docs/guides/image-prompting)、[OpenAI models page](https://developers.openai.com/api/docs/models) 和 [image generation guide](https://developers.openai.com/api/docs/guides/image-generation)。

```python
import base64
import os
from pathlib import Path

from openai import OpenAI
from PIL import Image

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Set OPENAI_API_KEY before running this notebook.")

IMAGE_MODEL = "gpt-image-2.5-flare"

client = OpenAI()
asset_dir = Path("images/transparent-image-assets")
asset_dir.mkdir(parents=True, exist_ok=True)
```

## 情境 1：季節性電商活動

一個虛構的居家香氛品牌，想把同一組商品用在多個季節性店面。先一次產生透明商品圖，再把同樣的素材放到不同的活動背景上，不用手動裁切。

### 1.1 定義原始商品 prompt

網站用了同一個虛構香氛品牌的四項商品。每個商品描述後面都接上相同的品牌與透明背景指示，讓整組商品風格一致。

**注意：** prompt 的指示優先於 `background="transparent"`。如果 prompt 描述了背景、場景、顏色或其他背景元素，模型可能會畫出那個背景，而不是輸出透明。prompt 要聚焦在單獨的主體，並明確要求透明背景。

```python
brand_prompt = (
    "One object from STILLROOM, an understated luxury botanical home-fragrance "
    "atelier: artisanal warm amber and honey-tinted hand-blown glass, subtle "
    "brushed brass hardware, natural ivory cotton cord, quiet "
    "Japanese-Scandinavian restraint, warm side-lit editorial studio "
    "photography, photorealistic micro-detail, immaculate premium campaign "
    "quality. Full object completely visible and generously padded. Preserve "
    "every natural transparency, refraction, translucent layer and fine "
    "material edge. Output an isolated object on actual fully transparent "
    "alpha; no backdrop, no rectangle, no plinth, no cast shadow, no readable "
    "writing, no label text, no watermark."
)

products = {
    "amber-parfum": (
        "A sculptural substantial clear honey-amber faceted glass "
        "eau-de-parfum bottle, slender rectangular body with softly rounded "
        "shoulders, heavy clear crystal cap, a small delicate sheer ivory "
        "organza ribbon loosely tied around the brushed brass neck with one "
        "translucent airy tail floating naturally; visible golden fragrance "
        "liquid and beautifully realistic glass refraction."
    ),
    "botanical-oil": (
        "A slim elegant cylindrical deep honey-amber transparent hand-blown "
        "glass botanical body-oil bottle, tall slender polished brushed-brass "
        "dropper cap with tiny ivory rubber bulb, translucent pale golden "
        "botanical oil inside and a tiny delicate preserved sprig of green "
        "wild fennel visible suspended within the liquid; subtle refraction, "
        "premium apothecary design."
    ),
    "reed-diffuser": (
        "A rounded low smoked-amber translucent glass home-fragrance diffuser "
        "vessel containing warm golden scented oil, topped by five naturally "
        "splayed very thin blonde rattan reeds and one extraordinarily "
        "delicate feathery dried pampas grass stem with fine hairlike wisps "
        "extending outward; realistic transparent glass and botanical fibers."
    ),
    "garden-candle": (
        "A quiet luxurious handmade botanical candle in a thick heavy "
        "translucent smoky-amber and milky frosted glass tumbler, creamy "
        "natural ivory wax, one small gently glowing clean candle flame, "
        "delicate transparent-edged frosted glass rim, a loose fine ivory "
        "cotton cord tied around the vessel with one tiny dried eucalyptus "
        "sprig, perfect warm reflections."
    ),
}
```

### 1.2 產生高品質透明 PNG

```python
generate_images = True

if generate_images:
    for filename, product_prompt in products.items():
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=f"{product_prompt} {brand_prompt}",
            background="transparent",
            size="1024x1536",
            quality="high",
            output_format="png",
        )

        image_bytes = base64.b64decode(result.data[0].b64_json)
        (asset_dir / f"{filename}.png").write_bytes(image_bytes)
```

### 1.3 檢查四個產生的商品

這些是活動網站用的原始、未修改的透明 PNG。

| Wild Fig Eau de Parfum | Meadow Botanical Oil |
| --- | --- |
| ![Wild Fig Eau de Parfum in a transparent amber-glass bottle](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/amber-parfum.png) | ![Meadow Botanical Oil in a transparent amber-glass bottle](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/botanical-oil.png) |
| **Cedar Reed Diffuser** | **Garden After Rain Candle** |
| ![Cedar Reed Diffuser with fine reeds and feathery pampas fibers](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/reed-diffuser.png) | ![Garden After Rain Candle in a frosted amber-glass vessel](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/garden-candle.png) |

下一個 cell 會確認每個檔案都有 alpha channel，並回報每張圖有多少比例是完全透明的。

```python
for filename in products:
    with Image.open(asset_dir / f"{filename}.png") as image:
        if image.mode != "RGBA":
            raise ValueError(f"{filename}.png does not have an alpha channel.")

        transparent_pixels = image.getchannel("A").histogram()[0]
        total_pixels = image.width * image.height
        transparent_percentage = 100 * transparent_pixels / total_pixels

        print(
            f"{filename}.png: {image.width}x{image.height}, "
            f"{transparent_percentage:.2f}% fully transparent"
        )
```

### 1.4 用 Codex 建立季節活動網站

把四張產生的 PNG 交給 Codex，請它為 STILLROOM 建一個單頁店面。完成的網站會把同樣的商品放到春、夏、秋、冬四種活動背景上，訪客可以切換單品、雙品或全系列，還有一個棋盤格檢視，讓透明效果看得見。

執行下面的 cell，把輸出連同圖片檔一起貼給 Codex。

```python
codex_prompt = '''
Build a simple, responsive single-page campaign website for STILLROOM, a
premium botanical home-fragrance brand, using these existing transparent PNGs:

- images/transparent-image-assets/amber-parfum.png
- images/transparent-image-assets/botanical-oil.png
- images/transparent-image-assets/reed-diffuser.png
- images/transparent-image-assets/garden-candle.png

Show the heading "One collection, four seasons." Add Spring, Summer, Autumn,
and Winter controls that change the campaign background and seasonal copy.
Include controls for one product, two products, and the full collection.
Let visitors choose the featured product and rearrange the same transparent
PNGs over every background. Add a "Show transparency" checkerboard toggle.
Keep the page visually clean and centered on the products. Do not generate
replacement images or run a separate background-removal step.
'''.strip()

print(codex_prompt)
```

### 1.5 看完成的店面

下面的截圖是同樣四個透明素材，放在不同活動背景和商品排列上的樣子。

**春季活動：四項商品的完整系列，綠色背景。**

![STILLROOM spring campaign website showing all four transparent product images on a green background](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/stillroom-spring-campaign.png)

**冬季活動：兩項商品的排列，深藍色背景。**

![STILLROOM winter campaign website showing the reed diffuser and candle on a dark blue background](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/stillroom-winter-campaign.png)

#### 仔細看難處理的邊緣

切換季節，檢查透明和霧面玻璃、香水瓶上的薄紗緞帶、擴香竹的細竹枝和髮絲般的蒲葦纖維，還有蠟燭的細棉芯。傳統的去背工具可能會切掉這些細節、產生光暈，或把半透明材質壓平。直接產生 alpha channel，能在同一件商品放到差異很大的背景上時，保留這些細微的邊緣。

## 情境 2：品牌企業簡報

企業團隊常常得用指定的 PowerPoint 主題，背景有特定顏色或漸層。AI 產生的圖表如果是不透明的白底，會跟主題衝突，透明 PNG 則能讓投影片原本的背景露出來。

### 2.1 定義簡報情境和模擬的業務資料

虛構的 Northstar Cloud 董事會檢討投影片用兩組資料：每季營收，以及合格銷售機會的區域分布。這些數字只是範例，不是真實的公司成果。


```python
quarterly_revenue = {
    "Q1": 42,
    "Q2": 51,
    "Q3": 63,
    "Q4": 78,
}

regional_pipeline = {
    "North America": 46,
    "Europe": 29,
    "APAC": 25,
}

revenue_growth = (
    (quarterly_revenue["Q4"] - quarterly_revenue["Q1"])
    / quarterly_revenue["Q1"]
)

print(f"Quarterly revenue: {quarterly_revenue} USD millions")
print(f"Regional pipeline: {regional_pipeline} percent")
print(f"Q1-to-Q4 revenue growth: {revenue_growth:.0%}")
```

### 2.2 定義透明圖表的 prompt

要求整張圖表都是透明區域，不只是輪廓外面。深色企業主題還要指定白色或淺色的標籤、明亮且符合品牌的顏色，以及不要卡片、外框、面板或填色的繪圖區。

模型會拿到精確的模擬數值，但產生的圖片內容終究是點陣圖。使用前要檢查標籤、數值和比例是否跟來源資料一致。如果正式報表需要精確的數字，圖表請用程式確定性地繪製，圖片生成留給插圖或其他視覺元素。


```python
revenue_values = ", ".join(
    f"{quarter} = ${amount}M"
    for quarter, amount in quarterly_revenue.items()
)

pipeline_values = ", ".join(
    f"{region} = {percentage}%"
    for region, percentage in regional_pipeline.items()
)

chart_prompts = {
    "quarterly-revenue-growth": (
        "Create one polished enterprise bar chart on a genuinely "
        "transparent background for a dark navy PowerPoint slide. "
        f"Use exactly four ascending bars with these values: {revenue_values}. "
        "Use cobalt blue, bright blue, electric azure, and turquoise bars. "
        "Add white quarter labels below each bar and white dollar-value "
        "labels above each bar. Add a subtle turquoise upward-trend arrow. "
        "Keep the plot area, grid, and space between bars transparent. "
        "Do not add a background, filled panel, frame, title, or card."
    ),
    "regional-pipeline-mix": (
        "Create one polished enterprise doughnut chart on a genuinely "
        "transparent background for a dark navy PowerPoint slide. "
        f"Use exactly these regional pipeline shares: {pipeline_values}. "
        "Use turquoise, cobalt blue, and coral segments, with a white "
        "100% label in the center. Place a white-text regional legend "
        "beside the chart. Keep the doughnut center, legend area, and "
        "all surrounding space transparent. Do not add a background, "
        "filled panel, frame, title, or card."
    ),
}
```

### 2.3 產生透明 PNG 圖表

跟商品範例一樣，要求 `background="transparent"` 和 `output_format="png"`。橫向的 `1536x1024` 讓圖表有足夠空間放標籤，`quality="high"` 則有助於小字。


```python
generate_charts = True

if generate_charts:
    for filename, prompt in chart_prompts.items():
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            background="transparent",
            size="1536x1024",
            quality="high",
            output_format="png",
        )

        image_bytes = base64.b64decode(result.data[0].b64_json)
        (asset_dir / f"{filename}.png").write_bytes(image_bytes)
```

### 2.4 檢查產生的圖表素材

下面是兩個獨立的透明 PNG，可以直接放到企業投影片主題上。

| Quarterly revenue | Regional pipeline mix |
| --- | --- |
| ![Transparent bar chart showing quarterly revenue increasing from 42 million to 78 million dollars](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/quarterly-revenue-growth.png) | ![Transparent doughnut chart showing regional pipeline shares for North America, Europe, and APAC](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/regional-pipeline-mix.png) |

下一個 cell 會檢查兩個檔案是否有真正的 alpha channel，並回報每張圖表有多少比例是完全透明的。


```python
for filename in chart_prompts:
    with Image.open(asset_dir / f"{filename}.png") as image:
        if image.mode != "RGBA":
            raise ValueError(f"{filename}.png does not have an alpha channel.")

        transparent_pixels = image.getchannel("A").histogram()[0]
        total_pixels = image.width * image.height
        transparent_percentage = 100 * transparent_pixels / total_pixels

        if transparent_pixels == 0:
            raise ValueError(f"{filename}.png has no fully transparent pixels.")

        print(
            f"{filename}.png: {image.width}x{image.height}, "
            f"{transparent_percentage:.2f}% fully transparent"
        )
```

### 2.5 用 Codex 建立品牌 PowerPoint 投影片

把兩張透明圖表 PNG、模擬的來源資料和指定的投影片主題交給 Codex。請它保留 alpha channel，使用投影片原生的背景，不要加白色矩形或裝飾性的背景形狀。

執行下面的 cell，把輸出連同圖表圖片檔一起貼給 Codex。


```python
presentation_prompt = f"""
Create one editable 16:9 PowerPoint slide for a fictional NORTHSTAR CLOUD
FY26 Q4 board review using these existing transparent PNG charts:

- images/transparent-image-assets/quarterly-revenue-growth.png
- images/transparent-image-assets/regional-pipeline-mix.png

Mock quarterly revenue, in USD millions: {quarterly_revenue}
Mock regional pipeline mix, in percent: {regional_pipeline}
Q1-to-Q4 revenue growth: {revenue_growth:.0%}

Use a subtle dark navy-to-teal gradient as the slide's native background.
Add the headline "Growth is accelerating across every region."
Add the subheadline "Revenue climbed 86% over four quarters while pipeline
stayed globally diversified."

Place the quarterly revenue chart on the left and the regional pipeline chart
on the right. Add a heading and short data description above each chart.
Preserve each PNG's real alpha channel so the gradient remains visible behind
both charts. Do not add white image frames, background panels, decorative
shapes, or a separate background-removal step.

Keep the slide clear, polished, and consistent with an enterprise board-deck
template. Add the fictional company name, reporting period, confidentiality
notice, and page number as editable PowerPoint text.
""".strip()

print(presentation_prompt)
```

### 2.6 看完成的企業投影片

PowerPoint 檔案不會直接在 notebook 輸出裡顯示，所以下面的圖是完成的單頁簡報。兩張產生的圖表在 PowerPoint 檔案裡仍然是獨立的 PNG 素材。

![Enterprise board-review slide with transparent quarterly revenue and regional pipeline charts placed directly on a subtle navy-to-teal gradient background](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/enterprise-chart-slide.png)

漸層在長條後面、甜甜圈圖的中間和每個標籤周圍都看得到，因為這些圖表有真正的 alpha channel。團隊可以把產生的視覺素材加進指定的企業簡報主題，不會出現礙眼的白框。


## 情境 3：設計模板素材

設計平台需要能用在各種版面的 app icon、貼紙和裝飾元素。用透明背景產生這些元素，使用者就能把同樣的素材放進任何模板，不用遮罩、去背或重畫背景。

### 3.1 產生透明的設計元素

```python
design_prompts = {
    "design-app-icon": (
        "Create one premium rounded-square app icon with an abstract "
        "folded paper bird in cobalt blue, lavender, and peach. Keep "
        "everything outside the rounded icon tile transparent. No text, "
        "watermark, shadows, or background."
    ),
    "design-sticker": (
        "Create one illustrated strawberry character sticker with rich "
        "coral-red fruit, sage-green leaves, and a close-fitting cream "
        "die-cut border. Keep everything outside the sticker border "
        "transparent. No text, watermark, shadows, or background."
    ),
    "design-decoration": (
        "Create one delicate editorial botanical sprig with fine "
        "dark-sage branches, muted green leaves, and small coral berries. "
        "Keep all space around and between the thin branches and leaves "
        "transparent. No text, shadows, or background."
    ),
}

generate_design_assets = True

if generate_design_assets:
    for filename, prompt in design_prompts.items():
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            background="transparent",
            size="1024x1024",
            quality="high",
            output_format="png",
        )

        image_bytes = base64.b64decode(result.data[0].b64_json)
        (asset_dir / f"{filename}.png").write_bytes(image_bytes)
```

### 3.2 把素材放到簡單的網站上

每個素材都是獨立的透明 PNG，可以移動、縮放，或用在別的模板上。

| App icon | Transparent sticker | Decorative element |
| --- | --- | --- |
| ![Transparent rounded app icon with an abstract folded paper bird](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/design-app-icon.png) | ![Transparent strawberry character sticker with a close-fitting die-cut border](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/design-sticker.png) | ![Transparent botanical decoration with fine branches and separate leaves](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/design-decoration.png) |

範例網頁把三個素材組合在有顏色的模板上，訪客可以切換背景，同樣的 PNG 維持在原位。

![Simple design-template website showing a transparent app icon, strawberry sticker, and botanical decoration reused on a colored canvas](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/design-template-studio.png)

## 情境 4：隨需列印商品

商品平台可以產生一份可直接列印的透明設計，放到不同商品上，不用針對每種衣物顏色去掉白色矩形。同一份圖案可以變成 T 恤、大學 T 或賣家目錄裡的其他商品。

### 4.1 產生可重複使用的印花設計和空白衣物

```python
merchandise_prompts = {
    "merchandise-design": (
        "Create one premium outdoors-inspired apparel illustration with "
        "an amber setting sun, slate-blue mountains, evergreen pine trees, "
        "a pale turquoise river, and small coral wildflowers. Arrange the "
        "elements into an organic compact circular composition with subtle "
        "screen-print texture. Keep the surrounding area and open spaces "
        "between the graphic elements transparent. No text, bounding "
        "badge, white rectangle, garment, or background."
    ),
    "merchandise-blank-tshirt": (
        "Create one photorealistic premium unisex ivory crew-neck T-shirt "
        "shown completely flat, front-facing, and centered. Leave the "
        "chest completely blank for a print design and keep everything "
        "outside the garment silhouette transparent. No person, hanger, "
        "mannequin, logos, graphics, shadows, or background."
    ),
    "merchandise-blank-sweatshirt": (
        "Create one photorealistic premium forest-green crew-neck "
        "sweatshirt shown completely flat, front-facing, and centered. "
        "Leave the chest completely blank for a print design and keep "
        "everything outside the garment silhouette transparent. No "
        "person, hanger, mannequin, logos, graphics, shadows, or background."
    ),
}

generate_merchandise_assets = True

if generate_merchandise_assets:
    for filename, prompt in merchandise_prompts.items():
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            background="transparent",
            size="1024x1024",
            quality="high",
            output_format="png",
        )

        image_bytes = base64.b64decode(result.data[0].b64_json)
        (asset_dir / f"{filename}.png").write_bytes(image_bytes)
```

### 4.2 把一份設計套到多個商品

印花圖案和兩件空白衣物都是各自獨立的透明圖片。分開保存，賣家就能把設計用在不同衣物類型、商品顏色和之後的目錄版型上。

| Reusable print design | Blank ivory T-shirt | Blank forest-green sweatshirt |
| --- | --- | --- |
| ![Transparent outdoor apparel illustration with mountains, pine trees, and a setting sun](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/merchandise-design.png) | ![Transparent product photograph of a blank ivory crew-neck T-shirt](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/merchandise-blank-tshirt.png) | ![Transparent product photograph of a blank forest-green crew-neck sweatshirt](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/merchandise-blank-sweatshirt.png) |

用 Pillow 裁掉透明的空白邊緣，把同一份圖案放到每件衣物上，再做出簡單的雙商品目錄預覽。

```python
from PIL import ImageDraw, ImageFont


def visible_region(image):
    # Remove fully transparent padding without changing visible pixels.
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("Expected a transparent PNG with visible artwork.")
    return image.crop(bounds)


canvas = Image.new("RGBA", (1600, 1020), "#f7f5f0")
draw = ImageDraw.Draw(canvas)

heading_font = ImageFont.load_default(size=57)
body_font = ImageFont.load_default(size=21)
label_font = ImageFont.load_default(size=25)
small_font = ImageFont.load_default(size=17)

draw.text((86, 70), "One design, ready to wear.", font=heading_font, fill="#202a27")
draw.text(
    (89, 151),
    "One transparent artwork. Two products. No background removal.",
    font=body_font,
    fill="#68726d",
)

with Image.open(asset_dir / "merchandise-design.png") as image:
    print_design = visible_region(image.convert("RGBA"))

garments = [
    ("merchandise-blank-tshirt", "Everyday T-shirt", "Natural cotton"),
    ("merchandise-blank-sweatshirt", "Essential sweatshirt", "Forest green"),
]

for index, (filename, title, color) in enumerate(garments):
    card_x = 86 + index * 741
    card_y = 221
    card_width = 690
    card_height = 691

    draw.rounded_rectangle(
        (card_x, card_y, card_x + card_width, card_y + card_height),
        radius=28,
        fill="#ffffff",
    )

    with Image.open(asset_dir / f"{filename}.png") as image:
        garment = visible_region(image.convert("RGBA"))

    garment.thumbnail((610, 505), Image.Resampling.LANCZOS)
    garment_x = card_x + (card_width - garment.width) // 2
    garment_y = card_y + 55 + (505 - garment.height) // 2

    artwork = print_design.copy()
    artwork.thumbnail(
        (round(garment.width * 0.32), round(garment.height * 0.32)),
        Image.Resampling.LANCZOS,
    )

    chest_x = (garment.width - artwork.width) // 2
    chest_y = round(garment.height * 0.28)
    garment.alpha_composite(artwork, dest=(chest_x, chest_y))
    canvas.alpha_composite(garment, dest=(garment_x, garment_y))

    draw.text((card_x + 41, card_y + 578), title, font=label_font, fill="#202a27")
    draw.text((card_x + 41, card_y + 620), color, font=small_font, fill="#68726d")

output_path = asset_dir / "merchandise-print-mockups.png"
canvas.convert("RGB").save(output_path, optimize=True)
print(f"Saved merchandise preview to {output_path}")
```

同一份透明設計自然地融入兩種衣物顏色，空白商品仍然可以留給其他設計使用。

![Print-on-demand catalog showing the same transparent outdoor illustration printed on an ivory T-shirt and a forest-green sweatshirt](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/transparent-image-assets/merchandise-print-mockups.png)

## 評估產生的素材

針對有代表性的活動、投影片、設計模板和商品 mockup，收集人工對透明度、邊緣品質、品牌契合度和實用性的回饋。也可以用具備視覺能力的語言模型，依明確的評分標準檢查同一批素材，標出不透明的背景、被切掉的細節、衣物上位置不佳的圖案，以及跟來源資料不符的圖表標籤。

## 結論

透明 PNG 素材讓團隊能把產生的圖片重複用在季節活動、品牌簡報、設計模板和商品目錄，不用手動去背。再搭配人工和視覺模型的評估，用量變大時也能維持創意產出的一致性。

## 重點整理

- `background="transparent"` 搭配 `output_format="png"` 會直接產生 alpha channel，邊緣比事後去背更能保留細節。
- prompt 只能描述孤立的主體，只要寫到背景或場景，模型就可能照畫，透明設定會被蓋過。
- 圖表要求整張透明，包含繪圖區內部，深色主題要指定淺色標籤。
- 圖片生成出來的圖表是點陣圖，數字要檢查；需要精確數值的正式報表請用程式繪製。
- 素材和空白商品分開保存，才能在不同背景、衣物和版型間重複使用。

## 練習

1. 把產生商品圖的 cell 裡的 `quality` 改成別的值，比較透明邊緣和細節的差異。
2. 在某個商品 prompt 故意加上一句背景描述，看看輸出還是不是透明，再改回去。
3. 改檢查 alpha channel 的 cell，額外算出每張圖「半透明像素」（alpha 介於 0 和 255 之間）的比例，用來判斷邊緣品質。
