---
translated: true
source: examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb
---

# 如何使用 DALL·E API

> 原文：[examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb)

## 這篇在做什麼

示範 DALL·E 影像 API 的三個 endpoint：用文字生成圖片、局部編輯圖片、產生圖片的變體。每個 endpoint 的參數都列出來，再搭配程式實際跑一遍。

## 學完你會

- 用 generations endpoint 依 prompt 生成圖片，並知道 dall-e-2 與 dall-e-3 的參數差異
- 用 variations endpoint 對既有圖片產生相似的變體
- 自己做出 mask，用 edits endpoint 重新生成圖片的指定區域

## 開跑前

- 需要 `OPENAI_API_KEY`，在終端機執行 \``export OPENAI_API_KEY="your API key"`\``
- 影像生成會產生 API 費用


這個 notebook 示範怎麼使用 OpenAI 的 DALL·E 影像 API endpoint。

API 有三個 endpoint：
- **Generations：**依輸入的文字描述產生一張或多張圖片
- **Edits：**編輯或延伸既有圖片
- **Variations：**產生輸入圖片的變體

## 設定

- 匯入需要的套件
- 匯入你的 OpenAI API key：在終端機執行 \``export OPENAI_API_KEY="your API key"`\`` 即可
- 設定存放圖片的資料夾

```python
# imports
from openai import OpenAI  # OpenAI Python library to make API calls
import requests  # used to download images
import os  # used to access filepaths
from PIL import Image  # used to print and edit images

# initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

```python
# set a directory to save DALL·E images to
image_dir_name = "images"
image_dir = os.path.join(os.curdir, image_dir_name)

# create the directory if it doesn't yet exist
if not os.path.isdir(image_dir):
    os.mkdir(image_dir)

# print the directory to save to
print(f"{image_dir=}")
```

??? note "輸出"

    ```text
    image_dir='./images'
    ```

## Generations

generation endpoint 會根據文字 prompt 建立圖片。[API Reference](https://platform.openai.com/docs/api-reference/images/create)

**必填參數：**
- `prompt` (str)：想要的圖片的文字描述。dall-e-2 最長 1000 字元，dall-e-3 最長 4000 字元。

**選填參數：**
- `model` (str)：用哪個模型生圖，預設 dall-e-2
- `n` (int)：要生成幾張，介於 1 到 10，預設 1
- `quality` (str)：圖片品質。hd 會有更細緻的細節，整張圖也更一致。只有 dall-e-3 支援。
- `response_format` (str)：回傳格式，只能是 "url" 或 "b64_json"，預設 "url"
- `size` (str)：圖片尺寸。dall-e-2 只能是 256x256、512x512 或 1024x1024；dall-e-3 只能是 1024x1024、1792x1024 或 1024x1792。預設 "1024x1024"。
- `style`(str | null)：圖片風格，只能是 vivid 或 natural。vivid 會偏向超寫實、戲劇化的圖，natural 比較自然、沒那麼誇張。只有 dall-e-3 支援。
- `user` (str)：代表你的終端使用者的唯一識別碼，讓 OpenAI 監控並偵測濫用。[了解更多](https://beta.openai.com/docs/usage-policies/end-user-ids)

```python
# create an image

# set the prompt
prompt = "A cyberpunk monkey hacker dreaming of a beautiful bunch of bananas, digital art"

# call the OpenAI API
generation_response = client.images.generate(
    model = "dall-e-3",
    prompt=prompt,
    n=1,
    size="1024x1024",
    response_format="url",
)

# print response
print(generation_response)
```

??? note "輸出"

    ```text
    ImagesResponse(created=1701994117, data=[Image(b64_json=None, revised_prompt=None, url='https://oaidalleapiprodscus.blob.core.windows.net/private/org-9HXYFy8ux4r6aboFyec2OLRf/user-8OA8IvMYkfdAcUZXgzAXHS7d/img-ced13hkOk3lXkccQgW1fAQjm.png?st=2023-12-07T23%3A08%3A37Z&se=2023-12-08T01%3A08%3A37Z&sp=r&sv=2021-08-06&sr=b&rscd=inline&rsct=image/png&skoid=6aaadede-4fb3-4698-a8f6-684d7786b067&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2023-12-07T16%3A41%3A48Z&ske=2023-12-08T16%3A41%3A48Z&sks=b&skv=2021-08-06&sig=tcD0iyU0ABOvWAKsY89gp5hLVIYkoSXQnrcmH%2Brkric%3D')])
    ```

```python
# save the image
generated_image_name = "generated_image.png"  # any name you like; the filetype should be .png
generated_image_filepath = os.path.join(image_dir, generated_image_name)
generated_image_url = generation_response.data[0].url  # extract image URL from response
generated_image = requests.get(generated_image_url).content  # download the image

with open(generated_image_filepath, "wb") as image_file:
    image_file.write(generated_image)  # write the image to the file
```

```python
# print the image
print(generated_image_filepath)
display(Image.open(generated_image_filepath))
```

## Variations

variations endpoint 會產生跟輸入圖片相似的新圖片（變體）。[API Reference](https://platform.openai.com/docs/api-reference/images/createVariation)

這裡我們對上面生成的圖片產生變體。

**必填參數：**
- `image` (str)：作為變體基礎的圖片。必須是有效的 PNG、小於 4MB 且為正方形。

**選填參數：**
- `model` (str)：用哪個模型產生變體，目前只支援 dall-e-2
- `n` (int)：要生成幾張，介於 1 到 10，預設 1
- `size` (str)：圖片尺寸，只能是 "256x256"、"512x512" 或 "1024x1024"。越小越快。預設 "1024x1024"。
- `response_format` (str)：回傳格式，只能是 "url" 或 "b64_json"，預設 "url"
- `user` (str)：代表你的終端使用者的唯一識別碼，讓 OpenAI 監控並偵測濫用。[了解更多](https://beta.openai.com/docs/usage-policies/end-user-ids)


```python
# create variations

# call the OpenAI API, using `create_variation` rather than `create`
variation_response = client.images.create_variation(
    image=generated_image,  # generated_image is the image generated above
    n=2,
    size="1024x1024",
    response_format="url",
)

# print response
print(variation_response)
```

??? note "輸出"

    ```text
    ImagesResponse(created=1701994139, data=[Image(b64_json=None, revised_prompt=None, url='https://oaidalleapiprodscus.blob.core.windows.net/private/org-9HXYFy8ux4r6aboFyec2OLRf/user-8OA8IvMYkfdAcUZXgzAXHS7d/img-noNRGgwaaotRGIe6Y2GVeSpr.png?st=2023-12-07T23%3A08%3A59Z&se=2023-12-08T01%3A08%3A59Z&sp=r&sv=2021-08-06&sr=b&rscd=inline&rsct=image/png&skoid=6aaadede-4fb3-4698-a8f6-684d7786b067&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2023-12-07T16%3A39%3A11Z&ske=2023-12-08T16%3A39%3A11Z&sks=b&skv=2021-08-06&sig=ER5RUglhtIk9LWJXw1DsolorT4bnEmFostfnUjY21ns%3D'), Image(b64_json=None, revised_prompt=None, url='https://oaidalleapiprodscus.blob.core.windows.net/private/org-9HXYFy8ux4r6aboFyec2OLRf/user-8OA8IvMYkfdAcUZXgzAXHS7d/img-oz952tL11FFhf9iXXJVIRUZX.png?st=2023-12-07T23%3A08%3A59Z&se=2023-12-08T01%3A08%3A59Z&sp=r&sv=2021-08-06&sr=b&rscd=inline&rsct=image/png&skoid=6aaadede-4fb3-4698-a8f6-684d7786b067&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2023-12-07T16%3A39%3A11Z&ske=2023-12-08T16%3A39%3A11Z&sks=b&skv=2021-08-06&sig=99rJOQwDKsfIeerlMXMHholhAhrHfYaQRFJBF8FKv74%3D')])
    ```

```python
# save the images
variation_urls = [datum.url for datum in variation_response.data]  # extract URLs
variation_images = [requests.get(url).content for url in variation_urls]  # download images
variation_image_names = [f"variation_image_{i}.png" for i in range(len(variation_images))]  # create names
variation_image_filepaths = [os.path.join(image_dir, name) for name in variation_image_names]  # create filepaths
for image, filepath in zip(variation_images, variation_image_filepaths):  # loop through the variations
    with open(filepath, "wb") as image_file:  # open the file
        image_file.write(image)  # write the image to the file
```

```python
# print the original image
print(generated_image_filepath)
display(Image.open(generated_image_filepath))

# print the new variations
for variation_image_filepaths in variation_image_filepaths:
    print(variation_image_filepaths)
    display(Image.open(variation_image_filepaths))
```

## Edits

edit endpoint 用 DALL·E 重新生成既有圖片的指定部分。需要三個輸入：要編輯的圖片、指定要重生區域的 mask，以及描述想要結果的 prompt。[API Reference](https://platform.openai.com/docs/api-reference/images/createEdit)

**必填參數：**
- `image` (str)：要編輯的圖片。必須是有效的 PNG、小於 4MB 且為正方形。沒有提供 mask 的話，圖片必須有透明區域，透明區域會被當成 mask。
- `prompt` (str)：想要的圖片的文字描述，最長 1000 字元。

**選填參數：**
- `mask` (file)：額外的圖片，完全透明的區域（例如 alpha 為 0）代表 image 要被編輯的地方。必須是有效的 PNG、小於 4MB，且尺寸跟 image 相同。
- `model` (str)：用哪個模型編輯圖片，目前只支援 dall-e-2
- `n` (int)：要生成幾張，介於 1 到 10，預設 1
- `size` (str)：圖片尺寸，只能是 "256x256"、"512x512" 或 "1024x1024"。越小越快。預設 "1024x1024"。
- `response_format` (str)：回傳格式，只能是 "url" 或 "b64_json"，預設 "url"
- `user` (str)：代表你的終端使用者的唯一識別碼，讓 OpenAI 監控並偵測濫用。[了解更多](https://beta.openai.com/docs/usage-policies/end-user-ids)


### 設定編輯區域

編輯需要一個 mask 來指定要重生的部分。alpha 為 0（透明）的像素都會被重新生成。下面的程式建立一個 1024x1024 的 mask，下半部是透明的。

```python
# create a mask
width = 1024
height = 1024
mask = Image.new("RGBA", (width, height), (0, 0, 0, 1))  # create an opaque image mask

# set the bottom half to be transparent
for x in range(width):
    for y in range(height // 2, height):  # only loop over the bottom half of the mask
        # set alpha (A) to zero to turn pixel transparent
        alpha = 0
        mask.putpixel((x, y), (0, 0, 0, alpha))

# save the mask
mask_name = "bottom_half_mask.png"
mask_filepath = os.path.join(image_dir, mask_name)
mask.save(mask_filepath)
```

### 執行編輯

現在把圖片、描述和 mask 送給 API，拿到 5 個編輯結果的範例

```python
# edit an image

# call the OpenAI API
edit_response = client.images.edit(
    image=open(generated_image_filepath, "rb"),  # from the generation section
    mask=open(mask_filepath, "rb"),  # from right above
    prompt=prompt,  # from the generation section
    n=1,
    size="1024x1024",
    response_format="url",
)

# print response
print(edit_response)
```

??? note "輸出"

    ```text
    ImagesResponse(created=1701994167, data=[Image(b64_json=None, revised_prompt=None, url='https://oaidalleapiprodscus.blob.core.windows.net/private/org-9HXYFy8ux4r6aboFyec2OLRf/user-8OA8IvMYkfdAcUZXgzAXHS7d/img-9UOVGC7wB8MS2Q7Rwgj0fFBq.png?st=2023-12-07T23%3A09%3A27Z&se=2023-12-08T01%3A09%3A27Z&sp=r&sv=2021-08-06&sr=b&rscd=inline&rsct=image/png&skoid=6aaadede-4fb3-4698-a8f6-684d7786b067&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2023-12-07T16%3A40%3A37Z&ske=2023-12-08T16%3A40%3A37Z&sks=b&skv=2021-08-06&sig=MsRMZ1rN434bVdWr%2B9kIoqu9CIrvZypZBfkQPTOhCl4%3D')])
    ```

```python
# save the image
edited_image_name = "edited_image.png"  # any name you like; the filetype should be .png
edited_image_filepath = os.path.join(image_dir, edited_image_name)
edited_image_url = edit_response.data[0].url  # extract image URL from response
edited_image = requests.get(edited_image_url).content  # download the image

with open(edited_image_filepath, "wb") as image_file:
    image_file.write(edited_image)  # write the image to the file
```

```python
# print the original image
print(generated_image_filepath)
display(Image.open(generated_image_filepath))

# print edited image
print(edited_image_filepath)
display(Image.open(edited_image_filepath))
```

## 重點整理

- DALL·E API 有 generations、variations、edits 三種 endpoint，分別對應生成、變體、局部重繪。
- `quality`、`style` 只有 dall-e-3 支援；variations 和 edits 目前只支援 dall-e-2。
- 兩個模型的 `size` 可選值和 `prompt` 長度上限都不同，換模型時要一起改。
- edits 靠 mask 的透明區域（alpha 為 0）決定要重生哪裡。
- 輸入圖片要是正方形 PNG 且小於 4MB。

## 練習

1. 把 `n` 改成 2、`size` 改成 "512x512"，看看生成速度和結果有什麼差別。
2. 在 mask 的程式碼裡，把透明區域從下半部改成上半部，再跑一次 edit，比較結果。
3. 把 generations 的 `model` 換成 dall-e-3，加上 `quality="hd"` 和 `style="natural"`，並把 `n` 改回 1，觀察跟 dall-e-2 的差別。
