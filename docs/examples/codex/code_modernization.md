---
translated: true
source: examples/codex/code_modernization.md
---

# 用 Codex 現代化你的 Codebase

> 原文：[examples/codex/code_modernization.md](https://github.com/openai/openai-cookbook/blob/main/examples/codex/code_modernization.md)

這份 cookbook 教你用 OpenAI Codex CLI 現代化舊的 codebase。

## 這篇在做什麼

用 Codex CLI 把一個 COBOL 投資組合系統，經過五個階段現代化。核心是一份叫 ExecPlan 的設計文件，agent 照著它一步步做：選 pilot、盤點、設計、實作、再複製到其他系統。每個階段都要 Codex 產出文件和測試，讓整個過程可讀、可稽核、可重複。

## 學完你會

- 設定 AGENTS.md 和 PLANS.md，讓 Codex 知道這個 repo 怎麼做規劃
- 用 prompt 讓 Codex 產出 pilot 的 ExecPlan、overview、design、validation 文件，以及 OpenAPI spec
- 寫 parity test，把新舊系統並排跑，證明輸出一致

## 開跑前

- 安裝 OpenAI Codex CLI
- 一個你想現代化的 legacy repo。範例用的是 COBOL 的[投資組合系統](https://github.com/sentientsergio/COBOL-Legacy-Benchmark-Suite/)，也可以換成別的 stack

## Introduction

Codex 被訓練成能讀懂、推理大型複雜的 codebase，跟工程師一起規劃工作，並產出高品質的修改。Code modernization 已經快速變成它最常見也最有價值的用途之一。在這個做法裡，工程師專注在架構和商業規則，Codex 負責繁重的工作：翻譯舊的寫法、提出安全的 refactor，並在系統演進時讓文件和測試保持同步。

這份 cookbook 示範怎麼用 **OpenAI 的 Codex CLI** 現代化 legacy repository，讓整個過程：

* 新進工程師看得懂
* 架構師和風險團隊可以稽核
* 能當成模式重複套用到其他系統

我們用一個 COBOL 的[投資組合系統](https://github.com/sentientsergio/COBOL-Legacy-Benchmark-Suite/)當作範例，並選一個 pilot flow 專心做。你可以換成任何 legacy stack（例如 Java monolith、PL/SQL），只要你有 legacy 程式、排程編排（jobs、scheduler、scripts）或共用資料來源。

---

## 高階概覽

我們分成 5 個階段，圍繞一份 executive plan（簡稱 ExecPlan）進行，它是一份 agent 可以照著執行、完成系統變更的設計文件。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/code-modernization-phases.png" alt="Code Modernization Phases" width="700"/>

針對選好的 pilot flow，我們會產出 4 種文件：

* **pilot_execplan.md**：統籌整個 pilot 的 ExecPlan，回答範圍是什麼、為什麼重要、要做哪些步驟，以及怎麼知道做完了。
* **pilot_overview.md**：涉及哪些 legacy 程式（範例是 COBOL）、編排 job（這裡是 JCL）和資料來源，資料怎麼在它們之間流動，以及這個業務流程實際在做什麼。
* **pilot_design.md**：系統的目標樣貌，包含負責這個流程的 service/module、新的資料模型，以及公開 API 或 batch 進入點。
* **pilot_validation.md**：定義怎麼證明行為一致，包含關鍵情境、共用的輸入資料集、怎麼新舊並排執行，以及「輸出一致」在實務上的意思。

這 4 個檔案能說清楚改了哪些程式、新系統該長什麼樣子，以及怎麼精確檢查行為沒有退步。

---

## Phase 0：設定 AGENTS 和 PLANS

**目標**：給 Codex 一份輕量的約定，說明這個 repo 怎麼做規劃，又不讓大家被流程壓垮。

我們參考 [Using PLANS.md for multi-hour problem solving](https://cookbook.openai.com/articles/codex_exec_plans) 這份 cookbook，建立 AGENTS.md 和 PLANS.md，放在 .agent 資料夾。

* AGENTS.md：如果你的 repo 還沒有 AGENTS.md，建議用 /init 指令產生。產生後，在 AGENTS.md 加一段，指示 agent 參考 PLANS.md。
* PLANS.md：以 cookbook 裡的範例當起點。

這些檔案說明什麼是 ExecPlan、什麼時候要建立或更新、放在哪裡，以及每份 plan 一定要有哪些段落。

### Codex CLI 能幫上忙的地方
如果你想讓 Codex 針對你的 repo 收緊 AGENTS 或 PLANS，可以執行：

```md
Please read the directory structure and refine .agent/AGENTS.md and .agent/PLANS.md so they are a clear, opinionated standard for how we plan COBOL modernization work here. Keep the ExecPlan skeleton but add one or two concrete examples.
```

---

## Phase 1：選 pilot，建立第一份 ExecPlan

**目標**：對齊一個真實但範圍有限的 pilot flow，並把 Phase 1 的計畫寫進同一份 ExecPlan 檔案。

**關鍵產出**：pilot_execplan.md

### 1.1 選 pilot flow
如果你還沒想好要 pilot 哪個流程，可以請 Codex 提案。在 repository 根目錄用這個 prompt：

```md
Look through this repository and propose one or two candidate pilot flows for modernization that are realistic but bounded.
For each candidate, list:
- COBOL programs and copybooks involved
- JCL members involved
- The business scenario in plain language
- End with a clear recommendation for which flow we should use as the first pilot
```

這裡我們選報表流程當 pilot。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pilot-candidate.png" alt="Pilot Candidate Flow" width="700"/>

### 1.2 請 Codex 建立 pilot ExecPlan

```md
Create pilot_execplan.md following .agent/PLANS.md. Scope it to the daily reporting flow. The plan should cover four outcomes for this one flow:
- Inventory and diagrams
- Modernization Technical Report content
- Target design and spec
- Test plan for parity
Use the ExecPlan skeleton and fill it in with concrete references to the actual COBOL and JCL files.
```

這份 plan 現在就是所有 pilot 工作的「大本營」。

---

## Phase 2：盤點與探索

**目標**：記錄 pilot flow 現在實際在做什麼：程式、job、資料流和業務規則。讓工程師不用讀完每一行 legacy 程式，也能討論該怎麼改。

**關鍵產出**：pilot_reporting_overview.md

**工程師可以專注的地方**：

* 確認哪些 job 真的在正式環境執行
* 補上 Codex 從程式碼推不出來的資訊（SLA、營運背景、負責人）
* 檢查圖表和描述有沒有問題

### 2.1 請 Codex 起草 overview
```md
Create or update pilot_reporting_overview.md with two top-level sections: “Inventory for the pilot” and “Modernization Technical Report for the pilot”.
Use pilot_execplan.md to identify the pilot flow.

In the inventory section, include:
1. The COBOL programs and copybooks involved, grouped as batch, online, and utilities if applicable
2. The JCL jobs and steps that call these programs
3. The data sets or tables they read and write
4. A simple text diagram that shows the sequence of jobs and data flows

In the modernization technical report section, describe:
1. The business scenario for this flow in plain language
2. Detailed behavior of each COBOL program in the flow
3. The data model for the key files and tables, including field names and meanings
4. Known technical risks such as date handling, rounding, special error codes, or tricky conditions
```

這份文件能幫工程師不用讀完所有程式，就了解 pilot 的樣貌和行為。

pilot_reporting_overview.md 裡的流程圖範例

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pilot-flow-diagram.png" alt="Pilot Flow Diagram" width="700"/>

### 2.2 更新 ExecPlan

overview 產生後，請 Codex 讓計畫保持同步

```md
Update pilot_execplan.md to reflect the new pilot_reporting_overview.md file.
- In Progress, mark the inventory and MTR sections as drafted.
- Add any notable findings to Surprises and discoveries and Decision log.
- Keep the ExecPlan readable for someone new to the repo.
```

Phase 2 結束時，你會有一份 pilot overview 文件，同時扮演系統盤點報告和現代化技術報告。

---

## Phase 3：設計、規格與驗證計畫

**目標**

* 決定 pilot flow 的現代版本該長什麼樣子
* 描述目標 service 和資料模型
* 定義怎麼用測試和並行執行證明結果一致

這個階段結束時，我們會決定要做什麼，以及怎麼證明它可行。

**關鍵產出**

* pilot_reporting_design.md
* pilot_reporting_validation.md
* modern/openapi/pilot.yaml
* modern/tests/pilot_parity_test.py

### 3.1 目標設計文件

```md
Based on pilot_reporting_overview.md, draft pilot_reporting_design.md with these sections:

# Target service design
- Which service or module will own this pilot flow in the modern architecture.
- Whether it will be implemented as a batch job, REST API, event listener, or a combination.
- How it fits into the broader domain model.

# Target data model
- Proposed database tables and columns that replace the current files or DB2 tables.
- Keys, relationships, and any derived fields.
- Notes about how legacy encodings such as packed decimals or EBCDIC fields will be represented.

# API design overview
- The main operations users or systems will call.
- A short description of each endpoint or event.
- A pointer to modern/openapi/pilot.yaml where the full schema will live.
```

### 3.2 API 規格

我們把 pilot flow 對外的行為寫進 OpenAPI 檔，讓現代系統有一份清楚、與語言無關的契約。這份 spec 會成為實作、產生測試和未來整合的依據，也讓 Codex 有具體的東西可以據以產生程式碼和測試。

```md
Using pilot_reporting_design.md, draft an OpenAPI file at modern/openapi/pilot.yaml that describes the external API for this pilot. Include:
- Paths and operations for the main endpoints or admin hooks
- Request and response schemas for each operation
- Field types and constraints, aligning with the target data model
```

輸出範例：

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pilot-yaml.png" alt="Pilot Yaml" width="700"/>

### 3.3 驗證與測試計畫

```md
Create or update pilot_reporting_validation.md with three sections:

# Test plan
- Key scenarios, including at least one happy path and a couple of edge cases.
- Inputs and outputs to capture for each scenario.

# Parity and comparison strategy
- How you will run the legacy COBOL flow and the modern implementation on the same input data.
- What outputs will be compared (files, tables, logs).
- How differences will be detected and triaged.

# Test scaffolding
- Notes about the test file modern/tests/pilot_parity_test.py, including how to run it.
- What needs to be filled in once the modern implementation exists.
```

接著請 Codex 產生測試的骨架：

```md
Using pilot_reporting_validation.md, create an initial test file at modern/tests/pilot_parity_test.py.

Include placeholder assertions and comments that reference the scenarios in the test plan, but do not assume the modern implementation is present yet.
```

### 3.4 更新 ExecPlan

```md
Update pilot_execplan.md so that Plan of work, Concrete steps, and Validation and acceptance explicitly reference:
1. pilot_reporting_overview.md
2. pilot_reporting_design.md
3. pilot_reporting_validation.md
4. modern/openapi/pilot.yaml
5. modern/tests/pilot_parity_test.py
```

Phase 3 結束時，你會有清楚的設計、機器可讀的 spec，以及說明怎麼證明結果一致的測試計畫和骨架。

---

## Phase 4：實作與比對

**目標：** 實作現代版的 pilot，跟 COBOL 版本並行執行，並證明預定情境下輸出一致。

**關鍵產出**

* modern/<stack>/pilot 底下的程式碼（例如 modern/java/pilot）
* modern/tests/pilot_parity_test.py 裡完成的測試
* pilot_reporting_validation.md 裡更新的段落，描述實際並行執行的步驟

### 4.1 產生現代程式碼的初稿

```md
Using pilot_reporting_design.md and the COBOL programs listed in pilot_reporting_overview.md, generate initial implementation code under modern/<stack>/pilot that:
- Defines domain models and database entities for the key records and tables.
- Implements the core business logic in service classes, preserving behavior from COBOL paragraphs.
- Adds comments that reference the original COBOL paragraphs and copybooks.
- Treat this as a first draft for engineers to review.
```

可以重複執行幾次，每次專注在不同模組。

### 4.2 接上 parity test

```md
Extend modern/tests/pilot_parity_test.py so that it:
- Invokes the legacy pilot flow using whatever wrapper or command we have for COBOL (for example a script that runs the JCL in a test harness).
- Invokes the new implementation through its API or batch entry point.
- Compares the outputs according to the “Parity and comparison strategy” in pilot_reporting_validation.md.
```

### 4.3 記錄並行執行的步驟

不另外寫 parallel_run_pilot.md，直接沿用 validation 文件：

```md
Update the Parity and comparison strategy section in pilot_reporting_validation.md so that it includes a clear, ordered list of commands to:
- Prepare or load the input data set
- Run the COBOL pilot flow on that data
- Run the modern pilot flow on the same data
- Compare outputs and interpret the results
- Include precise paths for outputs and a short description of what success looks like
```

### 4.4（需要時）用 Codex 反覆修正

測試失敗或行為不同時，用短迴圈處理：

```md
Here is a failing test from modern/tests/pilot_parity_test.py and the relevant COBOL and modern code. Explain why the outputs differ and propose the smallest change to the modern implementation that will align it with the COBOL behavior. Show the updated code and any test adjustments.
```

每完成一個有意義的段落，請 Codex 更新 ExecPlan：

```md
Update pilot_execplan.md so that Progress, Decision log, and Outcomes reflect the latest code, tests, and validation results for the pilot.
```

你會看到 ExecPlan 的「progress」和「outcomes」段落被更新成類似這樣：

```md
Progress  
- [x] Inventory and diagrams drafted (`pilot_reporting_overview.md` plus supporting notes in `system-architecture.md`).  
- [x] Modernization technical report drafted (`pilot_reporting_overview.md` MTR section).  
- [x] Target design spec drafted (`pilot_reporting_design.md` and `modern/openapi/pilot.yaml`).  
- [x] Parity test plan and scaffolding documented (`pilot_reporting_validation.md` and `modern/tests/pilot_parity_test.py`).

Outcomes  
- `pilot_reporting_overview.md`, `pilot_reporting_design.md`, and `pilot_reporting_validation.md` now provide an end-to-end narrative (inventory, design, validation).  
- `modern/openapi/pilot.yaml` describes the API surface, and `modern/python/pilot/{models,repositories,services}.py` hold the draft implementation.  
- `modern/tests/pilot_parity_test.py` exercises the parity flow using placeholders and helpers aligned with the validation strategy.  
- Remaining work is limited to updating the operations test appendix and wiring the services to the real runtime.
```

---

## Phase 5：把 pilot 變成可擴展的做法

**目標：** 提供可重複使用的範本給其他流程，並寫一份簡短的指南說明在這個 repo 怎麼用 Codex。

**關鍵產出**

* template_modernization_execplan.md
* how_to_use_codex_for_cobol_modernization.md

### 6.1 ExecPlan 範本

```md
Look at the pilot files we created:
1. pilot_reporting_overview.md
2. pilot_reporting_design.md
3. pilot_reporting_validation.md
4. pilot_execplan.md

Create template_modernization_execplan.md that a team can copy when modernizing another flow. It should:
1. Follow .agent/PLANS.md
2. Include placeholders for “Overview”, “Inventory”, “Modernization Technical Report”, “Target design”, and “Validation plan”
3. Assume a similar pattern: overview doc, design doc, validation doc, OpenAPI spec, and tests.
```

### 6.2 How-to 指南

```md
Using the same pilot files, write how_to_use_codex_for_cobol_modernization.md that:
1. Explains the phases at a high level (Pick a pilot, Inventory and discover, Design and spec, Implement and validate, Factory pattern).
2. For each phase, lists where coding agents helps and points to the relevant files and example prompts.
```

---

## 收尾

不管 pilot 是哪個，照這份 cookbook 的步驟做，最後的資料夾結構大致會像這樣：ExecPlan、三份 pilot 文件、一份 OpenAPI spec、一個 pilot 模組和一個 parity test。你也可以把 markdown 檔再分到 pilot 和 template 子資料夾，結構更清楚。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pilot-folder-structure.png" alt="Pilot Folder Structure" width="700"/>

你會發現 modern/python/pilot 裡還沒有可以執行的進入點，因為這些模組（models.py、repositories.py、services.py）只是初稿的積木。想在本機試的話有兩個選擇：

* 用互動式 shell 或小 script
* 自己寫 runner（例如 modern/python/pilot/main.py），把 repository 和 service 接起來

這份 cookbook 用 COBOL pilot flow 當範例，但同樣的模式也出現在很不一樣的 refactor 裡。例如有客戶用 Codex 遷移一個大型 monorepo，把數百張 Jira ticket 餵給它，讓 Codex 標出風險較高的工作、找出跨模組的相依，並起草程式碼修改，再由另一個 validator 審核和合併。

現代化 COBOL repository 只是其中一個常見的案例，同樣的做法適用於任何 legacy stack 或大規模遷移：把「現代化我們的 codebase」拆成一連串小而可測試的步驟（一份 ExecPlan、幾份文件，加上以 parity 為優先的實作）。Codex 負責處理理解舊寫法、產生候選的遷移方案和收緊 parity 這些繁瑣工作，你和團隊則專注在架構和取捨，讓每個要升級的系統都能更快、更安全、可重複地現代化。

## 重點整理

- 把「現代化」拆成五個階段，用 ExecPlan 當單一的計畫文件，讓 agent 有地方對齊進度。
- 先選一個範圍有限的 pilot，在小範圍驗證做法，再抽成範本複製到其他系統。
- 文件分工：overview 說現狀、design 說目標、validation 說怎麼證明，各自獨立好審查。
- 以 parity 為優先：先有 OpenAPI spec 和 parity test，再實作，新舊並行跑證明輸出一致。
- 人負責架構和取捨，Codex 負責讀舊程式、產生候選程式和文件，每個階段結束都要更新 ExecPlan。

## 練習

1. 對你自己的某個 repo 執行 `/init` 產生 AGENTS.md，再加一段指示 agent 參考 PLANS.md，看 Codex 之後的行為有什麼變化。
2. 用 Phase 1.1 的 prompt 請 Codex 為你的 repo 提出 pilot 候選，挑一個，並照 1.2 產生 pilot ExecPlan。
3. 照 Phase 3 為這個 pilot 產生 OpenAPI spec 和 parity test 骨架，故意讓一個測試失敗，用 4.4 的短迴圈請 Codex 修正，並更新 ExecPlan 的 progress。
