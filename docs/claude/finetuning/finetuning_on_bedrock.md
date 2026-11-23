---
translated: true
source: finetuning/finetuning_on_bedrock.ipynb
---

# 在 Bedrock 上 finetune Claude 3 Haiku

> 原文：[finetuning/finetuning_on_bedrock.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/finetuning/finetuning_on_bedrock.ipynb)

一步一步帶你在 Amazon Bedrock 上針對自訂任務 finetune Claude 3 Haiku。

## 這篇在做什麼

帶你走完在 Amazon Bedrock 上 finetune Claude 3 Haiku 的流程：準備 JSONL 資料集、上傳到 S3、用 `boto3` 啟動 finetuning job，最後呼叫 finetune 好的模型。範例資料集會教模型把所有問題都用 JSON 回答。

## 學完你會

- 照 Bedrock 的格式規則準備 JSONL 訓練資料
- 把資料上傳到 S3，並用 `boto3` 啟動和查詢 finetuning job
- 用 Provisioned Throughput 部署 finetune 後的模型並呼叫它

## 開跑前

- 需要有 Bedrock 權限的 AWS 帳號
- 一份資料集（也可以用這裡提供的範例資料集）
- [一個有權限存取你放訓練資料的 S3 bucket 的 service role](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-iam-role.html)
- finetune 完後用 Provisioned Throughput 託管模型會產生費用

這份 notebook 會帶你走完在 Amazon Bedrock 上 finetune Claude 3 Haiku 的流程

## 你需要準備
- 有 Bedrock 存取權限的 AWS 帳號
- 一份資料集（或使用這裡提供的範例資料集）
- [一個有權限存取你放訓練資料的 s3 bucket 的 service role](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-iam-role.html)

## 安裝相依套件

```python
%pip install boto3
```

```python
import boto3
```

## 準備資料集
Bedrock finetuning 用的資料集必須是 JSONL 檔（也就是每一行是一個 json 物件的檔案）。

JSONL 檔的每一行都要是下面這個結構的 JSON 物件：

```
{
  "system": "<optional_system_message>",
  "messages": [
    {"role": "user", "content": "user message"},
    {"role": "assistant", "content": "assistant response"},
    ...
  ]
}
```

- `system` 欄位是選填。
- 至少要有兩則 message。
- 第一則 message 必須來自 "user"。
- 最後一則 message 必須來自 "assistant"。
- user 和 assistant 的 message 必須交替出現。
- 不允許有多餘的 key。


## 範例資料集：JSON Mode
我們附了一份範例資料集，用來教模型把所有問題都用 JSON 回答。資料集長這樣：

```python
import json

sample_dataset = []
dataset_path = "datasets/json_mode_dataset.jsonl"
with open(dataset_path) as f:
    for line in f:
        sample_dataset.append(json.loads(line))

print(json.dumps(sample_dataset[0], indent=2))
```

## 把資料集上傳到 S3
finetuning 用的資料集必須放在 s3 上；這個 demo 會把範例資料集寫進你自己控制的 s3 bucket

```python
bucket_name = "YOUR_BUCKET_NAME"
s3_path = "json_mode_dataset.jsonl"

s3 = boto3.client("s3")
s3.upload_file(dataset_path, bucket_name, s3_path)
```

## 啟動 Bedrock finetuning job

資料集準備好之後，就能用 `boto3` 啟動 finetuning job。先設定 job 的幾個參數：

```python
# Configuration
job_name = "anthropic-finetuning-cookbook-training"
custom_model_name = "anthropic_finetuning_cookbook"
role = "YOUR_AWS_SERVICE_ROLE_ARN"
output_path = f"s3://{bucket_name}/finetuning_example_results/"
base_model_id = (
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0:200k"
)

# Hyperparameters
epoch_count = 5
batch_size = 4
learning_rate_multiplier = 1.0
```

然後用 `boto3` 啟動 job

```python
bedrock = boto3.client(service_name="bedrock")
bedrock_runtime = boto3.client(service_name="bedrock-runtime")

bedrock.create_model_customization_job(
    customizationType="FINE_TUNING",
    jobName=job_name,
    customModelName=custom_model_name,
    roleArn=role,
    baseModelIdentifier=base_model_id,
    hyperParameters={
        "epochCount": f"{epoch_count}",
        "batchSize": f"{batch_size}",
        "learningRateMultiplier": f"{learning_rate_multiplier}",
    },
    trainingDataConfig={"s3Uri": f"s3://{bucket_name}/{s3_path}"},
    outputDataConfig={"s3Uri": output_path},
)
```

訓練期間可以用這個檢查 job 的狀態：

```python
# Check for the job status
status = bedrock.get_model_customization_job(jobIdentifier=job_name)["status"]
```

## 使用你 finetune 好的模型！

要使用 finetune 好的模型，[你需要用 Amazon Bedrock 的 Provisioned Throughput 託管它](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-use.html)。模型在 Provisioned Throughput 準備好之後，就能透過 Bedrock API 呼叫。

```python
provisioned_throughput_arn = "YOUR_PROVISIONED_THROUGHPUT_ARN"
```

```python
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
body = json.dumps(
    {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "system": "JSON Mode: Enabled",
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "What is a large language model?"}],
            }
        ],
    }
)
response = bedrock_runtime.invoke_model(modelId=provisioned_throughput_arn, body=body)
body = json.loads(response["body"].read().decode("utf-8"))
```

```python
print(body["content"][0]["text"])
```

## 重點整理

- Bedrock finetuning 的資料是 JSONL，每行一段對話，格式規則很嚴格（交替、首尾角色、不能有多餘 key）。
- 流程是準備資料、傳到 S3、啟動 job、等訓練、再部署。
- finetune 後的模型要透過 Provisioned Throughput 託管才能呼叫，要留意成本。
- 範例資料集只教「用 JSON 回答」這種格式行為，finetuning 很適合教風格和格式。

## 練習

1. 檢查範例資料集的每一行是否符合規則，寫一個小腳本驗證。
2. 把範例資料集換成你自己的 20 筆問答（格式要求不變）。
3. 調整 job 參數（例如 epoch 數），重新啟動 job 並比較結果。
