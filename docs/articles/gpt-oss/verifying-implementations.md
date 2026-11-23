---
translated: true
source: articles/gpt-oss/verifying-implementations.md
---
# 驗證 gpt-oss 的實作

> 原文：[articles/gpt-oss/verifying-implementations.md](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/verifying-implementations.md)

## 這篇在做什麼

gpt-oss 模型帶來不少開源模型生態裡的新概念，實作不一定一次到位。這篇給做 inference 服務的開發者，或想檢驗某個 provider 實作的人，一套驗證方法：先用 smoke test 檢查 tool calling 和 API 格式，再用 evals 驗證輸出準確度。

## 學完你會

- 說明 gpt-oss 為什麼跟一般開源模型不一樣（harmony 格式、tool call 之間的 CoT、MXFP4 的 MoE 權重）
- 知道 Responses API 和 Chat Completions 各自該怎麼回傳 raw CoT
- 用 gpt-oss repo 的 Node.js 腳本跑 tool calling 測試，並用 `gpt_oss/evals` 跑 AIME、GPQA 等 eval

## 開跑前

- 要裝 Node.js 或類似 runtime
- 要有你想測的 provider 的 API 端點（和對應的 key）
- 跑 evals 會花算力或 API 費用

[OpenAI gpt-oss 模型](https://openai.com/open-models)為開源模型生態帶來很多新概念，而且[要讓它們照預期運作可能要花一點時間](https://x.com/ClementDelangue/status/1953119901649891367)。這份指南是要幫做 inference 解決方案的開發者驗證自己的實作，也給想自己測試任何 provider 實作、建立信心的開發者。

## 為什麼實作 gpt-oss 模型不太一樣？

這些新模型的行為，跟我們其他一些 OpenAI 模型比較像，而不是現有的開源模型。幾個例子：

1. **Harmony response format。** 這些模型是用我們的 [OpenAI harmony format](https://cookbook.openai.com/articles/openai-harmony) 來組織對話訓練的。一般 API 開發者大多不需要處理 harmony，但提供 Chat Completions 相容、Responses 相容或其他 inference API 的 provider，需要把輸入正確對應到 OpenAI harmony format。如果模型收到的 prompt 格式不對，會連鎖產生各種生成問題，至少 function calling 的表現會變差。
2. **處理 tool call 之間的 chain of thought（CoT）。** 這些模型可以在 CoT 當中執行 tool call。結果是，模型在後續的取樣中需要收到 CoT，直到得出最終回應。也就是說，raw CoT 不該顯示給終端使用者，但 API 應該把它回傳，讓開發者能連同 tool call 和 tool output 一起傳回去。[詳情請看這份獨立的指南](https://cookbook.openai.com/articles/gpt-oss/handle-raw-cot)。
3. **實際 inference 程式碼的差異。** 我們只用 MXFP4 格式發佈 mixture-of-experts（MoE）權重。這個格式還算新，加上其他架構上的決定，為其他開源模型寫的現有 inference 程式碼都得改過才能支援 gpt-oss。因此我們發佈了基本（未最佳化）的 [PyTorch 實作](https://github.com/openai/gpt-oss/tree/main/gpt_oss/torch)和[更最佳化的 Triton 實作](https://github.com/openai/gpt-oss/tree/main/gpt_oss/triton)。另外我們也驗證了 [vLLM 實作](https://github.com/vllm-project/vllm/blob/7e3a8dc90670fd312ce1e0d4eba9bf11c571e3ad/vllm/model_executor/models/gpt_oss.py)的正確性。希望這些能當作其他實作的教材。

## API 設計

### Responses API

為了最佳效能，我們建議 inference provider 實作我們的 Responses API 格式，因為這個 API 的形狀是專門為這類行為設計的：輸出 raw CoT 加上摘要過的 CoT（顯示給使用者），還有 tool call，而不用在格式上硬加額外屬性。要達到準確的效能，最重要的  
一點是把 raw CoT 放在 `output` 裡回傳。

為此我們在 Responses API 的 `reasoning` item 加了新的 `content` 陣列。Raw CoT 應該包在 `reasoning_text` 類型的元素裡，讓整個 output item 長得像這樣：

```
{
  "type": "reasoning",
  "id": "item_67ccd2bf17f0819081ff3bb2cf6508e60bb6a6b452d3795b",
  "status": "completed",
  "summary": [
    /* optional summary elements */
  ],
  "content": [
    {
      "type": "reasoning_text",
      "text": "The user needs to know the weather, I will call the get_weather tool."
    }
  ]
}
```

這些 item 應該在後續的輪次被接收，然後依照 [raw CoT 處理指南](https://cookbook.openai.com/articles/gpt-oss/handle-raw-cot)的說明，插回 harmony 格式的 prompt。

[完整規格請看 Responses API 文件](https://platform.openai.com/docs/api-reference/responses/create)。

### Chat Completions

很多 provider 提供 Chat Completions 相容的 API。雖然我們發佈的 API reference 文件還沒有加入取得 raw CoT 的方式，但透過 Chat Completions 相容 API 提供 gpt-oss 模型的 provider，仍然應該在 message 裡回傳 CoT，也要讓開發者有辦法把它傳回去。

目前社群裡沒有公認的規格，message 上的通用屬性不是 `reasoning` 就是 `reasoning_content`。**為了相容 OpenAI Agents SDK 之類的 client，我們建議在 Chat Completions 裡用 `reasoning` 欄位當作 raw CoT 的主要屬性**。

## 快速驗證 tool calling 和 API 格式

要驗證某個 provider 能不能用，可以用我們發佈在 [gpt-oss GitHub repository](https://github.com/openai/gpt-oss) 裡的 Node.js 腳本，它也能用來跑其他 eval。要跑測試，你需要安裝 [Node.js](http://nodejs.org/) 或類似的 runtime。

這些測試會對你要測的 Responses API 或 Chat Completions API 送出一系列以 tool/function calling 為主的請求。之後會評估是否呼叫了正確的 tool，以及 API 的格式是否正確。

這大致上是 smoke test，但應該能很好地指出 API 是否跟我們的 SDK 相容、能不能處理基本的 function calling。它不保證 inference 實作完全準確（準確度請看下面的 evals 一節），也不保證完全相容 OpenAI API。不過它們仍然是發現重大實作問題的有用指標。

要執行測試套件，跑下面的指令：

```shell
# clone the repository
git clone https://github.com/openai/gpt-oss.git

# go into the compatibility test directory
cd gpt-oss/compatibility-test/

# install the dependencies
npm install

# change the provider config in providers.ts to add your provider

# run the tests
npm start -- --provider <your-provider-name>
```

之後你會收到 API 實作的結果，以及 function call 表現的細節。

如果測試成功，輸出應該顯示 0 個無效請求，而且 pass@k 和 pass^k 都超過 90%。這代表實作很可能是對的。為了完全確定，你還是應該照下面說明檢查 evals。

想看每個回應的細節，可以看目錄裡產生的 `jsonl` 檔。

你也可以用 `DEBUG=openai-agents:openai npm start -- --provider <provider-name>` 開啟 debug 模式，檢視實際的請求 payload，不過可能會很吵。只跑一個測試的話，加上 `-n 1` 旗標，除錯比較容易。要測試 streaming 事件，可以用 `--streaming`。

## 用 evals 驗證正確性

Artificial Analysis 團隊正在對各個 provider 跑 AIME 和 GPQA evals。如果你不確定某個 provider，[到 Artificial Analysis 看最新的指標](https://artificialanalysis.ai/models/gpt-oss-120b/providers#evaluations)。

為了保險，你應該考慮自己跑 evals。要跑自己的 evals，可以在上面測試所在的同一個 repository 找到 `gpt_oss/evals` 資料夾，裡面有我們用來驗證 vLLM 實作和我們自己一些參考實作的測試 harness，涵蓋 AIME（每題 16 次嘗試）、GPQA（每題 8 次嘗試）和 Healthbench（每題 1 次嘗試）。你可以用同一個腳本測試你的實作。

測試 Responses API 相容的 API：

```bash
python -m gpt_oss.evals --base-url http://localhost:8000/v1 --eval aime25 --sampler responses --model openai/gpt-oss-120b --reasoning-effort high
```

測試 Chat Completions API 相容的 API：

```bash
python -m gpt_oss.evals --base-url http://localhost:8000/v1 --eval aime25 --sampler chat_completions --model openai/gpt-oss-120b --reasoning-effort high
```

如果你得到的 benchmark 結果跟我們發佈的相近，而且上面的 function calling 測試也成功，你的 gpt-oss 實作很可能是正確的。

## 重點整理

- gpt-oss 的行為更像 OpenAI 自家模型：用 harmony 格式、在 tool call 之間用 CoT、MoE 權重是 MXFP4，所以不能直接套用既有開源模型的 inference 程式碼。
- Raw CoT 不顯示給終端使用者，但 API 必須回傳，讓開發者在下一輪傳回來。
- Responses API 用 `reasoning` item 的 `content` 加 `reasoning_text`，Chat Completions 建議用 `reasoning` 欄位。
- 驗證分兩層：tool calling 的 smoke test 抓格式和基本呼叫問題，evals 驗證輸出準確度，兩者都過才算比較有把握。

## 練習

1. 照頁面指令對一個你有權限的 provider 跑 tool calling 測試，只加 `-n 1` 跑一個測試，看輸出的 `jsonl` 長什麼樣子。
2. 加上 `--streaming` 再跑一次，並用 `DEBUG=openai-agents:openai` 比較實際送出的請求 payload。
3. 用 `gpt_oss/evals` 對 Responses API 和 Chat Completions 各跑一次 GPQA，把分數跟 Artificial Analysis 的數字比較，判斷實作是否正確。
