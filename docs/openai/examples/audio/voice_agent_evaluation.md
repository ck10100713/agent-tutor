---
translated: true
source: examples/audio/voice_agent_evaluation.md
---
# GPT-Live 評估指南

> 原文：[examples/audio/voice_agent_evaluation.md](https://github.com/openai/openai-cookbook/blob/main/examples/audio/voice_agent_evaluation.md)

用受控請求、錄好的音檔和模擬對話，評估全雙工 (full-duplex) 語音 agent，衡量互動品質和經過驗證的任務結果。

## 這篇在做什麼

語音 agent 要一邊維持自然的對話，一邊把使用者交辦的事做對。這篇用一個虛構的餐廳訂位助理當範例，介紹 CRAWL、WALK、RUN 三種評估模式，從單次合成語音一路到完整的模擬通話。

## 學完你會

- 把一個請求從語音、delegation、tool 呼叫一路追到最後的應用程式狀態，並分別驗證每個邊界
- 依序用 CRAWL（合成語音）、WALK（真人錄音加雜訊）、RUN（模擬來電者）設計 eval 情境
- 挑出關鍵指標（task completion、tool accuracy、response latency 等），判斷失敗是 assistant、基礎設施還是 grader 的問題

## 開跑前

要實際跑 harness 的話，需要 OpenAI API key 和 GPT-Live 的存取權限，執行方式看 repo 裡的說明。

## 簡介

全雙工語音 agent 必須同時做到兩件事：維持自然、持續展開的對話，以及把使用者的任務正確完成。GPT-Live 可以一邊聽、一邊說、接受更正，還能在音訊持續進行時把工作委派出去。所以只評估逐字稿或最後的回覆，會漏掉重要的失敗情形。

完整的評估要追著一個請求走過整個系統：使用者說出口的意圖、agent 的對話行為、被委派的工作、實際執行的 tool、最後的應用程式狀態，以及最終傳達給使用者的結果。一句聽起來自然的確認，並不能證明後端有做對事。

這份指南介紹三種評估模式，複雜度分三個階段往上加。**CRAWL** 用合成的音訊測試受控的單回合請求。**WALK** 重播已儲存的錄音，測試音訊真實度和穩健性。**RUN** 加入獨立的模擬來電者，評估連續的多回合對話。這三種模式評估的是同一個 GPT-Live 助理、後端、tools 和應用程式，只是來電者輸入跟互動複雜度不同。

這份指南著重在持續性的、以任務為主的語音 agent 評估，因為 prompt、tool、模型跟應用邏輯會不斷演進。你也可以先做一次性的能力檢查，例如辨識口說的名字、數字和英數字串、轉錄準確度或複誦表現，確認模型符合你基本的音訊與語音需求。然後再用這個框架持續評估對話行為跟任務結果。

### 程式碼

可以直接跑的參考實作，請看 [GPT-Live evaluation harness](https://github.com/openai/openai-cookbook/tree/main/examples/audio/duplex_voice_agent_evaluation)。

repo 裡每種評估模式都有一個 harness：

- [Crawl](https://github.com/openai/openai-cookbook/tree/main/examples/audio/duplex_voice_agent_evaluation/crawl_harness)（單回合重播）

- [Walk](https://github.com/openai/openai-cookbook/tree/main/examples/audio/duplex_voice_agent_evaluation/walk_harness)（單回合錄音重播）

- [Run](https://github.com/openai/openai-cookbook/tree/main/examples/audio/duplex_voice_agent_evaluation/run_harness)（多回合來電者模擬）

執行 eval 的說明在 repo 裡。

你可以讓 Codex 指向想用的 harness，請它把評估改成適合你的應用、資料跟 grader。

## GPT-Live 基礎

GPT-Live 是兩層式架構。

`gpt-live-1` 語音前端負責處理即時對話，並決定要直接回答還是委派。用 Responses delegation 時，服務會提供後端 context；用 client delegation 時，你的應用會收到 delegation 的 metadata，並根據逐字稿和已驗證的應用狀態提供 context。後端負責比較深的推理、呼叫 tool 和更新應用狀態。

因此 GPT-Live 有兩個各自重要的職責：

1. 進行口語對話

2. 必要時把工作委派給後端模型

這個架構要求你分別評估每個邊界。要驗證 GPT-Live 有委派對的工作、後端有完成對的動作，以及 GPT-Live 有把已驗證的結果正確告訴使用者。

![Voice frontend and delegated backend architecture](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/voice-agent-evaluation/figure-01.png)

### 以 GPT-Live 的連續音訊為基礎

GPT-Live 在說話的同時也在聽，所以使用者說話、助理回應、打斷、委派的推理和 tool 執行可能互相重疊。評估 harness 因此必須把音訊和事件對齊到持續前進的時間軸上，不能假設對話是乾淨地輪流進行。它不能在兩次交談之間暫停時鐘：GPT-Live 預期收到連續的音訊串流，對話的回合是事後觀察出來的，不是在執行時強制規定的。

![Continuous duplex audio timeline](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/voice-agent-evaluation/figure-02.png)

### 追蹤一個任務，從語音到狀態

這份 cookbook 用一個虛構的餐廳訂位助理當貫穿全篇的範例。應用程式提供查詢空位、建立訂位、取消已授權訂位的 tools。

以 `restaurant_003` 為例，這是 CRAWL 跟 WALK 都會用到的「帶更正的訂位請求」。使用者說：“Book a table for Maya on August 7—sorry, August 6—at 7 p.m. for two.” 要通過評估，必須保留更正、剛好建立一筆 8 月 6 日的訂位、驗證最後的應用狀態，而且要等 tool 成功之後才確認訂位。

- **我們希望 agent 做的事：** `create_reservation(guest_name="Maya", date="2026-08-06", time="19:00", party_size=2)`

- **我們希望 agent 避免的事：** 建立 8 月 7 日的訂位、建立重複的訂位、或在執行完成前就確認成功

- **我們用來評估的依據：** 來源音訊、更正後的意圖、實際的 tool 呼叫跟參數、驗證過的最終狀態，以及完成後的口語確認

## 評估策略

### 要衡量的品質面向

評估時把音訊品質跟內容品質分開來看很有用，因為兩者可以各自失敗。自然的語音無法彌補錯誤的任務執行，任務做成功也無法彌補糟糕的口語互動。

在 GPT-Live 裡，同樣的原則適用於雙層架構的不同元件：

- **音訊與互動品質：GPT-Live**

GPT-Live 聽和說得好不好？包括清晰度、自然度、語速、回應時機、打斷與重疊的處理、附和聲 (backchannel)，以及是否準確傳達後端的結果。

- **推理與任務品質：GPT-Live 模型與 delegation 模型**
整個系統有沒有正確理解並完成使用者的請求？前端必須保留使用者的意圖並委派適當的工作。後端必須執行正確的動作，並回傳經過驗證的結果給前端轉述。

### Crawl, walk, run

與其一次評估所有複雜度的來源，不如把每個維度隔離開來。GPT-Live 的評估主要差在使用者音訊的來源跟真實度，以及互動的複雜度。

跟 [Realtime Eval Guide](https://developers.openai.com/cookbook/examples/realtime_eval_guide) 類似，我們採用 crawl、walk、run 的方式：

- **Crawl：** 合成音訊加上受控的單回合請求

- **Walk：** 已儲存的錄音加上受控的單回合請求

- **Run：** 模擬使用者加上連續的多回合對話

![Crawl, walk, and run evaluation strategy](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/voice-agent-evaluation/figure-03.png)

每種模式設計成讓不同的品質面向看得見。

**CRAWL** 用合成音訊建立功能基準線，評估推理與任務品質這一軸。**WALK** 測試這個行為在真實錄音及其聲學條件下是否還成立。**RUN** 用模擬來電者評估完整的全雙工對話。

自動化評估穩定之後，可以選擇加入人工評估，驗證真實世界的表現，並評估比較主觀的品質，例如對話自然度、韻律、口音或文化上是否恰當。

### 指標

所有評估模式都會回報任務完成度、診斷分數和佐證。當助理達成預期結果、到達預期的應用狀態，且滿足所有必要限制時，情境才算通過。CRAWL 跟 WALK 還會強制檢查 `expected.tools.required` 裡有順序的呼叫；RUN 則把這些呼叫當成偏好 tool 的診斷，只強制標了 `critical: true` 的流程步驟。

在推理與任務指標上，**task completion 是最主要的衡量**。當助理達成預期結果、到達預期的應用狀態、滿足必要要求，且沒有未授權的動作時，情境才算通過。語意品質、tool 準確度、delegation 準確度和執行次數這類次要指標，用來解釋失敗原因並找出改進機會。這些指標提供診斷細節和部分給分，但要通過仍必須滿足所有必要的任務、tool 跟 delegation 檢查。

在音訊與互動方面，我們用一小組團隊可以透過 prompt 和應用設計實際影響的指標。Response rate、latency 和打斷次數，幫助評估回應速度跟輪流說話。Speaking duration 幫助評估話多不多，delegation 期間的沉默則暴露後端工作時的延遲。

這組指標只是起點。如果你的應用很在意針對性的能力檢查，例如辨識口說的英數字串、名字和數字、轉錄準確度或 word error rate、複誦表現，就把相關指標跟單回合或多回合情境加進你的持續評估裡。

評分結合了確定性檢查跟獨立的 LLM judge。確定性檢查驗證可觀察的證據，例如 tool 呼叫、參數、授權、應用狀態和音訊時間。LLM judge 評估結果跟對話品質，必要時給部分分數。

用量會分開追蹤被評估助理的前端和後端。

人工審查者可以補足自動評估的缺口，特別是主觀的音訊品質，例如自然度、韻律、發音，以及對話節奏是否恰當。
| **Category** | **Metric** | **Description** | **Applies to** |
| --- | --- | --- | --- |
| **Reasoning & task** | **Task completion** | Whether the assistant achieves the intended outcome and application state while satisfying mandatory constraints (pass/fail). | All modes |
| **Reasoning & task** | **Semantic quality** | LLM-judged score for task understanding, context fidelity, clarification quality, grounded communication, and conversational coherence, as applicable. | All modes |
| **Reasoning & task** | **Tool accuracy** | Deterministic comparison of executed tools and arguments with expected calls. Missing, extra, or failed calls reduce the score. | All modes |
| **Reasoning & task** | **Tool calls** | Actual versus expected tool calls. Helps identify missing work, redundant calls, and unnecessary loops. | All modes |
| **Reasoning & task** | **Delegation accuracy** | Whether the assistant delegates when required, avoids delegation when forbidden, or makes either choice when optional. | All modes |
| **Reasoning & task** | **Delegations** | Actual versus expected frontend-to-backend handoffs. Multiple backend responses or tool calls within one delegation count as one. | All modes |
| **Reasoning & task** | **Conversation turns** | Actual versus expected substantive turns; excludes backchannels. | All modes; most useful for RUN |
| **Audio & interaction** | **Response rate** | Fraction of completed, acoustically eligible requests answered by the configured first-audio deadline. A qualifying spoken preamble counts; late responses, censored requests, and excluded requests are tracked separately. | All modes |
| **Audio & interaction** | **Response latency** | Mean time from the end of audible caller speech to the first qualifying assistant audio within the response deadline, including a spoken preamble; this is not time to task completion. | All modes |
| **Audio & interaction** | **Interruption rate** | Observed assistant interruptions per response-eligible caller turn. Helps identify unwanted overlap. | When eligible caller turns occur |
| **Audio & interaction** | **Speaking duration** | Total audible assistant speech and the largest speech total within one assistant turn. Helps assess verbosity and response length. | All modes |
| **Audio & interaction** | **Silence during delegation** | Total silence and the longest uninterrupted silent period while a delegation is active. Excludes speech from either participant. | All modes; zero when no delegation is active |
| **Consumption** | **Frontend usage** | Cumulative Live duration from `usage.seconds`; retain the final snapshot rather than summing updates. The API does not report frontend token counts. | All modes |
| **Consumption** | **Backend usage** | Delegated reasoning usage, including available input, output, reasoning, and caching details. | When delegation occurs |

語音模型是非確定性的，所以代表性的情境應該跑很多次。跨多次執行時，要回報每次執行的 latency 和時長指標的 P50 與 P90，並附上 task completion 比率和樣本數。每次執行的 response latency 是對及時回應的請求取平均，所以這些「執行層級平均值」的百分位數，跟「單一回應」的百分位數不一樣。

### 檢視結果

RUN harness 附有 viewer，可以檢視單一情境、探索事件時間軸、閱讀對話內容，並查看相關指標。加上 `--visualize` 旗標就能開啟。

下面可以瀏覽一段錄好的執行：播放對話、在時間軸上選一個點，檢視逐字稿、tool 活動和指標。這個 `restaurant_booking_complete` 範例錄於 2026 年 9 月 9 日 (UTC)，在「模擬輸出」一節也會用到。這次執行使用 client 管理的 delegation，John 用的是 Cedar 聲音。它示範如何檢視證據，單次執行不是效能 benchmark。

<iframe src="duplex_voice_agent_evaluation/recorded-example/view-results.html" title="Interactive voice-agent evaluation results" width="100%" height="1000" style="border: 1px solid #dfe4df; border-radius: 8px;" loading="lazy" sandbox="allow-scripts"></iframe>

如果你的文件檢視器沒辦法顯示內嵌的 HTML，可以[開啟互動式結果 viewer](https://github.com/openai/openai-cookbook/blob/main/examples/audio/duplex_voice_agent_evaluation/recorded-example/view-results.html)。

## Crawl：合成一個受控的請求

CRAWL 把書面的情境轉成來電者的語音，再把一個口說請求串流給 GPT-Live。它評估助理是否理解請求、回應是否恰當、是否正確使用已授權的 tools，以及是否到達預期的應用狀態。

因為請求文字、產生的音訊、應用 context 和預期結果在各次執行間可以保持一致，CRAWL 提供了一個受控的基準線，適合除錯和回歸測試。

### 運作方式

對每個情境，CRAWL harness 會：

1. 載入書面的來電者請求，以及只給評估者看的預期結果。

2. 用 text-to-speech 產生可重複使用的來電者音訊。

3. 以固定節奏的 PCM 區塊把音訊串流給 GPT-Live。

4. 讓助理直接回答、請求釐清、拒絕，或委派給有授權 tools 的推理後端。

5. 擷取助理的回應、tool 活動和最終應用狀態；評估結果；並儲存佐證檔案。

![Crawl evaluation workflow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/voice-agent-evaluation/figure-05.png)

### 評估重點與代表性的失敗模式

你可以用 CRAWL 評估這些面向：

- 意圖保留，包括單一請求內的更正。

- 助理是否適當地直接回答、請求釐清、拒絕或委派。

- Tool 的選擇、參數、執行和預期的呼叫次數。

- 授權和最終的應用狀態。

- 口語確認是否建立在已完成的動作上。

- Response latency，以及在來電者說話期間助理是否過早打斷。

下面的例子是餐廳訂位情境中有代表性的失敗案例。更多範例在 `crawl_harness/data/scenarios.json`。

| **Failure mode** | **Exemplary Scenario** | **Expected assistant behavior** | **Evaluation evidence** |
| --- | --- | --- | --- |
| Books the wrong date after a correction. | “Book a table for Maya on August 7—sorry, August 6—at 7 p.m. for two.” | Book August 6, not August 7, and confirm the corrected reservation. | Tool name and arguments, reservation state, and final spoken response. |
| Books a reservation when the caller only asks about availability. | “Do you have a table for two on August 7 at 7 p.m.?” | Check availability and report the result without creating a reservation. | Completed tool calls, absence of booking, and assistant response. |
| Guesses missing information. | “Book a table for two on August 7 at 7 p.m.” | Ask for the missing reservation name without creating a booking. | Clarification response, absence of reservation tool calls, and unchanged state. |
| Ignores authorized conversation history. | “Please make it 7 p.m.” | Recover the name, party size, and date from prior conversation context before booking. | Hydrated conversation history, reservation arguments, final state, and confirmation. |
| Delegates a question answerable from authorized context. | “What time does the restaurant close?” | Answer using the provided restaurant information without unnecessary delegation or tools. | Assistant response and absence of delegated tool calls. |

每個情境都定義了書面請求、已授權的應用 context、預期的助理行為、允許的 tools，以及用來判斷成功的應用狀態。情境從腳本化的使用者請求開始。harness 會在來電者輸入結束、委派的工作完成、有語音支撐的逐字稿群組穩定下來、安靜尾段結束之後，推斷這一輪已完成；API 本身不會發出權威的回合結束或音訊結束事件。委派之後，collector 還要求回傳的內容可用之後，要有一個新的口說回合開始。所以一個有效的回答如果跟較早的字幕群組共用，可能會逾時。

### 使用先前的對話歷史

單回合評估不一定要從空白對話開始。要測試既有對話中的關鍵時刻，可以把先前的使用者和助理回合當成文字 message，放進啟動時的 `session.input`，然後只把當前請求串流成音訊。

在 `scenarios.json` 裡，用 `input.context.summary` 在助理 instructions 中放簡短的背景摘要，用 `input.context.history` 在 `session.input` 中放先前的使用者與助理 message，或兩者都用。只有當前的 `input.text` 請求會被轉成音訊。

```json
{
  "input": {
    "text": "Please make it 7 p.m.",
    "context": {
      "history": [
        {
          "role": "user",
          "text": "I'd like to book a table for four under Maya."
        },
        {
          "role": "assistant",
          "text": "Which date would you like?"
        },
        {
          "role": "user",
          "text": "August 7, please."
        },
        {
          "role": "assistant",
          "text": "What time works best?"
        }
      ]
    }
  }
}
```

這樣可以還原先前的文字 context，不用重播歷史音訊，也不用模擬整段對話；但它不會還原待處理的工作或隱藏的 session 狀態。

## Walk：用真實錄音和可選的雜訊增加音訊真實度

WALK 評估的單回合任務跟 CRAWL 一樣，但使用核准過的來電者錄音，而不是在評估時才產生語音。強烈建議使用核准的真人錄音：它們最能代表真實的聲音、口音、發音、麥克風和環境如何影響助理的行為。如果拿不到合適的真人錄音，可以退而求其次用合成錄音和聲學效果。

除了參考逐字稿之外，每個情境還需要一個對應錄音的音檔，以及只給評估者看的預期結果。harness 會把儲存的錄音串流給 GPT-Live，並評估助理的回應、tool 活動和最終應用狀態。

WALK 讓任務跟預期結果保持不變，只改變錄音，藉此判斷來電者的聲音、發音、停頓、背景雜訊或通道條件，會不會影響助理的行為。

### 運作方式

對每個情境，WALK harness 會：

1. 載入附上的來電者錄音、參考逐字稿和只給評估者看的預期結果。

2. 解碼 WAV 錄音，並以固定節奏把原始音訊 frame 串流給 GPT-Live。

3. 讓助理直接回答、請求釐清、拒絕，或委派給已授權的 tools。

4. 擷取助理的回應、tool 活動和最終應用狀態。把有順序的助理音訊區塊放到本地的接收/播放時間軸上，因為輸出音訊事件沒有帶時間戳。

5. 對照參考資料評估觀察到的結果，並儲存佐證檔案。

參考逐字稿、預期答案、tool 預期和評分標準，都不會讓助理看到。

![Walk evaluation workflow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/voice-agent-evaluation/figure-06.png)

### 評估重點與代表性的失敗模式

WALK 最適合評估：

- 跨不同聲音、口音、發音和說話風格的意圖保留。

- 對背景雜訊、麥克風品質、房間音響和錄音條件的穩健性。

- 單一錄音請求中的停頓、猶豫和更正的處理。

- 助理是否適當地直接回答、請求釐清、拒絕或委派。

- Tool 的選擇、參數、授權和最終應用狀態。

- Response latency，以及在來電者說話期間助理是否過早打斷。

下面的例子說明餐廳訂位情境中有代表性的測試案例。`walk_harness/data/scenarios.json` 裡有一小組預先產生的合成範例。
| **Failure mode** | **Example condition** | **Expected result** | **What proves it** |
| --- | --- | --- | --- |
| Background noise obscures a corrected date. | The caller says, “August 7—sorry, August 6,” with added noise. | Reserve the table for August 6. | Tool arguments, final application state, and spoken confirmation. |
| Background sound is mistaken for a caller request. | The caller’s request includes synthetic background audio or an approved background recording. | Act only on the primary caller’s request. | Conversation audio, tool activity, and absence of unrelated actions. |
| Telephone-band filtering distorts a name or time. | A telephone-filtered request includes “Maya” and “7 p.m.” | Preserve the caller’s name and requested time. | Tool arguments, application state, and final confirmation. |
| Packet loss removes an important request detail. | Portions of a booking request are replaced by brief periods of silence. | Complete the correct booking or ask for clarification; do not guess. | Recording, assistant response, tool arguments, and application state. |
| Echo causes the assistant to repeat or duplicate an action. | A booking request includes delayed caller echo. | Create exactly one reservation with the correct details. | Tool-call count, reservation state, and spoken confirmation. |

跟 CRAWL 一樣，WALK 也無法確立多回合的釐清、讓出發話權 (yielding)、附和聲處理或對話恢復。這些行為要用 RUN 來測。

### 沒有真人錄音時

預設應該用核准的真人錄音。如果收集不實際，WALK 內含一個獨立的產生器，可以從書面情境產生可重複使用的合成錄音，或對既有的乾淨錄音套用受控的聲學效果。可用的確定性預設有 `clean`、`noisy`、`telephony`、`background_speech`、`echo`、`packet_loss` 和 `realistic`。

## Run：模擬一整段對話

RUN 評估語音助理在整段連續的全雙工對話中的表現，不強制輪流發言。它讓一個 GPT-Live session 持續運作，同時由一個獨立的模擬來電者即時提問、補充缺漏的資訊、改變需求，並回應助理。

跟 CRAWL 和 WALK 不同，RUN 可以評估只有跨多次交談才會出現的行為，包括對話記憶、釐清、打斷、附和聲和恢復。模擬來電者自己決定何時等待、回應、附和或打斷；harness 不會透過另外的發話權控制器來安排回合。

### 運作方式

RUN 的靈感來自 [τ-Voice](https://arxiv.org/abs/2603.13686) 的模擬使用者做法，但用了不同的對話模型。RUN 不透過另外的發話權控制器安排來電者的回合，而是把一個以 GPT-Live 為基礎的模擬來電者和助理，連在同一個連續的全雙工音訊 session 裡。雙方都可以同時聽和說，所以停頓、附和、重疊的說話和打斷都能自然出現。來電者追求一個私下的目標，harness 則記錄互動，並評估助理有沒有達到正確的結果。

對每個情境，harness 會：

1. 載入來電者的開場請求、私下目標、人設和議程，以及已授權的應用 context 和只給評估者看的預期結果。

2. 啟動獨立的模擬來電者，並在來電者與助理之間持續串流音訊。你可以選擇由助理或來電者先開口。

3. 讓助理直接回答、請求釐清、拒絕，或委派給有授權 tools 的推理後端，同時來電者自然地回應。

4. 偵測對話何時已解決（包括被接受的終止性拒絕），並讓剩下的助理發話和委派工作跑完。

5. 擷取對話、tool 活動和最終應用狀態；評估觀察到的結果；並儲存佐證檔案。

![Run simulation architecture](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/voice-agent-evaluation/figure-07.png)

即時音訊以均勻節奏的 20 毫秒 frame 串流。預設 200 毫秒的 `tick_ms` 間隔控制的是回報，不是即時音訊傳送或輪流發言。雙方全程都保持活躍，保留了停頓、重疊的說話、打斷和生成延遲。

對於沒有時間戳的即時音訊，relay 在啟動時會建立 400 毫秒的播放儲備，並在靜音時補充，每次等待上限 400 毫秒。回報的 response latency 使用緩衝後的播放時間軸，不是純模型的量測。

模擬來電者有自己的 GPT-Live 前端，以及一個輕量、受管理的 Responses 推理後端（`gpt-5.6-luna`，低 effort），沒有應用 tools。兩者都會收到私下的來電者目標、人設、已知事實和議程。來電者可以直接回答，也可以委派以取得指引；它同時決定**何時說話**和**說什麼**。只有被評估的助理擁有應用 tools 和狀態，預期結果則只給評估者看。打斷和附和聲會自然出現，並在執行結束後從錄下的互動推斷出來。

### 評估重點與代表性的失敗模式

RUN 可以評估：

- 多回合的任務完成與對話記憶。

- 釐清、追問，以及收集缺漏的資訊。

- 跨多次交談的更正和需求變更。

- 打斷、讓出發話權、附和聲和輪流發言。

- Tool 執行、授權和最終應用狀態。

- 口語確認是否建立在已完成的動作上。

- Response latency、重疊的說話、以秒計的前端時長，以及依模型分組的後端用量。

下面是餐廳訂位情境中失敗模式與對應 eval 的精選範例。更多範例在 `run_harness/data/scenarios.json`。

| **Failure mode** | **Exemplary scenario** | **Expected assistant behavior** | **Evaluation evidence** |
| --- | --- | --- | --- |
| Fails to collect missing information. | Caller asks to book a table without initially providing all required details. | Ask for the guest name, party size, and time before creating the reservation. | Conversation transcript, caller agenda, tool arguments, and final reservation state. |
| Ignores a correction introduced later in the conversation. | Caller initially requests August 7 but subsequently changes the date to August 8. | Apply the corrected date and book only the updated reservation. | Caller correction, tool arguments, final application state, and spoken confirmation. |
| Loses context while recovering from an unavailable option. | Caller requests an unavailable time and proposes an alternative. | Check the alternative, preserve relevant booking details, and book only after authorization. | Availability results, caller authorization, tool execution, and final state. |
| Keeps speaking through a meaningful caller interruption. | Caller interrupts an unavailable-slot explanation to request another date. | Yield promptly, process the alternative request, preserve the patio preference, and complete the authorized booking. | Caller and assistant audio overlap, yield latency, tool arguments, and application state. |
| Relents after repeated unauthorized requests. | Caller repeatedly asks to cancel another customer’s reservation. | Maintain the refusal and leave the reservation unchanged. | Conversation history, assistant responses, absence of cancellation, and final state. |

harness 把模擬使用者的語音、助理的語音、逐字稿、delegation 和 tool 活動，記錄在同一條持續前進的時間軸上。完成觀察器負責偵測對話何時解決，它不控制誰說話。

### 模擬輸出

每次 RUN 模擬都會產生整段對話的錄音、帶時間戳的逐字稿、結構化的事件 log 和結果報告。這些檔案合起來能看出說了什麼、什麼時候發生、哪些 tools 執行了，以及助理有沒有達成預期結果。

#### 音訊錄音

下面的 `restaurant_booking_complete` 錄音，就是互動式 viewer 裡那次 2026 年 9 月 9 日 (UTC) 的即時執行。內容是 John 先收集時間、人數和訂位姓名，再建立訂位。

<audio controls preload="metadata" src="duplex_voice_agent_evaluation/recorded-example/conversation.wav">Your viewer does not support embedded audio.</audio>

[下載對話錄音](https://github.com/openai/openai-cookbook/blob/main/examples/audio/duplex_voice_agent_evaluation/recorded-example/conversation.wav)。

錄音是 **42.34 秒、24 kHz 立體聲音訊**：模擬來電者在左聲道，助理在右聲道。兩個聲道共用同一條時間軸，所以停頓和重疊可以直接檢視。

報告顯示 response rate 為 75%，但這包含一個評分上的假象：scorer 把來電者最後的道別算成兩次回應機會，而助理只回答了一次。要區分是漏回應還是計算錯誤，要把錄音跟分數一起看。

#### 逐字稿與事件時間軸

下面的說話與 delegation 節錄，來自同一次執行的帶時間戳逐字稿。時間是從錄音開始算起的毫秒數。[完整逐字稿與事件節錄](https://github.com/openai/openai-cookbook/blob/main/examples/audio/duplex_voice_agent_evaluation/recorded-example/transcript.txt)還包含原始的 tool 與後端事件。互動式 viewer 用的就是這些說話時間戳，所以開場問候會出現在來電者的第一次回應之前。

```text
ASSISTANT 1180..3320ms: Hi, I'm John from Acme. How can I help you today?
USER 4840..8100ms: Hi John! I was hoping to book a table on August 7th, if that's possible.
DELEGATION 8400ms: target=client
ASSISTANT 9800..10840ms: Sure, let me check that for you.
ASSISTANT 11640..14780ms: Sure. What time would you like, for how many guests, and under what name?
USER 16280..19120ms: 7 p.m., please, for two under Maya.
DELEGATION 19600ms: target=client
ASSISTANT 20920..21580ms: Checking that now.
ASSISTANT 24240..28360ms: All set, Maya. You're confirmed for August 7th at 7 p.m. for two.
ASSISTANT 28980..31580ms: Your confirmation number is R-001.
USER 33300..36400ms: Wonderful. Thanks so much. Have a great day!
ASSISTANT 37440..38400ms: You're welcome! You too.
```

#### 結果報告

grader 判定這次執行通過，因為必要的結果與應用狀態檢查都過了。Tool accuracy 是 50%：助理做了兩次預期 tool 呼叫中的一次。Delegation accuracy 是 100%，delegation 有 2 次，預期是 1 次；這個分數檢查的是有沒有遵守必須或禁止委派的規則，不是跟預期次數是否一致。在這次執行裡，這些診斷分數不會覆蓋 task completion。如果某個流程對你的應用是必要的，就把對應的 `expected.procedure.steps[]` 項目標成 `critical: true`，讓它成為 RUN task completion 的門檻。

這張表保留了錄下的結果。其中的計分回合數來自指標報告，不應該靠數逐字稿的列數來推斷。前端音訊用量是模型回報的消耗量，跟錄音長度或可聽見的說話時長是不同的東西。

| **Metric** | **Result** |
| --- | --- |
| Task completion | Passed |
| Semantic quality | 90% |
| Tool accuracy | 50% |
| Tool calls | 1 of 2 expected |
| Delegation accuracy | 100% |
| Delegations | 2 versus 1 expected |
| Scored conversation turns | 7 versus 7 expected |
| Response latency | 1.513333 seconds |
| Response rate | 75% (3 of 4 scored opportunities) |
| Assistant interruption rate | 0% |
| Floor-hold silence (cumulative / maximum) | 4.62 / 1.7 seconds |
| Frontend audio usage | 42 seconds |
| Backend model | gpt-5.6-terra |
| Backend input tokens | 2374 |
| Backend output tokens | 105 |
| Backend total tokens | 2479 |

可以[下載結果表](https://github.com/openai/openai-cookbook/blob/main/examples/audio/duplex_voice_agent_evaluation/recorded-example/results.csv)，或[查看已發布的報告節錄](https://github.com/openai/openai-cookbook/blob/main/examples/audio/duplex_voice_agent_evaluation/recorded-example/results.json)。

## 把評估變成你自己的

### 從優先情境開始
先從一小組刻意挑選的情境開始，涵蓋對你的產品最重要的行為。一次只改一個變數，例如 prompt、後端模型或音訊條件，這樣進步和退步比較好解讀。

下面這些情境類型是不錯的起點，挑跟你的產品最相關的。

- **直接回答：** 問一個提供的 context 已經有答案的問題。助理應該正確回答，不建立 delegation、不跑 tool，也不暗示有做過什麼工作。

- **必要動作：** 要求一個必須真的送到應用程式的操作。要求用對的 function、精確的參數、只執行一次、符合預期的最終狀態，以及準確的口語結果。

- **對話中途更正：** 在助理回應的同時，更改目的地、時間、識別碼或需求。驗證既有任務有跟上使用者最新的意圖。

- **缺漏資訊：** 省略一個必要的細節。助理應該問一個有用的釐清問題，而不是亂猜或太早行動。

- **禁止的動作：** 要求情境禁止的事。驗證它有拒絕，並證明被禁止的訂位、寫入、刪除或轉交從未發生。

- **真實的對話壓力：** 測試猶豫、打斷、背景人聲、口音或電話音質的音訊。

給每個情境一個 ID、必要行為、禁止行為、預期證據和穩定的 fixture。等最初的案例穩定跑得起來、失敗可以追到根本原因之後，再擴充測試集。

### 先診斷失敗，再改系統

當情境失敗時，把請求從來電者的音訊一路追到助理的最後回應。判斷問題出在音訊傳送、語音理解、tool 執行、應用狀態變更，還是結果的傳達。在把結果當成助理的失敗之前，先確認測試有正確執行，而且擷取了足夠的證據來判斷結果。

- 如果正確的錄音根本沒送到模型，就改 sender 或 codec。

- 如果逐字稿是對的但 tool 參數錯了，就檢查 delegation。

- 如果已提交的應用狀態跟預期結果矛盾，就讓這個情境失敗，並記錄不一致的欄位。

- 如果任務成功了但使用者從未聽到結果，就檢查結果的傳達。

把問題分類成助理失敗、基礎設施或證據問題，或 grader 問題。保留相關的證據、隔離出最小而忠實的重現案例，並把它加進你的回歸測試集。

### 隨著系統進步增加真實度

一旦情境穩定通過，就在真實的音訊條件下重播同一個任務 (WALK)；如果結果取決於後續追問、更正或打斷，再把它擴展成完整對話 (RUN)。複雜情境失敗時，把它簡化成較單純的案例來找出根本原因。你也可以選擇送一小批情境給人工審查者，或讓真實來電者測試，以評估對話品質、驗證自動化 grader，並找出腳本化評估漏掉的失敗模式。

### 把 production 的失敗變成更好的評估

評估不會在上線時結束。要檢視 production 的對話，找出新的失敗模式，把有代表性的例子加進你的評估集，並在改進 prompt、tools 和應用邏輯時重跑。同時追蹤任務結果和互動品質，避免一個面向的進步造成另一個面向的退步。久而久之，這會變成一個評估飛輪：觀察真實行為、擴充測試覆蓋、改進系統，然後重複。

## 參考資料

Ray, S., Dhandhania, K., Barres, V., & Narasimhan, K. (2026). *τ-Voice: Benchmarking full-duplex voice agents on real-world domains*. arXiv. [https://arxiv.org/abs/2603.13686](https://arxiv.org/abs/2603.13686)

OpenAI. (n.d.). *Realtime Eval Guide*. OpenAI Cookbook. [https://developers.openai.com/cookbook/examples/realtime_eval_guide](https://developers.openai.com/cookbook/examples/realtime_eval_guide)

## 重點整理

- 語音 agent 要分開驗證三個邊界：有沒有委派對的工作、後端有沒有做對、前端有沒有如實轉述結果。聽起來自然的確認不等於後端真的做對。
- 音訊品質和任務品質可以各自失敗，要分開量測。task completion 是主要指標，其他分數是診斷用。
- Crawl、walk、run 每一步只多加一個變因：合成語音、真實錄音與雜訊、模擬來電者的多回合對話。
- 全雙工對話沒有乾淨的輪流，harness 要用連續的時間軸對齊音訊和事件。
- 失敗要先分類（助理、基礎設施、grader），再把最小重現案例加進回歸測試集。

## 練習

1. 照 `restaurant_003` 的格式，替 `crawl_harness/data/scenarios.json` 寫一個新情境：使用者要取消訂位，但只講了名字沒講日期，預期助理要追問而不是亂取消。
2. 挑一個 WALK 的情境，用產生器的 `noisy` 和 `packet_loss` 預設各產生一份錄音，比較 tool 參數和最終狀態是否一致。
3. 在 RUN 的某個情境裡，把某個流程步驟標成 `critical: true`，再讓助理跳過那一步，確認 task completion 會變成失敗，並對照沒標 critical 時的結果。
