---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/use-cases/EvalsAPI_Audio_Inputs.ipynb
---

# 用 Evals API 評測音訊輸入

> 原文：[examples/evaluation/use-cases/EvalsAPI_Audio_Inputs.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/EvalsAPI_Audio_Inputs.ipynb)

## 這篇在做什麼

示範怎麼用 OpenAI 的 Evals API 評測音訊任務。流程是用 sampling 讓模型針對音訊問題產生音訊回答，再用 model grader 拿標準答案去打分。整個過程不用先轉成文字，直接拿原始音訊進、音訊出。

## 學完你會

- 把 Hugging Face 上的音訊資料集轉成 base64，整理成 Evals API 能吃的資料來源
- 設定 `score_model` grader（或 `string_check` grader），建立 eval 和 run
- 輪詢 run 的結果，並查看單筆 output item

## 開跑前

- 需要 `OPENAI_API_KEY`，Evals 與音訊模型會產生費用
- 資料集來自 Hugging Face，需要能連網下載


之前要評測語音對話，得先把音訊轉成文字。現在可以直接用原始音訊，模型也能用音訊回答。這比較貼近客服這類使用者跟 agent 都用語音的場景。這篇用音訊模型當 grader 來評音訊回答；你也可以改用音訊的文字逐字稿，搭配現有的文字 grader，或兩種一起用。

這個例子要評估模型在兩件事上的表現：
1. 針對一段音訊訊息，對使用者的提問**產生合適的回答**
2. 回答**符合參考答案**這種高品質回應

## 安裝套件與設定

```python
# Install required packages
%pip install openai datasets pandas soundfile torch torchcodec pydub jiwer --quiet
```

```python
# Import libraries
from datasets import load_dataset, Audio
from openai import OpenAI
import base64
import os
import json
import time
import io
import soundfile as sf
import numpy as np
import pandas as pd
```

## 準備資料集

我們用 Hugging Face 上的 [big_bench_audio](https://huggingface.co/datasets/ArtificialAnalysis/big_bench_audio) 資料集。它是 Big Bench Hard 部分題目的音訊版，用來評估支援音訊輸入的模型的推理能力。每筆資料有一段描述邏輯問題的音訊、一個分類，和一個正式答案。

```python
dataset = load_dataset("ArtificialAnalysis/big_bench_audio")
# Ensure audio column is decoded into a dict with 'array' and 'sampling_rate'
dataset = dataset.cast_column("audio", Audio(decode=True))
```

我們把需要的欄位取出來，整理成類似 JSON 的格式，當作 Evals API 的資料來源。輸入音訊必須是 base64 字串，所以要先讀音訊檔再轉成 base64。

注意：音訊模型目前支援 WAV、MP3、FLAC、Opus 或 PCM16 格式，詳見 [audio inputs](https://platform.openai.com/docs/api-reference/chat/create#chat_create-audio)。

```python
# Audio helpers: file/array to base64
def get_base64(audio_path_or_datauri: str) -> str:
    if audio_path_or_datauri.startswith("data:"):
        # Already base64, just strip prefix
        return audio_path_or_datauri.split(",", 1)[1]
    else:
        # It's a real file path
        with open(audio_path_or_datauri, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")


def audio_to_base64(audio_val) -> str:
    """
    Accepts various Hugging Face audio representations and returns base64-encoded WAV bytes (no data: prefix).
    Handles:
      - dict or mapping-like with 'path'
      - decoded dict with 'array' and 'sampling_rate'
      - torchcodec AudioDecoder (mapping-like access via ['path'] or ['array'])
      - raw bytes
    """
    # Try to get a file path first
    try:
        path = None
        if isinstance(audio_val, dict) and "path" in audio_val:
            path = audio_val["path"]
        else:
            # Mapping-like access
            try:
                path = audio_val["path"]  # works for many decoder objects
            except Exception:
                path = getattr(audio_val, "path", None)
        if isinstance(path, str) and os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        pass

    # Fallback: use array + sampling_rate and render to WAV in-memory
    try:
        array = None
        sampling_rate = None
        try:
            array = audio_val["array"]
            sampling_rate = audio_val["sampling_rate"]
        except Exception:
            array = getattr(audio_val, "array", None)
            sampling_rate = getattr(audio_val, "sampling_rate", None)
        if array is not None and sampling_rate is not None:
            audio_np = np.array(array)
            buf = io.BytesIO()
            sf.write(buf, audio_np, int(sampling_rate), format="WAV")
            return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        pass

    if isinstance(audio_val, (bytes, bytearray)):
        return base64.b64encode(audio_val).decode("ascii")

    raise ValueError("Unsupported audio value; could not convert to base64")
```

```python
evals_data_source = []
audio_base64 = None

# Will use the first 3 examples for testing
for example in dataset["train"].select(range(3)):
    audio_val = example["audio"]
    try:
        audio_base64 = audio_to_base64(audio_val)
    except Exception as e:
        print(f"Warning: could not encode audio for id={example['id']}: {e}")
        audio_base64 = None
    evals_data_source.append({
        "item": {
            "id": example["id"],
            "category": example["category"],
            "official_answer": example["official_answer"],
            "audio_base64": audio_base64
        }
    })
```

印出資料來源清單的話，每個項目長得類似這樣：

```python
{
  "item": {
    "id": 0
    "category": "formal_fallacies"
    "official_answer": "invalid"
    "audio_base64": "UklGRjrODwBXQVZFZm10IBAAAAABAAEAIlYAAESsA..."
  }
}
```

## Eval 設定

資料來源和任務都有了，接著建立 eval。Evals API 的文件在 [API docs](https://platform.openai.com/docs/guides/evals)。


```python
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)
```

音訊輸入很大，所以要先把範例存成檔案，再上傳到 API。

```python
# Save the examples to a file
file_name = "evals_data_source.json"
with open(file_name, "w", encoding="utf-8") as f:
    for obj in evals_data_source:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

# Upload the file to the API
file = client.files.create(
    file=open(file_name, "rb"),
    purpose="evals"
)
```

Evals 分成兩部分：「Eval」和「Run」。在 Eval 裡定義資料的預期結構和測試標準（grader）。

### 資料來源設定

依照我們整理好的資料，資料來源設定如下：

```python
data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {
          "id": { "type": "integer" },
          "category": { "type": "string" },
          "official_answer": { "type": "string" },
          "audio_base64": { "type": "string" }
        },
        "required": ["id", "category", "official_answer", "audio_base64"]
      },
    "include_sample_schema": True, # enables sampling
}
```

### 測試標準

測試標準就是 grader 的設定。這裡用 `score_model` grader，它會拿正式答案和取樣出來的模型回應（在 `sample` namespace 裡），依回應是否符合正式答案輸出 0 或 1。回應同時包含音訊和音訊的文字逐字稿，這裡 grader 用的是音訊。更多 grader 資訊看 [API Grader docs](https://platform.openai.com/docs/api-reference/graders)。

資料和 grader 都設對，評測才有效。grader 的 prompt 通常需要反覆調整。

```python
grader_config = {
  "type": "score_model",
  "name": "Reference answer audio model grader",
  "model": "gpt-audio",
  "input": [
        {
            "role": "system",
            "content": 'You are a helpful assistant that evaluates audio clips to judge whether they match a provided reference answer. The audio clip is the model''s response to the question. Respond ONLY with a single JSON object matching: {"steps":[{"description":"string","conclusion":"string"}],"result":number}. Do not include any extra text. result must be a float in [0.0, 1.0].'
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Evaluate this audio clip to see if it reaches the same conclusion as the reference answer. Reference answer: {{item.official_answer}}",
                },
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "{{ sample.output_audio.data }}",
                        "format": "wav",
                    },
                },
            ],
        },
    ],
          "range": [0, 1],
          "pass_threshold": 0.6,
}
```

另一種做法是用 `string_check` grader，它同樣拿正式答案和取樣的模型回應，依回應是否包含參考答案輸出 0 到 1 的分數。這時 grader 用的是文字逐字稿。

```python
grader_config = {
  "type": "string_check",
  "name": "String check grader",
  "input": "{{sample.output_text}}",
  "reference": "{{item.official_answer}}",
  "operation": "ilike"
}
```

接著建立 eval 物件。

```python
eval_object = client.evals.create(
        name="Audio Grading Cookbook",
        data_source_config=data_source_config,
        testing_criteria=[grader_config],
    )
```

## 執行 Eval

建立 run 時，要傳入 eval 物件的 id、資料來源（就是前面整理好的資料），以及用來取樣產生模型回應的 chat message 輸入。

這個例子用的取樣訊息如下：

```python
sampling_messages = [
    {
        "role": "system",
        "content": "You are a helpful and obedient assistant that can answer questions with audio input. You will be given an audio input containing a question to answer."
    },
    {
        "role": "user",
        "type": "message",
        "content": {
            "type": "input_text",
            "text": "Answer the following question by replying with brief reasoning statements and a conclusion with a single word answer: 'valid' or 'invalid'."
        }
    },
    {
        "role": "user",
        "type": "message",
        "content": {
            "type": "input_audio",
            "input_audio": {
                "data": "{{ item.audio_base64 }}",
                "format": "wav"
            }
        }
    }]
```

現在啟動 eval run。

```python
eval_run = client.evals.runs.create(
        name="Audio Input Eval Run",
        eval_id=eval_object.id,
        data_source={
            "type": "completions", # sample using completions API; responses API is not supported for audio inputs
            "source": {
                "type": "file_id",
                "id": file.id
            },
            "model": "gpt-audio", # model used to generate the response; check that the model you use supports audio inputs
            "sampling_params": {
                "temperature": 0.0,
            },
            "input_messages": {
                "type": "template", 
                "template": sampling_messages},
            "modalities": ["audio", "text"],
        },
    )
```

## 輪詢並顯示結果

run 跑完就能看結果。你也可以到組織的 OpenAI Evals dashboard 看進度和結果。

```python
while True:
    run = client.evals.runs.retrieve(run_id=eval_run.id, eval_id=eval_object.id)
    if run.status == "completed":
        output_items = list(client.evals.runs.output_items.list(
            run_id=run.id, eval_id=eval_object.id
        ))
        df = pd.DataFrame({
                "id": [item.datasource_item["id"]for item in output_items],
                "category": [item.datasource_item["category"] for item in output_items],
                "official_answer": [item.datasource_item["official_answer"] for item in output_items],
                "model_response": [item.sample.output[0].content for item in output_items],
                "grading_results": ["passed" if item.results[0].passed else "failed"
                                    for item in output_items]
            })
        display(df)
        break
    if run.status == "failed":
        print(run.error)
        break
    time.sleep(5)
```

### 查看單筆 output item

要看完整的 output item 可以這樣做。output item 的結構定義在 API 文件的[這裡](https://platform.openai.com/docs/api-reference/evals/run-output-item-object)。

```python
first_item = output_items[0]

print(json.dumps(dict(first_item), indent=2, default=str))
```

## 結論

這篇走了一遍用 OpenAI Evals API 評測原生音訊輸入的流程，並示範用 score model grader 評分音訊回答。
### 下一步
- 把這個範例換成你自己的使用情境。
- 音訊檔很大的話，可以用 [uploads API](https://platform.openai.com/docs/api-reference/uploads/create)，支援到 8 GB。
- 到 [Evals dashboard](https://platform.openai.com/evaluations) 視覺化輸出並看評測表現。


## 重點整理

- 音訊 eval 可以直接用原始音訊進、音訊出，不必先轉文字，比較貼近真實語音場景。
- 輸入音訊要轉成 base64，資料大就存檔再上傳。
- Eval 定義資料結構和 grader，Run 才帶資料來源和取樣訊息去執行。
- `score_model` grader 用音訊打分，`string_check` grader 則用逐字稿比對，可以擇一或搭配。
- grader 的 prompt 要反覆調整，不然分數沒意義。

## 練習

1. 把資料集只取前 3 筆跑一次 run，確認整個流程通，再看 dashboard 上的結果。
2. 把 `score_model` grader 換成 `string_check` grader，比較兩種分數有沒有差。
3. 修改 `score_model` grader 的評分 prompt，例如改成 0 到 5 分的量表，看分數分布怎麼變。
