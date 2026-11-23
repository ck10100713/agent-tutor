---
translated: true
source: examples/skills_in_api.ipynb
---
# OpenAI API 的 Skills

> 原文：[examples/skills_in_api.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/skills_in_api.ipynb)

用 OpenAI API 建立 skill 的 cookbook。

## 這篇在做什麼

把一個 CSV 分析流程包成 skill，上傳到 API，再用 GPT-6 Astra 在 hosted shell 裡執行。同一份檔案也可以給本機的 shell runtime 使用。

## 學完你會

- 寫出帶 `SKILL.md` frontmatter 的 skill 資料夾，並用檔案或 zip 兩種方式上傳。
- 用 `skill_reference` 把 skill 掛到 hosted shell，並固定版本。
- 分辨什麼情況該用 system prompt、tool 還是 skill。

## 開跑前

- 需要 Python 3.10 以上、`curl`、`zip`。
- 需要 `OPENAI_API_KEY`，而且該 project 有 `gpt-6-astra` 和 hosted shell 的權限。
- 上傳 skill 和 Responses API 呼叫會產生模型與 container 費用。

Package a CSV analysis workflow as a skill, upload it, and run it with GPT-6 Astra in hosted shell. You can also expose the same files to a local shell runtime. 完整參考請看 [Skills 文件](https://developers.openai.com/api/docs/guides/tools-skills)。

## 什麼是 skill？

skill 是一組可重用的檔案（指示、腳本、資源），打包成資料夾，並以必要的 `SKILL.md` manifest 為核心。OpenAI 會把這個 bundle 複製到執行環境，讓模型能依需要讀取指示並執行程式碼。

在 hosted shell 裡，把 skill 掛到 shell tool 的環境（`environment.type="container_auto"`）時，會發生這些事：


- 服務把 skill 上傳並解壓縮到 runtime
- 服務讀取 `SKILL.md` 的 frontmatter（name 和 description），再把每個 skill 的 `name`、`description` 和 `path` 加進使用者 prompt 的 context，讓模型知道有這個 skill
- 如果模型決定使用某個 skill，就用 `path` 讀 `SKILL.md`，再透過 shell tool 瀏覽檔案和執行腳本

skill 的指示和其他使用者提供的指示有相同的優先順序。

skill 是用來放流程的：可重複、而且「怎麼做」很重要的工作流程（步驟、分支邏輯、格式規則、腳本）。如果你希望流程符合下面幾點，用 skill 很合適：

- 在不同的 prompt 和 agent 之間重用
- 有版本、可獨立發布
- 需要時才呼叫（不用塞進每個 system prompt）

### 什麼時候用 skill


**skill 特別適合、也特別有力的情況：**

1. **你想要一組可重用、能獨立版本管理的行為。**
例如：「PowerPoint 格式化流程」「公司專屬的報表產生器」「標準的資料清理 pipeline」。
2. **你的工作流程條件很多，或像複雜的流程圖一樣分支。**
例如：如果 X 就做這個，否則如果 Y 就做那個，再加上驗證和重試。
3. **你的工作流程需要執行程式碼和本機產物。**
任何會用到腳本、模板、測試資料或參考資源、而且該放在指示旁邊的東西。skill 就是設計成這些資源的 zip。
4. **你想讓 system prompt 保持精簡。**
把穩定的流程放進 skill，system prompt 只留全域行為。
5. **多個 agent 或團隊共用同一套「house style」。**
skill 很適合當成「組織標準函式庫」的模式。
6. **你需要可重現性**
skill 天生能用 skill 版本做版本固定（見下面的版本管理一節）。


**skill 比較不適合的情況：**

- 真的只做一次的任務（在對話裡臨時寫段 script 就好）。
- 你主要需要**即時的外部資料或副作用。**（那是 tool 或 API call 的工作）。
- 流程每天都在變（skill 要等工作流程穩定下來才有價值）。


## Skills、tools 和 system prompts 的差別

邊界不清楚的時候，system prompt 和 tool schema 都會變得很笨重。三者搭配使用，才能保持有條理，也讓模型表現更好。這是一個簡單的框架：

**System prompt：全域行為和限制**

適合放：
- 安全邊界、語氣、拒絕的風格
- 每一輪都適用的「一律做 X」原則
- 小而穩定的政策

避免：

- 把冗長的多步驟流程放在這裡（會讓每一輪都變臃腫，也變得脆弱）



**Tools：「在世界上做些什麼」**

模型需要下列情況時用 tool：

- 呼叫外部服務或資料庫
- 產生副作用（環境之外的任務，像取消訂單或寄 email）
- 取得即時狀態

tool 應該：

- 範圍窄
- 輸入有強型別
- 明確說出副作用

**Skills：打包好的流程（加程式碼和資源）**

你希望模型做到下列事情時用 skill：

- 遵循可重複的工作流程
- 使用腳本或模板
- 在 sandbox 裡執行程式碼
- 偶爾做，而不是每次都做


## Skill 打包：SKILL.md 和資料夾結構

### 資料夾結構

skill 就是一個資料夾 bundle。範例如下：
- `SKILL.md`（必要）
- 腳本，例如 `*.py`、`*.js`（選用）
- 輔助檔和 `requirements.txt`
- 資源、模板、範例輸入


### SKILL.md frontmatter

OpenAI 模型預期名稱和描述來自 frontmatter（對探索和路由很重要）。把 name 和 description 放在 `SKILL.md` 的 frontmatter。每次 API `create` 呼叫上傳一個 skill bundle（一個頂層資料夾），裡面剛好有一個 `SKILL.md` 或 `skill.md`。要上傳多個 skill，就上傳多個 bundle。


## 透過 API 建立 skill

把 skill 組好在資料夾之後，用 API 呼叫建立 skill。

### 上傳資料夾或上傳 zip


用 `POST /v1/skills` 上傳並驗證 skill，它會從 manifest 的 frontmatter 取出 name 和 description。你可以上傳 zip bundle，也可以在請求裡上傳多個檔案。

**做法 A：上傳檔案（multipart）**



```bash
curl --fail-with-body 'https://api.openai.com/v1/skills' \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F 'files[]=@./csv_insights_skill/SKILL.md;filename=csv_insights_skill/SKILL.md;type=text/markdown' \
  -F 'files[]=@./csv_insights_skill/run.py;filename=csv_insights_skill/run.py;type=text/plain' \
  -F 'files[]=@./csv_insights_skill/requirements.txt;filename=csv_insights_skill/requirements.txt;type=text/plain' \
  -F 'files[]=@./csv_insights_skill/assets/example.csv;filename=csv_insights_skill/assets/example.csv;type=text/csv'
```

**做法 B：上傳 zip**

```
curl -X POST 'https://api.openai.com/v1/skills' \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F 'files=@./csv_insights_skill.zip;type=application/zip'
```

每個 skill 只用一種上傳方式。zip 能把指示、腳本、相依套件和範例輸入放在一起。



**Skill 物件和版本指標**

回應會包含 skill 的 `id`、`default_version` 和 `latest_version`。把 `id` 和一個版本存下來，才能把上傳的 skill 掛到 hosted shell。

## 把 skill 掛進執行環境

要在 Responses API 使用 skill，用 `tools[].environment.skills` 把它們掛到 shell tool。

### 如何引用 skill

- **Hosted shell**（`environment.type="container_auto"`）：用 `skill_reference` 加 `skill_id` 和選用的 `version`，或用 `inline` 的 base64 zip bundle。
- **Local shell**（`environment.type="local"`）：為 runtime 裡有的檔案提供 `name`、`description` 和 `path`。Local shell 不接受 hosted 的 `skill_reference`。你的應用自己執行被要求的命令並回傳輸出。

## 可執行範例：`csv_insights_skill` Skill

這個逐步範例會在磁碟上建立檔案，再執行 Python 片段，它不是能用 **Run All** 一次跑完的 notebook。請把下面的腳本存成 `csv_insights_skill/run.py`。

前置條件：Python 3.10 以上、`curl`、`zip`，以及一個 `OPENAI_API_KEY` 環境變數，對應的 project 要有 `gpt-6-astra` 和 hosted shell 的權限。用 `python -m pip install --upgrade openai` 安裝最新的 Python SDK。

上傳的指令會在你的 API project 建立 skill。Responses API 呼叫會產生[模型與 container 費用](https://developers.openai.com/api/docs/pricing)。除非設定 `RUN_SKILLS_API=1`，否則 Python 的 API 範例是停用的。先跑本機檢查，準備好要送 API 請求時再啟用。

**1) 建立 skill 資料夾和範例輸入。**

```bash
mkdir -p csv_insights_skill/assets
```

完成後的資料夾應該包含：

```text
csv_insights_skill/
├── SKILL.md
├── requirements.txt
├── run.py
└── assets/
    └── example.csv
```

把這些相依套件存成 `csv_insights_skill/requirements.txt`。`tabulate` 是 pandas 的 `to_markdown()` 方法需要的。

```text
pandas
matplotlib
tabulate
```

把這份合成的輸入存成 `csv_insights_skill/assets/example.csv`：

```csv
quantity,price,category
2,10,books
3,15,games
,20,books
```


**2) 建立你的 `SKILL.md`**

```
---
name: csv-insights
description: Summarize a CSV, compute basic stats, and produce a markdown report + a plot image.
---

# CSV Insights Skill

## When to use this
Use this skill when the user provides a CSV file and wants:
- a quick summary (row/col counts, missing values)
- basic numeric statistics
- a simple visualization
- results packaged into an output folder (or zip)

## Inputs
- A CSV file path (local) or a file mounted in the container.

## Outputs
- `output/report.md`
- `output/plot.png` (when the CSV has a numeric column)

## How to run

Run from the directory containing this SKILL.md. The environment must have
pandas, matplotlib, and tabulate installed. If a dependency is unavailable,
report it rather than attempting an unapproved network install.

python run.py --input assets/example.csv --outdir output

Use the output directory requested by the user when one is provided.
Check that report.md exists and that plot.png exists for numeric input.

```

**3) 建立你的 `run.py`**

```python
import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def write_report(df: pd.DataFrame, outpath: Path) -> None:
    lines = []
    lines.append(f"# CSV Insights Report\n")
    lines.append(f"**Rows:** {len(df)}  \n**Columns:** {len(df.columns)}\n")
    lines.append("\n## Columns\n")
    lines.append("\n".join([f"- `{c}` ({df[c].dtype})" for c in df.columns]))

    missing = df.isna().sum()
    if missing.any():
        lines.append("\n## Missing values\n")
        for col, count in missing[missing > 0].items():
            lines.append(f"- `{col}`: {int(count)}")
    else:
        lines.append("\n## Missing values\nNo missing values detected.\n")

    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        lines.append("\n## Numeric summary (describe)\n")
        lines.append(numeric.describe().to_markdown())

    outpath.write_text("\n".join(lines), encoding="utf-8")


def make_plot(df: pd.DataFrame, outpath: Path) -> None:
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        # No numeric columns → skip plotting
        return

    # Plot the first numeric column as a simple histogram
    col = numeric.columns[0]
    plt.figure()
    df[col].dropna().hist(bins=30)
    plt.title(f"Histogram: {col}")
    plt.xlabel(col)
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(outpath)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to input CSV")
    parser.add_argument("--outdir", required=True, help="Directory for outputs")
    args = parser.parse_args()

    inpath = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(inpath)

    write_report(df, outdir / "report.md")
    make_plot(df, outdir / "plot.png")


if __name__ == "__main__":
    main()
```

**4) 先在本機測試，再把 skill 打成 zip。**

在包含 `csv_insights_skill` 的目錄下，安裝相依套件並執行腳本：

```bash
python -m pip install -r csv_insights_skill/requirements.txt
python csv_insights_skill/run.py --input csv_insights_skill/assets/example.csv --outdir local-output
```

`local-output/report.md` 應該回報三列、三欄，以及一個 `quantity` 的缺失值。`local-output/plot.png` 應該是 `quantity` 的直方圖。

只打包 skill 的檔案，不要包含產生的輸出：

```bash
zip -r csv_insights_skill.zip csv_insights_skill/SKILL.md csv_insights_skill/requirements.txt csv_insights_skill/run.py csv_insights_skill/assets
```

**5) 上傳 skill（真的會送 API 請求）。**

準備好要建立 skill 時才執行這個指令。它會把回應存到 `skill.json`，供下一步使用。

```bash
curl --fail-with-body 'https://api.openai.com/v1/skills' \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F 'files=@./csv_insights_skill.zip;type=application/zip' \
  -o skill.json
```

**6) 透過 hosted shell 執行 skill（真的會送 API 請求）。**

設定 `RUN_SKILLS_API=1`，然後在跟 `skill.json` 同一個目錄下執行這段程式。它會固定使用上傳 skill 的預設版本，並分析 skill 內附的 CSV，不需要另外上傳 CSV。

Hosted shell 使用它已安裝的相依套件，對外網路預設是關閉的。skill 遇到缺少相依套件時會回報，不會自動開啟網路。可下載的產物請存在 `/mnt/data` 底下，詳見 [Shell guide](https://developers.openai.com/api/docs/guides/tools-shell#hosted-runtime-details)。

```python
import json
import os
from pathlib import Path

from openai import OpenAI

if os.environ.get("RUN_SKILLS_API") == "1":
    client = OpenAI()
    skill = json.loads(Path("skill.json").read_text())
    response = client.responses.create(
        model="gpt-6-astra",
        tools=[
            {
                "type": "shell",
                "environment": {
                    "type": "container_auto",
                    "skills": [
                        {
                            "type": "skill_reference",
                            "skill_id": skill["id"],
                            "version": str(skill["default_version"]),
                        }
                    ],
                },
            }
        ],
        input=(
            "Use the csv-insights skill to analyze its bundled assets/example.csv. "
            "Run the skill's run.py and write outputs to /mnt/data/csv-insights-output. "
            "Verify the row count and missing values, and link to report.md and plot.png."
        ),
    )
    print(response.output_text)
else:
    print("Skipped live API request. Set RUN_SKILLS_API=1 to run.")
```

**7) 要求一次 local shell call（選用，真的會送 API 請求）。**

Local shell 使用你上面建立的檔案，不用上傳，也不用引用 hosted skill。請在你的執行環境裡，從包含 `csv_insights_skill` 的目錄執行這段程式。

這段程式只會請求並顯示命令，不會執行它們，也不會完成分析。要完成整個流程，你的應用必須審查並在 sandbox 執行 `shell_call` 的命令、擷取 stdout、stderr 和結束狀態，再用對應的 `call_id` 回傳 `shell_call_output`，一直做到模型回傳最終答案為止。執行迴圈和輸出格式請看 [Local shell mode](https://developers.openai.com/api/docs/guides/tools-shell#local-shell-mode)。

```python
import os
from pathlib import Path

from openai import OpenAI

if os.environ.get("RUN_SKILLS_API") == "1":
    client = OpenAI()
    skill_path = Path("csv_insights_skill").resolve()
    response = client.responses.create(
        model="gpt-6-astra",
        tools=[
            {
                "type": "shell",
                "environment": {
                    "type": "local",
                    "skills": [
                        {
                            "name": "csv-insights",
                            "description": (
                                "Summarize a CSV, compute basic stats, and produce "
                                "a markdown report + a plot image."
                            ),
                            "path": str(skill_path),
                        }
                    ],
                },
            }
        ],
        input=(
            "Use the csv-insights skill to analyze its bundled assets/example.csv "
            "and write outputs to local-output."
        ),
    )
    for item in response.output:
        if item.type == "shell_call":
            print(item.action.commands)
    print(response.output_text)
else:
    print("Skipped live API request. Set RUN_SKILLS_API=1 to run.")
```

## 實務上的最佳做法

**1) 讓 skill 容易被「發現」**

* 在 frontmatter 放**清楚**的 `name` 和 `description`。
* 在 `SKILL.md` 寫上：什麼時候用、怎麼執行、預期輸出、注意事項。

- 加上明確的路由指引：「什麼時候用」對「什麼時候不要用」，再加幾個關鍵的邊界案例，全部寫在 `SKILL.md` 裡。

- 在正面範例旁邊，也放反面範例（skill 不該被觸發的情況），可以提高路由的準確度。

- 如果路由感覺不穩定，先調整 name、description 和範例，再考慮改程式碼。

這點來自「批次上傳」的討論：name 和 description 要來自 frontmatter，而且先用少量的 skill 測試。

**2) 優先用 zip 上傳，比較可靠也可重現**

* zip 好攜帶、容易做版本管理，上傳出問題時也是個好用的替代方法。

**3) 正式環境要固定版本**

你要能說「執行這個版本的流程」，而不是「執行最新的版本」。上傳的 skill 有 **default_version** 和 **latest_version** 兩個指標。用 `POST /v1/skills/{skill_id}/versions` 建立新版本，詳見[版本與管理](https://developers.openai.com/api/docs/guides/tools-skills#versioning-and-management)。

* 固定版本：`version: "2"`
* 跟著最新：`version: "latest"`
* 省略時：預設用 `default_version`

可以考慮把模型和 skill 版本一起固定，讓不同部署之間的行為可重現。

**4) 把 skill 設計成小型 CLI**

好的 skill 腳本：

* 能從命令列執行
* 印出確定性的 stdout
* 失敗時明確報錯，附上用法或錯誤訊息
* 需要時把輸出寫到固定的檔案路徑

在 skill 裡加入具體的模板和實作範例（輸入、命令、預期輸出）。模型呼叫 skill 時會讀這些細節，而探索用的 metadata 則仍屬於輸入 context 的一部分。如果範例是針對特定工作流程的，優先把範例和模板放在 skill 裡，而不是系統層級的 few-shot prompting。

**5) 不要在 system prompt 裡重複 skill 的內容**

如果 system prompt 重複了整個流程，大家就會：

* 繞過 skill
* 把邏輯塞進 tool schema

這樣 skill 的意義（可重用、有版本、按條件呼叫）就沒了。system prompt 的內容要和 skill 分開。

**6) 網路存取**

把 skill 和開放的網路存取合在一起風險很高。如果非用網路不可，要使用嚴格的允許清單，並把 tool 輸出當成不可信。面向消費者、使用者期待有確認機制的應用，要避免這種組合。
**如果需要網路存取，要把允許清單搭配明確的「哪些資料可以離開」指引。**

**7) 使用能可靠執行多步驟流程的模型**

skill 在模型擅長長 context 推理和多步驟 tool 執行（瀏覽檔案系統、執行 CLI、驗證）時效果最好。
如果看到只做一半或執行很脆弱，就換更強的模型或簡化流程，並在 `SKILL.md` 加入明確的驗證步驟和輸出檢查。

**限制與驗證**

- `SKILL.md` 的比對不分大小寫
- 只允許一個 manifest 檔（`skill.md` 或 `SKILL.md`）
- Frontmatter 驗證遵循 Agent Skills 規格（name 欄位）
- zip 上傳大小上限：50 MB
- 每個 skill 版本的檔案數上限：500
- 解壓縮後單一檔案大小上限：25 MB

## 結論

skill 是 prompt 和 tool 之間缺的那個「中間層」：**prompt** 定義隨時生效的行為，**tool** 提供原子化的能力和副作用，**skill** 則把可重複的流程（指示、腳本、資源）打包起來，讓模型**只在需要時才掛載並執行。**

**用 skill 讓 system prompt 保持精簡、工作流程耐用。** 從小處開始，把一個穩定的流程打包，配上清楚的 `SKILL.md`，讓它能當小型 CLI 執行，然後上線。上線之後，固定版本以確保可重現，用發布新版本的方式安全地迭代，並把你的 skill 庫當成內部的標準函式庫：經過稽核、容易找到、跨 agent 共用。

當使用者從單輪的助理擴展到長時間運作的 agent，skill 能把「prompt 義大利麵」變成**可維護、可測試、有版本的工作流程**，讓你建出可以信任、重用並隨時間演進的 agent 行為。

要開始使用 Skills，請看我們的[文件](https://developers.openai.com/api/docs/guides/tools-skills)。

## 重點整理

- skill 是以 `SKILL.md` 為核心的檔案 bundle，模型只在需要時才讀取並執行。
- system prompt 放全域行為，tool 放副作用和即時資料，skill 放可重複的流程。
- name 和 description 來自 frontmatter，路由好不好，主要看這兩個欄位和 `SKILL.md` 裡的使用時機說明。
- 正式環境要固定 skill 版本（必要時連模型一起固定），並優先用 zip 上傳。
- skill 腳本要像小型 CLI：輸出確定、失敗明確，網路存取預設關閉。

## 練習

1. 把範例 `example.csv` 多加幾列資料，重跑本機測試，確認 `report.md` 的列數和缺失值有跟著變。
2. 修改 `SKILL.md` 的 description，加上「Don't use when」的反面範例，看看路由行為有沒有改變。
3. 改 `run.py`，讓它額外對另一個數值欄位畫直方圖，並更新 `SKILL.md`，再上傳成新版本，用 `version` 固定在新版本重跑 hosted shell。
