---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/use-cases/bulk-experimentation.ipynb
---
# Evals API 使用案例：大量測試模型與 prompt

> 原文：[examples/evaluation/use-cases/bulk-experimentation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/bulk-experimentation.ipynb)



## 這篇在做什麼
用 Evals API 一次測試多組模型和 prompt 的組合，目標是讓推播通知摘要器表現最好。建一個用 LLM 當評審的 Eval，再用 3 種 prompt 乘上 3 個模型跑出 9 個 Run。

## 學完你會
- 設定 Eval 的 `data_source_config`（JSON Schema）和 `testing_criteria`（model grader）。
- 在 grader 裡用 `{{item.notifications}}` 和 `{{sample.output_text}}` 這些變數。
- 用迴圈對所有 prompt 和模型的組合建立 Run，一次比較多種設定。

## 開跑前
- 需要 OpenAI API key（Evals 和模型呼叫會產生費用）。


Eval 是**以任務為導向**、可反覆迭代的，也是檢查 LLM 整合表現並加以改進的最佳方式。

下面這個 eval 要處理的任務是**測試多種模型和 prompt 的變化**。

我們的使用情境是：
1. 我想讓我的推播通知摘要器得到最好的表現

## Eval 的結構

Eval 有兩個部分，"Eval" 和 "Run"。"Eval" 存放測試標準的設定，以及 "Run" 所用資料的結構。一個 Eval `has_many` 個 run，這些 run 由你的測試標準來評估。

```python
import pydantic
import openai
from openai.types.chat import ChatCompletion
import os

os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "your-api-key")
```

## 使用情境

我們要測試的整合是推播通知摘要器，它接收多則推播通知，把它們濃縮成一則訊息。

```python
class PushNotifications(pydantic.BaseModel):
    notifications: str

print(PushNotifications.model_json_schema())
```

```python
DEVELOPER_PROMPT = """
You are a helpful assistant that summarizes push notifications.
You are given a list of push notifications and you need to collapse them into a single one.
Output only the final summary, nothing else.
"""

def summarize_push_notification(push_notifications: str) -> ChatCompletion:
    result = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": push_notifications},
        ],
    )
    return result

example_push_notifications_list = PushNotifications(notifications="""
- Alert: Unauthorized login attempt detected.
- New comment on your blog post: "Great insights!"
- Tonight's dinner recipe: Pasta Primavera.
""")
result = summarize_push_notification(example_push_notifications_list.notifications)
print(result.choices[0].message.content)
```

# 設定你的 eval

Eval 存放多個 *Run* 共用的設定，包含兩個部分：
1. 資料來源設定 `data_source_config`：之後的 *Run* 要符合的 schema（欄位）。
    - `data_source_config` 用 JSON Schema 定義 Eval 裡可用的變數。
2. 測試標準 `testing_criteria`：怎麼判斷你的整合對資料來源的每一*列*資料是否運作正常。

這個使用情境要測試推播通知摘要的 completion 好不好，所以我們照這個目標設定 eval。

```python
# We want our input data to be available in our variables, so we set the item_schema to
# PushNotifications.model_json_schema()
data_source_config = {
    "type": "custom",
    "item_schema": PushNotifications.model_json_schema(),
    # We're going to be uploading completions from the API, so we tell the Eval to expect this
    "include_sample_schema": True,
}
```

這個 data_source_config 定義了整個 eval 裡可用的變數。

這個 item schema：
```json
{
  "properties": {
    "notifications": {
      "title": "Notifications",
      "type": "string"
    }
  },
  "required": ["notifications"],
  "title": "PushNotifications",
  "type": "object"
}
```
表示 eval 裡會有 `{{item.notifications}}` 這個變數可用。

`"include_sample_schema": True`
表示 eval 裡會有 `{{sample.output_text}}` 這個變數可用。

**接下來，用這些變數來設定測試標準。**

```python
GRADER_DEVELOPER_PROMPT = """
Categorize the following push notification summary into the following categories:
1. concise-and-snappy
2. drops-important-information
3. verbose
4. unclear
5. obscures-meaning
6. other 

You'll be given the original list of push notifications and the summary like this:

<push_notifications>
...notificationlist...
</push_notifications>
<summary>
...summary...
</summary>

You should only pick one of the categories above, pick the one which most closely matches and why.
"""
GRADER_TEMPLATE_PROMPT = """
<push_notifications>{{item.notifications}}</push_notifications>
<summary>{{sample.output_text}}</summary>
"""
push_notification_grader = {
    "name": "Push Notification Summary Grader",
    "type": "label_model",
    "model": "o3-mini",
    "input": [
        {
            "role": "developer",
            "content": GRADER_DEVELOPER_PROMPT,
        },
        {
            "role": "user",
            "content": GRADER_TEMPLATE_PROMPT,
        },
    ],
    "passing_labels": ["concise-and-snappy"],
    "labels": [
        "concise-and-snappy",
        "drops-important-information",
        "verbose",
        "unclear",
        "obscures-meaning",
        "other",
    ],
}
```

`push_notification_grader` 是一個 model grader（llm-as-a-judge），它看輸入 `{{item.notifications}}` 和產生的摘要 `{{sample.output_text}}`，把它標成 "correct" 或 "incorrect"。
再透過 "passing_labels" 指定什麼樣的答案算通過。

注意：底層用的是 structured outputs，所以標籤一定是合法的。

**現在建立 eval，開始加資料進去！**

```python
eval_create_result = openai.evals.create(
    name="Push Notification Bulk Experimentation Eval",
    metadata={
        "description": "This eval tests many prompts and models to find the best performing combination.",
    },
    data_source_config=data_source_config,
    testing_criteria=[push_notification_grader],
)
eval_id = eval_create_result.id
```

# 建立 Run

eval 和 testing_criteria 設定好之後，就可以開始加一堆 run 了！
先從一些推播通知資料開始。

```python
push_notification_data = [
        """
- New message from Sarah: "Can you call me later?"
- Your package has been delivered!
- Flash sale: 20% off electronics for the next 2 hours!
""",
        """
- Weather alert: Thunderstorm expected in your area.
- Reminder: Doctor's appointment at 3 PM.
- John liked your photo on Instagram.
""",
        """
- Breaking News: Local elections results are in.
- Your daily workout summary is ready.
- Check out your weekly screen time report.
""",
        """
- Your ride is arriving in 2 minutes.
- Grocery order has been shipped.
- Don't miss the season finale of your favorite show tonight!
""",
        """
- Event reminder: Concert starts at 7 PM.
- Your favorite team just scored!
- Flashback: Memories from 3 years ago.
""",
        """
- Low battery alert: Charge your device.
- Your friend Mike is nearby.
- New episode of "The Tech Hour" podcast is live!
""",
        """
- System update available.
- Monthly billing statement is ready.
- Your next meeting starts in 15 minutes.
""",
        """
- Alert: Unauthorized login attempt detected.
- New comment on your blog post: "Great insights!"
- Tonight's dinner recipe: Pasta Primavera.
""",
        """
- Special offer: Free coffee with any breakfast order.
- Your flight has been delayed by 30 minutes.
- New movie release: "Adventures Beyond" now streaming.
""",
        """
- Traffic alert: Accident reported on Main Street.
- Package out for delivery: Expected by 5 PM.
- New friend suggestion: Connect with Emma.
"""]
```

現在設定一批要測試的 prompt。

我們想測試一個基本 prompt，再加幾個變化：
1. 第一種只用基本 prompt
2. 第二種加入一些我們想要的摘要長什麼樣的正面範例
3. 最後一種同時加入正面和負面範例

我們也會列出要使用的模型清單。

```python
PROMPT_PREFIX = """
You are a helpful assistant that takes in an array of push notifications and returns a collapsed summary of them.
The push notification will be provided as follows:
<push_notifications>
...notificationlist...
</push_notifications>

You should return just the summary and nothing else.
"""

PROMPT_VARIATION_BASIC = f"""
{PROMPT_PREFIX}

You should return a summary that is concise and snappy.
"""

PROMPT_VARIATION_WITH_EXAMPLES = f"""
{PROMPT_VARIATION_BASIC}

Here is an example of a good summary:
<push_notifications>
- Traffic alert: Accident reported on Main Street.- Package out for delivery: Expected by 5 PM.- New friend suggestion: Connect with Emma.
</push_notifications>
<summary>
Traffic alert, package expected by 5pm, suggestion for new friend (Emily).
</summary>
"""

PROMPT_VARIATION_WITH_NEGATIVE_EXAMPLES = f"""
{PROMPT_VARIATION_WITH_EXAMPLES}

Here is an example of a bad summary:
<push_notifications>
- Traffic alert: Accident reported on Main Street.- Package out for delivery: Expected by 5 PM.- New friend suggestion: Connect with Emma.
</push_notifications>
<summary>
Traffic alert reported on main street. You have a package that will arrive by 5pm, Emily is a new friend suggested for you.
</summary>
"""

prompts = [
    ("basic", PROMPT_VARIATION_BASIC),
    ("with_examples", PROMPT_VARIATION_WITH_EXAMPLES),
    ("with_negative_examples", PROMPT_VARIATION_WITH_NEGATIVE_EXAMPLES),
]

models = ["gpt-4o", "gpt-4o-mini", "o3-mini"]
```

**現在只要用迴圈跑過所有 prompt 和所有模型，就能一次測試一堆設定組合！**

我們用 'completion' 的 run data source，並用 template 變數放入推播通知清單。

OpenAI 會幫你呼叫 completion，並填入 "sample.output_text"

```python
for prompt_name, prompt in prompts:
    for model in models:
        run_data_source = {
            "type": "completions",
            "input_messages": {
                "type": "template",
                "template": [
                    {
                        "role": "developer",
                        "content": prompt,
                    },
                    {
                        "role": "user",
                        "content": "<push_notifications>{{item.notifications}}</push_notifications>",
                    },
                ],
            },
            "model": model,
            "source": {
                "type": "file_content",
                "content": [
                    {
                        "item": PushNotifications(notifications=notification).model_dump()
                    }
                    for notification in push_notification_data
                ],
            },
        }

        run_create_result = openai.evals.runs.create(
            eval_id=eval_id,
            name=f"bulk_{prompt_name}_{model}",
            data_source=run_data_source,
        )
        print(f"Report URL {model}, {prompt_name}:", run_create_result.report_url)
```



## 恭喜，你剛剛在資料集上測試了 9 種不同的 prompt 和模型組合！

## 重點整理
- Eval 放共用設定（資料結構和測試標準），Run 是用某組設定跑出來的一次評估，一個 Eval 有很多 Run。
- `data_source_config` 決定 eval 裡有哪些變數可用，`include_sample_schema` 讓模型輸出變成 `{{sample.output_text}}`。
- Model grader 是 llm-as-a-judge，用 `passing_labels` 定義什麼算通過。
- 把 prompt 和模型做成清單再用迴圈建 Run，就能系統性地比較多種組合。

## 練習
1. 在 prompt 清單裡多加一個變化（例如要求摘要不超過 20 字），確認 Run 數量增加。
2. 把模型清單換成你想比較的其他模型。
3. 修改 `push_notification_grader` 的評分指示（例如要求摘要必須保留最重要的一則通知），看各組合的通過率變化。
