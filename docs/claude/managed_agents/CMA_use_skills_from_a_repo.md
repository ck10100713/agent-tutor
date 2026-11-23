---
translated: true
source: managed_agents/CMA_use_skills_from_a_repo.ipynb
---
# Skills: 自動載入 repo 裡的 .claude/skills

> 原文：[managed_agents/CMA_use_skills_from_a_repo.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_use_skills_from_a_repo.ipynb)

掛載一個 GitHub repository，session 啟動時會自動找出根目錄的 .claude/skills 並注入 agent。這篇看請求符合 skill 描述時「先讀再照做」的流程，並說明目錄結構跟生命週期規則。

## 這篇在做什麼

如果團隊已經把 skill 寫在 repo 的 `.claude/skills/` 裡，Managed Agents 的 session 掛載這個 repo 後就會自動發現這些 skill，不用再上傳到 Skills API。這篇用一個公開 repo 實際跑一遍，並整理 scanner 的規則跟限制。

## 學完你會

- 知道 scanner 期待的 skill 目錄結構（`.claude/skills/<name>/SKILL.md`）。
- 用 `github_repository` resource 掛載 repo，讓 agent 不掛任何 skill 也能用 repo 的 skill。
- 判斷什麼時候該用 repo skill、什麼時候該用 Skills API。

## 開跑前

- 需要 `GITHUB_TOKEN` 環境變數（Fine-grained personal access token，有公開 repo 讀取權限就夠）。
- 需要 Anthropic API key，並使用 Managed Agents。

團隊如果已經替 Claude Code 寫了 skill，通常會放在 repository 的 `.claude/skills/<skill-name>/SKILL.md`，跟它描述的程式碼一起版本控管。把這些一個個上傳到 Skills API、再到每個 agent 上釘版本，等於做兩次工，而且只要有人改了 repo 就會不同步。

Session 掛載 GitHub repository 時，harness 會在 session 啟動時掃描 repo 根目錄的 `.claude/skills/`，把找到的每個 skill 注入 agent 的 system prompt：包含 skill 的名稱、描述，以及它在 sandbox 裡的路徑。當請求符合某個 skill 的描述時，model 會用內建的 `read` tool 讀該 skill 的 `SKILL.md`，然後照著做，包括 skill 附帶的 script 或參考檔。不用上傳、agent 上不用設 `skills` 欄位、也不用管版本。你拿到的 skill 就是你 checkout 的那個 branch 上的版本。

這篇 notebook 會講：

- scanner 期待的磁碟目錄結構
- 怎麼掛載 repo 讓 skill 被發現
- 確認 skill 被發現，並觀察「先讀再照做」的流程
- 邊界在哪：結構規則、skill 數量上限、session 中途變更

## 1. 設定 client

你的環境需要有 `GITHUB_TOKEN`。這個 notebook 掛載的 repo 是公開的，所以 Fine-grained personal access token 加上公開 repo 讀取權限就夠了。Repository skill 只有在 Anthropic 代管的環境（`anthropic_cloud`）才會被發現。自架 sandbox 不會 clone GitHub repository，所以不在這個功能的範圍內。

```python
%%capture
%pip install -qU "anthropic>=2.0.0" python-dotenv
```

```python
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

BETAS = ["managed-agents-2026-04-01"]
MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
GH_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GH_TOKEN:
    raise SystemExit(
        "Set GITHUB_TOKEN in your environment (a fine-grained PAT with public-repo read)."
    )
client = anthropic.Anthropic()
```

## 2. Scanner 找的目錄結構

Skill 只從一個地方找：repository 根目錄的 `.claude/skills/`，每個 skill 一個目錄，每個目錄最上層要有 `SKILL.md`。跟 Claude Code 用的慣例一樣。

```
your-repo/
└── .claude/
    └── skills/
        ├── cookbook-audit/
        │   ├── SKILL.md          <- name + description frontmatter, then instructions
        │   ├── style_guide.md    <- reference file the instructions point at
        │   └── validate_notebook.py  <- script the instructions run
        └── another-skill/
            └── SKILL.md
```

`SKILL.md` 開頭是 YAML frontmatter，帶 `name` 跟 `description`。Model 決定要不要打開檔案是拿 description 來比對，所以它要寫得像觸發條件：這個 skill 做什麼、什麼時候該用。

```markdown
---
name: cookbook-audit
description: Audit an Anthropic Cookbook notebook based on a rubric. Use whenever a notebook review or audit is requested.
---

# Cookbook Audit
...
```

公開的 `anthropics/claude-cookbooks` repository 就附了這樣一個 skill，有 `style_guide.md` 裡的評分標準，以及一個 `validate_notebook.py` script。掛載這個 repo，就一次拿到有說明、有參考檔、有可執行 script 的 skill。

## 3. 建立不掛任何 skill 的 agent

Agent 的定義完全沒提到 skill，只有標準 toolset 跟通用 prompt。Skill 是跟著 repository 來的，不是跟著 agent 定義。

```python
env = client.beta.environments.create(
    name="repo-skills-demo",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
    betas=BETAS,
)

reviewer = client.beta.agents.create(
    name="cookbook_reviewer",
    description="Reviews notebooks in a mounted cookbook repository.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-use-skills-from-a-repo"},
    model={"id": MODEL},
    system="You review notebooks in the repository mounted under /workspace. "
    "When the repository provides a process for a task, follow it.",
    tools=[{"type": "agent_toolset_20260401"}],
    betas=BETAS,
)
print(f"{reviewer.name}: {reviewer.id} v{reviewer.version}")
```

## 4. 掛載 repository

`github_repository` resource 會在 session 啟動時把 repo clone 進 container。`url` 用單純的 `https://github.com/{owner}/{repo}` 格式（不加 `.git`，也不能用 SSH 格式）。`checkout` 可以釘 branch 或 commit，`mount_path` 可以覆寫預設的 `/workspace/<repo-name>`。Skill 發現是跟著 checkout 的 ref 走，所以 branch 不同、skill 就會不同。

```python
session = client.beta.sessions.create(
    agent=reviewer.id,
    environment_id=env.id,
    title="Cookbook audit",
    resources=[
        {
            "type": "github_repository",
            "url": "https://github.com/anthropics/claude-cookbooks",
            "authorization_token": GH_TOKEN,
            "checkout": {"type": "branch", "name": "main"},
            # mount_path defaults to /workspace/claude-cookbooks
        }
    ],
    betas=BETAS,
)
print(session.id, session.status)
```

## 5. 問 agent 有哪些 skill

發現是 session 啟動時就做完的，所以這個問題不用探索檔案就能回答。Agent 直接從 system prompt 說出 `cookbook-audit` 跟它的 `SKILL.md` 路徑。

```python
from utilities import stream_until_end_turn

client.beta.sessions.events.send(
    session.id,
    events=[
        {
            "type": "user.message",
            "content": [{"type": "text", "text": "What skills are available to you in this repo?"}],
        }
    ],
    betas=BETAS,
)
stream_until_end_turn(client, session.id)
```

## 6. 不提名字就觸發 skill

Description 的用意就是讓 model 依意圖來判斷。這個請求完全沒提 "skill" 或 "cookbook-audit"，只說想要 skill 產出的結果。

注意看 tool event。這一輪的第一個 `read` 會打開 skill 的 `SKILL.md`。接著 agent 照 skill 的指示做：讀 `style_guide.md`、執行 `validate_notebook.py`、依評分標準打分，而不是自己發明一套稽核流程。

```python
client.beta.sessions.events.send(
    session.id,
    events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": "Do a notebook audit of "
                    "managed_agents/CMA_iterate_fix_failing_tests.ipynb "
                    "against the cookbook style guide, and give me the score.",
                }
            ],
        }
    ],
    betas=BETAS,
)

with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "agent.tool_use":
            target = ev.input.get("file_path") or ev.input.get("command") or ""
            print(f"[{ev.name}] {str(target)[:100]}")
        elif ev.type == "agent.message":
            print("".join(b.text for b in ev.content if b.type == "text"), end="")
        elif ev.type == "session.status_idle":
            print(f"\n[idle] stop_reason={ev.stop_reason.type}")
            break
```

把 `read` 呼叫單獨挑出來，就能看到完整流程：先讀 skill 的 `SKILL.md`，再讀 skill 附帶的參考檔跟 script，最後才是工作碰到的 repository 檔案。

```python
reads = [
    ev.input.get("file_path")
    for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS)
    if ev.type == "agent.tool_use" and ev.name == "read"
]
for path in reads:
    print(path)
```

## 7. Scanner 強制執行的規則

**結構很嚴格。** 只有 repository 根目錄的 `.claude/skills/<name>/SKILL.md` 會在 session 啟動時被宣告。沒有子目錄的 `.claude/skills/SKILL.md`、兩層巢狀的 `.claude/skills/a/b/SKILL.md`、缺少 `.claude` 上層的 `skills/<name>/SKILL.md`，都會被忽略。

**Frontmatter 很寬鬆。** 沒有 frontmatter 的 `SKILL.md` 仍然會被宣告，名稱用目錄名，description 為空。很長的 description 會被壓成一行，超過 2,000 字元會被截斷。CRLF 換行也能正常解析。

**有數量上限。** 只有前 64 個 skill 目錄會被宣告。超過的會被默默丟掉，不會報錯，所以 skill 很多的 repository 要把 session 依賴的 skill 放前面，而且數量要少。

**掃描只跑一次。** 發現動作在 session 啟動時進行，結果保存在該 session 內。Session 進行中才 push 新 skill 到 repository，對正在跑的 session 沒有影響，下一個針對該 repository 建立的 session 才看得到。

**巢狀 skill 是延遲發現的。** 如果 repository 有 `packages/foo/.claude/skills/lint/SKILL.md` 但根目錄沒有 skill，啟動時什麼都不會宣告。等 agent 用內建 `read` tool 讀了 `packages/foo/` 底下的檔案，harness 才會注意到這個巢狀的 `.claude/skills/` 目錄，並在 session 剩下的時間裡把 `lint` 顯示出來。透過 `bash`（`cat`）讀同一個檔案不會觸發，只有 `read` tool 會。

## 8. Repository skill 與 Skills API 並存

兩種機制可以同時用在一個 session，兩種 skill 都會出現在 agent 的清單。

Skill 跟程式碼放一起比較合理時，用 repository skill：build 跟測試慣例、review checklist、部署 runbook，任何你希望 pull request 跟原始碼一起改的東西。不管是人或 agent，clone 這個 repo 的人拿到的指示都一樣。

如果 skill 是跨 repository 的組織層級資產、需要獨立於任何程式碼的版本管理，或是要在沒有掛載任何 repository 的 session 裡使用，就用 [Skills API](https://platform.claude.com/docs/en/managed-agents/skills)（在 agent 上設 `skills=[{"type": "custom", "skill_id": ...}]`）。

兩邊名稱衝突是允許的：repository 的 `verify` skill 跟組織的 `verify` skill 會同時出現，路徑不同，model 依請求內容選擇。如果兩個掛載的 repository 都有同名 skill，兩個都會被宣告，掛載路徑各自不同。

## 9. 清理

```python
from utilities import wait_for_idle_status

wait_for_idle_status(client, session.id)
client.beta.sessions.archive(session.id, betas=BETAS)
client.beta.environments.archive(env.id, betas=BETAS)
print("archived")
```

## 重點整理

- Repository skill 跟程式碼一起版本控管，session 掛載 repo 就自動發現，不用上傳或在 agent 上設定。
- Model 靠 SKILL.md 的 description 判斷要不要用，description 要寫得像觸發條件。
- 發現的流程是「先用 `read` 讀 SKILL.md，再照它的指示行動」，掃描只在 session 啟動時做一次。
- 結構嚴格（只認根目錄 `.claude/skills/<name>/SKILL.md`），最多 宣告 前 64 個。
- 跟程式碼綁在一起的 skill 用 repo，跨 repo 或要獨立版本的 skill 用 Skills API。

## 練習

1. 把掛載時的 `checkout` 改成另一個 branch 或 commit，問 agent 它有哪些 skill，看清單有沒有變。
2. 換一個沒提 skill 名稱、但符合 `cookbook-audit` description 的請求，觀察 `read` 呼叫的順序有沒有一樣。
3. 自己建一個 repo，放兩個 skill（一個結構正確、一個多包一層目錄），掛載後確認只有正確的那個被宣告。
