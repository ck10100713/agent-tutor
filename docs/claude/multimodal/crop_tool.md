---
translated: true
source: multimodal/crop_tool.ipynb
---

# 給 Claude 一個 zoom tool，讓它讀懂圖片裡的細節

> 原文：[multimodal/crop_tool.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/multimodal/crop_tool.ipynb)

給 Claude 一個 zoom tool，它可以裁出指定區域並放大，用來仔細分析圖表、文件和示意圖。

## 這篇在做什麼

Claude 看圖只看一次，而且解析度固定，圖上的小字或靠得很近的線條看不清時，再怎麼調 prompt 也沒用。這篇做一個 zoom tool，Claude 想看細節時就呼叫它，工具從原始高解析度圖片裁出該區域並放大回傳。在公開的圖表閱讀 benchmark 上，準確率成長超過一倍。

## 學完你會

- 用官方文件的 `resized_size()` 先把圖縮好，讓 Claude 給的像素座標跟你手上的圖 1:1 對得上
- 寫出一個可以直接搬進任何專案的 zoom tool：輸入絕對像素座標，輸出放到預算上限的放大裁圖
- 跑完整的 agentic loop，並處理 stop reason，避免長時間思考的回合被悄悄截斷

## 開跑前

需要 Anthropic API key，以及 Python 3.11 以上。這個 tool 會多花 token，每次 zoom 都要重送整段對話加一張放大圖。

## 簡介

圖上有東西太小看不清楚時，你會湊近看。Claude 自己做不到這件事：它看圖只有一次，解析度固定，圖表標籤或兩條很靠近的線在那個解析度下太小，就是看不出來。

zoom tool 就是給 Claude「湊近看」的動作。

Claude 要求看某個區域時，工具從完整解析度的原圖裁出那塊區域，放大後回傳，小東西就看得清楚了。這份 notebook 會把這個工具做出來，在公開的圖表閱讀 benchmark 上，準確率成長超過一倍（結果在下面）。為什麼放大有用，要從 Claude 實際怎麼看圖講起，後面會說。

**讀完這份 cookbook，你會學到：**

- 用官方文件的 `resized_size()` 參考實作預先縮圖，讓 Claude 給的像素座標跟你手上的圖 1:1 對應
- 定義一個自成一體的 zoom tool，輸入絕對像素座標，輸出填滿預算的放大裁圖，可以直接搬進任何專案
- 跑 tool 外面那層 agentic loop，包含 stop reason 的處理，避免思考很久的長回合被悄悄截斷

這份 notebook 用圖表當範例，不過只要「細節相對整張圖很小」都適用：密集的文件、UI 截圖、電路圖、掃描表單、標籤照片。

![The zoom-tool loop: one user message carries the question and the chart image to Claude; Claude sees the image in 28-by-28-pixel patches, and when a detail is too small it calls zoom(x1, y1, x2, y2) in pixel coordinates; your handle_zoom() implementation crops that region from the full-resolution original and returns it magnified; the exchange repeats until Claude answers — here, that the Widget-E line is higher.](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/crop_tool/architecture_diagram.png)

## 先看結果

### 範例問題

![A dense six-series line chart of monthly production by product line, with a tiny peak annotation and several close crossings.](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/crop_tool/example_problem.png)

**在第 48 個月，Widget-A 和 Widget-E 哪個產品線的值比較高？** 那個月兩條線只差約 26 個單位，在這張圖裡大約 8 個像素，而且就在一個真正的交叉點旁邊。（這是 notebook 自己產生的示範問題，風格模仿下面 benchmark 用的那種密集真實圖表；benchmark 本身的題目是保留的評測集，不會在這裡公開。）

### 有 tool 跟沒 tool 的差別

直接問的話，模型會回答 **Widget-A**，語氣很有自信，還常常把附近的交叉講得好像已經發生過，結果 40 次紀錄裡錯了 36 次（90%）。給它 zoom tool 後，它會對交叉處反覆 zoom，每次裁得更緊，從放大圖讀出順序，回答 **Widget-E**，用這份 notebook 做出來的程式碼，40 次全對（100%）。（這些是對同一個示範問題的重複執行；下面的 benchmark 數字是另外一次單次測量。）你之後會親自跑一遍這個過程。

### 數字

同樣的做法，用 [Chartography](https://huggingface.co/datasets/surgeai/chartography) 測過。這是 Surge AI 的公開 benchmark，有 100 題針對密集真實圖表的閱讀問題。每個模型每題各問兩次（有 tool 和沒 tool），自由格式的答案依 dataset card 的做法由模型評審打分。下圖每根長條是一個模型在一種條件下、100 題的準確率，箭頭表示加上 tool 後的變化；每題平均成本在圖的註解裡。tool 換來準確率的代價是更多 token：每次 zoom 呼叫都要重送整段對話加一張放大的裁圖。

![Grouped bar chart of accuracy on Chartography: for each model, a translucent bar for the no-tool condition and a solid bar for the zoom-tool condition, with an arrow marking the improvement. claude-fable-5 rises from 29% to 73% (+44 points); claude-sonnet-5 from 13% to 44% (+31 points). The figure note lists mean cost per question: claude-fable-5 $0.08 without the tool and $0.95 with it; claude-sonnet-5 $0.02 and $0.64.](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/crop_tool/results_accuracy.png)

這些數字來自對公開 Claude API 跑 benchmark，用的就是圖上標的模型：每個模型每種條件取 100 題的準確率（2026-07-18），成本取 30 題 usage 樣本的平均（2026-07-19），照公開 API 價格計算（Sonnet 5 用推出期優惠價），不含評審的費用。zoom 組有開 prompt caching，沒 tool 組是單次不快取的呼叫，因為一次性請求用不到快取；loop 最後的收尾呼叫會 miss cache，所以最佳化過的 client 會再便宜一點。

> **Note:** Chartography 是保留的評測集，不要拿去訓練（[dataset card](https://huggingface.co/datasets/surgeai/chartography) 附了 canary string 就是為了這個）。Prompt、標準答案和 metadata 版權屬 Surge AI，CC BY 4.0。網路來源的圖表圖片仍屬原權利人，這份 cookbook 沒有轉散布資料集的任何內容。

## 前置條件

**需要的知識：**
- Python 基礎
- 對 Messages API 的 [tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) 有基本認識

**需要的工具：**
- Python 3.11 以上
- Anthropic API key（[在這裡申請](https://console.anthropic.com)）

## 環境設定

```python
%pip install -q anthropic pillow matplotlib
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

```python
import base64
from collections.abc import Iterable, Mapping
from io import BytesIO
from typing import Any, cast

from anthropic import Anthropic
from IPython.display import Image, display
from PIL import Image as PILImage

client = Anthropic()
MODEL = "claude-fable-5"
```

## 建立示範圖表

我們畫一張 zoom tool 最適合處理的圖：六條線、密集的格線，答案用刻意縮小的字印在圖上。自己產生圖表的好處是 ground truth 很明確，而且那個標註在完整視圖下真的小到讀不出來。

```python
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(12)
months = np.arange(60)
fig, ax = plt.subplots(figsize=(16, 9), dpi=100)
series = {}
for name, base, amp in [
    ("Widget-A", 5200, 420),
    ("Widget-B", 4800, 380),
    ("Widget-C", 5600, 450),
    ("Widget-D", 4400, 300),
    ("Widget-E", 5014, 340),
    ("Widget-F", 4600, 410),
]:
    y = base + amp * np.sin(months / 7 + base % 7) + rng.normal(0, 90, months.size).cumsum() / 4
    series[name] = y
    ax.plot(months, y, lw=1.0, label=name)

# The detail our question hinges on: a tiny annotation at Widget-C's peak
peak_x = int(np.argmax(series["Widget-C"]))
peak_y = float(series["Widget-C"][peak_x])
ax.scatter([peak_x], [peak_y], s=12, color="crimson", zorder=3)
ax.annotate(
    f"peak: {peak_y:,.0f} units",
    (peak_x, peak_y),
    textcoords="offset points",
    xytext=(5, 4),
    fontsize=5,
)

ax.set_title("Monthly production by product line")
ax.set_xlabel("Month")
ax.set_ylabel("Units")
ax.grid(True, lw=0.3, alpha=0.6)
ax.legend(fontsize=7, ncols=3)

# Hand the figure to the rest of the notebook as a PIL image
buffer = BytesIO()
fig.savefig(buffer, format="PNG", bbox_inches="tight")
plt.close(fig)
buffer.seek(0)
chart_image = PILImage.open(buffer)

question = "What exact value is annotated at the peak of the Widget-C line?"
answer = f"peak: {peak_y:,.0f} units"

print(f"Chart size: {chart_image.size}")
print(f"Question: {question}")
_buf = BytesIO()
chart_image.save(_buf, format="PNG")
display(Image(data=_buf.getvalue(), width=560))
```

??? note "輸出"

    ```text
    Chart size: (1325, 777)
    Question: What exact value is annotated at the peak of the Widget-C line?
    ```

## Claude 怎麼看圖，以及為什麼用像素座標

有兩件關於 [Claude 如何處理圖片](https://platform.claude.com/docs/en/build-with-claude/vision#evaluate-image-size)的事，決定了這個 tool 的設計：

1. **圖片用 visual token 計量。** 每個 28×28 像素的 patch 算一個 visual token，每個模型有圖片預算：標準解析度等級下，任一邊不能超過 1568 像素，一張圖最多 1568 個 visual token；高解析度等級的模型（例如 `claude-fable-5` 和 `claude-sonnet-5`）允許 2576 像素和 4784 個 visual token。超過限制的圖會在 Claude 看到之前自動縮小，小細節也跟著縮沒了。

2. **Claude 用絕對像素座標效果最好。** [vision coordinates guide](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates) 建議明確要求像素座標，並且不建議用正規化（0 到 1）座標。有個陷阱：Claude 用的座標是它*實際看到的那張圖*裡的像素位置，也就是自動縮小之後的。解法是上傳前自己先 resize，讓你手上的圖就是 Claude 看到的圖，每個座標都 1:1 對應。

座標指南提供了一個參考實作 `resized_size()`，能算出 Claude 會把圖縮成多大。我們把它複製下來，用兩次：

- **上傳前：** 先縮好要給 Claude 看的圖，這樣它送來的 zoom 座標才能 1:1 對到我們手上的圖。
- **zoom 時：** 把裁出的區域*放大*到預算內最大的尺寸，讓裡面每個元素拿到盡量多的 patch。

## 定義 zoom tool

每次 zoom 呼叫的流程：

1. Claude 用像素座標 `(x1, y1)`–`(x2, y2)` 指定區域，原點 `(0, 0)` 在左上角（x 往右增加，y 往下增加）。
2. 我們把座標對應到完整解析度的原圖（可能比 Claude 看到的那份大），並從中裁出該區域。
3. 把裁圖放大到圖片預算允許的最大尺寸，然後回傳。

從原圖裁而不是從縮小後的副本裁，zoom 就能用上來源圖片的每一個像素。

還有個實務細節：放大後的裁圖用 JPEG 回傳，不用 PNG。tool result 會一直累積在對話裡，幾張填滿預算的詳細圖表 PNG 就可能超過 API 的 [32 MB 請求大小限制](https://platform.claude.com/docs/en/api/overview#request-size-limits)。（對話裡累積很多大圖時，用 [Files API](https://platform.claude.com/docs/en/build-with-claude/files) 可以讓請求大小不受歷史長度影響。）

下一個 cell 是自成一體的，schema 和實作都在裡面，不需要其他 cell，可以直接複製到你自己的專案。

```python
# The zoom tool: schema + implementation. This cell is self-contained (it needs
# only Pillow, plus the anthropic SDK for its type annotations), so you can copy it
# straight into your own project.
import base64
import math
from io import BytesIO

from anthropic.types import ImageBlockParam, TextBlockParam, ToolParam
from PIL import Image as PILImage

# Image limits for the model you're using — see "Resolution and token cost":
# https://platform.claude.com/docs/en/build-with-claude/vision#evaluate-image-size
MAX_EDGE = 2576  # high-resolution tier; use 1568 for standard-tier models
MAX_TOKENS = 4784  # high-resolution tier; use 1568 for standard-tier models


def count_image_tokens(width: int, height: int) -> int:
    """Visual tokens consumed by an image: one token per 28x28 pixel patch."""
    return math.ceil(width / 28) * math.ceil(height / 28)


# Reference implementation from the vision coordinates guide ("Resize your image
# before uploading"):
# https://platform.claude.com/docs/en/build-with-claude/vision-coordinates#resize-your-image-before-uploading
def resized_size(
    width: int,
    height: int,
    max_edge: int = MAX_EDGE,
    max_tokens: int = MAX_TOKENS,
) -> tuple[int, int]:
    """The size Claude resizes an image to before padding.

    Images that already fit within the limits are returned unchanged.
    """

    def fits(w: int, h: int) -> bool:
        return (
            math.ceil(w / 28) * 28 <= max_edge
            and math.ceil(h / 28) * 28 <= max_edge
            and count_image_tokens(w, h) <= max_tokens
        )

    if fits(width, height):
        return (width, height)
    if height > width:
        resized_h, resized_w = resized_size(height, width, max_edge, max_tokens)
        return (resized_w, resized_h)

    # Binary search along the long edge for the largest aspect-preserving
    # size that fits.
    aspect_ratio = width / height
    lo, hi = 1, width  # lo always fits; hi never fits
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if fits(mid, max(round(mid / aspect_ratio), 1)):
            lo = mid
        else:
            hi = mid
    return (lo, max(round(lo / aspect_ratio), 1))


def prepare_image(image: PILImage.Image) -> PILImage.Image:
    """Resize an image to exactly the size Claude will see.

    The pixel coordinates Claude uses refer to the image it saw — after any
    automatic server-side downscaling. Doing the same resize client-side first
    means Claude's coordinates map 1:1 onto the image we hold.
    """
    target = resized_size(image.width, image.height)
    if (image.width, image.height) == target:
        return image
    return image.resize(target, PILImage.Resampling.LANCZOS)


def zoom_size(width: int, height: int) -> tuple[int, int]:
    """The largest aspect-preserving size within the image limits.

    This is the upscale target for a zoomed crop: the larger the crop is drawn,
    the more 28x28 patches each element inside it covers. resized_size() finds
    the largest size that fits whenever its input is over the limits, so we
    scale the crop's size far past the limits and let the search come back down.
    """
    return resized_size(width * 10_000, height * 10_000)


def pil_to_base64(image: PILImage.Image, format: str = "PNG") -> str:
    """Convert PIL Image to base64 string.

    Transparency is composited onto white: a bare .convert("RGB") would
    flatten transparent backgrounds (common in web charts) to black.
    """
    if image.mode != "RGB":
        rgba = image.convert("RGBA")
        background = PILImage.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    buffer = BytesIO()
    # subsampling=0 keeps full chroma resolution: 4:2:0 subsampling halves color
    # detail, which can smear 1-2px colored chart lines in a magnified crop.
    image.save(
        buffer, format=format, **({"quality": 92, "subsampling": 0} if format == "JPEG" else {})
    )
    return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")


# Tool definition for the Anthropic API
ZOOM_TOOL: ToolParam = {
    "name": "zoom",
    "description": (
        "Zoom into a rectangular region of an image. Returns the region cropped "
        "from the full-resolution original and magnified, so that small details "
        "become legible."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "x1": {
                "type": "integer",
                "description": "Left edge of the region, in pixels (the origin is the image's top-left corner)",
            },
            "y1": {
                "type": "integer",
                "description": "Top edge of the region, in pixels",
            },
            "x2": {
                "type": "integer",
                "description": "Right edge of the region, in pixels (must be greater than x1)",
            },
            "y2": {
                "type": "integer",
                "description": "Bottom edge of the region, in pixels (must be greater than y1)",
            },
            "image_index": {
                "type": "integer",
                "description": "Which image to zoom into, counting images in the conversation from 0. Omit when there is only one image.",
            },
        },
        "required": ["x1", "y1", "x2", "y2"],
    },
}


def handle_zoom(
    original: PILImage.Image, view_size: tuple[int, int], x1: int, y1: int, x2: int, y2: int
) -> list[TextBlockParam | ImageBlockParam]:
    """Execute a zoom call and return the tool result content for Claude.

    original is the full-resolution image; view_size is the size of the copy
    Claude saw (the output of prepare_image()), which is the coordinate space
    of x1/y1/x2/y2.
    """
    view_w, view_h = view_size
    x1, x2 = max(0, min(x1, view_w)), max(0, min(x2, view_w))
    y1, y2 = max(0, min(y1, view_h)), max(0, min(y2, view_h))
    if x1 >= x2 or y1 >= y2:
        return [
            {
                "type": "text",
                "text": "Error: invalid region (need x1 < x2 and y1 < y2, within the image)",
            }
        ]

    # Map view coordinates onto the original. The resize preserved the aspect
    # ratio, so one scale factor covers both axes.
    scale = original.width / view_w
    box = (round(x1 * scale), round(y1 * scale), round(x2 * scale), round(y2 * scale))
    cropped = original.crop(box)
    zoomed = cropped.resize(zoom_size(cropped.width, cropped.height), PILImage.Resampling.LANCZOS)

    # Zoomed crops go back as JPEG: every tool result stays in the conversation,
    # and a few full-budget PNGs of detailed charts can exceed the API's 32 MB
    # request size limit. JPEG keeps each zoom to a fraction of that.
    return [
        {
            "type": "text",
            "text": (
                f"Zoomed into ({x1},{y1})-({x2},{y2}) of the image you see at "
                f"{view_w}x{view_h}px: a {cropped.width}x{cropped.height}px region "
                f"of the original, returned magnified to {zoomed.width}x{zoomed.height}px."
            ),
        },
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": pil_to_base64(zoomed, "JPEG"),
            },
        },
    ]
```

先手動測一下 zoom tool 再交給 Claude，這裡 zoom 到圖表上半部、有峰值標註的地方：

```python
def show_tool_result(blocks: Iterable[Mapping[str, Any]], show_text: bool = True) -> None:
    """Print the text and display the images among a tool result's content blocks.

    A notebook convenience for inspecting what a zoom call returns. It reads the
    blocks loosely (they are plain dicts on their way to the API), so it is not
    part of the tool itself.
    """
    for block in blocks:
        if block.get("type") == "text" and show_text:
            print(block["text"])
        elif block.get("type") == "image":
            display(Image(data=base64.b64decode(block["source"]["data"]), width=400))


view = prepare_image(chart_image)
print(f"Original size: {chart_image.size}, size Claude sees: {view.size}")

# Zoom into the upper-middle band of the chart
result = handle_zoom(chart_image, view.size, x1=0, y1=0, x2=view.width, y2=int(view.height * 0.3))
show_tool_result(result)
```

??? note "輸出"

    ```text
    Original size: (1325, 777), size Claude sees: (1325, 777)
    Zoomed into (0,0)-(1325,233) of the image you see at 1325x777px: a 1325x233px region of the original, returned magnified to 2576x453px.
    ```

## Agentic Loop

現在把一切串起來：把圖和 zoom tool 一起送給 Claude，讓它呼叫 tool 直到有答案。SDK 的 `tool_runner` 負責驅動整個流程，模型要求時就呼叫我們的 `zoom` 函式，把放大的裁圖餵回去，模型回答時停止（或在 `max_iterations` 之後停，防止無限迴圈）。

有三個細節要注意：

- 我們同時保留**兩份**圖：完整解析度的原圖（給 tool 裁切用），和 Claude 實際看到的預先縮好的副本（它的尺寸定義了座標空間）。`zoom` 函式同時 closure 這兩份。
- prompt 裡**寫明每張圖的尺寸和座標慣例**，Claude 才知道自己在哪個像素空間裡工作。
- `@beta_tool` 會從函式簽名和 docstring 建出 tool 的 schema。要加第二個 tool，就再 decorate 一個函式、加進 `tools` 清單，runner 會依名稱分派。

還有個小麻煩：API 可能在伺服器端暫停很長的回合（`stop_reason == "pause_turn"`），而 runner 目前不會自己恢復，所以下面包在外面的小迴圈會在這時重放 transcript 並繼續。

```python
from anthropic import beta_tool
from anthropic.types.beta import BetaContentBlockParam, BetaMessageParam


def ask_with_zoom_tool(images, question: str, verbose: bool = True, model: str = MODEL):
    """Ask Claude a question about one or more images, with the zoom tool available."""
    if not isinstance(images, list):
        images = [images]
    originals = images
    views = [prepare_image(image) for image in originals]

    @beta_tool
    def zoom(x1: int, y1: int, x2: int, y2: int, image_index: int = 0) -> list:
        """Zoom into a rectangular region of an image to see it magnified.

        Use this whenever text, numbers, lines, or details are too small to read
        confidently in the full view. The region is cropped from the image's
        full-resolution original and scaled up to fill the image budget, so
        small elements become much easier to read. Coordinates are absolute
        pixels in the image as you see it, origin at the top-left corner.
        Zoom again on the result for even finer detail.

        Args:
            x1: Left edge of the region in pixels (origin is the image's top-left corner).
            y1: Top edge of the region in pixels.
            x2: Right edge of the region in pixels (must be greater than x1).
            y2: Bottom edge of the region in pixels (must be greater than y1).
            image_index: Which image to zoom into (0 for the first image, 1 for the second).
        """
        if not 0 <= image_index < len(originals):
            return [{"type": "text", "text": f"Error: image_index {image_index} is out of range"}]
        return handle_zoom(originals[image_index], views[image_index].size, x1, y1, x2, y2)

    content: list[BetaContentBlockParam] = []
    for i, view in enumerate(views):
        content.append({"type": "text", "text": f"Image {i} ({view.width}x{view.height} pixels):"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": pil_to_base64(view),
                },
            }
        )
    content.append(
        {
            "type": "text",
            "text": (
                f"Answer the following question about the image{'s' if len(views) > 1 else ''} "
                f"above. Coordinates are absolute pixels with the origin at the top-left corner. "
                f"Use the zoom tool to examine any detail that is too small to read confidently."
                f"\n\nThe question is: {question}"
            ),
        }
    )
    messages: list[BetaMessageParam] = [{"role": "user", "content": content}]

    runner = final = None  # bound before the loop for the type checker; the body always runs
    for _reentry in range(5):  # pause_turn re-entries are bounded, like the tool loop itself
        runner = client.beta.messages.tool_runner(
            model=model,
            max_tokens=8192,
            tools=[zoom],
            messages=messages,
            max_iterations=20,
        )
        for message in runner:
            called = [block for block in message.content if block.type == "tool_use"]
            if verbose:
                for block in called:
                    print(f"[Tool] {block.name}({block.input})")
                if called:
                    # The runner caches this response and reuses it internally, so
                    # peeking at it here does not re-run the tool. It is the
                    # tool_result message the runner sends next; its blocks are the
                    # plain dicts handle_zoom() built, so read them as such.
                    peek = cast(Any, runner.generate_tool_call_response())
                    for tool_result in peek["content"] if peek else []:
                        # An errored tool call carries a plain string instead
                        # of blocks; only successful zooms have images to show.
                        if isinstance(tool_result["content"], list):
                            show_tool_result(tool_result["content"], show_text=False)
        final = runner.until_done()
        if final.stop_reason != "pause_turn":
            break
        # The server paused a long turn; the runner doesn't resume these itself,
        # so replay the transcript so far and continue where it left off. The
        # counter records how often that happened.
        globals().setdefault("PAUSE_TURN_RESUMES", []).append(_reentry + 1)
        snapshot = {}
        runner.set_messages_params(lambda params, _out=snapshot: (_out.update(params), params)[1])
        messages = [*snapshot["messages"], {"role": "assistant", "content": final.content}]
    assert runner is not None and final is not None  # the loop ran at least once

    answer = "\n".join(block.text for block in final.content if block.type == "text")
    if not answer.strip():
        # The run ended without a text answer - usually the iteration budget ran
        # out mid-zoom. Give the model one plain turn to answer from what it has
        # (the same wrap-up the hand-written loop in the appendix uses). When the
        # budget ran out, the runner has already appended the final assistant
        # message and its tool results to the transcript, so we only append the
        # wrap-up request itself (appending the final message again would
        # duplicate its tool calls and the API would reject the transcript).
        snapshot = {}
        runner.set_messages_params(lambda params, _out=snapshot: (_out.update(params), params)[1])
        transcript = list(snapshot["messages"])
        if not (transcript and transcript[-1]["role"] == "user"):
            transcript.append({"role": "assistant", "content": final.content})
        transcript.append(
            {
                "role": "user",
                "content": (
                    "You have used your zoom budget. Answer the original question now, "
                    "based on everything you have seen."
                ),
            }
        )
        wrap_up = client.beta.messages.create(model=model, max_tokens=8192, messages=transcript)
        final = wrap_up
        answer = "\n".join(block.text for block in final.content if block.type == "text")
    if verbose:
        for block in final.content:
            if block.type == "text":
                print(f"[Assistant] {block.text}")
    # Join every text block: long answers can arrive in several, and the
    # answer is not always in the last one.
    return answer
```

## 示範：圖表分析

我們請 Claude 分析這張圖表，看它怎麼用 zoom tool 檢視特定區域。

```python
print(f"Question: {question}\n")

print("Claude's analysis:\n")
final_answer = ask_with_zoom_tool(chart_image, question)

print(f"\nGround truth (we drew it): {answer}")
```

??? note "輸出"

    ```text
    Question: What exact value is annotated at the peak of the Widget-C line?

    Claude's analysis:
    ```

    ```text
    [Tool] zoom({'x1': 260, 'y1': 35, 'x2': 450, 'y2': 80})
    ```

    ```text
    [Assistant] The annotation at the peak of the Widget-C line reads **"peak: 6,053 units"** — so the exact annotated value is **6,053 units**.

    Ground truth (we drew it): peak: 6,053 units
    ```

## 當完整視圖騙了你

讀小字只是失敗模式的一半，另一半是*幾何*。同一張圖的第 48 個月，Widget-A 和 Widget-E 兩條線差約 26 個單位，在這個渲染下大約 8 個像素，不到一個 28×28 patch，附近還有一個真正的交叉讓人更混淆。這種間距的排序問題，在 patch 的粒度下根本不可能解出來。

不用 tool 直接問，Claude 會很有自信地選錯線，40 次紀錄裡錯 36 次。有 zoom tool 時，它會放大交叉區域（反覆 zoom，每次裁得更緊），然後答對，40 次全對。

> **Note:** 這個接近平手的對比是針對 `claude-fable-5` 調的，它是上面 benchmark 中最強的圖表閱讀者。小一點的模型即使有 tool 也更常答錯，在我們的實驗裡，`claude-sonnet-5` 有 tool 時，這個交叉處 10 次只答對 1 次。zoom 能把像素找回來，但要判斷一個幾乎貼在一起的交叉，還是得靠模型最好的視覺推理。

```python
question_2 = "At month 48, which product line has the higher value: Widget-A or Widget-E?"

# Without the tool: one plain Messages call, same image
view = prepare_image(chart_image)
response = client.messages.create(
    model=MODEL,
    max_tokens=8192,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"Answer the following question about the image below.\n\nThe question is: {question_2}",
                },
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": pil_to_base64(view),
                    },
                },
            ],
        }
    ],
)
print("WITHOUT the tool:")
print("".join(block.text for block in response.content if block.type == "text"))

print("\nWITH the zoom tool:")
ask_with_zoom_tool(chart_image, question_2)

higher = "Widget-E" if series["Widget-E"][48] > series["Widget-A"][48] else "Widget-A"
gap = abs(series["Widget-E"][48] - series["Widget-A"][48])
print(f"\nGround truth (from the data): {higher} is higher at month 48, by about {gap:.0f} units.")
```

??? note "輸出"

    ```text
    WITHOUT the tool:
    **Widget-A** has the higher value at month 48. The blue Widget-A line is rising steeply at that point (around ~5,350 units), having just crossed above the purple Widget-E line, which is declining (around ~5,300 units). The two lines cross at roughly month 47, so by month 48 Widget-A is slightly above Widget-E.

    WITH the zoom tool:
    ```

    ```text
    [Tool] zoom({'x1': 980, 'y1': 230, 'x2': 1120, 'y2': 360})
    ```

    ```text
    [Tool] zoom({'x1': 1025, 'y1': 270, 'x2': 1075, 'y2': 320})
    ```

    ```text
    [Assistant] **Widget-E** has the higher value at month 48.

    Zooming in on that region shows the purple Widget-E line (around ~5,310 units) sits just above the blue Widget-A line (around ~5,290 units) at month 48. The two lines cross shortly after — at roughly month 48–49 — after which Widget-A overtakes Widget-E, but at exactly month 48, Widget-E is still slightly higher.

    Ground truth (from the data): Widget-E is higher at month 48, by about 26 units.
    ```
下面是這個過程的動態版：完整視圖、模型的 zoom 呼叫，以及兩條線終於分開的放大裁圖：

![Animated walkthrough of the zoom exchange: the full chart appears with the question; without the tool, the model answers Widget-A, marked wrong; the view then zooms in twice, each crop tighter than the last, until the magnified crossing shows the Widget-E line still above Widget-A at month 48; with the tool, the model answers Widget-E, marked correct.](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/crop_tool/zoom_demo.gif)

## 多張圖片的對話

對話裡有多張圖時，tool 要知道該 zoom 哪一張。上面的 schema 已經有個選用參數 `image_index`（0 是第一張，1 是第二張，以此類推），`ask_with_zoom_tool()` 也接受一個 list：

```python
ask_with_zoom_tool([chart_image, other_chart], "Which of the two charts has more categories?")
```

每張圖在 prompt 裡都標了索引和像素尺寸，Claude 就能指名要看哪張，並用對應的座標空間。

## 總結

zoom tool 的做法：

1. 用 `resized_size()` **預先縮好**要送的圖，讓 Claude 的像素座標 1:1 對到你手上的圖，並在 prompt 裡寫明尺寸和左上角原點。
2. **定義一個 zoom tool**，接受絕對像素座標。
3. **從完整解析度的原圖裁切**，不要從縮小的副本裁，並把裁圖**放大**到模型的圖片預算，小元素才有足夠的 visual token 被讀出來。
4. **讓 Claude 自己決定**什麼時候、zoom 哪裡。

這樣有效是因為 Claude 先看整張圖，找出需要細看的區域，再把它們放大重讀。代價是每次 zoom 都多一次模型往返，放大的圖也要花 visual token，所以是用更高的延遲和 token 用量，換細節型問題的準確率。（另外，如果你在有 code execution 的 agent 框架裡跑 Claude，可能根本不用自己做這些：能跑程式的 agent 通常會自己寫一段裁切放大的腳本，一樣的模式，自給自足。）

## 附錄：手寫 Loop

`tool_runner` 只是方便用，它做的每件事都能用單純的 `client.messages.create` 呼叫寫出來，看過一次運作機制很值得。這裡也是你自己控制所有邊角情況的地方：tool call 一出現就執行（即使回合被 token 上限截斷）、恢復伺服器暫停的回合、當被 token 上限截斷的回合既沒有 tool call 也沒有文字時，再給模型一個純文字回合讓它回答、以及明確地依名稱分派 tool（未知名稱回傳錯誤結果，讓幻想出 tool 的模型能自己恢復）。

下面這個版本在一般情況下等同 runner 版，有兩個刻意的差異：runner 把迭代次數限制在 20 次、pause-turn 重新進入限制在 5 次，而這個版本會一直跑到模型停止，正式環境請自己加上限。

```python
from anthropic.types import (
    ContentBlockParam,
    ImageBlockParam,
    MessageParam,
    TextBlockParam,
    ToolResultBlockParam,
)


def ask_with_zoom_tool_manual(
    images, question: str, verbose: bool = True, model: str = MODEL
) -> str:
    """Ask Claude a question about one or more images, with the zoom tool available.

    Accepts a single PIL image or a list of them. Returns Claude's final text.
    """
    originals = images if isinstance(images, list) else [images]
    views = [prepare_image(image) for image in originals]

    content: list[ContentBlockParam] = [
        {
            "type": "text",
            "text": f"Answer the following question about the image below.\n\nThe question is: {question}",
        }
    ]
    for i, view in enumerate(views):
        label = f"Image {i}" if len(views) > 1 else "The image"
        content.append({"type": "text", "text": f"\n{label} is {view.width}x{view.height} pixels:"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": pil_to_base64(view),
                },
            }
        )
    content.append(
        {
            "type": "text",
            "text": (
                "\nPixel coordinates start at (0, 0) in the top-left corner, with x increasing "
                "to the right and y increasing downward. Use the zoom tool to examine small "
                "details like legends, axis labels, and closely spaced values."
            ),
        }
    )

    messages: list[MessageParam] = [{"role": "user", "content": content}]
    nudged = False

    while True:
        response = client.messages.create(
            model=model, max_tokens=8192, tools=[ZOOM_TOOL], messages=messages
        )

        if verbose:
            for block in response.content:
                if block.type == "text":
                    print(f"[Assistant] {block.text}")
                elif block.type == "tool_use":
                    print(f"[Tool] zoom({block.input})")

        if response.stop_reason == "pause_turn":
            # The model paused a long turn; hand it back as-is and let it continue.
            messages.append({"role": "assistant", "content": response.content})
            continue

        tool_calls = [block for block in response.content if block.type == "tool_use"]

        if tool_calls:
            # Execute the tool calls and continue — keyed on the presence of the
            # calls rather than on stop_reason, so a turn that emitted a complete
            # call and then hit the token cap still gets its tool result.
            messages.append({"role": "assistant", "content": response.content})

            tool_results: list[ToolResultBlockParam] = []
            for block in tool_calls:
                if block.name != "zoom":
                    # Dispatch by name: when you add more tools, route each name
                    # to its handler here. Unknown names get an error result.
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Unknown tool: {block.name}",
                            "is_error": True,
                        }
                    )
                    continue
                # block.input is typed loosely; the tool call's arguments arrive as a dict.
                inputs = dict(cast(Mapping[str, Any], block.input))
                image_index = inputs.pop("image_index", 0)
                if not 0 <= image_index < len(originals):
                    result: list[TextBlockParam | ImageBlockParam] = [
                        {
                            "type": "text",
                            "text": f"Error: image_index {image_index} is out of range",
                        }
                    ]
                else:
                    try:
                        result = handle_zoom(
                            originals[image_index], views[image_index].size, **inputs
                        )
                    except TypeError as e:
                        # A malformed call (e.g. a missing coordinate, possible when a
                        # turn is cut off mid-call) gets an error result back, so the
                        # model can correct itself instead of crashing the loop.
                        result = [{"type": "text", "text": f"Error: invalid zoom arguments ({e})"}]
                if verbose:
                    show_tool_result(result, show_text=False)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )

            messages.append({"role": "user", "content": tool_results})
            continue

        if (
            response.stop_reason == "max_tokens"
            and not any(block.type == "text" for block in response.content)
            and response.content
            and not nudged
        ):
            # The turn hit the token cap mid-thought: no answer text, no tool call.
            # Hand the partial turn back and ask for a concise wrap-up (once).
            nudged = True
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": "You ran out of output tokens. State your final answer concisely now.",
                }
            )
            continue

        # Join every text block of the final turn: models that think can emit
        # several, and the answer is not always in the last one.
        return "\n".join(block.text for block in response.content if block.type == "text")
```

## 重點整理

- 圖片在 Claude 眼中是固定大小的 patch 和固定預算，太小的細節在縮放過程中就消失了，prompt 救不回來。
- 預先用 `resized_size()` 縮圖，讓你手上的圖就是 Claude 看到的圖，座標才能 1:1 對應。
- zoom tool 要從完整解析度的原圖裁切，再放大到預算上限，這樣才用得到所有原始像素。
- 準確率提升是用 token 和延遲換的，每次 zoom 都是一次額外往返加一張圖。
- 自己寫 loop 時要處理 `pause_turn` 和被 token 上限截斷的回合，不然長回合會悄悄失敗。

## 練習

1. 把示範問題改成問另一個月份或另兩條線，跑有 tool 跟沒 tool 的版本，看答案有沒有變。
2. 在 prompt 或 tool 呼叫的地方，把座標改成 0 到 1 的正規化座標，觀察 Claude 回傳的區域跟你預期差多少。
3. 把 zoom 回傳的格式從 JPEG 改成 PNG，連續 zoom 幾次，看請求大小如何成長，再想想怎麼用 Files API 解決。
