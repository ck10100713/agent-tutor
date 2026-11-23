---
translated: true
source: examples/Leveraging_model_distillation_to_fine-tune_a_model.ipynb
---

# 用 model distillation 微調出一個小模型

> 原文：[examples/Leveraging_model_distillation_to_fine-tune_a_model.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Leveraging_model_distillation_to_fine-tune_a_model.ipynb)

把大模型蒸餾（distill）成一個微調過的小模型。

## 這篇在做什麼

用大模型的輸出去 fine-tune 小模型，這就是 OpenAI 的 Distillation。這篇把 `gpt-4o` 的輸出蒸餾到 `gpt-4o-mini`，再跟沒蒸餾的 `gpt-4o-mini` 比準確率。任務是看法國葡萄酒的評論，預測葡萄品種。

## 學完你會

- 用 Structured Outputs 加 enum 把分類答案限制在固定清單內
- 用 `store=True` 加 metadata 存下 gpt-4o 的 completion，並在平台上篩選出來做 distillation
- 用同一組驗證資料比較 gpt-4o、gpt-4o-mini 和蒸餾後模型的準確率

## 開跑前

- 環境變數 `OPENAI_API_KEY`
- 需要從 Kaggle 下載 wine-reviews 資料集
- Fine-tuning 和呼叫模型都會花錢

OpenAI **Distillation** 是拿大模型的輸出去 fine-tune 小模型。換成小模型之後，特定任務的延遲和成本可以降下來。這篇把 `gpt-4o` 的輸出蒸餾到 `gpt-4o-mini`，再跟一般沒蒸餾的 `gpt-4o-mini` 比較。

分類的部分會用 **Structured Outputs** 搭配 enum。我們會量測 structured outputs 對 fine-tuned 模型的影響，也會證明它對每個模型都能用，包括蒸餾後的模型。

流程是先分析資料集，拿到 4o 和 4o mini 的輸出，看兩者的表現差異，接著做 distillation，再分析蒸餾後模型的表現。

## 前置作業

先安裝並載入套件。
確認你的 OpenAI API key 已經設成環境變數 "OPENAI_API_KEY"，client 會直接讀取。

```python
! pip install openai tiktoken numpy pandas tqdm --quiet
```

```python
import openai
import json
import tiktoken
from tqdm import tqdm
from openai import OpenAI
import numpy as np
import concurrent.futures
import pandas as pd

client = OpenAI()
```

## 載入並了解資料集

這篇用的資料來自這個 Kaggle 競賽：[https://www.kaggle.com/datasets/zynicide/wine-reviews](https://www.kaggle.com/datasets/zynicide/wine-reviews)。

資料集有很多列，你可以拿整份跑。我自己偏愛法國酒，所以只留下法國葡萄酒，這樣列數和葡萄品種都比較少，方便聚焦。

這是個分類問題，要根據描述、子產區和省份來預測葡萄品種，這些資訊都會放進 prompt。這給了模型很多線索。你可以拿掉會讓任務變簡單很多的資訊，例如葡萄的產地，看看模型單靠其他資訊能猜得多準。

先把評論中出現次數少於五次的葡萄品種濾掉。

接著從資料集隨機取 500 列來做。

```python
df = pd.read_csv('data/winemag/winemag-data-130k-v2.csv')
df_france = df[df['country'] == 'France']

# Let's also filter out wines that have less than 5 references with their grape variety – even though we'd like to find those
# they're outliers that we don't want to optimize for that would make our enum list be too long
# and they could also add noise for the rest of the dataset on which we'd like to guess, eventually reducing our accuracy.

varieties_less_than_five_list = df_france['variety'].value_counts()[df_france['variety'].value_counts() < 5].index.tolist()
df_france = df_france[~df_france['variety'].isin(varieties_less_than_five_list)]

df_france_subset = df_france.sample(n=500)
df_france_subset.head()
```

??? note "輸出"

    ```text
            Unnamed: 0 country                                        description  \
    95206        95206  France  Full, fat, ripe, perfumed wine that is full of...   
    66403        66403  France  For simple Chablis, this is impressive, rich, ...   
    71277        71277  France  This 50-50 blend of Marselan and Merlot opens ...   
    27484        27484  France  The medium-intense nose of this solid and easy...   
    124917      124917  France  Fresh, pure notes of Conference pear peel enti...   

                              designation  points  price      province  \
    95206   Château de Mercey Premier Cru      91   35.0      Burgundy   
    66403                         Domaine      89   26.0      Burgundy   
    71277                       La Remise      84   13.0  France Other   
    27484                Authentic & Chic      86   10.0  France Other   
    124917                            NaN      89   30.0        Alsace   

                 region_1 region_2       taster_name taster_twitter_handle  \
    95206        Mercurey      NaN        Roger Voss            @vossroger   
    66403         Chablis      NaN        Roger Voss            @vossroger   
    71277   Vin de France      NaN     Lauren Buzzeo             @laurbuzz   
    27484   Vin de France      NaN     Lauren Buzzeo             @laurbuzz   
    124917         Alsace      NaN  Anne Krebiehl MW           @AnneInVino   

                                                        title             variety  \
    95206   Antonin Rodet 2010 Château de Mercey Premier C...          Pinot Noir   
    66403               William Fèvre 2005 Domaine  (Chablis)          Chardonnay   
    71277   Domaine de la Mordorée 2014 La Remise Red (Vin...           Red Blend   
    27484   Romantic 2014 Authentic & Chic Cabernet Sauvig...  Cabernet Sauvignon   
    124917  Domaine Vincent Stoeffler 2015 Pinot Gris (Als...          Pinot Gris   

                               winery  
    95206               Antonin Rodet  
    66403               William Fèvre  
    71277      Domaine de la Mordorée  
    27484                    Romantic  
    124917  Domaine Vincent Stoeffler
    ```

把所有葡萄品種撈出來，放進 prompt，也放進 structured outputs 的 enum 清單。

```python
varieties = np.array(df_france['variety'].unique()).astype('str')
varieties
```

??? note "輸出"

    ```text
    array(['Gewürztraminer', 'Pinot Gris', 'Gamay',
           'Bordeaux-style White Blend', 'Champagne Blend', 'Chardonnay',
           'Petit Manseng', 'Riesling', 'White Blend', 'Pinot Blanc',
           'Alsace white blend', 'Bordeaux-style Red Blend', 'Malbec',
           'Tannat-Cabernet', 'Rhône-style Red Blend', 'Ugni Blanc-Colombard',
           'Savagnin', 'Pinot Noir', 'Rosé', 'Melon',
           'Rhône-style White Blend', 'Pinot Noir-Gamay', 'Colombard',
           'Chenin Blanc', 'Sylvaner', 'Sauvignon Blanc', 'Red Blend',
           'Chenin Blanc-Chardonnay', 'Cabernet Sauvignon', 'Cabernet Franc',
           'Syrah', 'Sparkling Blend', 'Duras', 'Provence red blend',
           'Tannat', 'Merlot', 'Malbec-Merlot', 'Chardonnay-Viognier',
           'Cabernet Franc-Cabernet Sauvignon', 'Muscat', 'Viognier',
           'Picpoul', 'Altesse', 'Provence white blend', 'Mondeuse',
           'Grenache-Syrah', 'G-S-M', 'Pinot Meunier', 'Cabernet-Syrah',
           'Vermentino', 'Marsanne', 'Colombard-Sauvignon Blanc',
           'Gros and Petit Manseng', 'Jacquère', 'Negrette', 'Mauzac',
           'Pinot Auxerrois', 'Grenache', 'Roussanne', 'Gros Manseng',
           'Tannat-Merlot', 'Aligoté', 'Chasselas', "Loin de l'Oeil",
           'Malbec-Tannat', 'Carignan', 'Colombard-Ugni Blanc', 'Sémillon',
           'Syrah-Grenache', 'Sciaccerellu', 'Auxerrois', 'Mourvèdre',
           'Tannat-Cabernet Franc', 'Braucol', 'Trousseau',
           'Merlot-Cabernet Sauvignon'], dtype='<U33')
    ```

## 產生 prompt

寫一個產生 prompt 的函式，先拿清單裡第一支酒試試看。

```python
def generate_prompt(row, varieties):
    # Format the varieties list as a comma-separated string
    variety_list = ', '.join(varieties)
    
    prompt = f"""
    Based on this wine review, guess the grape variety:
    This wine is produced by {row['winery']} in the {row['province']} region of {row['country']}.
    It was grown in {row['region_1']}. It is described as: "{row['description']}".
    The wine has been reviewed by {row['taster_name']} and received {row['points']} points.
    The price is {row['price']}.

    Here is a list of possible grape varieties to choose from: {variety_list}.
    
    What is the likely grape variety? Answer only with the grape variety name or blend from the list.
    """
    return prompt

# Example usage with a specific row
prompt = generate_prompt(df_france.iloc[0], varieties)
prompt
```

??? note "輸出"

    ```text
    '\n    Based on this wine review, guess the grape variety:\n    This wine is produced by Trimbach in the Alsace region of France.\n    It was grown in Alsace. It is described as: "This dry and restrained wine offers spice in profusion. Balanced with acidity and a firm texture, it\'s very much for food.".\n    The wine has been reviewed by Roger Voss and received 87 points.\n    The price is 24.0.\n\n    Here is a list of possible grape varieties to choose from: Gewürztraminer, Pinot Gris, Gamay, Bordeaux-style White Blend, Champagne Blend, Chardonnay, Petit Manseng, Riesling, White Blend, Pinot Blanc, Alsace white blend, Bordeaux-style Red Blend, Malbec, Tannat-Cabernet, Rhône-style Red Blend, Ugni Blanc-Colombard, Savagnin, Pinot Noir, Rosé, Melon, Rhône-style White Blend, Pinot Noir-Gamay, Colombard, Chenin Blanc, Sylvaner, Sauvignon Blanc, Red Blend, Chenin Blanc-Chardonnay, Cabernet Sauvignon, Cabernet Franc, Syrah, Sparkling Blend, Duras, Provence red blend, Tannat, Merlot, Malbec-Merlot, Chardonnay-Viognier, Cabernet Franc-Cabernet Sauvignon, Muscat, Viognier, Picpoul, Altesse, Provence white blend, Mondeuse, Grenache-Syrah, G-S-M, Pinot Meunier, Cabernet-Syrah, Vermentino, Marsanne, Colombard-Sauvignon Blanc, Gros and Petit Manseng, Jacquère, Negrette, Mauzac, Pinot Auxerrois, Grenache, Roussanne, Gros Manseng, Tannat-Merlot, Aligoté, Chasselas, Loin de l\'Oeil, Malbec-Tannat, Carignan, Colombard-Ugni Blanc, Sémillon, Syrah-Grenache, Sciaccerellu, Auxerrois, Mourvèdre, Tannat-Cabernet Franc, Braucol, Trousseau, Merlot-Cabernet Sauvignon.\n    \n    What is the likely grape variety? Answer only with the grape variety name or blend from the list.\n    '
    ```

在送出查詢之前，先用 tiktoken 估算 token 數和 completion 成本。這個估算不含 fine-tuning，fine-tuning 的成本還取決於訓練集大小和 epoch 數等因素。

```python
# Load encoding for the GPT-4 model
enc = tiktoken.encoding_for_model("gpt-4o")

# Initialize a variable to store the total number of tokens
total_tokens = 0

for index, row in df_france_subset.iterrows():
    prompt = generate_prompt(row, varieties)
    
    # Tokenize the input text and count tokens
    tokens = enc.encode(prompt)
    token_count = len(tokens)
    
    # Add the token count to the total
    total_tokens += token_count

print(f"Total number of tokens in the dataset: {total_tokens}")
print(f"Total number of prompts: {len(df_france_subset)}")
```

??? note "輸出"

    ```text
    Total number of tokens in the dataset: 245439
    Total number of prompts: 500
    ```

```python
# outputing cost in $ as of 2024/10/16

gpt4o_token_price = 2.50 / 1_000_000  # $2.50 per 1M tokens
gpt4o_mini_token_price = 0.150 / 1_000_000  # $0.15 per 1M tokens

total_gpt4o_cost = gpt4o_token_price*total_tokens
total_gpt4o_mini_cost = gpt4o_mini_token_price*total_tokens

print(total_gpt4o_cost)
print(total_gpt4o_mini_cost)
```

??? note "輸出"

    ```text
    0.6135975
    0.03681585
    ```

## 準備儲存 completion 的函式

回答必須是固定葡萄品種清單中的一個，所以用 structured outputs 把模型限制在這個清單內。這樣會得到一個確定的值，可以直接跟正確品種比對，也不會出現資料集以外的答案。

想多了解 Structured Outputs，可以看這份 [cookbook](https://cookbook.openai.com/examples/structured_outputs_intro) 和這份 [文件](https://platform.openai.com/docs/guides/structured-outputs/introduction)。

```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "grape-variety",
        "schema": {
            "type": "object",
            "properties": {
                "variety": {
                    "type": "string",
                    "enum": varieties.tolist()
                }
            },
            "additionalProperties": False,
            "required": ["variety"],
        },
        "strict": True
    }
}
```

要做 distillation，必須先存下大模型的所有 completion，之後才能拿給小模型當參考去 fine-tune。所以我們在 `client.chat.completions.create` 加上 `store=True`，把 gpt-4o 的 completion 存起來。

我們會把所有 completion 都存起來（包括 4o-mini 和之後的 fine-tuned 模型），這樣就能直接在 OpenAI 平台上跑 [Evals](https://platform.openai.com/docs/guides/evals)。

存的時候最好加上 metadata 標籤，之後在 OpenAI 平台上就能篩選出特定的一批 completion 來做 distillation 和 eval。

```python
# Initialize the progress index
metadata_value = "wine-distillation" # that's a funny metadata tag :-)

# Function to call the API and process the result for a single model (blocking call in this case)
def call_model(model, prompt):
    response = client.chat.completions.create(
        model=model,
        store=True,
        metadata={
            "distillation": metadata_value,
        },
        messages=[
            {
                "role": "system",
                "content": "You're a sommelier expert and you know everything about wine. You answer precisely with the name of the variety/blend."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
         response_format=response_format
    )
    return json.loads(response.choices[0].message.content.strip())['variety']
```

## 平行處理

資料量大，所以用 concurrent futures 讓 completion 平行執行。我們會遍歷 dataframe，每 20 列印一次進度，並把各模型的結果存回同一個 dataframe，欄位名稱是 `{model}-variety`。

```python
def process_example(index, row, model, df, progress_bar):
    global progress_index

    try:
        # Generate the prompt using the row
        prompt = generate_prompt(row, varieties)

        df.at[index, model + "-variety"] = call_model(model, prompt)
        
        # Update the progress bar
        progress_bar.update(1)
        
        progress_index += 1
    except Exception as e:
        print(f"Error processing model {model}: {str(e)}")

def process_dataframe(df, model):
    global progress_index
    progress_index = 1  # Reset progress index

    # Create a tqdm progress bar
    with tqdm(total=len(df), desc="Processing rows") as progress_bar:
        # Process each example concurrently using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_example, index, row, model, df, progress_bar): index for index, row in df.iterrows()}
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()  # Wait for each example to be processed
                except Exception as e:
                    print(f"Error processing example: {str(e)}")

    return df
```

整個 dataframe 跑之前，先試一下呼叫模型的函式，看輸出對不對。

```python
answer = call_model('gpt-4o', generate_prompt(df_france_subset.iloc[0], varieties))
answer
```

??? note "輸出"

    ```text
    'Pinot Noir'
    ```

很好，確認可以拿到葡萄品種。現在用 `gpt-4o` 和 `gpt-4o-mini` 處理整個資料集，比較結果。

```python
df_france_subset = process_dataframe(df_france_subset, "gpt-4o")
```

??? note "輸出"

    ```text
    Processing rows: 100%|███████████████████████████████████████████████| 500/500 [00:41<00:00, 12.09it/s]
    ```

```python
df_france_subset = process_dataframe(df_france_subset, "gpt-4o-mini")
```

??? note "輸出"

    ```text
    Processing rows: 100%|███████████████████████████████████████████████| 500/500 [01:31<00:00,  5.45it/s]
    ```

## 比較 gpt-4o 和 gpt-4o-mini

兩個模型的 chat completion 都拿到了，現在拿它們跟正確的葡萄品種比對，看猜中的準確率。這裡直接用 Python 做，因為只是簡單的字串比對。如果你的任務需要更複雜的 eval，可以用 OpenAI Evals 或我們的開源 eval 框架。

```python
models = ['gpt-4o', 'gpt-4o-mini']

def get_accuracy(model, df):
    return np.mean(df['variety'] == df[model + '-variety'])

for model in models:
    print(f"{model} accuracy: {get_accuracy(model, df_france_subset) * 100:.2f}%")
```

??? note "輸出"

    ```text
    gpt-4o accuracy: 81.80%
    gpt-4o-mini accuracy: 69.00%
    ```

可以看到 gpt-4o 找葡萄品種比 4o-mini 強（高 12.80%，相對 4o-mini 差不多高了 20%）。不禁讓人懷疑，是不是訓練 gpt-4o 的時候有讓它喝酒！

## 把 gpt-4o 的輸出蒸餾到 gpt-4o-mini

假設這個預測會常常跑，我們希望 completion 更快更便宜，但準確率不要掉。如果能把 4o 的準確率蒸餾到 4o-mini，那就太好了，對吧？來做吧！

到 OpenAI 的 Stored completions 頁面：[https://platform.openai.com/chat-completions](https://platform.openai.com/chat-completions)。

選擇 gpt-4o 這個模型（一定要選對，你不會想蒸餾剛才跑的 4o-mini 的輸出）。再選 metadata `distillation: wine-distillation`，這樣只會篩出這篇 cookbook 跑出來的 stored completion。

![Filtering out completions](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/filtering-out-completions.png)

選好 completion 之後，點右上角的「Distill」，就能用這些 completion 去 fine-tune 模型。點下去之後會自動建立跑 fine-tuning 所需的檔案。接著選 `gpt-4o-mini` 當 base model，參數保留預設（你也可以自己改，或反覆調整來提升表現）。

![Distilling modal](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/distilling.png)

fine-tuning job 開始之後，可以在 fine-tuning 頁面拿到 job ID。我們會用它來監控 job 狀態，完成後也用它取得 fine-tuned 模型的 id。

![Fine tuning job](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/fine-tuning-job.png)

```python
# copy paste your fine-tune job ID below
finetune_job = client.fine_tuning.jobs.retrieve("ftjob-pRyNWzUItmHpxmJ1TX7FOaWe")

if finetune_job.status == 'succeeded':
    fine_tuned_model = finetune_job.fine_tuned_model
    print('finetuned model: ' + fine_tuned_model)
else:
    print('finetuned job status: ' + finetune_job.status)
```

??? note "輸出"

    ```text
    finetuned model: ft:gpt-4o-mini-2024-07-18:distillation-test:wine-distillation:AIZntSyE
    ```

## 用蒸餾後的模型跑 completion

模型 fine-tune 好了，現在用它跑 completion，跟 gpt4o 和 gpt4o-mini 比準確率。
我們另外取一批不同的法國酒（因為輸出被限制在法國葡萄品種、沒有離群值，驗證資料集也要限定在這個範圍）。每個模型各跑 300 筆。

```python
validation_dataset = df_france.sample(n=300)

models.append(fine_tuned_model)

for model in models:
    another_subset = process_dataframe(validation_dataset, model)
```

??? note "輸出"

    ```text
    Processing rows: 100%|███████████████████████████████████████████████| 300/300 [00:20<00:00, 14.69it/s]
    Processing rows: 100%|███████████████████████████████████████████████| 300/300 [00:27<00:00, 10.99it/s]
    Processing rows: 100%|███████████████████████████████████████████████| 300/300 [00:37<00:00,  8.08it/s]
    ```

比較各模型的準確率

```python
for model in models:
    print(f"{model} accuracy: {get_accuracy(model, another_subset) * 100:.2f}%")
```

??? note "輸出"

    ```text
    gpt-4o accuracy: 79.67%
    gpt-4o-mini accuracy: 64.67%
    ft:gpt-4o-mini-2024-07-18:distillation-test:wine-distillation:AIZntSyE accuracy: 79.33%
    ```

比沒蒸餾的 gpt-4o-mini 相對提升了將近 **22%！🎉**

我們的 fine-tuned 模型表現比 gpt-4o-mini 好很多，而且 base model 是同一個。之後預測葡萄品種，就可以用這個模型，成本和延遲都更低。

## 重點整理

- Distillation 是用大模型的輸出當訓練資料，讓小模型在特定任務上逼近大模型的表現，省成本也省延遲。
- 蒸餾的原料是 stored completions，所以呼叫時要加 `store=True`，再用 metadata 標籤方便之後篩選。
- 分類任務用 Structured Outputs 加 enum，可以把答案鎖在固定清單，比對準確率時不用處理奇怪的輸出。
- 蒸餾時要選對來源模型，只拿大模型（gpt-4o）的 completion，不能混進小模型的。
- 評估要用沒參與訓練的另一批資料，才能公平比較三個模型。

## 練習

1. 把 enum 清單換成不限制的字串輸出（拿掉 structured outputs），看 gpt-4o-mini 的準確率會怎麼變。
2. 在產生 prompt 的函式裡拿掉產地相關欄位，重新跑 gpt-4o 和 gpt-4o-mini，看兩者差距有沒有拉大。
3. 把驗證資料從 300 筆改成別的數量，並換一個 metadata 標籤存 completion，在平台上只篩出新標籤的資料重做一次 distillation，比較結果。
