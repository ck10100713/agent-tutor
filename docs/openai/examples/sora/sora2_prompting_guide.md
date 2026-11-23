---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/sora/sora2_prompting_guide.ipynb
---

# Sora 2 Prompting 指南

> 原文：[examples/sora/sora2_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/sora/sora2_prompting_guide.ipynb)

教你寫出有效的 Sora 2 影片 prompt。

## 這篇在做什麼

這篇是 Sora 2 的 prompting 指南，講怎麼把一個鏡頭描述清楚：鏡頭、動作、光線、色彩、對白。同時介紹 Sora API 的參數和 endpoint，以及圖片輸入、角色參考、影片延伸和編輯這些進階功能。

## 學完你會

- 分清楚哪些設定要放在 API 參數（model、size、seconds、characters），哪些才寫在 prompt 裡。
- 把「A beautiful street at night」這類模糊描述，改寫成鏡頭、動作、光線都具體的強 prompt。
- 用圖片輸入、角色、影片延伸和編輯，做出風格一致的多段影片。

## 開跑前

需要 OpenAI API key 和可以使用 Sora API 的帳號，影片生成會產生費用。


# 寫出成功的影片 prompt

## 更新 - 2026 年 3 月
這份指南已更新，反映最新的 Sora API 功能，包括：
- **角色參考（物件和動物）**：上傳一次角色，就能在多支影片裡重複使用，外觀保持一致。
- **更高解析度輸出**：可生成 1920×1080 或 1080×1920 的影片。
- **更長的影片**：最長時間從 12 秒增加到 20 秒。
- **影片延伸**：用完整的初始片段當脈絡來延伸現有影片，不只是最後一個 frame。
- **影片的 Batch API**：為較大型的製作流程執行非同步的影片生成工作。


## 下 prompt 之前
把寫 prompt 想成對一位沒看過你分鏡表的攝影師做簡報。你沒講的細節，他會自己即興發揮，結果可能跟你想的不一樣。把「鏡頭」要達成的效果講具體，模型就更能控制、更一致。

不過刻意留白也很有用。給模型更多創作空間，可能得到驚喜的變化和意想不到的漂亮詮釋。兩種做法都對：**詳細的 prompt 給你控制力和一致性，簡短的 prompt 則為創意結果留空間。** 怎麼取捨看你的目標和想要的結果。
把 prompt 當成創意願望清單，不是合約。跟 ChatGPT 一樣，**同一個 prompt 多跑幾次會得到不同結果**，這是特色不是 bug。每次生成都是新的詮釋，有時第二或第三個結果更好。

最重要的是準備好反覆調整。鏡頭、光線或動作的小改動，就可能讓結果差很多。跟模型合作：你給方向，模型給你創意變化。

這不是精確的科學，下面的建議是我們跟模型合作過程中學到的經驗。




## API 參數
prompt 控制影片的內容，但有些屬性只能由 API 參數決定。你沒辦法用文字要求它們，必須在 API 呼叫裡明確設定：
- **model**：`sora-2` 或 `sora-2-pro`。
- **size**：格式為 {width}x{height} 的字串。支援的解析度依所選的 model 而定：
    - sora-2
        - 720x1280, 1280x720, 
    - sora-2-pro
        - 720x1280, 1280x720
        - 1024x1792, 1792x1024
        - 1080x1920, 1920x1080 
- **seconds**：片段長度，支援的值："4"、"8"、"12"、"16"、"20"。預設是 "4"。
- **characters** *(選填)*：一次生成最多可參考 **兩個已上傳的角色**。每個項目要包含 Characters API 回傳的角色 ID。

這些參數是影片的容器：解析度、長度和角色參考不會因為 prompt 裡寫「make it longer」就改變。要在 API 呼叫裡明確設定；prompt 控制的是其他一切（主體、動作、光線、風格）。更多細節看 [Sora API 文件](https://developers.openai.com/api/docs/guides/video-generation)。

### 影片解析度
影片解析度直接影響 Sora 的畫面保真度和動作一致性。解析度越高，細節、質感和光線轉換越準確；解析度低則會壓縮視覺資訊，常出現模糊或 artifact。

### 影片長度
模型通常在較短的片段上更可靠地遵循指示。要有最好的結果，鏡頭盡量簡短。如果專案允許，剪輯時把兩段 4 秒的片段接起來，可能會比直接生成一段 8 秒的效果更好。

## Endpoints
Sora API 支援幾個用來生成和迭代影片的 endpoint：

- **Create video**：`POST /v1/videos`  
  從 prompt 生成新影片。

- **Create character**：`POST /v1/videos/characters`  
  上傳一段簡短的參考影片，建立可重複使用的角色。

- **Extend video**：`POST /v1/videos/extensions`  
  接續現有影片。會用完整的原始片段當脈絡。

- **Edit video**：`POST /v1/videos/{video_id}/edits`  
  用新的 prompt 編輯現有影片。

## 有效的 prompt 結構
清楚的 prompt 描述鏡頭的方式，就像把它畫在分鏡表上。講明鏡頭取景、註明景深、把動作拆成節拍來描述，並設定光線和色調。用幾個獨特的細節固定住主體，能讓它容易辨認；只放一個合理的動作，鏡頭會更好懂。

如果需要涵蓋一段序列，一個 prompt 裡描述多個鏡頭也可以。這樣做的時候，每個鏡頭區塊要分清楚：一次只有一個鏡頭設定、一個主體動作和一套光線。這讓你可以彈性地生成短的獨立片段，或較長的連續時刻，看專案需要。把每個鏡頭當成一個創意單元，可以在剪輯時接起來，也可以讓它們一次連續播完。

- 較短的 prompt 讓模型有更多創作自由，預期會有驚喜的結果。 
- 較長、較詳細的 prompt 會限制模型的創意。它會盡量照你的指引做，但不一定每次都可靠。

這是一個短 prompt 的例子：
```text
In a 90s documentary-style interview, an old Swedish man sits in a study and says, "I still remember when I was young."
```
這個 prompt 很可能會順利：
- `90s documentary` 設定影片的風格。模型會據此選擇鏡頭焦段、光線和調色這些變數。
- `an old Swedish man sits in a study` 用很少的細節描述主體和場景，讓模型自由決定這個人和場景的樣子。
- `and says, "I still remember when I was young."` 描述對白。Sora 很可能能精確照做。

這個 prompt 會穩定地生成符合這些要求的影片。不過因為留了很多細節沒講，結果可能不完全符合你的想像。例如 prompt 沒描述時間、天氣、服裝、語氣、角色的外貌和年紀、鏡頭角度、剪接、場景設計和很多其他因素。你沒描述的，Sora 就會自己編。

### 極度詳細
複雜的電影感鏡頭，可以超越標準的 prompt 結構，用專業製作的術語指定畫面質感、鏡頭設定、調色、聲音設計，甚至拍攝的理由。這就像導演對攝影組或視覺特效組做簡報。鏡頭、濾鏡、光線、調色和運動的詳細提示，能幫模型鎖定非常特定的美學風格。

例如你可以描述**觀眾最先注意到什麼**、**攝影器材和鏡頭**、**光線方向**、**色彩配置**、**質感**、**現場音效（diegetic sound）**和**鏡頭時間點**。想複製真實的攝影風格（例如 IMAX 空拍、35mm 手持、復古 16mm 紀錄片）或要在多個鏡頭間維持嚴格的連貫性，這個做法很有效。

#### 範例

```python
Format & Look
Duration 4s; 180° shutter; digital capture emulating 65 mm photochemical contrast; fine grain; subtle halation on speculars; no gate weave.

Lenses & Filtration
32 mm / 50 mm spherical primes; Black Pro-Mist 1/4; slight CPL rotation to manage glass reflections on train windows.

Grade / Palette
Highlights: clean morning sunlight with amber lift.
Mids: balanced neutrals with slight teal cast in shadows.
Blacks: soft, neutral with mild lift for haze retention.

Lighting & Atmosphere
Natural sunlight from camera left, low angle (07:30 AM).
Bounce: 4×4 ultrabounce silver from trackside.
Negative fill from opposite wall.
Practical: sodium platform lights on dim fade.
Atmos: gentle mist; train exhaust drift through light beam.

Location & Framing
Urban commuter platform, dawn.
Foreground: yellow safety line, coffee cup on bench.
Midground: waiting passengers silhouetted in haze.
Background: arriving train braking to a stop.
Avoid signage or corporate branding.

Wardrobe / Props / Extras
Main subject: mid-30s traveler, navy coat, backpack slung on one shoulder, holding phone loosely at side.
Extras: commuters in muted tones; one cyclist pushing bike.
Props: paper coffee cup, rolling luggage, LED departure board (generic destinations).

Sound
Diegetic only: faint rail screech, train brakes hiss, distant announcement muffled (-20 LUFS), low ambient hum.
Footsteps and paper rustle; no score or added foley.

Optimized Shot List (2 shots / 4 s total)

0.00–2.40 — “Arrival Drift” (32 mm, shoulder-mounted slow dolly left)
Camera slides past platform signage edge; shallow focus reveals traveler mid-frame looking down tracks. Morning light blooms across lens; train headlights flare softly through mist. Purpose: establish setting and tone, hint anticipation.

2.40–4.00 — “Turn and Pause” (50 mm, slow arc in)
Cut to tighter over-shoulder arc as train halts; traveler turns slightly toward camera, catching sunlight rim across cheek and phone screen reflection. Eyes flick up toward something unseen. Purpose: create human focal moment with minimal motion.

Camera Notes (Why It Reads)
Keep eyeline low and close to lens axis for intimacy.
Allow micro flares from train glass as aesthetic texture.
Preserve subtle handheld imperfection for realism.
Do not break silhouette clarity with overexposed flare; retain skin highlight roll-off.

Finishing
Fine-grain overlay with mild chroma noise for realism; restrained halation on practicals; warm-cool LUT for morning split tone.
Mix: prioritize train and ambient detail over footstep transients.
Poster frame: traveler mid-turn, golden rim light, arriving train soft-focus in background haze.
```

## 決定畫面質感的視覺提示
寫 prompt 時，**風格是引導模型最有力的槓桿之一**。描述整體美學，例如 *"1970s film"*、*"epic, IMAX-scale scene"* 或 *"16mm black-and-white film"*，會建立一個視覺基調，框住其他所有選擇。盡早確立風格，模型才能一路延續下去。

同樣的細節，依你要的是精緻的好萊塢劇情片、手持的手機影片，還是有顆粒感的復古廣告，讀起來會很不一樣。基調定下來之後，再用鏡頭、動作和光線疊加細節。

清楚才會贏。不要寫 *"a beautiful street"* 這種模糊的提示，改寫 *"wet asphalt, zebra crosswalk, neon sign reflection"*。不要寫 *"moves quickly"*，改寫 *"jogs three steps and stops at the curb"*。指向可見結果的動詞和名詞，永遠會給你更清楚、更一致的輸出。

| **弱的 prompt** | **強的 prompt** |
| --- | --- |
| “A beautiful street at night” | “Wet asphalt, zebra crosswalk, neon signs reflecting in puddles” |
| “Person moves quickly” | “Cyclist pedals three times, brakes, and stops at crosswalk” |
| “Cinematic look” | “Anamorphic 2.0x lens, shallow DOF, volumetric light” |

鏡頭指示和取景決定一個鏡頭給人的感覺。從上方拍的廣角鏡頭強調空間和背景，視線高度的特寫則把注意力放在情緒上。景深又加了一層：淺景深能讓主體在模糊的背景中突出，深景深則讓前景和背景都保持清晰。光線設定基調的力道一樣強。柔和溫暖的主光營造親切感，單一的硬光加上冷色邊緣則偏向戲劇性。

介紹角色時，要預期會有些不可預測，措辭的小改動可能改變角色的身分、姿勢，甚至場景的焦點。跨鏡頭時保持描述一致，重複使用相同的措辭來維持連貫，並避免混用可能互相衝突的特徵。

**弱**

```text
Camera shot: cinematic look
```

**強**
```text
Camera shot: wide shot, low angle
Depth of field: shallow (sharp on subject, blurred background)
Lighting + palette: warm backlight with soft rim
```

一些好的取景指示範例：
- wide establishing shot, eye level 
- wide shot, tracking left to right with the charge
- aerial wide shot, slight downward angle
- medium close-up shot, slight angle from behind

一些好的鏡頭運動指示範例：
- slowly tilting camera
- handheld eng camera

## 控制動作和時間
動作常常是最難抓準的部分，所以要保持簡單。每個鏡頭應該只有一個清楚的鏡頭運動和一個清楚的主體動作。動作最好用節拍或次數來描述，例如小步伐、手勢或停頓，這樣它們才有時間上的依據。

“Actor walks across the room” 沒給多少可以發揮的東西。像 “Actor takes four steps to the window, pauses, and pulls the curtain in the final second” 這樣一句，時間就精準而且做得到。

**弱**
```text
Actor walks across the room.
```

**強**
```text
Actor takes four steps to the window, pauses, and pulls the curtain in the final second.
```

## 光線和色彩的一致性
光線決定氣氛的程度不輸動作或場景。畫面中擴散的光感覺平靜中性，單一的強光源則製造強烈對比和緊張感。想把多個片段剪在一起時，光線邏輯保持一致才能讓剪輯無縫。

要描述光線的質感，也要描述加強它的色彩錨點。不要只寫「brightly lit room」這種籠統的註記，要指明光源和色調的組合：“soft window light with a warm lamp fill and a cool edge from the hallway”。點出三到五個顏色，有助於讓跨鏡頭的色調保持穩定。

**弱**
```text
Lighting + palette: brightly lit room
```

**強**
```text
Lighting + palette: soft window light with warm lamp fill, cool rim from hallway 
Palette anchors: amber, cream, walnut brown
```

## 用圖片輸入取得更多控制
想對鏡頭的**構圖和風格**做更細的控制，可以用**圖片輸入**當視覺參考。照片、數位藝術或 AI 生成的圖都可以。這能鎖定角色設計、服裝、場景佈置或整體美學這些元素。模型把圖片當成第一個 frame 的錨點，你的文字 prompt 則定義接下來發生什麼。

**怎麼用**

在 POST /videos 請求裡，把圖片檔放在 input_reference 參數。
- 圖片必須符合目標影片的解析度（size）。
- 支援的檔案格式：`image/jpeg`、`image/png` 和 `image/webp`。



| 用 [OpenAI GPT Image](https://platform.openai.com/docs/guides/image-generation) 生成的輸入圖片 | 用 Sora 2 生成的影片（轉成 GIF） |
| :--: | :--: |
| ![](https://cdn.openai.com/API/docs/images/sora/sora_woman_skyline_original_2.jpeg)<p><small>[Download this image](https://cdn.openai.com/API/docs/images/sora/woman_skyline_original_720p.jpeg)</small></p> | ![](https://cdn.openai.com/API/docs/images/sora/sora_woman_skyline_video.gif)<p><small>Prompt: _“She turns around and smiles, then slowly walks out of the frame.”_</small></p> |
| ![](https://cdn.openai.com/API/docs/images/sora/sora_monster_original_2.jpeg)<p><small>[Download this image](https://cdn.openai.com/API/docs/images/sora/monster_original_720p.jpeg)</small></p> | ![](https://cdn.openai.com/API/docs/images/sora/sora_monster_original.gif) <p><small>Prompt: _“The fridge door opens. A cute, chubby purple monster comes out of it.”_</small></p> |

### 實驗小技巧

如果你手邊沒有視覺參考，[OpenAI 的圖片生成模型](https://platform.openai.com/docs/guides/image-generation)是很好的產生方式。你可以很快做出環境和場景設計，再把它們當參考丟進 Sora。這是測試美學風格、替影片找到漂亮起點的好方法。

## 對白和音訊
對白必須直接寫在 prompt 裡。把它放在文字描述下面的 <dialogue> 區塊，讓模型清楚分辨視覺描述和說出口的台詞。台詞要簡短自然，並盡量把對話限制在幾句話內，讓時間能配合片段長度。多角色的場景，要一致地標示說話者並輪流發言；這樣模型比較能把每句台詞對應到正確角色的手勢和表情。

也要想節奏和時間：4 秒的鏡頭通常容納一到兩句簡短的對話，8 秒的片段可以多幾句。冗長複雜的演說不太可能對得上，還可能破壞節奏。

如果鏡頭是無聲的，你仍然可以用一個小小的聲音來暗示節奏，例如 “distant traffic hiss” 或 “a crisp snap”。把它當成節奏提示，不是完整的配樂。

帶對白的 prompt 範例：

```text
A cramped, windowless room with walls the color of old ash. A single bare bulb dangles from the ceiling, its light pooling onto the scarred metal table at the center. Two chairs face each other across it. On one side sits the Detective, trench coat draped across the back of his chair, eyes sharp and unblinking. Across from him, the Suspect slouches, cigarette smoke curling lazily toward the ceiling. The silence presses in, broken only by the faint hum of the overhead light.

Dialogue:
- Detective: "You’re lying. I can hear it in your silence."
- Suspect: "Or maybe I’m just tired of talking."
- Detective: "Either way, you’ll talk before the night’s over."
```

背景聲音的描述範例：

```text
The hum of espresso machines and the murmur of voices form the background.
```

## 用影片編輯來迭代
編輯是用來微調，不是賭運氣。用它做可控的改動，一次一個，並說明你要改什麼：“same shot, switch to 85 mm”，或 “same lighting, new palette: teal, sand, rust”。結果接近時，把它固定成參考，只描述要微調的地方。這樣已經成功的部分都會被鎖住。

如果一個鏡頭一直失敗，就把它精簡：固定鏡頭、簡化動作、清掉背景。等它能用了，再一步步疊加複雜度。

| 原始影片 | 編輯後的影片 |
| --- | --- |
| ![Original Video 1](https://cdn.openai.com/API/docs/images/sora/sora_monster_original.gif)<p><small>Original Video</small></p> | ![Edited Video 1](https://cdn.openai.com/API/docs/images/sora/sora_monster_orange.gif)<p><small>_Edit prompt: "Change the color of the monster to orange"_</small></p> |
| ![Original Video 1](https://cdn.openai.com/API/docs/images/sora/sora_monster_original.gif)<p><small>Original Video</small></p> | ![Edited Video 2](https://cdn.openai.com/API/docs/images/sora/sora_monster_2monsters.gif)<p><small>_Edit prompt: "A second monster comes out right after"_</small></p> |

## 角色

Characters API 讓你用簡短的參考影片建立可重複使用的角色。建立之後，角色可以在之後的生成裡重複使用，讓外觀和畫面上的身分保持一致。任何動物或物件都可以做成角色。 

### 建立角色
上傳一段簡短的參考片段來建立角色。要求如下：
- MP4 影片
- 2 到 4 秒
- 720p 到 1080p 解析度
- 16:9 或 9:16 的長寬比

### 用角色生成
建立影片時，帶上角色 ID，並在 prompt 裡用名字稱呼該角色。建議一次生成不要超過 2 個角色。

```bash
{
  "model": "sora-2",
  "prompt": "A cinematic shot of Alfie running through wet grass at sunrise",
  "size": "720x1280",
  "seconds": "4",
  "characters": [
    { "id": "char_123" }
  ]
}
```
下面是三個用上傳的角色（一隻叫 Alfie 的狗）生成的 GIF 範例。最左邊的影片是用來建立角色的原始參考

| 輸入的角色影片 | 生成 1 | 生成 2 | 生成 3 |
| --- | --- | --- | --- |
| <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/sora/gifs/alfie_input.gif" width="220"> | <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/sora/gifs/alfie_museum.gif" width="220"> | <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/sora/gifs/alfie_f1.gif" width="220"> | <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/sora/gifs/alfie_tokyo.gif" width="220"> |

## 延伸影片

你可以生成額外的片段來延伸現有影片。模型會用完整的原始片段當脈絡，有助於維持場景的連貫。這適合用較短的片段組出較長的序列。單次延伸最多支援 20 秒。一支影片最多可以延伸 6 次，總長 120 秒。



# Prompt 模板和範例

## Prompt 結構
一種有效的寫法是把你希望模型使用的不同種類資訊分開。這**不是萬用的成功配方**，但它給你一個清楚的框架，也更容易保持一致。不是每個細節都要寫，鏡頭用不到的就可以省略。

事實上，**刻意讓某些元素保持開放，會鼓勵模型更有創意**。你對每個視覺選擇限制得越少，模型越有空間去詮釋，帶給你出乎意料但常常很美的變化。描述很詳細的 prompt 會產生較一致、可控的結果，較簡短的 prompt 則能解鎖多樣、新鮮又有想像力的結果。
描述型的 prompt 模板：

```text
[Prose scene description in plain language. Describe characters, costumes, scenery, weather and other details. Be as descriptive to generate a video that matches your vision.]

Cinematography:
Camera shot: [framing and angle, e.g. wide establishing shot, eye level]
Mood: [overall tone, e.g. cinematic and tense, playful and suspenseful, luxurious anticipation]

Actions:
- [Action 1: a clear, specific beat or gesture]
- [Action 2: another distinct beat within the clip]
- [Action 3: another action or dialogue line]

Dialogue:
[If the shot has dialogue, add short natural lines here or as part of the actions list. Keep them brief so they match the clip length.]
```

## Prompt 範例

### 範例 1
```text
Style: Hand-painted 2D/3D hybrid animation with soft brush textures, warm tungsten lighting, and a tactile, stop-motion feel. The aesthetic evokes mid-2000s storybook animation — cozy, imperfect, full of mechanical charm. Subtle watercolor wash and painterly textures; warm–cool balance in grade; filmic motion blur for animated realism.

Inside a cluttered workshop, shelves overflow with gears, bolts, and yellowing blueprints. At the center, a small round robot sits on a wooden bench, its dented body patched with mismatched plates and old paint layers. Its large glowing eyes flicker pale blue as it fiddles nervously with a humming light bulb. The air hums with quiet mechanical whirs, rain patters on the window, and the clock ticks steadily in the background.

Cinematography:
Camera: medium close-up, slow push-in with gentle parallax from hanging tools
Lens: 35 mm virtual lens; shallow depth of field to soften background clutter
Lighting: warm key from overhead practical; cool spill from window for contrast
Mood: gentle, whimsical, a touch of suspense

Actions:
- The robot taps the bulb; sparks crackle.
- It flinches, dropping the bulb, eyes widening.
- The bulb tumbles in slow motion; it catches it just in time.
- A puff of steam escapes its chest — relief and pride.
- Robot says quietly: "Almost lost it… but I got it!"

Background Sound:
Rain, ticking clock, soft mechanical hum, faint bulb sizzle.
```

### 範例 2
```text
Style: 1970s romantic drama, shot on 35 mm film with natural flares, soft focus, and warm halation. Slight gate weave and handheld micro-shake evoke vintage intimacy. Warm Kodak-inspired grade; light halation on bulbs; film grain and soft vignette for period authenticity.

At golden hour, a brick tenement rooftop transforms into a small stage. Laundry lines strung with white sheets sway in the wind, catching the last rays of sunlight. Strings of mismatched fairy bulbs hum faintly overhead. A young woman in a flowing red silk dress dances barefoot, curls glowing in the fading light. Her partner — sleeves rolled, suspenders loose — claps along, his smile wide and unguarded. Below, the city hums with car horns, subway tremors, and distant laughter.

Cinematography:
Camera: medium-wide shot, slow dolly-in from eye level
Lens: 40 mm spherical; shallow focus to isolate the couple from skyline
Lighting: golden natural key with tungsten bounce; edge from fairy bulbs
Mood: nostalgic, tender, cinematic

Actions:
- She spins; her dress flares, catching sunlight.
- Woman (laughing): "See? Even the city dances with us tonight."
- He steps in, catches her hand, and dips her into shadow.
- Man (smiling): "Only because you lead."
- Sheets drift across frame, briefly veiling the skyline before parting again.

Background Sound:
Natural ambience only: faint wind, fabric flutter, street noise, muffled music. No added score.

``` 

## 重點整理

- 解析度、長度、model 和角色是 API 參數，寫在 prompt 裡不會生效。
- 詳細的 prompt 換來控制力和一致性，簡短的 prompt 換來創意空間，同一個 prompt 每次結果也不同。
- 描述要具體到看得見：用名詞和動詞指向可見的結果，一個鏡頭只放一個鏡頭運動和一個主體動作。
- 光線和色彩要有邏輯並點出三到五個顏色，多個片段才好剪在一起。
- 想改結果用編輯或延伸，一次只改一個變數，其他的鎖住。

## 練習

1. 拿頁面上的短 prompt 範例，加上時間、天氣和服裝三個細節，比較兩個版本生成結果的差異。
2. 把頁面上動作的弱 prompt，改寫成用「幾步、停頓、最後一秒做什麼」描述的強 prompt，並把 seconds 設成 4 和 8 各跑一次，看節奏對不對得上。
3. 用 Characters API 上傳一段 2 到 4 秒的參考片段，在 prompt 裡用角色名字生成兩個不同場景，再用 Extend video 把其中一支延伸一次，檢查外觀是否一致。
