---
translated: true
source: articles/how_to_work_with_large_language_models.md
---
# 怎麼跟大型語言模型合作

> 原文：[articles/how_to_work_with_large_language_models.md](https://github.com/openai/openai-cookbook/blob/main/articles/how_to_work_with_large_language_models.md)



## 這篇在做什麼
這篇用白話講大型語言模型怎麼運作，以及怎麼用 prompt 控制它。會比較 instruction、completion、scenario、demonstration 和 fine-tuning 五種下 prompt 的方式，最後補上寫 code 的能力和幾個提升輸出品質的 prompt 技巧。

## 學完你會
- 解釋 LLM 是「預測下一段文字」的函式，以及這為什麼讓 prompt 影響最大。
- 針對同一個需求，分別寫出 instruction、completion、scenario、few-shot 四種 prompt。
- 用「說得更具體、給 context、要求專家口吻、逐步推理」這幾招改善輸出。



## 大型語言模型怎麼運作

[大型語言模型][Large language models Blog Post]是把文字對應到文字的函式。給它一段輸入文字，它會預測接下來應該出現的文字。

大型語言模型厲害的地方在於，它在大量文字上被訓練去降低這個預測誤差，結果就學會了對預測有用的各種概念。例如它會學到：

- 怎麼拼字
- 文法怎麼運作
- 怎麼改寫句子
- 怎麼回答問題
- 怎麼進行對話
- 怎麼用多種語言寫作
- 怎麼寫程式
- 等等

它的做法是「閱讀」大量既有文字，學習字詞在上下文裡通常怎麼跟其他字詞一起出現，再用學到的東西預測使用者請求之後最可能出現的下一個字，然後是再下一個字。

GPT-3 和 GPT-4 驅動了[很多軟體產品][OpenAI Customer Stories]，包括生產力工具、教育應用、遊戲等等。

## 怎麼控制大型語言模型

模型所有的輸入裡，影響最大的就是文字 prompt。

可以用幾種方式 prompt 大型語言模型產生輸出：

- **Instruction**：直接告訴模型你要什麼
- **Completion**：引導模型接續完成你起頭的內容
- **Scenario**：給模型一個情境讓它演出來
- **Demonstration**：示範你要的東西給模型看，可以用：
  - prompt 裡放幾個範例
  - fine-tuning 訓練資料集裡放幾百到幾千個範例

下面各舉一個例子。

### Instruction prompt

把指令寫在 prompt 的最上面（或最下面，或兩邊都寫），模型會盡力照著做，做完就停。指令可以很詳細，別怕寫一整段明確描述你要的輸出，只要注意模型能處理多少 [token](https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them)。

Instruction prompt 範例：

```text
Extract the name of the author from the quotation below.

“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
```

輸出：

```text
Ted Chiang
```

### Completion prompt 範例

Completion 風格的 prompt 利用的是大型語言模型會試著寫出它認為最有可能接下去的文字。要引導模型，可以先開頭一個 pattern 或句子，讓輸出把它補完成你想看到的樣子。跟直接下指令比起來，這種方式需要更仔細、更多實驗。而且模型不一定知道該在哪停，所以常常需要 stop sequence 或後處理，把超出期望輸出的文字截掉。

Completion prompt 範例：

```text
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation

The author of this quote is
```

輸出：

```text
 Ted Chiang
```

### Scenario prompt 範例

給模型一個情境或角色去演出來，對複雜的問題或想要有創意的回答很有幫助。用假設式 prompt 時，你先設定一個情境、問題或故事，再請模型以那個情境裡的角色，或該主題專家的身分來回應。

Scenario prompt 範例：

```text
Your role is to extract the name of the author from any given text

“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
```

輸出：

```text
 Ted Chiang
```

### Demonstration prompt 範例（few-shot learning）

跟 completion 風格的 prompt 類似，demonstration 是示範給模型看你要它做什麼。這種做法有時叫 few-shot learning，因為模型是從 prompt 裡提供的少數幾個範例學習。

Demonstration prompt 範例：

```text
Quote:
“When the reasoning mind is forced to confront the impossible again and again, it has no choice but to adapt.”
― N.K. Jemisin, The Fifth Season
Author: N.K. Jemisin

Quote:
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
Author:
```

輸出：

```text
 Ted Chiang
```

### Fine-tuned prompt 範例

有了足夠的訓練範例，就可以 [fine-tune][Fine Tuning Docs] 一個自訂模型。這時候就不需要指令了，因為模型可以從提供的訓練資料學會任務。不過還是建議加分隔序列（例如 `->`、`###`，或任何在你輸入裡不常出現的字串），告訴模型 prompt 在哪結束、輸出該從哪開始。沒有分隔序列的話，模型可能繼續延伸輸入文字，而不是開始寫你想要的答案。

Fine-tuned prompt 範例（針對用類似 prompt-completion 配對訓練過的自訂模型）：

```text
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation

###


```

輸出：

```text
 Ted Chiang
```

## 程式碼能力

大型語言模型不只擅長文字，也可以很會寫程式。OpenAI 的 [GPT-4][GPT-4 and GPT-4 Turbo] 就是代表。

GPT-4 驅動了[許多創新產品][OpenAI Customer Stories]，包括：

- [GitHub Copilot]（在 Visual Studio 和其他 IDE 自動補全程式碼）
- [Replit](https://replit.com/)（可以補全、解釋、編輯和產生程式碼）
- [Cursor](https://cursor.sh/)（在專為跟 AI 結對程式設計打造的編輯器裡更快開發軟體）

GPT-4 比 `gpt-3.5-turbo-instruct` 這類之前的模型更先進。但要讓 GPT-4 在寫程式任務上發揮最好，還是要給清楚具體的指令，所以設計好的 prompt 需要多花點心思。

### 更多 prompt 建議

更多 prompt 範例請看 [OpenAI Examples][OpenAI Examples]。

一般來說，輸入的 prompt 是改善模型輸出的最佳槓桿。可以試試這些技巧：

- **說得更具體**：例如你要輸出是逗號分隔的清單，就要求它回傳逗號分隔的清單。如果希望它不知道答案時說「我不知道」，就告訴它：'Say "I don't know" if you do not know the answer.'。指令越具體，模型回應得越好。
- **提供 context**：幫助模型了解你的請求的全貌。可以是背景資訊、你想要的東西的範例/示範，或是說明任務的目的。
- **請模型以專家的身分回答**：明確要求模型產生高品質輸出，或是像專家寫的那樣，可以誘導模型給出它認為專家會寫的較高品質答案。像 "Explain in detail" 或 "Describe step-by-step" 這類說法很有效。
- **讓模型寫下說明推理的一連串步驟**：如果想知道答案背後的「為什麼」，就 prompt 模型把推理寫出來。做法很簡單，在每個答案前加一行像 "[Let's think step by step](https://arxiv.org/abs/2205.11916)" 的話。

[Fine Tuning Docs]: https://platform.openai.com/docs/guides/fine-tuning
[OpenAI Customer Stories]: https://openai.com/customer-stories
[Large language models Blog Post]: https://openai.com/research/better-language-models
[GitHub Copilot]: https://github.com/features/copilot/
[GPT-4 and GPT-4 Turbo]: https://platform.openai.com/docs/models/gpt-4-and-gpt-4-turbo
[GPT3 Apps Blog Post]: https://openai.com/blog/gpt-3-apps/
[OpenAI Examples]: https://platform.openai.com/examples

## 重點整理
- LLM 本質上是預測下一段文字，所以 prompt 是影響輸出最大的輸入。
- 五種下 prompt 的方式各有取捨：instruction 最直接，completion 要處理停止點，scenario 適合創意題，few-shot 靠範例，fine-tuning 靠大量資料。
- Fine-tuned 模型的 prompt 要加分隔序列，不然模型可能接著延伸輸入。
- 輸出不理想時，先從 prompt 下手：更具體、給 context、要求專家口吻、要求逐步推理。

## 練習
1. 拿頁面上的 instruction prompt，改成要求輸出逗號分隔的清單，看輸出有沒有照做。
2. 把 completion prompt 的開頭改成別的 pattern，並加上 stop sequence，觀察輸出在哪裡截斷。
3. 把 demonstration prompt 的範例從 3 個減成 1 個、再增加到 5 個，比較輸出的穩定度。
