---
translated: true
status: deprecated
tags:
- 原文已封存
source: articles/what_is_new_with_dalle_3.mdx
---
# DALL·E 3 有什麼新東西？

> 原文：[articles/what_is_new_with_dalle_3.mdx](https://github.com/openai/openai-cookbook/blob/main/articles/what_is_new_with_dalle_3.mdx)



## 這篇在做什麼
介紹 DALL·E 3 的 Image generation API 跟 DALL·E 2 比多了哪些參數和功能，並用大量範例說明每個參數對成品的影響。後半是作者試出來的應用點子（icon、logo、貼紙等）和目前還做不好的題目。

## 學完你會
- 知道 `model`、`style`、`quality`、`size` 這幾個 DALL·E 3 參數怎麼設、預設值是什麼。
- 判斷什麼情境該用 natural 或 vivid、standard 或 hd、方形或橫直幅。
- 用 Potrace 把生成的圖轉成 SVG，做出自己的 icon 產生流程。

DALL·E-3 是我們最新版的 DALL-E 文字生圖模型。作為目前文字生圖的最先進水準，DALL·E 能在各種領域生成高品質的圖片。如果你想知道 DALL·E-3 怎麼做出來的技術細節，可以看我們的[研究論文](https://cdn.openai.com/papers/dall-e-3.pdf)。這篇文章會介紹 DALL·E-3 的新功能和能力，也會舉一些你可以用 API 做的新產品範例。

先提醒一下，Image generation API 沒有變，endpoint 和格式都跟 DALL·E-2 一樣。如果你想看 Image API 的使用教學，請見這篇 [Cookbook 文章](https://cookbook.openai.com/examples/dalle/image_generations_edits_and_variations_with_dall-e)。

目前 DALL·E-3 只能用 **Generations** 這個 API endpoint（/v1/images/generations）。還不支援 variations 或 inpainting，不過 Edits 和 Variations endpoint 仍可搭配 DALL·E-2 使用。

## Generations

generation API endpoint 會根據文字 prompt 生成圖片。我們新增了幾個參數，讓你可以做出更多東西。以下是選項的簡介：

### 新參數：

- **model**（‘dall-e-2’ 或 ‘dall-e-3’）：你要用哪個模型生成。要小心設成 ‘dall-e-3’，因為留空的話預設是 ‘dall-e-2’。
- **style**（‘natural’ 或 ‘vivid’）：生成圖片的風格，必須是 vivid 或 natural。Vivid 會讓模型偏向生成超寫實、戲劇化的圖片。Natural 會讓模型生成比較自然、不那麼超寫實的圖片。預設是 ‘vivid’。
- **quality**（‘standard’ 或 ‘hd’）：生成圖片的品質。‘hd’ 會生成細節更細、整張圖一致性更高的圖片。預設是 ‘standard’。

### 其他參數：

- **prompt**（str）：想要的圖片的文字描述，最長 1000 字元。必填。
- **n**（int）：要生成幾張圖，必須介於 1 到 10，預設是 1。dall-e-3 只支援 n=1。
- **size**（...）：生成圖片的尺寸。DALL·E-2 模型必須是 256x256、512x512 或 1024x1024。DALL·E-3 模型必須是 1024x1024、1792x1024 或 1024x1792。
- **response_format**（'url' 或 'b64_json'）：圖片的回傳格式，必須是 "url" 或 "b64_json"。預設是 "url"。
- **user**（str）：代表你的終端使用者的唯一識別碼，幫助 OpenAI 監控和偵測濫用。了解更多。

## 新功能

DALL·E-3 上線時帶來很多新功能，幫你生成想要的圖片。以下是新東西的簡介：

### Prompt Rewriting

最新 DALL·E-3 API 有個新功能叫 prompt rewriting，我們會用 GPT-4 在你的 prompt 傳給 DALL-E 之前先優化。我們的研究發現，prompt 寫得很詳細，結果會好很多。關於 captioning、prompting 和安全緩解措施，可以看 [DALL·E-3 研究論文](https://cdn.openai.com/papers/dall-e-3.pdf)。

_注意這個功能目前沒辦法關掉，不過你可以在 prompt 裡直接對 relabeler 下指示，一樣能得到很高的忠實度，後面的範例會示範。_

![Prompt Rewriting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/dalle_3_improved_prompts.png)

### Standard 與 HD 品質

DALL·E-3 新增 'quality' 參數，讓你調整所有生成結果的細節程度和條理。'standard' 品質就是你熟悉的 DALL·E-3，'hd' 則對細節和 prompt 的貼合度更講究。注意把品質設成 ‘hd’ 會提高每張圖的成本，生成時間通常也會多約 10 秒。

例如這裡有兩個 icon，分別是 'hd' 和 'standard' 品質。兩種品質的選擇通常看口味，但需要捕捉更多細節、質感，或把場景構圖弄得更好時，'hd' 常常比較好。

![Icons](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/icons.jpg)

再看另一個例子，prompt 是 'An infinite, uniform grid of tessellated cubes.'，DALL·E 順手把它改寫成 _"An infinite, uniform grid of tessellated cubes painted carefully in an isometric perspective. The cubes are meticulously arranged in such a way that they seem to stretch endlessly into the distance. Each cube is identical to the next, with light reflecting consistently across all surfaces, underscoring their uniformity. This is a digitally rendered image."_：

![Cubes](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/cubes.jpg)

### 新尺寸

DALL·E-3 接受三種圖片尺寸：1024px x 1024px、1792px x 1024px 和 1024px x 1792px。除了在長寬比上更有彈性，這些尺寸還會明顯影響生成圖片的風格和情境。例如想要像手機拍出來的照片，直幅可能比較適合；風景畫或數位設計，橫幅可能比較好。

為了展示差異，這裡是同一個 prompt 用不同長寬比生成的多個版本。這次的 prompt 是：“Professional photoshoot of a Chemex brewer in the process of brewing coffee.”（參考用，這是[真實 Chemex 咖啡壺](https://m.media-amazon.com/images/I/61lrld81vxL.jpg)的照片。）

這是方形的生成結果（HD 和 standard 品質都有）：

![square_coffee](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/square_coffee.jpg)

可以看到這些圖的取景貼近物品，像是在比較封閉的空間裡拍的，周圍有各種東西。

這是同樣 prompt 用比較寬的長寬比的結果：

![wide_coffee](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/wide_coffee.jpg)

跟前面比，這些是特寫的形式。背景模糊，焦點更集中在物品本身，更像專業安排的攝影，而不是隨手拍。

最後是直幅：

![tall_coffee](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/tall_coffee.jpg)

這些更像手機照片，比較隨性自然，動作也比較多：慢慢滴落的咖啡，或是從壺裡倒出來的畫面。

### 新風格

DALL·E-3 新增兩種風格：natural 和 vivid。natural 風格比較接近 DALL·E-2 的風格，寫實但比較平淡；vivid 是新風格，偏向生成超寫實、電影感的圖片。供參考，ChatGPT 裡所有 DALL·E 生成的圖都是 'vivid' 風格。

當 DALL·E-3 把本來應該簡單、低調或寫實的主體誇大或弄混時，natural 風格特別有用。我常用它來生成 logo、庫存照片，或是想對應現實物品的情況。

這是同樣 prompt 用 vivid 風格的例子。vivid 電影感強很多（而且很好看），但如果你不需要那種效果，可能會太搶眼。

![vivid_coffee](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/vivid_coffee.jpg)

很多情況我比較喜歡 natural 風格，例如這張湯瑪斯·科爾（Thomas Cole）《Desolation》風格的畫：

![thomas_cole](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/thomas_cole.jpg)

## 範例與 Prompt

為了幫你開始用 DALL·E-3 做東西，我想了幾個可以用 API 做的產品範例，也收集了一些目前似乎只有 DALL·E-3 做得到的風格和能力。我也列了幾個我一直沒辦法讓 DALL·E-3 生成的主題，你想挑戰的話可以試試。

### Icon 生成

你有沒有為網站或 app 找不到完美的 icon 而苦惱過？如果有個客製 icon 產生器 app，讓你選 icon 的風格、尺寸和主題，然後從 DALL·E 生成的圖產出客製 SVG，應該很棒。這是我用 DALL·E-3 生成的一些網站 icon：

![icon_set](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/icon_set.jpg)

這裡我用 Potrace 把圖片轉成 SVG，你可以在[這裡](https://potrace.sourceforge.net/)下載。我是這樣轉換圖片的：

```bash
potrace -s cat.jpg -o cat.svg
```

轉成 SVG 之前，你可能需要先提高圖片的亮度和對比。我用下面的指令處理：

```bash
convert cat.jpg -brightness-contrast 50x50 cat.jpg
```

### Logo 生成

DALL·E-3 很適合幫公司或產品的 logo 設計起個頭。用 'Vector logo design of a Greek statue, minimalistic, with a white background' 當 prompt，我得到下面的結果：

![logo_greece](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/logo_greece.jpg)

這是我做的另一個 logo，給一間阿拉伯咖啡店：

![logo_arabia](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/logo_arabia.jpg)

要在既有 logo 上迭代的話，我拿 OpenAI 的 logo，請 GPT-4V 描述它，再請 DALL·E 生成這個 logo 的變化版：

![iteration](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/iteration.jpg)

### 客製刺青

DALL·E-3 很會生成線稿，可以拿來做客製刺青。這是我用 DALL·E-3 生成的一些線稿：

![tattoos](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/tattoos.jpg)

### 模切貼紙與 T 恤

如果能用 DALL·E-3 生成客製模切貼紙和 T 恤，再串接 Printful 或 Stickermule 這類 print-on-demand 服務呢？幾分鐘內就能拿到客製貼紙或 T 恤，完全不用設計經驗。這是我用 DALL·E-3 生成的一些貼紙：

![stickers](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/stickers.jpg)

### Minecraft 造型（Skin）

費了點功夫，我讓 DALL·E-3 生成了 Minecraft skin。我相信靠巧妙的 prompt，可以讓 DALL·E-3 穩定生成很棒的 Minecraft skin。直接用 'Minecraft' 這個詞可能不行，因為 DALL·E 可能以為你想生成遊戲本身的內容，所以可以換個方式表達："Flat player skin texture of a ninja skin, compatible with Minecraftskins.com or Planet Minecraft."

這是我做出來的結果，可能還需要修一修，但我覺得是個不錯的起點：

![minecraft](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/minecraft.jpg)

### 還有更多⋯⋯

這些是我有想過但還沒空試的點子：

- 客製表情符號或 Twitch emote？
- 向量插圖？
- 個人化 Bitmoji 風格頭像？
- 專輯封面？
- 客製賀卡？
- 跟 DALL·E「pair-programming」做海報、傳單？

## 作品展示

我們才剛開始摸索 DALL·E-3 能做到什麼。這裡是我目前看過最棒的一些風格、生成結果和 prompt。有些圖我找不到原作者，如果你知道是誰做的，請告訴我！

![collage](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/collage.jpg)

來源：

[@scharan79 on Reddit](https://www.reddit.com/r/dalle2/comments/170ce1r/dalle_3_is_pretty_good_at_drawing/)  
[@TalentedJuli on Reddit](https://www.reddit.com/r/dalle2/comments/1712x7a/60s_pulp_magazine_illustration_is_the_best_style/)  
[@Wild-Culture-5068 on Reddit](https://www.reddit.com/r/dalle2/comments/17dwp0s/soviet_blade_runner/)  
[@popsicle_pope on Reddit](https://www.reddit.com/r/dalle2/comments/170lx1z/%F0%9D%94%AA%F0%9D%94%A2%F0%9D%94%B1%F0%9D%94%9E%F0%9D%94%AA%F0%9D%94%AC%F0%9D%94%AF%F0%9D%94%AD%F0%9D%94%A5%F0%9D%94%AC%F0%9D%94%B0%F0%9D%94%A6%F0%9D%94%B0/)  
[@gopatrik on Twitter](https://twitter.com/gopatrik/status/1717579802205626619)  
[@ARTiV3RSE on Twitter](https://twitter.com/ARTiV3RSE/status/1720202013638599040)  
[@willdepue on Twitter](https://twitter.com/willdepue/status/1705677997150445941)  
Various OpenAI employees

## 挑戰

DALL·E-3 還很新，還有很多它不擅長的事（也可能是我還沒摸清楚怎麼下 prompt）。這些是你可能想試試看的挑戰：

### 網頁設計

DALL·E 很不擅長生成看起來真實的網站、app 等等，常常生成的像是網頁設計師的作品集頁面。這是我目前做出最好的結果：

![websites](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/websites.jpg)

### 無縫貼圖（Seamless Textures）

DALL·E-3 感覺離生成無縫貼圖只差一點點。常常生成得很棒，只是邊緣稍微被切掉，或有一些瑕疵。看下面的例子：

![seamless](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/seamless.jpg)

### 字型

用 DALL·E 生成客製字型或迭代字母設計應該很酷，但我還沒辦法讓它成功。這是我目前做出最好的結果：

![fonts](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_3/fonts.jpg)

## 更多資源

謝謝你讀到這裡！如果你想找更多 DALL·E-3 的資源，這裡有一些相關連結：

- [DALL·E-3 Blog Post](https://openai.com/dall-e-3)
- [DALL·E-3 Research Paper](https://cdn.openai.com/papers/dall-e-3.pdf)
- [Image API Documentation](https://platform.openai.com/docs/api-reference/images)
- [Image API Cookbook](https://cookbook.openai.com/examples/dalle/image_generations_edits_and_variations_with_dall-e)

## 重點整理
- `model` 要明確設成 `dall-e-3`，留空會落到 `dall-e-2`。
- DALL·E-3 目前只有 Generations endpoint，且只支援 `n=1`。
- `style`（natural/vivid）管風格，`quality`（standard/hd）管細節，hd 比較貴也比較慢。
- 尺寸會影響構圖和氛圍：方形偏封閉取景，橫幅偏特寫，直幅偏手機隨拍感。
- Prompt rewriting 無法關閉，要控制結果就在 prompt 裡直接下指示。

## 練習
1. 用同一個 prompt 分別跑 `style="natural"` 和 `style="vivid"`，比較差異。
2. 同一個 prompt 跑三種 `size`，記下每種的構圖特色。
3. 做一個小腳本：生成一張 icon，用 Potrace 轉成 SVG，並在轉換前先調整亮度和對比。
