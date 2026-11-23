---
translated: true
source: examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide.md
---

# ChatGPT Enterprise Prompting 指南

> 原文：[examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide.md)

在 ChatGPT Enterprise 裡寫出更好的日常工作 prompt 的 Cookbook。

## 這篇在做什麼

這是一份給 ChatGPT Enterprise 使用者的 prompt 寫法指南，不需要進階技術背景。它從心態、界定範圍、結構化寫 prompt、meta-prompting 到提高準確度，一路用實際例子帶你把日常任務寫清楚。

## 學完你會

- 用 `# Context`、`# Instructions`、`# Additional Information` 三段結構寫出清楚的 prompt
- 把一個太大的任務縮成「一個 prompt 對一個產出」，換到更有深度的結果
- 用 meta-prompting 讓 ChatGPT 幫你改 prompt，並加上來源、自我檢查等準確度護欄

## 開跑前

需要有 ChatGPT Enterprise 帳號。想直接套用的話，可以裝文中提供的 Skill。


這份指南是給想從 ChatGPT 得到更穩定結果的 Enterprise 使用者，不需要進階技術背景。內容偏實務、以例子為主，容易套用在日常工作上，不管是摘要文件、起草 email、翻譯內容、分析簡單情境，還是發想敘事。

注意，並沒有一個完美的 prompt 範本。這份指南的目的是幫你把任務講得夠清楚，讓 ChatGPT 能產出可靠又有用的結果。

> <details>
> <summary><strong>馬上開始用</strong>：安裝附帶的 Skill，立刻套用這些最佳做法</summary>
> 
> 現在沒時間讀完整份指南？可以在 ChatGPT 安裝附帶的 Skill，馬上套用這些 prompt 最佳做法。
> 
> **在這裡下載 Skill：** [Prompting Best Practices Skill](https://cdn.openai.com/cookbook/chatgpt-prompt-guide/prompt-redrafter.zip)
> 
> Skill 是小型、可重複使用的附加功能，教 ChatGPT 怎麼做特定任務或照固定流程做事。這個 Skill 幫你更一致地套用這份指南的建議，每次不用多做設定就能得到比較好的結果。
> 
> **安裝步驟：**
> 1. 從上面的連結下載 Skill
> 2. 登入 ChatGPT
> 3. 點 ChatGPT 的個人頭像
> 4. 在跳出的選單選 Skills
> 5. 點 **New Skill**
> 6. 選 **Upload from your computer**
> 7. 上傳剛下載的檔案
> 8. 開新對話，在日常工作中使用
> 
> 等你有時間，再回來讀這份指南，看更深入的說明、例子和背後的道理。
> </details>

## **目錄**
1. [簡介](#1-introduction)
2. [心態](#2-mindset)
3. [界定問題範圍](#3-scope-the-problem)
4. [把 prompt 寫清楚](#4-write-the-prompt-clearly)
5. [用 ChatGPT 幫你寫 prompt（meta-prompting）](#5-use-chatgpt-to-help-you-prompt-meta-prompting)
6. [提高準確度](#6-improve-accuracy)
7. [結論](#7-conclusion)
8. [Prompting 101 範例](#prompting-101-examples)

## 1. 簡介
Prompt engineering 是設計和優化 prompt 的藝術與科學，目的是跟語言模型有效互動，得到準確、簡潔又切題的回應。

大型語言模型是根據從資料學到的模式，一個字一個字預測下一個字來產生回應。所以你怎麼問很重要：你的 prompt 就是模型判斷「好」長什麼樣子的起點。

接下來幾節有幾個主軸：
- Prompting 不是要騙模型，而是要把工作、背景和成功的標準講清楚。
- Prompting 是反覆調整的過程（這很正常）。不要期待第一個 prompt 就完美。試一下、失敗、從失敗學到東西，再寫出更好的 prompt。你應該預期 prompt 要隨時間一直調整。

## 2. 心態
**把 prompt 當成交給新實習生的 "handoff"**

想像你要把工作交給一位剛到職第一週的聰明實習生。他很積極也有能力，但不知道你的專案、你的偏好，或你的團隊覺得什麼算「好」。他沒辦法像資深同事那樣自己補上缺少的背景。

如果你要交付一項任務，尤其是交給新實習生，通常會交代：
* 你在做什麼（背景加上為什麼重要）
* 你要他做什麼（具體任務）
* 「好」長什麼樣（對象、語氣、格式，還有一定要包含的重點）

寫 prompt 也是同樣的心態。你不只是問一個問題，而是在定義一項任務，讓 ChatGPT 交出你真的能用的東西。

**追求清楚，不要追求聰明**

很多 prompt 失敗的原因很單純：沒告訴模型讀者是誰、要什麼格式、用什麼標準做決定。把這些講明白，品質通常會快速提升。

**自我檢查：** 如果你把 prompt 給不同職務或不同組織的人看，他們不用額外解釋就能懂你要什麼嗎？

## 3. 界定問題範圍

界定範圍就是在開始之前先定義成功的標準和界線。範圍抓得好，就不會寫出又長又散的 prompt，也能減少白費的來回修改。因為你已經清楚定義了「好」是什麼，結果也比較容易讓人信任。

### A. 動筆之前，先仔細想

* **模型需要什麼背景才能理解這個任務？**
* **我要的單一產出是什麼？**
例如：「300 字的主管摘要」、「一封回信草稿」、「一張重點事實表」。
* **哪些格式和設定很重要？**
長度、語氣、條列還是段落、法律或法規限制、要用哪些資料來源。
* **我會用什麼標準判斷「好」？**
清晰度、正確性、風格，或是回覆必須包含的項目清單。

**經驗法則：** 如果你沒辦法用一兩句話描述「好」，模型也沒辦法穩定做到。

### B. 把問題縮到 prompt 做得到的範圍
**記住：單一 prompt 能做的事有限。** 如果你一直擴充 prompt，加進更多任務、更多格式、更多邊界情況，就更可能得到淺薄、不一致或不完整的結果。範圍收緊通常勝過「什麼都做」的 prompt。

**為什麼？** ChatGPT 每次產出的量通常差不多。你要它涵蓋的東西越多，同樣的注意力就分散到每一項，每項的深度就變少。任務越多，答案越薄。

所以當 prompt 感覺模糊或塞太滿，就把它縮到清楚只有一個交付物。

例如，你叫 ChatGPT「幫每一任美國總統寫傳記」，它大概會回 45 個一句話的摘要。但如果你說「寫第 6 任美國總統傳記的一個段落，只聚焦在他上任第一年」，它就會對那一年的重點事件講得很深入。

**範圍越小，深度和掌控度越好。** 必要的話，把 prompt 拆成多個獨立的 prompt。

## 4. 把 prompt 寫清楚
**寫完整的 prompt 之前，先花 30 秒用簡單的結構把工作列出來。最簡單的方法是用標題。**

所有 LLM 都看得懂一種叫 "markdown" 的語言，其中最容易學會的是用 "#" 代表標題。所以在 ChatGPT 裡，模型知道以 "#" 開頭的那行是文件的段落或標題。這能讓你和 ChatGPT 很快看出 prompt 每個部分在做什麼。

我們建議用下面的 prompt 版面。下面也有幾個實際使用情境的例子。

```md
# Context
What you’re working on and any background information the model needs.

# Instructions
Exactly what you want ChatGPT to do.

# Additional info / Constraints
Anything it must follow: tone, length, rules, constraints, etc.
```

這是最精簡的建議結構，不是固定範本。你可以依任務需要新增、刪除或改標題名稱。

### Context
在 Context 這段，建議讓模型扮演某個角色（persona）。

**範例**

* “You are a program manager writing a weekly status update.”
* “You are a customer support lead drafting a calm, helpful reply.”
* “You are a finance analyst explaining assumptions clearly.”
* “You are a clear, concise writing assistant. Do not invent facts. If information is missing, do not make assumptions.”

### Instructions

在 Instructions 這段，清楚列出你要 ChatGPT 做的每一件事。

**範例**
* “Extract relevant information and present it in a clean, organized format.”
* “Read the document and produce a 3–5 bullet executive summary”
* “Provide a recommendation with 2–3 supporting reasons.”


### Additional Information

在 Additional Information 這段，以下是一些可以加進去提高輸出品質的項目：

* 目標（Goal）：「好」長什麼樣？ <br>
例如：「附行動項目的 3 句主管摘要」、「抽出表格資料列的 CSV」、「給主管用的政策草稿」。
* 對象與語氣（Audience / tone）：誰會讀？ <br>
資深主管、法務、開發者、客戶、內部團隊，每種都對應不同的用語和細節程度。
* 格式與長度（Format & length）：輸出該是什麼形狀？ <br>
條列、表格、JSON、100 到 200 字，或「一張投影片的內容量」。
* 涵蓋範圍（Coverage）：必須考慮什麼、可以忽略什麼？ <br>
哪些文件、時間範圍、部門或地區重要？
* 限制（Constraints）：不可妥協的事。 <br>
截止時間、資料隱私規則、禁止內容、「不要捏造事實」、「不要包含姓名」等。
* 驗收標準（Acceptance criteria）：你怎麼判斷它對不對。 <br>
例如：「包含 3 個行動項目」、「符合我們的範本」、「可以被解析的有效 CSV」。

## 5. 用 ChatGPT 幫你寫 prompt（meta-prompting）

Meta-prompting 是用 ChatGPT 來**寫或改進你的 prompt**。本質上是請模型幫你給它更好的指示。當你知道自己要什麼、但不確定怎麼清楚或一致地表達時，特別有用。

做法很簡單：把你零散的筆記貼給 ChatGPT（或用語音功能直接跟它講），請它幫你把 prompt 寫得更清楚，例如請它反問你問題、請它複述你想做的事、找出缺漏的地方等等。

你也可以用 **Skill** 來輔助。例如，你常常要 ChatGPT 用固定方式整理粗糙的 prompt，prompt 重寫的 Skill 就能把它變成可重複的流程。

**範例 prompt**

```
Help me build a prompt that I can feed to a GenAI language model. I'm going to paste my draft prompt below - you ask me questions, then write up a clean prompt summarizing what we covered. The final prompt should have 3 sections ("# Context", "# Instructions", and "# Additional Information").
```

**什麼時候*不要*用 meta-prompting**

下面這些情況，meta-prompting 不是對的工具：

* 任務已經很簡單，直接寫 prompt 就好
* 缺的是**原始資料**（你需要的是對的文件或資料，不是更漂亮的 prompt）
* 你想靠「prompt」硬解決需求不清楚的問題，界定範圍還是要先做

Skill 可以讓 meta-prompting 更一致，但取代不了好的範圍界定，也取代不了正確的原始資料。

## 6. 提高準確度

如果輸出必須符合事實，或風險很高，就加上簡單的護欄：

* **要求提供來源**（或在可能時要求直接引用你提供的資料）。
* **標示不確定的地方：**「不確定的地方請標上 (needs verification)。」
* **在 prompt 最後加品質檢查清單：**
    * “Make sure the output includes X, Y, Z; avoid A, B.”
* **要求自我檢查：**
    * “Before finishing, list any assumptions you made.”

這是及早抓到「很有自信的亂猜」最快的方法之一。

另外，要確保模型有它需要的所有背景。例如記得上傳相關檔案，或連接相關的 ChatGPT Apps。

要測試準確度，建議跑一個小型 eval。想 5 到 10 個你知道答案的問題，請 ChatGPT 寫出答案，再比對結果。你也可以請 ChatGPT 檢查一份輸出，用像這樣的 prompt：

```
Check the output for:
- Accuracy: Does it avoid making up facts?
- Completeness: Did it include the required points?
- Format: Does it match the requested structure?
- Tone: Is it appropriate for the audience?
- Assumptions: Are any guesses clearly labeled?
```

## 7. 結論
想從 ChatGPT Enterprise 得到更可靠的結果，最快的方法是把每個 prompt 當成一次清楚的 handoff：提供最少必要的背景、定義任務、描述「好」長什麼樣。這樣做的話，你花在對付不一致輸出的時間會變少，花在交出真正能用的成果的時間會變多。

記住：
* 先界定範圍：一個 prompt 對一個交付物。範圍越小，深度越好，意外也越少。
* 結構化你的 prompt：用 # Context、# Instructions、# Additional Information / Constraints 這類簡單標題，消除模糊空間。
* 有意識地反覆調整：第一次結果不對，就根據出錯的地方改 prompt（缺背景、格式不清楚、對象不清楚、要求塞太多）。
* 重要的時候加上準確度護欄：盡量要求提供來源或引用。
如果你一直照著這些原則做，輸出會更清楚、更可信，也更快變成有價值的成果。接下來我們用一些 prompt 範例把這些東西具體化，針對常見的日常任務，示範 OK → Good → Excellent 的 prompt 寫法。

## Prompting 101 範例

為了說明普通、好、優秀 prompt 的差別，先從一個簡單的例子開始。

#### Okay prompt（任務）  
```md
Tell me about perennial gardening.
```

#### Good prompt（加上 context / persona）
```md
I am a novice gardener living in Northern Virginia. Tell me about perennial gardening. I am interested in planting some perennials in a 10 ft x 10 ft flower bed in front of my house.
```

#### Excellent prompt（再加上輸出要求） 
```md
I am a novice gardener living in Northern Virginia. Tell me about perennial gardening. I am interested in planting some perennials in a 10 ft x 10 ft flower bed in front of my house. Provide a beginners guide to perennial gardening in my area with step by step instructions. Include a list of recommended plants for my area and a shopping list of supplies I need to buy. 
```

有了這個基礎，接下來看幾個實用情境。

### 1. 摘要文件

#### 1. Okay prompt
```md 
Summarize the attached document for **[audience]** in **10 bullets**, focusing on **what it is, key points, and what to do next**.
```

#### 2. Good prompt
```md
# Context
I've attached a document that I need summarized for **[audience]**.

# Task
Summarize the document so the audience can quickly understand:
- what it is and why it matters
- the key takeaways
- decisions needed and next steps

# Requirements
- 1-paragraph overview (what this doc is + purpose)
- Key points (7–12 bullets)
- Decisions required (if any)
- Action items / next steps (owner + timeline if stated)
- Risks / caveats (if any)
- Open questions (if the doc is unclear)

# Output format
Use headings and bullets. Keep it concise. Do not invent details — if missing, say “not specified.”
```
#### 3. Excellent prompt
```md

## System
You are an expert synthesizer. Convert the uploaded document into a crisp, decision-ready brief.
**Do not invent details.** If something is missing, label it as **Not specified** or add it to **Open Questions**.

## Audience
Summarize for: **[audience]**  
Their goal: **[e.g., decide / align / get informed / take action]**

## Task
Create a decision-ready summary of the document below.

## Output format (NON-NEGOTIABLE)
1) **Executive Summary (5 bullets max)**
   - What this document is
   - Why it matters
   - Most important takeaway
   - Decision(s) needed (if any)
   - Immediate next step

2) **Key Takeaways**
   - 8–12 bullets, written in plain language
   - Include numbers/dates only if stated in the document

3) **Decisions & Recommendations**
   - Decisions required (if any)
   - Recommendations stated in the document (if any)
   - If the document is informational only, say “No decisions requested.”

4) **Action Items**
   - List action items explicitly stated or clearly implied
   - Format: Action | Owner (if stated) | Due date (if stated) | Notes
   - If not stated, use “Not specified.”

5) **Risks / Constraints / Caveats**
   - Up to 5 bullets
   - Only include what the document supports

6) **Open Questions**
   - Up to 10 questions that must be answered to execute or decide

7) **Direct Quotes (optional, max 3)**
   - Include up to 3 short quotes (≤25 words each) that are the most “load-bearing”
   - If the doc is long, select quotes that best represent its intent

## Constraints
- Keep it skimmable; no long paragraphs
- Use the document’s terminology; don’t rebrand concepts
- Be explicit about uncertainty; mark anything missing as **Not specified**
- If there are multiple sections, preserve structure by grouping takeaways by section
```

### 2. 搜尋（Apps）

#### 1. Okay prompt
```md
Search our SharePoint for the latest HR handbook and summarize the current PTO policy.
```

#### 2. Good prompt
```md

## Context
I need the most current, authoritative internal guidance on our **PTO policy**, located in SharePoint (HR handbook).

## Task
Search our **SharePoint** for the latest **HR handbook** and summarize the **current PTO policy**.

## Requirements
- Prefer the newest and most authoritative HR-owned doc(s).
- If multiple versions exist, identify which one is current and why.
- Summarize in plain language:
  - Eligibility (who the policy applies to)
  - Accrual/balance rules OR “unlimited PTO” rules (whichever applies)
  - Request/approval process
- Include links/titles to the sources you used.

## Output format
1) Source(s) found (with SharePoint links)  
2) PTO policy summary (headed bullets)  
3) Any recent changes/updates (if found)  
4) Open questions / missing info (if unclear)
```

#### 3. Excellent prompt

```md

## System (role)
You are an expert internal knowledge navigator. Your job is to find the **most authoritative and up-to-date** internal answer, reconcile conflicts across documents, and cite exactly where each key point comes from.

## Goal
Find and summarize our company’s current **PTO policy** from internal knowledge sources (SharePoint).

## Search strategy (do this in order)
1) Find the canonical handbook/policy doc for PTO
2) Find recent updates and amendments to the PTO policy
3) Find clarifications and edge cases e.g. carryover, accrual, medical leave etc.

## Source ranking rules
Prioritize in this order:
1) HR/People Ops owned handbook or policy repository (source of truth)
2) Official HR announcements that link to the policy
3) HR FAQs / manager guides that clarify edge cases
De-prioritize personal notes, outdated slide decks, or duplicated wiki pages.

## Conflict handling
If two docs disagree:
- Prefer the most recent HR-owned doc OR the doc that explicitly says it is the source of truth
- Call out the discrepancy and recommend which doc should be treated as current
- If still unclear, list the exact question to ask HR/Payroll (and who to ask)

## Output format
1) **Best sources** (up to 5)
   - Title + SharePoint link + owner (if available) + last updated date (if available)
   - 1-line why it’s authoritative
2) **PTO policy summary** (copy/paste ready)
   - Eligibility / coverage
   - How PTO is earned/managed (accrual vs unlimited, balance visibility)
   - Request & approval process (lead time, manager approval, blackout rules if any)
   - Carryover / caps / payout rules (if applicable)
   - Related policies: sick time, holidays, LOA (only if referenced)
   - Edge cases: new hires, part-time, transfers, LOA, termination
3) **What changed recently** (last 6–18 months, if found)
4) **Gray areas** (max 5) + how internal docs address them (or “Not specified”)
5) **What to open next** (3 links) for deeper detail
   - e.g., sick leave policy, holiday calendar, leave of absence policy, payroll payout rules
6) **Open questions** (max 7) + suggested owners (HR/People Ops/Payroll)

## Constraints
- Use only what’s supported by internal sources; do not guess
- If you can’t find the policy, propose the best next queries and likely owners
- Keep it concise and skimmable
```

### 3. 扮演角色（Persona）

#### 1. Okay prompt

```md
Act as a procurement lead and critique this memo, focusing on risks, missing info, and what you’d negotiate.

Memo [paste or attach memo]
```

#### 2. Good prompt

```md
# Persona
You are a Procurement Lead reviewing the attached proposal for a new vendor/tool.

# Context
I’m sharing a draft memo. Your job is to pressure-test it before it goes to leadership.

# What to do
- Identify what’s unclear, risky, or missing for procurement approval
- Call out likely blockers (security, data handling, pricing, implementation, vendor lock-in)
- Suggest the top changes to make this memo procurement-ready

# Output format
1) 5 bullet critique (most important issues first)  
2) A “questions procurement will ask” list (8–12 questions)  

# Memo
[paste memo here or attach as file]
```

#### 3. Excellent prompt
```md
# Persona
You are a seasoned Procurement Lead at a 1,000–10,000 employee company. You protect the business from vendor risk, unclear scope, and hidden costs while enabling teams to move fast when the case is strong.

# Goal
Review the memo below as if it’s headed to an exec approval meeting. Pressure-test it for procurement readiness: cost clarity, implementation realism, legal/security risk, and negotiation posture.

# How to behave
- Be direct, specific, and skeptical—but fair.
- If the memo lacks needed info, propose the exact missing content and where it should go.

# What to focus on (non-negotiable)

## Commercials / pricing
- Pricing model (seats/usage/tier), expected year-1 cost, renewal risk
- Hidden costs (implementation, training, admin overhead, integrations)
- Term flexibility (pilot, ramp, opt-out, true-ups)

## Risk & compliance
- Data types involved, data retention/deletion, sub-processors
- Security requirements (SSO/SAML, RBAC, audit logs, encryption)
- Regulatory/contract risks (DPAs, SLAs, liability caps)

## Implementation & adoption
- Realistic timeline, owners, dependencies, change management
- Support model (who administers, who supports users)
- Success metrics and how they’ll be measured

## Vendor viability & lock-in
- Exit plan, portability of data, migration costs
- Roadmap dependency risk, vendor support quality

# Output format (NON-NEGOTIABLE)
1) **Procurement Verdict**: Approve / Approve with conditions / Block (1 line)  
2) **Top 7 issues** (bullets): each must include *why it matters* + *how to fix*  
3) **Negotiation asks** (table): Ask | Rationale | “Fallback if they refuse”  
4) **Due diligence checklist** (max 12 bullets): what we must confirm before signing  
5) **Missing information**: exact sections/lines you’d add to the memo (copy/paste-ready)  
6) **Questions for the business owner** (max 10): the highest-leverage clarifications

# Memo
[paste memo here or attach as file]
```

### 4. 研究（Deep Research）

#### 1. Okay prompt
```md
Research the best East Coast cities for a first showroom for a mid-sized California D2C furniture brand. Compare the top markets on market opportunity, channels/distribution, costs/complexity, and strategic considerations, and include an executive summary with sources.
```

#### 2. Good prompt
```md
# Context
I’m building a market entry strategy for a mid-sized California D2C furniture brand considering its **first East Coast showroom**. We haven’t chosen a city yet.

# Task
Identify and compare the **best 5–7 East Coast cities** for a first showroom. Prioritize an objective view of **opportunity vs. complexity**.

# What “good” looks like
- For each city, cover the key factors below with **sources for major numbers and claims**
- End with a **comparison table** and a **top-2 recommendation**

# What to cover (per city)
1) **Market opportunity**
- Furniture demand signals
- Competitive landscape

2) **Channel & distribution**
- Major channels (e-comm + retail) and how customers discover/buy
- Logistics considerations

3) **Cost & complexity**
- Real estate / operating cost considerations for a showroom

# Output format
- Executive summary (8–12 bullets)
- City-by-city sections
- Final comparison table + recommended top 2 cities (with rationale)
```

#### 3. Excellent prompt

```md
# Decision goal
We must pick **one** city to open the first East Coast showroom for our mid-sized D2C furniture brand. Produce a recommendation that is **auditably sourced** and **directly comparable across cities**.

# Context
- Brand: mid-sized D2C furniture, California-based
- Showroom role: drive **brand trust + conversion lift**, not just revenue in-store
- Constraints: we can realistically support **one** launch market with a small team

# Task
1) Build a shortlist of **6 cities** (East Coast)  
2) Score each city using the rubric below  
3) Recommend **top 1** (plus a backup) with explicit tradeoffs and assumptions

# Rubric (use this exact weighting)
Score each city **1–5** (5 = best). Provide a short justification + citation(s).
- **Market pull (35%)**: demand proxy strength, target customer density, growth signals
- **Showroom economics (25%)**: rent ranges, staffing costs, expected operating burden
- **Delivery feasibility (15%)**: last-mile constraints, service expectations, return complexity
- **Competitive intensity (25%)**: concentration of strong incumbents + differentiation room

# Evidence rules
- For any numeric claim, include **source + date**. Prefer data from the last **24 months**.
- If a metric is unavailable, use a **proxy** (and label it clearly as a proxy).
- Call out **key uncertainties** and how they could change the ranking.

# City sections
For each city:
- 3–5 bullets “why it wins / why it loses”
- Key metrics table (only the metrics you used for scoring)
- Notes on major assumptions / proxies

# Output format
1) Executive summary (10 bullets max)  
2) Scored ranking table (with weighted totals)  
3) City writeups
4) Final recommendation
5) Sources
```

## 重點整理

- 把 prompt 當成交給新實習生的 handoff：背景、任務、「好」的標準都要講。
- 一個 prompt 對一個交付物，範圍越小深度越好。
- 用 Context、Instructions、Additional Information 三段結構消除模糊。
- Meta-prompting 適合「知道要什麼但不會講」，缺原始資料或需求不清時沒用。
- 重要任務加上來源、不確定標記、自我檢查，並用 5 到 10 題已知答案的小 eval 驗證。

## 練習

1. 挑一個你這週真的要做的任務（例如摘要一份文件），先寫成 Okay prompt，再照三段結構改成 Excellent prompt，比較兩次輸出。
2. 把一個「寫每個部門的年度報告」這種過大的 prompt，拆成三個各只有一個交付物的 prompt，看每份的深度有什麼差別。
3. 用 meta-prompting 讓 ChatGPT 反問你問題來改寫你的 prompt，然後設計 5 題你知道答案的題目，跑一次小 eval，看改寫前後準確度有沒有變。
