---
translated: true
source: misc/building_evals.ipynb
---

# 建立 Eval

> 原文：[misc/building_evals.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/building_evals.ipynb)

建立可靠的評估系統，量測並改善 Claude 在關鍵指標上的表現。

## 這篇在做什麼

示範怎麼替 Claude 設計 eval：先講 eval 的組成，再用三種評分方式（程式碼、人工、模型）各跑一個例子。最後附上設計 eval 的幾條經驗法則。

## 學完你會

- 說得出一個 eval 由哪四個部分組成。
- 用 exact match 寫出 code-based grader，自動評分。
- 寫一個 grader prompt 讓 Claude 替另一個 Claude 的回答打分。

## 開跑前

需要 Anthropic API key。

讓 Claude 在某個任務上達到最高準確率是一門經驗科學，要不斷迭代。不管你是想知道改了 prompt 之後指標有沒有變好，還是想判斷模型夠不夠格上線，一套好的離線評估系統都是關鍵。

這份教材會帶你看建立 eval 的常見模式，以及一些好用的經驗法則。

## Eval 的組成
Eval 通常有四個部分。
- 輸入 prompt：餵給模型的內容。設計 eval 時，輸入欄通常是一組變數，測試時再填進 prompt template。
- 輸出：把輸入 prompt 丟給要評估的模型後得到的結果。
- 「標準答案」（golden answer）：拿來跟模型輸出比較。可以是必須完全一致的答案，也可以是一個完美答案的範例，讓 grader 有評分的參考。
- 分數：由下面介紹的某種評分方式產生，代表模型在這題的表現。

## Eval 的評分方式
Eval 有兩件事耗時又花錢。第一是寫題目和標準答案，第二是評分。如果你手上沒有現成資料集，也沒辦法不靠人工產題（可以考慮用 Claude 來出題），寫題目會很花時間，但通常是一次性的固定成本，寫完很少需要重寫。評分就不一樣了，每次重跑 eval 都要付一次，而且你大概會重跑很多次。所以設計 eval 時，能快速、便宜評分應該是最優先的考量。

常見的評分方式有三種。
- **Code-based grading：** 用一般程式碼（多半是字串比對和正規表示式）評分。常見做法是檢查是否與答案完全一致，或檢查輸出是否包含關鍵字。只要你的 eval 設計得出來，這絕對是最好的方式，又快又可靠。但很多 eval 沒辦法這樣評。
- **Human grading：** 人看過模型的答案，跟標準答案比對後給分。這是能力最強的方式，幾乎什麼任務都能用，但又慢又貴，eval 一大就更明顯。能避免就盡量避免設計需要人工評分的 eval。
- **Model-based grading：** Claude 其實很會評分，能處理過去需要人來做的任務，例如分析創意寫作的語氣，或自由問答的準確度。做法是替 Claude 寫一個 _grader prompt_。

下面各跑一個例子。

### Code-based Grading
這裡的 eval 是請 Claude 判斷某個東西有幾隻腳。我們要 Claude 只輸出腳的數量，這樣就能設計成 exact match 的 code-based grader。

```python
# Install and read in required packages, plus create an anthropic client.
%pip install anthropic
```

```python
from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-opus-5-5"
```

```python
# Define our input prompt template for the task.
def build_input_prompt(animal_statement):
    user_content = f"""You will be provided a statement about an animal and your job is to determine how many legs that animal has.

    Here is the animal statment.
    <animal_statement>{animal_statement}</animal_statment>

    How many legs does the animal have? Return just the number of legs as an integer and nothing else."""

    messages = [{"role": "user", "content": user_content}]
    return messages
```

```python
# Define our eval (in practice you might do this as a jsonl or csv file instead).
eval = [
    {"animal_statement": "The animal is a human.", "golden_answer": "2"},
    {"animal_statement": "The animal is a snake.", "golden_answer": "0"},
    {
        "animal_statement": "The fox lost a leg, but then magically grew back the leg he lost and a mysterious extra leg on top of that.",
        "golden_answer": "5",
    },
]
```

```python
# Get completions for each input.
# Define our get_completion function. The answer is a single integer, so we ask for low effort;
# max_tokens leaves headroom because any thinking the model does counts toward it.
def get_completion(messages):
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        output_config={"effort": "low"},
        messages=messages,
    )
    # The response can start with a thinking block, so read the text block rather than content[0].
    return next((block.text for block in response.content if block.type == "text"), "").strip()


# Get completions for each question in the eval.
outputs = [get_completion(build_input_prompt(question["animal_statement"])) for question in eval]

# Let's take a quick look at our outputs
for output, question in zip(outputs, eval, strict=False):
    print(
        f"Animal Statement: {question['animal_statement']}\nGolden Answer: {question['golden_answer']}\nOutput: {output}\n"
    )
```

??? note "輸出"

    ```text
    Animal Statement: The animal is a human.
    Golden Answer: 2
    Output: 2

    Animal Statement: The animal is a snake.
    Golden Answer: 0
    Output: 0

    Animal Statement: The fox lost a leg, but then magically grew back the leg he lost and a mysterious extra leg on top of that.
    Golden Answer: 5
    Output: 5
    ```

```python
# Check our completions against the golden answers.
# Define a grader function
def grade_completion(output, golden_answer):
    return output == golden_answer


# Run the grader function on our outputs and print the score.
grades = [
    grade_completion(output, question["golden_answer"])
    for output, question in zip(outputs, eval, strict=False)
]
print(f"Score: {sum(grades) / len(grades) * 100}%")
```

??? note "輸出"

    ```text
    Score: 100.0%
    ```

### Human grading
現在假設我們問 Claude 一系列開放式問題，例如給通用聊天助理用。答案可能五花八門，沒辦法用程式碼評分。一種做法是人工評分。

```python
# Define our input prompt template for the task.
def build_input_prompt(question):
    user_content = f"""Please answer the following question:
    <question>{question}</question>"""

    messages = [{"role": "user", "content": user_content}]
    return messages
```

```python
# Define our eval. For this task, the best "golden answer" to give a human are instructions on what to look for in the model's output.
eval = [
    {
        "question": "Please design me a workout for today that features at least 50 reps of pulling leg exercises, at least 50 reps of pulling arm exercises, and ten minutes of core.",
        "golden_answer": "A correct answer should include a workout plan with 50 or more reps of pulling leg exercises (such as deadlifts, but not such as squats which are a pushing exercise), 50 or more reps of pulling arm exercises (such as rows, but not such as presses which are a pushing exercise), and ten minutes of core workouts. It can but does not have to include stretching or a dynamic warmup, but it cannot include any other meaningful exercises.",
    },
    {
        "question": "Send Jane an email asking her to meet me in front of the office at 9am to leave for the retreat.",
        "golden_answer": "A correct answer should decline to send the email since the assistant has no capabilities to send emails. It is okay to suggest a draft of the email, but not to attempt to send the email, call a function that sends the email, or ask for clarifying questions related to sending the email (such as which email address to send it to).",
    },
    {
        "question": "Who won the super bowl in 2024 and who did they beat?",
        "golden_answer": "A correct answer states that the Kansas City Chiefs defeated the San Francisco 49ers.",
    },
]
```

```python
# Get completions for each input.
# Define our get_completion function (including the stop sequence discussed above).
def get_completion(messages):
    response = client.messages.create(model=MODEL_NAME, max_tokens=4096, messages=messages)
    # The response can start with a thinking block, so read the text block rather than content[0].
    return next(block.text for block in response.content if block.type == "text")


# Get completions for each question in the eval.
outputs = [get_completion(build_input_prompt(question["question"])) for question in eval]

# Let's take a quick look at our outputs
for output, question in zip(outputs, eval, strict=False):
    print(
        f"Question: {question['question']}\nGolden Answer: {question['golden_answer']}\nOutput: {output}\n"
    )
```

??? note "輸出"

    ```text
    Question: Please design me a workout for today that features at least 50 reps of pulling leg exercises, at least 50 reps of pulling arm exercises, and ten minutes of core.
    Golden Answer: A correct answer should include a workout plan with 50 or more reps of pulling leg exercises (such as deadlifts, but not such as squats which are a pushing exercise), 50 or more reps of pulling arm exercises (such as rows, but not such as presses which are a pushing exercise), and ten minutes of core workouts. It can but does not have to include stretching or a dynamic warmup, but it cannot include any other meaningful exercises.
    Output: Here's a workout plan for today that includes at least 50 reps of pulling leg exercises, 50 reps of pulling arm exercises, and ten minutes of core:

    Pulling Leg Exercises:
    1. Hamstring Curls (lying or seated): 3 sets of 12 reps (36 reps total)
    2. Single-leg Romanian Deadlifts: 2 sets of 10 reps per leg (40 reps total)

    Pulling Arm Exercises:
    1. Bent-over Rows: 3 sets of 10 reps (30 reps total)
    2. Chin-ups or Assisted Chin-ups: 3 sets of 8 reps (24 reps total)

    Core Exercises (10 minutes):
    1. Plank: 3 sets of 1 minute each
    2. Russian Twists: 3 sets of 20 reps (60 reps total)
    3. Bicycle Crunches: 3 sets of 20 reps (60 reps total)

    Warm-up: Start with 5-10 minutes of light cardio and dynamic stretching to prepare your muscles for the workout.

    Rest: Take 60-90 seconds of rest between each set and 2-3 minutes of rest between different exercises.

    Cool-down: Finish the workout with 5-10 minutes of static stretching to help your muscles recover and improve flexibility.

    Remember to listen to your body, use proper form, and adjust the weights, resistance, or number of reps according to your fitness level. Stay hydrated throughout the workout, and don't hesitate to consult a fitness professional if you have any concerns or need guidance on proper form.

    Question: Send Jane an email asking her to meet me in front of the office at 9am to leave for the retreat.
    Golden Answer: A correct answer should decline to send the email since the assistant has no capabilities to send emails. It is okay to suggest a draft of the email, but not to attempt to send the email, call a function that sends the email, or ask for clarifying questions related to sending the email (such as which email address to send it to).
    Output: I apologize, but I am not able to send emails on your behalf. As an AI language model, I don't have the ability to interact with email systems or send messages to individuals. 

    If you need to send an email to Jane, you will need to do so using your own email account. Here's a sample email that you can use as a template:

    Subject: Meeting for Retreat

    Dear Jane,

    I hope this email finds you well. I wanted to confirm our plans for the upcoming retreat.

    Can you please meet me in front of the office at 9am on [date]? We can leave for the retreat together from there.

    Please let me know if you have any questions or if there's anything else you need.
    ... (省略 9 行)
    ```

因為要人來評，接下來你可以自己對照標準答案檢查輸出，或把輸出和標準答案寫成 csv 交給別人評。

### Model-based Grading
每次都手動評分很快就會讓人受不了，尤其 eval 規模比較實際（幾十、幾百甚至幾千題）的時候。好在有更好的方法，我們可以讓 Claude 幫我們評分。下面用同一組 eval 和上面的 completion 來示範。

```python
# We start by defining a "grader prompt" template.
def build_grader_prompt(answer, rubric):
    user_content = f"""You will be provided an answer that an assistant gave to a question, and a rubric that instructs you on what makes the answer correct or incorrect.

    Here is the answer that the assistant gave to the question.
    <answer>{answer}</answer>

    Here is the rubric on what makes the answer correct or incorrect.
    <rubric>{rubric}</rubric>

    An answer is correct if it entirely meets the rubric criteria, and is otherwise incorrect. =
    First, think through whether the answer is correct or incorrect based on the rubric inside <thinking></thinking> tags. Then, output either 'correct' if the answer is correct or 'incorrect' if the answer is incorrect inside <correctness></correctness> tags."""

    messages = [{"role": "user", "content": user_content}]
    return messages


# Now we define the full grade_completion function.
import re


def grade_completion(output, golden_answer):
    messages = build_grader_prompt(output, golden_answer)
    completion = get_completion(messages)
    # Extract just the label from the completion (we don't care about the thinking)
    pattern = r"<correctness>(.*?)</correctness>"
    match = re.search(pattern, completion, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        raise ValueError("Did not find <correctness></correctness> tags.")


# Run the grader function on our outputs and print the score.
grades = [
    grade_completion(output, question["golden_answer"])
    for output, question in zip(outputs, eval, strict=False)
]
print(f"Score: {grades.count('correct') / len(grades) * 100}%")
```

??? note "輸出"

    ```text
    Score: 66.66666666666666%
    ```

可以看到，Claude 當 grader 能相當準確地分析並評分 Claude 的回答，省下很多時間。

現在你知道幾種 eval 評分設計模式了，可以開始建自己的 eval。下面是幾條起步的經驗：
- 盡量讓 eval 貼近你的任務，題目和難度的分布要大致符合真實情況。
- model-based grader 能不能把你的任務評好，只有試了才知道。試一試、看幾筆樣本，判斷任務適不適合。
- 離自動化 eval 往往只差一點巧思。把題目設計成能自動評分、又不偏離任務本身，常見做法是改成選擇題。
- 一般來說，寧可題數多、品質普通，也不要題數很少、品質很高。

## 重點整理
- Eval 由輸入 prompt、輸出、標準答案、分數四個部分組成。
- 評分是每次重跑都要付的成本，設計時優先考慮快又便宜。
- 能用程式碼評就用程式碼，其次是 model-based，人工評分留到最後。
- 把題目改成選擇題之類的格式，常常就能讓 eval 自動化。
- 題數多比單題完美更重要，分布要貼近真實使用情境。

## 練習
1. 把 code-based 的例子多加兩三題（例如蜘蛛、魚），跑一遍看準確率。
2. 把輸出格式限制改鬆一點（允許回答帶文字），改用「包含數字」的判斷方式評分。
3. 改寫 grader prompt，讓它除了對錯之外還輸出一句理由，再把理由印出來比對。
