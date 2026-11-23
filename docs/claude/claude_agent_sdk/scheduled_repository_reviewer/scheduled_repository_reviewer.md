---
translated: true
source: claude_agent_sdk/scheduled_repository_reviewer/scheduled_repository_reviewer.ipynb
---
# 打造排程式的 repository reviewer

> 原文：[claude_agent_sdk/scheduled_repository_reviewer/scheduled_repository_reviewer.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/scheduled_repository_reviewer/scheduled_repository_reviewer.ipynb)

打造一個排程執行、唯讀的 review agent。它會 resume 前一次的 session，並回傳通過 schema 驗證的 verdict，把每次 review 跟上一次串起來。

## 這篇在做什麼

這篇用 Claude Agent SDK 做一個可以無人值守、定時掃描 repository 的 reviewer。每次執行都回傳程式讀得懂的 verdict 跟 findings，而且靠 resume session 記得上一輪看過什麼。
筆記本先手動跑兩輪（第一輪是完整 baseline，第二輪是 resume 後的追蹤），最後再把同一個 reviewer 掛上 cron。

## 學完你會

- 用 `permission_mode="dontAsk"` 搭配 `max_turns` 和 `max_budget_usd`，跑一個有邊界、唯讀的 review agent。
- 用 `ClaudeAgentOptions(resume=...)` 接續上次的 session，並靠 `output_format` schema 回覆裡的 `RESUME-LINK` 欄位驗證連續性。
- 用 `scheduled_review.py` 把 reviewer 掛上 cron，輸出可 grep 的 `VERDICT` 與完成行，失敗時用 `except ResultError` 以非 0 exit code 結束。

## 開跑前

- 需要 Anthropic API key，放在 `.env` 的 `ANTHROPIC_API_KEY`。
- 需要 Python 3.11 以上，claude-agent-sdk 0.2.140 以上。
- 完整跑一遍大約花一毛美金左右的 API 費用。

## 簡介

把重複的 review 苦工變成你能掌控的無人值守任務。就算 repository 已經被好好 review 過，兩次 review 之間仍然會有變動，這些變動可能帶進之前沒人標記過的問題。這篇的做法是把這份工作交給 agent。

照你排的時程，agent 會掃過 repository，回傳程式能讀的 verdict 跟 findings。跨次執行的連續性來自 resumed session，這是本篇的核心 Agent SDK 功能。resume 只是排程 reviewer 的其中一種設計選擇：resumed session 會把整個上一輪帶過來，不用另外建儲存層。每次執行一開始就已經載入上次的 findings 跟 reviewer 讀過的所有內容，不是從空白開始。*什麼時候該 resume、什麼時候重新開始* 那一節會把各種選擇對應到適合的工作。

repository 在第一次執行時會做一次完整的 baseline review。之後每次執行都 resume 前一次的 session，從 agent 已經回報過的 findings 接著做。你每個週期只讀一份簡短的追蹤報告，而每份追蹤報告都會複述上一次 review 的 findings 來證明連續性。這份筆記本手動跑前兩個週期，最後把同一個 reviewer 放上排程。

## 你會學到什麼

讀完這篇，你可以：

- 在 `permission_mode="dontAsk"` 下，設定 `max_turns` 和 `max_budget_usd`，讓有邊界、唯讀的 review agent 在排程器底下無人值守執行
- 用 `ClaudeAgentOptions(resume=...)` 接續執行，並檢查 `output_format` schema 回覆裡的 `RESUME-LINK` 欄位來證明連續性：已修好的 finding 移到 `resolved`，新埋進去的 bug 被抓到
- 用 `scheduled_review.py` 把 reviewer 放上 cron，輸出可 grep 的 `VERDICT` 與完成行，並用範圍很窄的 `except ResultError` 路徑以非 0 exit code 結束

## 什麼時候用這個做法

適合需要「記得上一輪」的週期性 review，例如依賴套件稽核或文件是否過期的掃描。排程器由你自己跑，Claude Code 提供讀取工具、權限規則和可 resume 的 session。

如果你不想自己維護排程器跟基礎設施，下面這些託管方案可能更適合：

- [Claude Code routines](https://code.claude.com/docs/en/routines) 適合想排程 review 自己 GitHub repository 的個人開發者。你設定一次 prompt、repository 和 connector，Claude 就在託管環境跑這個 routine。Routines 目前是 research preview，跑在 Claude 訂閱方案上。
- [Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 適合想透過 Claude API 設定託管的情境。它代管 agent loop 跟 workspace，[scheduled deployment](https://platform.claude.com/docs/en/managed-agents/scheduled-deployments) 會依你設的 cron 節奏啟動 session。Managed Agents 目前是 beta，而且被 review 的 repository 會進到託管的 session workspace。

如果你想自己跑排程器和 review 環境，就用這篇的做法。

## 前置條件

開始之前請確認你有：

**需要的知識：**

* Python 基礎：熟悉 async/await、函式和基本資料結構
* 對 agentic 模式有基本了解：建議先讀 [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
* 對 Agent SDK 的 `query()` 函式有基本認識：如果沒碰過 SDK，先看 [the one-liner research agent](../00_The_one_liner_research_agent.md)

**需要的工具：**

* Python 3.11 以上
* claude-agent-sdk 0.2.140 以上，這個版本加入了本篇失敗路徑會 catch 的 typed `ResultError`
* Anthropic API key（[在這裡申請](https://platform.claude.com/settings/keys)）

請在筆記本所在的目錄執行，這樣它寫出的檔案才會放在旁邊。

**費用提醒：** 這份筆記本的即時執行完整跑一遍，通常大約花一毛美金的 API 費用，附帶的 script 跑起來也差不多。每次執行都會在摘要行印出自己的花費。

## 設定

先安裝需要的套件：

```python
%%capture
%pip install -U "claude-agent-sdk>=0.2.140" python-dotenv
```

**注意：** 確認你的 `.env` 檔包含：

```bash
ANTHROPIC_API_KEY=your_key_here
```

載入環境變數：

```python
from dotenv import load_dotenv

_ = load_dotenv()
```

## 建立一個要被 review 的範例 repository

建立一個含有已知缺陷的 repository，這樣你才能檢查 reviewer 回報了什麼。下面的程式會在 `demo_repo/` 放一個小服務，讓筆記本裡的 review 拿來測。每個檔案的原始碼都是一個字串常數，程式把它寫到磁碟上。這些檔案不會被 import，所以 bug 不會被觸發，最後的 Clean up 一節會在你做完時移除 `demo_repo/`。這個服務的兩個應用程式檔各有一個真正的 bug：

* `app/config.py` 把整個環境變數複製進 config，然後把結果印出來。這兩行合在一起，會把 process 持有的所有環境變數（包含 secret）都寫進 log。
* `app/math_utils.py` 用 `len(values)` 當除數算平均。傳入空 list 就會丟出 `ZeroDivisionError`。

```python
from pathlib import Path

REPO_DIR = Path("demo_repo").resolve()

README_MD = """# sample-repo

A small service kept here so the scheduled reviewer has something to read.
"""

CONFIG_PY = """import os


def load_config(path):
    config = {"source": path}
    config["environment"] = dict(os.environ)
    print("loaded config:", config)
    return config
"""

MATH_UTILS_PY = """def divide(numerator, denominator):
    return numerator / denominator


def average(values):
    return divide(sum(values), len(values))
"""

SAMPLE_REPO_FILES = {
    "README.md": README_MD,
    "app/config.py": CONFIG_PY,
    "app/math_utils.py": MATH_UTILS_PY,
}

for relative_path, body in SAMPLE_REPO_FILES.items():
    target = REPO_DIR / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")

seeded = sorted(str(path.relative_to(REPO_DIR)) for path in REPO_DIR.rglob("*") if path.is_file())
print("sample repo:", seeded)
```

??? note "輸出"

    ```text
    sample repo: ['README.md', 'app/config.py', 'app/math_utils.py']
    ```

## 定義 review 的回傳格式

範例 repository 備好後，下一步是 review 回答的格式契約。排程 review 的使用者都是程式，所以 reviewer 要回傳一個依欄位讀取的 JSON 物件。`output_format` 接收 JSON schema，回覆會直接以符合 schema 的形狀出現在 `ResultMessage.structured_output`。每次 review 帶一個 review id、一個來自固定集合的 verdict，以及一組 findings，每個 finding 有自己的 id。

finding id 是連續性證明的關鍵。追蹤 review 會點名上一次執行的 id，表示 reviewer 確實把那些 findings 帶了過來。

```python
from enum import StrEnum


class Verdict(StrEnum):
    """The two verdicts a scheduled review may report."""

    OK = "ok"
    CONCERNS = "concerns"


VERDICT_VALUES = [verdict.value for verdict in Verdict]

FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "file": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["id", "file", "summary"],
}

FIRST_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "review_id": {"type": "string"},
        "verdict": {"type": "string", "enum": VERDICT_VALUES},
        "findings": {"type": "array", "items": FINDING_SCHEMA},
    },
    "required": ["review_id", "verdict", "findings"],
}
```

## 為追蹤 review 擴充 schema

這篇會跑兩次 review，第二次需要一種方式指回第一次。`previous_review_id` 和 `previous_finding_ids` 指向第一次 review，`resolved` 列出已經不成立的上次 finding id。把第一個 schema 合併進來，共用的那一半只留一份，兩個 schema 就不會各自漂移。

`previous_review_id` 和 `previous_finding_ids` 負責連續性斷言。reviewer 把先前的 review 帶過來時，這兩個欄位會回傳第一次的 review id 和 finding id。reviewer 如果從頭開始，欄位會反映這件事，你會從那次執行的 log 行發現。

```python
CONTINUITY_PROPERTIES = {
    "previous_review_id": {"type": "string"},
    "previous_finding_ids": {"type": "array", "items": {"type": "string"}},
    "resolved": {"type": "array", "items": {"type": "string"}},
}

FOLLOW_UP_REVIEW_SCHEMA = FIRST_REVIEW_SCHEMA | {
    "properties": FIRST_REVIEW_SCHEMA["properties"] | CONTINUITY_PROPERTIES,
    "required": [*FIRST_REVIEW_SCHEMA["required"], *CONTINUITY_PROPERTIES.keys()],
}

print("follow-up required fields:", FOLLOW_UP_REVIEW_SCHEMA["required"])
```

??? note "輸出"

    ```text
    follow-up required fields: ['review_id', 'verdict', 'findings', 'previous_review_id', 'previous_finding_ids', 'resolved']
    ```

## 設定有邊界、唯讀的 reviewer

兩個 schema 都定義好之後，接著是 agent 設定。下面這些選項適合無人值守的 agent：

* **`tools`**：決定 agent 有哪些內建工具。只留 `Read`、`Glob`、`Grep`，reviewer 就沒有任何寫入工具。
* **`allowed_tools`**：決定哪些工具呼叫不用權限提示就能執行。`Read` 的授權限定在 repository 路徑，在 `dontAsk` 下讀取範圍外的檔案會被當成 tool error 拒絕。`Glob` 和 `Grep` 是不帶範圍的授權，整個工具都被放行，限制它們的是 `deny_reads_outside_repo` hook。執行摘要裡出現的 `StructuredOutput` 來自 `output_format`，不是這份清單，它只負責傳回回覆。
* **`permission_mode="dontAsk"`**：永遠不提示，沒有事先批准的一律拒絕。`auto` 權限模式同樣不會有例行提示，但它會在執行時用 model classifier 批准或拒絕每個呼叫。這個 reviewer 用 `dontAsk`，讓工具範圍固定在 allow 規則內。
* **`model`**：把 review 固定在指定的 model。沒固定的話，SDK 會用環境的預設 model，而預設會隨時間改變。固定後，排程任務的成本和 review 行為會維持在你設定的狀態，直到你自己決定更改。
* **`strict_mcp_config=True`**：讓 session 只能用這份設定宣告的 MCP server，也就是沒有任何一個。沒開的話，機器或帳號上設定的 MCP server 會掛進 session，它們的工具定義會進入每個 request。
* **`max_turns` 和 `max_budget_usd`**：限制 agentic loop 的回合數和花費。超過任一個，執行會以終端錯誤結果 `error_max_turns` 或 `error_max_budget_usd` 結束，SDK 會把它以 `ResultError` 丟給你的程式。執行是在花費已經超過預算後才停，所以一個週期可能超出上限。
* **`hooks`**：把 `deny_reads_outside_repo` 註冊成 [`PreToolUse`](https://code.claude.com/docs/en/agent-sdk/hooks) callback。這個 callback 會看到每個 `Read`、`Grep`、`Glob` 呼叫，路徑解析後在 repository 外就拒絕；Glob pattern 如果以 `/` 或 `~` 開頭、含 `..` 片段、或含 `{` 大括號，也會拒絕。
* **`setting_sources=[]`**：讓這次執行不讀機器上的檔案系統設定。這樣排程 review 在你的筆電和跑 cron 的機器上行為一致。空 list 也會把被 review 的 repository 自己的 `.claude/settings.json` 和 `CLAUDE.md` 擋在 session 外。reviewer 的 `cwd` 就是那個 repository，你無法掌控的 repository 不該設定它自己的 reviewer。
* **`output_format` 和 `resume`**：`output_format` 要求回覆符合你傳入的 schema，`resume` 負責在執行之間帶連續性。冷啟動時傳 `None`，排程的追蹤執行則傳上一次的 session id。

### 這些選項實作的安全防護

上面這組選項實作了幾道讓 agent 無人值守執行的防護。唯讀的工具授權、MCP 與設定隔離，以及 turn 與預算上限，限制了一次執行能做的事。定期重置 session 則限制了 session context 能留多久。

讀取範圍有兩層。`allowed_tools` 的授權把 `Read` 限制在 repository 路徑（筆記本和 script 都一樣），而讀取仍然受執行任務的使用者自身檔案權限約束。請用只有 review 所需權限的使用者來跑部署步驟。

Claude Code 對 `Grep` 和 `Glob` 套用 `Read` 規則是盡力而為。`deny_reads_outside_repo` 讓讀取限制不必依賴那種涵蓋範圍。

附帶的 script 裝了同一個 hook，而且這個 hook 已經拒絕讀取 service 目錄。script 另外加了一條 `disallowed_tools` 規則當獨立的第二層，擋住 `Read` 工具讀取那個放 env 和 session 檔的目錄。這條規則只有在傳入 `service_dir` 參數時才會設定，筆記本的呼叫不設它。

同樣的防護也能對付 prompt injection，細節見 [Protect against prompt injection](https://code.claude.com/docs/en/security#protect-against-prompt-injection)。`tools` 限制在 `Read`、`Glob`、`Grep` 時，session 沒有 shell 也沒有網路工具，reviewer 讀到的內容除了回覆本身無處可去。這也是這份筆記本要檢查回覆的原因，也是 `review.log` 要跟被 review 的 repository 用同樣方式處理的原因。

```python
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    HookContext,
    HookMatcher,
    ProcessError,
    ResultError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

READ_ONLY_TOOLS = ["Read", "Glob", "Grep"]
MODEL = "claude-sonnet-5-5"
FIRST_RUN_BUDGET_USD = 0.25
FOLLOW_UP_BUDGET_USD = 0.20
FIRST_RUN_MAX_TURNS = 20
FOLLOW_UP_MAX_TURNS = 14
TEXT_LOG_CHARS = 400


def clip(text: Any) -> str:
    """Flatten text onto one bounded log line, marking the cut when one happens.

    Findings arrive as free text and land in a log other tools grep. Dropping
    unprintable characters and collapsing whitespace keeps each field on one
    log line of its own.
    """
    printable = "".join(char if char.isprintable() else " " for char in str(text))
    flat = " ".join(printable.split())
    return flat if len(flat) <= TEXT_LOG_CHARS else flat[:TEXT_LOG_CHARS] + "..."


REVIEWER_SYSTEM_PROMPT = (
    "You are a repository review agent running on a schedule with nobody "
    "watching. Inspect the files with your read-only tools, keep the review "
    "short, and answer with the JSON object the caller's schema describes."
)


def deny_reads_outside_repo(repo: Path):
    """Deny any Read, Grep, or Glob call whose path resolves outside repo.

    The hook confines Grep and Glob deterministically instead of relying
    on Read-rule coverage of those tools. Candidate paths resolve
    symlinks, so a Read through an in-repository link is denied when it
    lands outside. Absolute Glob patterns, patterns carrying a `..` segment, and
    patterns carrying brace syntax the segment check can't reason about are
    denied rather than trusted to stay inside their search root.
    """

    def denial(reason: str) -> dict[str, Any]:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    async def deny(
        input_data: dict[str, Any], tool_use_id: str | None, context: HookContext
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input") or {}
        raw = tool_input.get("file_path") or tool_input.get("path")
        if raw:
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = repo / candidate
            candidate = candidate.resolve()
            if not candidate.is_relative_to(repo):
                return denial(f"path outside the repository under review: {candidate}")
        if input_data.get("tool_name") == "Glob":
            pattern = tool_input.get("pattern")
            if isinstance(pattern, str) and (
                pattern.startswith(("/", "~")) or "{" in pattern or ".." in pattern.split("/")
            ):
                return denial(f"glob pattern may leave the repository under review: {pattern}")
        return {}

    return deny


def review_options(
    repo: Path,
    schema: dict[str, Any],
    max_turns: int,
    resume_session_id: str | None = None,
    service_dir: Path | None = None,
) -> ClaudeAgentOptions:
    """Build the options for one scheduled review pass."""
    options = ClaudeAgentOptions(
        # The agent works inside the reviewed repository.
        cwd=str(repo),
        system_prompt=REVIEWER_SYSTEM_PROMPT,
        tools=READ_ONLY_TOOLS,
        # The //-anchored form is deliberate: with a single leading slash
        # the rule anchors at the settings source, not the filesystem
        # root, matches nothing, and every read is denied under dontAsk.
        # repo is absolute, so the rendered rule keeps the double slash.
        allowed_tools=[f"Read(/{repo}/**)", "Glob", "Grep"],
        permission_mode="dontAsk",
        model=MODEL,
        # Keep machine- and account-configured MCP servers out of the
        # session.
        strict_mcp_config=True,
        max_turns=max_turns,
        max_budget_usd=FOLLOW_UP_BUDGET_USD if resume_session_id else FIRST_RUN_BUDGET_USD,
        hooks={
            "PreToolUse": [
                HookMatcher(matcher="Read|Grep|Glob", hooks=[deny_reads_outside_repo(repo)])
            ]
        },
        # Same behavior on a laptop and on the box that runs the cron job.
        setting_sources=[],
        output_format={"type": "json_schema", "schema": schema},
        # None on a cold run, and the persisted session id on a follow-up.
        resume=resume_session_id,
    )
    if service_dir is not None:
        # A second, independent layer beside the hook, which already
        # denies these reads: block the Read tool on the service
        # directory, where the env and session files live.
        options.disallowed_tools = [f"Read(/{service_dir}/**)"]
    return options
```

## 用 fallback 讀取回覆

回覆到達時已經通過 review schema 驗證。下面的兩個 reader `verdict_of` 和 `finding_ids`，在使用的當下對 `verdict` 和 `findings` 這兩個程式會據以行動的欄位再檢查一次。每個 reader 對應欄位需要的形狀，不符合就退回固定預設值。這個 cell 也定義了 `RunOutcome`（runner 要填的容器）和 `string_items`（連續性檢查用的 list reader）。
verdict 缺漏或無法辨識時，會被讀成 `concerns`，也就是會引起注意的狀態。findings list 如果是其他形狀，就回傳空的 id，不去猜一個不完整的結果。程式最後會拿格式錯誤的輸入測這兩個預設值，所以下面的輸出會看到 fallback 的結果。

```python
from dataclasses import asdict, dataclass, field


@dataclass
class RunOutcome:
    """What one scheduled run reported back."""

    session_id: str | None = None
    subtype: str = "no_result"
    num_turns: int = 0
    total_cost_usd: float | None = None
    denials: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    tools_attempted: list[str] = field(default_factory=list)


def sequence_of(value: Any) -> list[Any]:
    """Return a list-shaped field's items, or nothing when it isn't one."""
    match value:
        case [*items]:
            return items
        case _:
            return []


def verdict_of(payload: dict[str, Any]) -> Verdict:
    """Read the verdict from the structured reply, falling back to concerns
    when the field is missing or unrecognized."""
    match payload:
        case {"verdict": str(value)} if value in VERDICT_VALUES:
            return Verdict(value)
        case _:
            return Verdict.CONCERNS


def finding_ids(payload: dict[str, Any]) -> list[str]:
    """Collect finding ids from the structured reply."""
    ids: list[str] = []
    for finding in sequence_of(payload.get("findings")):
        match finding:
            case {"id": str(finding_id)}:
                ids.append(finding_id)
    return ids


def string_items(value: Any) -> list[str]:
    """Collect the plain strings from a list-shaped field."""
    return [item for item in sequence_of(value) if isinstance(item, str)]


print("fallbacks:", verdict_of({}), finding_ids({"findings": "not-a-list"}))
```

??? note "輸出"

    ```text
    fallbacks: concerns []
    ```

## 建立 review runner

schema、選項和 reader 在 runner 裡合在一起。runner 串流接收訊息、印出 reviewer 說的話、列出 reviewer 用過的工具，並保留最後那個 `ResultMessage` 的 `session_id` 和 `structured_output`。

每次執行最後的報告先印 verdict，再逐行印每個 finding，內容是透過回覆 reader 讀出來的。每個 block 的輸出有長度上限，被截斷的行會有明顯標記，這個上限避免一則很長的回覆灌爆排程的 log。structured-output 的執行通常只輸出很少的文字，在呼叫工具前可能先說一兩行。在錄製的執行裡，兩個週期都只串流了工具呼叫。不管哪種情況，log 裡的 findings 都來自回覆的 payload，不是串流文字。

這個 runner 以 [`scheduled_review.py`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/scheduled_repository_reviewer/scheduled_review.py) 的形式放在筆記本旁邊，這是你把 reviewer 放上排程時要部署的 companion script。

失敗的執行會以非 0 exit code 結束，而且不會印出完成行。兩種失敗類型都這樣收尾：

* **超過邊界**：`max_turns` 或 `max_budget_usd` 會讓執行以終端錯誤結果結束，CLI 也以非 0 退出。SDK 把這個結果以 `ResultError` 丟給你的程式，並帶著該結果的 subtype。
* **沒有終端結果就失敗**：CLI process 執行到一半被殺，或連線一直打不開，會丟出它自己的 exception 型別，逃過 typed catch，所以不會印出失敗行。

每次 review 執行都在 `run_review` 呼叫外面 catch `ResultError`，印一行 `REVIEW-CYCLE-INCOMPLETE`，然後 re-raise。筆記本遇到失敗就停，不會繼續跑到成功行。後面「驗證失敗路徑」那一節的刻意失敗執行，則 catch `ResultError` 但不 re-raise，因為觸發失敗就是那個 cell 的目的。

```python
async def run_review(
    *,
    repo: Path,
    label: str,
    prompt: str,
    schema: dict[str, Any],
    max_turns: int,
    resume_session_id: str | None = None,
    service_dir: Path | None = None,
) -> RunOutcome:
    """Run one review pass and return its structured result."""
    options = review_options(repo, schema, max_turns, resume_session_id, service_dir)
    outcome = RunOutcome()
    # The raw payload of a terminal error result, kept so the except branch
    # below can re-raise it typed.
    error_result: dict[str, Any] | None = None
    try:
        async for message in query(prompt=prompt, options=options):
            match message:
                case AssistantMessage(content=blocks):
                    for block in blocks:
                        match block:
                            case TextBlock(text=text):
                                line = text.strip()
                                if line:
                                    # Cap what a scheduled log absorbs per block.
                                    print(f"[{label}] {clip(line)}")
                            case ToolUseBlock(name=tool_name):
                                outcome.tools_attempted.append(tool_name)
                case ResultMessage() as result:
                    outcome.session_id = result.session_id
                    outcome.subtype = result.subtype
                    outcome.num_turns = result.num_turns
                    outcome.total_cost_usd = result.total_cost_usd
                    outcome.denials = len(result.permission_denials or [])
                    if isinstance(result.structured_output, dict):
                        outcome.payload = result.structured_output
                    error_result = asdict(result) if result.is_error else None
    except ProcessError as exc:
        # The SDK raises ResultError itself when the error result is the last
        # frame the CLI emits. CLI 2.1.301 (bundled with claude-agent-sdk
        # 0.2.168) sends a task_summary frame after it, and the SDK then falls
        # back to a bare ProcessError; re-raise it typed from the result this
        # loop already saw, so callers keep one narrow `except ResultError`.
        if isinstance(exc, ResultError) or error_result is None:
            raise
        reason = "; ".join(error_result.get("errors") or []) or error_result.get("result")
        message = f"Claude Code returned an error result: {reason or error_result.get('subtype')}"
        raise ResultError(message, data=error_result, exit_code=exc.exit_code) from exc
    return outcome


def report(label: str, outcome: RunOutcome) -> Verdict:
    """Print the scheduler-shaped lines for one run and return its verdict."""
    cost = f"{outcome.total_cost_usd:.4f}" if outcome.total_cost_usd is not None else "n/a"
    print(
        f"{label} session={outcome.session_id} subtype={outcome.subtype} "
        f"turns={outcome.num_turns} denials={outcome.denials} "
        f"cost_usd={cost} "
        f"tools_attempted={','.join(dict.fromkeys(outcome.tools_attempted)) or 'none'}"
    )
    verdict = verdict_of(outcome.payload)
    print(f"VERDICT: {verdict}")
    for finding in sequence_of(outcome.payload.get("findings")):
        match finding:
            case {"id": str(finding_id), "file": str(file_path), "summary": str(summary)}:
                print(f"  {clip(finding_id)} {clip(file_path)}: {clip(summary)}")
    return verdict
```

## 跑冷啟動 review

這兩次即時執行從這裡開始，當作排程的前兩個週期，只是把間隔壓縮掉。第一次 review 是冷啟動。沒設 `resume`，執行會讀完整個 repository，並用第一次 review 的 schema 回答。執行結束時會得到一個 verdict、一組 finding id，以及下一次要 resume 的 `session_id`。

**預期輸出：** 一行 `subtype=success` 的 `RUN-1` 摘要，接著是 `VERDICT: concerns`，底下的 finding 行涵蓋兩個埋進去的缺陷。一個缺陷可能被拆成多個 finding，不過錄製的執行是每個缺陷印一個。摘要行裡的 session id 就是第二次執行要 resume 的對象。

摘要行裡 `denials` 不為 0，代表讀取限制有在作用。hook 會拒絕以根目錄起頭的 `Read` 嘗試，例如 `/app/config.py`，reviewer 會改用 repository 內的路徑重試。使用大括號展開的 `Glob` pattern，例如 `**/*.{py,md}`，也會算進同一個數字。一次執行有沒有 denial，要看 reviewer 一開始試了哪些路徑和 pattern。

denial 會消耗 turn 預算做重試。如果你的 repository 的 review 常用大括號 pattern，請調整 hook 去展開它，對每個展開結果做同樣的檢查，而不是直接拒絕這個 pattern。

```python
import uuid

FIRST_REVIEW_ID = f"review-{uuid.uuid4().hex[:8]}"
FIRST_PROMPT = (
    f"Scheduled review {FIRST_REVIEW_ID} of the repository in the current "
    "directory. "
    "Read the source files and report correctness or security problems you can "
    "point at a specific file and function. Give each finding a summary of "
    "one or two sentences and an id of the form "
    'F1, F2, and so on. Use the verdict "concerns" when you report at least one '
    'finding and "ok" when the repository looks clean. Echo '
    f"{FIRST_REVIEW_ID} back as review_id."
)

try:
    first = await run_review(
        repo=REPO_DIR,
        label="run-1",
        prompt=FIRST_PROMPT,
        schema=FIRST_REVIEW_SCHEMA,
        max_turns=FIRST_RUN_MAX_TURNS,
    )
except ResultError as exc:
    cost = (exc.data or {}).get("total_cost_usd")
    cost_str = f"{cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
    print(
        f"REVIEW-CYCLE-INCOMPLETE stage=run-1 subtype={exc.subtype} "
        f"reason={exc.terminal_reason} cost_usd={cost_str}"
    )
    raise

if first.subtype != "success" or first.session_id is None or not first.payload:
    print(f"REVIEW-CYCLE-INCOMPLETE stage=run-1 subtype={first.subtype}")
    raise RuntimeError("run 1 did not complete; there is no session to resume")
first_verdict = report("RUN-1", first)
```

??? note "輸出"

    ```text
    RUN-1 session=f3f70d8c-2d10-46f4-9cd8-58528c10dd22 subtype=success turns=5 denials=0 cost_usd=0.0171 tools_attempted=Glob,Read,StructuredOutput
    VERDICT: concerns
      F1 app/config.py: load_config copies the whole os.environ into the config and then prints it, so secrets such as API keys and tokens end up in logs. Load only the specific variables needed and don't print them.
      F2 app/math_utils.py: average() raises ZeroDivisionError for an empty list because it divides by len(values) with no check. divide() has the same problem when the denominator is 0. Handle empty input explicitly.
    ```

## 在兩個週期之間改動 repository

實際部署時，週期之間進來的變動，不是修好了 reviewer 回報的 finding，就是引入了 reviewer 沒見過的問題。下面的程式各做一個這兩種改動，再跑追蹤 review。

程式修好 `app/math_utils.py` 的除以零防護，這個 finding 應該以 resolved 回來。它還新增一個檔案 `app/retry.py`，裡面的重試迴圈沒有上限，這是追蹤 review 應該抓成新問題的對象。這個新問題在第一次執行從沒讀過的檔案裡。抓得到，就證明追蹤 review 看的是 repository 現在的樣子，不是從已經知道的檔案憑記憶回答。

```python
MATH_UTILS_FIXED = """def divide(numerator, denominator):
    if denominator == 0:
        raise ValueError("denominator must be non-zero")
    return numerator / denominator


def average(values):
    if not values:
        return 0.0
    return divide(sum(values), len(values))
"""

RETRY_PY = """import time


def fetch_with_retry(fetch):
    while True:
        try:
            return fetch()
        except ConnectionError:
            time.sleep(1)
"""

(REPO_DIR / "app/math_utils.py").write_text(MATH_UTILS_FIXED, encoding="utf-8")
(REPO_DIR / "app/retry.py").write_text(RETRY_PY, encoding="utf-8")
changed = sorted(str(path.relative_to(REPO_DIR)) for path in REPO_DIR.rglob("*") if path.is_file())
print("repository now:", changed)
```

??? note "輸出"

    ```text
    repository now: ['README.md', 'app/config.py', 'app/math_utils.py', 'app/retry.py']
    ```

## 跑 resumed review

下一次排程執行把第一次的 `session_id` 當 `resume` 傳入，並要求追蹤用的 schema。prompt 的第一個指示是重新列出 repository 的檔案。少了這一步，resumed 的 agent 可能只憑第一次讀過的檔案回答，沒發現 `app/retry.py` 是新的。下面的程式拿回覆跟第一次比對，印出一行 `RESUME-LINK`，用三個欄位帶著連續性證明：

* `same_session`：兩次執行共用同一個 session，表示 resume 本身有成功
* `prior_review_id_echoed`：追蹤 review 有點名第一次 review 的 id
* `recalled_findings`：追蹤 review 帶回了第一次執行多少個 finding id

三個條件都成立時，reviewer 就是根據它已經做過的 review 在回答。其中任何一個不成立，程式就在獨立一行印出 `RESUME-LINK-BROKEN` 標記。回覆也會列出 `resolved`，也就是已經不成立的上次 finding id。

**預期輸出：**

* 一行 `RESUME-LINK`，`same_session=True`、`prior_review_id_echoed=True`，且 `recalled_findings` 數量是滿的
* 一個 `resolved` list，裡面是除以零防護的 finding id
* findings 保留 config 洩漏，並加上新的 retry bug
* 以 `REVIEW-CYCLE-COMPLETE` 行收尾這個週期

```python
SECOND_REVIEW_ID = f"review-{uuid.uuid4().hex[:8]}"
FOLLOW_UP_PROMPT = (
    f"Scheduled review {SECOND_REVIEW_ID} of the same repository, one cycle "
    "later. List the repository's files again, then read the source files as "
    "they stand now. Answer from the most recent review you did in this "
    "conversation: put its review id in previous_review_id and the ids of the "
    "findings it reported in previous_finding_ids. Report the findings that "
    "still apply, keeping the ids you gave them earlier, list in resolved the "
    "ids of previous findings that no longer apply, and report anything newly "
    "wrong as a new finding with a summary of one or two sentences. Echo "
    f"{SECOND_REVIEW_ID} back as review_id."
)

try:
    second = await run_review(
        repo=REPO_DIR,
        label="run-2",
        prompt=FOLLOW_UP_PROMPT,
        schema=FOLLOW_UP_REVIEW_SCHEMA,
        max_turns=FOLLOW_UP_MAX_TURNS,
        resume_session_id=first.session_id,
    )
except ResultError as exc:
    cost = (exc.data or {}).get("total_cost_usd")
    cost_str = f"{cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
    print(
        f"REVIEW-CYCLE-INCOMPLETE stage=run-2 subtype={exc.subtype} "
        f"reason={exc.terminal_reason} cost_usd={cost_str}"
    )
    raise

if second.subtype != "success" or second.session_id is None or not second.payload:
    print(f"REVIEW-CYCLE-INCOMPLETE stage=run-2 subtype={second.subtype}")
    raise RuntimeError("run 2 did not complete")
second_verdict = report("RUN-2", second)

prior_ids = finding_ids(first.payload)
recalled_ids = string_items(second.payload.get("previous_finding_ids"))
matched = sorted(set(recalled_ids) & set(prior_ids))
echoed = second.payload.get("previous_review_id") == FIRST_REVIEW_ID
print(
    f"RESUME-LINK run1_session={first.session_id} "
    f"run2_session={second.session_id} "
    f"same_session={second.session_id == first.session_id} "
    f"prior_review_id_echoed={echoed} "
    f"recalled_findings={len(matched)}/{len(set(prior_ids))}"
)
print(f"resolved={[clip(i) for i in string_items(second.payload.get('resolved'))]}")
if second.session_id != first.session_id or not echoed or (prior_ids and not matched):
    # Prints on a completed run by design, mirroring the script's marker.
    print(
        f"RESUME-LINK-BROKEN same_session={second.session_id == first.session_id} "
        f"recalled_findings={len(matched)}/{len(set(prior_ids))}"
    )
print(f"REVIEW-CYCLE-COMPLETE runs=2 verdicts={first_verdict},{second_verdict}")
```

??? note "輸出"

    ```text
    RUN-2 session=f3f70d8c-2d10-46f4-9cd8-58528c10dd22 subtype=success turns=6 denials=0 cost_usd=0.0404 tools_attempted=Glob,Read,StructuredOutput
    VERDICT: concerns
      F1 app/config.py: load_config still copies all of os.environ into the config and prints it, which leaks secrets to logs.
      F3 app/retry.py: fetch_with_retry loops forever on ConnectionError, with no attempt limit, no backoff and no timeout. A permanently unreachable service hangs the caller indefinitely.
    RESUME-LINK run1_session=f3f70d8c-2d10-46f4-9cd8-58528c10dd22 run2_session=f3f70d8c-2d10-46f4-9cd8-58528c10dd22 same_session=True prior_review_id_echoed=True recalled_findings=2/2
    resolved=['F2']
    REVIEW-CYCLE-COMPLETE runs=2 verdicts=concerns,concerns
    ```

## 用埋好的改動核對 findings

repository 裡的 bug 和週期之間的改動都是事先知道的，所以可以當兩次執行的標準答案。

### 檢查第一次執行的報告

第一次執行至少要回報兩個埋進去的 bug：

* `app/config.py`：loader 把整個環境複製進 config 並印出來
* `app/math_utils.py`：`divide` 沒有除以零防護，所以 `average([])` 會丟出 `ZeroDivisionError`

`config["environment"] = dict(os.environ)` 單看是無害的一行。洩漏的成因是下一行的 `print` 把它公開了，而環境變數正是部署放 secret 的地方。要報出這個問題，reviewer 得把這三件事在整個檔案裡接起來。除以零防護只測 reviewer 有沒有仔細讀。

### 檢查追蹤 review 的差異

追蹤 review 的報告把週期之間的改動拆成三部分：

* config 洩漏仍在 `findings`，沿用先前的 id
* 已修好的除以零防護，它的 id 移到 `resolved`
* `app/retry.py` 的無上限重試以新 finding 出現

`prior_review_id_echoed=True` 表示 resumed reviewer 說出了第一次執行給它的 id，`recalled_findings` 算的是第一次的 finding id 有幾個被帶回來。

### 預期每次執行會有差異

model 輸出每次會不同。reviewer 可能：

* 用不同的方式描述 findings
* 指派不同的 id
* 把一個埋進去的 bug 拆成好幾個 finding（除以零防護可能是一個 finding，也可能是 `divide` 和 `average` 兩個分開的）
* 回報額外的低嚴重度觀察

`resolved` 裡的 id 取決於這次改動修掉了什麼，不管 reviewer 怎麼拆。不管措辭如何，正確的第一次執行會報出兩個埋好的 bug，正確的追蹤執行會報出三部分差異，`RESUME-LINK` 欄位則帶著連續性證明。

你可以改 `demo_repo/` 裡的其他東西再跑一次追蹤，看差異怎麼變。筆記本把 baseline 固定在第一次執行，所以重複跑追蹤會回報 `prior_review_id_echoed=False` 並印出 `RESUME-LINK-BROKEN` 標記，即使 resume 其實成功了。附帶的 script 每次執行後都會存新的 baseline，重複的追蹤執行在那裡連結不會斷。

## 驗證失敗路徑

runner 那一節描述了失敗的執行長什麼樣子。下面的 cell 刻意觸發一次：對同一個 repository 跑一次全新的 review，設 `max_turns=1`，這個上限容不下一次完整 review。執行以終端錯誤結果結束，SDK 把它以 `ResultError` 丟出，`except` 區塊印出失敗行，帶著該結果的 `subtype` 和 `terminal_reason`。

**預期輸出：** 一行 `REVIEW-CYCLE-INCOMPLETE`，內容是 `stage=induced subtype=error_max_turns reason=max_turns`，加上這次失敗執行花掉的費用，而且沒有完成行。

```python
try:
    await run_review(
        repo=REPO_DIR,
        label="induced",
        prompt=FIRST_PROMPT,
        schema=FIRST_REVIEW_SCHEMA,
        max_turns=1,
    )
except ResultError as exc:
    cost = (exc.data or {}).get("total_cost_usd")
    cost_str = f"{cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
    print(
        f"REVIEW-CYCLE-INCOMPLETE stage=induced subtype={exc.subtype} "
        f"reason={exc.terminal_reason} cost_usd={cost_str}"
    )
else:
    raise RuntimeError("the run completed under max_turns=1")
```

??? note "輸出"

    ```text
    REVIEW-CYCLE-INCOMPLETE stage=induced subtype=error_max_turns reason=max_turns cost_usd=0.0009
    ```

## 把 reviewer 放上排程

前面兩個週期是手動跑的。排程時，每個週期就是呼叫一次 [`scheduled_review.py`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/scheduled_repository_reviewer/scheduled_review.py)，也就是筆記本旁的 companion script。它從自己的 service 目錄執行，以要 review 的 repository 當參數，並帶著同樣的 schema 和回覆 reader。

script 的標記行用 `REVIEW-RUN`，筆記本的週期用 `REVIEW-CYCLE`，筆記本的標記永遠不會出現在排程的 log 裡。session 檔 `.last_review_session` 不在 service 目錄時，script 就冷啟動 review，檔案存在就 resume。它的 `read_state` 函式承擔了筆記本裡由變數代勞的持久化。

排程之前，先把 script 讀過一遍。

請在常駐的主機上跑 reviewer。給任務一個檔案權限只限於 review 所需的使用者，以下每個步驟都用該使用者執行。resume 依賴兩個在週期之間必須保留的本機檔案：

* `.last_review_session`，script 放在自己旁邊 service 目錄裡的 session 檔
* SDK 寫在 `~/.claude/projects/` 底下的 session transcript，如果你設了 `CLAUDE_CONFIG_DIR`，則是它底下的 `projects/` 目錄

service 目錄要放在被 review 的 repository 外面。這樣的配置下，乾淨的 checkout 或切換 branch 不會刪掉 session 檔，這個檔案也不會出現在 reviewer 讀到的檔案裡。從這篇自己的目錄試跑 `python scheduled_review.py demo_repo`，會在啟動時被拒絕，印出 `reason=repository-inside-service-directory` 的 usage 行。service 目錄放在 repository 裡面也會同樣被拒絕，印出 `reason=service-directory-inside-repository` 的 usage 行。

### 排程 script

1. 建立 service 目錄和它自己的環境。筆記本的 `%pip` 安裝只影響筆記本自己的環境，而 cron 執行的是指令裡指名的直譯器。service 目錄要帶自己的 virtual environment，裡面裝好 SDK：

   ```bash
   sudo mkdir -p /srv/reviewer && sudo chown $USER /srv/reviewer && cd /srv/reviewer
   python3 -m venv .venv
   .venv/bin/pip install "claude-agent-sdk>=0.2.140"
   cp /path/to/scheduled_review.py .
   ```

   請用 3.11 以上的 `python3`，也就是前置條件列的下限，更舊的直譯器會在 script 第一個 import 就失敗。

2. 建立 cron 任務要 source 的環境檔，放在 `/srv/reviewer/reviewer.env`。環境必須由排程器提供，因為 cron 啟動時幾乎沒有任何環境變數。要用 `export` 行，因為單純的 `KEY=value` 只會設定 shell 變數，Python process 不會繼承。cron 會把 `PATH` 縮到最小，請把它設成涵蓋任務需要的執行檔所在目錄：

   ```bash
   # /srv/reviewer/reviewer.env, sourced by the cron job
   export PATH=/usr/local/bin:$PATH
   export ANTHROPIC_API_KEY=your_key_here
   ```

   放入 key 之前，先建立空檔案並限制權限：`touch /srv/reviewer/reviewer.env && chmod 600 /srv/reviewer/reviewer.env`，再把上面的行加進去。script 預設也會禁止自己 `Read` service 目錄，讓放 key 的檔案不會出現在任何 finding 裡。同樣的禁止會讓 review 位於 service 目錄內的 repository 時什麼都看不到，所以 script 直接拒絕那種配置。不要把 key 放在 crontab 那一行裡，因為任何能列出 crontab 的人都讀得到。

3. 從 service 目錄手動跑一次 script，指向你要 review 的 repository：

   ```bash
   cd /srv/reviewer && . ./reviewer.env && .venv/bin/python scheduled_review.py /path/to/your/repo
   ```

   第一次執行是冷啟動 review，會印出 `REVIEW-RUN-COMPLETE: cold`，並建立 `.last_review_session` 檔和 session transcript，之後每次排程執行都 resume 它們。如果執行以 `error_max_budget_usd` 結束且 exit 1，排程前請調高 `FIRST_RUN_BUDGET_USD`。冷啟動預算不夠就建立不了 baseline，之後每個排程週期都會重複同樣的失敗。
4. 用 `crontab -e` 加一條 crontab，設成每晚 02:00 review。要用跟步驟 3 同一個使用者排程，因為 session transcript 放在那個使用者的 home 底下：

   ```bash
   0 2 * * * cd /srv/reviewer && . ./reviewer.env && flock -n -E 99 .review.lock .venv/bin/python scheduled_review.py /path/to/your/repo >> /srv/reviewer/review.log 2>&1 || echo "REVIEW-RUN-EXIT: $?" >> /srv/reviewer/review.log
   ```

   這一條尾端會把失敗的呼叫的 exit status 變成一行 log。兩個 redirect 都用絕對路徑指定 log，標記不會寫到相對於 cron 啟動目錄的檔案裡。

   `flock -n` 在前一次執行還握著鎖時，直接跳過這次呼叫，`-E 99` 讓這個跳過有自己的 exit code。被跳過的執行會記 `REVIEW-RUN-EXIT: 99`，不會被當成失敗。`flock` 在 Linux 主機上來自 util-linux。macOS 預設沒有 flock，可以用 Homebrew 的 [flock formula](https://formulae.brew.sh/formula/flock) 安裝。

   findings 會引用 repository 的內容，所以 `review.log` 要跟被 review 的 repository 用同樣方式處理。log 的輪替方式跟你其他服務的 log 一樣。下一節的 `REVIEW-RUN-EXIT` 那一列說明怎麼讀它。


### 讀輸出行

排程器讀的是這些行：

| Line | Fires when | Exit code | Alert |
|---|---|---|---|
| `VERDICT: ok` or `VERDICT: concerns` | 完成的 review 回報結構化回覆裡的 verdict。失敗的執行不會印這行 | 0 | `concerns` 時告警 |
| `RESUME-LINK ...` | 每次 resumed 執行都有。`same_session=True` 加上穩定的 `recalled_findings` 數量，代表連續性正常，`current_findings` 是追蹤 review 自己的 finding 數 | 0 | 在你自己的告警裡對 `recalled_findings` 設門檻。數量慢慢崩掉不會印任何標記，那正是「定期重置 session」一節說的重置訊號 |
| `RESUME-LINK-BROKEN ...` | 連結直接斷掉：session 遺失、echo 遺失，或 recall 變成零。標記在該行最前面，方便 grep | 0 | 告警。這次執行已經為下個週期存好新的 baseline |
| `REVIEW-RUN-COMPLETE: cold` or `: resumed` | review 確實成功 | 0 | 不用處理。它出現就代表這個週期已收尾 |
| `REVIEW-RUN-INCOMPLETE ...` | 執行以終端錯誤結果結束，最常見是超過邊界。`subtype` 指出是什麼讓它結束，邊界與 schema 失敗會加上 `reason`。session 崩潰後這行可能出現 `cost_usd=0.0000`，意思是費用未知，不是零 | 1 | 告警。邊界失敗會保留 session 檔，修法是改設定 |
| `REVIEW-RUN-INCOMPLETE ... subtype=error_max_structured_output_retries` | 回覆多次驗證 schema 失敗，或是 [model fallback](https://code.claude.com/docs/en/model-config#automatic-model-fallback) 撤回了已完成的回覆而且沒有剩下的 retry 可以取代它。兩者都不是 session 的問題 | 1 | 告警。session 檔會保留 |
| `REVIEW-RUN-INCOMPLETE stage=usage ...` | 呼叫方式本身錯了，例如缺少 repository 參數 | 2 | 告警。修 crontab 那一條 |
| `SESSION-FILE-CLEARED: next run reviews cold` | resumed 執行以 `subtype=error_during_execution` 失敗，最常見是儲存的 session 無法再 resume；暫時性的連線失敗也會落在這裡，用一次冷啟動重建換來自我修復 | 1 | 除了失敗告警外不用另外處理。下個週期會冷啟動重建 baseline |
| `SESSION-STATE-NOT-SAVED ...` | review 完成了，但狀態寫不進去，最常見是磁碟滿了或唯讀。標記上面的 findings 是有效的。後面接 `SESSION-FILE-CLEARED` 代表下次執行冷啟動重建；接 `SESSION-FILE-STALE` 代表下次會 resume 上一個 session | 1 | 告警。修磁碟，review 本身不用重跑 |
| `REVIEW-RUN-EXIT: <code>` | crontab 那一條的尾端記錄非 0 的 exit，包含被跳過的重疊執行留下的 `99` | n/a | 除了 99 以外的任何 code 都告警 |
| No line at all | 執行在拿到終端結果前就死了，例如 process 被殺或連線一直打不開 | non-zero | 缺少完成行、又沒有 `99` 的跳過可以解釋時告警 |

刻意設 `max_turns=1` 的執行會印出一行以 `REVIEW-RUN-INCOMPLETE stage=cold subtype=error_max_turns reason=max_turns` 開頭的行，這是 grep 用的前綴，後面接上這次執行的 `cost_usd`。「驗證失敗路徑」那一節在筆記本裡觸發過同樣的終端結果。

成功的週期會在 log 留下 `REVIEW-RUN-COMPLETE`，失敗的週期會留下 `REVIEW-RUN-EXIT` 標記。除了 99 以外的任何 `REVIEW-RUN-EXIT` code，或是缺少完成行又沒有 `99` 跳過可解釋的週期，都要告警。跳過是正常的重疊，反覆跳過代表執行時間超過排程間隔。每個標記的 grep 都要錨定在行首。finding 文字會被截成單行縮排的內容，所以標記只會出現在一行的開頭。`stage=resumed` 失敗後接著 `SESSION-FILE-CLEARED` 行，代表儲存的 session 已經無法 resume，最常見的原因是 `~/.claude/projects/` 底下的 transcript 不見了。

### 客製 reviewer

* **prompt**：把追蹤用的 prompt 指向你想讓 review 追蹤的東西，例如新增的依賴、破壞性的 API 變更，或 TODO 債。
* **schema**：加上你的告警需要的欄位，例如每個 finding 的嚴重度。回覆會依你宣告的 schema 驗證後回來。script 帶著自己那份 schema 和 reader 的副本，客製任何一邊時兩邊都要改。
* **邊界**：`max_turns` 和 `max_budget_usd` 放在 script 最上面。筆記本 cell 裡的兩個邊界是依三個檔案的範例 repository 設定的，比錄製執行的 `cost_usd` 留了餘裕。script 的預設值則為真實的 repository 留了餘裕。預算是防止失控的後盾，跟 turn 上限一樣分開設定。baseline review 用 `FIRST_RUN_BUDGET_USD`，每次追蹤用 `FOLLOW_UP_BUDGET_USD`。追蹤的上限是排程會被乘上去的那個。以預設值來算，每晚跑的任務最壞一個月大約是 30 × $0.50 = $15，再加偶爾一次冷啟動重建，而錄製的執行每次只花幾分錢。看幾個週期的摘要行裡的 `cost_usd`，找出適合你的上限。這個數字是 client 端的估算，不是帳單資料，[Track cost and usage](https://code.claude.com/docs/en/agent-sdk/cost-tracking) 說明了差異。[`effort` 選項](https://code.claude.com/docs/en/agent-sdk/agent-loop#effort-level) 是另一個控制成本的手段，文件建議只讀檔案的 agent 用 `"low"`，這個 reviewer 就是這種。
* **model**：換掉 `MODEL` 別名，在成本和能力之間取捨。固定 model 讓這種改動是你刻意做的。

## 定期重置 session

長期存活的 session 本來就會累積 context。這些 context 也會推高成本，還可能讓 reviewer 被舊結論牽著走。定期（每週，或 repository 結構改變時）刪掉 script 旁的 session 檔，下一次執行就會冷啟動 review 並重建 baseline。

追蹤 review 的 `recalled_findings` 數量是實際的營運訊號。數量掉下去，代表 session 退化了，該重置。

## 什麼時候 resume、什麼時候重新開始

排程的 review 任務可以 resume 上一次的 session、每個週期重新開始，或是重新開始但把先前的 findings 餵進去。下表把各個選擇對應到適合的任務：

| Reach for | When |
|---|---|
| 每次呼叫用全新的 session | 每個工作單元都各自被評判。把關 pull request 的 CI reviewer 需要這樣：不能有舊意見，也不能有帶過來的 context 影響這次的 verdict。 |
| 全新的 session，並餵入先前的 findings | 任務只需要上次回報的內容。追蹤 TODO 債的工具，回報上週的項目哪些還沒結束，就是這種形狀：回覆裡的 finding id 就帶了比對所需的一切，每個週期對程式碼做全新的判斷，週期之間也不會有儲存的 session 過期或遺失。 |
| resumed session | 任務要跟上一輪看過的所有東西比對。每晚的依賴稽核，只標出上次之後新增或變更的套件，要檢查 reviewer 讀過的完整清單，而那份清單大部分從沒進入回覆。自己把它往前餵，得序列化 reviewer 觀察到的一切，這正是 resume 幫你省下的工作。 |

## 清理

筆記本在 `demo_repo/` 寫了四個檔案，也就是兩個週期的 fixture 加上週期之間的改動。下面的程式在確認目錄裡只有這份 fixture 後把它們移除。如果想先照標準答案那一節做差異實驗，先不要清理，之後需要這些檔案時再跑一次建立範例 repository 的程式。

如果你也跑了 companion script，service 目錄裡的 `.last_review_session` 檔也要一併刪掉。這些執行還在 `~/.claude/projects/` 底下寫了 session transcript，刪掉那裡對應的 project 資料夾就能移除它們。

```python
import shutil

config_path = REPO_DIR / "app" / "config.py"
if config_path.exists() and config_path.read_text(encoding="utf-8") == CONFIG_PY:
    shutil.rmtree(REPO_DIR, ignore_errors=True)
    print("removed", REPO_DIR.name)
else:
    print("left", REPO_DIR.name, "in place: it does not hold the seeded fixture")
```

??? note "輸出"

    ```text
    removed demo_repo
    ```

## 你學到了什麼

* **替無人值守的 agent 設邊界**：`tools` 和 `allowed_tools` 決定有什麼工具、哪些不用提示就能跑，`max_turns` 加 `max_budget_usd` 限制 loop 和花費，所以排程執行只能在你選的限度內出錯。
* **證明連續性**：resume 前一次 session 的 agent 會記得它已經找到的東西。讓每次執行都在回覆裡複述上一次的 findings 來證明這點，resume 壞掉時 log 會當場顯示。
* **把 reviewer 放上排程**：無人值守的 review 是回報給程式的，所以它的輸出是 exit code 和排程器能 grep 的固定行。對這個 reviewer 來說，就是代表 repository 狀態的 verdict 行、只在成功後才印的完成行，以及標記每個失敗的非 0 exit。

## 延伸閱讀

* [Get structured output from agents](https://code.claude.com/docs/en/agent-sdk/structured-outputs)：這篇回覆用到的 `output_format` schema 和 `structured_output` 欄位的完整文件
* [Work with sessions](https://code.claude.com/docs/en/agent-sdk/sessions)：session 生命週期，超出這篇用的 resume，包括把 session fork 成兩條路徑
* [Configure permissions](https://code.claude.com/docs/en/agent-sdk/permissions)：這篇 `dontAsk` 背後的權限模式模型，以及為互動使用設計的模式
* [Security](https://code.claude.com/docs/en/security)：Claude Code 的安全防護，包括處理不受信任內容的最佳做法
* [Track cost and usage](https://code.claude.com/docs/en/agent-sdk/cost-tracking)：`max_budget_usd` 背後的成本介面，以及摘要行費用數字的來源

## 重點整理

- 無人值守的 agent 靠兩層限制：`tools` / `allowed_tools` 決定能做什麼，`max_turns` / `max_budget_usd` 決定能做多久、花多少。
- resume 讓 agent 帶著上一輪讀過的所有內容開工，不用另外建儲存層，但要在回覆裡複述前次 finding id 來驗證 resume 真的有效。
- 排程任務的輸出是給程式讀的：結構化 schema、固定格式的標記行、非 0 exit code，讓 grep 和告警能直接接上。
- 讀取範圍要靠 hook 這種不依賴工具涵蓋範圍的機制再加一層，並用 `setting_sources=[]` 避免被 review 的 repository 設定自己的 reviewer。
- resume、全新 session、全新 session 加餵入 findings 各有適合的任務，session 也要定期重置，避免 context 越滾越大。

## 練習

1. 把追蹤 review 的 prompt 改成另外追蹤一件事（例如 TODO 註解），在 `demo_repo/` 加一個含 TODO 的檔案，看追蹤 review 有沒有抓到。
2. 在 review schema 的每個 finding 加一個 `severity` 欄位（限定 `low` / `medium` / `high`），再改 verdict 邏輯，讓有 `high` 的 finding 時印出 `VERDICT: concerns`。
3. 把 `max_budget_usd` 調到很低的值，跑一次冷啟動 review，觀察 `ResultError` 的 subtype 跟 `REVIEW-CYCLE-INCOMPLETE` 行，再想想排程時 `FIRST_RUN_BUDGET_USD` 為什麼要比追蹤的預算高。
