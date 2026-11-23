---
translated: true
source: articles/techniques_to_improve_reliability.md
---
# 提升可靠度的技巧

> 原文：[articles/techniques_to_improve_reliability.md](https://github.com/openai/openai-cookbook/blob/main/articles/techniques_to_improve_reliability.md)

## 這篇在做什麼

GPT-3 做不好某個任務時，不一定是模型不行，常常是 prompt 沒給它足夠的空間去想。這篇整理了一批研究出來的技巧，像是拆解任務、先解釋再回答、多採樣取多數決、用 verifier 挑答案，讓模型在需要推理的任務上更穩。

## 學完你會

- 知道為什麼模型會在複雜任務上亂猜，以及怎麼用 `Let's think step by step` 這類 prompt 讓它先推理再回答。
- 會把一個複雜指令拆成幾個子任務（先辨識語言再摘要、先逐條檢查線索再下結論）。
- 能分辨 self-consistency、verifier、selection-inference、least-to-most 這些技巧各自適合什麼情境、要付出什麼成本。

## 開跑前

這篇以概念為主，程式碼範例用的是 `gpt-3.5-turbo-instruct`，要自己跑的話需要 OpenAI API key。

GPT-3 在複雜任務上失敗時，你會怎麼做？

- 找一個更好的 prompt，希望能引出更可靠的答案？
- 花錢準備幾千筆範例去 fine-tune 一個客製模型？
- 認定模型做不到，直接放棄？

沒有一個簡單的答案，要看情況。不過如果你的任務牽涉邏輯推理或比較複雜，可以試試這篇的技巧，做出更可靠、表現更好的 prompt。

## 為什麼 GPT-3 在複雜任務上會失敗

如果有人要你算 13 乘以 17，答案會馬上冒出來嗎？大多數人應該不會。但這不代表人類不會做兩位數乘法。給幾秒鐘，加上紙跟筆，不難算出 13 x 17 = 130 + 70 + 21 = 221。

同樣的道理，如果你給 GPT-3 的任務複雜到它在算下一個 token 的那點時間內做不完，它可能會編一個錯的答案出來。但跟人一樣，這不代表模型做不到。只要給它一些時間和空間把事情推理出來，它還是有機會穩定地答對。

舉個例子，如果你拿下面這題丟球的數學題問 `gpt-3.5-turbo-instruct`，它會答錯：

```gpt-3.5-turbo-instruct
Q: A juggler has 16 balls. Half of the balls are golf balls and half of the golf balls are blue. How many blue golf balls are there?
A:
```

```gpt-3.5-turbo-instruct
There are 8 blue golf balls.
```

這是不是代表 GPT-3 連簡單數學題都不會？不是。其實只要在 prompt 裡加上 `Let's think step by step`，模型就能穩定地解出來：

```gpt-3.5-turbo-instruct
Q: A juggler has 16 balls. Half of the balls are golf balls and half of the golf balls are blue. How many blue golf balls are there?
A: Let's think step by step.
```

```gpt-3.5-turbo-instruct
There are 16 balls in total.
Half of the balls are golf balls.
That means that there are 8 golf balls.
Half of the golf balls are blue.
That means that there are 4 blue golf balls.
```

當然，光看一個例子，很難判斷 `Let's think step by step` 這招是真的有效，還是剛好這題運氣好。但它真的有效。在一組文字數學題的 benchmark 上，這招把 GPT-3 的解題率從沒什麼用的 18% 大幅拉到 79%。

## 模型的能力取決於 context

剛開始用 GPT-3 時，常見的觀念錯誤是以為它的能力在所有情境下都固定不變。例如 GPT-3 答錯一題簡單的邏輯題，就認為它不會簡單的邏輯。

但從 `Let's think step by step` 的例子可以看到，GPT-3 看起來的失敗，有時只要換個更好的 prompt，幫模型把自己導向正確的輸出，就能補救。

## 怎麼提升複雜任務的可靠度

這篇接下來會介紹提升大型語言模型在複雜任務上可靠度的技巧。有些技巧只適用特定類型的問題，但很多都建立在可以廣泛套用的通用原則上，例如：

- 給更清楚的指令
- 把複雜任務拆成較簡單的子任務
- 把指令組織好，讓模型不要跑題
- 讓模型先解釋再回答
- 針對多個可能的答案要求說明理由，再整合
- 產生很多輸出，再用模型挑出最好的
- Fine-tune 客製模型，把表現推到最高

## 把複雜任務拆成簡單任務

要給模型更多時間和空間思考，一個方法是把任務拆成比較小的塊。

舉例來說，假設我們針對一段文字問模型一題選擇題，這裡用的是一場 Clue（妙探尋兇）遊戲。直接問的話，`gpt-3.5-turbo-instruct` 沒辦法把線索 3 跟 5 湊在一起，答錯了：

```gpt-3.5-turbo-instruct
Use the following clues to answer the following multiple-choice question.

Clues:
1. Miss Scarlett was the only person in the lounge.
2. The person with the pipe was in the kitchen.
3. Colonel Mustard was the only person in the observatory.
4. Professor Plum was not in the library nor the billiard room.
5. The person with the candlestick was in the observatory.

Question: Was Colonel Mustard in the observatory with the candlestick?
(a) Yes; Colonel Mustard was in the observatory with the candlestick
(b) No; Colonel Mustard was not in the observatory with the candlestick
(c) Unknown; there is not enough information to determine whether Colonel Mustard was in the observatory with the candlestick

Solution:
```

```gpt-3.5-turbo-instruct
(c) Unknown; there is not enough information to determine whether Colonel Mustard was in the observatory with the candlestick
```

線索 3 和 5 其實已經確定：只有 Colonel Mustard 一個人在 observatory，而在 observatory 的人拿著燭台。模型卻沒能把這兩點合起來，得到正確答案 (a) Yes。

不過，我們可以不要直接要答案，而是把任務拆成三塊：

- 第一，逐條看線索，判斷這條線索可能有沒有關係
- 第二，把相關的線索合起來，推理出問題的答案
- 第三，寫出最終答案：(a)、(b) 或 (c)

```gpt-3.5-turbo-instruct
Use the following clues to answer the following multiple-choice question, using the following procedure:
(1) First, go through the clues one by one and consider whether the clue is potentially relevant
(2) Second, combine the relevant clues to reason out the answer to the question
(3) Third, map the answer to one of the multiple choice answers: either (a), (b), or (c)

Clues:
1. Miss Scarlett was the only person in the lounge.
2. The person with the pipe was in the kitchen.
3. Colonel Mustard was the only person in the observatory.
4. Professor Plum was not in the library nor the billiard room.
5. The person with the candlestick was in the observatory.

Question: Was Colonel Mustard in the observatory with the candlestick?
(a) Yes; Colonel Mustard was in the observatory with the candlestick
(b) No; Colonel Mustard was not in the observatory with the candlestick
(c) Unknown; there is not enough information to determine whether Colonel Mustard was in the observatory with the candlestick

Solution:
(1) First, go through the clues one by one and consider whether the clue is potentially relevant:
```

```gpt-3.5-turbo-instruct
Clue 1: Miss Scarlett was the only person in the lounge. This clue is not relevant.
Clue 2: The person with the pipe was in the kitchen. This clue is not relevant.
Clue 3: Colonel Mustard was the only person in the observatory. This clue is relevant.
Clue 4: Professor Plum was not in the library nor the billiard room. This clue is not relevant.
Clue 5: The person with the candlestick was in the observatory. This clue is relevant.

(2) Second, combine the relevant clues to reason out the answer to the question:
Clue 3 and Clue 5 both say that the person with the candlestick was in the observatory. Colonel Mustard was the only person in the observatory, so Colonel Mustard was the person with the candlestick.

(3) Third, write the final answer:
(a) Yes; Colonel Mustard was in the observatory with the candlestick
```

給模型更多時間和空間思考，再用一個推理計畫帶著它走，它就能算出正確答案 (a) Yes。

把複雜指令拆成小任務還有另一個好處，就是能讓模型專注在每個子任務上。

例如，我們請 `gpt-3.5-turbo-instruct` 用原文的語言摘要一段文字，模型可能會不小心滑回英文：

```gpt-3.5-turbo-instruct
Summarize the text using the original language of the text. The summary should be one sentence long.

Text:
"""
La estadística (la forma femenina del término alemán Statistik, derivado a su vez del italiano statista, "hombre de Estado")​ es una ciencia que estudia la variabilidad, colección, organización, análisis, interpretación, y presentación de los datos, así como el proceso aleatorio que los genera siguiendo las leyes de la probabilidad.​ La estadística es una ciencia formal deductiva, con un conocimiento propio, dinámico y en continuo desarrollo obtenido a través del método científico formal. En ocasiones, las ciencias fácticas necesitan utilizar técnicas estadísticas durante su proceso de investigación factual, con el fin de obtener nuevos conocimientos basados en la experimentación y en la observación. En estos casos, la aplicación de la estadística permite el análisis de datos provenientes de una muestra representativa, que busca explicar las correlaciones y dependencias de un fenómeno físico o natural, de ocurrencia en forma aleatoria o condicional.
"""

Summary:
```

```gpt-3.5-turbo-instruct
The text explains that statistics is a science that studies the variability, collection, organization, analysis, interpretation, and presentation of data, as well as the random process that generates them following the laws of probability.
```

但如果先請模型辨識文字的語言，再做摘要，就會可靠很多：

```gpt-3.5-turbo-instruct
First, identify the language of the text. Second, summarize the text using the original language of the text. The summary should be one sentence long.

Text:
"""
La estadística (la forma femenina del término alemán Statistik, derivado a su vez del italiano statista, "hombre de Estado")​ es una ciencia que estudia la variabilidad, colección, organización, análisis, interpretación, y presentación de los datos, así como el proceso aleatorio que los genera siguiendo las leyes de la probabilidad.​ La estadística es una ciencia formal deductiva, con un conocimiento propio, dinámico y en continuo desarrollo obtenido a través del método científico formal. En ocasiones, las ciencias fácticas necesitan utilizar técnicas estadísticas durante su proceso de investigación factual, con el fin de obtener nuevos conocimientos basados en la experimentación y en la observación. En estos casos, la aplicación de la estadística permite el análisis de datos provenientes de una muestra representativa, que busca explicar las correlaciones y dependencias de un fenómeno físico o natural, de ocurrencia en forma aleatoria o condicional.
"""

Language:
```

```gpt-3.5-turbo-instruct
Spanish

La estadística es una ciencia que estudia la variabilidad, colección, organización, análisis, interpretación, y presentación de los datos, así como el proceso aleatorio que los genera siguiendo las leyes de la probabilidad.
```

## 讓模型先解釋再回答

另一個很有效的技巧是 prompt 模型一步步把答案推理出來，而不是直接跳到最終答案。模型像是把想法說出來，答對的機率會高很多。

### Zero-shot

#### 方法

[Takeshi Kojima 等人在 2022 年發表](https://arxiv.org/abs/2205.11916)的研究指出，最簡單的做法是在答案前面加上 `Let's think step by step.`。圖 2 是一個例子：

[![zero-shot reasoning example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/zero-shot_reasoners_fig2.png)
<br>Source: _Large Language Models are Zero-Shot Reasoners_ by Takeshi Kojima et al. (2022).](https://arxiv.org/abs/2205.11916)

#### 結果

作者把這個簡單的招數用在 MultiArith 數學資料集上，發現 `Let's think step by step` 讓準確率翻了四倍，從 18% 到 79%。

[![zero-shot reasoning example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/zero-shot_reasoners_tab5.png)
<br>Source: _Large Language Models are Zero-Shot Reasoners_ by Takeshi Kojima et al. (2022).](https://arxiv.org/abs/2205.11916)

#### 啟示

雖然 `Let's think step by step` 在數學題上效果很好，但並不是對所有任務都有用。作者發現它對多步驟算術、符號推理、策略題和其他推理題幫助最大。對簡單數學題或常識題沒幫助，推測對很多非推理類的任務也不會有用。

[![zero-shot reasoning example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/zero-shot_reasoners_tab1.png)
<br>Source: _Large Language Models are Zero-Shot Reasoners_ by Takeshi Kojima et al. (2022).](https://arxiv.org/abs/2205.11916)

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2205.11916)。

如果你把這招用在自己的任務上，不用怕改指令。`Let's think step by step` 算是很通用的說法，換成格式更嚴格、貼合你情境的指令，效果可能更好。例如你可以試比較有結構的版本：`First, think step by step about why X might be true. Second, think step by step about why Y might be true. Third, think step by step about whether X or Y makes more sense.`。你甚至可以給模型一個範例格式，幫它不要偏掉，例如：

```gpt-3.5-turbo-instruct
Using the IRS guidance below, answer the following questions using this format:
(1) For each criterion, determine whether it is met by the vehicle purchase
- {Criterion} Let's think step by step. {explanation} {yes or no, or if the question does not apply then N/A}.
(2) After considering each criterion in turn, phrase the final answer as "Because of {reasons}, the answer is likely {yes or no}."

IRS guidance:
"""
You may be eligible for a federal tax credit under Section 30D if you purchased a car or truck that meets the following criteria:
- Does the vehicle have at least four wheels?
- Does the vehicle weigh less than 14,000 pounds?
- Does the vehicle draw energy from a battery with at least 4 kilowatt hours that may be recharged from an external source?
- Was the vehicle purchased in a year before 2022?
  - If so, has the manufacturer sold less than 200,000 qualifying vehicles? (Tesla and GM have sold more than 200,000 qualifying vehicles.)
- Was the vehicle purchased in a year after 2022?
  - If so, is the vehicle present in the following list of North American-assembled vehicles? (The only electric vehicles assembled in North America are the Audi Q5, BMW 330e, BMW X5, Chevrolet Bolt EUV, Chevrolet Bolt EV, Chrysler Pacifica PHEV, Ford Escape PHEV, Ford F Series, Ford Mustang MACH E, Ford Transit Van, GMC Hummer Pickup, GMC Hummer SUV, Jeep Grand Cherokee PHEV, Jeep Wrangler PHEV, Lincoln Aviator PHEV, Lincoln Corsair Plug-in, Lucid Air, Nissan Leaf, Rivian EDV, Rivian R1S, Rivian R1T, Tesla Model 3, Tesla Model S, Tesla Model X, Tesla Model Y, Volvo S60, BMW 330e, Bolt EV, Cadillac Lyriq, Mercedes EQS SUV, and Nissan Leaf.)
"""

Question: Can I claim a federal tax credit for my Toyota Prius Prime bought in 2021?

Solution:

(1) For each criterion, determine whether it is met by the vehicle purchase
- Does the vehicle have at least four wheels? Let's think step by step.
```

```gpt-3.5-turbo-instruct
 The Toyota Prius Prime has four wheels, so the answer is yes.
- Does the vehicle weigh less than 14,000 pounds? Let's think step by step. The Toyota Prius Prime weighs less than 14,000 pounds, so the answer is yes.
- Does the vehicle draw energy from a battery with at least 4 kilowatt hours that may be recharged from an external source? Let's think step by step. The Toyota Prius Prime has a battery with at least 4 kilowatt hours that may be recharged from an external source, so the answer is yes.
- Was the vehicle purchased in a year before 2022? Let's think step by step. The Toyota Prius Prime was purchased in 2021, which is before 2022, so the answer is yes.
- Was the vehicle purchased in a year after 2022? N/A
- If so, is the vehicle present in the following list of North American-assembled vehicles? N/A

(2) After considering each criterion in turn, phrase the final answer as "Because of {reasons}, the answer is likely {yes or no}."

Because the Toyota Prius Prime meets all of the criteria for a federal tax credit, the answer is likely yes.
```

### Few-shot 範例

#### 方法

要讓模型把答案推理出來，有很多做法。其中一種是用幾個範例示範（few-shot），這是 [Google 的 Jason Wei 和 Denny Zhou 等人](https://ai.googleblog.com/2022/05/language-models-perform-reasoning-via.html)研究的。下面是一個 few-shot 的 chain-of-thought prompt 範例：

[![chain of thought example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/chain_of_thought_fig1.png)
<br>Source: _Chain of Thought Prompting Elicits Reasoning in Large Language Models_ Jason Wei and Denny Zhou et al. (2022)](https://ai.googleblog.com/2022/05/language-models-perform-reasoning-via.html)

更多由人工標註者寫的推理鏈示範：

[![chain of thought example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/chain_of_thought_fig3.png)
<br>Source: _Chain of Thought Prompting Elicits Reasoning in Large Language Models_ Jason Wei and Denny Zhou et al. (2022)](https://ai.googleblog.com/2022/05/language-models-perform-reasoning-via.html)

[（附註：梨子到底會不會浮在水上，其實有人質疑過）](https://twitter.com/Meaningness/status/1561062170074370048?s=20&t=mpHt8f3RRboztXxdhLFnWQ)

#### 結果

在小學程度的數學題上測試，作者發現 chain of thought prompting 讓解題率變成三倍，從 18% 到 57%。

[![chain of thought example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/chain_of_thought_fig5.png)
<br>Source: _Chain of Thought Prompting Elicits Reasoning in Large Language Models_ Jason Wei and Denny Zhou et al. (2022)](https://ai.googleblog.com/2022/05/language-models-perform-reasoning-via.html)

除了數學題，chain of thought prompting 在運動常識理解、拋硬幣追蹤、末字母串接這些題目上也提升了表現。大多數情況下不需要很多範例就能把效果推到頂（大約 8 個以內）。

[![chain of thought example](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/chain_of_thought_fig11.png)
<br>Source: _Chain of Thought Prompting Elicits Reasoning in Large Language Models_ Jason Wei and Denny Zhou et al. (2022)](https://ai.googleblog.com/2022/05/language-models-perform-reasoning-via.html)

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2201.11903)。

#### 啟示

相較於 `Let's think step by step`，few-shot 範例的好處是你比較容易指定模型在給出最終答案前要用什麼格式、多長、什麼風格的推理。當模型一開始的推理方式或深度不對時，這特別有用。

### Fine-tuned

#### 方法

一般來說，想把一個任務的表現榨到最高，就得 fine-tune 一個客製模型。但用解釋來 fine-tune 模型可能需要幾千筆範例解釋，寫起來很貴。

2022 年，Eric Zelikman 和 Yuhuai Wu 等人發表了一個很聰明的做法：用 few-shot prompt 產生一個解釋資料集，拿來 fine-tune 模型。想法是先用 few-shot prompt 產生候選解釋，只留下能得到正確答案的那些。接著，對一部分答錯的題目，再試一次 few-shot prompt，但這次把正確答案放進題目裡，取得更多解釋。作者把這個流程叫做 STaR (Self-taught Reasoner)：

[![STaR procedure](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/star_fig1.png)
<br>Source: _STaR: Bootstrapping Reasoning With Reasoning_ by Eric Zelikman and Yujuai Wu et al. (2022)](https://arxiv.org/abs/2203.14465)

用這個技巧，你可以同時拿到 fine-tuning 和 chain-of-thought prompting 的好處，又不用寫幾千筆範例解釋。

#### 結果

作者把這個技巧用在 Common Sense Q&A 資料集上，發現 STaR 同時贏過單用 chain-of-thought prompting（73% > 37%）和單用 fine-tuning（73% > 60%）：

[![STaR results](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/star_tab1.png)
<br>Source: _STaR: Bootstrapping Reasoning With Reasoning_ by Eric Zelikman and Yujuai Wu et al. (2022)](https://arxiv.org/abs/2203.14465)

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2203.14465)。

#### 啟示
用 few-shot prompt 來擴充或修改 fine-tuning 資料集，這個想法可以推廣到寫解釋以外的地方。例如你手上有大量非結構化的文字想拿來訓練，可以用 prompt 從這些文字抽出結構化資料集，再用結構化資料集去 fine-tune 一個客製模型。

## Chain-of-thought prompting 的延伸

chain-of-thought prompting 也有不少延伸做法被發表出來。

### Selection-inference prompting

#### 方法

這是 Antonia Creswell 等人發表的，chain-of-thought 的一個延伸做法，把原本同時產生解釋和答案的單一 prompt，拆成比較小的部分。首先，一個 prompt 從文字中選出相關的事實子集（selection prompt）。然後第二個 prompt 根據選出的事實推論出結論（inference prompt）。這兩個 prompt 會在迴圈裡輪流執行，產生多步推理，最後得到最終答案。作者用下面的圖說明這個想法：

[![Selection-inference prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/selection-inference_fig1.png)
<br>Source: _Selection-Inference: Exploiting Large Language Models for Interpretable Logical Reasoning_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2205.09712)

#### 結果

用在 7B 參數的模型上，作者發現 selection-inference prompting 在 bAbi 和 Proof Writer 這兩個 benchmark 任務上，表現比 chain-of-thought prompting 好很多（這兩個任務都需要比較長的推理步驟）。他們達到的最佳表現是把 selection-inference prompting 和 fine-tuning 結合起來。

[![Selection-inference prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/selection-inference_fig4.png)
<br>Source: _Selection-Inference: Exploiting Large Language Models for Interpretable Logical Reasoning_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2205.09712)

#### 啟示

雖然在這些 benchmark 上提升很大，但這些 benchmark 是刻意挑的，因為它們需要比較長的推理序列。對不需要多步推理的問題，提升可能小很多。

這個結果帶出兩個使用大型語言模型的通則。一，把複雜任務拆成小任務，是提升可靠度和表現的好方法，任務越細，模型出錯的空間越小。二，要拿到最高表現，通常要把 fine-tuning 跟你選的方法結合起來。

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2205.09712)。

### Faithful reasoning architecture

發表 selection-inference prompting 幾個月後，作者在後續論文中擴充了這個技巧，加入幾個想法：

- 判斷 selection-inference 迴圈該停還是該繼續
- 加一個 value function，幫忙在多條推理路徑上搜尋
- 讓模型針對句子標籤（例如 sen1）做推理，而不是把整句寫出來，藉此減少編造假事實的 hallucination，這需要對模型做 fine-tuning

#### 方法

在原本的 selection-inference 技巧裡，專門的 selection prompt 和 inference prompt 輪流執行，選事實、再從事實做推論，合起來產生一連串的推理步驟。

作者在這個技巧上加了兩個元件。

第一，他們加了一個「halter」模型，每次推論完之後，問它目前的推論夠不夠回答問題。如果夠，就由模型產生最終答案。

halter 模型有幾個好處：

- 它可以視需要告訴 selection-inference 流程該停還是該繼續。
- 如果流程一直沒停，就不會有答案，這通常比一個 hallucinated 的猜測好。

[![Faithful reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/faithful-reasoning_fig3.png)
<br>Source: _Faithful Reasoning Using Large Language Models_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2208.14271)

[![Faithful reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/faithful-reasoning_fig5.png)
<br>Source: _Faithful Reasoning Using Large Language Models_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2208.14271)

第二，他們加了 value function，用來評估推理步驟的品質，並在多條推理軌跡上搜尋。這呼應了提升可靠度的常見主題：不要只讓模型產生一個答案，而是產生一組答案，再用某種 value function、discriminator 或 verifier 模型挑出最好的。

[![Faithful reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/faithful-reasoning_fig7.png)
<br>Source: _Faithful Reasoning Using Large Language Models_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2208.14271)

除了這兩個延伸，作者還用了一個技巧來減少編造假事實的 hallucination。他們不讓模型寫出事實句子，而是 fine-tune 模型去處理句子標籤（例如 sen1）。這樣可以避免模型編出 prompt context 裡沒提到的假事實。

[![Faithful reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/faithful-reasoning_fig4.png)
<br>Source: _Faithful Reasoning Using Large Language Models_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2208.14271)

#### 結果

作者在兩個 benchmark 上評估這個技巧：ProofWriter 任務（沒有附圖）和 [EntailmentBankQA](https://allenai.org/data/entailmentbank)（有附圖）。這個技巧大幅提升了準確率，尤其是在比較難的推理題上。

![Faithful reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/faithful-reasoning_tab2.png)
<br>Source: _Faithful Reasoning Using Large Language Models_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2208.14271)

而且，他們的句子標籤技巧幾乎消除了 hallucination。

![Faithful reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/faithful-reasoning_tab5.png)
<br>Source: _Faithful Reasoning Using Large Language Models_ by Antonia Creswell et al. (2022)](https://arxiv.org/abs/2208.14271)

#### 啟示

這篇論文帶出幾個提升大型語言模型可靠度的實用心得：

- 把複雜任務拆成更小、更可靠的子任務
- 一步一步產生答案，過程中就做評估
- 產生很多可能的答案，再用另一個模型或函式挑出看起來最好的
- 限制模型能說的內容來減少 hallucination（例如用句子標籤取代整個句子）
- 針對特定任務 fine-tune 模型，把表現推到最高

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2205.09712)。

### Least-to-most prompting

chain-of-thought prompting 除了在長推理鏈上表現不好（selection-inference 在這方面很強），在範例很短但任務很長的時候也特別吃力。

#### 方法

Least-to-most prompting 是另一個把推理任務拆成更小、更可靠子任務的技巧。做法是用類似 `To solve {question}, we need to first solve: "` 的 prompt，讓模型提出一個子任務。有了這個子任務，模型就能產生解答。解答會被接到原本的問題後面，然後重複這個流程，直到產生最終答案。

[![Least-to-most prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/least-to-most_fig1.png)
<br>Source: _Least-to-most Prompting Enables Complex Reasoning in Large Language Models_ by Denny Zhou et al. (2022)](https://arxiv.org/abs/2205.10625)

#### 結果

用 `code-davinci-002`（針對程式碼優化，但仍能理解文字）在涉及長推理鏈的 benchmark 上測試，作者量到最高 16% -> 99.7% 的提升。

[
![Least-to-most prompting results on last-letter-concatenation task](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/least-to-most_tab4.png)
![Least-to-most prompting results on SCAN](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/least-to-most_tab9.png)
![Least-to-most prompting results on DROP numerical reasoning](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/least-to-most_tab11.png)
<br>Source: _Least-to-most Prompting Enables Complex Reasoning in Large Language Models_ by Denny Zhou et al. (2022)](https://arxiv.org/abs/2205.10625)

#### 啟示

least-to-most prompting 的提升很亮眼，但這些是在一小組需要長推理鏈的任務上量到的。

不過它們還是說明了一個共通的主題：提升可靠度的做法是 (a) 把複雜任務拆成較小的子任務，(b) 給模型更多時間和空間把答案算出來。

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2205.10625)。

## 相關的想法

### Maieutic prompting

#### 方法

前面的技巧都是想把答對的機率拉到最高，這個做法不太一樣：用 GPT-3 產生一棵可能解釋的樹（包含正確的_和錯誤的_），再分析它們之間的關係，猜哪一組是對的。這個技巧是 [Jaehun Jung 等人在 2022 年 5 月](https://arxiv.org/abs/2205.11822)提出，取名 maieutic prompting（maieutic 指的是蘇格拉底式的提問法，用問題引出想法）。

這個方法很複雜，流程如下：

- 第一，建一棵 maieutic tree，每個節點是一個可能為真或為假的陳述：
  - 從一個選擇題或是非陳述開始（例如 `War cannot have a tie`）
  - 針對這個問題的每個可能答案，用模型產生對應的解釋（prompt 像 `War cannot have a tie? True, because`）
  - 接著，把問題和產生的解釋一起丟給模型，請它給出答案。如果把解釋反過來講（加上像 `It is wrong to say that {explanation}` 的前綴）答案就跟著反過來，這個解釋就算「邏輯完整」(logically integral)。
  - 如果某個解釋不是邏輯完整的，就遞迴重複上面的流程，把每個解釋變成一個真或假的問題，再為每個新問題產生更多解釋。
  - 所有遞迴解釋都做完後，你會得到一棵解釋樹，樹上每個葉節點都有一個性質：把解釋反過來，模型的答案也會反過來。
- 第二，把這棵樹轉成關係圖：
  - 對樹上每個節點，計算模型對它的相對信心（由給定解釋時回答 `True` 的機率推得）
  - 對樹上每一對節點，用模型判斷它們是互相蘊含（implied）還是互相矛盾
- 第三，找出最一致的一組信念，把它們當成真的：
  - 具體來說，利用每個節點的信心強度和節點之間的邏輯關係，把問題寫成加權最大可滿足性問題 (MAX-SAT)
  - 用 solver 找出最自洽的一組信念，把它們當成真的
[
![Maieutic prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/maieutic_fig2.png)
![Maieutic prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/maieutic_fig6.png)
<br>Source: _Maieutic Prompting: Logically Consistent Reasoning with Recursive Explanations_ by Jaehun Jung et al. (2022)](https://arxiv.org/abs/2205.11822)

#### 結果

[![Maieutic prompting results](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/maieutic_tab1.png)
<br>Source: _Maieutic Prompting: Logically Consistent Reasoning with Recursive Explanations_ by Jaehun Jung et al. (2022)](https://arxiv.org/abs/2205.11822)

#### 啟示

除了複雜之外，這個方法還有一個限制：它似乎只適用於能寫成選擇題的問題。

想了解更多，可以讀[完整論文](https://arxiv.org/abs/2205.11822)。

## 其他延伸

### Self-consistency

#### 方法

對答案是離散集合的任務，有一個簡單的提升可靠度做法：從模型採樣多組解釋和答案（用大於 0 的 temperature），然後選出現最多次的那個當最終答案。

[![Self-consistency method](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/self-consistency_fig1.png)
<br>Source: _Self-Consistency Improves Chain of Thought Reasoning in Language Models_ by Xuezhi Wang et al. (2022)](https://arxiv.org/abs/2203.11171)

#### 結果

這個技巧在一系列數學和推理 benchmark 上，讓準確率提升了 1 到 24 個百分點。（下圖是 Google LaMDA 模型的結果；用 Google 較大的 PaLM 模型時，基準線比較高，但提升幅度小一些。）

[![Self-consistency results](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/self-consistency_fig3.png)
<br>Source: _Self-Consistency Improves Chain of Thought Reasoning in Language Models_ by Xuezhi Wang et al. (2022)](https://arxiv.org/abs/2203.11171)

#### 啟示

雖然這個技巧很好實作，但可能很貴。產生 10 個答案，成本就會變成 10 倍。

而且跟很多這類技巧一樣，它只適用於答案有限的任務。對每個答案都獨一無二的開放式任務（例如寫詩），挑最常見的答案根本沒意義。

最後，這個技巧在有多條路徑或多種說法能得到答案時最有幫助；如果只有一條路，它可能完全沒用。極端的例子：如果任務是產生單一 token 的答案，從 100 次生成裡取最常見的 token，跟取 logprobs 最高的 token 沒有差別（後者用 temperature=0 生成一次就拿得到）。

### Verifiers

另一個提升任務表現的關鍵技巧，是訓練一個 verifier（或 discriminator）模型，來評估主要生成模型的輸出。如果 discriminator 否決了輸出，就可以重新對生成模型採樣，直到拿到可接受的輸出。很多時候，判斷一個答案比創造一個答案容易，這也解釋了這個方法為什麼強。

#### 方法

2021 年，OpenAI 的研究者把這個技巧用在小學數學題上，流程如下：

- 首先，用題目和解答 fine-tune 一個模型
- 對訓練集中的每一題，產生 100 個解答
- 這 100 個解答各自根據最終答案是否正確，被自動標成正確或錯誤
- 用這些解答（有些標正確、有些標錯誤）fine-tune 一個 verifier 模型，讓它判斷某個題目加候選解答是正確還是錯誤
- 最後，在測試時，生成模型對每題產生 100 個解答，verifier 模型給分最高的那個被選為最終答案

[![Verifier method](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/verifiers_fig3.png)
<br>Source: _Training Verifiers to Solve Math Word Problems_ by Karl Cobbe et al. (2021)](https://arxiv.org/abs/2110.14168)

#### 結果

用 175B 的 GPT-3 模型和 8,000 筆訓練範例，這個技巧把小學數學的準確率從約 33% 大幅拉到約 55%。

[![Verifier results](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/verifiers_fig5.png)
<br>Source: _Training Verifiers to Solve Math Word Problems_ by Karl Cobbe et al. (2021)](https://arxiv.org/abs/2110.14168)

#### 啟示

跟 self-consistency 一樣，這個方法可能很貴，每個任務產生 100 個解答，成本大約會變成 100 倍。

## 可靠度的理論

雖然上面的技巧做法各異，目標都一樣：提升複雜任務的可靠度。它們主要靠這幾種方式：

- 把不可靠的操作拆成較小、較可靠的操作（例如 selection-inference prompting）
- 用多個步驟或多重關係，讓整個系統的可靠度比任何單一元件都高（例如 maieutic prompting）

### Probabilistic graphical models

這種用不太可靠的元件組出可靠系統的思路，讓人想到 probabilistic programming，那個領域的很多分析技巧都能拿來用在這裡。

在 _Language Model Cascades_ 這篇論文裡，David Dohan 等人用 probabilistic graphical models 的框架來解讀上面這些技巧：

#### Chain of thought prompting

[![graphical model of chain of thought prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/lm_cascades_fig1.png)
<br>Source: _Language Model Cascades_ by David Dohan et al. (2022)](https://arxiv.org/abs/2207.10342)

#### Fine-tuned chain of thought prompting / Self-taught reasoner

[![graphical model of fine-tuned chain of thought prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/lm_cascades_fig3.png)
<br>Source: _Language Model Cascades_ by David Dohan et al. (2022)](https://arxiv.org/abs/2207.10342)

#### Selection-inference prompting

[![graphical model of selection-inference prompting](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/lm_cascades_fig4.png)
<br>Source: _Language Model Cascades_ by David Dohan et al. (2022)](https://arxiv.org/abs/2207.10342)

#### Verifiers

[![graphical model of verifiers](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/lm_cascades_fig5.png)
<br>Source: _Language Model Cascades_ by David Dohan et al. (2022)](https://arxiv.org/abs/2207.10342)

#### 啟示

把這些技巧寫成 probabilistic graphical models，不一定能馬上幫你解決某個具體問題，但這個框架可能有助於挑選、組合，甚至發現新的技巧。

## 結語

大型語言模型的研究非常活躍，變化很快。研究者不只持續改進模型，也持續改進我們對如何用好模型的理解。要看出這個步調，可以注意上面分享的論文全部都是過去 12 個月內發表的（我寫這篇的時間是 2022 年 9 月）。

未來會有更好的模型和更好的技巧出現。就算這裡的具體技巧被未來的最佳實務取代，背後的通用原則大概仍會是任何進階使用者工具箱裡的重要部分。

## 參考文獻

| Lesson                                                                                                                         | Paper                                                                                                                                     | Date     |
| ------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| Break complex tasks into simpler subtasks (and consider exposing the intermediate outputs to users)                            | [AI Chains: Transparent and Controllable Human-AI Interaction by Chaining Large Language Model Prompts](https://arxiv.org/abs/2110.01691) | 2021 Oct |
| You can improve output by generating many candidates, and then picking the one that looks best                                 | [Training Verifiers to Solve Math Word Problems](https://arxiv.org/abs/2110.14168)                                                        | 2021 Oct |
| On reasoning tasks, models do better when they reason step-by-step before answering                                            | [Chain of Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903)                                 | 2022 Jan |
| You can improve step-by-step reasoning by generating many explanation-answer outputs, and picking the most popular answer      | [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171)                               | 2022 Mar |
| If you want to fine-tune a step-by-step reasoner, you can do it with multiple-choice question & answer data alone              | [STaR: Bootstrapping Reasoning With Reasoning](https://arxiv.org/abs/2203.14465)                                                          | 2022 Mar |
| The step-by-step reasoning method works great even with zero examples                                                          | [Large Language Models are Zero-Shot Reasoners](https://arxiv.org/abs/2205.11916)                                                         | 2022 May |
| You can do better than step-by-step reasoning by alternating a ‘selection’ prompt and an ‘inference’ prompt                    | [Selection-Inference: Exploiting Large Language Models for Interpretable Logical Reasoning](https://arxiv.org/abs/2205.09712)             | 2022 May |
| On long reasoning problems, you can improve step-by-step reasoning by splitting the problem into pieces to solve incrementally | [Least-to-most Prompting Enables Complex Reasoning in Large Language Models](https://arxiv.org/abs/2205.10625)                            | 2022 May |
| You can have the model analyze both good and bogus explanations to figure out which set of explanations are most consistent    | [Maieutic Prompting: Logically Consistent Reasoning with Recursive Explanations](https://arxiv.org/abs/2205.11822)                        | 2022 May |
| You can think about these techniques in terms of probabilistic programming, where systems comprise unreliable components       | [Language Model Cascades](https://arxiv.org/abs/2207.10342)                                                                               | 2022 Jul |
| You can eliminate hallucination with sentence label manipulation, and you can reduce wrong answers with a 'halter' prompt      | [Faithful Reasoning Using Large Language Models](https://arxiv.org/abs/2208.14271)                                                        | 2022 Aug |

## 重點整理

- 模型答錯，常常是因為沒有空間推理，不是它不會。先讓它一步步想（`Let's think step by step`、few-shot 範例）通常就能改善。
- 把複雜任務拆成小子任務，是最通用的做法。任務越細，模型出錯的空間越小，也比較不會跑題。
- 多生成、再挑選（self-consistency 取多數決、verifier 打分數）可以拉高準確率，但成本會變成 N 倍，而且只適用答案有限的任務。
- 限制模型能說的內容（例如用句子標籤取代整句）和加一個 halter 判斷何時該停，可以減少 hallucination。
- 要把表現推到最高，通常要把 fine-tuning 和這些 prompt 技巧結合。

## 練習

1. 拿頁面上丟球那題（或自己挑一題多步驟數學題），分別用有和沒有 `Let's think step by step` 的 prompt 各跑 5 次，數一下答對幾次。
2. 把摘要任務改成兩段：先一個 prompt 辨識語言，再把辨識結果塞進第二個 prompt 做摘要，試試不同語言的文字，看會不會還滑回英文。
3. 對同一題用 temperature=0.7 取樣 10 次，每次都用 chain-of-thought prompt，寫幾行程式抽出最終答案並做多數決（self-consistency），比較跟單次回答的準確率差多少，也算一下成本多了幾倍。
