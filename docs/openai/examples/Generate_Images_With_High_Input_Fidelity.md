---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Generate_Images_With_High_Input_Fidelity.ipynb
---

# 用 high input fidelity 生成圖片

> 原文：[examples/Generate_Images_With_High_Input_Fidelity.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Generate_Images_With_High_Input_Fidelity.ipynb)

用 Image API 的 high input fidelity 保留圖片細節。

## 這篇在做什麼
示範 Image API 和 Responses 圖片生成 tool 都有的 `input_fidelity` 參數。設成 `"high"` 之後，編輯圖片時臉、logo 這類細節會被保留得更好。範例涵蓋局部編輯、臉部保留、品牌一致性和商品修圖。

## 學完你會
- 在圖片編輯請求加上 `input_fidelity="high"`，只改局部而不動其他地方
- 合併多張圖（例如臉加配件）時，知道第一張圖的細節保留最完整
- 判斷哪些場景值得多花 input token 開 high fidelity

## 開跑前
需要 OpenAI API key，圖片生成會產生費用。

這份 cookbook 說明怎麼用 `input_fidelity` 參數，保留輸入圖片裡有辨識度的特徵。

設成 `input_fidelity="high"` 特別適合編輯有臉、logo，或任何需要高保真度輸出的圖片。

如果你還不熟用 OpenAI API 生成圖片，建議先看我們的[圖片生成入門 cookbook](https://cookbook.openai.com/examples/generate_images_with_gpt_image)。


## 設定

```python
%pip install pillow openai -U  # (skip if already installed)
```

```python
import base64, os
from io import BytesIO
from PIL import Image
from IPython.display import display, Image as IPImage
from openai import OpenAI

client = OpenAI()
# Set your API key if not set globally
#client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

```python
folder_path = "imgs"
os.makedirs(folder_path, exist_ok=True)
```

```python
def resize_img(image, target_w):
    w, h = image.size
    target_h = int(round(h * (target_w / float(w))))
    resized_image = image.resize((target_w, target_h), Image.LANCZOS)
    return resized_image

def edit_img(input_img, prompt):
    result = client.images.edit(
        model="gpt-image-1",
        image=input_img,
        prompt=prompt,
        input_fidelity="high",
        quality="high",
        output_format="jpeg"
    )

    image_base64 = result.data[0].b64_json
    image_bytes = base64.b64decode(image_base64)
    image = Image.open(BytesIO(image_bytes))
    return image
```

## 精準編輯

high input fidelity 讓你對圖片做細微修改，不會動到不相關的區域，很適合受控的局部修改。

使用情境：
- **物品編輯：** 改單一元素（例如換杯子顏色），其他地方完全不動。
- **移除元素：** 乾淨移除單一元素，不影響其餘畫面。
- **新增元素：** 把新物件自然加進場景。

```python
edit_input_path = "imgs/desk.png"
edit_input_img = open(edit_input_path, "rb")
display(IPImage(edit_input_path))
```

### 物品編輯

```python
edit_prompt = "Make the mug olive green"
edit_result = edit_img(edit_input_img, edit_prompt)
```

```python
# Display result
edit_resized_result = resize_img(edit_result, 300)
display(edit_resized_result)
```

### 移除物品

```python
remove_prompt = "Remove the mug from the desk"
remove_result = edit_img(edit_input_img, remove_prompt)
```

```python
# Display result
remove_resized_result = resize_img(remove_result, 300)
display(remove_resized_result)
```

### 新增物品

```python
add_prompt = "Add a post-it note saying 'Be right back!' to the monitor"
add_result = edit_img(edit_input_img, add_prompt)
```

```python
# Display result
add_resized_result = resize_img(add_result, 300)
display(add_resized_result)
```

## 臉部保留


用 high input fidelity 時，臉的保留程度比標準模式好很多。需要人物在編輯後仍然認得出來時就用它。

使用情境：
- **圖片編輯：** 編輯照片但保留臉部特徵。
- **個人化：** 做出在不同背景或風格下仍像本人的 avatar。
- **照片合成：** 把多張照片裡的臉合成一張圖。

**注意：** 目前所有輸入圖片都會高保真保留，但只有你提供的第一張會額外保留更豐富的紋理。要處理來自不同照片的多張臉時，建議先把需要的臉合成一張組合圖再送出請求（見下面的範例）。

```python
face_input_path = "imgs/woman_portrait.png"
face_input_img = open(face_input_path, "rb")
display(IPImage(face_input_path))
```

### 圖片編輯

```python
edit_face_prompt = "Add soft neon purple and lime green lighting and glowing backlighting."
edit_face_result = edit_img(face_input_img, edit_face_prompt)
```

```python
# Display result
edit_face_resized_result = resize_img(edit_face_result, 300)
display(edit_face_resized_result)
```

### Avatar

```python
avatar_prompt = "Generate an avatar of this person in digital art style, with vivid splash of colors."
avatar_result = edit_img(face_input_img, avatar_prompt)
```

```python
# Display result
avatar_resized_result = resize_img(avatar_result, 300)
display(avatar_resized_result)
```

### 合併多張有臉的照片

```python
second_woman_input_path = "imgs/woman_smiling.jpg"
second_woman_input_img = open(second_woman_input_path, "rb")
display(IPImage(second_woman_input_path))
```

```python
def combine_imgs(left_path, right_path, bg_color=(255, 255, 255)):
    
    left_img = Image.open(open(left_path, "rb"))
    right_img = Image.open(open(right_path, "rb"))
    
    # Ensure RGBA for safe pasting (handles transparency)
    left = left_img.convert("RGBA")
    right = right_img.convert("RGBA")

    # Resize right to match left height
    target_h = left.height
    scale = target_h / float(right.height)
    target_w = int(round(right.width * scale))
    right = right.resize((target_w, target_h), Image.LANCZOS)

    # New canvas
    total_w = left.width + right.width
    canvas = Image.new("RGBA", (total_w, target_h), bg_color + (255,))

    # Paste
    canvas.paste(left, (0, 0), left)
    canvas.paste(right, (left.width, 0), right)

    return canvas
```

```python
combined_img = combine_imgs(second_woman_input_path, face_input_path)
display(combined_img)
```

```python
import io

# utility function to convert to bytes
def pil_to_bytes(img, fmt="PNG"):
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf

combined_img_bytes = pil_to_bytes(combined_img)
```

```python
combined_prompt = "Put these two women in the same picture, holding shoulders, as if part of the same photo."
combined_result = edit_img(("combined.png", combined_img_bytes, "image/png"), combined_prompt)
```

```python
# Display result
combined_resized_result = resize_img(combined_result, 300)
display(combined_resized_result)
```

## 品牌一致性

有時候生成圖片必須維持品牌識別。high input fidelity 能讓 logo 和其他獨特設計元素忠於原始素材。

使用情境：
- **行銷素材：** 生成含品牌 logo 的 banner 或社群貼文，logo 不變形。
- **Mockup：** 把 logo 或其他品牌素材放進模板或生活場景，不會被意外改動。
- **商品攝影：** 為不同活動換商品背景，同時保持商品細節清晰。

```python
logo_input_path = "imgs/logo.png"
logo_input_img = open(logo_input_path, "rb")
display(IPImage(logo_input_path))
```

### 行銷素材

```python
marketing_prompt = "Generate a beautiful, modern hero banner featuring this logo in the center. It should look futuristic, with blue & violet hues."
marketing_result = edit_img(logo_input_img, marketing_prompt)
```

```python
# Display result
marketing_resized_result = resize_img(marketing_result, 300)
display(marketing_resized_result)
```

### Mockup

```python
mockup_prompt = "Generate a highly realistic picture of a hand holding a tilted iphone, with an app on the screen that showcases this logo in the center with a loading animation below"
mockup_result = edit_img(logo_input_img, mockup_prompt)
```

```python
# Display result
mockup_resized_result = resize_img(mockup_result, 300)
display(mockup_resized_result)
```

### 商品攝影

```python
bag_input_path = "imgs/bag.png"
bag_input_img = open(bag_input_path, "rb")
display(IPImage(bag_input_path))
```

```python
product_prompt = "Generate a beautiful ad with this bag in the center, on top of a dark background with a glowing halo emanating from the center, behind the bag."
product_result = edit_img(bag_input_img, product_prompt)
```

```python
# Display result
product_resized_result = resize_img(product_result, 300)
display(product_resized_result)
```

## 時尚與商品修圖


電商和時尚常需要改服裝或商品細節，又不能失去真實感。high input fidelity 讓布料紋理、花樣和 logo 保持一致。

使用情境：
- **服裝變化：** 改模特兒照片上衣服的顏色或款式。
- **加配件：** 在模特兒照片加上珠寶、帽子等配件，不改姿勢和臉。
- **商品擷取：** 讓同一件商品或服裝出現在新場景，細節完整保留。

```python
model_input_path = "imgs/model.png"
model_input_img = open(model_input_path, "rb")
display(IPImage(model_input_path))
```

### 服裝變化

```python
variation_prompt = "Edit this picture so that the model wears a blue tank top instead of the coat and sweater."
variation_result = edit_img(model_input_img, variation_prompt)
```

```python
# Display result
variation_resized_result = resize_img(variation_result, 300)
display(variation_resized_result)
```

### 加配件

這個範例會合併 2 張輸入圖。有臉的那張要放在第一個，因為第一張圖保留的細節比較多。

```python
input_imgs = [('model.png',
                 open('imgs/model.png', 'rb'),
                 'image/png'),
    ('bag.png', open('imgs/bag.png', 'rb'),'image/png'),
]
```

```python
accessory_prompt = "Add the crossbody bag to the outfit."
accessory_result = edit_img(input_imgs, accessory_prompt)
```

```python
# Display result
accessory_resized_result = resize_img(accessory_result, 300)
display(accessory_resized_result)
```

### 商品擷取

```python
extraction_prompt = "Generate a picture of this exact same jacket on a white background"
extraction_result = edit_img(model_input_img, extraction_prompt)
```

```python
# Display result
extraction_resized_result = resize_img(extraction_result, 300)
display(extraction_resized_result)
```

## 總結

這篇說明了怎麼開啟 high input fidelity，更好地保留輸入圖片裡重要的視覺細節。

可以拿上面的使用情境當靈感，用自己的圖試試這個參數，看在哪些情況差異最大。

要記得 high input fidelity 會比預設消耗更多圖片輸入 token。另外雖然所有輸入圖片都用 high input fidelity 處理，清單裡第一張圖保留最細的細節和最豐富的紋理，這對臉特別重要。

開心動手吧！

## 重點整理
- `input_fidelity="high"` 讓編輯時未被要求修改的區域維持原樣，特別是臉、logo、紋理。
- 它在 Image API 和 Responses 的圖片生成 tool 都能用。
- 多張輸入圖時，第一張的細節保留最好，要保留的臉應放第一個。
- high fidelity 會多用圖片輸入 token，要依場景取捨。

## 練習
1. 把任一個編輯範例的 `input_fidelity` 改回預設值，比較輸出和 high 版本差在哪。
2. 換成你自己的照片或 logo，改 prompt 做一次物品移除。
3. 做一次合併兩張圖的請求，對調圖片順序，觀察臉的保留程度有沒有變。
