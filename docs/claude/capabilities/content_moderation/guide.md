---
translated: true
source: capabilities/content_moderation/guide.ipynb
---
# 用 Claude 落實內容政策

> 原文：[capabilities/content_moderation/guide.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/content_moderation/guide.ipynb)

把書面的內容政策編譯成確定性的 JSON 規則，從文字和圖片抽取有型別的欄位，再由完全不呼叫模型的規則引擎產生可稽核的判定。

## 這篇在做什麼

做一條內容審核 pipeline：Claude 負責把政策文字編譯成 JSON 規則，以及從內容（含圖片）抽取欄位，真正下判定的是一個純函式的規則引擎。這樣同樣的輸入一定得到同樣的結果，而且每個判定都有逐條 assertion 的稽核軌跡。最後用同一套程式碼跑三個領域，並用有標註的樣本量測準確度。

## 學完你會

- 設計一份 extraction schema，讓欄位描述同時是抽取指示和編譯依據，並用 context schema 放平台已知的資訊。
- 寫出帶 scope 和三值邏輯的 JSON 規則，用 validator 驅動的 repair loop 編譯政策，還能把「看起來未滿 25 歲」這種條件做成 LLM assertion。
- 用一句白話新增規則、換領域重跑，並用標註樣本做 extraction eval。

## 開跑前

- Python 3.10+ 和 Anthropic API key（放在環境變數或 `.env` 的 `ANTHROPIC_API_KEY`）
- 會真的呼叫 API，預設約 10 到 15 分鐘、約一美元；設 `RUN_FULL_EVAL=1`（Step 10）會再加倍
- 資料放在 notebook 旁邊的 `data/<domain>/`，引擎和兩個 Claude 階段在同目錄的 `engine.py` 和 `pipeline.py`

內容審核是在內容發布前，先對照書面政策檢查，再決定怎麼處理：發布、拒絕，或交給人工審核。內容可以來自任何地方：使用者留言、賣家商品刊登、廣告素材、必須經過法務放行的行銷活動。政策是由政策、法務或品牌團隊用白話寫成的，而內容進來的速度比任何審核團隊讀得完的速度都快。負責這個流程的人都面對同一個矛盾：**政策是人用文字寫的，但執行需要一致、便宜、可稽核。**

這份指南會建立一條內容審核 pipeline，由 Claude 把書面政策編譯成確定性、可稽核的規則。你會編譯一份貼近實況的廣告放行政策，從內容（包括廣告圖片）抽取有型別的欄位，由完全不呼叫模型的規則引擎產生判定，然後把同一條 pipeline 跑在三個領域，並用有標註的樣本來衡量。

> **這個 notebook 的所有資料都是合成的。** 公司、品牌、政策和廣告圖片都是為這份指南編的。裡面的規則是為了說明模式，並不代表真實的廣告或審核要求，請不要當成合規依據。

## 你會學到

- 設計一份抽取 schema，讓欄位描述同時是抽取指示
- 一個帶有 **scope** 和三值邏輯的小型 JSON 規則語言
- 用 **validator 驅動的 repair loop** 編譯政策文字
- **LLM assertion**：把「不能有看起來未滿 25 歲的人」這類規則，做成由模型判斷的欄位
- 用 structured outputs 抽取，包括從圖片抽取
- 用一句白話新增一條規則
- 在三個領域用標註樣本做評估

## 先決條件

- Python 3.10+ 和 Anthropic API key（環境變數或 `.env` 裡的 `ANTHROPIC_API_KEY`，setup cell 會載入）。
- 資料跟 notebook 放在一起（`data/<domain>/`）：schema、政策文件、標註樣本，以及合成的廣告圖片（品牌都是虛構的，用 Pillow 產生，所以 ground-truth 標註天生正確）。

引擎和兩個 Claude 階段放在 notebook 旁邊的 `engine.py` 和 `pipeline.py`。指南會 import 它們，並展示值得讀的部分。如果你是在 cookbook 網站上讀，完整檔案在 GitHub：
[engine.py](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/content_moderation/engine.py) 和 [pipeline.py](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/content_moderation/pipeline.py)。

**成本和執行時間。** 這個 notebook 會真的呼叫 API：預設大約 10 到 15 分鐘、約一美元；`RUN_FULL_EVAL=1`（Step 10）會再加倍。已存的輸出來自完整執行，所以你也可以只讀不跑。

在 Colab 上執行的話，API key 放在 Colab 的 Secrets（左側的鑰匙圖示），資料檔要從 GitHub 把 `data/` 和兩個 `.py` 檔一起上傳或 clone 下來。


## 整體做法

最直覺的 LLM 做法是把政策貼進 prompt，請模型給判定。demo 時行得通，但到了正式環境的量就會出問題：

| 用 prompt 下判定 | 正式環境需要的 |
|---|---|
| 同樣的內容在不同次執行可能得到不同判定 | 相同輸入，相同決定 |
| 拒絕的理由是模型當下隨便生成的文字 | 證據軌跡：規則、assertion、預期值 vs. 實際值 |
| 政策變更就是一次無法審查的 prompt 修改 | 有版本、可 diff、可重播的規則檔 |

這份 cookbook 重新設計問題，讓 Claude 只出現在兩個地方，而且 **從不決定判定結果**：


```python
from IPython.display import Image

Image("images/architecture.png")
```

1. **Schema**（你寫）：關於一則內容，所有可以被知道的有型別欄位。
2. **Compiler**（Claude，每次政策變更跑一次）：把每條政策條文轉成針對這些欄位的規則，並用靜態 validator 檢查。
3. **Extractor**（Claude，每則內容跑一次）：一次呼叫就把文字和圖片讀成有型別的欄位。
4. **Engine**（沒有模型）：把規則套用到欄位上。相同輸入、相同判定，並附帶逐條 assertion 的稽核軌跡。

規則引擎一直都值得信任；它們一直缺的，是像政策人員那樣讀政策、像審核員那樣讀內容的能力。這部分由 Claude 補上。

範例是一間虛構媒體網路 **Northwind** 的廣告素材放行。另外兩個領域，市集商品刊登和社群內容，用的是完全相同的程式碼。


```python
%%capture
%pip install -U "anthropic>=2.0.0" python-dotenv

import json
import pathlib

from dotenv import load_dotenv

load_dotenv()

from engine import evaluate, validate_document
from pipeline import compile_policies, compile_single_rule, extract_fields

DATA = pathlib.Path("data")


def show(obj, limit=2000):
    s = json.dumps(obj, indent=2)
    print(s[:limit] + ("\n… (truncated)" if len(s) > limit else ""))
```

## Step 1：定義抽取 schema

整條 pipeline 都建立在 schema 上，所以從這裡開始。schema 是模型和規則引擎之間的契約：關於一則內容可以被知道的全部事實。有兩個設計重點比什麼都重要：

- **欄位描述身兼兩職。** 它們是 Claude 執行時遵循的抽取指示，也是 compiler 用來判斷某條政策條文對應哪個欄位的依據。寫的時候想像你在對一位謹慎的審核員下指示。
- **欄位可以刻意允許 null。** 像 `apr_disclosed` 這種欄位是 `boolean | null`，因為「看不出來」是合理的答案，引擎對它的處理也跟 `false` 不同（下面會講三值邏輯）。

欄位同時包含客觀事實（`price_or_rate_shown`）和有範圍限制的判斷（`text_coverage`）。要允許多少判斷，是在 schema 這裡決定的。


```python
schema = json.loads((DATA / "ad_creatives" / "schema.json").read_text())

for name, spec in schema["properties"].items():
    t = " | ".join(spec["type"]) if isinstance(spec["type"], list) else spec["type"]
    t = f"enum[{', '.join(spec['enum'])}]" if "enum" in spec else t
    print(f"{name:<36} {t}")
print(f"\n{len(schema['properties'])} fields")
```

??? note "輸出"

    ```text
    ad_category                          enum[alcohol, gambling, financial_services, pharma_supplements, weight_loss, cosmetics_skincare, apparel_footwear, electronics, food_beverage, other]
    brand_name                           string | null
    headline_text                        string
    disclaimer_present                   boolean
    disclaimer_text                      string | null
    age_gate_shown                       integer | null
    text_coverage                        enum[low, medium, high]
    before_after_imagery                 boolean
    superlative_claims                   array
    health_claim_present                 boolean
    price_or_rate_shown                  boolean
    apr_disclosed                        boolean | null
    people_depicted                      boolean
    depicted_person_apparent_minor       boolean | null
    competitor_reference                 boolean
    landing_url_domain                   string | null
    target_min_age                       integer | null

    17 fields
    ```

### context schema

規則需要的東西，不是都能從內容本身讀出來。廣告會在哪裡投放、走哪個通路、廣告主是代管還是自助：你的平台在任何審核開始前就已經知道這些。它們是關於投放位置的事實，不是內容的事實。

這些放在第二份比較小的 schema，叫 **context schema**。你的程式碼在要求判定時把它們傳進來，完全不會對它們做抽取。在 Step 2 會看到規則怎麼限定在特定 context，像「只限 New Jersey」。


```python
context_schema = json.loads((DATA / "ad_creatives" / "context.json").read_text())
show({k: v.get("enum", v["type"]) for k, v in context_schema["properties"].items()})
```

??? note "輸出"

    ```text
    {
      "country": "string",
      "state": [
        "string",
        "null"
      ],
      "channel": [
        "display",
        "social",
        "video",
        "email"
      ],
      "advertiser_tier": [
        "managed",
        "self_serve"
      ]
    }
    ```

## Step 2：規則語言

在請 Claude 編譯任何東西之前，先看它需要產出什麼。編譯後的規則集是一份 JSON 文件：

```json
{
  "derived_fields": { /* LLM-judged booleans the compiler needed, see Step 4 */ },
  "rules": [
    {
      "id": "5.1_nj_gambling_helpline",
      "policy_ref": "5.1",
      "policy_text": "Gambling creatives running in New Jersey must display the 1-800-GAMBLER helpline.",
      "action": "block",                       // block = reject; flag = human review
      "scope": {                               // WHERE the rule applies (context ∪ fields)
        "all": [
          {"field": "state", "op": "eq", "value": "NJ"},
          {"field": "ad_category", "op": "eq", "value": "gambling"}
        ]
      },
      "when": {                                // the VIOLATION (fields only)
        "not": {"field": "disclaimer_text", "op": "regex", "value": "1-800-GAMBLER"}
      }
    }
  ],
  "uncompilable": [ /* clauses that map to no field and no judgment; surfaced, not dropped */ ]
}
```

條件用 `all` / `any` / `not` 組合葉節點 assertion（`eq, neq, gt, gte, lt, lte, in, not_in, contains, not_contains, regex, exists`）。有三個設計選擇很重要：

- **`when` 代表違規**（規則觸發就是違反政策），跟 linter 和防火牆規則的慣例一樣。trace 會寫成「因為 X 而觸發」。
- **scope 和違規分開。**「酒類廣告必須有警語」其實是兩句話：*對誰*，以及 *什麼是錯的*。scope 也可以讀取抽取永遠不可能知道的投放 context。
- **三值邏輯。** 缺少的值會被評估成 *unknown*，而一條本來會觸發、但無法確認的規則，會給出 `needs_review`，而不是一個有把握的判定。


## Step 3：規則引擎

現在是下判定的部分。引擎（`engine.py`，約 200 行）是 `(rules, fields, context)` 的純函式，沒有模型也沒有 I/O。這部分可以讓你的合規團隊做單元測試，也是兩則相同內容不可能得到不同判定的原因。它的核心：

```python
def evaluate_rule(rule, fields, context=None):
    rr = RuleResult(rule["id"], rule.get("action", "flag"), "clear")
    if "scope" in rule:
        rr.scope_result = _eval(rule["scope"], {**fields, **(context or {})}, rr.scope_trace)
        if rr.scope_result is False:
            rr.outcome = "out_of_scope"
            return rr
    w = _eval(rule["when"], fields, rr.trace)
    if rr.scope_result is None:  # can't confirm applicability: only a definite pass is safe
        rr.outcome = "clear" if w is False else "unknown"
    else:
        rr.outcome = "fired" if w is True else "clear" if w is False else "unknown"
    return rr

def evaluate(rules, fields, context=None):
    results = [evaluate_rule(r, fields, context) for r in rules]
    fired   = [r for r in results if r.outcome == "fired"]
    unknown = [r for r in results if r.outcome == "unknown"]
    if any(r.action == "block" for r in fired): decision = "block"
    elif fired:                                 decision = "flag"
    elif unknown:                               decision = "needs_review"
    else:                                       decision = "approve"
    ...
```

`_eval` 走訪條件樹，把每個 assertion 加進 trace（連同它的 `all`/`any`/`not` 結構），並像 SQL 傳遞 null 那樣傳遞 unknown。[engine.py](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/content_moderation/engine.py) 裡還有 `validate_document`，也就是 Step 5 compiler 的 repair loop 用的靜態檢查器。


### 試玩

目前還沒有用到模型，所以可以直接玩引擎。手寫一條規則和一個 fields dict，看 trace，包括某個值是 `null` 時，以及 context 改變 scope 時會怎樣。


```python
demo_rules = [
    {
        "id": "bonus_cap_flag",
        "policy_text": "Sign-up bonuses over $1000 are flagged for review.",
        "action": "flag",
        "when": {"field": "bonus_amount_usd", "op": "gt", "value": 1000},
    },
    {
        "id": "nj_bonus_cap_block",
        "policy_text": "In New Jersey, sign-up bonuses over $1000 are blocked.",
        "action": "block",
        "scope": {"field": "state", "op": "eq", "value": "NJ"},
        "when": {"field": "bonus_amount_usd", "op": "gt", "value": 1000},
    },
]

fields = {"bonus_amount_usd": 1500}

print("── California:")
print(evaluate(demo_rules, fields, {"state": "CA"}).explain())
print("\n── New Jersey — same fields, different scope:")
print(evaluate(demo_rules, fields, {"state": "NJ"}).explain())
print("\n── Bonus amount unreadable (null) — three-valued logic routes to review:")
print(evaluate(demo_rules, {"bonus_amount_usd": None}, {"state": "NJ"}).explain())
```

??? note "輸出"

    ```text
    ── California:
    DECISION: FLAG
      ✗ [flag] bonus_cap_flag
          T  bonus_amount_usd gt 1000  (actual: 1500)
      – out of scope: nj_bonus_cap_block

    ── New Jersey — same fields, different scope:
    DECISION: BLOCK
      ✗ [flag] bonus_cap_flag
          T  bonus_amount_usd gt 1000  (actual: 1500)
      ✗ [block] nj_bonus_cap_block
          scope:
            T  state eq 'NJ'  (actual: 'NJ')
          T  bonus_amount_usd gt 1000  (actual: 1500)

    ── Bonus amount unreadable (null) — three-valued logic routes to review:
    DECISION: NEEDS_REVIEW
      ? [flag] bonus_cap_flag  — could not determine: bonus_amount_usd
      ? [block] nj_bonus_cap_block  — could not determine: bonus_amount_usd
    ```

## Step 4：LLM assertions

到目前為止，引擎只會比較值。但有些政策條文沒辦法化簡成對可抽取事實的比較：*「酒類廣告素材不得出現任何看起來未滿 25 歲的人。」* 沒有哪個欄位在講這件事。在引擎裡呼叫模型會毀掉我們剛建好的一切，所以 compiler 改成 **製造一個欄位**：一個 `derived_fields` 項目，它的 `judge` 指示是一個精確的是非題，之後像其他欄位一樣被引用：

```json
"derived_fields": {
  "depicted_person_apparent_under_25": {
    "type": ["boolean", "null"],
    "judge": "True if any person depicted appears to be under 25. Null if no people or indeterminate.",
    "source_policy": "1.1"
  }
},
// rule: {"all": [{"field": "people_depicted", "op": "eq", "value": true},
//                {"field": "depicted_person_apparent_under_25", "op": "eq", "value": true}]}
```

這個判斷是在跟其他欄位同一次抽取呼叫中回答的，所以引擎仍然是純的，而 `null` 仍然會導向人工審核。注意上面的 `people_depicted` 閘門：判斷類的規則要先通過前提條件，這樣「廣告裡沒有人」時，規則會評估成 *clear*，不會把每張風景照都送去審核。

compiler 會依序嘗試：先用現有欄位加運算子，再用衍生的判斷欄位，最後才是 `uncompilable`（用在需要外部資料的條文，像博弈執照登記的查詢）。


## Step 5：編譯政策文件

有了 schema、規則語言和引擎，就能編譯真正的政策了。它是照政策團隊實際的寫法寫的：給人讀的條文文字。編譯前先讀一遍，注意條文 1.1 的未滿 25 歲那行（需要判斷）、條文 1.2 的執照那行（uncompilable），以及第 5 節的地區規則（scope）。


```python
policies = (DATA / "ad_creatives" / "policies.md").read_text()
print(policies)
```

??? note "輸出"

    ```text
    # Ad Creative Acceptance Policy — Northwind Media Network

    *Written the way a policy team actually writes: prose, for humans. The compiler's job is to turn each numbered clause into one or more machine-checkable rules over the extraction schema — and to say so explicitly when a clause can't be reduced to the available fields.*

    ## 1. Restricted categories

    1.1 **Alcohol.** Alcohol advertising is accepted only when audience targeting is set to 21+ and the creative carries a responsible-drinking message (e.g. "Drink Responsibly", "Enjoy Responsibly"). Alcohol creatives must not depict anyone who appears to be under 25.

    1.2 **Gambling & betting.** Must target 18+ (21+ preferred), must display an age badge in the creative, and must include a problem-gambling helpline or "gamble responsibly" style message. Claims of guaranteed winnings or "risk-free" bets are prohibited outright. Gambling advertisers must hold a valid gaming license in every state the campaign targets.

    1.3 **Financial services.** Any ad that shows an interest rate, monthly payment, or promotional credit offer must state a representative APR in the creative. "Guaranteed approval" and similar language is not permitted.

    1.4 **Weight loss, supplements & pharma.** Before/after body or skin comparison imagery is not permitted in any category. Ads must not claim to treat, cure, or prevent a medical condition. Weight-loss ads may not target under-18s.

    ## 2. Claims & substantiation

    2.1 Superlatives and absolutes ("#1", "best", "guaranteed", "instant", "miracle", "risk-free") require substantiation we can't verify at review time — flag any creative using them for manual review rather than rejecting.

    2.2 Comparative advertising that names or shows a competitor brand is flagged for legal review.

    ## 3. Creative quality

    3.1 Text overlay should be kept minimal. Creatives where text covers a high proportion of the image are rejected; medium coverage is flagged with a recommendation to reduce.

    3.2 Every creative must clearly identify the advertiser — a brand name or logo must be visible.

    ## 4. Audience safety

    4.1 If targeting metadata leaves minimum age unset, treat the ad as reaching all ages: restricted categories (alcohol, gambling, weight loss, financial services) are then rejected regardless of creative content.

    4.2 Creatives depicting apparent minors are not permitted in alcohol, gambling, weight-loss, or cosmetics/skincare categories.

    ## 5. Regional & channel requirements

    5.1 **New Jersey.** Gambling creatives running in New Jersey must display the 1-800-GAMBLER helpline number in the creative.

    5.2 **Email.** Alcohol and gambling creatives may not run in the email channel at all.

    5.3 **Self-serve accounts.** Financial-services ads from self-serve advertisers are always flagged for manual review, even when otherwise compliant.
    ```

compiler 的 prompt 帶著 schema、context schema，以及含六條編譯規則的規則格式規格（把 scope 和違規分開；一條列出多個值的條文編成一條 `in` 規則，不要複製成多條；多個要求編成多條規則；優先用運算子，再用衍生欄位，最後才 `uncompilable`；絕不發明欄位）。

讓它適合上線的部分是 `pipeline.compile_policies` 裡的 **repair loop**：`validate_document` 對輸出做靜態檢查，任何問題（發明的欄位、不在集合內的 enum 值、洩漏到 `when` 裡的 context key）都會當成只能修正的一輪送回給 Claude。幻覺碰到 validator 就活不下去。

```python
for round_no in range(max_repair_rounds + 1):
    doc = _parse_json_reply(claude_reply(messages))
    problems = validate_document(doc, schema, context_schema)
    if not problems:
        return doc, attempts
    messages += [assistant(reply), user("Fix ONLY these problems: " + json.dumps(problems))]
```


```python
compiled, attempts = compile_policies(policies, schema, context_schema)

for a in attempts:
    status = "clean" if not a["problems"] else json.dumps(a["problems"])
    print(f"round {a['round']}: {status}")
print(
    f"\n{len(compiled['rules'])} rules · {len(compiled.get('derived_fields', {}))} derived fields · "
    f"{len(compiled.get('uncompilable', []))} uncompilable"
)
print("\nrule ids:", ", ".join(r["id"] for r in compiled["rules"]))
print("\nderived fields:")
for name, spec in compiled.get("derived_fields", {}).items():
    print(f"  {name}: {spec['judge'][:110]}")
print("\nuncompilable:")
for u in compiled.get("uncompilable", []):
    print(f"  [{u['policy_ref']}] {u['policy_text'][:80]}… → {u['reason'][:100]}")
```

??? note "輸出"

    ```text
    round 0: clean

    22 rules · 6 derived fields · 2 uncompilable

    rule ids: 1.1a_alcohol_targeting_21, 1.1b_alcohol_responsible_message, 1.1c_alcohol_no_under_25, 1.2a_gambling_targeting_18, 1.2b_gambling_age_badge, 1.2c_gambling_responsible_message, 1.2d_gambling_no_guaranteed_or_risk_free, 1.3a_financial_apr_required, 1.3b_financial_no_guaranteed_approval, 1.4a_no_before_after_imagery, 1.4b_no_medical_claims, 1.4c_weight_loss_targeting_18, 2.1_superlatives_review, 2.2_competitor_reference_review, 3.1a_text_coverage_high, 3.1b_text_coverage_medium, 3.2_advertiser_identified, 4.1_restricted_unset_min_age, 4.2_no_minors_restricted_categories, 5.1_nj_gambling_helpline, 5.2_no_alcohol_gambling_email, 5.3_self_serve_financial_review

    derived fields:
      responsible_drinking_message_present: Look at the creative image, headline, and body copy. Answer true if any of them carries a responsible-drinking
      depicted_person_apparent_under_25: If the creative shows one or more real-looking people, answer true if any of them appears to be under 25 years
      responsible_gambling_message_present: Look at the creative image, headline, and body copy. Answer true if they include a problem-gambling helpline (
      guaranteed_winnings_or_risk_free_bet_claim: Look at the headline, body copy, and image text. Answer true if the ad claims or implies guaranteed winnings, 
      credit_terms_shown: Look at the headline, body copy, and image text. Answer true if the ad shows any of the following: an interest
      guaranteed_approval_claim: Look at the headline, body copy, and image text. Answer true if the ad states or implies that credit, loan, or

    uncompilable:
      [1.2] Gambling advertisers must hold a valid gaming license in every state the campaig… → Checking this requires an external lookup of the advertiser's gaming licenses against a state licens
      [1.2] Must target 18+ (21+ preferred).… → The '21+ preferred' part is a stated preference, not a requirement, so there is no violation to chec
    ```

### validator 會抓到什麼

要看 repair loop 在防什麼，可以用三種方式弄壞一條規則再驗證。實際編譯時，這些一模一樣的訊息會送回給 Claude 去修。


```python
broken = {
    "derived_fields": {},
    "rules": [
        {
            "id": "bad1",
            "action": "block",
            "when": {"field": "creative_has_disclamer", "op": "eq", "value": True},
        },  # invented field
        {
            "id": "bad2",
            "action": "block",
            "when": {"field": "ad_category", "op": "eq", "value": "liquor"},
        },  # not in the enum
        {
            "id": "bad3",
            "action": "block",
            "scope": {"field": "ad_category", "op": "eq", "value": "gambling"},
            "when": {"field": "state", "op": "eq", "value": "NJ"},
        },  # context key in `when`
    ],
}
show(validate_document(broken, schema, context_schema))
```

??? note "輸出"

    ```text
    {
      "bad1": [
        "bad1.when: unknown field 'creative_has_disclamer' (available: ['ad_category', 'age_gate_shown', 'apr_disclosed', 'before_after_imagery', 'brand_name', 'competitor_reference', 'depicted_person_apparent_minor', 'disclaimer_present', 'disclaimer_text', 'headline_text', 'health_claim_present', 'landing_url_domain', 'people_depicted', 'price_or_rate_shown', 'superlative_claims', 'target_min_age', 'text_coverage'])"
      ],
      "bad2": [
        "bad2.when: 'liquor' not in enum for 'ad_category': ['alcohol', 'gambling', 'financial_services', 'pharma_supplements', 'weight_loss', 'cosmetics_skincare', 'apparel_footwear', 'electronics', 'food_beverage', 'other']"
      ],
      "bad3": [
        "bad3.when: unknown field 'state' (available: ['ad_category', 'age_gate_shown', 'apr_disclosed', 'before_after_imagery', 'brand_name', 'competitor_reference', 'depicted_person_apparent_minor', 'disclaimer_present', 'disclaimer_text', 'headline_text', 'health_claim_present', 'landing_url_domain', 'people_depicted', 'price_or_rate_shown', 'superlative_claims', 'target_min_age', 'text_coverage'])"
      ]
    }
    ```

### 跟手寫規則集比較

`rules.golden.json` 是我們手寫的同一份政策的編譯結果。編譯出來的版本通常涵蓋相同的條文，但常常更依賴衍生欄位（用語意判斷「有負責任飲酒的訊息」，而不是脆弱的 `regex`）。這可以說更好，但會讓更多面向落在模型判斷上；這個取捨由你來審查，正是規則做成檔案的意義。

**這個 notebook 接下來都用 golden 規則集**，讓每次執行的結果可重現；想用你自己編的，就換成 `compiled`。


```python
golden = json.loads((DATA / "ad_creatives" / "rules.golden.json").read_text())
assert not validate_document(golden, schema, context_schema)

g_refs = {r["policy_ref"] for r in golden["rules"]}
c_refs = {r.get("policy_ref") for r in compiled["rules"]}
print("clause coverage — golden:", sorted(g_refs))
print(
    "missing vs golden:",
    sorted(g_refs - c_refs) or "none",
    "· extra:",
    sorted(c_refs - g_refs) or "none",
)

active = golden  # ← the ruleset used below
```

??? note "輸出"

    ```text
    clause coverage — golden: ['1.1', '1.2', '1.3', '1.4', '2.1', '2.2', '3.1', '3.2', '4.1', '4.2', '5.1', '5.2', '5.3']
    missing vs golden: none · extra: none
    ```

## Step 6：從內容抽取欄位

規則有了，現在需要欄位來套用，這就是抽取（`pipeline.extract_fields`）：每則內容一次 Claude 呼叫。這個呼叫會隨量放大，所以用 Sonnet，編譯（每次政策變更一次）則用 Opus。輸出 schema 是抽取 schema 加上規則集的判斷欄位，用 **structured outputs** 強制執行，所以欄位回來時是有型別的：

```python
response = _client().messages.create(
    model=EXTRACTOR_MODEL,
    system="You extract facts. You decide nothing about policy; report only what you observe.",
    messages=[{"role": "user", "content": [image_block, {"type": "text", "text": prompt}]}],
    output_config={"format": {"type": "json_schema",
                              "schema": build_extraction_schema(schema, derived_fields)}},
)
```

衍生的判斷是描述以 `JUDGMENT:` 開頭的欄位，跟著一起回來，`null` 代表「真的看不出來」，絕不是「懶得判斷」。完整原始碼：
[pipeline.py](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/content_moderation/pipeline.py)。


拿一張合成的運動博弈廣告素材來跑。所有跟政策有關的東西都是在合成圖片時刻意放進去的：一個 **$1,500** 的獎金數字、一個 **21+** 徽章，還有一條小字，寫著 *"Gamble Responsibly."*，但 **沒有** New Jersey 要求的 1-800-GAMBLER 協助專線。


```python
from IPython.display import Image as IPImage
from IPython.display import display

img_path = DATA / "ad_creatives" / "images" / "betpeak_bonus.png"
display(IPImage(str(img_path), width=380))

submission = {
    "headline": "Get up to $1,500 in bonus bets",
    "body": "New BetPeak members get up to $1,500 in bonus bets on signup. 21+.",
    "brand": "BetPeak",
    "targeting": {"min_age": 21, "geo": "US-NJ"},
}
fields = extract_fields(submission, schema, active.get("derived_fields", {}), image_path=img_path)
show(fields)
```

??? note "輸出"

    ```text
    {
      "ad_category": "gambling",
      "brand_name": "BetPeak",
      "headline_text": "Get up to $1,500 in bonus bets",
      "disclaimer_present": true,
      "disclaimer_text": "Gamble Responsibly.",
      "age_gate_shown": 21,
      "text_coverage": "low",
      "before_after_imagery": false,
      "superlative_claims": [],
      "health_claim_present": false,
      "price_or_rate_shown": true,
      "apr_disclosed": null,
      "people_depicted": false,
      "depicted_person_apparent_minor": null,
      "competitor_reference": false,
      "landing_url_domain": null,
      "target_min_age": 21,
      "depicted_person_apparent_under_25": null
    }
    ```

## Step 7：評估

欄位抽出來了，規則編好了：判定現在只是一次函式呼叫。每條觸發的規則都會指出它對應的政策條文，每個 assertion 都顯示預期值 vs. 實際值。而且因為評估是免費的，**改變投放 context 不需要再呼叫模型**：同一組欄位，分別用 New Jersey 和 California 評估會得到不同判定，而且原因你都指得出來。


```python
print("── New Jersey placement:")
print(
    evaluate(
        active["rules"],
        fields,
        {"country": "US", "state": "NJ", "channel": "display", "advertiser_tier": "managed"},
    ).explain()
)

print("\n── Same fields, California placement — zero model calls:")
print(
    evaluate(
        active["rules"],
        fields,
        {"country": "US", "state": "CA", "channel": "display", "advertiser_tier": "managed"},
    ).explain()
)
```

??? note "輸出"

    ```text
    ── New Jersey placement:
    DECISION: BLOCK
      ✗ [block] 5.1_nj_gambling_helpline
          scope:
            T  all:
              T  state eq 'NJ'  (actual: 'NJ')
              T  ad_category eq 'gambling'  (actual: 'gambling')
          T  any:
            F  disclaimer_present eq False  (actual: True)
            T  not:
              F  disclaimer_text regex '1-800-GAMBLER'  (actual: 'Gamble Responsibly.')
      – out of scope: 1.1a_alcohol_targeting_21, 1.1b_alcohol_responsible_message, 1.1c_alcohol_no_under_25, 1.3a_finance_apr_required, 1.3b_finance_no_guaranteed_approval, 1.4c_weight_loss_targeting_18, 5.2_no_alcohol_gambling_email, 5.3_self_serve_finance_review

    ── Same fields, California placement — zero model calls:
    DECISION: APPROVE
      – out of scope: 1.1a_alcohol_targeting_21, 1.1b_alcohol_responsible_message, 1.1c_alcohol_no_under_25, 1.3a_finance_apr_required, 1.3b_finance_no_guaranteed_approval, 1.4c_weight_loss_targeting_18, 5.1_nj_gambling_helpline, 5.2_no_alcohol_gambling_email, 5.3_self_serve_finance_review
      ✓ all 13 applicable rules clear
    ```

## Step 8：用白話新增規則

政策變更很少是以重寫的文件形式出現，通常是政策團隊的一句話。`pipeline.compile_single_rule` 用同樣的 compiler 模式，一次處理一條條文：針對 schema 編譯這句話（適合的話重用既有的衍生欄位），用同一個 repair loop 驗證，再把新增的內容附加成規則集的 **新版本**。注意，一句話可以合理地編成 *好幾條* 規則（一般情況標記，但在某一州則直接封鎖），而且 compiler 被告知不可合併或丟掉任何一部分。


```python
addition = compile_single_rule(
    "Sign-up bonus offers greater than $1000 must be flagged for review, "
    "and in New Jersey they are blocked outright.",
    active,
    schema,
    context_schema,
)
show(addition)

# Append as a new ruleset version (never edit in place; rulesets are versioned artifacts)
active_v2 = {
    "derived_fields": {**active["derived_fields"], **addition["derived_fields"]},
    "rules": active["rules"] + addition["rules"],
    "uncompilable": active.get("uncompilable", []),
}
assert not validate_document(active_v2, schema, context_schema)
print(f"\nruleset v2: {len(active_v2['rules'])} rules")
```

??? note "輸出"

    ```text
    {
      "rules": [
        {
          "id": "custom_signup_bonus_over_1000_review",
          "policy_ref": "custom",
          "policy_text": "Sign-up bonus offers greater than $1000 must be flagged for review.",
          "action": "flag",
          "uses_llm_fields": true,
          "scope": {
            "not": {
              "field": "state",
              "op": "eq",
              "value": "NJ"
            }
          },
          "when": {
            "field": "signup_bonus_over_1000",
            "op": "eq",
            "value": true
          }
        },
        {
          "id": "custom_signup_bonus_over_1000_nj_block",
          "policy_ref": "custom",
          "policy_text": "Sign-up bonus offers greater than $1000 are blocked outright in New Jersey.",
          "action": "block",
          "uses_llm_fields": true,
          "scope": {
            "field": "state",
            "op": "eq",
            "value": "NJ"
          },
          "when": {
            "field": "signup_bonus_over_1000",
            "op": "eq",
            "value": true
          }
        }
      ],
      "derived_fields": {
    ... (省略 12 行)
    ```

BetPeak 的素材宣傳 $1,500 的獎金，所以新規則應該抓得到。先前跑的抽取裡沒有這個衍生判斷，所以要針對 v2 的衍生欄位重新抽取，再評估。注意 California 是標記，New Jersey 是封鎖。


```python
fields_v2 = extract_fields(submission, schema, active_v2["derived_fields"], image_path=img_path)
print("── New Jersey, ruleset v2:")
print(
    evaluate(
        active_v2["rules"],
        fields_v2,
        {"country": "US", "state": "NJ", "channel": "display", "advertiser_tier": "managed"},
    ).explain()
)
```

??? note "輸出"

    ```text
    ── New Jersey, ruleset v2:
    DECISION: BLOCK
      ✗ [flag] 3.1b_text_coverage_medium
          T  text_coverage eq 'medium'  (actual: 'medium')
      ✗ [block] 5.1_nj_gambling_helpline
          scope:
            T  all:
              T  state eq 'NJ'  (actual: 'NJ')
              T  ad_category eq 'gambling'  (actual: 'gambling')
          T  any:
            F  disclaimer_present eq False  (actual: True)
            T  not:
              F  disclaimer_text regex '1-800-GAMBLER'  (actual: 'Gamble Responsibly.')
      ✗ [block] custom_signup_bonus_over_1000_nj_block
          scope:
            T  state eq 'NJ'  (actual: 'NJ')
          T  signup_bonus_over_1000 eq True  (actual: True)
      – out of scope: 1.1a_alcohol_targeting_21, 1.1b_alcohol_responsible_message, 1.1c_alcohol_no_under_25, 1.3a_finance_apr_required, 1.3b_finance_no_guaranteed_approval, 1.4c_weight_loss_targeting_18, 5.2_no_alcohol_gambling_email, 5.3_self_serve_finance_review, custom_signup_bonus_over_1000_review
    ```

## Step 9：換一個領域

上面的內容，除了三個資料檔以外，完全沒有提到廣告。一個領域就是 `schema.json + context.json + policies.md`。這裡有另外兩個：

- **`product_listings`**：第三方市集的商品刊登（仿冒跡象、醫療宣稱、站外付款、賣家等級和地區規則）
- **`ugc`**：社群留言和評論（騷擾、PII、垃圾訊息、依介面範圍而定的髒話規則）

各自編譯，並端到端跑一個有代表性的樣本。（編譯後的規則集會快取在 `evaluation/compiled/` 底下，重跑時不會重新編譯。）


```python
CACHE = pathlib.Path("evaluation/compiled")
CACHE.mkdir(parents=True, exist_ok=True)


def load_domain(name):
    d = DATA / name
    return {
        "dir": d,
        "schema": json.loads((d / "schema.json").read_text()),
        "context": json.loads((d / "context.json").read_text()),
        "policies": (d / "policies.md").read_text(),
        "samples": [
            json.loads(line)
            for line in (d / "samples.jsonl").read_text().splitlines()
            if line.strip()
        ],
    }


def rules_for(name, dom):
    if name == "ad_creatives":
        return golden
    cache = CACHE / f"{name}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    doc, attempts_ = compile_policies(dom["policies"], dom["schema"], dom["context"])
    cache.write_text(json.dumps(doc, indent=2))
    return doc


for name in ["product_listings", "ugc"]:
    dom = load_domain(name)
    doc = rules_for(name, dom)
    assert not validate_document(doc, dom["schema"], dom["context"])
    s = dom["samples"][1]  # a violating sample from each domain
    f = extract_fields(s["submission"], dom["schema"], doc.get("derived_fields", {}))
    v = evaluate(doc["rules"], f, s["context"])
    print(f"═══ {name}: {len(doc['rules'])} rules · sample: {s['name']}")
    print("   " + v.explain().replace("\n", "\n   "), "\n")
```

??? note "輸出"

    ```text
    ═══ product_listings: 9 rules · sample: Rolex at $89, 'authentic'
       DECISION: BLOCK
         ✗ [block] 3.1b_luxury_low_price_authentic_claim
             scope:
               T  all:
                 T  luxury_brand_mentioned exists  (actual: 'Rolex')
                 T  price_usd lt 100  (actual: 89.0)
             T  claims_authentic eq True  (actual: True)
         – out of scope: 4.1a_blades_new_seller, 4.1b_blades_eu, 4.2_new_seller_high_value_electronics
    ```

    ```text
    ═══ ugc: 7 rules · sample: Personal attack on the author
       DECISION: BLOCK
         ✗ [block] 1.1_personal_attacks
             T  personal_attack eq True  (actual: True)
         – out of scope: 1.2b_profanity_forum, 3.2_new_account_links, 4.1_undisclosed_incentive
    ```

## Step 10：衡量成效

最後，整套東西表現得如何？每個領域都附一份 `samples.jsonl`：投稿內容（有些帶廣告圖片），加上該領域政策下的預期決定。抽取是唯一不確定的階段，所以這其實是一個 **extraction eval**，也正是你在正式環境該投入調校的地方（欄位描述、judge 指示、圖片品質）。

為了讓這個 notebook 執行起來便宜，下面的 cell 預設每個領域只跑 2 個樣本。在環境裡設 `RUN_FULL_EVAL=1`（或執行 `evaluation/run_eval.py`）就能跑完整 22 個樣本的表。下面已存的輸出來自完整執行。


```python
import os

FULL = os.environ.get("RUN_FULL_EVAL") == "1"
PER_DOMAIN = None if FULL else 2  # token-light default; RUN_FULL_EVAL=1 for all samples

totals = {"correct": 0, "n": 0}
for name in ["ad_creatives", "product_listings", "ugc"]:
    dom = load_domain(name)
    doc = rules_for(name, dom)
    samples = dom["samples"][:PER_DOMAIN] if PER_DOMAIN else dom["samples"]
    correct = 0
    print(
        f"═══ {name} — {len(samples)} of {len(dom['samples'])} samples"
        + ("" if FULL else "  (subset — set RUN_FULL_EVAL=1 for all)")
    )
    for s in samples:
        image = dom["dir"] / s["image"] if s.get("image") else None
        f = extract_fields(
            s["submission"], dom["schema"], doc.get("derived_fields", {}), image_path=image
        )
        v = evaluate(doc["rules"], f, s["context"])
        ok = v.decision == s["expected"]
        correct += ok
        mark = "✓" if ok else "✗"
        fired = ", ".join(r.rule_id for r in v.fired) or "—"
        print(
            f"  {mark} {s['name']:<38} expected {s['expected']:<12} got {v.decision:<12} fired: {fired}"
        )
    print(f"  → {correct}/{len(samples)}\n")
    totals["correct"] += correct
    totals["n"] += len(samples)

print(
    f"TOTAL: {totals['correct']}/{totals['n']} decisions correct "
    f"({100 * totals['correct'] / totals['n']:.0f}%)"
)
```

??? note "輸出"

    ```text
    ═══ ad_creatives — 10 of 10 samples
    ```

    ```text
      ✓ Sneaker ad — clean                     expected approve      got approve      fired: —
    ```

    ```text
      ✓ Sportsbook bonus — NJ, no helpline     expected block        got block        fired: 3.1b_text_coverage_medium, 5.1_nj_gambling_helpline
    ```

    ```text
      ✓ Loan rate without APR — self-serve     expected block        got block        fired: 1.3a_finance_apr_required, 5.3_self_serve_finance_review
    ```

    ```text
      ✓ Skincare before/after                  expected block        got block        fired: 1.4a_no_before_after
    ```

    ```text
      ✓ Wine ad done right                     expected approve      got approve      fired: —
    ```

    ```text
      ✓ Wine ad in the email channel           expected block        got block        fired: 5.2_no_alcohol_gambling_email
    ```

    ```text
      ✓ Weight-loss ad targeting teens         expected block        got block        fired: 1.4c_weight_loss_targeting_18, 2.1_superlatives_review, 3.1b_text_coverage_medium
    ```

    ```text
      ✓ Phone ad naming a competitor           expected flag         got flag         fired: 2.2_competitor_reference
    ```

    ```text
      ✓ Casino ad with no age badge            expected block        got block        fired: 1.2b_gambling_age_badge
    ```

    ```text
      ✓ Supplement claiming to cure            expected block        got block        fired: 1.4b_no_health_claims
      → 10/10

    ═══ product_listings — 6 of 6 samples
    ```

    ```text
      ✓ Blender — clean listing                expected approve      got approve      fired: —
    ```

    ```text
      ✓ Rolex at $89, 'authentic'              expected block        got block        fired: 3.1b_luxury_low_price_authentic_claim
    ```

    ```text
      ✓ Supplement that 'cures' insomnia       expected block        got block        fired: 1.1_no_medical_claims, 1.2_no_fda_claims
    ```

    ```text
      ✓ Seller asking for Venmo                expected block        got block        fired: 2.1_no_contact_info, 2.2_no_offplatform_payment
    ```

    ```text
      ✓ Chef's knife from a new seller         expected block        got block        fired: 4.1a_blades_new_seller
    ```

    ```text
      ✓ New seller, $899 camera                expected flag         got flag         fired: 4.2_new_seller_high_value_electronics
      → 6/6

    ═══ ugc — 6 of 6 samples
    ```

    ```text
      ✓ Thoughtful comment                     expected approve      got approve      fired: —
    ```

    ```text
      ✓ Personal attack on the author          expected block        got block        fired: 1.1_personal_attacks
    ```

    ```text
      ✓ Profanity in news comments             expected block        got block        fired: 1.2a_profanity_news_comments
    ```

    ```text
      ✓ Profanity in the forum                 expected flag         got flag         fired: 1.2b_profanity_forum
    ```

    ```text
      ✓ Doxxing attempt                        expected block        got block        fired: 1.1_personal_attacks, 2.1_personal_information
    ```

    ```text
      ✓ New account posting a link             expected flag         got flag         fired: 3.2_new_account_links
      → 6/6

    TOTAL: 22/22 decisions correct (100%)
    ```

### 一個邊界案例

有一個 UGC 樣本真的很模糊：一個新帳號貼了 *"I wrote a longer response on my blog: [link]"*。預期是 **flag**（新帳號連結審核），而依執行情況，extractor 有時會判斷成 `promotional: true`，因此升級成 **block**。不管哪種結果，抽取都不算錯，是 schema 把邊界留得很模糊。

重點是修正的路徑：你不用動規則或引擎，只要把欄位描述寫得更精確再重跑 eval。這裡的 prompt engineering 影響範圍窄而且可量測：一個欄位、一段描述、表裡的一個數字。


## 上線注意事項

編譯在每次政策變更時跑一次；抽取是每則內容一次呼叫，所以量大時你只需要優化一個 prompt（把 schema 放進[快取的 prefix](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)，補資料用 [Batch API](https://platform.claude.com/docs/en/build-with-claude/batch-processing) 跑）。對既有的抽取結果重新評估，不管是新的規則集版本或是 what-if，都是免費的。

規則集要保持不可變，並且每次審核都記錄 `(內容, 抽出的欄位, 規則集版本, context, 判定, trace)`；這樣稽核人員幾個月後問「為什麼」你答得出來，也能在採用新規則集前，用歷史資料重播驗證。把 `needs_review` 交給人工，並觀察它的比例：某個欄位的 `null` 變多，通常代表描述需要改進。也要把限制攤在檯面上：帶有 `uses_llm_fields` 的規則靠的是模型判斷，而 `uncompilable` 的條文需要這條 pipeline 沒有的系統。

## 什麼時候用這個模式

適合的情況：政策是你自己的而且常常變、判定必須向投稿者或稽核人員解釋、同一則內容會在不同投放位置或政策版本下被重新檢查，而且負責政策的人不是工程師。

不適合的情況：單一類別的偵測而且有業界標準分類（CSAM、暴力），這種情況專用的分類器才是對的選擇；還有沒有政策變更需求的一次性分類，單純的分類 prompt 比較簡單。

## 重點整理

- 讓 Claude 只做「讀懂政策」和「讀懂內容」，下判定交給沒有模型的純函式引擎，這樣結果一致、便宜、可稽核。
- schema 是模型和引擎之間的契約，欄位描述同時是抽取指示和編譯依據，允許 null 是為了表達「看不出來」。
- 三值邏輯讓 unknown 變成 `needs_review`，而不是假裝有把握；scope 與違規分開，投放 context 變了不用再呼叫模型。
- 沒辦法比較的條文，由 compiler 製造 derived field 交給抽取階段判斷，validator 加 repair loop 擋掉幻覺出來的欄位。
- 品質問題集中在抽取階段，調的是欄位描述，影響範圍小又好量測。

## 練習

1. 把 Step 3 試玩的那條手寫規則，改成用 `gte` 或 `in` 比較別的欄位，並把欄位值設成 `null`，看 trace 怎麼顯示 unknown。
2. 在 Step 8 換一句你自己的白話政策（例如某個州禁止特定用語），跑 `compile_single_rule`，看它產生幾條規則、有沒有重用既有的衍生欄位。
3. 針對 Step 10 的邊界案例，改 `ugc` schema 裡 `promotional` 欄位的描述，把「新帳號貼自己部落格連結」是否算推銷寫清楚，再跑 eval 看那個樣本的結果有沒有穩定。
