---
translated: true
source: examples/Whisper_correct_misspelling.ipynb
---

# 修正轉錄的拼字錯誤：prompt 還是後處理

> 原文：[examples/Whisper_correct_misspelling.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Whisper_correct_misspelling.ipynb)



## 這篇在做什麼
處理語音轉文字裡公司名、產品名拼錯的問題。比較兩種做法：把正確拼法放進 Whisper 的 prompt 參數，或轉錄後用 GPT-4 搭配同一份清單做拼字修正。

## 學完你會
- 用 Whisper 的 prompt 參數引導專有名詞的轉錄
- 用 GPT-4 當 spell checker 對轉錄結果做後處理
- 判斷兩種做法在規模、可靠度、成本和延遲上的取捨

## 開跑前
需要 OpenAI API key，並下載範例音檔。

我們要解決的問題是提升轉錄的精確度，尤其是公司名和產品名。做法是雙管齊下，同時用 Whisper 的 prompt 參數和 GPT-4 的後處理能力。

修正錯誤的兩種方式：

- 把正確拼法的清單直接放進 Whisper 的 prompt 參數，引導一開始的轉錄。

- 轉錄之後用 GPT-4 修正拼字錯誤，同樣使用那份正確拼法清單放進 prompt。

這些策略的目標，是讓不熟悉的專有名詞轉錄得精確。

## 環境設定

開始之前先做這兩件事：

- 匯入 OpenAI Python 函式庫（沒有的話要用 ```pip install openai``` 安裝）
- 下載範例音檔

```python
# imports
from openai import OpenAI  # for making OpenAI API calls
import urllib  # for downloading example audio files
import os  # for accessing environment variables

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

```python
# set download paths
ZyntriQix_remote_filepath = "https://cdn.openai.com/API/examples/data/ZyntriQix.wav"


# set local save locations
ZyntriQix_filepath = "data/ZyntriQix.wav"

# download example audio files and save locally
urllib.request.urlretrieve(ZyntriQix_remote_filepath, ZyntriQix_filepath)
```

??? note "輸出"

    ```text
    ('data/ZyntriQix.wav', <http.client.HTTPMessage at 0x10559a910>)
    ```

## 用一段虛構的錄音建立 baseline

我們的參考點是一段獨白，內容由 ChatGPT 根據作者給的 prompt 產生，再由作者本人唸出來。也就是說作者既用 prompt 引導 ChatGPT 的輸出，也親自把它講出來。

我們虛構的公司 ZyntriQix 有一系列科技產品，包括 Digique Plus、CynapseFive、VortiQore V8、EchoNix Array、OrbitalLink Seven 和 DigiFractal Matrix。公司也主導幾個專案，例如 PULSE、RAPT、B.R.I.C.K.、Q.U.A.R.T.Z. 和 F.L.I.N.T.。

```python
# define a wrapper function for seeing how prompts affect transcriptions
def transcribe(prompt: str, audio_filepath) -> str:
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
transcribe(prompt="", audio_filepath=ZyntriQix_filepath)
```

??? note "輸出"

    ```text
    "Have you heard of ZentricX? This tech giant boasts products like Digi-Q+, Synapse 5, VortiCore V8, Echo Nix Array, and not to forget the latest Orbital Link 7 and Digifractal Matrix. Their innovation arsenal also includes the Pulse framework, Wrapped system, they've developed a brick infrastructure court system, and launched the Flint initiative, all highlighting their commitment to relentless innovation. ZentricX, in just 30 years, has soared from a startup to a tech titan, serving us tech marvels alongside a stimulating linguistic challenge. Quite an adventure, wouldn't you agree?"
    ```

Whisper 把我們的公司名和產品名轉錯了，縮寫的大小寫也錯。我們把正確名稱以清單形式放進 prompt 試試。

```python
# add the correct spelling names to the prompt
transcribe(
    prompt="ZyntriQix, Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, OrbitalLink Seven, DigiFractal Matrix, PULSE, RAPT, B.R.I.C.K., Q.U.A.R.T.Z., F.L.I.N.T.",
    audio_filepath=ZyntriQix_filepath,
)
```

??? note "輸出"

    ```text
    "Have you heard of ZyntriQix? This tech giant boasts products like Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, and not to forget the latest OrbitalLink Seven and DigiFractal Matrix. Their innovation arsenal also includes the PULSE framework, RAPT system. They've developed a B.R.I.C.K. infrastructure, Q.U.A.R.T. system, and launched the F.L.I.N.T. initiative, all highlighting their commitment to relentless innovation. ZyntriQix in just 30 years has soared from a startup to a tech titan, serving us tech marvels alongside a stimulating linguistic challenge. Quite an adventure, wouldn't you agree?"
    ```

放入產品名清單之後，有些產品名轉對了，但有些還是拼錯。

```python
# add a full product list to the prompt
transcribe(
    prompt="ZyntriQix, Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, OrbitalLink Seven, DigiFractal Matrix, PULSE, RAPT, AstroPixel Array, QuantumFlare Five, CyberPulse Six, VortexDrive Matrix, PhotonLink Ten, TriCircuit Array, PentaSync Seven, UltraWave Eight, QuantumVertex Nine, HyperHelix X, DigiSpiral Z, PentaQuark Eleven, TetraCube Twelve, GigaPhase Thirteen, EchoNeuron Fourteen, FusionPulse V15, MetaQuark Sixteen, InfiniCircuit Seventeen, TeraPulse Eighteen, ExoMatrix Nineteen, OrbiSync Twenty, QuantumHelix TwentyOne, NanoPhase TwentyTwo, TeraFractal TwentyThree, PentaHelix TwentyFour, ExoCircuit TwentyFive, HyperQuark TwentySix, B.R.I.C.K., Q.U.A.R.T.Z., F.L.I.N.T.",
    audio_filepath=ZyntriQix_filepath,
)
```

??? note "輸出"

    ```text
    "Have you heard of ZentricX? This tech giant boasts products like DigiCube Plus, Synapse 5, VortiCore V8, EchoNix Array, and not to forget the latest Orbital Link 7 and Digifractal Matrix. Their innovation arsenal also includes the PULSE framework, RAPT system. They've developed a brick infrastructure court system and launched the F.L.I.N.T. initiative, all highlighting their commitment to relentless innovation. ZentricX in just 30 years has soared from a startup to a tech titan, serving us tech marvels alongside a stimulating linguistic challenge. Quite an adventure, wouldn't you agree?"
    ```

## 可以用 GPT-4 修正拼字錯誤

事先不知道講話內容、但手上有現成產品名清單時，GPT-4 特別好用。

這種 GPT-4 後處理的做法，比只靠 Whisper 的 prompt 參數更容易擴展，因為 Whisper prompt 有 244 個 token 的上限。GPT-4 能處理更大的正確拼法清單，對很長的產品清單比較穩。

不過這個做法也有限制。它受所選模型的 context window 限制，遇到大量不重複詞彙時會有困難。例如有幾千個 SKU 的公司，GPT-4 的 context window 可能不夠用，需要找其他方案。

有趣的是，GPT-4 後處理看起來比單用 Whisper 可靠。用產品清單來做，結果的可靠度會提高。但代價是成本會增加，延遲也會變高。

```python
# define a wrapper function for seeing how prompts affect transcriptions
def transcribe_with_spellcheck(system_message, audio_filepath):
    completion = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {"role": "system", "content": system_message},
            {
                "role": "user",
                "content": transcribe(prompt="", audio_filepath=audio_filepath),
            },
        ],
    )
    return completion.choices[0].message.content
```

現在把原本的產品清單輸入 GPT-4，看它的表現。我們想評估這個模型在事先不知道轉錄裡會出現哪些詞的情況下，能不能把專有產品名拼對。實驗中 GPT-4 成功拼對了產品名，證明它是確保轉錄準確的可靠工具。

```python
system_prompt = "You are a helpful assistant for the company ZyntriQix. Your task is to correct any spelling discrepancies in the transcribed text. Make sure that the names of the following products are spelled correctly: ZyntriQix, Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, OrbitalLink Seven, DigiFractal Matrix, PULSE, RAPT, B.R.I.C.K., Q.U.A.R.T.Z., F.L.I.N.T."
new_text = transcribe_with_spellcheck(system_prompt, audio_filepath=ZyntriQix_filepath)
print(new_text)
```

??? note "輸出"

    ```text
    Have you heard of ZyntriQix? This tech giant boasts products like Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, and not to forget the latest OrbitalLink Seven and DigiFractal Matrix. Their innovation arsenal also includes the PULSE framework, RAPT system, they've developed a B.R.I.C.K. infrastructure court system, and launched the F.L.I.N.T. initiative, all highlighting their commitment to relentless innovation. ZyntriQix, in just 30 years, has soared from a startup to a tech titan, serving us tech marvels alongside a stimulating linguistic challenge. Quite an adventure, wouldn't you agree?
    ```

這次我們給了一份完整的產品清單，包含之前用過的所有拼法，另外加了新名稱。這模擬真實情境：手上有大量 SKU 清單，但不確定轉錄裡會出現哪些詞。把這份很長的清單餵進去之後，輸出的轉錄是正確的。

```python
system_prompt = "You are a helpful assistant for the company ZyntriQix. Your task is to correct any spelling discrepancies in the transcribed text. Make sure that the names of the following products are spelled correctly: ZyntriQix, Digique Plus, CynapseFive, VortiQore V8, EchoNix Array,  OrbitalLink Seven, DigiFractal Matrix, PULSE, RAPT, AstroPixel Array, QuantumFlare Five, CyberPulse Six, VortexDrive Matrix, PhotonLink Ten, TriCircuit Array, PentaSync Seven, UltraWave Eight, QuantumVertex Nine, HyperHelix X, DigiSpiral Z, PentaQuark Eleven, TetraCube Twelve, GigaPhase Thirteen, EchoNeuron Fourteen, FusionPulse V15, MetaQuark Sixteen, InfiniCircuit Seventeen, TeraPulse Eighteen, ExoMatrix Nineteen, OrbiSync Twenty, QuantumHelix TwentyOne, NanoPhase TwentyTwo, TeraFractal TwentyThree, PentaHelix TwentyFour, ExoCircuit TwentyFive, HyperQuark TwentySix, GigaLink TwentySeven, FusionMatrix TwentyEight, InfiniFractal TwentyNine, MetaSync Thirty, B.R.I.C.K., Q.U.A.R.T.Z., F.L.I.N.T. Only add necessary punctuation such as periods, commas, and capitalization, and use only the context provided."
new_text = transcribe_with_spellcheck(system_prompt, audio_filepath=ZyntriQix_filepath)
print(new_text)
```

??? note "輸出"

    ```text
    Have you heard of ZyntriQix? This tech giant boasts products like Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, and not to forget the latest OrbitalLink Seven and DigiFractal Matrix. Their innovation arsenal also includes the PULSE framework, RAPT system, they've developed a B.R.I.C.K. infrastructure court system, and launched the F.L.I.N.T. initiative, all highlighting their commitment to relentless innovation. ZyntriQix, in just 30 years, has soared from a startup to a tech titan, serving us tech marvels alongside a stimulating linguistic challenge. Quite an adventure, wouldn't you agree?
    ```

我們用 GPT-4 當拼字檢查器，使用先前放在 prompt 裡的同一份正確拼法清單。

```python
system_prompt = "You are a helpful assistant for the company ZyntriQix. Your first task is to list the words that are not spelled correctly according to the list provided to you and to tell me the number of misspelled words. Your next task is to insert those correct words in place of the misspelled ones. List: ZyntriQix, Digique Plus, CynapseFive, VortiQore V8, EchoNix Array,  OrbitalLink Seven, DigiFractal Matrix, PULSE, RAPT, AstroPixel Array, QuantumFlare Five, CyberPulse Six, VortexDrive Matrix, PhotonLink Ten, TriCircuit Array, PentaSync Seven, UltraWave Eight, QuantumVertex Nine, HyperHelix X, DigiSpiral Z, PentaQuark Eleven, TetraCube Twelve, GigaPhase Thirteen, EchoNeuron Fourteen, FusionPulse V15, MetaQuark Sixteen, InfiniCircuit Seventeen, TeraPulse Eighteen, ExoMatrix Nineteen, OrbiSync Twenty, QuantumHelix TwentyOne, NanoPhase TwentyTwo, TeraFractal TwentyThree, PentaHelix TwentyFour, ExoCircuit TwentyFive, HyperQuark TwentySix, GigaLink TwentySeven, FusionMatrix TwentyEight, InfiniFractal TwentyNine, MetaSync Thirty, B.R.I.C.K., Q.U.A.R.T.Z., F.L.I.N.T."
new_text = transcribe_with_spellcheck(system_prompt, audio_filepath=ZyntriQix_filepath)
print(new_text)
```

??? note "輸出"

    ```text
    The misspelled words are: ZentricX, Digi-Q+, Synapse 5, VortiCore V8, Echo Nix Array, Orbital Link 7, Digifractal Matrix, Pulse, Wrapped, brick, Flint, and 30. The total number of misspelled words is 12.

    The corrected paragraph is:

    Have you heard of ZyntriQix? This tech giant boasts products like Digique Plus, CynapseFive, VortiQore V8, EchoNix Array, and not to forget the latest OrbitalLink Seven and DigiFractal Matrix. Their innovation arsenal also includes the PULSE framework, RAPT system, they've developed a B.R.I.C.K. infrastructure court system, and launched the F.L.I.N.T. initiative, all highlighting their commitment to relentless innovation. ZyntriQix, in just MetaSync Thirty years, has soared from a startup to a tech titan, serving us tech marvels alongside a stimulating linguistic challenge. Quite an adventure, wouldn't you agree?
    ```

## 重點整理
- Whisper 的 prompt 參數能引導專有名詞的拼法，但有 244 token 的上限，效果也不保證全部都對。
- 用 GPT-4 做後處理，可以吃進更長的名稱清單，結果比單用 Whisper 可靠。
- 後處理的代價是成本和延遲增加，而且仍受模型 context window 限制。
- 清單特別大（例如上千個 SKU）時，兩種方法都可能不夠用，要另找方案。

## 練習
1. 在 Whisper 的 prompt 裡只放一半的產品名，觀察哪些名稱還是會拼錯。
2. 改 GPT-4 的 system prompt，要求它只修正清單裡的名稱、不要動其他文字，再比較輸出。
3. 在清單裡加幾個發音相近但不在音檔裡的假產品名，看 GPT-4 會不會誤改原本正確的詞。
