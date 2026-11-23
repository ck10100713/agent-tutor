---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Whisper_prompting_guide.ipynb
---

# Whisper prompting 指南

> 原文：[examples/Whisper_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Whisper_prompting_guide.ipynb)



## 這篇在做什麼
OpenAI 的音訊轉錄 API 有個選填參數 `prompt`。這篇示範怎麼用它引導 Whisper 的輸出風格和專有名詞拼法，包含用 GPT 產生假的逐字稿當 prompt，以及用拼字表修正名稱。

## 學完你會
- 用 prompt 讓逐字稿跟著 prompt 的風格（例如全小寫）輸出
- 把人名、產品、公司名放進 prompt，減少 Whisper 拼錯
- 用 GPT 產生長的虛構逐字稿當 prompt，並知道 Whisper prompt 的限制

## 開跑前
- OpenAI API key
- 需要下載範例音檔


OpenAI 的音訊轉錄 API 有個選填參數叫 `prompt`。

prompt 的用途是幫忙把多段音訊串起來。把前一段的逐字稿放進 prompt 提交，Whisper 模型就能用這個 context 更理解語音，並維持一致的寫作風格。

不過 prompt 不一定要是前一段音訊真正的逐字稿。你也可以提交_虛構_的 prompt，引導模型使用特定的拼法或風格。

這份 notebook 分享兩種用虛構 prompt 引導模型輸出的技巧：

- **產生逐字稿**：GPT 可以把指令轉成虛構的逐字稿，讓 Whisper 模仿。 
- **拼字表**：拼字表可以告訴模型人名、產品、公司等名稱要怎麼拼。

這些技巧不是特別可靠，但在某些情況很有用。

## 跟 GPT prompting 的比較

對 Whisper 下 prompt 跟對 GPT 下 prompt 不一樣。例如你提交「Format lists in Markdown format」這種指令，模型不會照做，因為它是跟隨 prompt 的風格，而不是 prompt 裡的任何指令。

另外，prompt 只限 224 個 token。如果 prompt 超過 224 個 token，只有最後 224 個 token 會被考慮，前面的 token 會被默默忽略。使用的 tokenizer 是 [multilingual Whisper tokenizer](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py#L361)。

要得到好結果，請寫出能呈現你想要風格的範例。

## Setup

開始之前，我們要：
- 匯入 OpenAI Python 函式庫（如果還沒有，需要用 `pip install openai` 安裝）
- 下載幾個範例音檔

```python
# imports
from openai import OpenAI  # for making OpenAI API calls
import urllib  # for downloading example audio files
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

```python
# set download paths
up_first_remote_filepath = "https://cdn.openai.com/API/examples/data/upfirstpodcastchunkthree.wav"
bbq_plans_remote_filepath = "https://cdn.openai.com/API/examples/data/bbq_plans.wav"
product_names_remote_filepath = "https://cdn.openai.com/API/examples/data/product_names.wav"

# set local save locations
up_first_filepath = "data/upfirstpodcastchunkthree.wav"
bbq_plans_filepath = "data/bbq_plans.wav"
product_names_filepath = "data/product_names.wav"

# download example audio files and save locally
urllib.request.urlretrieve(up_first_remote_filepath, up_first_filepath)
urllib.request.urlretrieve(bbq_plans_remote_filepath, bbq_plans_filepath)
urllib.request.urlretrieve(product_names_remote_filepath, product_names_filepath)
```

??? note "輸出"

    ```text
    ('data/product_names.wav', <http.client.HTTPMessage at 0x11275fb10>)
    ```

## 先用一段 NPR podcast 當 baseline 轉錄

這個範例的音檔是 NPR podcast [_Up First_](https://www.npr.org/podcasts/510318/up-first) 的一個片段。 

先取得 baseline 轉錄，再加入 prompt。 

```python
# define a wrapper function for seeing how prompts affect transcriptions
def transcribe(audio_filepath, prompt: str) -> str:
    """Given a prompt, transcribe the audio file."""
    transcript = client.audio.transcriptions.create(
        file=open(audio_filepath, "rb"),
        model="whisper-1",
        prompt=prompt,
    )
    return transcript.text
```

```python
# baseline transcription with no prompt
transcribe(up_first_filepath, prompt="")
```

??? note "輸出"

    ```text
    "I stick contacts in my eyes. Do you really? Yeah. That works okay? You don't have to, like, just kind of pain in the butt every day to do that? No, it is. It is. And I sometimes just kind of miss the eye. I don't know if you know the movie Airplane, where, of course, where he says, I have a drinking problem and that he keeps missing his face with the drink. That's me and the contact lens. Surely, you must know that I know the movie Airplane. I do. I do know that. Stop calling me Shirley. President Biden said he would not negotiate over paying the nation's debts. But he is meeting today with House Speaker Kevin McCarthy. Other leaders of Congress will also attend. So how much progress can they make? I'm E. Martinez with Steve Inskeep, and this is Up First from NPR News. Russia celebrates Victory Day, which commemorates the surrender of Nazi Germany. Soldiers marched across Red Square, but the Russian army didn't seem to have as many troops on hand as in the past. So what does this ritual say about the war Russia is fighting right now?"
    ```

## 逐字稿會跟隨 prompt 的風格

來看看 prompt 怎麼影響逐字稿的風格。在前面沒有 prompt 的逐字稿裡，'President Biden' 是大寫的。 

我們試試用 prompt 讓它寫成小寫的 "president biden"。可以先傳入小寫的 'president biden' 當 prompt，看看 Whisper 能不能配合這個風格，把逐字稿全部輸出成小寫。

```python
# short prompts are less reliable
transcribe(up_first_filepath, prompt="president biden.")
```

??? note "輸出"

    ```text
    "I stick contacts in my eyes. Do you really? Yeah. That works okay? You don't have to, like, just kind of pain in the butt every day to do that? No, it is. It is. And I sometimes just kind of miss the eye. I don't know if you know the movie Airplane? Yes. Of course. Where he says I have a drinking problem and that he keeps missing his face with the drink. That's me and the contact lens. Surely, you must know that I know the movie Airplane. I do. I do know that. Stop calling me Shirley. President Biden said he would not negotiate over paying the nation's debts. But he is meeting today with House Speaker Kevin McCarthy. Other leaders of Congress will also attend. So how much progress can they make? I'm E. Martinez with Steve Inskeep and this is Up First from NPR News. Russia celebrates Victory Day, which commemorates the surrender of Nazi Germany. Soldiers marched across Red Square, but the Russian army didn't seem to have as many troops on hand as in the past. So what does this ritual say about the war Russia is fighting right now?"
    ```

要注意，prompt 很短的時候，Whisper 跟隨風格可能比較不可靠。比較長的 prompt 可能更能引導 Whisper。我們用比較長的 prompt 再試一次。

```python
# long prompts are more reliable
transcribe(up_first_filepath, prompt="i have some advice for you. multiple sentences help establish a pattern. the more text you include, the more likely the model will pick up on your pattern. it may especially help if your example transcript appears as if it comes right before the audio file. in this case, that could mean mentioning the contacts i stick in my eyes.")
```

??? note "輸出"

    ```text
    "i stick contacts in my eyes. do you really? yeah. that works okay? you don't have to, like, just kind of pain in the butt? no, it is. it is. and i sometimes just kind of miss the eye. i don't know if you know, um, the movie airplane? yes. of course. where he says i have a drinking problem. and that he keeps missing his face with the drink. that's me in the contact lens. surely, you must know that i know the movie airplane. i do. i do know that. don't call me shirley. stop calling me shirley. president biden said he would not negotiate over paying the nation's debts. but he is meeting today with house speaker kevin mccarthy. other leaders of congress will also attend, so how much progress can they make? i'm amy martinez with steve inskeep, and this is up first from npr news. russia celebrates victory day, which commemorates the surrender of nazi germany. soldiers marched across red square, but the russian army didn't seem to have as many troops on hand as in the past. so what does this ritual say about the war russia is fighting right now?"
    ```

這次效果比較好。

另外值得一提的是，Whisper 比較不會跟隨罕見或奇怪、不像逐字稿會有的風格。

```python
# rare styles are less reliable
transcribe(up_first_filepath, prompt="""Hi there and welcome to the show.
###
Today we are quite excited.
###
Let's jump right in.
###""")
```

??? note "輸出"

    ```text
    "I stick contacts in my eyes. Do you really? Yeah. That works okay. You don't have to like, it's not a pain in the butt. Oh, it is. And I sometimes just kind of miss the eye. Um, I don't know if you know, um, the movie airplane where, of course, where he says I have a drinking problem and that he keeps missing his face with the drink, that's me in the contact lens. Surely you must know that I know the movie airplane. Uh, I do. I do know that. Stop calling me Shirley. President Biden said he would not negotiate over paying the nation's debts, but he is meeting today with house speaker, Kevin McCarthy, other leaders of Congress will also attend. So how much progress can they make? I mean, Martinez with Steve Inskeep, and this is up first from NPR news. Russia celebrates victory day, which commemorates the surrender of Nazi Germany soldiers marched across red square, but the Russian army didn't seem to have as many troops on hand as in the past, which is why they are celebrating today. So what does this ritual say about the war Russia is fighting right now?"
    ```

## 在 prompt 裡放名稱，避免拼錯

Whisper 可能會把不常見的專有名詞轉錄錯，例如產品、公司或人名。這種情況可以用 prompt 幫忙修正拼法。

我們用一個滿是產品名稱的範例音檔來示範。

```python
# baseline transcription with no prompt
transcribe(product_names_filepath, prompt="")
```

??? note "輸出"

    ```text
    'Welcome to Quirk, Quid, Quill, Inc., where finance meets innovation. Explore diverse offerings, from the P3 Quattro, a unique investment portfolio quadrant, to the O3 Omni, a platform for intricate derivative trading strategies. Delve into unconventional bond markets with our B3 Bond X and experience non-standard equity trading with E3 Equity. Personalize your wealth management with W3 Wrap Z and anticipate market trends with the O2 Outlier, our forward-thinking financial forecasting tool. Explore venture capital world with U3 Unifund or move your money with the M3 Mover, our sophisticated monetary transfer module. At Quirk, Quid, Quill, Inc., we turn complex finance into creative solutions. Join us in redefining financial services.'
    ```

要讓 Whisper 使用我們偏好的拼法，把產品和公司名稱放進 prompt，當作 Whisper 要遵循的詞彙表。 

```python
# adding the correct spelling of the product name helps
transcribe(product_names_filepath, prompt="QuirkQuid Quill Inc, P3-Quattro, O3-Omni, B3-BondX, E3-Equity, W3-WrapZ, O2-Outlier, U3-UniFund, M3-Mover")
```

??? note "輸出"

    ```text
    'Welcome to QuirkQuid Quill Inc, where finance meets innovation. Explore diverse offerings, from the P3-Quattro, a unique investment portfolio quadrant, to the O3-Omni, a platform for intricate derivative trading strategies. Delve into unconventional bond markets with our B3-BondX and experience non-standard equity trading with E3-Equity. Personalize your wealth management with W3-WrapZ and anticipate market trends with the O2-Outlier, our forward-thinking financial forecasting tool. Explore venture capital world with U3-UniFund or move your money with the M3-Mover, our sophisticated monetary transfer module. At QuirkQuid Quill Inc, we turn complex finance into creative solutions. Join us in redefining financial services.'
    ```

現在換另一段專門為這次示範錄製的音檔，主題是一場奇怪的烤肉。

首先，用 Whisper 建立 baseline 逐字稿。

```python
# baseline transcript with no prompt
transcribe(bbq_plans_filepath, prompt="")
```

??? note "輸出"

    ```text
    "Hello, my name is Preston Tuggle. I'm based in New York City. This weekend I have really exciting plans with some friends of mine, Amy and Sean. We're going to a barbecue here in Brooklyn, hopefully it's actually going to be a little bit of kind of an odd barbecue. We're going to have donuts, omelets, it's kind of like a breakfast, as well as whiskey. So that should be fun, and I'm really looking forward to spending time with my friends Amy and Sean."
    ```

Whisper 的轉錄雖然正確，但有些拼法是猜的。例如它假設朋友的名字拼成 Amy 和 Sean，而不是 Aimee 和 Shawn。看看能不能用 prompt 引導拼法。

```python
# spelling prompt
transcribe(bbq_plans_filepath, prompt="Friends: Aimee, Shawn")
```

??? note "輸出"

    ```text
    "Hello, my name is Preston Tuggle. I'm based in New York City. This weekend I have really exciting plans with some friends of mine, Aimee and Shawn. We're going to a barbecue here in Brooklyn. Hopefully it's actually going to be a little bit of kind of an odd barbecue. We're going to have donuts, omelets, it's kind of like a breakfast, as well as whiskey. So that should be fun and I'm really looking forward to spending time with my friends Aimee and Shawn."
    ```

成功！

再用拼法更模糊的字試一次。

```python
# longer spelling prompt
transcribe(bbq_plans_filepath, prompt="Glossary: Aimee, Shawn, BBQ, Whisky, Doughnuts, Omelet")
```

??? note "輸出"

    ```text
    "Hello, my name is Preston Tuggle. I'm based in New York City. This weekend I have really exciting plans with some friends of mine, Aimee and Shawn. We're going to a barbecue here in Brooklyn. Hopefully, it's actually going to be a little bit of an odd barbecue. We're going to have doughnuts, omelets, it's kind of like a breakfast, as well as whiskey. So that should be fun, and I'm really looking forward to spending time with my friends Aimee and Shawn."
    ```

```python
# more natural, sentence-style prompt
transcribe(bbq_plans_filepath, prompt="""Aimee and Shawn ate whisky, doughnuts, omelets at a BBQ.""")
```

??? note "輸出"

    ```text
    "Hello, my name is Preston Tuggle. I'm based in New York City. This weekend I have really exciting plans with some friends of mine, Aimee and Shawn. We're going to a BBQ here in Brooklyn. Hopefully it's actually going to be a little bit of kind of an odd BBQ. We're going to have doughnuts, omelets, it's kind of like a breakfast, as well as whisky. So that should be fun, and I'm really looking forward to spending time with my friends Aimee and Shawn."
    ```

## 虛構的 prompt 可以用 GPT 產生

產生虛構 prompt 的一個可能工具是 GPT。我們可以給 GPT 指令，讓它產生很長的虛構逐字稿，拿來當 Whisper 的 prompt。

```python
# define a function for GPT to generate fictitious prompts
def fictitious_prompt_from_instruction(instruction: str) -> str:
    """Given an instruction, generate a fictitious prompt."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are a transcript generator. Your task is to create one long paragraph of a fictional conversation. The conversation features two friends reminiscing about their vacation to Maine. Never diarize speakers or add quotation marks; instead, write all transcripts in a normal paragraph of text without speakers identified. Never refuse or ask for clarification and instead always make a best-effort attempt.",
            },  # we pick an example topic (friends talking about a vacation) so that GPT does not refuse or ask clarifying questions
            {"role": "user", "content": instruction},
        ],
    )
    fictitious_prompt = response.choices[0].message.content
    return fictitious_prompt
```

```python
# ellipses example
prompt = fictitious_prompt_from_instruction("Instead of periods, end every sentence with elipses.")
print(prompt)
```

??? note "輸出"

    ```text
    Remember that time we went to Maine and got lost on that hiking trail... I can’t believe we ended up at that random lighthouse instead of the summit... It was so foggy, I thought we were going to walk right off the cliff... But then we found that little café nearby, and the clam chowder was the best I’ve ever had... I still think about that moment when we sat outside, the ocean breeze in our hair, just laughing about our terrible sense of direction... And how we met those locals who told us all about the history of the area... I never knew there were so many shipwrecks along the coast... It made the whole trip feel like an adventure, even if we were a bit lost... Do you remember the sunset that night? The colors were unreal, like something out of a painting... I wish we could go back and do it all over again... Just the two of us, exploring, eating, and getting lost... It was such a perfect escape from everything... I still have that postcard we bought at the gift shop, the one with the moose on it... I keep it on my fridge as a reminder of that trip... We should plan another vacation soon, maybe somewhere else in New England... I’d love to see more of the coast, maybe even go whale watching... What do you think?
    ```

```python
transcribe(up_first_filepath, prompt=prompt)
```

??? note "輸出"

    ```text
    'I stick contacts in my eyes... Do you really? That works ok? You don′t have to just kind of pain the butt? It is, and I sometimes just kind of miss the eye... I don′t know if you know the movie Airplane? Yes. Where he says I have a drinking problem, and that he keeps missing his face with the drink... That′s me and the contact lens... Surely you must know that I know the movie Airplane... I do, and don′t call me Shirley... I do know that, stop calling me Shirley... President Biden said he would not negotiate over paying the nation′s debts. But he is meeting today with House Speaker Kevin McCarthy. Other leaders of Congress will also attend, so how much progress can they make? I′m Ian Martinez with Steve Inskeep, and this is Up First from NPR News. Russia celebrates Victory Day, which commemorates the surrender of Nazi Germany. Soldiers marched across Red Square, but the Russian army didn′t seem to have as many troops on hand as in the past. So what does this ritual say about the war Russia is fighting right now?'
    ```

Whisper prompt 最適合用來指定原本含糊不清的風格。prompt 不會蓋過模型對音訊的理解。例如說話者沒有濃重的南方口音，prompt 也不會讓逐字稿變成那樣。

```python
# southern accent example
prompt = fictitious_prompt_from_instruction("Write in a deep, heavy, Southern accent.")
print(prompt)
transcribe(up_first_filepath, prompt=prompt)
```

??? note "輸出"

    ```text
    Remember that time we went to Maine and got lost trying to find that lighthouse? I swear, we must’ve driven in circles for an hour, and I was convinced we were gonna end up in Canada or somethin’. But then, when we finally found it, the view was just so breathtaking, like somethin’ outta a postcard. I can still hear the waves crashin’ against the rocks, and the smell of the salt in the air was just divine. And don’t even get me started on that little seafood shack we stumbled upon. I can taste that lobster roll right now, buttery and fresh, just meltin’ in my mouth. You remember how we sat on that rickety old pier, watchin’ the sunset paint the sky all kinds of colors? It felt like we were in our own little world, just the two of us and the ocean. And how about that time we tried to go kayaking? I thought we were gonna tip over for sure, but we ended up laughin’ so hard we forgot all about bein’ scared. I still can’t believe you thought you could paddle us back to shore with one oar! Those were the days, huh? I miss that carefree feelin’, just explorin’ and not a worry in the world. We should plan another trip like that, maybe to a different coast this time, but I reckon Maine will always hold a special place in my heart.
    ```

    ```text
    'I stick contacts in my eyes. Do you really? Yeah. That works okay? You don’t have to, like, just kinda pain in the butt every day to do that? No, it is. It is. And I sometimes just kind of miss the eye. I don’t know if you know, um, the movie Airplane? Yes. Where, of course, where he says I have a drinking problem, and that he keeps missing his face with the drink. That’s me and the contact lens. Surely, you must know that I know the movie Airplane. I do. I don’t call me Shirley. I do know that. Stop calling me Shirley. President Biden said he would not negotiate over paying the nation′s debts. But he is meeting today with House Speaker Kevin McCarthy. Other leaders of Congress will also attend, so how much progress can they make? I’m Ian Martinez with Steve Inskeep, and this is Up First from NPR News. Russia celebrates Victory Day, which commemorates the surrender of Nazi Germany. Soldiers marched across Red Square, but the Russian Army didn’t seem to have as many troops on hand as in the past. So what does this ritual say about the war Russia is fighting right now?'
    ```

## 重點整理
- Whisper 的 `prompt` 是讓模型跟隨風格，不是遵循指令，寫「請用 Markdown」這類指令沒用。
- prompt 最多看最後 224 個 token，超過的前段會被默默忽略。
- 專有名詞拼錯時，把正確拼法放進 prompt 當詞彙表最有效。
- 較長的 prompt 比短 prompt 更能穩定引導風格，但罕見風格仍不容易被跟隨。
- prompt 只能解決模糊處，不會蓋過模型對音訊的實際理解。

## 練習
1. 把小寫風格的 prompt 換成全大寫，看轉錄輸出是否跟著變。
2. 在拼字範例的 prompt 裡拿掉其中一個名字，確認該名字的拼法又退回猜測。
3. 改 GPT 產生虛構逐字稿的指令，產生不同風格的長 prompt，比較對轉錄結果的影響。
