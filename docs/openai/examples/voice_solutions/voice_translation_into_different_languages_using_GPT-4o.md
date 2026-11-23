---
translated: true
source: examples/voice_solutions/voice_translation_into_different_languages_using_GPT-4o.ipynb
---
# Voice Translation into Different Languages

> 原文：[examples/voice_solutions/voice_translation_into_different_languages_using_GPT-4o.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/voice_translation_into_different_languages_using_GPT-4o.ipynb)



## 這篇在做什麼

用 GPT-4o 的 audio-in、audio-out 能力，把一段英文音檔直接配音成印地語，一次 API 呼叫就好。後面再用 BLEU 和 ROUGE 評估翻譯品質。

## 學完你會

- 寫一個把 base64 音檔送進 `gpt-4o-audio-preview` 的函式，並依 output modality 拿到文字或音訊。
- 一次呼叫就同時拿到目標語言的逐字稿和配音音檔。
- 把配音結果轉寫回原語言，用 BLEU、ROUGE 算分，並知道分數不好時該調哪裡。

## 開跑前

- 設好 `OPENAI_API_KEY` 環境變數。
- 需要有一個 WAV 音檔，跟 code cell 裡用到的套件（例如播放用的 `pydub`）。

### 用 GPT-4o 做音檔的語音翻譯

有沒有想過把 podcast 翻成自己的母語？翻譯並配音能讓音訊內容被全世界更多人接觸。有了 GPT-4o 新的 audio-in 和 audio-out 模態，這件事變得比以往簡單。

這份指南會帶你用 OpenAI 的 GPT-4o audio modality API，把一個英文音檔翻成印地語。

GPT-4o 簡化了音訊內容的配音流程。以前你得先把音訊轉成文字，再翻成目標語言，再轉回音訊。現在有了 GPT-4o 的 voice-to-voice 能力，輸入音訊、輸出音訊，一步就搞定。

先說明一下這份 cookbook 裡「**語言（Language）**」和書寫「**文字系統（Script）**」的用法。這兩個詞常被混用，但在這個任務裡要分清楚。

**- Language** 指的是口說或書寫的溝通系統。例如印地語和馬拉地語是不同的語言，但都用天城文（Devanagari）書寫。同樣地，英語和法語是不同語言，但都用拉丁字母書寫。

**- Script** 指的是用來書寫某個語言的字元或符號集合。例如塞爾維亞語傳統上用西里爾字母書寫，也會用拉丁字母書寫。


GPT-4o 的 audio-in、audio-out 讓你只要一次 API 呼叫，就能把音訊從一種語言配音成另一種。

**1. 轉寫（Transcribe）**：用 GPT-4o 把來源音檔轉成來源語言的文字。如果你已經有來源音訊的逐字稿，可以跳過這步。

**2. 配音（Dub）**：直接把音檔從來源語言配成目標語言。

**3. 取得翻譯 benchmark**：用 BLEU 或 ROUGE。

**4. 解讀並改善**：依分數調整步驟 1 到 3 的 prompt 參數。


開始之前，請確認你已經把 OpenAI API key 設成環境變數，並照下面 code cell 的說明裝好需要的套件。

### Step 1：用 GPT-4o 把音訊轉成來源語言的文字

先寫一個函式，用 chat completions API endpoint 把音檔送到 OpenAI 的 GPT-4o API 處理。

`process_audio_with_gpt_4o` 函式接收三個輸入：

1. 一個 base64 編碼的音檔（base64_encoded_audio），會送給 GPT-4o 模型。
2. 想要的輸出模態（例如 text，或 text 加 audio）。
3. 一個 system prompt，指示模型怎麼處理輸入。

這個函式會對 OpenAI 的 chat/completions endpoint 發出 API 請求。request header 帶有授權用的 API key。data payload 包含模型類型（`gpt-4o-audio-preview`）、選擇的輸出模態，以及音訊細節，例如聲音類型和格式（這裡是 "alloy" 和 "wav"）。payload 也把 system prompt 和 base64 編碼的音檔放在 "user" 訊息裡。如果 API 請求成功（HTTP 200），就回傳 JSON 回應；如果出錯（非 200），就印出錯誤碼和訊息。

這個函式讓你能透過 OpenAI 的 GPT-4o API 做音訊處理，依輸入內容完成配音、轉寫或翻譯等任務。

```python
# Make sure requests package is installed  
import requests 
import os
import json

# Load the API key from the environment variable
api_key = os.getenv("OPENAI_API_KEY")


def process_audio_with_gpt_4o(base64_encoded_audio, output_modalities, system_prompt):
    # Chat Completions API end point 
    url = "https://api.openai.com/v1/chat/completions"

    # Set the headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    # Construct the request data
    data = {
        "model": "gpt-4o-audio-preview",
        "modalities": output_modalities,
        "audio": {
            "voice": "alloy",
            "format": "wav"
        },
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": base64_encoded_audio,
                            "format": "wav"
                        }
                    }
                ]
            }
        ]
    }
    
    request_response = requests.post(url, headers=headers, data=json.dumps(data))
    if request_response.status_code == 200:
        return request_response.json()
    else:  
        print(f"Error {request_response.status_code}: {request_response.text}")
        return
```

用 `process_audio_with_gpt_4o` 函式，我們先取得來源音訊的英文逐字稿。如果你已經有來源語言的逐字稿，可以跳過這步。

這一步我們做的事：
1. 讀取 WAV 檔並轉成 base64 編碼。
2. 把 output modality 設成 ["text"]，因為我們只需要文字逐字稿。
3. 提供 system prompt，指示模型專注轉寫語音，忽略掌聲之類的背景雜音。
4. 呼叫 process_audio_with_gpt_4o 函式處理音訊並回傳逐字稿。

```python
import base64
audio_wav_path = "./sounds/keynote_recap.wav"

# Read the WAV file and encode it to base64
with open(audio_wav_path, "rb") as audio_file:
    audio_bytes = audio_file.read()
    english_audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

modalities = ["text"]
prompt = "The user will provide an audio file in English. Transcribe the audio to English text, word for word. Only provide the language transcription, do not include background noises such as applause. "

response_json = process_audio_with_gpt_4o(english_audio_base64, modalities, prompt)

english_transcript = response_json['choices'][0]['message']['content']

print(english_transcript)
```

??? note "輸出"

    ```text
    Hello and welcome to our first ever OpenAI DevDay. Today, we are launching a new model, GPT-4 Turbo. GPT-4 Turbo supports up to 128,000 tokens of context. We have a new feature called JSON mode, which ensures that the model will respond with valid JSON. You can now call many functions at once. And it will do better at following instructions in general. You want these models to be able to access better knowledge about the world, so do we. So we're launching retrieval in the platform. You can bring knowledge from outside documents or databases into whatever you're building. GPT-4 Turbo has knowledge about the world up to April of 2023, and we will continue to improve that over time. DALL-E 3, GPT-4 Turbo with Vision, and the new text-to-speech model are all going into the API today. Today, we're launching a new program called Custom Models. With Custom Models, our researchers will work closely with a company to help them make a great custom model, especially for them and their use case using our tools. Higher rate limits. We're doubling the tokens per minute for all of our established GPT-4 customers so that it's easier to do more, and you'll be able to request changes to further rate limits and quotas directly in your API account settings. And GPT-4 Turbo is considerably cheaper than GPT-4, by a factor of 3x for prompt tokens and 2x for completion tokens starting today. We're thrilled to introduce GPTs. GPTs are tailored versions of ChatGPT for a specific purpose. And because they combine instructions, expanded knowledge, and actions, they can be more helpful to you. They can work better in many contexts, and they can give you better control. We know that many people who want to build a GPT don't know how to code. We've made it so that you can program the GPT just by having a conversation. You can make private GPTs. You can share your creations publicly with a link for anyone to use. Or, if you're on ChatGPT Enterprise, you can make GPTs just for your company. And later this month, we're going to launch the GPT Store. So those are GPTs, and we can't wait to see what you'll build. We're bringing the same concept to the API. The Assistant API includes persistent threads so they don't have to figure out how to deal with long conversation history, built-in retrieval, code interpreter, a working Python interpreter in a sandbox environment, and, of course, the improved function calling. As intelligence gets integrated everywhere, we will all have superpowers on demand. We're excited to see what you all will do with this technology and to discover the new future that we're all going to architect together. We hope when you come back next year, what we launch today is going to look very quaint relative to what we're busy creating for you now. Thank you for all you do. Thanks for coming here today.
    ```

這份英文逐字稿會當作 ground truth，在 Step 3 拿來對印地語配音做 benchmark。

### Step 2：用 GPT-4o 把音訊從來源語言配音成目標語言

用 GPT-4o，我們可以一次 API 呼叫，直接把音檔從英文配成印地語，同時拿到印地語逐字稿。做法是把 output modality 設成 `["text", "audio"] `

```python
glossary_of_terms_to_keep_in_original_language = "Turbo, OpenAI, token, GPT, Dall-e, Python"

modalities = ["text", "audio"]
prompt = f"The user will provide an audio file in English. Dub the complete audio, word for word in Hindi. Keep certain words in English for which a direct translation in Hindi does not exist such as  ${glossary_of_terms_to_keep_in_original_language}."

response_json = process_audio_with_gpt_4o(english_audio_base64, modalities, prompt)

message = response_json['choices'][0]['message']
```

下面的程式會從 GPT-4o 的回應取出印地語逐字稿和配音音訊。以前這會是多步驟流程，要好幾次 API 呼叫，先轉寫、再翻譯、最後產生目標語言的音訊。現在用 GPT-4o，一次 API 呼叫就能完成。

```python
# Make sure pydub is installed 
from pydub import AudioSegment
from pydub.playback import play
from io import BytesIO

# Get the transcript from the model. This will vary depending on the modality you are using. 
hindi_transcript = message['audio']['transcript']

print(hindi_transcript)

# Get the audio content from the response 
hindi_audio_data_base64 = message['audio']['data']
```

??? note "輸出"

    ```text
    स्वागत है हमारे पहले OpenAI DevDay में।

    आज हम एक नए मॉडल का लॉन्च कर रहे हैं, GPT-4 Turbo। GPT-4 Turbo अब 1,28,000 टोकens के कॉन्टेक्स्ट को सपोर्ट करता है। हमारे पास एक नया फीचर है जिसे JSON मोड कहा जाता है, जो सुनिश्चित करता है कि मॉडल वैध JSON के साथ प्रतिक्रिया करेगा। अब आप कई फंक्शन्स को एक साथ कॉल कर सकते हैं। और ये सामान्य रूप से इंस्ट्रक्शंस का पालन करने में बेहतर करेगा। आप चाहते हैं कि ये मॉडल दुनिया के बारे में बेहतर जानकारी तक पहुंच सकें, हम भी। इसलिए हम प्लैटफॉर्म में Retrieval लॉन्च कर रहे हैं। आप बाहरी दस्तावेज़ या डेटाबेस से जो भी आप बना रहे हैं, उसमें ज्ञान ला सकते हैं। GPT-4 Turbo को अप्रैल 2023 तक की दुनिया की जानकारी है, और हम इसे समय के साथ और बेहतर बनाना जारी रखेंगे। DALL·E 3, GPT-4 Turbo with vision, और नया Text-to-Speech मॉडल सभी को आज उपलब्ध कर रहे हैं एपीआई में। आज हम एक नए प्रोग्राम का लॉन्च कर रहे हैं जिसे Custom Models कहा जाता है। Custom Models के साथ, हमारे शोधकर्ता एक कंपनी के साथ निकटता से काम करेंगे ताकि वे एक महान Custom Model बना सकें, विशेष रूप से उनके और उनके उपयोग के मामले के लिए, हमारे Tools का उपयोग करके। उच्च दर लिमिट्स, हम सभी मौजूदा GPT-4 ग्राहकों के लिए Tokens प्रति मिनट को दोगुना कर रहे हैं ताकि अधिक करना आसान हों। और आप अपने एपीआई खाता सेटिंग्स में सीधे दर की सीमाओं और कोटों में बदलाव के लिए अनुरोध कर सकेंगे। और GPT-4 Turbo जीपीटी-4 की तुलना में काफी सस्ता है; प्रॉम्प्ट टोकन्स के लिए 3x और कम्पलीटेशन टोकन्स के लिए 2x से, आज से।

    हम जीपीटीस पेश कर रहे हैं। GPTs चैट GPT के कस्टमाइज़्ड संसकरण हैं, एक विशिष्ट उद्देश्य के लिए। और क्योंकि वे इंस्ट्रक्शंस, विस्तारित ज्ञान, और कार्रवाइयों को जोड़ते हैं, वे आपके लिए अधिक मददगार हो सकते हैं। वे कई सामाजीक उपयोग में बेहतर काम कर सकते हैं और आपको बेहतर नियंत्रण दे सकते हैं। हम जानते हैं कि कई लोग जो GPT बनाना चाहते हैं, उन्हें कोडिंग का ज्ञान नहीं है। हमने इसे एसे बनाया है कि आप GPT को केवल एक बातचीत से प्रोग्राम कर सकते हैं। आप प्राइवेट GPT बना सकते हैं। आप अपनी creation को किसी भी के लिए उपयोग करने के लिए लिंक के साथ सार्वजनिक रूप से शेयर कर सकते हैं। या, अगर आप ChatGPT एंटरप्राइज पर हैं, तो आप केवल अपनी कंपनी के लिए GPT बना सकते हैं। और इस महीने के बाद में हम GPT स्टोर लॉन्च करेंगे। तो ये हैं GPTs, और हम उत्सुक हैं देखने के लिए कि आप क्या बनाएंगे।

    हम एपीआई में वही संस्कल्पना ला रहे हैं। सहायक एपीआई में persistent threads शामिल हैं, ताकि उन्हें लंबी बातचीत के इतिहास से निपटने का तरीका पता न करना पड़े। बिल्ट-इन Retrieval, कोड इंटरप्रेटर, एक काम करने वाला Python इंटरप्रेटर एक सैंडबॉक्स वातावरण में, और of course, सुधरा हुआ फंक्शन कॉलिंग भी शामिल है।

    जैसे-जैसे बुद्धिमत्ता हर जगह एकीकृत होती जाएगी, हम सभी के पास मांग पर सुपर पावर्स होंगे। हम देखने के लिए उत्साहित हैं कि आप सब इस तकनीक के साथ क्या कर पाएंगे और उस नए भविष्य की खोज, जिसे हम सब मिलकर बनाने वाले हैं।

    हम आशा करते हैं कि आप अगले साल फिर आएंगे क्योंकि आज हमने जो लॉन्च किया है, वह उस परिप्रेक्ष्य से बहुत मामूली लगेगा जो हम अब आपके लिए बना रहे हैं। आप सभी के तरीके लिए धन्यवाद। आज यहां आने के लिए धन्यवाद।
    ```

轉出來的文字是印地語和英語混合，各自用自己的文字系統表示：印地語用天城文，英語用拉丁字母。這樣做能讓兩種語言的字都唸得正確，聽起來比較自然。我們用 `pydub` 模組來播放音訊，程式如下。

```python
# Play the audio 
audio_data_bytes = base64.b64decode(hindi_audio_data_base64)
audio_segment = AudioSegment.from_file(BytesIO(audio_data_bytes), format="wav")

play(audio_segment)
```

### Step 3：取得翻譯 benchmark（例如 BLEU 或 ROUGE）

我們可以用 BLEU 和 ROUGE 這類評估指標，把翻譯文字和參考譯文比較，來評估翻譯品質。

**BLEU (Bilingual Evaluation Understudy)**：衡量候選譯文和參考譯文之間 n-gram 的重疊程度。分數範圍 0 到 100，越高代表品質越好。

**ROUGE (Recall-Oriented Understudy for Gisting Evaluation)**：常用在摘要評估。衡量候選文字和參考文字之間 n-gram 的重疊，以及最長共同子序列。

理想上，要準確評估需要一份參考譯文（人工翻譯的版本）。不過要建立這種評估不容易，因為需要精通兩種語言的雙語人員花時間花力氣。

另一個做法是把目標語言的輸出音檔轉寫回原語言，再用 GPT-4o 來評估翻譯品質。

```python
# Translate the audio output file generated by the model back into English and compare with the reference text 
modalities = ["text"]
prompt = "The user will provide an audio file in Hindi. Transcribe the audio to English text word for word. Only provide the language transcription, do not include background noises such as applause. "

response_json = process_audio_with_gpt_4o(hindi_audio_data_base64, modalities, prompt)

re_translated_english_text = response_json['choices'][0]['message']['content']

print(re_translated_english_text)
```

??? note "輸出"

    ```text
    Welcome to our first OpenAI Dev Day. Today we are launching a new model, GPT-4 Turbo. GPT-4 Turbo now supports a context of 128,000 tokens. We have a new feature called JSON mode where the model will respond via JSON. Now you can call multiple functions simultaneously, and it will generally follow instructions better. You want this model to access external knowledge databases or documents to bring knowledge into what you are building. GPT-4 Turbo has knowledge of the world up to April 2023, and we'll continue to improve it over time.

    DALL·E 3, GPT-4 Turbo with vision, and the new text-to-speech model are all being made available today in the API. Today, we are launching a new program called custom models. Custom models will work closely to make great custom models specifically for you and your use case. Utilizing our tools, we are doubling the rate limits for all existing GPT-4 customers to tokens per minute. You'll be able to directly request rate limit and quota changes in your API account settings.

    And GPT-4 Turbo is much cheaper compared to GPT-4, 2x for completion tokens starting today. We are introducing GPTs. GPTs are custom versions of ChatGPT for a specific purpose, and since they incorporate instructions with broad knowledge and action capabilities, they can help you more. They can perform better in many social tasks. We know that many people who want to build GPTs don't know how to code. We've built it so that you can program a GPT with just one line.

    You can create a private GPT. You can publish your creation publicly with a link for anyone to use, or if you have ChatGPT Enterprise, you can build GPTs just for your own company. We will be launching a GPT store. So that's GPTs, and we're excited to see what you build. We're bringing customization into the API. Assistance API includes persistent threads so that it doesn't have to figure out how to engage with history from long conversations. A built-in retriever, code interpreter, a working Python interpreter in a sandbox environment, and of course, improved function calling. As intelligence integrates everywhere, we'll all have superpowers on demand.

    We're excited to see what you'll be able to build with this technology and explore this new future that we're all creating together. We hope you come back next year because what we're building for you now will make today seem very humble in that context. Thank you all for your approach. Thank you for being here today.
    ```

拿到從印地語音訊轉回英文文字的結果後，就可以跟原本的英文逐字稿比較，跑評估指標。

```python
# Make sure scarebleu package is installed 
import sacrebleu
# Make sure rouge-score package is installed 
from rouge_score import rouge_scorer 

# We'll use the original English transcription as the reference text 
reference_text = english_transcript

candidate_text = re_translated_english_text

# BLEU Score Evaluation
bleu = sacrebleu.corpus_bleu([candidate_text], [[reference_text]])
print(f"BLEU Score: {bleu.score}")

# ROUGE Score Evaluation
scorer = rouge_scorer.RougeScorer(['rouge1', 'rougeL'], use_stemmer=True)
scores = scorer.score(reference_text, candidate_text)
print(f"ROUGE-1 Score: {scores['rouge1'].fmeasure}")
print(f"ROUGE-L Score: {scores['rougeL'].fmeasure}")
```

??? note "輸出"

    ```text
    BLEU Score: 35.27656890256424
    ROUGE-1 Score: 0.8148148148148149
    ROUGE-L Score: 0.6934156378600822
    ```

### Step 4：解讀分數，並依需要調整步驟 1 到 3 的 prompt 參數

這個例子裡，BLEU 和 ROUGE 的分數都顯示語音翻譯的品質介於非常好到優秀之間。

**BLEU 分數怎麼解讀：** 雖然沒有通用的標準，一種常見的解讀如下：

0 到 10：品質差，有明顯錯誤、不流暢。

10 到 20：品質低，部分能懂，但錯誤很多。

20 到 30：普通，能傳達大致意思，但不夠精確流暢。

30 到 40：好，能懂也相對準確，只有小錯誤。

40 到 50：非常好，準確流暢，幾乎沒錯。

50 以上：優秀，非常接近人工翻譯。

**ROUGE 分數怎麼解讀：** 「好」的 ROUGE 分數會因任務、資料集和領域而不同。下面的準則可以當作好結果的參考：

ROUGE-1（unigram 重疊）：對 abstractive summarization 任務，0.5 到 0.6 通常算好。

ROUGE-L（最長共同子序列）：0.4 到 0.5 左右通常算好，代表模型能抓到參考文字的結構。

如果你的翻譯分數不理想，可以想想下面的問題：

#### 1. 來源音訊有沒有被正確轉寫？
如果逐字稿有錯，例如把發音相近的字搞混，你可以在 Step 1 的 system prompt 裡提供一份這類詞彙的 glossary，幫模型避開誤解，正確轉寫特定術語。

#### 2. 來源音訊有沒有文法錯誤？
如果來源音訊有文法錯誤，可以加一個後處理步驟，用 GPT 模型修正逐字稿，去掉文法錯誤並加上適當標點。之後不用 GPT-4o 的 audio-in、audio-out 模態，而是把修正後的逐字稿，用 GPT-4o 的 text-in、audio-out 模態產生目標語言的音訊。

#### 3. 有沒有些詞適合保留原語言？
有些術語或概念在目標語言裡可能沒有合適的翻法，或是用原文反而比較好懂。回頭檢查你的 `glossary_of_terms_to_keep_in_original_language`，把這類詞加進去，維持清晰度跟上下文。

### 結論

總結來說，這份 cookbook 提供了一個清楚、一步一步的翻譯和配音流程，讓內容更容易被全球觀眾接觸。用 GPT-4o 的音訊輸入輸出能力，把音檔從一種語言翻譯配音成另一種變得簡單很多。我們的範例是把音檔從英文翻成印地語。

整個流程可以拆成下面這些步驟：

**1. 轉寫：** 用 GPT-4o 的 text modality，把來源語言音訊轉成來源語言的文字。

**2. 配音：** 用 GPT-4o 的 audio modality，直接把音檔配成目標語言。

**3. 評估翻譯品質：** 用 BLEU 或 ROUGE 分數，跟參考文字比較，評估翻譯的準確度。

**4. 優化流程：** 需要的話，調整 prompt 參數來改善轉寫和配音結果。

這份指南也強調了「language」和「script」的差別。這兩個詞常被搞混，但在翻譯工作裡很重要。Language 是口說或書寫的溝通系統，script 是用來書寫語言的字元集合。弄懂這個差別，對有效翻譯和配音很關鍵。

照這份 cookbook 的技巧，你可以翻譯並配音各種內容，從 podcast、教學影片到長片電影，翻成多種語言。這個方法適用於娛樂、教育、商業和全球傳播等各種產業，幫創作者觸及不同語言的觀眾。

## 重點整理

- GPT-4o 的 audio-in、audio-out 把「轉寫、翻譯、合成語音」三步壓成一次 API 呼叫，差別只在 output modality 設 `["text"]` 還是 `["text", "audio"]`。
- Language 和 script 是兩回事，混合語言的輸出會各自用自己的文字系統，唸起來才自然。
- 沒有人工參考譯文時，可以把配音結果轉寫回原語言，再跟原逐字稿算 BLEU、ROUGE。
- 分數不好先查三件事：來源轉寫對不對、來源有沒有文法錯誤、有沒有該保留原文的詞，調整的位置都在 prompt 的 glossary 或前處理。

## 練習

1. 把 Step 2 的目標語言從印地語換成別的語言，重跑並比較 BLEU 分數。
2. 在 Step 1 的 system prompt 加一份 glossary，放幾個容易聽錯的專有名詞，看轉寫結果有沒有變好。
3. 照「來源音訊有文法錯誤」的建議，在中間加一個文字修正步驟，改用 text-in、audio-out 產生配音，比較跟原本直接 audio-in 的分數差異。
