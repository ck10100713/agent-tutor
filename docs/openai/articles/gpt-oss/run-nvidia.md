---
translated: true
status: deprecated
tags:
- 原文已封存
source: articles/gpt-oss/run-nvidia.ipynb
---

# 用 NVIDIA TensorRT-LLM 跑 gpt-oss-20b

> 原文：[articles/gpt-oss/run-nvidia.ipynb](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/run-nvidia.ipynb)



## 這篇在做什麼
一步步示範怎麼用 NVIDIA TensorRT-LLM 在 GPU 上高效跑 `gpt-oss-20b`。從拉 Docker container、確認安裝，到用 Python API 下載權重、自動建 engine 並產生文字。

## 學完你會
- 用 NGC 預建 container 或從原始碼 build 的方式準備 TensorRT-LLM 環境。
- 用 `tensorrt_llm.LLM` API 從 Hugging Face 下載模型，並自動建出對應你 GPU 架構的 engine。
- 跑一次文字生成確認一切正常，並知道後續可以做 benchmark、quantization 和部署。

## 開跑前
- 需要至少 20 GB VRAM 的 NVIDIA GPU（建議 Hopper、Blackwell、RTX PRO 或 RTX 50 系列）。
- 需要 CUDA Toolkit 12.8 以上和 Python 3.12 以上。
- 需要 Hugging Face token（`HF_TOKEN`）下載模型。
- 沒有 GPU 的話可以用 NVIDIA Brev 租一台。


這份 notebook 一步步說明怎麼用 NVIDIA 的 TensorRT-LLM 優化 `gpt-oss` 模型，做高效能推論。TensorRT-LLM 提供好用的 Python API 來定義大型語言模型（LLM），並支援最先進的優化，讓推論在 NVIDIA GPU 上有效率地執行。TensorRT-LLM 也包含建立 Python 和 C++ runtime 的元件，以高效能的方式編排推論執行。


TensorRT-LLM 支援這兩個模型：
- `gpt-oss-20b`
- `gpt-oss-120b`

這份指南會跑 `gpt-oss-20b`，如果想試比較大的模型或需要更多客製化，看[這份](https://github.com/NVIDIA/TensorRT-LLM/blob/main/docs/source/blogs/tech_blog/blog9_Deploying_GPT_OSS_on_TRTLLM.md)部署指南。

注意：你的輸入 prompt 應該使用 [harmony response](http://cookbook.openai.com/articles/openai-harmony) 格式，模型才能正常運作，不過這份指南不要求這點。

#### 在 NVIDIA Brev 上啟動
用 [NVIDIA Brev](https://developer.nvidia.com/brev) 可以簡化環境設定。點下面的按鈕，在 Brev instance 上啟動這個專案，必要的依賴都已經預先設定好。

部署完成後，點 "Open Notebook" 按鈕就能開始這份指南

[![Launch on Brev](https://brev-assets.s3.us-west-1.amazonaws.com/nv-lb-dark.svg)](https://brev.nvidia.com/launchable/deploy?launchableID=env-30i1YjHsRWT109HL6eYxLUeHIwF)

## 前置需求

### 硬體
要跑 gpt-oss-20b 模型，你需要至少 20 GB VRAM 的 NVIDIA GPU。

建議的 GPU：NVIDIA Hopper（例如 H100、H200）、NVIDIA Blackwell（例如 B100、B200）、NVIDIA RTX PRO、NVIDIA RTX 50 系列（例如 RTX 5090）。

### 軟體
- CUDA Toolkit 12.8 或更新版本
- Python 3.12 或更新版本

## 安裝 TensorRT-LLM

安裝 TensorRT-LLM 有很多種方式。這份指南會介紹用 NVIDIA NGC 的預建 Docker container，以及從原始碼 build。

如果你用 NVIDIA Brev，可以跳過這一節。

## 使用 NVIDIA NGC

從 [NVIDIA NGC](https://www.nvidia.com/en-us/gpu-cloud/) 拉 GPT-OSS 專用的預建 [TensorRT-LLM container](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tensorrt-llm/containers/release/tags)。
這是最簡單的起手方式，也確保所有依賴都包含在內。

```bash
docker pull nvcr.io/nvidia/tensorrt-llm/release:gpt-oss-dev
docker run --gpus all -it --rm -v $(pwd):/workspace nvcr.io/nvidia/tensorrt-llm/release:gpt-oss-dev
```

## 使用 Docker（從原始碼 Build）

或者你可以從原始碼 build TensorRT-LLM container。
如果你想修改原始碼或使用自訂 branch，這個做法就很有用。
詳細說明看[官方文件](https://github.com/NVIDIA/TensorRT-LLM/tree/feat/gpt-oss/docker)。

TensorRT-LLM 很快就能用 pip 安裝

> GPU 架構注意事項：第一次跑模型時，TensorRT-LLM 會針對你特定的 GPU 架構（例如 Hopper、Ada 或 Blackwell）build 一個優化過的 engine。如果你看到警告說你 GPU 的 CUDA capability（例如 sm_90、sm_120）和 PyTorch 安裝不相容，請確保你有最新的 NVIDIA driver，以及和你的 PyTorch 版本相符的 CUDA Toolkit 版本。

# 確認 TensorRT-LLM 安裝

```python
from tensorrt_llm import LLM, SamplingParams
```

# 使用 TensorRT-LLM Python API

下一個 code cell 會示範怎麼用 TensorRT-LLM Python API 來：
1. 從 Hugging Face 下載指定的模型權重（用你的 HF_TOKEN 驗證）。
2. 如果還沒有，自動為你的 GPU 架構 build TensorRT engine。
3. 載入模型並準備好做推論。
4. 跑一個簡單的文字生成範例，確認一切正常。

**注意**：第一次執行可能要幾分鐘，因為要下載模型和 build engine。
之後會快很多，因為 engine 會被快取。

```python
llm = LLM(model="openai/gpt-oss-20b")
```

```python
prompts = ["Hello, my name is", "The capital of France is"]
sampling_params = SamplingParams(temperature=0.8, top_p=0.95)
for output in llm.generate(prompts, sampling_params):
    print(f"Prompt: {output.prompt!r}, Generated text: {output.outputs[0].text!r}")
```

# 結論與下一步
恭喜！你已經用 TensorRT-LLM Python API 成功優化並跑起一個大型語言模型。

在這份 notebook 裡，你學到了：
- 用必要的依賴設定好環境。
- 用 `tensorrt_llm.LLM` API 從 Hugging Face Hub 下載模型。
- 自動 build 出針對你 GPU 量身打造的高效能 TensorRT engine。
- 用優化後的模型做推論。


你可以探索更進階的功能，進一步提升效能和效率：

- Benchmarking：試著跑 [benchmark](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/benchmarking-default-performance.html#benchmarking-with-trtllm-bench)，比較 TensorRT-LLM engine 和原始 Hugging Face 模型的延遲與吞吐量。你可以對更多 prompt 迭代並量測執行時間。

- Quantization：TensorRT-LLM [支援](https://github.com/NVIDIA/TensorRT-Model-Optimizer)多種量化技術（像 INT8 或 FP8），在對準確度影響很小的情況下縮小模型並加速推論。這對在資源受限的硬體上部署模型是很強的功能。

- 用 NVIDIA Dynamo 部署：在 production 環境，你可以用 [NVIDIA Dynamo](https://docs.nvidia.com/dynamo/latest/) 部署你的 TensorRT-LLM engine，做到穩健、可擴展、多模型的 serving。



## 重點整理
- TensorRT-LLM 會針對你的 GPU 架構編譯專屬的 engine，所以第一次跑比較慢，之後有快取。
- gpt-oss-20b 至少要 20 GB VRAM，硬體是主要門檻。
- NGC 預建 container 是最省事的安裝方式，從原始碼 build 適合要改程式碼的人。
- 用高階的 `LLM` API，下載、建 engine、載入、推論都一個物件搞定。
- 想再榨效能，下一步是 benchmark、quantization，再到 Dynamo 做 production serving。

## 練習
1. 在生成的 code cell 改 prompt，換成你自己的問題，確認輸出正常。
2. 把 prompt 改成一次傳入多個（例如 10 個），用 `time` 量測總耗時並算出平均每個 prompt 的時間。
3. 改用 harmony response 格式包裝 prompt，比較輸出和直接傳純文字有什麼不同。
