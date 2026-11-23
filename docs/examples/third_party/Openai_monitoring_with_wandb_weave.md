---
translated: true
source: examples/third_party/Openai_monitoring_with_wandb_weave.ipynb
---

# 用 Weights & Biases Weave 監控 OpenAI API

> 原文：[examples/third_party/Openai_monitoring_with_wandb_weave.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/Openai_monitoring_with_wandb_weave.ipynb)



## 這篇在做什麼
用 W&B 的 OpenAI integration 記錄每一次 OpenAI API 呼叫，並產生 Weave Board 這種 LLM 用量監控 dashboard，讓你看成本、延遲、吞吐量等指標。

## 學完你會
- 呼叫 `init_monitor()` 開始記錄 OpenAI API 呼叫，並打開 Weave Board
- 把 system prompt、template 等參數當作 attribute 記錄下來，方便分組分析
- 記錄 streaming 訊息，以及用不同 prompt 設定做實驗後在 Board 上比較

## 開跑前
- OpenAI API key
- Weights & Biases 帳號（需要登入，並設定 wandb 的使用者或團隊名稱）


<img src="http://wandb.me/logo-im-png" width="400" alt="Weights & Biases" />

<!--- @wandbcode{weave_openai_client_qs} -->

<a target="_blank" href="https://colab.research.google.com/github/wandb/weave/blob/master/examples/prompts/llm_monitoring/openai_client_quickstart.ipynb">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>

**注意：** 跑這份 colab 需要 [OpenAI API key](https://platform.openai.com/account/api-keys)。

用 W&B 的 OpenAI integration 來監控 OpenAI API 呼叫，了解你的專案和團隊怎麼使用 LLM。
這個範例會產生 template 化的 Weave Board，也就是 LLM 用量監控 dashboard，你可以在 UI 裡探索和客製化。

* 自動追蹤 LLM 用量，並彙總各專案、各團隊的成本、延遲和吞吐量等有用指標
* 動態查詢所有 OpenAI API 呼叫的 log，並從中得出洞察
* 用視覺化方式反覆操作：切分、彙總、探索資料，客製化 panel 來聚焦有趣的模式，並透過互動式 dashboard 更輕鬆地跟團隊分享進度

<img src="https://raw.githubusercontent.com/wandb/weave/master/docs/assets/full_board_view.png">

[試玩這個 Weave Board 的線上版本 →](http://wandb.me/llm-monitoring-board)

#### 第一次用 Weights & Biases？[-> 在這裡註冊帳號 <-](https://wandb.ai/site)

# 步驟 0：Setup

安裝相依套件，登入 W&B 以便儲存和分享你的成果，並驗證 OpenAI。

```python
# if not already installed
!pip install -qqq weave openai tiktoken wandb
```

```python
import wandb
wandb.login()
```

```python
import weave
import os
WANDB_BASE_URL = "https://api.wandb.ai"
os.environ["WANDB_BASE_URL"] = WANDB_BASE_URL
```

```python
# authenticate with OpenAI
from getpass import getpass

if os.getenv("OPENAI_API_KEY") is None:
  os.environ["OPENAI_API_KEY"] = getpass("Paste your OpenAI key from: https://platform.openai.com/account/api-keys\n")
assert os.getenv("OPENAI_API_KEY", "").startswith("sk-"), "This doesn't look like a valid OpenAI API key"
print("OpenAI API key configured")
```

# 步驟 1：設定 W&B 的資料串流與儲存

把 WB_ENTITY 設成你的 wandb 使用者名稱或團隊名稱。登入 W&B 並前往首頁 [wandb.ai/home](https://wandb.ai/home)，在左側欄的「Profile」和「Teams」下可以看到有效的選項。

```python
WB_ENTITY = "" # set to your wandb username or team name
WB_PROJECT = "weave" # top-level directory for this work
STREAM_NAME = "openai_logs" # record table which stores the logs of OpenAI API calls as they stream in
```

# 步驟 2：呼叫 init_monitor()

要開始監控 OpenAI API 用量，呼叫 `init_monitor(<stream>)`，其中 `<stream>` 的格式是 `<wandb_team_or_user>/<wandb_project>/<stream_name>`。這個 stream 會記錄並儲存所有 OpenAI API 呼叫。

執行這個 cell 會印出一個連結，可在 Weave UI 查看目前的專案。

```python
from weave.monitoring import openai, init_monitor
m = init_monitor(f"{WB_ENTITY}/{WB_PROJECT}/{STREAM_NAME}")

# specifying a single model for simplicity
OPENAI_MODEL = 'gpt-3.5-turbo'

# prefill with some sample logs
r = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": "hello world!"}])
r = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[{"role": "user", "content": "what is 2+2?"}])
```

# 步驟 3：預覽監控 dashboard

點上面的連結預覽資料串流，然後點右側欄的「OpenAI Monitor Board」，為這個資料串流建立 Weave Board。

<img src="https://raw.githubusercontent.com/wandb/weave/master/docs/assets/short_board_attempt.gif" width=75%>

# 步驟 4：探索並了解你的 LLM 用量

要儲存你的成果，點頁面上方自動產生的名稱來重新命名 Board。要分享 Board，點右上角的 \"Publish\"。

<img src="https://raw.githubusercontent.com/wandb/weave/master/docs/assets/publish_board_short.gif" width=75%>

想在迭代時即時看到成果，可以：
* 把 Board 開在另一個分頁，重新整理就能看到最新資料
* 隨時重新命名 Board 方便參考，並 \"Publish\" 那個版本，把連結分享給別人
* 到 weave.wandb.ai 找到對應的 W&B entity 和 W&B project 名稱，就能找到之前儲存的 Board
* 或用 Board template 開一個新的 instance，帶著目前累積的所有資料重新開始


接下來我們會示範幾種追蹤 OpenAI API 呼叫的方式。依你的使用情境還有更多可能，我們很期待看到你用這些起手式 template 做出什麼。

# 範例

## 範例 0：記錄 prompt 和它的 completion

監控一個 ChatCompletion 請求，並印出對應的回應，只取出 completion 的文字。

```python
response = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[
        {"role": "user", "content": f"What is the meaning of life, the universe, and everything?"},
    ])
print(response['choices'][0]['message']['content'])
```

## 範例 1：把相關參數當作 attribute 追蹤

把感興趣的參數獨立出來，當作 attribute 記錄在 log 紀錄上。
這裡我們把「system prompt」跟「prompt template」和「equation」參數分開追蹤。這次我們會印出 ChatCompletion 呼叫完整的結構化回應。

```python
system_prompt = "you always write in bullet points"
prompt_template = 'solve the following equation step by step: {equation}'
params = {'equation': '4 * (3 - 1)'}
openai.ChatCompletion.create(model=OPENAI_MODEL,
                             messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt_template.format(**params)},
                                ],
                             # you can add additional attributes to the logged record
                             # see the monitor_api notebook for more examples
                             monitor_attributes={
                                 'system_prompt': system_prompt,
                                 'prompt_template': prompt_template,
                                 'params': params
                             })
```

## 範例 2：記錄持續進行的訊息串流

監控一串訊息，並把結果記成一筆紀錄。注意：這種格式不會計算 token。

```python
from weave.monitoring.openai import message_from_stream
r = openai.ChatCompletion.create(model=OPENAI_MODEL, messages=[
        {"role": "system", "content": "You are a robot and only speak in robot, like beep bloop bop."},
        {"role": "user", "content": "Tell me a 50-word story."},
    ], stream=True)
for s in message_from_stream(r):
    print(s, end='')
```

## 範例 3：把 prompt engineering 實驗結構化

這裡比較幾個簡單的選項：system prompt、使用者問題和目標讀者。你可以自己做實驗，在 Board 裡探索並依不同參數分組，看看有沒有有趣的洞察。

```python
def explain_math(system_prompt, prompt_template, params):
    openai.ChatCompletion.create(model=OPENAI_MODEL,
                             messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": prompt_template.format(**params)},
                                ],
                             # you can add additional attributes to the logged record
                             # see the monitor_api notebook for more examples
                             monitor_attributes={
                                 'system_prompt': system_prompt,
                                 'prompt_template': prompt_template,
                                 'params': params
                             })
```

```python
# feel free to substitute your own prompts :)
system_prompts = ["you're extremely flowery and poetic", "you're very direct and precise", "balance brevity with insight"]
prompt_template = 'explain the solution of the following to a {audience}: {equation}'
equations = ['x^2 + 4x + 9 = 0', '15 * (2 - 6) / 4']
audience = ["new student", "math genius"]

for system_prompt in system_prompts:
    for equation in equations:
        for person in audience:
            params = {"equation" : equation, "audience" : person}
            explain_math(system_prompt, prompt_template, params)
```

## 重點整理
- 監控的核心是 `init_monitor(<stream>)`，之後的 OpenAI API 呼叫都會被記錄到指定的 stream。
- Weave Board 把 log 變成 dashboard，能看成本、延遲、吞吐量，並自己切分資料。
- 把 system prompt、template 等參數記成 attribute，之後才能依這些參數分組比較。
- streaming 訊息可以記成單筆紀錄，但不會計算 token。
- prompt 實驗結構化記錄後，就能在 Board 上直接比較不同設定的效果。

## 練習
1. 在範例 0 換一個 prompt 再呼叫一次，到 Board 上確認新紀錄出現。
2. 在範例 1 多加一個自己的參數（例如 `audience`），並在 Board 上依它分組。
3. 在範例 3 新增一組 system prompt 選項，比較它和原本選項的 token 用量與回應差異。
