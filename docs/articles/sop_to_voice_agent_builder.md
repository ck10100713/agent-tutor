---
translated: true
source: articles/sop_to_voice_agent_builder.md
---
# 打造一個照 SOP 走的語音 agent

> 原文：[articles/sop_to_voice_agent_builder.md](https://github.com/openai/openai-cookbook/blob/main/articles/sop_to_voice_agent_builder.md)

把書面的 SOP 變成 prompt、tool 和應用程式端的檢查，讓語音 agent 在來電者改口或更正答案時，仍然走在正確的流程上。

## 這篇在做什麼

這篇用兩個範例流程示範怎麼讓 GPT-Live 語音 agent 照 SOP 做事：一個是照退貨 SOP 走的電商客服，一個是逐題問出可上班時段的排班助理。重點是 SOP 的規則不能只塞進 prompt，要分散到 GPT-Live 的 prompt、後端模型的 prompt 和應用程式程式碼三個地方。

## 學完你會

- 把一份 SOP 拆成「GPT-Live 的 prompt」「後端模型的 prompt」「應用程式檢查」三層，並知道每條規則該放哪層。
- 處理通話中途的狀況：過期或延遲的 handoff 要丟掉、消費者同意（consent）要另外驗證、使用者改口時只採用最新答案。
- 用 Decisions trigger 當備援，在 GPT-Live 漏掉或太晚 handoff 時仍然只觸發一次後端工作，不會重複存檔。

## 開跑前

- Python 3.12，以及 OpenAI Cookbook 的 [companion package](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/README.md)。
- 離線重播不需要 key；要用麥克風實際通話，需要設定 `OPENAI_API_KEY`，而且該 project 要有 GPT-Live 和 Terra（`gpt-6.1-terra`）的存取權。
- 建議戴耳機。

## 簡介

GPT-Live 讓你做出低延遲、能被打斷、對話自然的語音 agent。但很多應用還是得照一套詳細的流程、SOP 或結構化 workflow 走。

在 chained 語音架構裡，你的應用負責串起語音轉文字、模型回應和語音播放，所以每句話什麼時候開始、說什麼，都由你控制。GPT-Live 支援連續對話，聽、說和後端工作可以重疊進行。來電者可以在查詢還在跑的時候更正答案，也可以在聽到必要的但書之前就打斷說明。這樣對話比較自然，但要讓它照流程走，光把 SOP 放進 prompt 是不夠的。

## 內容包含什麼

- **錄音：** 九段簡短通話，是模擬來電者跟 GPT-Live 的對話。每個範例都會說明要注意聽什麼，例如替換品的提案、太晚的 handoff 或取消。
- **圖表和 tool 時間軸：** 圖表說明 app、語音模型和後端怎麼分工。時間軸把 handoff、tool 參數和結果放在錄音旁邊，可以直接跳到事情發生的那一刻。
- **可執行的範例：** [companion package](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/README.md) 裡有這兩個 app、它們的 prompt 和 tool，還有離線重播案例或用麥克風實際通話的說明。

## 在通話中管理 workflow

我們用兩個範例流程：一個是必須照退貨 SOP 走的電商客服，另一個是要逐題問出使用者可上班時段的排班助理。

先看一位 Blossom Store 的顧客來電詢問訂單追蹤，接著試圖違反政策爭取商店抵用金。再來看一個可用時段訪談員，它會儲存應徵者的答案，並從應徵者追蹤系統（ATS）取得後續問題。我們會一邊聽通話、一邊對照 tool log，追蹤語音前端、後端和應用狀態發生了什麼事。

在 [GPT-Live session](https://developers.openai.com/api/docs/guides/live-conversations) 裡，語音模型（`gpt-live-1`）負責跟來電者講話，你的 app 負責跑 workflow。你要給模型對話所需的指示，並告訴它什麼時候把工作交給後端。

1. **[Blossom Store](#example-1-blossom-store)。** 當追蹤請求變成損壞回報，GPT-Live 會用 [client delegation](https://developers.openai.com/api/docs/guides/live-delegation?delegation-mode=client#configure-client-delegation) 把新請求交給 app。用 `gpt-6.1-terra` 的 Responses 後端讀店家 SOP 並提出要用的 tool。app 在建立替換品之前，會先檢查訂單和來電者是否同意。
2. **[可用時段訪談](#example-2-structured-interviewing)。** GPT-Live 詢問開始上班的日子和偏好班別，每次回答後都 delegate。app 儲存每個明確的選擇，向 ATS 取得下一個正式問題，最後請應徵者確認兩個選擇。如果 GPT-Live 的 handoff 太晚，[針對來電者逐字稿的 Decisions trigger](https://developers.openai.com/api/docs/guides/decisions-voice#react-to-transcripts) 可以標記答案已完成。app 會記錄實際是哪個訊號啟動了工作。

## 前置條件與設定

在 Cookbook 網站上可以直接播放錄音；在 GitHub 上看就用 WebM 下載連結。要跑範例的話，使用 Python 3.12 和 [companion package](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/README.md)。以下指令請在你的 OpenAI Cookbook clone 根目錄執行，每次執行都用新的輸出目錄。

```sh
cd examples/audio/sop_voice_workflows
python3.12 -m venv .venv
source .venv/bin/activate
export PYTHONPATH=.
```

**離線重播 Blossom。** 這會對測試用的店家跑四句腳本化的來電者台詞和一個腳本化的後端。不需要 key、麥克風或安裝套件。在終端機找 `"pass": true`，並在 `runs/blossom-reference/reference.json` 找替換單 `RP001`。

```sh
python -m delivery.runner --reference --out runs/blossom-reference
```

**跟 Blossom Store 對話。** 接上耳機，為有 GPT-Live 和 Terra 存取權的 project 設定 `OPENAI_API_KEY`，然後執行下面的指令。看到「Connected. Speak now」之後，試著說「My desk lamp arrived with a cracked base. Can I get a replacement?」。結束時按 Ctrl-C。在 `runs/blossom-mic/final-state.json` 檢查 `store.effects`，看店家有沒有建立替換品。只是詢問的話，在你接受提案之前訂單不會有任何變動。

```sh
python -m pip install -r requirements.txt
python -m delivery_voice --mic --output runs/blossom-mic
```

**試試可用時段訪談。** 用同樣的相依套件，並且要有訪談模型的存取權，開一通新的通話。GPT-Live 會從應徵者追蹤系統（ATS）取得開場問題並詢問。

```sh
python -m interview_app --mic --output runs/interview-01
```

要離線檢視任一組設定，執行 `python -m delivery_voice --describe` 或 `python -m interview_app --describe`。要在不開語音 session 的情況下測 Blossom 的後端，可以[跑純文字案例](#choosing-a-backend-for-blossom)。

## 範例 1：Blossom Store

顧客來電問「我的訂單到哪了？」。追蹤請求還沒送到店家，室友就把包裹拿進來了。「燈壞了。」

## 1. 把訂單支援 SOP 變成 instructions 和 tool

從 [Blossom Store 的訂單支援 SOP](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/delivery/SOP.md) 的三種請求開始。針對每一種，決定後端必須查什麼、GPT-Live 該解釋什麼、哪些需要顧客許可。

- **追蹤配送。** `get_order({})` 回傳顧客所選訂單的物流更新。如果物流商有提供，GPT-Live 可以告知預計送達日。
- **申請延遲配送抵用金。** 訂單延遲超過 24 小時時，`check_credit_eligibility({})` 會回傳報價。抵用金是 $20 和訂單總額兩者中較小的。GPT-Live 說出金額、解釋會退回原付款方式，並徵求許可。顧客明確同意後，後端用報價 ID 請求 `register_credit`。
- **替換損壞商品。** 顧客描述損壞情況後，`check_replacement_availability` 會檢查訂單上的商品。物流商必須顯示已送達，而且同一商品要有庫存。GPT-Live 提供同一商品免費替換，寄到原訂單地址。顧客明確同意後，後端用 offer ID 請求 `create_replacement`。

我們來看店家 SOP 裡的這一條，並跟著它走進實作。

> 如果顧客更正細節或改變請求，使用最新的資訊。

| 規則該放哪裡 | 這個範例怎麼實作 |
| --- | --- |
| GPT-Live 的 prompt | 「把訂單問題、損壞描述、抵用金請求，以及對未結提案的回覆交給後端處理。」當來電者回報損壞，GPT-Live 會 delegate 並交出新請求。 |
| Terra 的 prompt | 「先前被中斷的查詢不提供可用結果。」Terra 重新讀取所選訂單。一拿到商品 ID 並知道壞了什麼，就請求 `check_replacement_availability`。 |
| 應用程式碼 | 用時間戳把每個 handoff 對應到來電者說的話。如果追蹤的 handoff 在來電者回報損壞之後才到，就丟掉。建立替換品之前，先確認來電者同意的是店家剛剛提出的那個提案。 |

## 2. 通話流程

1. **「我的訂單到哪了？」** GPT-Live delegate 追蹤請求。在這個測試裡，我們故意延遲追蹤的 handoff，直到來電者開始說燈壞了。我們要檢查 app 會跳過過期的追蹤查詢，並在 GPT-Live 交出損壞回報時改走替換流程。
2. **「其實室友剛把它拿進來了。燈壞了。」** 新請求優先。後端為損壞回報取得訂單，並詢問燈的哪個部分壞了。
3. **「底座裂了。」** 後端用訂單裡的商品 ID 和顧客的描述檢查庫存。店家提供另一盞檯燈免費替換，寄到原訂單地址。GPT-Live 現在可以說明這些條件並詢問顧客是否要替換。
4. **「好，寄替換品給我。」** Terra 請求 `create_replacement({"offer_id": "REPL-LAMP-1"})`。在開立新的替換品之前，目前的 app 會先跟 Terra 做一次獨立的同意檢查，確認顧客是否同意 GPT-Live 所描述的提案。店家檢查提案是否仍有效，並只記錄一筆替換。GPT-Live 可以唸出店家的收據。

![The customer reports a broken lamp before the tracking handoff arrives. The app drops the old handoff, checks the lamp, and creates one replacement after the customer accepts.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/audio/sop_voice_workflows/diagrams/store-order-support.svg)

想追蹤太晚的追蹤 handoff 和替換流程，請看[完整尺寸的 Blossom Store 圖](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/diagrams/store-order-support.svg)。

<a id="lets-listen-and-inspect-the-tool-calls"></a>

## 聽聽燈壞掉的通話

在這通電話裡，顧客從「我的訂單到哪了？」開始，最後確認替換一盞壞掉的檯燈。

<audio controls preload="metadata" aria-label="Blossom Store. A customer reports a broken lamp and accepts a replacement." src="../examples/audio/sop_voice_workflows/recordings/blossom-late-handoff.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/blossom-late-handoff.webm?raw=true">Download the broken-lamp call (WebM)</a>
</audio>

<details id="blossom-tool-calls" style="border: 1px solid #84848455; border-radius: 8px; padding: 0.75rem 1rem">
<summary style="cursor: pointer"><strong>顯示 tool call</strong></summary>

時間從錄音開頭算起。展開每個 call 可以看參數和當時發生的事。

<details>
<summary style="cursor: pointer">0:03.18 · 扣住原本的追蹤 handoff</summary>

測試故意扣住 GPT-Live 的追蹤 handoff，在 **0:03.78**（來電者開始回報損壞時）才放出同一個事件。它的時間戳仍然指向追蹤請求，所以 app 在它能執行任何店家 tool 之前就忽略了它。

</details>
<details>
<summary style="cursor: pointer">0:07.52 · GPT-Live 把損壞回報交給 app</summary>

GPT-Live 為「燈壞了」送出第二次 delegation。app 把更新後的對話交給 Terra，Terra 為損壞回報請求取得訂單。

</details>
<details>
<summary style="cursor: pointer">0:09.42 · 讀取訂單，確認損壞的商品</summary>

`get_order({})`

店家回傳 `shipping_status: delivered`，並辨識出商品是一盞檯燈（`LAMP-1`）。GPT-Live 問是哪個部分損壞。

</details>
<details>
<summary style="cursor: pointer">0:22.52 · 檢查這盞燈能不能替換</summary>

`check_replacement_availability({"item_id": "LAMP-1", "damage_description": "The base is cracked"})`

店家提供同一盞燈免費替換，寄到原訂單地址，並回傳 offer ID `REPL-LAMP-1`。GPT-Live 說明條件並徵求許可。

</details>
<details>
<summary style="cursor: pointer">0:39.14 · 顧客接受後建立替換品</summary>

`create_replacement({"offer_id": "REPL-LAMP-1"})`
來電者在 **0:34.84** 開始說「好，寄替換品給我」。店家回傳 `status: created` 和 `RP001`，GPT-Live 接著唸出這個編號。

</details>

想從 tool call 直接跳到錄音中的對應時刻，請看[完整通話時間軸](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/recordings/broken-lamp.html)。

</details>

## 政策協商

像抵用金這種有實質影響的事，我們要確保有照政策走。如果 GPT-Live 問「要不要把 $20 抵用金退回您原本的付款方式？」，**「That works for me. Let’s do that」** 是明確的同意，但 **「Yes, but can you make it $35?」** 在確認任何抵用金之前還需要再談。

Terra 照 SOP 選擇要請求哪個 tool。當它提議開立新抵用金或建立替換品時，app 會對 Terra 做第二次不帶 tool 的 Responses 呼叫，並提供已驗證的條款、GPT-Live 的提案，以及來電者完整的回覆。Terra 要指出傳達每個必要條款的字句，並判斷來電者是否同意。例如 GPT-Live 提供另一盞燈卻沒提價格，價格欄位就應該是空的。app 要求每個條款都有證據，而且決定是 `accepted` 才會繼續。

Python 負責檢查店家能驗證的事實。被提供的報價必須仍屬於這張訂單、來電者的回覆必須仍是最新的、店家對這個提案不能已有送出紀錄。審查結果不確定或無法取得時，帳本維持不動。如果檢查進行中來電者又開口說話，app 會丟掉舊的決定。

**來電者要求 $35。** GPT-Live 說明店家能提供 $20，並問來電者要不要。店家不發放任何抵用金。

<audio controls preload="metadata" aria-label="Blossom Store. The caller asks for $35 after a $20 offer." src="../examples/audio/sop_voice_workflows/recordings/blossom-consent-counteroffer.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/blossom-consent-counteroffer.webm?raw=true">Download the $35 counteroffer (WebM)</a>
</audio>

<details><summary><strong>查看還價的 tool call</strong></summary>

在 0:06.10，店家用 `get_order` 取得訂單。在 0:07.26，`check_credit_eligibility` 回傳 $20 的報價。來電者要求 $35 之後，GPT-Live 在 0:22.90 把回覆交給 Terra。Terra 沒有要求任何寫入，所以 app 沒有同意檢查要跑，帳本維持空的。

我們也用同樣的回覆[測試了錯誤的寫入請求](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/delivery/consent-results.json)。測試仍然提議登記那筆 $20 報價時，同意檢查回傳 `not_accepted`，店家拒絕了這個請求。

</details>

**來電者接受。** 這位來電者說「That works for me. Let’s do that.」。注意聽回覆前的提案，以及店家發放抵用金之後的確認。

<audio controls preload="metadata" aria-label="Blossom Store. The caller accepts the $20 credit in their own words." src="../examples/audio/sop_voice_workflows/recordings/blossom-consent-acceptance.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/blossom-consent-acceptance.webm?raw=true">Download the accepted $20 credit (WebM)</a>
</audio>

<details><summary><strong>查看已接受的抵用金和它的同意檢查</strong></summary>

店家在 0:05.84 取得訂單，在 0:06.88 檢查資格。來電者接受後，Terra 提議 `register_credit({"quote_id":"CREDIT-20"})`。同意審查在 GPT-Live 的提案裡找到 $20 金額、原付款方式，以及徵求許可的說法。在 0:25.14，店家登記了這筆報價並回傳 `RF001`。帳本裡有一筆抵用金。[錄下來的 tool 時間軸](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/recordings/blossom-consent-calls.json)除了兩份最終帳本，也包含審查者的證據。

```json
{
  "decision": "accepted",
  "spoken_evidence": {
    "amount": "twenty dollar credit",
    "payment_method": "your original payment method",
    "permission_request": "Would you like me to register it?"
  }
}
```

</details>

<details><summary><strong>聽聽來電者打斷提案時會怎樣</strong></summary>

注意聽 GPT-Live 在店家發放抵用金之前，會重複抵用金條款並再次徵求許可。

<audio controls preload="none" aria-label="Blossom Store. The caller interrupts the credit offer and asks GPT-Live to repeat it." src="../examples/audio/sop_voice_workflows/recordings/blossom-interruption.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/blossom-interruption.webm?raw=true">Download the interrupted offer (WebM)</a>
</audio>

在這段較早的錄音裡，來電者在 0:10.82 GPT-Live 還沒徵求許可前就搶話。GPT-Live 重複了 $20 的金額、說出原付款方式，並再問了一次。來電者新的「Yes」從 0:20.92 開始。店家在 0:23.74 登記了一次抵用金。

</details>

<a id="choosing-backend-models"></a>

## 為 Blossom 選後端

用 client delegation 的話，由我們的 app 決定哪個模型處理 GPT-Live 送來的店家請求。我們選了 `gpt-6.1-terra`，因為在我們的測試裡它比 Luna 更穩定地照 Blossom 的 SOP 走。

**照 SOP 走。** 在[原始的後端測試](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/delivery/REPORT.md#how-we-compared-the-backends)裡，兩個模型拿到同樣的 SOP、五個店家 tool 和腳本化的文字回覆。這個測試是在加入獨立的同意檢查之前跑的。

| 錄下的後端執行，重新評分 | Terra | Luna |
| --- | ---: | ---: |
| 完整照 SOP 走的執行次數 | 68/68 | 65/68 |
| 明確同意後又再問一次許可 | 0/29 | 0/29 |
| 店家 tool call 總數 | 157 | 172 |

有位來電者對 $20 的提案回覆「Yes, but can you make it $35?」。Terra 會問 $20 可不可以接受。在[其中一次 Luna 的執行](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/delivery/results.json)裡，Luna 直接請求了抵用金。測試用的店家只檢查來電者回覆的是一個目前有效、未使用的報價，並依賴 Luna 解讀回覆，所以發出了 $20。

我們用一個文字審查者[重新評分了存下來的回覆](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/delivery/credit-grade-results.json)，它會讀完整的抵用金提案，但看不到預期的價格。它找出實際提供的金額、錢會去哪裡，以及 agent 有沒有徵求許可，再由程式把它的結果跟店家的報價比對。另有一次 Luna 的回覆提供了正確的 $20，但漏掉了 app 記錄新提案所需的報價 ID，那次執行沒有發放抵用金。這個檢查評的是後端的文字。要知道 GPT-Live 實際說了什麼，要看接收端的音訊。

[計時資料](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/diagrams/blossom-backend-time.json)涵蓋後端處理每句腳本化回覆的工作，包括 tool call。Luna 多出來的 15 次 call 裡，有 12 次是訂單查詢。

![Median backend time per scripted caller turn, including tool round trips. Terra, 2.88 seconds. Luna, 3.18 seconds. Each median covers 129 turns.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/audio/sop_voice_workflows/diagrams/blossom-backend-time.svg)

**檢查同意。** 現在，店家在發放新抵用金或建立替換品之前，會另外用一次 Terra 呼叫，檢查 GPT-Live 有沒有說明店家的條款、來電者有沒有同意。

我們[測試了這個檢查](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/delivery/REPORT.md#checking-consent-before-a-write)：每次試驗都要求店家照做，即使來電者說了不。試驗在審查跑完、且店家正確發放或拒絕抵用金或替換品時算通過。在含重複的 78 個案例中，Terra 通過 **142/142** 次試驗，Luna 通過 **133/142**。Terra 的檢查中位數耗時 2.00 秒。

**試試燈壞掉的案例。** 裝好相依套件，並為有 Terra 存取權的 project 設定 `OPENAI_API_KEY` 後，執行這個針對目前 app 的純文字測試。

```sh
python -m delivery.runner --ids status_to_damage --out runs/blossom-terra
```

打開輸出目錄裡的 `status_to_damage__gpt-6.1-terra__1.json`，可以看 tool call、結果和評分。通過的執行會記錄一筆替換。你也可以[用兩個後端跑同一個案例](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/delivery/REPORT.md#try-the-same-case)。

## 範例 2：結構化訪談

我們要做一個簡單的排程器，訪談員要收集兩個偏好：開始上班的日子和班別。ATS 在通話前提供開場問題。每次明確選擇後，app 儲存答案並查下一題要問什麼。app 必須能處理應徵者隨時更改答案或選擇。

## 1. 用第一個問題開始 session

用 ATS 的開場問題「Which start day works for you, Monday or Tuesday?」當作 GPT-Live 的起點。[訪談 prompt](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/interview_app/meaning.py) 讓每個模型各司其職。

| 誰 | 我們要它做什麼 |
| --- | --- |
| **GPT-Live**，訪談員 | 一次問一個正式問題。把答案、更正和請求交給 app。等 app 提供下一題。 |
| **Decisions**，盯著逐字稿 | 在應徵者說話時，問「app 有事要做嗎？」（`needs_backend_v1`）和「答案取決於某個條件嗎？」（`condition_v1`）。隨著更多字出現，Decisions 可以修改任一個標籤。 |
| **Luna**，後端解讀者 | 連同目前的問題、訪談紀錄和 Decisions 標籤，一起讀受訪者的回覆。提出下一步，例如儲存日期、釐清條件或重複問題。 |

app 在儲存答案之前，會拿 Luna 的提案對照目前的 ATS 紀錄做檢查。在缺少 handoff 時，Decisions 的結果可以啟動這個檢查。如果檢查已經在跑，trigger 不會再多存一次。

## 當一句回覆回答了兩個問題

GPT-Live 問應徵者哪天可以開始。「Yeah, I could work any shift on Monday」一次回答了兩個問題。在 **0:10.10**，GPT-Live 把回覆交給 app，Decisions 也標記了這個答案。app 只從 GPT-Live 的 handoff 啟動一次後端工作。

在 **0:13.26**，app 儲存 Monday，並問 ATS 接下來是什麼。ATS 回傳班別問題，並列出 `either` 為允許的答案。因為應徵者已經說過任何班別都行，app 就儲存 `either`，再問 ATS 一次。只有確認動作會回到 GPT-Live。注意聽訪談員把兩個選擇唸回來並請應徵者確認。

<audio controls preload="metadata" aria-label="Availability interview. The candidate can work any shift on Monday." src="../examples/audio/sop_voice_workflows/recordings/interview-multi-answer.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/interview-multi-answer.webm?raw=true">Download the Monday interview (WebM)</a>
</audio>

<details>
<summary>查看週一的 tool call</summary>

時間軸把 **0:13.26** 的四個 call 依 app 執行的順序放在一起。

| ATS call | 結果 |
| --- | --- |
| `record_answer({"question_id": "day", "value": "Monday"})` | 以 revision 1 儲存 Monday。 |
| `get_next_question({})` | 回傳班別問題，允許的答案包含 `either`。 |
| `record_answer({"question_id": "shift", "value": "either"})` | 以 revision 2 儲存班別。 |
| `get_next_question({})` | 回傳確認問題。 |
在 **0:29.00**，應徵者確認兩個選擇之後，`complete_interview({"day": "Monday", "shift": "either"})` 以 revision 3 記錄了完成。

</details>

打開[完整的週一時間軸](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/recordings/interview-multi-answer.html)，可以跳到錄音中的某個 handoff 或 tool call。

**當答案帶有條件。** 應徵者說「Tuesday, if the shift ends before five.」。GPT-Live 把答案交給 app。app 把 Tuesday 和應徵者的條件放在一起。ATS 沒有班別時數可以查，所以 GPT-Live 解釋這點，並問是否先不確認 Tuesday。注意聽後續的問答。通話結束時，ATS 仍然沒有已確認的開始日。

<audio controls preload="metadata" aria-label="Interview call with tentative Tuesday availability and a five o'clock finish condition" src="../examples/audio/sop_voice_workflows/recordings/interview-conditional-clarification.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/interview-conditional-clarification.webm?raw=true">Download the conditional Tuesday answer (WebM)</a>
</audio>

<details>
<summary>這兩通測試通話發生了什麼？</summary>

兩通電話裡，handoff 都是 GPT-Live 自己做的。app 在處理時它先簡短回應應徵者，然後問要不要把 Tuesday 留空。在主打的那通裡，這段後續問話第一個有聲的部分，在 app 回傳指引後 0.98 秒到達接收端。第二通的接收端音訊也很清楚，但有兩個字幕字詞和指引落在同一個時間 frame。[錄音檢查和 ATS 結果](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/recordings/interview-conditional-clarification.json)包含較早的嘗試，以及五個文字測試，測的是接下來會發生什麼事。重複說「Tuesday」會讓條件維持未解決。說明條件已經解決，則可以確認這一天。

</details>

ATS 一旦有了日期和班別，就會把兩者當作摘要回傳。GPT-Live 把它們唸回來，說明這只是記錄可用時段，並不代表確認錄取，再請應徵者確認兩項。在完成訪談之前，app 會[檢查目前的摘要和它的播放證據](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/interview_app/workflow.py#L188-L199)。如果 app 只能驗證口述摘要的一部分，就保留已儲存的答案，並請 GPT-Live 再唸一次。有更正的話，要用更新後的答案產生新的摘要。

![In the recorded Tuesday call, Decisions starts the interview check while the app holds GPT-Live’s handoff. The ATS saves Tuesday once.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/audio/sop_voice_workflows/diagrams/interview-current.svg)

## 2. 漏掉或太晚的 delegation

在[錄下的 Tuesday 通話](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/recordings/interview-handoff.html)裡，Decisions 在 **0:09.32** 標記了答案。GPT-Live 在 **0:09.68** delegate，但測試故意扣住這個 handoff。在 **0:10.96**，controller 記錄了 `decisions_recovery`，並請 Luna 解讀答案。在 **0:12.66**，ATS 只儲存一次 Tuesday 並回傳班別問題。太晚到的 handoff 指向同一個答案，沒有造成第二次儲存。

<audio controls preload="metadata" aria-label="Tuesday answer with a deliberately delayed handoff" src="../examples/audio/sop_voice_workflows/recordings/interview-handoff.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/interview-handoff.webm?raw=true">Download the late Tuesday handoff (WebM)</a>
</audio>

看 controller 的 `app.route` 事件上的 `reason`，就知道是什麼啟動了解讀。app 對每次處理的逐字稿更新記錄一個 reason。

| log 裡的 route | 發生了什麼 |
| --- | --- |
| `native_delegation` | GPT-Live 把答案交給 app。Decisions 可能也標記過。 |
| `decisions_recovery` | 沒有任何 handoff 認領這個答案。Decisions 把最新的逐字稿更新標記為需要後端處理。 |
| `settled_unclassified` | 沒有 handoff，也沒有 Decisions 的正向結果。在 1.8 秒沒有新的語音或逐字稿文字之後，這個範例會請 Luna 解讀手上有的內容。如果 trigger 把回覆標為 backchannel（附和語），就跳過這個備援。 |

啟動解讀不代表授權儲存。例如沒有 condition 標籤時，光靠 timeout 不能確定 Tuesday。[controller](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/interview_app/live.py) 在啟動解讀者之前，會先把這筆逐字稿更新標記為處理中。三種 route 都用這個檢查。

```python
# Excerpt from Controller.tick, with timing and logging omitted.
if t.source in t.jobs or t.done == t.source:
    return
t.jobs.add(t.source)
scope = {"turn": t.number, "source_event_id": t.source,
         "revision": self.store.snapshot()["revision"]}
self.start(self.process(t, scope, labels))
```

**Tuesday 還是答案嗎？** Luna 解讀「Tuesday」的時候，應徵者可能又補一句「actually, Monday」。Luna 回覆時，app [會檢查自己手上仍是同一個答案](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/interview_app/live.py#L445-L453)。如果應徵者又說話了、逐字稿變了，或 ATS 紀錄有了較新的版本，app 就丟掉舊的解讀。

**先儲存，再問下一題。** 在這通電話裡，儲存 Tuesday 讓訪談紀錄從版本 0 變成版本 1。app 用版本 1 [向 ATS 要下一個問題](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/interview_app/workflow.py#L241-L248)。日期填好之後，ATS 回傳班別問題。app 用 `session.commentary.append` 把它送給 GPT-Live，`delegation_id: null`，因為沒有 GPT-Live 的 handoff 擁有這件工作。`app.route` 的紀錄告訴我們是 Decisions 啟動的。

**如果儲存確認遺失，** app 會[檢查 ATS 的收據](https://github.com/openai/openai-cookbook/blob/b71327cc3713b87229eab2407c07ff8b95c9a00d/examples/audio/sop_voice_workflows/interview_app/store.py#L93-L103)，找結尾是 `/save_day` 的請求。下一題的請求有自己的 ID，結尾是 `/after_day`。用同樣的 ID 和參數重試，會回傳原本的結果。

## 3. 檢查更正、取消和查詢失敗

**更正。** 如果應徵者把 Monday 改成 Tuesday，就用最新的答案。從 Monday 開始的工作不能蓋掉 Tuesday。在錄下的更正測試裡，ATS 先儲存 Monday，然後改成 Tuesday，並再次取得班別問題。

**取消。** 「Maybe cancel the interview」不會關閉紀錄。只有當後端把回覆解讀為要求停止，而且 Decisions 把它標為明確時，app 才能取消。在我們的通話裡，「Please cancel this interview now」產生了一次取消。

<details><summary><strong>聽兩次取消請求並查看結果</strong></summary>

<audio controls preload="none" aria-label="A candidate considers cancelling, then clearly asks to stop." src="../examples/audio/sop_voice_workflows/recordings/interview-cancel.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/interview-cancel.webm?raw=true">Download the cancellation call (WebM)</a>
</audio>

Decisions 把「Maybe cancel」標為 `incomplete`，app 讓紀錄保持開啟。第二次回覆之後，Decisions 回傳 `unconditional`，後端請求取消。ATS 只跑了一次 `cancel_interview({})`。

</details>

**查詢失敗。** ATS 儲存了 Tuesday，但無法提供下一題。app 暫停 session，紀錄仍保持開啟。在接收端錄音裡，GPT-Live 說：「I saved Tuesday. I couldn’t retrieve the next question, so we’ll pause here.」。這個 workflow 沒有招募後續追蹤的佇列。

<audio controls preload="metadata" aria-label="Availability interview. Tuesday is saved and the interviewer pauses when the next question is unavailable." src="../examples/audio/sop_voice_workflows/recordings/interview-lookup-pause.webm">
  <a href="../examples/audio/sop_voice_workflows/recordings/interview-lookup-pause.webm?raw=true">Download the failed lookup (WebM)</a>
</audio>

<details id="failed-lookup-tool-calls" style="margin-top: 0.75rem; border: 1px solid #84848455; border-radius: 8px; padding: 0.75rem 1rem">
<summary style="cursor: pointer"><strong>顯示 tool call</strong></summary>

在這段錄音的 **0:12.70**，[tool 收據](https://github.com/openai/openai-cookbook/blob/main/examples/audio/sop_voice_workflows/recordings/interview-lookup-pause-tools.json)顯示答案是在查詢失敗之前就已儲存。

1. `record_answer({"question_id": "day", "value": "Tuesday"})` 回傳 `ok`。ATS 以 revision 1 儲存 Tuesday。
2. 在 revision 1 的 `get_next_question({})` 回傳 `unavailable`。ATS 保留 Tuesday、班別維持空白，也沒有記錄完成。

</details>

## 把回合制 workflow 改成 GPT-Live

在回合制語音 app 裡，來電者說完話，你的程式碼才決定 agent 回覆前要做什麼。用 GPT-Live 的話，後端在忙的時候對話還在繼續。來電者可以停頓一下，聽到 agent 開始回應，然後對一個聽起來已經完整的答案補上「but only if…」。你要重新思考應用架構，才能善用模型的低延遲和全雙工特性，同時在後端提供結構、guardrail 和檢查。

把 SOP 帶進 GPT-Live 時，先問每個步驟「怎樣才算完成」。用 prompt 告訴 GPT-Live 什麼時候要找後端取得指引或已驗證的事實。用 Decisions trigger 來追蹤情緒、當 guardrail、標記後端工作，或評估 agent 或來電者正在說什麼。

要測整通電話的 workflow 表現，請參考 [GPT-Live 評估指南](https://developers.openai.com/cookbook/examples/audio/voice_agent_evaluation)。

## 重點整理

- SOP 的一條規則通常要拆到三個地方：GPT-Live 的 prompt 決定何時 handoff，後端模型的 prompt 決定怎麼用 tool，應用程式碼負責驗證事實和時序。
- 全雙工對話裡，過期的結果一定會出現。用時間戳、逐字稿版本和 ATS 的 revision 判斷結果是否還是最新，過期就丟掉。
- 有實質影響的寫入（抵用金、替換品）要在 app 端另做一次同意檢查，要求每個條款都有證據，不能只靠 agent 自己說「對方同意了」。
- Decisions trigger 是 handoff 的備援，而不是第二條寫入路徑。啟動解讀不等於授權儲存，所以一個答案不會被存兩次。
- 儲存要有冪等性：用帶固定 ID 的請求，丟了確認也能重試並拿回原結果。

## 練習

1. 在 Blossom 的 SOP 規則表（GPT-Live 的 prompt、Terra 的 prompt、應用程式碼）裡，替「抵用金不能超過訂單總額」這條規則決定放哪一層，並寫一句理由。
2. 把 `settled_unclassified` 的 1.8 秒等待時間改成 0.5 秒和 4 秒各跑一次，觀察 `app.route` 的 reason 分佈和 Tuesday 被存幾次有什麼變化。
3. 在訪談 app 的儲存流程裡，模擬「save 的確認遺失」：用同一個以 `/save_day` 結尾的請求 ID 和參數重送兩次，確認 ATS 的 revision 沒有多加一次。
