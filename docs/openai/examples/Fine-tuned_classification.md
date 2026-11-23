---
translated: true
source: examples/Fine-tuned_classification.ipynb
---

# Fine-tuning 分類範例

> 原文：[examples/Fine-tuned_classification.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Fine-tuned_classification.ipynb)

## 這篇在做什麼
fine-tune 一個 `babbage-002` 分類器（`ada` 系列的替代品），讓它區分棒球和冰球兩種運動的郵件。流程包含準備資料、跑資料整理工具、訓練、看驗證結果，最後用模型做預測。

## 學完你會
- 把 newsgroup 資料集整理成 prompt 和 completion 的 jsonl 格式
- 用資料整理工具加上分隔符號、切出訓練與驗證集，並啟動 fine-tuning
- 用 fine-tuned 模型做單一 token 的分類預測，並用 logprobs 看各類別機率

## 開跑前
需要 OpenAI API key，fine-tuning 與推論都會產生費用。

我們要 fine-tune 一個 `babbage-002` 分類器（`ada` 模型的替代品），區分兩種運動：棒球和冰球。

```python
from sklearn.datasets import fetch_20newsgroups
import pandas as pd
import openai
import os

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

categories = ['rec.sport.baseball', 'rec.sport.hockey']
sports_dataset = fetch_20newsgroups(subset='train', shuffle=True, random_state=42, categories=categories)
```

 ## 資料探索
 newsgroup 資料集可以用 sklearn 載入。先看看資料本身：

```python
print(sports_dataset['data'][0])
```

??? note "輸出"

    ```text
    From: dougb@comm.mot.com (Doug Bank)
    Subject: Re: Info needed for Cleveland tickets
    Reply-To: dougb@ecs.comm.mot.com
    Organization: Motorola Land Mobile Products Sector
    Distribution: usa
    Nntp-Posting-Host: 145.1.146.35
    Lines: 17

    In article <1993Apr1.234031.4950@leland.Stanford.EDU>, bohnert@leland.Stanford.EDU (matthew bohnert) writes:

    |> I'm going to be in Cleveland Thursday, April 15 to Sunday, April 18.
    |> Does anybody know if the Tribe will be in town on those dates, and
    |> if so, who're they playing and if tickets are available?

    The tribe will be in town from April 16 to the 19th.
    There are ALWAYS tickets available! (Though they are playing Toronto,
    and many Toronto fans make the trip to Cleveland as it is easier to
    get tickets in Cleveland than in Toronto.  Either way, I seriously
    doubt they will sell out until the end of the season.)

    -- 
    Doug Bank                       Private Systems Division
    dougb@ecs.comm.mot.com          Motorola Communications Sector
    dougb@nwu.edu                   Schaumburg, Illinois
    dougb@casbah.acns.nwu.edu       708-576-8207
    ```

```python
sports_dataset.target_names[sports_dataset['target'][0]]
```

??? note "輸出"

    ```text
    'rec.sport.baseball'
    ```

```python
len_all, len_baseball, len_hockey = len(sports_dataset.data), len([e for e in sports_dataset.target if e == 0]), len([e for e in sports_dataset.target if e == 1])
print(f"Total examples: {len_all}, Baseball examples: {len_baseball}, Hockey examples: {len_hockey}")
```

??? note "輸出"

    ```text
    Total examples: 1197, Baseball examples: 597, Hockey examples: 600
    ```

上面是棒球類別的一個樣本，是寄到郵件群組的一封信。可以看到總共有 1197 筆，兩種運動平均分布。

## 資料準備
我們把資料集轉成 pandas dataframe，有 prompt 和 completion 兩欄。prompt 是郵件群組的信，completion 是運動名稱，hockey 或 baseball。為了示範和加快 fine-tuning，我們只取 300 筆。實際使用時，範例越多效果越好。

```python
import pandas as pd

labels = [sports_dataset.target_names[x].split('.')[-1] for x in sports_dataset['target']]
texts = [text.strip() for text in sports_dataset['data']]
df = pd.DataFrame(zip(texts, labels), columns = ['prompt','completion']) #[:300]
df.head()
```

??? note "輸出"

    ```text
                                                  prompt completion
    0  From: dougb@comm.mot.com (Doug Bank)\nSubject:...   baseball
    1  From: gld@cunixb.cc.columbia.edu (Gary L Dare)...     hockey
    2  From: rudy@netcom.com (Rudy Wade)\nSubject: Re...   baseball
    3  From: monack@helium.gas.uug.arizona.edu (david...     hockey
    4  Subject: Let it be Known\nFrom: <ISSBTL@BYUVM....   baseball
    ```

baseball 和 hockey 都是單一 token。我們把資料集存成 jsonl 檔。

```python
df.to_json("sport2.jsonl", orient='records', lines=True)
```

### 資料整理工具
接著可以用資料整理工具，它會在 fine-tuning 前對資料集提出一些改進建議。啟動工具前先更新 openai 函式庫，確保用的是最新的資料整理工具。我們另外指定 `-q`，自動接受所有建議。

```python
!openai tools fine_tunes.prepare_data -f sport2.jsonl -q
```

??? note "輸出"

    ```text
    Analyzing...

    - Your file contains 1197 prompt-completion pairs
    - Based on your data it seems like you're trying to fine-tune a model for classification
    - For classification, we recommend you try one of the faster and cheaper models, such as `ada`
    - For classification, you can estimate the expected model performance by keeping a held out dataset, which is not used for training
    - There are 11 examples that are very long. These are rows: [134, 200, 281, 320, 404, 595, 704, 838, 1113, 1139, 1174]
    For conditional generation, and for classification the examples shouldn't be longer than 2048 tokens.
    - Your data does not contain a common separator at the end of your prompts. Having a separator string appended to the end of the prompt makes it clearer to the fine-tuned model where the completion should begin. See https://platform.openai.com/docs/guides/fine-tuning/preparing-your-dataset for more detail and examples. If you intend to do open-ended generation, then you should leave the prompts empty
    - The completion should start with a whitespace character (` `). This tends to produce better results due to the tokenization we use. See https://platform.openai.com/docs/guides/fine-tuning/preparing-your-dataset for more details

    Based on the analysis we will perform the following actions:
    - [Recommended] Remove 11 long examples [Y/n]: Y
    - [Recommended] Add a suffix separator `\n\n###\n\n` to all prompts [Y/n]: Y
    - [Recommended] Add a whitespace character to the beginning of the completion [Y/n]: Y
    - [Recommended] Would you like to split into training and validation set? [Y/n]: Y


    Your data will be written to a new JSONL file. Proceed [Y/n]: Y

    Wrote modified files to `sport2_prepared_train (1).jsonl` and `sport2_prepared_valid (1).jsonl`
    Feel free to take a look!

    Now use that file when fine-tuning:
    > openai api fine_tunes.create -t "sport2_prepared_train (1).jsonl" -v "sport2_prepared_valid (1).jsonl" --compute_classification_metrics --classification_positive_class " baseball"

    After you’ve fine-tuned a model, remember that your prompt has to end with the indicator string `\n\n###\n\n` for the model to start generating completions, rather than continuing with the prompt.
    Once your model starts training, it'll approximately take 30.8 minutes to train a `curie` model, and less for `ada` and `babbage`. Queue will approximately take half an hour per job ahead of you.
    ```

工具貼心地給了一些資料集的改進建議，並把資料集切成訓練集和驗證集。

prompt 和 completion 之間需要一個分隔字串（suffix），告訴模型輸入文字已經結束，接下來要預測類別。因為每個範例都用相同的分隔符號，模型就能學到在分隔符號之後要預測 baseball 或 hockey。
completion 前面加空白字元也有用，因為大部分單字 token 都帶空白前綴。
工具也認出這很可能是分類任務，所以建議把資料集切成訓練集和驗證集，讓我們能輕鬆衡量模型在新資料上的預期表現。

## Fine-tuning
工具建議我們執行下面的指令來訓練。因為這是分類任務，我們想知道在提供的驗證集上，分類用例的泛化表現如何。

直接複製 CLI 工具建議的指令就行。我們特別加上 `-m ada`，fine-tune 較便宜、較快的 ada 模型，在分類用例上它的表現通常和較慢、較貴的模型差不多。

```python
train_file = client.files.create(file=open("sport2_prepared_train.jsonl", "rb"), purpose="fine-tune")
valid_file = client.files.create(file=open("sport2_prepared_valid.jsonl", "rb"), purpose="fine-tune")

fine_tuning_job = client.fine_tuning.jobs.create(training_file=train_file.id, validation_file=valid_file.id, model="babbage-002")

print(fine_tuning_job)
```

??? note "輸出"

    ```text
    FineTuningJob(id='ftjob-REo0uLpriEAm08CBRNDlPJZC', created_at=1704413736, error=None, fine_tuned_model=None, finished_at=None, hyperparameters=Hyperparameters(n_epochs='auto', batch_size='auto', learning_rate_multiplier='auto'), model='babbage-002', object='fine_tuning.job', organization_id='org-9HXYFy8ux4r6aboFyec2OLRf', result_files=[], status='validating_files', trained_tokens=None, training_file='file-82XooA2AUDBAUbN5z2DuKRMs', validation_file='file-wTOcQF8vxQ0Z6fNY2GSm0z4P')
    ```

模型大約十分鐘就訓練完成。你可以到 [https://platform.openai.com/finetune/](https://platform.openai.com/finetune/) 看 fine-tune 的進度。

也可以用程式查狀態：

```python
fine_tune_results = client.fine_tuning.jobs.retrieve(fine_tuning_job.id)
print(fine_tune_results.finished_at)
```

??? note "輸出"

    ```text
    1704414393
    ```

### [進階] 結果與預期模型表現
現在可以下載結果檔，看在保留的驗證集上的預期表現。

```python
fine_tune_results = client.fine_tuning.jobs.retrieve(fine_tuning_job.id).result_files
result_file = client.files.retrieve(fine_tune_results[0])
content = client.files.content(result_file.id)
# save content to file
with open("result.csv", "wb") as f:
    f.write(content.text.encode("utf-8"))
```

```python
results = pd.read_csv('result.csv')
results[results['train_accuracy'].notnull()].tail(1)
```

??? note "輸出"

    ```text
          step  train_loss  train_accuracy  valid_loss  valid_mean_token_accuracy
    2843  2844         0.0             1.0         NaN                        NaN
    ```

準確率達到 99.6%。下面的圖可以看到訓練過程中驗證集的準確率怎麼上升。

```python
results[results['train_accuracy'].notnull()]['train_accuracy'].plot()
```

## 使用模型
現在可以呼叫模型取得預測。

```python
test = pd.read_json('sport2_prepared_valid.jsonl', lines=True)
test.head()
```

??? note "輸出"

    ```text
                                                  prompt completion
    0  From: gld@cunixb.cc.columbia.edu (Gary L Dare)...     hockey
    1  From: smorris@venus.lerc.nasa.gov (Ron Morris ...     hockey
    2  From: golchowy@alchemy.chem.utoronto.ca (Geral...     hockey
    3  From: krattige@hpcc01.corp.hp.com (Kim Krattig...   baseball
    4  From: warped@cs.montana.edu (Doug Dolven)\nSub...   baseball
    ```

prompt 後面要用和 fine-tuning 時相同的分隔符號，這裡是 `\n\n###\n\n`。因為我們關心的是分類，所以 temperature 要盡量低，而且只需要一個 token 的 completion 就能得到模型的預測。

```python
ft_model = fine_tune_results.fine_tuned_model

# note that this calls the legacy completions api - https://platform.openai.com/docs/api-reference/completions
res = client.completions.create(model=ft_model, prompt=test['prompt'][0] + '\n\n###\n\n', max_tokens=1, temperature=0)
res.choices[0].text
```

??? note "輸出"

    ```text
    ' hockey'
    ```

要取得 log probability，可以在 completion 請求指定 logprobs 參數

```python
res = client.completions.create(model=ft_model, prompt=test['prompt'][0] + '\n\n###\n\n', max_tokens=1, temperature=0, logprobs=2)
res.choices[0].logprobs.top_logprobs
```

??? note "輸出"

    ```text
    [{' hockey': 0.0, ' Hockey': -22.504879}]
    ```

可以看到模型預測 hockey 的機率比 baseball 高很多，這是正確的預測。請求 log_probs 後，就能看到每個類別的預測（log）機率。

### 泛化
有趣的是，我們 fine-tune 的分類器相當通用。雖然是用寄到不同郵件群組的信訓練的，它也能成功預測推文。

```python
sample_hockey_tweet = """Thank you to the 
@Canes
 and all you amazing Caniacs that have been so supportive! You guys are some of the best fans in the NHL without a doubt! Really excited to start this new chapter in my career with the 
@DetroitRedWings
 !!"""
res = client.completions.create(model=ft_model, prompt=sample_hockey_tweet + '\n\n###\n\n', max_tokens=1, temperature=0, logprobs=2)
res.choices[0].text
```

??? note "輸出"

    ```text
    ' hockey'
    ```

```python
sample_baseball_tweet="""BREAKING: The Tampa Bay Rays are finalizing a deal to acquire slugger Nelson Cruz from the Minnesota Twins, sources tell ESPN."""
res = client.completions.create(model=ft_model, prompt=sample_baseball_tweet + '\n\n###\n\n', max_tokens=1, temperature=0, logprobs=2)
res.choices[0].text
```

## 重點整理
- 分類任務可以用 fine-tuning，把類別名稱當成單一 token 的 completion。
- prompt 結尾要有固定的分隔符號，推論時也要用同一個，模型才知道該輸出類別。
- 分類時 temperature 設低、只要一個 token，並用 logprobs 看各類別的機率。
- 切出驗證集才能衡量模型在新資料上的表現。
- 即使訓練資料是郵件，模型也能泛化到推文這類不同形式的文字。

## 練習
1. 把取樣的 300 筆改成 100 筆重新 fine-tune，比較驗證準確率。
2. 推論時把分隔符號拿掉，看預測結果會不會變差。
3. 換成自己寫的幾句棒球或冰球推文，用 logprobs 檢查模型對每個類別的信心。
