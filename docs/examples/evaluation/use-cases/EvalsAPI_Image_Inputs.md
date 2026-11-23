---
translated: true
source: examples/evaluation/use-cases/EvalsAPI_Image_Inputs.ipynb
---

# 對圖片輸入使用 Evals API

> 原文：[examples/evaluation/use-cases/EvalsAPI_Image_Inputs.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/EvalsAPI_Image_Inputs.ipynb)



## 這篇在做什麼
示範怎麼用 OpenAI Evals API 評估圖片相關任務。用 sampling 讓模型針對圖片和 prompt 產生回答，再用 model grader（LLM as a Judge）對照圖片、prompt 和參考答案打分數。

## 學完你會
- 從 Hugging Face 載入 VibeEval 資料集，整理成 Evals API 可用的 data source
- 建立含 model grader 的 eval，並用圖片 URL 當輸入
- 建立 run、輪詢結果、查看單筆 output item

## 開跑前
- OpenAI API key（要能用 Evals API）


這份 cookbook 示範怎麼用 OpenAI 的 Evals 框架處理圖片相關任務。我們用 Evals API 對模型針對圖片和 prompt 產生的回答評分：用 **sampling** 產生模型回答，用 **model grading**（LLM as a Judge）依圖片、prompt 和參考答案替回答打分數。

這個範例會評估模型能不能：
1. 針對使用者關於圖片的 prompt，**產生適當的回答**
3. **對齊參考答案**，也就是高品質回答的代表

## 安裝相依套件與設定

```python
# Install required packages
!pip install openai datasets pandas --quiet
```

```python
# Import libraries
from datasets import load_dataset
from openai import OpenAI
import os
import json
import time
import pandas as pd
```

## 資料集準備

我們用 Hugging Face 上的 [VibeEval](https://huggingface.co/datasets/RekaAI/VibeEval) 資料集，裡面有使用者 prompt、對應的圖片和參考答案。先載入資料集。

```python
dataset = load_dataset("RekaAI/VibeEval")
```

我們取出需要的欄位，整理成類似 json 的格式，作為 Evals API 的 data source。輸入圖片可以是網址，也可以是 base64 編碼字串。這裡用資料集提供的網址。 

```python
evals_data_source = []

# select the first 3 examples in the dataset to use for this cookbook
for example in dataset["test"].select(range(3)):
    evals_data_source.append({
        "item": {
            "media_url": example["media_url"], # image web URL
            "reference": example["reference"], # reference answer
            "prompt": example["prompt"] # prompt
        }
    })
```

印出 data source 清單，每個項目的格式應該類似：

```python
{
  "item": {
    "media_url": "https://storage.googleapis.com/reka-annotate.appspot.com/vibe-eval/difficulty-normal_food1_7e5c2cb9c8200d70.jpg"
    "reference": "This appears to be a classic Margherita pizza, which has the following ingredients..."
    "prompt": "What ingredients do I need to make this?"
  }
}
```

## Eval 設定

有了 data source 和任務，就可以建立 eval。OpenAI Evals API 的文件請看 [API docs](https://platform.openai.com/docs/evals/overview)。


```python
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
```

Eval 分成兩個部分：「Eval」和「Run」。在「Eval」裡，我們定義資料的預期結構和測試標準（grader）。

### Data Source Config

依照我們整理好的資料，data source config 如下：

```python
data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {
          "media_url": { "type": "string" },
          "reference": { "type": "string" },
          "prompt": { "type": "string" }
        },
        "required": ["media_url", "reference", "prompt"]
      },
    "include_sample_schema": True, # enables sampling
}
```

### 測試標準

測試標準的部分，我們設定 grader config。這個範例用的是 model grader，輸入包含圖片、參考答案和取樣得到的模型回答（在 `sample` namespace 裡），再依模型回答和參考答案的接近程度，以及回答對這段對話是否合適，輸出 0 到 1 的分數。更多 model grader 的資訊請看 [API Grader docs](https://platform.openai.com/docs/api-reference/graders)。 

資料和 grader 都做對，是評估有效的關鍵，所以你大概會需要反覆調整 grader 的 prompt。 

**注意**：圖片 url 欄位或 template 要放在 input image 物件裡才會被當成圖片，不然會被當成文字字串。 

```python
grader_config = {
	    "type": "score_model",
        "name": "Score Model Grader",
        "input":[
            {
                "role": "system",
		        "content": "You are an expert grader. Judge how well the model response suits the image and prompt as well as matches the meaniing of the reference answer. Output a score of 1 if great. If it's somewhat compatible, output a score around 0.5. Otherwise, give a score of 0."
	        },
	        {
		        "role": "user",
		        "content": [{ "type": "input_text", "text": "Prompt: {{ item.prompt }}."},
							{ "type": "input_image", "image_url": "{{ item.media_url }}", "detail": "auto" },
							{ "type": "input_text", "text": "Reference answer: {{ item.reference }}. Model response: {{ sample.output_text }}."}
				]
	        }
		],
		"pass_threshold": 0.9,
	    "range": [0, 1],
	    "model": "o4-mini" # model for grading; check that the model you use supports image inputs
	}
```

接著建立 eval 物件。

```python
eval_object = client.evals.create(
        name="Image Grading",
        data_source_config=data_source_config,
        testing_criteria=[grader_config],
    )
```

## Eval Run

建立 run 時，要傳入 eval 物件的 id、data source（就是前面整理的資料），以及取樣產生模型回答時使用的 chat message 輸入。注意 Evals API 也支援把含圖片的 stored completions 和 responses 當作 data source，詳見 [Additional Info: Logs Data Source](#additional-info-logs-data-source) 一節。

這個範例使用的 sampling message 輸入如下。

```python
sampling_messages = [{
    "role": "user",
    "type": "message",
    "content": {
        "type": "input_text",
        "text": "{{ item.prompt }}"
      }
  },
  {
    "role": "user",
    "type": "message",
    "content": {
        "type": "input_image",
        "image_url": "{{ item.media_url }}",
        "detail": "auto"
    }
  }]
```

現在啟動 eval run。

```python
eval_run = client.evals.runs.create(
        name="Image Input Eval Run",
        eval_id=eval_object.id,
        data_source={
            "type": "responses", # sample using responses API
            "source": {
                "type": "file_content",
                "content": evals_data_source
            },
            "model": "gpt-4o-mini", # model used to generate the response; check that the model you use supports image inputs
            "input_messages": {
                "type": "template", 
                "template": sampling_messages}
        }
    )
```

## 輪詢並顯示結果

run 結束後就可以看結果。你也可以在組織的 OpenAI evals dashboard 看進度和結果。 

```python
while True:
    run = client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
    if run.status == "completed" or run.status == "failed": # check if the run is finished
        output_items = list(client.evals.runs.output_items.list(
            run_id=run.id, eval_id=eval_object.id
        ))
        df = pd.DataFrame({
                "prompt": [item.datasource_item["prompt"] for item in output_items],
                "reference": [item.datasource_item["reference"] for item in output_items],
                "model_response": [item.sample.output[0].content for item in output_items],
                "score": [item.results[0].score for item in output_items],
                "passed": [item.results[0].passed for item in output_items],
                "grading_results": [item.results[0].sample["output"][0]["content"] for item in output_items]
            })
        display(df)
        break
    time.sleep(5)
```

??? note "輸出"

    ````text
                                                  prompt  \
    0  Please provide latex code to replicate this table   
    1           What ingredients do I need to make this?   
    2                   Is this safe for a vegan to eat?   

                                               reference  \
    0  Below is the latex code for your table:\n```te...   
    1  This appears to be a classic Margherita pizza,...   
    2  Based on the image, this dish appears to be a ...   

                                          model_response  score  passed  \
    0  Certainly! Below is the LaTeX code to replicat...    0.5   False   
    1  To make a classic Margherita pizza similar to ...    1.0    True   
    2  To determine if the dish is safe for a vegan, ...    1.0    True   

                                         grading_results  
    0  {"steps":[{"description":"Interpreted prompt r...  
    1  {"steps":[{"description":"Compare model's ingr...  
    2  {"steps":[{"description":"Compare model respon...
    ````

### 查看單筆 Output Item

要看完整的 output item，可以這樣做。output item 的結構定義在 API 文件[這裡](https://platform.openai.com/docs/api-reference/evals/run-output-item-object)。

```python
first_item = output_items[0]

print(json.dumps(dict(first_item), indent=2, default=str))
```

??? note "輸出"

    ````text
    {
      "id": "outputitem_687833f102ec8191a6e53a5461b970c2",
      "created_at": 1752708081,
      "datasource_item": {
        "prompt": "Please provide latex code to replicate this table",
        "media_url": "https://storage.googleapis.com/reka-annotate.appspot.com/vibe-eval/difficulty-normal_table0_b312eea68bcd0de6.png",
        "reference": "Below is the latex code for your table:\n```tex\n\\begin{table}\n\\begin{tabular}{c c c c} \\hline  & \\(S2\\) & Expert & Layman & PoelM \\\\ \\cline{2-4} \\(S1\\) & Expert & \u2013 & 54.0 & 62.7 \\\\  & Layman & 46.0 & \u2013 & 60.7 \\\\  &,PoelM,LM,LM,LM,LM,LM,,L,M,,L,M,,L,M,,L,M,,,\u2013&39.3 \\\\\n[-1ex] \\end{tabular}\n\\end{table}\n```."
      },
      "datasource_item_id": 1,
      "eval_id": "eval_687833d68e888191bc4bd8b965368f22",
      "object": "eval.run.output_item",
      "results": [
        {
          "name": "Score Model Grader-73fe48a0-8090-46eb-aa8e-d426ad074eb3",
          "sample": {
            "input": [
              {
                "role": "system",
                "content": "You are an expert grader. Judge how well the model response suits the image and prompt as well as matches the meaniing of the reference answer. Output a score of 1 if great. If it's somewhat compatible, output a score around 0.5. Otherwise, give a score of 0."
              },
              {
                "role": "user",
                "content": "Prompt: Please provide latex code to replicate this table. <image>https://storage.googleapis.com/reka-annotate.appspot.com/vibe-eval/difficulty-normal_table0_b312eea68bcd0de6.png</image> Reference answer: Below is the latex code for your table:\n```tex\n\\begin{table}\n\\begin{tabular}{c c c c} \\hline  & \\(S2\\) & Expert & Layman & PoelM \\\\ \\cline{2-4} \\(S1\\) & Expert & \u2013 & 54.0 & 62.7 \\\\  & Layman & 46.0 & \u2013 & 60.7 \\\\  &,PoelM,LM,LM,LM,LM,LM,,L,M,,L,M,,L,M,,L,M,,,\u2013&39.3 \\\\\n[-1ex] \\end{tabular}\n\\end{table}\n```.. Model response: Certainly! Below is the LaTeX code to replicate the table you provided:\n\n```latex\n\\documentclass{article}\n\\usepackage{array}\n\\usepackage{multirow}\n\\usepackage{booktabs}\n\n\\begin{document}\n\n\\begin{table}[ht]\n    \\centering\n    \\begin{tabular}{c|c|c|c}\n        \\multirow{2}{*}{S1} & \\multirow{2}{*}{S2} & \\multicolumn{3}{c}{Methods} \\\\ \n        \\cline{3-5}\n        & & Expert & Layman & PoeLM \\\\\n        \\hline\n        Expert & & - & 54.0 & 62.7 \\\\\n        Layman & & 46.0 & - & 60.7 \\\\\n        PoeLM & & 37.3 & 39.3 & - \\\\\n    \\end{tabular}\n    \\caption{Comparison of different methods}\n    \\label{tab:methods_comparison}\n\\end{table}\n\n\\end{document}\n```\n\n### Explanation:\n- The `multirow` package is used to create the multi-row header for `S1` and `S2`.\n- The `booktabs` package is used for improved table formatting (with `\\hline` for horizontal lines).\n- Adjust the table's caption and label as needed.."
              }
            ],
            "output": [
              {
                "role": "assistant",
                "content": "{\"steps\":[{\"description\":\"Assess if the provided LaTeX code correctly matches the structure of the target table, including the diagonal header, column counts, and alignment.\",\"conclusion\":\"The code fails to create the diagonal split between S1 and S2 and mismatches column counts (defines 4 columns but uses 5).\"},{\"description\":\"Check the header layout: the target table has a single diagonal cell spanning two axes and three following columns labeled Expert, Layman, PoeLM. The model uses \\\\multirow and a \\\\multicolumn block named 'Methods', which does not replicate the diagonal or correct labeling.\",\"conclusion\":\"Header structure is incorrect and does not match the prompt's table.\"},{\"description\":\"Verify the data rows: the model code includes two empty cells after S1 and before the data, misaligning all data entries relative to the intended columns.\",\"conclusion\":\"Data rows are misaligned due to incorrect column definitions.\"},{\"description\":\"Overall compatibility: the code is syntactically flawed for the target table and conceptually does not replicate the diagonal header or correct column count.\",\"conclusion\":\"The response does not satisfy the prompt.\"}],\"result\":0.0}"
              }
            ],
            "finish_reason": "stop",
            "model": "o4-mini-2025-04-16",
            "usage": {
              "total_tokens": 2185,
              "completion_tokens": 712,
              "prompt_tokens": 1473,
              "cached_tokens": 0
            },
            "error": null,
    ... (省略 15 行)
    ````

## 補充：Logs Data Source

如前面提到，Evals API 支援把含圖片的 logs（也就是 stored completions 或 responses）當作 data source。要使用這個功能，請這樣修改 eval 設定： 

建立 Eval
  - 設定 `data_source_config = { "type": "logs" }`
  - 修改 `grader_config` 的 template，改用 `{{item.input}}` 和（或）`{{sample.output_text}}`，代表 log 的輸入和輸出

建立 Eval Run
  - 在 `data_source` 欄位指定篩選條件，用來取得這次 eval run 對應的 logs（更多資訊請看[文件](https://platform.openai.com/docs/api-reference/evals/createRun)）

## 結論

這份 cookbook 介紹了用 OpenAI Evals API 評估圖片任務的流程。sampling 和 model grading 兩邊都用上圖片輸入功能，讓這個任務的評估流程更順。

期待你把它延伸到自己的圖片應用，不管是 OCR 準確度、圖片生成評分，還是其他任務！

## 重點整理
- Evals 分成「Eval」（資料結構加 grader）和「Run」（實際跑的資料與取樣設定）兩層。
- 圖片可以用網址或 base64 傳入，但要放進 input image 物件，否則會被當成純文字。
- model grader 讓 LLM 依圖片、參考答案和模型回答打分數，grader 的 prompt 值得反覆調整。
- Evals API 也能直接拿含圖片的 logs（stored completions 或 responses）當 data source。
- 資料和 grader 都做好，評估結果才可信。

## 練習
1. 只取資料集前 5 筆跑一次 run，確認整個流程通了，再放大筆數。
2. 修改 grader 的 prompt，例如加上評分標準或改分數範圍，比較分數分布的變化。
3. 把 data source 換成 `logs` 類型，改用 `{{item.input}}` 和 `{{sample.output_text}}` 做 template。
