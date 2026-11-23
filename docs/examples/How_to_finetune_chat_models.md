---
translated: true
source: examples/How_to_finetune_chat_models.ipynb
---

# 如何 fine-tune chat 模型

> 原文：[examples/How_to_finetune_chat_models.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_finetune_chat_models.ipynb)

## 這篇在做什麼

用 RecipeNLG 資料集做食材實體抽取（NER），一步步 fine-tune `gpt-4o-mini-2024-07-18`。流程涵蓋載入資料、準備訓練與驗證資料、上傳檔案、建立 fine-tuning job，最後拿 fine-tuned 模型做推論。

## 學完你會

- 把資料整理成 chat 格式的 `.jsonl` 訓練與驗證檔，並上傳到 `Files` endpoint
- 建立 fine-tuning job、追蹤狀態與事件，拿到 `fine_tuned_model` ID
- 用 fine-tuned 模型呼叫 chat completions 做推論

## 開跑前

- 需要 `OPENAI_API_KEY`
- GPT-4o mini fine-tuning 只開放給 [Tier 4 和 5 用量等級](https://platform.openai.com/docs/guides/rate-limits/usage-tiers)的開發者
- fine-tuning 與推論都會產生費用


Fine-tuning 是用比 prompt 放得下的多得多的範例去訓練模型，讓你在很多任務上得到更好的結果。這個 notebook 是新的 GPT-4o mini fine-tuning 的逐步指南。我們用 [RecipeNLG 資料集](https://github.com/Glorf/recipenlg)做實體抽取，這個資料集提供各種食譜，以及每份食譜抽取出來的通用食材清單，是常見的具名實體辨識（NER）資料集。

注意：**GPT-4o mini fine-tuning 開放給 [Tier 4 和 5 用量等級](https://platform.openai.com/docs/guides/rate-limits/usage-tiers)的開發者。**你可以到 fine-tuning dashboard，點「create」，在 base model 下拉選單選「gpt-4o-mini-2024-07-18」開始。

我們會依序進行這幾個步驟：

1. **設定：**載入資料集，篩選成單一領域來 fine-tune。
2. **資料準備：**建立訓練與驗證範例，並上傳到 `Files` endpoint。
3. **Fine-tuning：**建立你的 fine-tuned 模型。
4. **推論：**用 fine-tuned 模型對新輸入做推論。

做完之後，你應該能訓練、評估並部署 fine-tuned 的 `gpt-4o-mini-2024-07-18` 模型。

更多 fine-tuning 資訊，可參考[文件指南](https://platform.openai.com/docs/guides/fine-tuning)或 [API reference](https://platform.openai.com/docs/api-reference/fine-tuning)。


## 設定


```python
# make sure to use the latest version of the openai python package
!pip install --upgrade --quiet openai
```

```python
import json
import openai
import os
import pandas as pd
from pprint import pprint

client = openai.OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    organization="<org id>",
    project="<project id>",
)
```

Fine-tuning 在聚焦於特定領域時效果最好。資料集要夠聚焦，模型才學得起來，但也要夠通用，沒看過的範例才不會被漏掉。基於這點，我們從 RecipesNLG 資料集取出一個子集，只保留來自 [cookbooks.com](https://cookbooks.com/) 的文件。


```python
# Read in the dataset we'll use for this task.
# This will be the RecipesNLG dataset, which we've cleaned to only contain documents from www.cookbooks.com
recipe_df = pd.read_csv("data/cookbook_recipes_nlg_10k.csv")

recipe_df.head()
```

??? note "輸出"

    ```text
                       title                                        ingredients  \
    0    No-Bake Nut Cookies  ["1 c. firmly packed brown sugar", "1/2 c. eva...   
    1  Jewell Ball'S Chicken  ["1 small jar chipped beef, cut up", "4 boned ...   
    2            Creamy Corn  ["2 (16 oz.) pkg. frozen corn", "1 (8 oz.) pkg...   
    3          Chicken Funny  ["1 large whole chicken", "2 (10 1/2 oz.) cans...   
    4   Reeses Cups(Candy)    ["1 c. peanut butter", "3/4 c. graham cracker ...   

                                              directions  \
    0  ["In a heavy 2-quart saucepan, mix brown sugar...   
    1  ["Place chipped beef on bottom of baking dish....   
    2  ["In a slow cooker, combine all ingredients. C...   
    3  ["Boil and debone chicken.", "Put bite size pi...   
    4  ["Combine first four ingredients and press in ...   

                                                  link             source  \
    0   www.cookbooks.com/Recipe-Details.aspx?id=44874  www.cookbooks.com   
    1  www.cookbooks.com/Recipe-Details.aspx?id=699419  www.cookbooks.com   
    2   www.cookbooks.com/Recipe-Details.aspx?id=10570  www.cookbooks.com   
    3  www.cookbooks.com/Recipe-Details.aspx?id=897570  www.cookbooks.com   
    4  www.cookbooks.com/Recipe-Details.aspx?id=659239  www.cookbooks.com   

                                                     NER  
    0  ["brown sugar", "milk", "vanilla", "nuts", "bu...  
    1  ["beef", "chicken breasts", "cream of mushroom...  
    2  ["frozen corn", "cream cheese", "butter", "gar...  
    3  ["chicken", "chicken gravy", "cream of mushroo...  
    4  ["peanut butter", "graham cracker crumbs", "bu...
    ```

## 資料準備

先來準備資料。用 `ChatCompletion` 格式 fine-tune 時，每個訓練範例就是一個簡單的 `messages` 清單。例如一筆資料可能長這樣：

```
[{'role': 'system',
  'content': 'You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided.'},

 {'role': 'user',
  'content': 'Title: No-Bake Nut Cookies\n\nIngredients: ["1 c. firmly packed brown sugar", "1/2 c. evaporated milk", "1/2 tsp. vanilla", "1/2 c. broken nuts (pecans)", "2 Tbsp. butter or margarine", "3 1/2 c. bite size shredded rice biscuits"]\n\nGeneric ingredients: '},

 {'role': 'assistant',
  'content': '["brown sugar", "milk", "vanilla", "nuts", "butter", "bite size shredded rice biscuits"]'}]
```

訓練時這段對話會被拆開：最後一則是模型要產生的 `completion`，其餘的 `messages` 則當作 prompt。建立訓練範例時要記得這點。如果你的模型要處理多輪對話，就要提供有代表性的多輪範例，對話變長時才不會表現變差。

注意目前每個訓練範例有 4096 token 的上限，超過的部分會在 4096 token 處被截斷。


```python
system_message = "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."


def create_user_message(row):
    return f"Title: {row['title']}\n\nIngredients: {row['ingredients']}\n\nGeneric ingredients: "


def prepare_example_conversation(row):
    return {
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": create_user_message(row)},
            {"role": "assistant", "content": row["NER"]},
        ]
    }


pprint(prepare_example_conversation(recipe_df.iloc[0]))
```

??? note "輸出"

    ```text
    {'messages': [{'content': 'You are a helpful recipe assistant. You are to '
                              'extract the generic ingredients from each of the '
                              'recipes provided.',
                   'role': 'system'},
                  {'content': 'Title: No-Bake Nut Cookies\n'
                              '\n'
                              'Ingredients: ["1 c. firmly packed brown sugar", '
                              '"1/2 c. evaporated milk", "1/2 tsp. vanilla", "1/2 '
                              'c. broken nuts (pecans)", "2 Tbsp. butter or '
                              'margarine", "3 1/2 c. bite size shredded rice '
                              'biscuits"]\n'
                              '\n'
                              'Generic ingredients: ',
                   'role': 'user'},
                  {'content': '["brown sugar", "milk", "vanilla", "nuts", '
                              '"butter", "bite size shredded rice biscuits"]',
                   'role': 'assistant'}]}
    ```

現在對資料集的一個子集這麼做，當作訓練資料。你可以從 30 到 50 個精心挑選的範例開始。訓練集變大，效能會持續線性成長，但 job 也會跑更久。


```python
# use the first 100 rows of the dataset for training
training_df = recipe_df.loc[0:100]

# apply the prepare_example_conversation function to each row of the training_df
training_data = training_df.apply(prepare_example_conversation, axis=1).tolist()

for example in training_data[:5]:
    print(example)
```

??? note "輸出"

    ```text
    {'messages': [{'role': 'system', 'content': 'You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided.'}, {'role': 'user', 'content': 'Title: No-Bake Nut Cookies\n\nIngredients: ["1 c. firmly packed brown sugar", "1/2 c. evaporated milk", "1/2 tsp. vanilla", "1/2 c. broken nuts (pecans)", "2 Tbsp. butter or margarine", "3 1/2 c. bite size shredded rice biscuits"]\n\nGeneric ingredients: '}, {'role': 'assistant', 'content': '["brown sugar", "milk", "vanilla", "nuts", "butter", "bite size shredded rice biscuits"]'}]}
    {'messages': [{'role': 'system', 'content': 'You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided.'}, {'role': 'user', 'content': 'Title: Jewell Ball\'S Chicken\n\nIngredients: ["1 small jar chipped beef, cut up", "4 boned chicken breasts", "1 can cream of mushroom soup", "1 carton sour cream"]\n\nGeneric ingredients: '}, {'role': 'assistant', 'content': '["beef", "chicken breasts", "cream of mushroom soup", "sour cream"]'}]}
    {'messages': [{'role': 'system', 'content': 'You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided.'}, {'role': 'user', 'content': 'Title: Creamy Corn\n\nIngredients: ["2 (16 oz.) pkg. frozen corn", "1 (8 oz.) pkg. cream cheese, cubed", "1/3 c. butter, cubed", "1/2 tsp. garlic powder", "1/2 tsp. salt", "1/4 tsp. pepper"]\n\nGeneric ingredients: '}, {'role': 'assistant', 'content': '["frozen corn", "cream cheese", "butter", "garlic powder", "salt", "pepper"]'}]}
    {'messages': [{'role': 'system', 'content': 'You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided.'}, {'role': 'user', 'content': 'Title: Chicken Funny\n\nIngredients: ["1 large whole chicken", "2 (10 1/2 oz.) cans chicken gravy", "1 (10 1/2 oz.) can cream of mushroom soup", "1 (6 oz.) box Stove Top stuffing", "4 oz. shredded cheese"]\n\nGeneric ingredients: '}, {'role': 'assistant', 'content': '["chicken", "chicken gravy", "cream of mushroom soup", "shredded cheese"]'}]}
    {'messages': [{'role': 'system', 'content': 'You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided.'}, {'role': 'user', 'content': 'Title: Reeses Cups(Candy)  \n\nIngredients: ["1 c. peanut butter", "3/4 c. graham cracker crumbs", "1 c. melted butter", "1 lb. (3 1/2 c.) powdered sugar", "1 large pkg. chocolate chips"]\n\nGeneric ingredients: '}, {'role': 'assistant', 'content': '["peanut butter", "graham cracker crumbs", "butter", "powdered sugar", "chocolate chips"]'}]}
    ```

除了訓練資料，也可以**選擇性**提供驗證資料，用來確認模型沒有對訓練集 overfit。


```python
validation_df = recipe_df.loc[101:200]
validation_data = validation_df.apply(
    prepare_example_conversation, axis=1).tolist()
```

接著要把資料存成 `.jsonl` 檔，每一行是一個訓練範例對話。


```python
def write_jsonl(data_list: list, filename: str) -> None:
    with open(filename, "w") as out:
        for ddict in data_list:
            jout = json.dumps(ddict) + "\n"
            out.write(jout)
```

```python
training_file_name = "tmp_recipe_finetune_training.jsonl"
write_jsonl(training_data, training_file_name)

validation_file_name = "tmp_recipe_finetune_validation.jsonl"
write_jsonl(validation_data, validation_file_name)
```

訓練用 `.jsonl` 檔的前 5 行長這樣：


```python
# print the first 5 lines of the training file
!head -n 5 tmp_recipe_finetune_training.jsonl
```

??? note "輸出"

    ```text
    {"messages": [{"role": "system", "content": "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."}, {"role": "user", "content": "Title: No-Bake Nut Cookies\n\nIngredients: [\"1 c. firmly packed brown sugar\", \"1/2 c. evaporated milk\", \"1/2 tsp. vanilla\", \"1/2 c. broken nuts (pecans)\", \"2 Tbsp. butter or margarine\", \"3 1/2 c. bite size shredded rice biscuits\"]\n\nGeneric ingredients: "}, {"role": "assistant", "content": "[\"brown sugar\", \"milk\", \"vanilla\", \"nuts\", \"butter\", \"bite size shredded rice biscuits\"]"}]}
    {"messages": [{"role": "system", "content": "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."}, {"role": "user", "content": "Title: Jewell Ball'S Chicken\n\nIngredients: [\"1 small jar chipped beef, cut up\", \"4 boned chicken breasts\", \"1 can cream of mushroom soup\", \"1 carton sour cream\"]\n\nGeneric ingredients: "}, {"role": "assistant", "content": "[\"beef\", \"chicken breasts\", \"cream of mushroom soup\", \"sour cream\"]"}]}
    {"messages": [{"role": "system", "content": "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."}, {"role": "user", "content": "Title: Creamy Corn\n\nIngredients: [\"2 (16 oz.) pkg. frozen corn\", \"1 (8 oz.) pkg. cream cheese, cubed\", \"1/3 c. butter, cubed\", \"1/2 tsp. garlic powder\", \"1/2 tsp. salt\", \"1/4 tsp. pepper\"]\n\nGeneric ingredients: "}, {"role": "assistant", "content": "[\"frozen corn\", \"cream cheese\", \"butter\", \"garlic powder\", \"salt\", \"pepper\"]"}]}
    {"messages": [{"role": "system", "content": "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."}, {"role": "user", "content": "Title: Chicken Funny\n\nIngredients: [\"1 large whole chicken\", \"2 (10 1/2 oz.) cans chicken gravy\", \"1 (10 1/2 oz.) can cream of mushroom soup\", \"1 (6 oz.) box Stove Top stuffing\", \"4 oz. shredded cheese\"]\n\nGeneric ingredients: "}, {"role": "assistant", "content": "[\"chicken\", \"chicken gravy\", \"cream of mushroom soup\", \"shredded cheese\"]"}]}
    {"messages": [{"role": "system", "content": "You are a helpful recipe assistant. You are to extract the generic ingredients from each of the recipes provided."}, {"role": "user", "content": "Title: Reeses Cups(Candy)  \n\nIngredients: [\"1 c. peanut butter\", \"3/4 c. graham cracker crumbs\", \"1 c. melted butter\", \"1 lb. (3 1/2 c.) powdered sugar\", \"1 large pkg. chocolate chips\"]\n\nGeneric ingredients: "}, {"role": "assistant", "content": "[\"peanut butter\", \"graham cracker crumbs\", \"butter\", \"powdered sugar\", \"chocolate chips\"]"}]}
    ```

### 上傳檔案

現在可以把檔案上傳到我們的 `Files` endpoint，讓 fine-tuned 模型使用。


```python
def upload_file(file_name: str, purpose: str) -> str:
    with open(file_name, "rb") as file_fd:
        response = client.files.create(file=file_fd, purpose=purpose)
    return response.id


training_file_id = upload_file(training_file_name, "fine-tune")
validation_file_id = upload_file(validation_file_name, "fine-tune")

print("Training file ID:", training_file_id)
print("Validation file ID:", validation_file_id)
```

??? note "輸出"

    ```text
    Training file ID: file-3wfAfDoYcGrSpaE17qK0vXT0
    Validation file ID: file-HhFhnyGJhazYdPcd3wrtvIoX
    ```

## Fine-tuning

現在可以用產生好的檔案，加上一個選填的 suffix（用來辨識模型）建立 fine-tuning job。回應裡有一個 `id`，可以用來查詢 job 的更新。

注意：檔案要先經過我們系統處理，所以你可能會遇到 `File not ready` 錯誤。這時等幾分鐘再重試就好。


```python
MODEL = "gpt-4o-mini-2024-07-18"

response = client.fine_tuning.jobs.create(
    training_file=training_file_id,
    validation_file=validation_file_id,
    model=MODEL,
    suffix="recipe-ner",
)

job_id = response.id

print("Job ID:", response.id)
print("Status:", response.status)
```

??? note "輸出"

    ```text
    Job ID: ftjob-UiaiLwGdGBfdLQDBAoQheufN
    Status: validating_files
    ```

#### 檢查 job 狀態

你可以對 `https://api.openai.com/v1/alpha/fine-tunes` endpoint 發 `GET` request 列出 alpha fine-tune job。這裡要確認上一步拿到的 ID 最後變成 `status: succeeded`。

完成後，可以用 `result_files` 從驗證集取樣結果（如果你有上傳驗證集），並用 `fine_tuned_model` 參數裡的 ID 呼叫你訓練好的模型。


```python
response = client.fine_tuning.jobs.retrieve(job_id)

print("Job ID:", response.id)
print("Status:", response.status)
print("Trained Tokens:", response.trained_tokens)
```

??? note "輸出"

    ```text
    Job ID: ftjob-UiaiLwGdGBfdLQDBAoQheufN
    Status: running
    Trained Tokens: None
    ```

我們可以用 events endpoint 追蹤 fine-tune 的進度。下面的 cell 可以多跑幾次，直到 fine-tune 完成。


```python
response = client.fine_tuning.jobs.list_events(job_id)

events = response.data
events.reverse()

for event in events:
    print(event.message)
```

??? note "輸出"

    ```text
    Step 288/303: training loss=0.00
    Step 289/303: training loss=0.01
    Step 290/303: training loss=0.00, validation loss=0.31
    Step 291/303: training loss=0.00
    Step 292/303: training loss=0.00
    Step 293/303: training loss=0.00
    Step 294/303: training loss=0.00
    Step 295/303: training loss=0.00
    Step 296/303: training loss=0.00
    Step 297/303: training loss=0.00
    Step 298/303: training loss=0.01
    Step 299/303: training loss=0.00
    Step 300/303: training loss=0.00, validation loss=0.04
    Step 301/303: training loss=0.16
    Step 302/303: training loss=0.00
    Step 303/303: training loss=0.00, full validation loss=0.33
    Checkpoint created at step 101 with Snapshot ID: ft:gpt-4o-mini-2024-07-18:openai-gtm:recipe-ner:9o1eNlSa:ckpt-step-101
    Checkpoint created at step 202 with Snapshot ID: ft:gpt-4o-mini-2024-07-18:openai-gtm:recipe-ner:9o1eNFnj:ckpt-step-202
    New fine-tuned model created: ft:gpt-4o-mini-2024-07-18:openai-gtm:recipe-ner:9o1eNNKO
    The job has successfully completed
    ```

完成後，就能從 job 取得 fine-tuned 模型的 ID：


```python
response = client.fine_tuning.jobs.retrieve(job_id)
fine_tuned_model_id = response.fine_tuned_model

if fine_tuned_model_id is None:
    raise RuntimeError(
        "Fine-tuned model ID not found. Your job has likely not been completed yet."
    )

print("Fine-tuned model ID:", fine_tuned_model_id)
```

??? note "輸出"

    ```text
    Fine-tuned model ID: ft:gpt-4o-mini-2024-07-18:openai-gtm:recipe-ner:9o1eNNKO
    ```

## 推論


最後一步是用你的 fine-tuned 模型做推論。跟傳統的 `FineTuning` 一樣，只要呼叫 `ChatCompletions`，把新的 fine-tuned 模型名稱填進 `model` 參數即可。


```python
test_df = recipe_df.loc[201:300]
test_row = test_df.iloc[0]
test_messages = []
test_messages.append({"role": "system", "content": system_message})
user_message = create_user_message(test_row)
test_messages.append({"role": "user", "content": user_message})

pprint(test_messages)
```

??? note "輸出"

    ```text
    [{'content': 'You are a helpful recipe assistant. You are to extract the '
                 'generic ingredients from each of the recipes provided.',
      'role': 'system'},
     {'content': 'Title: Beef Brisket\n'
                 '\n'
                 'Ingredients: ["4 lb. beef brisket", "1 c. catsup", "1 c. water", '
                 '"1/2 onion, minced", "2 Tbsp. cider vinegar", "1 Tbsp. prepared '
                 'horseradish", "1 Tbsp. prepared mustard", "1 tsp. salt", "1/2 '
                 'tsp. pepper"]\n'
                 '\n'
                 'Generic ingredients: ',
      'role': 'user'}]
    ```

```python
response = client.chat.completions.create(
    model=fine_tuned_model_id, messages=test_messages, temperature=0, max_tokens=500
)
print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    ["beef brisket", "catsup", "water", "onion", "cider vinegar", "horseradish", "mustard", "salt", "pepper"]
    ```

## 結論

恭喜，你現在可以用 `ChatCompletion` 格式 fine-tune 自己的模型了！期待看到你做出什麼


## 重點整理

- Fine-tuning 適合範例多到塞不進 prompt 的任務，領域要聚焦但又不能窄到漏掉沒見過的案例。
- chat 格式的訓練範例是 `messages` 清單，最後一則是模型要產生的輸出，其餘當 prompt。
- 訓練資料從 30 到 50 筆精選範例就能起步，資料越多效果越好，但 job 也越久。
- 驗證集是選配，用來確認沒有 overfit。
- fine-tuning job 是非同步的，要輪詢狀態或事件，成功後用 `fine_tuned_model` 的 ID 呼叫。

## 練習

1. 把訓練資料的筆數改成 50，重新產生 `.jsonl` 並確認每行格式正確。
2. 建立 job 時加上自己的 `suffix`，並在 job 完成後確認 `fine_tuned_model` 名稱裡有它。
3. 推論時換三個沒在訓練集出現的食譜，比較 fine-tuned 模型和原本 `gpt-4o-mini` 抽出的食材差異。
