---
translated: true
source: examples/multimodal/document_and_multimodal_understanding_tips.ipynb
---
# 用 GPT-5.4 發揮視覺與文件理解的最佳表現

> 原文：[examples/multimodal/document_and_multimodal_understanding_tips.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/document_and_multimodal_understanding_tips.ipynb)

用 GPT-5.4 處理視覺任務、拿到最佳表現的實用指南。

## 這篇在做什麼

整理用 GPT-5.4 處理文件和圖片時，影響結果最大的幾個 request 參數：image detail、verbosity、reasoning effort 和 Code Interpreter。每個設定都搭配實際範例（手寫表單、報紙、平面圖、圖表、賽程表、警察報告表單），說明什麼情況該調哪一個。

## 學完你會

- 依失敗的樣子選對設定：小字或手寫用 `detail="original"`，要逐字轉錄用高 verbosity，需要整合多區域資訊就提高 reasoning effort。
- 用 Code Interpreter 加上固定座標格式（`[x_min, y_min, x_max, y_max]`，`0..999`）做 bounding box 定位。
- 在不能用 Code Interpreter 的環境，改用「定位、本機裁切、重跑」的流程。

## 開跑前

需要 `OPENAI_API_KEY`，並且帳號要能使用 GPT-5.4 和 Responses API。


GPT-5.4 是真實世界多模態工作負載的一大進步。

以前讓視覺系統吃力、或需要把 OCR、版面偵測和自訂 parser 拼在一起的文件，包括密集的掃描檔、手寫表單、工程圖和滿是圖表的報告，現在常常能用 GPT-5.4 一次推論就解讀並推理完。

不過，要拿到最好的結果，模型設定是關鍵。image detail、verbosity、reasoning effort 和 tool 使用這些小選擇，會大幅影響表現。

這份 notebook 專注在對文件工作影響最大的幾個調整：image detail、verbosity、reasoning effort 和 tool 使用。目標是說明每一個在什麼時候重要、會怎麼改變輸出，以及怎麼選出既穩健又實用的設定組合。

這份 notebook 的所有範例都透過 `client.responses.create(...)` 使用 **Responses API**。我們說的「設定」就是傳進這個呼叫的 request 參數。

### 輸入格式

- **`input`**：類似 message 的物件列表（通常是一個 `{ "role": "user", "content": [...] }`）
- **`content`**：有型別的區塊列表，通常是：
  - `{ "type": "input_text", "text": "..." }`
  - `{ "type": "input_image", "image_url": "...", "detail": "auto" | "original" }`

### 這份 notebook 會用到的參數

- **Image detail**（`input_image.detail`）：控制視覺處理時使用的圖片解析度。大多數頁面用 `"auto"`；文字很小、手寫或掃描品質差時用 `"original"`。
- **Verbosity**（`text={"verbosity": ...}`）：影響文字輸出是壓縮還是逐字貼近原文。要忠實轉錄時，高 verbosity 有幫助。
- **Reasoning effort**（`reasoning={"effort": ...}`）：在圖片已經看得清楚之後，把更多算力用在多步驟的視覺推理（圖表、表格、示意圖）。
- **Tool 使用**（`tools=[...]` + `instructions=...`）：可選擇讓模型在回答前使用像 **Code Interpreter** 這樣的 tool 做縮放、裁切、檢查；一次回答就夠的話就不要加 tool。

最簡單的 request 長這樣：

```python
response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Extract the total amount due."},
                {
                    "type": "input_image",
                    "image_url": "data:image/png;base64,...",
                    "detail": "auto",
                },
            ],
        }
    ],
)
```

### 輸出格式

- 模型會回傳一個 **response 物件**，裡面有一個或多個 output item。
- 這份 notebook 大多用 `response.output_text` 來方便地取得最終文字。
- **結構化輸出**拿到的仍然是文字，只是你用 `text={"format": ...}` 要求模型輸出成 JSON，再用 `json.loads(response.output_text)` 解析。


## 快速決策指南
這張表可以當起點。好的經驗法則是先從簡單設定開始，再針對失敗的樣子調整對應的設定。

| 如果你的任務像這樣 | 先用這個設定 | 原因 |
|---|---|---|
| 一般文件問答或擷取 | `detail="auto"` | 對清晰頁面來說，阻力最低的預設值 |
| 密集掃描檔、螢幕截圖、手寫或很小的標籤 | `detail="original"` | 保留常常會流失的細小視覺訊號 |
| 逐字轉錄或轉成 markdown | `text={"verbosity": "high"}` | 鼓勵模型保留更多版面，少做改寫 |
| 區域定位 | 要求回傳固定 `0..999` 網格中的 `[x_min, y_min, x_max, y_max]` | 容易裁切、畫框、除錯，也方便餵給下游系統 |
| 跨多個區域的圖表、表格、表單或圖面問答 | 把 reasoning effort 提高到 'high' 或 'xhigh' | 改善多步驟視覺推理 |
| 多輪視覺檢查 | 加上 Code Interpreter | 適合人類會先縮放、裁切、旋轉或檢查好幾個子區域才回答的情況 |

## 環境設定

執行這份 notebook 之前，請確認環境裡已設定 `OPENAI_API_KEY`。如果還沒有 API key，可以到 [platform.openai.com](https://platform.openai.com/api-keys) 建立。

```bash
export OPENAI_API_KEY="your_api_key_here"
```

需要的話，安裝 notebook 的相依套件：

```bash
pip install --upgrade openai pillow
```

```python
import base64
import json
import mimetypes
import tempfile
from pathlib import Path

from IPython.display import Markdown, display
from PIL import Image, ImageDraw
from openai import OpenAI

client = OpenAI()
```

```python
### Helper function

def image_to_data_url(image_path: str | Path) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
```

## 1. 密集頁面和手寫：提高 image detail

`detail` 參數控制模型處理圖片時使用的解析度。大多數應用應該從 `detail="auto"` 開始，讓模型自己選合適的解析度。但如果頁面有手寫、小標籤、密集表格、低對比的掃描檔，或是有細小文字的螢幕截圖，改成 `detail="original"` 可以大幅改善結果。如果模型大致正確，卻一直漏掉小欄位或註記，提高 image detail 通常是第一個該試的調整。

這個範例刻意放了很小的 email 和電話欄位，而不只是較大的手寫姓名。圖片被降低解析度時，最先劣化的就是這類細節。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/3C_insurance_form.png" alt="Handwritten insurance form" style="max-width: 100%; width: 720px;" />


````python
handwriting_prompt = """
Read the handwritten earthquake insurance application and return JSON with these keys:
- applicant_name
- applicant_email
- applicant_home_phone
- applicant_cell_phone
- co_applicant_name
- co_applicant_email
- co_applicant_home_phone
- co_applicant_work_phone
- effective_date
- expiration_date
- dwelling_coverage_limit_usd
- square_footage
- year_of_construction
"""

handwritten_form_path = "../../images/3C_insurance_form.png"
handwriting_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": handwriting_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(handwritten_form_path),
                    "detail": "original",
                },
            ],
        }
    ],
    text={"format": {"type": "json_object"}
    },
)

handwriting_result = json.loads(handwriting_response.output_text)
display(Markdown(f"### Extracted insurance form\n\n```json\n{json.dumps(handwriting_result, indent=2, ensure_ascii=False)}\n```"))
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 2. 要忠實轉錄：提高 verbosity

請多模態模型轉錄文件時，它們傾向壓縮版面。意思會保留，但空白、換行和類似表格的排版可能被簡化。這種行為在問答時通常是好事，但在 OCR 類的任務就不是。

提高 verbosity，也就是 `text={"verbosity": "high"}`，會讓模型更偏向逐字呈現和精確轉錄。OCR 類的工作負載，以及重視完整性和格式忠實度的目標擷取，都適合這個設定。

下面的範例用 `Ticket To The Arts` 版面，要求完整轉錄四則刊登內容，同時固定 image detail 不變。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/newspaper.png" alt="Newspaper clipping" style="max-width: 100%; width: 720px;" />


````python
section_prompt = "Transcribe everything in the Ticket To The Arts section. Do not summarize or paraphrase. Do not add any additional text."

newspaper_path = "../../examples/multimodal/images/newspaper.png"
section_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": section_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(newspaper_path),
                    "detail": "original",
                },
            ],
        }
    ],
    text={"verbosity": "high"},
)

display(Markdown(f"### Transcription preview\n\n```text\n{section_response.output_text}\n```"))
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 3. 圖片看得清楚但答案需要組合資訊：提高 reasoning effort

圖片讀得清楚之後，下一個瓶頸常常是推理而不是感知。這在答案必須整合圖片多個部分的資訊、而不是讀單一欄位的文件上很常見。圖表、表格、技術示意圖和密集的視覺版面常屬於這一類。

這種情況下，提高 reasoning effort（`reasoning={"effort": "high"}`）可能比提高 image detail 更有幫助。模型已經看到內容了，它需要的是更多能力去連結標籤、比較區域、跟隨結構，並正確算出最終答案。

下面是幾種不同類型的任務或圖片，更高的 reasoning 在這些情況下有幫助。

### 範例：平面圖推理

下面的平面圖是個好例子，任務已經超出轉錄。要答對，模型得讀房間標籤、理解空間關係，並利用圖上可見的尺寸算出數值。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/apartment_floorplan.png" alt="Apartment floorplan" style="max-width: 100%; width: 720px;" />


````python
floorplan_prompt = """
Inspect this apartment floorplan and return JSON with these keys:
- total_named_rooms_excluding_hallways_and_closets
- largest_room
- room_immediately_east_of_kitchen
- room_immediately_south_of_study
- bedroom_1_total_area_ft2
- bedroom_2_total_area_ft2

Rules:
- Use the room labels and dimension annotations that are visible on the drawing.
- Return integers for numeric fields.
- Return JSON only.
"""

floorplan_path = "../../examples/multimodal/images/apartment_floorplan.png"
floorplan_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": floorplan_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(floorplan_path),
                    "detail": "original",
                },
            ],
        }
    ],
    reasoning={"effort": "high"},
    text={"format": {"type": "json_object"}},
)

floorplan_result = json.loads(floorplan_response.output_text)
display(Markdown(f"### Floorplan reasoning result\n\n```json\n{json.dumps(floorplan_result, indent=2, ensure_ascii=False)}\n```"))
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

### 範例：圖表理解

圖表理解也有同樣的模式。如果任務只是讀標題或找出某一個點的數值，預設設定可能就夠了。但如果答案取決於比較多條數列、追蹤相鄰區間的變化，或估計隨時間的趨勢，推理就會變成限制因素。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/NotRealCorp_chart.png" alt="Line chart" style="max-width: 100%; width: 720px;" />


````python
chart_prompt = """
Inspect this line chart and return a JSON with these keys:
- largest_qoq_increase: {"channel": ..., "from_quarter": ..., "to_quarter": ..., "approx_delta_millions": ...}
- largest_qoq_drop: {"channel": ..., "from_quarter": ..., "to_quarter": ..., "approx_delta_millions": ...}
- fastest_growing_channel_overall

Rules:
- Use approximate values only when exact values are not printed.
- Base the answer on the visible lines and quarter labels.
- Return JSON only.
"""

chart_path = "../../images/NotRealCorp_chart.png"
chart_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": chart_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(chart_path),
                    "detail": "original",
                },
            ],
        }
    ],
    reasoning={"effort": "high"},
    text={"format": {"type": "json_object",}},
)

chart_result = json.loads(chart_response.output_text)
display(Markdown(f"### Chart reasoning result\n\n```json\n{json.dumps(chart_result, indent=2, ensure_ascii=False)}\n```"))
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

### 範例：密集賽程表的長距離視覺推理

密集的比賽賽程表很適合用來測試 reasoning，因為模型要在擁擠的版面中沿著路徑追蹤，分清左右兩邊的區域，並在不迷失結構的情況下找出最終結果。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/bracket.png" alt="Tournament bracket" style="max-width: 100%; width: 1000px;" />


````python
bracket_prompt = """
Inspect this tournament bracket image and return JSON with these keys:
- left_bracket_title
- right_bracket_title
- mens_champion_team
- womens_champion_team
- mens_runner_up_team
- womens_runner_up_team

Rules:
- Use the visible central championship score boxes.
- Team labels may include seeds; if you include a seed, keep it attached to the same string.
- Return JSON only.
"""

bracket_path = "../../examples/multimodal/images/bracket.png"
bracket_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": bracket_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(bracket_path),
                    "detail": "original",
                },
            ],
        }
    ],
    reasoning={"effort": "high"},
    text={"format": {"type": "json_object"}},
)

bracket_result = json.loads(bracket_response.output_text)
display(Markdown(f"### Bracket reasoning result\n\n```json\n{json.dumps(bracket_result, indent=2, ensure_ascii=False)}\n```"))
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 4. 多輪檢查和 bounding box 定位：用 Code Interpreter

有些文件任務用人的方式來解比較容易：看整頁、縮放或裁切某個區域、檢查另一個地方，再把證據整合成最終答案。

Code Interpreter 在這些視覺任務特別有用：
- 頁面很密集，證據分散在多個區域
- 模型需要縮放、裁切、旋轉，或做中間檢查
- 品質上的準確度比最低延遲更重要

對定位任務（包含 bounding box），除了開放 code interpreter，還要給嚴格的座標約定，例如 `[x_min, y_min, x_max, y_max]`，以及固定的座標空間，像是原點在左上角的 `0..999`。

實務上，這個組合（code interpreter 加上明確的框格式）通常比單次視覺呼叫更可靠、更可重現。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/multimodal/images/police_form.png" alt="Police report form" style="max-width: 100%; width: 720px;" />


````python
bbox_prompt = """
Find the license plate number for Vehicle 1 and Vehicle 2 in this police report form.
It is written after License # and is a 7-digit number.
Do not guess or infer the license plate number.

Return JSON with this schema:
{
  "b": [
    {"label": "vehicle_1_license_plate", "bbox": [x_min, y_min, x_max, y_max]},
    {"label": "vehicle_2_license_plate", "bbox": [x_min, y_min, x_max, y_max]}
  ]
}

Use discrete normalized coordinates between 0 and 999.
Return JSON only.
"""

police_form_path = "../../examples/multimodal/images/police_form.png"
with Path(police_form_path).open("rb") as asset_file:
    uploaded_file = client.files.create(file=asset_file, purpose="user_data")

bbox_schema = {
    "type": "object",
    "properties": {
        "b": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "enum": ["vehicle_1_license_plate", "vehicle_2_license_plate"],
                    },
                    "bbox": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 999},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["label", "bbox"],
                "additionalProperties": False,
            },
            "minItems": 2,
            "maxItems": 2,
        }
    },
    "required": ["b"],
    "additionalProperties": False,
}

bbox_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": bbox_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(police_form_path),
                    "detail": "original",
                },
            ],
        }
    ],
    reasoning={"effort": "high"},
    text={
        "format": {
            "type": "json_schema",
            "name": "plate_bboxes",
            "schema": bbox_schema,
            "strict": True,
        }
    },
    instructions=(
        "You are an expert document analyst. Use Code Interpreter before answering. "
        "Inspect the uploaded file, crop or zoom if needed, then answer in JSON."
    ),
    tools=[
        {
            "type": "code_interpreter",
            "container": {
                "type": "auto",
                "memory_limit": "4g",
                "file_ids": [uploaded_file.id],
            },
        }
    ],
)

bbox_results = json.loads(bbox_response.output_text)["b"]
display(Markdown(f"### Detected plate regions\n\n```json\n{json.dumps(bbox_results, indent=2, ensure_ascii=False)}\n```"))

annotated = Image.open(police_form_path).convert("RGB")
draw = ImageDraw.Draw(annotated)
width, height = annotated.size
palette = ["red", "dodgerblue", "limegreen", "orange", "magenta", "cyan"]

for index, item in enumerate(bbox_results):
    color = palette[index % len(palette)]
    x_min, y_min, x_max, y_max = item["bbox"]
    pixel_bbox = [
        round(x_min * (width - 1) / 999),
        round(y_min * (height - 1) / 999),
        round(x_max * (width - 1) / 999),
        round(y_max * (height - 1) / 999),
    ]
    draw.rectangle(pixel_bbox, outline=color, width=4)
    draw.text((pixel_bbox[0] + 4, max(0, pixel_bbox[1] - 16)), item["label"], fill=color)

display(annotated)
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 5. 不能用 Code Interpreter：做窄範圍的裁切再重跑流程

在受限的環境裡，你可能不想給模型一個通用的 Python sandbox。實用的替代方案是兩階段流程：

1. 定位你在意的欄位或區域
2. 在本機裁切該區域
3. 對裁切結果重跑一個更小、更聚焦的 prompt

這通常能拿回多輪檢查的大部分價值，同時讓可操作的範圍保持很小。


````python
target_region = next(
    item for item in bbox_results if item["label"] == "vehicle_2_license_plate"
)

source_image = Image.open(police_form_path).convert("RGB")
width, height = source_image.size
x_min, y_min, x_max, y_max = target_region["bbox"]
pixel_bbox = [
    round(x_min * (width - 1) / 999),
    round(y_min * (height - 1) / 999),
    round(x_max * (width - 1) / 999),
    round(y_max * (height - 1) / 999),
]
padding = 0.18
pad_x = round((pixel_bbox[2] - pixel_bbox[0]) * padding)
pad_y = round((pixel_bbox[3] - pixel_bbox[1]) * padding)
crop = source_image.crop(
    (
        max(0, pixel_bbox[0] - pad_x),
        max(0, pixel_bbox[1] - pad_y),
        min(width, pixel_bbox[2] + pad_x),
        min(height, pixel_bbox[3] + pad_y),
    )
)

tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
crop_path = Path(tmp.name)
tmp.close()
crop.save(crop_path)

display(crop)

crop_prompt = """
Read the license number value in this cropped police-form region.
It is next to the word License #.

Return JSON with one key:
- license_number

Return JSON only.
"""

crop_schema = {
    "type": "object",
    "properties": {
        "license_number": {"type": "string"},
    },
    "required": ["license_number"],
    "additionalProperties": False,
}

crop_response = client.responses.create(
    model="gpt-5.4",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": crop_prompt},
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(crop_path),
                    "detail": "original",
                },
            ],
        }
    ],
    text={
        "format": {
            "type": "json_schema",
            "name": "license_number_extraction",
            "schema": crop_schema,
            "strict": True,
        }
    },
)

crop_result = json.loads(crop_response.output_text)
display(Markdown(f"### Crop-and-rerun result\n\n```json\n{json.dumps(crop_result, indent=2, ensure_ascii=False)}\n```"))
````

??? note "輸出"

    ![](document_and_multimodal_understanding_tips_files/out_21_0.png)

    ```text
    <IPython.core.display.Markdown object>
    ```

## 結論

總結一下：先從簡單的開始。任務簡單、頁面清楚時，用原生視覺、`detail="auto"`，不加 tool。

文字很小、手寫、低對比，或掃描品質差時，提高 image detail（`detail="original"`）。

需要忠實轉錄而不是壓縮摘要時，提高 verbosity。

圖片看得清楚、但答案需要整合多個區域時，提高 reasoning effort。

需要多輪檢查（縮放、裁切、旋轉）時用 Code Interpreter，尤其是密集頁面。

做 bounding box 時，要求嚴格的約定：固定 `0..999` 座標空間（左上角為原點）中的 `[x_min, y_min, x_max, y_max]`，並強制結構化 JSON 輸出。

如果不能用 Code Interpreter，就用裁切再重跑：定位、在本機裁切，再跑聚焦的擷取 prompt。

在受限環境裡，提供輕量的視覺工具（裁切、縮放、旋轉、OCR 區域備援），可以控制得更緊。

## 重點整理

- 從簡單設定開始，再針對失敗的樣子調整對應的參數，不要一次全開。
- 小字和手寫是感知問題，用 `detail="original"`；需要整合多區域資訊是推理問題，提高 reasoning effort。
- 逐字轉錄要用高 verbosity，不然模型會壓縮版面。
- 定位任務要給固定的座標約定並輸出結構化 JSON，才好下游處理。
- 沒有 Code Interpreter 時，用「定位、本機裁切、重跑」也能拿回多輪檢查的大部分效果。

## 練習

1. 拿保險表單範例，把 `detail` 分別設成 `"auto"` 和 `"original"`，比較小欄位（email、電話）的辨識差異。
2. 在報紙範例中，把 `verbosity` 從預設改成 `"high"`，檢查換行和排版有沒有更貼近原文。
3. 在平面圖或圖表範例中，把 reasoning effort 從低調到 `"high"`，並寫一個需要跨區域計算的新問題，比較答案的正確性和花費的 token。
