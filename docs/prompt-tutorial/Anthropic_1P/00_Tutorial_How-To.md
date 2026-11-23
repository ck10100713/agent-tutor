---
translated: true
source: Anthropic 1P/00_Tutorial_How-To.ipynb
---

# 教學使用說明

> 原文：[Anthropic 1P/00_Tutorial_How-To.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/00_Tutorial_How-To.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com

## 這篇在做什麼

這篇是整個 prompt engineering 教學的開場，說明怎麼把環境跑起來、API key 怎麼設，以及後面每一章都會用到的 `get_completion` helper 長什麼樣。跑完這篇，後面的章節就能直接接著玩。

## 學完你會

- 把教學 repo 抓到本機並裝好相依套件
- 設定 `API_KEY` 和 `MODEL_NAME`，讓後面所有 notebook 共用
- 用 `get_completion` 對 Claude 送一段 prompt 並印出回應

## 開跑前

這個教學需要 Anthropic API key。沒有的話可以到 [Anthropic Console](https://console.anthropic.com/) 申請，或是直接看[靜態版答案表](https://docs.google.com/spreadsheets/u/0/d/1jIxjzUWG-6xBVIa2ay6yDpLyeuOh_hR_ZB75a47KX_E/edit)。

## 怎麼開始

1. 把這個 repo clone 到本機。

2. 執行下面的指令安裝相依套件：
 

```python
!pip install anthropic
```

3. 設定 API key 和 model 名稱。把 `"your_api_key_here"` 換成你自己的 Anthropic API key。

```python
API_KEY = "your_api_key_here"
MODEL_NAME = "claude-3-haiku-20240307"

# Stores the API_KEY & MODEL_NAME variables for use across notebooks within the IPython store
%store API_KEY
%store MODEL_NAME
```

4. 照順序執行 notebook 的 cell，跟著說明操作。

---

## 使用須知與小技巧 💡

- 這個課程用 Claude 3 Haiku、temperature 設 0。temperature 後面會再講，現在只要知道這組設定的結果比較固定。課程裡的 prompt engineering 技巧也適用於舊世代的 Claude 模型，例如 Claude 2 和 Claude Instant 1.2。

- 可以用 `Shift + Enter` 執行目前的 cell 並跳到下一個。

- 看完一頁教學後，到資料夾裡下一個編號的檔案；如果這一章的內容都做完了，就換到下一個編號的資料夾。

### Anthropic SDK 與 Messages API
整個教學都會用 [Anthropic python SDK](https://docs.anthropic.com/claude/reference/client-sdks) 和 [Messages API](https://docs.anthropic.com/claude/reference/messages_post)。

下面是教學裡執行 prompt 的範例。先建立 `get_completion`，這個 helper function 會把 prompt 送給 Claude 並回傳 Claude 產生的回應。現在先執行那個 cell。

```python
import anthropic

client = anthropic.Anthropic(api_key=API_KEY)

def get_completion(prompt: str):
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        temperature=0.0,
        messages=[
          {"role": "user", "content": prompt}
        ]
    )
    return message.content[0].text
```

接著寫一段給 Claude 的範例 prompt，用 `get_completion` 印出 Claude 的輸出。執行下面的 cell，回應會印在它下方。

可以隨意改 prompt 字串，看 Claude 會給出什麼不同的回應。

```python
# Prompt
prompt = "Hello, Claude!"

# Get Claude's response
print(get_completion(prompt))
```

前面定義的 `API_KEY` 和 `MODEL_NAME` 會在整個教學中重複使用。記得每一頁的 cell 都要從上到下依序執行。

## 重點整理

- 教學靠 `API_KEY` 和 `MODEL_NAME` 兩個變數驅動，每頁都要先從上到下跑過。
- `get_completion` 把「送 prompt、拿回應」包成一個函式，後面章節都在改 prompt 字串。
- 課程用 Claude 3 Haiku 加 temperature 0，輸出比較固定，方便對照答案。
- 底層是 Anthropic Python SDK 的 Messages API。

## 練習

1. 把範例 prompt 的問題換成別的，看回應怎麼變。
2. 把 `MODEL_NAME` 換成別的 Claude 模型再跑一次，比較回答差異。
3. 改 `get_completion` 裡的 `max_tokens`，看看設很小時回應會怎麼被截斷。
