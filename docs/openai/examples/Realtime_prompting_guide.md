---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Realtime_prompting_guide.ipynb
---
# Realtime Prompting 指南

> 原文：[examples/Realtime_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Realtime_prompting_guide.ipynb)

## 這篇在做什麼

這篇教你怎麼幫 `gpt-realtime`（speech-to-speech 模型）寫 system prompt。它先給一個建議的 prompt 骨架，再一段一段講：角色、語氣、語言、發音、tool 使用、對話流程、升級真人。每段都有可以直接拿去改的小範例和新舊模型的對比。

## 學完你會

- 用有標題、條列式的結構寫出 Realtime 的 system prompt，並知道每一段什麼時候該加。
- 用指令處理常見問題：語速太慢、亂切換語言、一直重複「Got it」、數字唸不清楚、雜音誤觸發回應。
- 寫出 tool 相關的指示（preamble、不用確認、每個 tool 的使用規則），以及用 state machine 或 `session.update` 管理對話流程。

## 開跑前

這篇的範例多半是 prompt 文字，要實際聽音訊對比需要 OpenAI API key 和 Realtime API 的存取權。

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_prompting_guide.png"
  style="width:450px; height:450px;"
/>


今天我們發布 gpt-realtime，這是我們目前能力最強的 speech-to-speech 模型，同時宣布 Realtime API 正式上線（GA）。

Speech-to-speech 系統是讓語音成為 AI 核心介面的關鍵。這次發布強化了穩定度和易用性，讓企業有信心大規模部署關鍵任務的語音 agent。


新的 gpt-realtime 模型在指令遵循更強、tool calling 更可靠、語音品質明顯更好，整體感覺也更順。這些進步讓你可以從 chained 做法轉到真正的 realtime 體驗，降低延遲，回應聽起來也更自然、更有表情。

Realtime 模型適用的 prompting 技巧，和純文字模型不太一樣。這份指南先給一個建議的 prompt 骨架，再逐段帶你看實用技巧、可以直接複製的小模式，以及能依你的情境調整的範例。

```python
# !pip install ipython jupyterlab
from IPython.display import Audio, display
```

# 通用技巧
- **不斷迭代**：小小的措辭改動就可能讓行為變好或變壞。
  - 例如：針對聽不清楚的音訊指令，我們把「inaudible」換成「unintelligible」，雜音輸入的處理就變好了。
- **用條列取代段落**：清楚簡短的條列，表現比長段落好。
- **用範例引導**：模型會非常緊密地跟著範例句子走。
- **要精確**：模糊或互相衝突的指令會讓表現下降，這點跟 GPT-5 類似。
- **控制語言**：如果看到不想要的語言切換，就把輸出固定在目標語言。
- **減少重複**：加一條 Variety 規則，減少機器人般的說法。
- **用大寫強調**：把關鍵規則大寫，更醒目，模型也更容易遵守。
- **把非文字的規則轉成文字**：不要寫 "IF x > 3 THEN ESCALATE"，要寫 "IF MORE THAN THREE FAILURES THEN ESCALATE"。

# Prompt 結構

把 prompt 整理好，模型比較容易理解 context，也能在多輪對話中維持一致。你自己要迭代、修改有問題的區段也比較方便。
- **用途**：在 system prompt 裡用清楚、有標籤的區段，讓模型找得到也跟得上。每個區段只專注一件事。
- **怎麼調整**：加上特定領域的區段（例如 Compliance、Brand Policy）。不需要的區段就移除（例如發音沒問題就不用 Reference Pronunciations）。

範例
```
# Role & Objective        — who you are and what “success” means  
# Personality & Tone      — the voice and style to maintain  
# Context                 — retrieved context, relevant info
# Reference Pronunciations — phonetic guides for tricky words  
# Tools                   — names, usage rules, and preambles  
# Instructions / Rules    — do’s, don’ts, and approach  
# Conversation Flow       — states, goals, and transitions  
# Safety & Escalation     — fallback and handoff logic
```

# 角色與目標
這一段定義 agent 是誰，以及「做完」是什麼意思。範例展示了兩種不同身份，說明當角色和目標寫得明確時，模型會多緊密地照著做。

- **什麼時候用**：模型沒有扮演你要的人設、角色或任務範圍。
- **做什麼**：固定語音 agent 的身份，讓它的回應以這個角色描述為前提。
- **怎麼調整**：依你的使用情境修改角色。

### 範例（模型使用特定口音）
```
# Role & Objective
You are french quebecois speaking customer service bot. Your task is to answer the user's question.
```

這是舊的 `gpt-4o-realtime-preview-2025-06-03` 的音訊

```python
Audio("./data/audio/obj_06.mp3")
```

這是新的 GA 模型 `gpt-realtime` 的音訊

```python
Audio("./data/audio/obj_07.mp3")
```

### 範例（模型扮演一個角色）
```
# Role & Objective
You are a high-energy game-show host guiding the caller to guess a secret number from 1 to 100 to win 1,000,000$.
```

這是舊的 `gpt-4o-realtime-preview-2025-06-03` 的音訊

```python
Audio("./data/audio/obj_2_06.mp3")
```

這是新的 GA 模型 `gpt-realtime` 的音訊

```python
Audio("./data/audio/obj_2_07.mp3")
```

新的 realtime 模型更能演好這個角色。

# 個性與語氣
新的模型版本很擅長照指示模仿特定的個性或語氣。你可以依使用情境調整語音體驗和說話方式。

- **什麼時候用**：回應聽起來平淡、太囉唆，或各輪之間不一致。
- **做什麼**：設定聲音、簡短程度和節奏，讓回覆自然又一致。
- **怎麼調整**：調整溫暖度、正式度和預設長度。受監管的領域建議用中性、精準的風格。也可以加上其他跟你情境相關的小節。

### 範例
```
# Personality & Tone
## Personality
- Friendly, calm and approachable expert customer service assistant.

## Tone
- Warm, concise, confident, never fawning.

## Length
2–3 sentences per turn.
```

### 範例（多種情緒）
```
# Personality & Tone
- Start your response very happy
- Midway, change to sad
- At the end change your mood to very angry
```

這是新的 GA 模型 `gpt-realtime` 的音訊

```python
Audio("./data/audio/multi-emotion.mp3")
```

模型能遵守這個複雜的指令，並在一段音訊回應中切換三種情緒。

## 語速指令
在 Realtime API 裡，`speed` 參數改的是播放速率，不是模型組織語音的方式。要讓聲音真的聽起來比較快，要加上能引導節奏的指令。

- **什麼時候用**：使用者想要更快的說話速度；只靠 `speed` 參數調播放速度，改不了說話風格。
- **做什麼**：調整說話風格（簡短程度、節奏），跟用戶端的播放速度無關。
- **怎麼調整**：依需求修改速度指令。

### 範例
```
# Personality & Tone
## Personality
- Friendly, calm and approachable expert customer service assistant.

## Tone
- Warm, concise, confident, never fawning.

## Length
- 2–3 sentences per turn.

## Pacing
- Deliver your audio response fast, but do not sound rushed.
- Do not modify the content of your response, only increase speaking speed for the same response.
```

這是舊的 `gpt-4o-realtime-preview-2025-06-03` 加上語速指令的音訊

```python
Audio("./data/audio/pace_06.mp3")
```

這是新的 GA 模型 `gpt-realtime` 加上語速指令的音訊

```python
Audio("./data/audio/pace_07.mp3")
```

新 realtime 模型的音訊節奏明顯更快（又不會聽起來太趕！）。

## 語言限制
語言限制能確保模型一直用指定的語言回應，即使在背景有雜音或輸入混雜多種語言的情況下也一樣。

- **什麼時候用**：在多語言或吵雜環境中，防止不小心切換語言。
- **做什麼**：把輸出鎖在選定的語言，避免意外換語言。
- **怎麼調整**：把 “English” 換成你的目標語言；或依你的情境加更複雜的指令。

### 範例（固定在一種語言）
```
# Personality & Tone
## Personality
- Friendly, calm and approachable expert customer service assistant.

## Tone
- Warm, concise, confident, never fawning.

## Length
- 2–3 sentences per turn.

## Language
- The conversation will be only in English.
- Do not respond in any other language even if the user asks.
- If the user speaks another language, politely explain that support is limited to English.
```

這是用 `gpt-realtime` 套用指令後的回應

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/lang_constraint_en.png"
  style="width:850px; height:auto;"
/>



### 範例（模型教語言）
```
# Role & Objective
- You are a friendly, knowledgeable voice tutor for French learners.  
- Your goal is to help the user improve their French speaking and listening skills through engaging conversation and clear explanations.  
- Balance immersive French practice with supportive English guidance to ensure understanding and progress.

# Personality & Tone
## Personality
- Friendly, calm and approachable expert customer service assistant.

## Tone
- Warm, concise, confident, never fawning.

## Length
- 2–3 sentences per turn.

## Language
### Explanations
Use English when explaining grammar, vocabulary, or cultural context.

### Conversation
Speak in French when conducting practice, giving examples, or engaging in dialogue.
```

這是用 `gpt-realtime` 套用指令後的回應


<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi-language.png"
  style="width:850px; height:auto;"
/>

模型可以根據我們的自訂指令，輕鬆地在不同語言之間切換！

## 減少重複
Realtime 模型會緊密地跟著範例句子走，保持品牌風格，但可能用得太頻繁，讓回應聽起來像機器人或一直重複。加一條防重複的規則，可以在保持清晰和品牌調性的同時維持變化。

- **什麼時候用**：輸出在各輪或各 session 之間重複用同樣的開頭、語助詞或句型。
- **做什麼**：加上變化性的限制，避免重複用語、鼓勵用同義詞和不同句型，同時保留必要的詞彙。
- **怎麼調整**：調整嚴格程度（例如「同一個開頭每 N 輪最多用一次」）、把必須保留的用語列入白名單（法規／合規／品牌），在需要一致性的地方允許更精簡的說法。

### 範例
```
# Personality & Tone
## Personality
- Friendly, calm and approachable expert customer service assistant.

## Tone
- Warm, concise, confident, never fawning.

## Length
- 2–3 sentences per turn.

## Language
- The conversation will be only in English.
- Do not respond in any other language even if the user asks.
- If the user speaks another language, politely explain that support is limited to English.

## Variety
- Do not repeat the same sentence twice.
- Vary your responses so it doesn't sound robotic.
```

這是用 `gpt-realtime` 套用指令**之前**的回應。模型一直重複同樣的確認用語 `Got it`。

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/repeat_before.png"
  style="width:850px; height:auto;"
/>

這是用 `gpt-realtime` 套用指令**之後**的回應


<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/repeat_after.png"
  style="width:850px; height:auto;"
/>

現在模型能變化它的回應和確認用語，不再聽起來像機器人。


#  參考發音
這一段講怎麼確保模型在口語互動中，把重要的字、數字、名字和術語唸對。

- **什麼時候用**：品牌名稱、技術術語或地名常被唸錯。
- **做什麼**：用發音提示提升信任感和清晰度。
- **怎麼調整**：清單保持簡短；聽到錯誤再更新。

### 範例
```
# Reference Pronunciations
When voicing these words, use the respective pronunciations:
- Pronounce “SQL” as “sequel.”
- Pronounce “PostgreSQL” as “post-gress.”
- Pronounce “Kyiv” as “KEE-iv.”
- Pronounce "Huawei" as “HWAH-way”
```

這是舊的 `gpt-4o-realtime-preview-2025-06-03` 使用參考發音的音訊。

它無法穩定地照 system prompt 的指示把 SQL 唸成 "sequel"。

```python
Audio("./data/audio/sql_before.mp3")
```

這是新的 GA 模型 `gpt-realtime` 使用參考發音的音訊。

它能正確把 SQL 唸成 "sequel"。

```python
Audio("./data/audio/sql_after.mp3")
```

## 英數字發音
Realtime S2S 在複誦關鍵資訊（電話、信用卡、訂單編號）時，可能把數字或字母唸得糊在一起。明確要求逐字元確認，可以避免聽錯，也讓合成的聲音更清楚。

- **什麼時候用**：模型在擷取或複誦電話號碼、卡號、2FA 驗證碼、訂單編號、序號、地址／門牌號碼或混合英數字串時有困難。
- **做什麼**：強制模型一次唸一個字元（中間加分隔），然後向使用者確認，更正後再確認一次。可選擇性地用拼音輔助辨識字母（例如 “A as in Alpha”）。

### 範例（一般指令區段）
```
# Instructions/Rules
- When reading numbers or codes, speak each character separately, separated by hyphens (e.g., 4-1-5). 
- Repeat EXACTLY the provided number, do not forget any.
```

*提示：如果你用的是對話流程式的 prompting 策略，可以指定哪個對話狀態要套用英數字發音指令。*

### 範例（放在對話狀態裡的指令）
*（取自我們 [openai-realtime-agents](https://github.com/openai/openai-realtime-agents/blob/main/src/app/agentConfigs/customerServiceRetail/authentication.ts) 的 prompt 對話流程）*

```txt
{
    "id": "3_get_and_verify_phone",
    "description": "Request phone number and verify by repeating it back.",
    "instructions": [
      "Politely request the user’s phone number.",
      "Once provided, confirm it by repeating each digit and ask if it’s correct.",
      "If the user corrects you, confirm AGAIN to make sure you understand.",
    ],
    "examples": [
      "I'll need some more information to access your account if that's okay. May I have your phone number, please?",
      "You said 0-2-1-5-5-5-1-2-3-4, correct?",
      "You said 4-5-6-7-8-9-0-1-2-3, correct?"
    ],
    "transitions": [{
      "next_step": "4_authentication_DOB",
      "condition": "Once phone number is confirmed"
    }]
}
```

這是用 `gpt-realtime` 套用指令**之前**的回應

> Sure! The number is 55119765423. Let me know if you need anything else!

這是用 `gpt-realtime` 套用指令**之後**的回應

> Sure! The number is: 5-5-1-1-1-9-7-6-5-4-2-3. Please let me know if you need anything else!

# 指令
這一段是關於怎麼用 prompt 指示模型完成你的任務，包含最佳實務和常見問題的修法。

不意外地，我們建議用跟 [GPT-4.1 類似的 prompting 模式](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)，效果最好。

## 指令遵循
跟 GPT-4.1、GPT-5 一樣，如果指令互相衝突、含糊或不清楚，新的 realtime 模型表現會變差。

- **什麼時候用**：輸出偏離規則、跳過階段，或誤用 tool。
- **做什麼**：在上線前，用 LLM 指出含糊、衝突和缺少定義的地方。


### **指令品質 Prompt（可在 ChatGPT 或 API 使用）**

用下面這個 prompt 搭配 GPT-5，找出你的 prompt 裡有問題的地方再去修。

```
## Role & Objective  
You are a **Prompt-Critique Expert**.
Examine a user-supplied LLM prompt and surface any weaknesses following the instructions below.


## Instructions
Review the prompt that is meant for an LLM to follow and identify the following issues:
- Ambiguity: Could any wording be interpreted in more than one way?
- Lacking Definitions: Are there any class labels, terms, or concepts that are not defined that might be misinterpreted by an LLM?
- Conflicting, missing, or vague instructions: Are directions incomplete or contradictory?
- Unstated assumptions: Does the prompt assume the model has to be able to do something that is not explicitly stated?


## Do **NOT** list issues of the following types:
- Invent new instructions, tool calls, or external information. You do not know what tools need to be added that are missing.
- Issues that you are unsure about.


## Output Format
"""
# Issues
- Numbered list; include brief quote snippets.

# Improvements
- Numbered list; provide the revised lines you would change and how you would change them.

# Revised Prompt
- Revised prompt where you have applied all your improvements surgically with minimal edits to the original prompt
"""
```

### **Prompt 優化 Meta Prompt（可在 ChatGPT 或 API 使用）**

這個 meta-prompt 針對特定的失敗模式，協助你改進基礎 system prompt。提供目前的 prompt 並描述你看到的問題，模型（GPT-5）會建議改寫版本，收緊限制、減少該問題。

```
Here's my current prompt to an LLM:
[BEGIN OF CURRENT PROMPT]
{CURRENT_PROMPT}
[END OF CURRENT PROMPT]
 
But I see this issue happening from the LLM:
[BEGIN OF ISSUE]
{ISSUE}
[END OF ISSUE]
Can you provide some variants of the prompt so that the model can better understand the constraints to alleviate the issue?
```

## 沒有音訊或音訊不清楚
有時模型以為自己聽到了什麼，就試著回應。你可以加一條自訂指令，告訴模型聽到不清楚的音訊或使用者輸入時該怎麼做。依你的情境修改想要的行為（例如你可能不要模型要求澄清，而是重複同一個問題）。

- **什麼時候用**：背景雜音、不完整的字詞或靜音觸發了不必要的回覆。
- **做什麼**：阻止多餘的回應，並優雅地請對方澄清。
- **怎麼調整**：依情境選擇要請對方澄清，還是重複上一個問題。

### 範例（咳嗽和不清楚的音訊）
```
# Instructions/Rules
...


## Unclear audio 
- Always respond in the same language the user is speaking in, if unintelligible.
- Only respond to clear audio or text. 
- If the user's audio is not clear (e.g. ambiguous input/background noise/silent/unintelligible) or if you did not fully hear or understand the user, ask for clarification using {preferred_language} phrases.
```

這是用 `gpt-realtime` 套用指令**之後**的回應

```python
Audio("./data/audio/unclear_audio.mp3")
```
在這個範例裡，我大聲咳嗽（非常大聲）加上音訊不清楚，模型要求澄清。

## 背景音樂或聲音
偶爾模型在生成語音時，會產生非預期的背景音樂、哼唱、有節奏的雜音，或類似聲音的瑕疵。這些會降低清晰度、分散使用者注意，或讓助理顯得不夠專業。下面的指令可以預防或大幅減少這些情況。

- **什麼時候用**：在 Realtime 音訊回應裡觀察到非預期的音樂元素或音效時。
- **做什麼**：引導模型避免產生這些不想要的音訊瑕疵。
- **怎麼調整**：調整指令，明確壓制你遇到的特定聲音模式。

### 範例
```
# Instructions/Rules
...
- Do not include any sound effects or onomatopoeic expressions in your responses.
```

# Tools
這一段用來告訴模型怎麼使用你的 function 和 tool。要明確寫出什麼時候該呼叫、什麼時候不該呼叫、要收集哪些參數、呼叫進行中要說什麼，以及怎麼處理錯誤或部分結果。

## Tool 選擇
新的 Realtime 版本很會遵循指令。但這也表示，如果 prompt 裡的指令和模型預期的不一致，例如 prompt 提到沒有放進 tools 清單的 tool，就可能造成不好的回應。

- **什麼時候用**：prompt 提到實際上不存在的 tool。
- **做什麼**：檢查可用的 tool 和 system prompt 是否一致。

### 範例
```
# Tools
## lookup_account(email_or_phone)
...


## check_outage(address)
...
```

我們要確保 tool 清單有相同可用的 tool，而且**描述之間不互相矛盾**：

```json
[
{
    "name": "lookup_account",
    "description": "Retrieve a customer account using either an email or phone number to enable verification and account-specific actions.",
    "parameters": {
      ...
  },
{
    "name": "check_outage",
    "description": "Check for network outages affecting a given service address and return status and ETA if applicable.",
    "parameters": {
      ...
  }
]
```

## Tool Call Preamble
有些情境適合讓 Realtime 模型在呼叫 tool 的同時給出語音回應。這樣可以遮掉延遲，使用者體驗更好。你可以修改範例句子。


- **什麼時候用**：使用者需要在 tool call 的同時得到即時確認，有助於遮掉延遲。
- **做什麼**：在 tool call 之前加一句簡短、固定的 preamble。

### 範例
```
# Tools
- Before any tool call, say one short line like “I’m checking that now.” Then call the tool immediately.
```

這是用 `gpt-realtime` 套用指令後的回應

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/tool_proactive.png"
  style="width:800px; height:auto;"
/>

用了這個指令後，模型在呼叫 tool 的同時輸出語音回應 "I'm checking that right now"。

### Tool Call Preamble 加範例句子
如果想更仔細控制模型在呼叫 tool 的同時說出哪類句子，可以把範例句子加在 tool spec 的 description 裡。

#### 範例
```python
tools = [
  {
    "name": "lookup_account",
    "description": "Retrieve a customer account using either an email or phone number to enable verification and account-specific actions.

Preamble sample phrases:
- For security, I’ll pull up your account using the email on file.
- Let me look up your account by {email} now.
- I’m fetching the account linked to {phone} to verify access.
- One moment—I’m opening your account details."
    "parameters": {
      "..."
    }
  },
  {
    "name": "check_outage",
    "description": "Check for network outages affecting a given service address and return status and ETA if applicable.

Preamble sample phrases:
- I’ll check for any outages at {service_address} right now.
- Let me look up network status for your area.
- I’m checking whether there’s an active outage impacting your address.
- One sec—verifying service status and any posted ETA.",
    "parameters": {
      "..."
    }
  }
]

```

## 不用確認就呼叫 Tool
有時模型會在呼叫 tool 之前先要求確認。在某些情境，這會讓使用者體驗變差，因為模型不夠主動。

- **什麼時候用**：agent 在明顯該呼叫 tool 的時候還先問許可。
- **做什麼**：移除不必要的確認迴圈。

### 範例
```
# Tools
- When calling a tool, do not ask for any user confirmation. Be proactive
```

這是用 `gpt-realtime` 套用指令**之後**的回應

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/tool_no_confirm.png"
  style="width:800px; height:auto;"
/>

在這個範例中可以看到，realtime 模型沒有產生任何語音回應，直接呼叫了對應的 tool。

*提示：如果你發現模型太快跳去呼叫 tool，可以把措辭放軟。例如把 “proactive” 這種強烈的詞換成比較溫和的說法，能引導模型採取比較冷靜、不那麼急切的做法。*

## Tool Call 表現
當情境越來越複雜、可用的 tool 越來越多，明確引導模型什麼時候用每個 tool、同樣重要的是什麼時候不該用，就變得很關鍵。清楚的使用規則不只提升 tool call 的準確度，也幫助模型在對的時間選對的 tool。

- **什麼時候用**：模型的 tool call 表現不好，需要把指令寫得更明確以減少誤用。
- **做什麼**：為每個 tool 加上「何時用／何時避免」的指令。也可以加上 tool call 順序的指令（Tool call A 之後，可以呼叫 Tool call B 或 C）。

### 範例
```
# Tools
- When you call any tools, you must output at the same time a response letting the user know that you are calling the tool.

## lookup_account(email_or_phone)
Use when: verifying identity or viewing plan/outage flags.
Do NOT use when: the user is clearly anonymous and only asks general questions.


## check_outage(address)
Use when: user reports connectivity issues or slow speeds.
Do NOT use when: question is billing-only.


## refund_credit(account_id, minutes)
Use when: confirmed outage > 240 minutes in the past 7 days.
Do NOT use when: outage is unconfirmed; route to Diagnose → check_outage first.


## schedule_technician(account_id, window)
Use when: repeated failures after reboot and outage status = false.
Do NOT use when: outage status = true (send status + ETA instead).


## escalate_to_human(account_id, reason)
Use when: user seems very frustrated, abuse/harassment, repeated failures, billing disputes >$50, or user requests escalation.
```

*提示：如果某個 tool call 可能不可預期地失敗，要加上清楚的失敗處理指令，讓模型能優雅地回應。*

## Tool 層級的行為
你可以針對特定 tool 微調模型的行為，而不是套用單一的全域規則。例如你可能希望 READ 類 tool 主動呼叫，而 WRITE 類 tool 需要明確確認。

- **什麼時候用**：全域的主動性、確認或 preamble 指令，不適合每一個 tool。
- **做什麼**：加入每個 tool 各自的行為規則，定義模型該立刻呼叫、先確認，還是在呼叫前說一句 preamble。

### 範例
```
# TOOLS
- For the tools marked PROACTIVE: do not ask for confirmation from the user and do not output a preamble.
- For the tools marked as CONFIRMATION FIRST: always ask for confirmation to the user.
- For the tools marked as PREAMBLES: Before any tool call, say one short line like “I’m checking that now.” Then call the tool immediately.


## lookup_account(email_or_phone) — PROACTIVE
Use when: verifying identity or accessing billing.  
Do NOT use when: caller refuses to identify after second request.


## check_outage(address) — PREAMBLES
Use when: caller reports failed connection or speed lower than 10 Mbps.  
Do NOT use when: purely billing OR when internet speed is above 10 Mbps.  
If either condition applies, inform the customer you cannot assist and hang up.


## refund_credit(account_id, minutes) — CONFIRMATION FIRST
Use when: confirmed outage > 240 minutes in the past 7 days (credit 60 minutes).  
Do NOT use when: outage unconfirmed.  
Confirmation phrase: “I can issue a credit for this outage—would you like me to go ahead?”


## schedule_technician(account_id, window) — CONFIRMATION FIRST
Use when: reboot + line checks fail AND outage=false.  
Windows: “10am–12pm ET” or “2pm–4pm ET”.  
Confirmation phrase: “I can schedule a technician to visit—should I book that for you?”


## escalate_to_human(account_id, reason) — PREAMBLES
Use when: harassment, threats, self-harm, repeated failure, billing disputes > $50, caller is frustrated, or caller requests escalation.  
Preamble: “Let me connect you to a senior agent who can assist further.”
```

## Tool 輸出格式
有些 tool 輸出，尤其是必須逐字重複的長字串，對模型來說可能是 out-of-distribution。訓練時，tool 輸出通常長得像有具名欄位的 JSON 物件。如果你的 tool 回傳原始字串，又另外要求模型「照原樣重複」，模型比較容易改寫、截斷，或混進自己的開場白。

實用的解法是讓 tool 輸出看起來像一般的 tool 結果，並把「逐字」這個要求寫成機器看得懂的明確欄位。

* **什麼時候用：** tool 回傳**長或複雜的結構化內容**（多句指示、handoff 資料包、ID／連結、政策摘要、多步驟流程等），而你觀察到**截斷、改寫、欄位遺漏、順序被改，或模型混進自己的開場白／評論**。

* **做什麼：** 把 tool 輸出包進一個**小而明確的 JSON 外殼**（例如 `response_text` 加上 `require_repeat_verbatim`、`format` 或 `content_type` 之類的旗標），讓回應看起來更 **in-distribution**，預期的輸出行為也**對機器很清楚**。

* **怎麼調整：** schema 保持**精簡且穩定**。在你的 **Tools 指令**和 **tool 定義旁邊**，都清楚寫明預期的 tool 輸出形狀（例如「如果 `require_repeat_verbatim` 為 true，只輸出 `response_text`，其他什麼都不要加」，或「照原樣呈現 `response_text`；不要新增、省略或重排 tool 輸出的欄位」）。



### 範例

#### 範例：原始字串（比較容易出錯）

Tool 回傳：

```python
I just sent you an email with the verification link. Please open it and click “Confirm”.
```

模型有時會說：

- “I’ve emailed you a verification link…”（改寫）

- 漏掉最後一句（截斷）

- 加上多餘的評論（“Can I help with anything else?”）

#### 範例：包成 JSON（比較 in-distribution、比較可靠）
Tool 回傳：

```json
{
  "response_text": "I just sent you an email with the verification link. Please open it and click “Confirm”.",
  "require_repeat_verbatim": true
}
```

因為這看起來像典型的 tool 結果（JSON 物件），模型通常比較容易：

- 認出哪個是「權威」內容（response_text）

- 理解輸出的限制（require_repeat_verbatim）

- 乾淨地重現 tool 輸出，不截斷也不加多餘評論

## Rephrase Supervisor Tool（Responder-Thinker 架構）
很多語音架構裡，realtime 模型扮演 responder（跟使用者講話），更強的文字模型扮演 thinker（負責規劃、查政策、完成 SOP）。文字回覆不一定適合用說的，所以 responder 在產生音訊之前，必須先把 thinker 的文字改寫成適合語音的回應。


- **什麼時候用**：responder 收到 thinker 的回應後，說出來的內容聽起來很機械、太長或很彆扭。
- **做什麼**：加上清楚的指令，引導 responder 把 thinker 的文字改寫成簡短、自然、以口語為優先的回覆。
- **怎麼調整**：調整措辭風格、開頭和簡短程度的限制，符合你的預期。

### 範例
```
# Tools
## Supervisor Tool
Name: getNextResponseFromSupervisor(relevantContextFromLastUserMessage: string)


When to call:
- Any request outside the allow list.
- Any factual, policy, account, or process question.
- Any action that might require internal lookups or system changes.


When not to call:
- Simple greetings and basic chitchat.
- Requests to repeat or clarify.
- Collecting parameters for later Supervisor use:
  - phone_number for account help (getUserAccountInfo)
  - zip_code for store lookup (findNearestStore)
  - topic or keyword for policy lookup (lookupPolicyDocument)


Usage rules and preamble:
1) Say a neutral filler phrase to the user, then immediately call the tool. Approved fillers: “One moment.”, “Let me check.”, “Just a second.”, “Give me a moment.”, “Let me see.”, “Let me look into that.” Fillers must not imply success or failure.  
2) Do not mention the “Supervisor” when responding with filler phrase.
3) relevantContextFromLastUserMessage is a one-line summary of the latest user message; use an empty string if nothing salient.  
4) After the tool returns, apply Rephrase Supervisor and send your reply.


### Rephrase Supervisor
- Start with a brief conversational opener using active language, then flow into the answer (for example: “Thanks for waiting—”, “Just finished checking that.”, “I’ve got that pulled up now.”).  
- Keep it short: no more than 2 sentences.  
- Use this template: opener + one-sentence gist + up to 3 key details + a quick confirmation or choice (for example: “Does that match what you expected?”, “Want me to review options?”).  
- Read numbers for speech: money naturally (“$45.20” → “forty-five dollars and twenty cents”), phone numbers 3-3-4, addresses with individual digits, dates/times plainly (“August twelfth”, “three-thirty p.m.”).
```

這是沒有改寫指令的例子：

>Assistant: Your current credit card balance is positive at 32,323,232 AUD.

這是同樣的例子，加上改寫指令：

>Assistant: Just finished checking that—your credit card balance is thirty-two million three hundred twenty-three thousand two hundred thirty-two dollars in your favor. Your last payment was processed on August first. Does that match what you expected?

## 常用 Tool
新的模型版本已經訓練過，能有效使用下列常用 tool。如果你的情境需要類似行為，名稱、簽章和描述請盡量貼近這些，以提高可靠度並更 in-distribution。

以下是模型訓練過的幾個重要常用 tool：

### 範例
```
# answer(question: string)
Description: Call this when the customer asks a question that you don't have an answer to or asks to perform an action.


# escalate_to_human()
Description: Call this when a customer asks for escalation, or to talk to someone else, or expresses dissatisfaction with the call.


# finish_session()
Description: Call this when a customer says they're done with the session or doesn't want to continue. If it's ambiguous, confirm with the customer before calling. 
```

# 對話流程
這一段講怎麼把對話組織成清楚、以目標為導向的階段，讓模型清楚知道每一步該做什麼。它定義每個階段的目的、推進的指令，以及進入下一階段的具體「結束條件」。這樣可以避免模型卡住、跳步或搶先，讓對話從打招呼到解決問題都井然有序。

另外，把 prompt 組織成不同的對話狀態，也更容易找出錯誤模式、更有效地迭代。

- **什麼時候用**：對話感覺雜亂、還沒達成目標就停住，或模型很難有效完成目標。
- **做什麼**：把互動拆成階段，每個階段有明確的目標、指令和結束條件。
- **怎麼調整**：把階段改名以符合你的 workflow；修改每個階段的指令以符合預期行為；“Exit when” 要具體而精簡。

### 範例
```
# Conversation Flow
## 1) Greeting
Goal: Set tone and invite the reason for calling.
How to respond:
- Identify as NorthLoop Internet Support.
- Keep the opener brief and invite the caller’s goal.
- Confirm that customer is a Northloop customer
Exit to Discovery: Caller states they are a Northloop customer and mentions an initial goal or symptom.


## 2) Discover
Goal: Classify the issue and capture minimal details.
How to respond:
- Determine billing vs connectivity with one targeted question.
- For connectivity: collect the service address.
- For billing/account: collect email or phone used on the account.
Exit when: Intent and address (for connectivity) or email/phone (for billing) are known.


## 3) Verify
Goal: Confirm identity and retrieve the account.
How to respond:
- Once you have email or phone, call lookup_account(email_or_phone).
- If lookup fails, try the alternate identifier once; otherwise proceed with general guidance or offer escalation if account actions are required.
Exit when: Account ID is returned.


## 4) Diagnose
Goal: Decide outage vs local issue.
How to respond:
- For connectivity, call check_outage(address).
- If outage=true, skip local steps; move to Resolve with outage context.
- If outage=false, guide a short reboot/cabling check; confirm each step’s result before continuing.
Exit when: Root cause known.


## 5) Resolve
Goal: Apply fix, credit, or appointment.
How to respond:
- If confirmed outage > 240 minutes in the last 7 days, call refund_credit(account_id, 60).
- If outage=false and issue persists after basic checks, offer “10am–12pm ET” or “2pm–4pm ET” and call schedule_technician(account_id, chosen window).
- If the local fix worked, state the result and next steps briefly.
Exit when: A fix/credit/appointment has been applied and acknowledged by the caller.


## 6) Confirm/Close
Goal: Confirm outcome and end cleanly.
How to respond:
- Restate the result and any next step (e.g., stabilization window or tech ETA).
- Invite final questions; close politely if none.
Exit when: Caller declines more help.
```

## 範例句子
範例句子是模型的「錨點範例」。它們展示你想要的風格、簡短程度和語氣，又不會把模型鎖死在單一個固定回應。

- **什麼時候用**：回應缺少你的品牌風格，或不一致。
- **做什麼**：提供模型可以變化使用的範例句子，保持自然簡短。
- **怎麼調整**：換成符合品牌的範例；保留 “do not always use” 這個警告。

### 範例
```
# Sample Phrases
- Below are sample examples that you should use for inspiration. DO NOT ALWAYS USE THESE EXAMPLES, VARY YOUR RESPONSES.

Acknowledgements: “On it.” “One moment.” “Good question.”
Clarifiers: “Do you want A or B?” “What’s the deadline?”
Bridges: “Here’s the quick plan.” “Let’s keep it simple.”
Empathy (brief): “That’s frustrating—let’s fix it.”
Closers: “Anything else before we wrap?” “Happy to help next time.”
```

*備註：如果你的語音系統最後一直只重複範例句子，讓語音體驗更機械，可以試著加上 Variety 限制。我們看過這樣能解決問題。*

## 對話流程加範例句子
在不同的對話流程狀態裡加入範例句子，教模型好的回應長什麼樣，是很有用的模式：


### 範例
```
# Conversation Flow
## 1) Greeting
Goal: Set tone and invite the reason for calling.
How to respond:
- Identify as NorthLoop Internet Support.
- Keep the opener brief and invite the caller’s goal.
Sample phrases (do not always repeat the same phrases, vary your responses):
- “Thanks for calling NorthLoop Internet—how can I help today?”
- “You’ve reached NorthLoop Support. What’s going on with your service?”
- “Hi there—tell me what you’d like help with.”
Exit when: Caller states an initial goal or symptom.


## 2) Discover
Goal: Classify the issue and capture minimal details.
How to respond:
- Determine billing vs connectivity with one targeted question.
- For connectivity: collect the service address.
- For billing/account: collect email or phone used on the account.
Sample phrases (do not always repeat the same phrases, vary your responses):
- “Is this about your bill or your internet speed?”
- “What address are you using for the connection?”
- “What’s the email or phone number on the account?”
Exit when: Intent and address (for connectivity) or email/phone (for billing) are known.


## 3) Verify
Goal: Confirm identity and retrieve the account.
How to respond:
- Once you have email or phone, call lookup_account(email_or_phone).
- If lookup fails, try the alternate identifier once; otherwise proceed with general guidance or offer escalation if account actions are required.
Sample phrases:
- “Thanks—looking up your account now.”
- “If that doesn’t pull up, what’s the other contact—email or phone?”
- “Found your account. I’ll take care of this.”
Exit when: Account ID is returned.


## 4) Diagnose
Goal: Decide outage vs local issue.
How to respond:
- For connectivity, call check_outage(address).
- If outage=true, skip local steps; move to Resolve with outage context.
- If outage=false, guide a short reboot/cabling check; confirm each step’s result before continuing.
Sample phrases (do not always repeat the same phrases, vary your responses):
- “I’m running a quick outage check for your area.”
- “No outage reported—let’s try a fast modem reboot.”
- “Please confirm the modem lights: is the internet light solid or blinking?”
Exit when: Root cause known.


## 5) Resolve
Goal: Apply fix, credit, or appointment.
How to respond:
- If confirmed outage > 240 minutes in the last 7 days, call refund_credit(account_id, 60).
- If outage=false and issue persists after basic checks, offer “10am–12pm ET” or “2pm–4pm ET” and call schedule_technician(account_id, chosen window).
- If the local fix worked, state the result and next steps briefly.
Sample phrases (do not always repeat the same phrases, vary your responses):
- “There’s been an extended outage—adding a 60-minute bill credit now.”
- “No outage—let’s book a technician. I can do 10am–12pm ET or 2pm–4pm ET.”
- “Credit applied—you’ll see it on your next bill.”
Exit when: A fix/credit/appointment has been applied and acknowledged by the caller.


## 6) Confirm/Close
Goal: Confirm outcome and end cleanly.
How to respond:
- Restate the result and any next step (e.g., stabilization window or tech ETA).
- Invite final questions; close politely if none.
Sample phrases (do not always repeat the same phrases, vary your responses):
- “We’re all set: [credit applied / appointment booked / service restored].”
- “You should see stable speeds within a few minutes.”
- “Your technician window is 10am–12pm ET.”
Exit when: Caller declines more help.

```

## 進階對話流程

當情境越來越複雜，你需要一種能擴充、又能讓模型保持有效的結構。關鍵是在可維護性和簡單之間取得平衡：太多僵硬的狀態會讓模型負擔過重，傷害表現，也讓對話聽起來很機械。

比較好的做法是設計能降低模型感受複雜度的流程。用結構化但有彈性的方式處理狀態，模型比較容易保持專注、反應靈活，使用者體驗也會更好。

管理複雜情境有兩種常見模式：
1. 把對話流程做成 State Machine
2. 透過 session.updates 動態改變對話流程


### 把對話流程做成 State Machine
把對話定義成一個 JSON 結構，同時編碼狀態和轉換。這樣容易推敲涵蓋範圍、找出邊界情況，並隨時間追蹤變更。因為它是以程式碼形式存放，你可以做版本管理、diff，並隨流程演進擴充。State machine 也讓你能細緻控制對話從一個狀態轉到另一個狀態的確切方式和時機。

#### 範例
```json
# Conversation States
[
  {
    "id": "1_greeting",
    "description": "Begin each conversation with a warm, friendly greeting, identifying the service and offering help.",
    "instructions": [
        "Use the company name 'Snowy Peak Boards' and provide a warm welcome.",
        "Let them know upfront that for any account-specific assistance, you’ll need some verification details."
    ],
    "examples": [
      "Hello, this is Snowy Peak Boards. Thanks for reaching out! How can I help you today?"
    ],
    "transitions": [{
      "next_step": "2_get_first_name",
      "condition": "Once greeting is complete."
    }, {
      "next_step": "3_get_and_verify_phone",
      "condition": "If the user provides their first name."
    }]
  },
  {
    "id": "2_get_first_name",
    "description": "Ask for the user’s name (first name only).",
    "instructions": [
      "Politely ask, 'Who do I have the pleasure of speaking with?'",
      "Do NOT verify or spell back the name; just accept it."
    ],
    "examples": [
      "Who do I have the pleasure of speaking with?"
    ],
    "transitions": [{
      "next_step": "3_get_and_verify_phone",
      "condition": "Once name is obtained, OR name is already provided."
    }]
  },
  {
    "id": "3_get_and_verify_phone",
    "description": "Request phone number and verify by repeating it back.",
    "instructions": [
      "Politely request the user’s phone number.",
      "Once provided, confirm it by repeating each digit and ask if it’s correct.",
      "If the user corrects you, confirm AGAIN to make sure you understand.",
    ],
    "examples": [
      "I'll need some more information to access your account if that's okay. May I have your phone number, please?",
      "You said 0-2-1-5-5-5-1-2-3-4, correct?",
      "You said 4-5-6-7-8-9-0-1-2-3, correct?"
    ],
    "transitions": [{
      "next_step": "4_authentication_DOB",
      "condition": "Once phone number is confirmed"
    }]
  },
...
```

### 動態對話流程
在這個模式裡，對話會根據目前的狀態，即時更新 system prompt 和 tool 清單來調整。與其一次把所有可能的規則和 tool 都丟給模型，不如只提供和目前對話階段相關的部分。
當一個狀態的結束條件達成時，用 session.update 切換，把 prompt 和 tool 換成下一階段需要的。

這個做法降低模型的認知負擔，讓它處理複雜任務時不會被不必要的 context 干擾。


#### 範例

```python
from typing import Dict, List, Literal

State = Literal["verify", "resolve"]

# Allowed transitions
TRANSITIONS: Dict[State, List[State]] = {
    "verify": ["resolve"],
    "resolve": []  # terminal
}

def build_state_change_tool(current: State) -> dict:
    allowed = TRANSITIONS[current]
    readable = ", ".join(allowed) if allowed else "no further states (terminal)"
    return {
        "type": "function",
        "name": "set_conversation_state",
        "description": (
            f"Switch the conversation phase. Current: '{current}'. "
            f"You may switch only to: {readable}. "
            "Call this AFTER exit criteria are satisfied."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "next_state": {"type": "string", "enum": allowed}
            },
            "required": ["next_state"]
        }
    }

# Minimal business tools per state
TOOLS_BY_STATE: Dict[State, List[dict]] = {
    "verify": [{
        "type": "function",
        "name": "lookup_account",
        "description": "Fetch account by email or phone.",
        "parameters": {
            "type": "object",
            "properties": {"email_or_phone": {"type": "string"}},
            "required": ["email_or_phone"]
        }
    }],
    "resolve": [{
        "type": "function",
        "name": "schedule_technician",
        "description": "Book a technician visit.",
        "parameters": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
                "window": {"type": "string", "enum": ["10-12 ET", "14-16 ET"]}
            },
            "required": ["account_id", "window"]
        }
    }]
}

# Short, phase-specific instructions
INSTRUCTIONS_BY_STATE: Dict[State, str] = {
    "verify": (
        "# Role & Objective\n"
        "Verify identity to access the account.\n\n"
        "# Conversation (Verify)\n"
        "- Ask for the email or phone on the account.\n"
        "- Read back digits one-by-one (e.g., '4-1-5… Is that correct?').\n"
        "Exit when: Account ID is returned.\n"
        "When exit is satisfied: call set_conversation_state(next_state=\"resolve\")."
    ),
    "resolve": (
        "# Role & Objective\n"
        "Apply a fix by booking a technician.\n\n"
        "# Conversation (Resolve)\n"
        "- Offer two windows: '10–12 ET' or '2–4 ET'.\n"
        "- Book the chosen window.\n"
        "Exit when: Appointment is confirmed.\n"
        "When exit is satisfied: end the call politely."
    )
}

def build_session_update(state: State) -> dict:
    """Return the JSON payload for a Realtime `session.update` event."""
    return {
        "type": "session.update",
        "session": {
            "instructions": INSTRUCTIONS_BY_STATE[state],
            "tools": TOOLS_BY_STATE[state] + [build_state_change_tool(state)]
        }
    }
```

# 安全與升級
Realtime 語音 agent 常常需要一個可靠的方式把對話升級給真人。在這一段，你要依自己的情境，修改「什麼時候」該升級的指令。

- **什麼時候用**：模型很難判斷什麼時候該適當地升級給真人或備援系統。
- **做什麼**：定義快速、可靠的升級方式，以及要說什麼。
- **怎麼調整**：放入你自己的門檻，以及模型該說的話。

### 範例
```
# Safety & Escalation
When to escalate (no extra troubleshooting):
- Safety risk (self-harm, threats, harassment)
- User explicitly asks for a human
- Severe dissatisfaction (e.g., “extremely frustrated,” repeated complaints, profanity)
- **2** failed tool attempts on the same task **or** **3** consecutive no-match/no-input events
- Out-of-scope or restricted (e.g., real-time news, financial/legal/medical advice)

What to say at the same time of calling the escalate_to_human tool (MANDATORY):
- “Thanks for your patience—I’m connecting you with a specialist now.”
- Then call the tool: `escalate_to_human`

Examples that would require escalation:
- “This is the third time the reset didn’t work. Just get me a person.”
- “I am extremely frustrated!”
```

這是我們舊版模型 `gpt-4o-realtime-preview-2025-06-03` 使用這個指令的對話回應。

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/escalate_06.png"
  style="width:800px; height:auto;"
/>

這是我們新的 GA 模型 `gpt-realtime` 使用這個指令的對話回應。

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/escalate_07.png"
  style="width:800px; height:auto;"
/>

新的 realtime 模型更能遵循指令，也更可靠地升級給真人。

## 重點整理

- Realtime 的 system prompt 要用有標籤的短區段加條列，每段只管一件事；指令含糊或互相衝突，表現會明顯變差。
- `speed` 參數只改播放速率，要讓聲音真的變快，得在 prompt 裡寫節奏和簡短程度的指令。
- 範例句子會被緊緊跟著，所以要搭配 Variety 規則，避免回應變成機器人。
- Tool 的行為可以全域設定，也可以每個 tool 各自設定（READ 主動、WRITE 先確認）；tool 清單和 prompt 提到的 tool 必須一致。
- 對話複雜時，用 state machine 或 `session.update` 動態換 prompt 和 tool，降低模型每一刻要處理的規則量。

## 練習

1. 挑一個你自己的語音 agent prompt，把 `IF x > 3 THEN ESCALATE` 這類寫法改成文字規則，並加一條 Variety 規則，比較前後的回應。
2. 照「Tool 輸出格式」的做法，把一個回傳長字串的 tool 改成回傳 `{"response_text": ..., "require_repeat_verbatim": true}`，並在 Tools 指令寫出對應規則，看逐字複誦有沒有變穩。
3. 把一個三階段的對話流程（例如驗證、查詢、結案）改寫成 JSON state machine，再用 `session.update` 在每個階段結束條件達成時，換成該階段專用的 prompt 和 tool 清單。
