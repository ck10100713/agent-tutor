---
translated: true
source: articles/per_run_spending_controller_responses_api.md
---
# 用 Responses API 做每次執行的花費控制器

> 原文：[articles/per_run_spending_controller_responses_api.md](https://github.com/openai/openai-cookbook/blob/main/articles/per_run_spending_controller_responses_api.md)

用 token 計數、最高成本估算、用量追蹤和安全的錯誤處理，為每次 Responses API 執行設定由應用自己掌控的模型 token 預算。

## 這篇在做什麼

用 Responses API 的 agent 完成一個任務時，可能會呼叫模型好幾次。組織和專案層級的花費上限只管整體用量，管不到「這個任務還付不付得起下一次請求」。這篇做一個控制器，每次執行有自己的預算，送請求之前先預留最高可能花費，回應回來後記帳並把沒用到的退回，餘額不夠就停手。

## 學完你會

- 算出一次 Responses API 請求的最高可能成本（ordinary input、cached input、cache write、output）
- 寫一個執行緒安全的 `RunBudget`，做預留、結算和退回
- 在請求送出前擋下會超支的呼叫，並在請求中斷或成本不明時安全地停止整次執行

## 開跑前

- Python 3.12 以上，`openai>=2.28.0`
- 範例用離線 client，不需要 API key；要用真的 client 才需要 `OPENAI_API_KEY`，會產生費用

用一個情境來講。客服工單 #4821 問訂單 ORD-42 什麼時候到。訂單已出貨，週五送達。給這張工單 $0.02 的預算。第一次回覆花 $0.01。再回覆一次最高可能花 $0.0146，但只剩 $0.01，所以應用停止。

這個控制器處理的是預設處理層級（default processing tier）下，同步、非 streaming 的 Responses API 請求。預算只涵蓋模型 token 成本，hosted tools 和其他費用不算。下面的價格、token 數、模型名稱和上限都是編的，不是 OpenAI 目前的價格、真實的模型上限，也不保證你最後的帳單。

## 估算 Responses API 請求最高可能花多少

範例價格單位是每一百萬 token 的美元：

| Token type | Example price (USD per 1 million tokens) |
| --- | ---: |
| Ordinary input | $4.00 |
| Cached input | $2.00 |
| Cache writes | $8.00 |
| Output | $20.00 |

應用的上限設成每次請求 10,000 個 input token 和 250 個 output token。這些數字是範例設定，不是真實模型的上限。只有所選模型把 cache write 另外計費時，才會用到 cache write 價格。

工單 #4821 用了 1,200 個 input token。為了避免低估回應成本，假設每個 input token 都用最高的 input 價格。這裡單獨計費的 cache write 最貴：

```text
(1,200 x $8.00 + 250 x $20.00) / 1,000,000 = $0.0146
```

用 Python 內建的 `Fraction` 型別讓金額保持精確。真的送請求之前，要檢查模型、預設處理層級、token 上限和價格。`verified_at` 日期記錄的是這些價格何時查證過，不代表它們現在還是正確的。見[目前的 API 價格](https://developers.openai.com/api/docs/pricing)和[模型文件](https://developers.openai.com/api/docs/models)。

![Model spending control: count the input, set aside the highest possible cost, run the model, and record the actual cost.](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/per_run_spending_controller/decision_flow.svg)

## 讓每次執行不超出預算

### 定義模型和價格

你需要 Python 3.12 或更新版本，以及 `openai>=2.28.0`。把模型、預設處理層級、token 價格和請求上限一起設定。用固定的模型 ID，API 會原樣回傳在 `response.model`。這個範例不支援 model alias。只有模型沒有另外計 cache write 時，才把 `cache_write_usd_per_million` 設成 `None`。範例價格只能搭配離線 client 使用。

```python
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from threading import Lock
from types import SimpleNamespace
from typing import Any
from openai.types.responses import Response

@dataclass(frozen=True)
class RateCard:
    model: str
    service_tier: str
    input_usd_per_million: Fraction
    cached_usd_per_million: Fraction
    cache_write_usd_per_million: Fraction | None
    output_usd_per_million: Fraction
    max_input_tokens: int
    max_output_tokens: int
    example_only: bool = True
    verified: bool = False
    verified_at: date | None = None

    def __post_init__(self) -> None:
        if not all(type(value) is str and value.strip()
                   for value in (self.model, self.service_tier)):
            raise ValueError("Model and service tier must be nonempty strings")
        if self.service_tier != "default":
            raise ValueError("Only the default service tier is supported")
        for name in (
            "input_usd_per_million", "cached_usd_per_million",
            "output_usd_per_million",
        ):
            value = getattr(self, name)
            if type(value) is not Fraction or value <= 0:
                raise ValueError(f"{name} price must be a positive exact dollar amount")
        if self.cache_write_usd_per_million is not None and (
            type(self.cache_write_usd_per_million) is not Fraction
            or self.cache_write_usd_per_million <= 0
        ):
            raise ValueError("Cache-write price must be a positive exact dollar amount")
        if type(self.max_input_tokens) is not int or self.max_input_tokens <= 0:
            raise ValueError("Maximum input tokens must be a positive integer")
        if type(self.max_output_tokens) is not int or self.max_output_tokens < 16:
            raise ValueError("Maximum output tokens must be an integer of at least 16")
        if type(self.example_only) is not bool or type(self.verified) is not bool:
            raise ValueError("Pricing verification flags must be boolean")
        if self.example_only and self.verified:
            raise ValueError("Example pricing cannot be marked verified")
        if self.verified_at is not None and type(self.verified_at) is not date:
            raise ValueError("Pricing verification date must be a date")
        if self.verified and self.verified_at is None:
            raise ValueError("Record when you checked the model pricing")
        if self.example_only and self.verified_at is not None:
            raise ValueError("Example pricing cannot have a verification date")
        if not self.example_only and self.model == "example-model":
            raise ValueError("Replace the example model with your verified model")

EXAMPLE_RATE_CARD = RateCard(
    model="example-model",
    service_tier="default",
    input_usd_per_million=Fraction("4.00"),
    cached_usd_per_million=Fraction("2.00"),
    cache_write_usd_per_million=Fraction("8.00"),
    output_usd_per_million=Fraction("20.00"),
    max_input_tokens=10_000,
    max_output_tokens=250,
    example_only=True,
)
```

### 追蹤這次執行的預算

`RunBudget` 追蹤已經花掉的錢和暫時預留的錢。它的 lock 防止同一個 Python 行程裡的兩個請求預留到同一筆錢。當 cache write 有獨立價格時，回應必須包含 cache write 的 token 數。

```python
class BudgetExceeded(RuntimeError):
    pass

class UncertainCharge(RuntimeError):
    pass

@dataclass
class RunBudget:
    maximum: Fraction
    spent: Fraction = field(default_factory=Fraction, init=False)
    pending: Fraction = field(default_factory=Fraction, init=False)
    blocked: bool = field(default=False, init=False)
    _holds: dict[object, Fraction] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.maximum) is not Fraction or self.maximum <= 0:
            raise ValueError("Budget must be a positive exact dollar amount")

    def ensure_active(self, minimum: Fraction) -> None:
        if type(minimum) is not Fraction or minimum < 0:
            raise ValueError("Minimum must be a nonnegative exact dollar amount")
        with self._lock:
            if self.blocked or self.spent + self.pending + minimum > self.maximum:
                raise BudgetExceeded("The remaining run budget is insufficient")

    def reserve(self, amount: Fraction) -> object:
        if type(amount) is not Fraction or amount <= 0:
            raise ValueError("Reservation must be a positive exact dollar amount")
        with self._lock:
            if self.blocked or self.spent + self.pending + amount > self.maximum:
                raise BudgetExceeded("The remaining run budget is insufficient")
            handle = object()
            self._holds[handle] = amount
            self.pending += amount
            return handle

    def settle(self, handle: object, actual: Fraction) -> None:
        if type(handle) is not object or type(actual) is not Fraction or actual < 0:
            raise ValueError("Invalid spend settlement")
        with self._lock:
            held = self._holds.get(handle)
            if held is None or held > self.pending:
                raise ValueError("Reservation is unknown or already settled")
            del self._holds[handle]
            self.pending -= held
            self.spent += actual
            if actual > held:
                self.blocked = True
                raise UncertainCharge("Actual spend exceeded the amount reserved")

    def block(self) -> None:
        with self._lock:
            self.blocked = True

def _tokens(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise UncertainCharge(f"Invalid {name} token count")
    return value

def actual_cost(usage: Any, rates: RateCard) -> Fraction:
    if usage is None:
        raise UncertainCharge("Token usage is missing")
    details = getattr(usage, "input_tokens_details", None)
    if details is None:
        raise UncertainCharge("Input token details are missing")
    input_tokens = _tokens(getattr(usage, "input_tokens", None), "input")
    output_tokens = _tokens(getattr(usage, "output_tokens", None), "output")
    total_tokens = _tokens(getattr(usage, "total_tokens", None), "total")
    if total_tokens != input_tokens + output_tokens:
        raise UncertainCharge("Total tokens do not match input and output")
    cached = _tokens(getattr(details, "cached_tokens", None), "cached")
    if rates.cache_write_usd_per_million is not None:
        if not hasattr(details, "cache_write_tokens"):
            raise UncertainCharge("Cache-write token accounting is missing")
        written = _tokens(details.cache_write_tokens, "cache-write")
    else:
        observed = _tokens(getattr(details, "cache_write_tokens", 0), "cache-write")
        if observed:
            raise UncertainCharge("Cache writes require a verified cache-write price")
        written = 0
    ordinary = input_tokens - cached - written
    if (
        input_tokens > rates.max_input_tokens
        or output_tokens > rates.max_output_tokens or ordinary < 0
    ):
        raise UncertainCharge("Usage exceeds the configured request bounds")
    return (
        ordinary * rates.input_usd_per_million
        + cached * rates.cached_usd_per_million
        + written * (rates.cache_write_usd_per_million or Fraction())
        + output_tokens * rates.output_usd_per_million
    ) / 1_000_000
```

### 每次請求前檢查預算

計算 token 和產生回應時，要用同一個 `model` 和 `input`。Instructions、tool schema、圖片、檔案和對話歷史也會用掉 input token。如果你加了這些，就要把相同的支援欄位同時傳給兩個請求。`max_output_tokens`、`service_tier` 和 `store` 只傳給產生回應的請求。

```python
def response_with_budget(
    client: Any, prompt: str, budget: RunBudget, rates: RateCard,
    *, allow_example: bool = False,
) -> Response | SimpleNamespace:
    if type(prompt) is not str or not prompt.strip():
        raise ValueError("Only nonempty text prompts are supported")
    if type(allow_example) is not bool:
        raise ValueError("Example authorization must be a boolean")
    if (rates.example_only or not rates.verified) and not (
        allow_example and type(client) is OfflineClient
    ):
        raise ValueError("API requests require explicitly verified pricing")
    if client.max_retries != 0:
        raise ValueError("Initialize the OpenAI client with max_retries=0")
    budget.ensure_active(
        rates.max_output_tokens * rates.output_usd_per_million / 1_000_000
    )
    request = {"model": rates.model, "input": prompt}
    count = _tokens(client.responses.input_tokens.count(**request).input_tokens, "input")
    if count > rates.max_input_tokens:
        raise BudgetExceeded("Request exceeds the configured input limit")
    worst_input_price = max(
        price for price in (
            rates.input_usd_per_million, rates.cached_usd_per_million,
            rates.cache_write_usd_per_million,
        )
        if price is not None
    )
    reservation = budget.reserve(
        (
            count * worst_input_price
            + rates.max_output_tokens * rates.output_usd_per_million
        ) / 1_000_000
    )
    try:
        response = client.responses.create(
            **request, max_output_tokens=rates.max_output_tokens,
            service_tier=rates.service_tier, store=False,
        )
        if response.model != rates.model:
            raise UncertainCharge("Response used an unexpected model")
        if response.service_tier != rates.service_tier:
            raise UncertainCharge("Unexpected service tier")
        cost = actual_cost(response.usage, rates)
    except BaseException:
        # An interruption after submission may still incur a charge.
        budget.block()
        raise
    if response.status != "completed":
        budget.block()
    budget.settle(reservation, cost)
    if response.status != "completed":
        raise UncertainCharge(f"Response ended with status: {response.status}")
    return response

def format_dollars(amount: Fraction) -> str:
    return "$" + f"{amount:.9f}".rstrip("0").rstrip(".")
```

`response_with_budget` 回傳完整的 response，包括 `response.output_text` 和 `response.output`。它會檢查 API 用的是設定的模型和處理層級。如果請求被中斷或無法確認成本，這次執行會永久停止，預留的預算維持被占用。如果一個不完整的 response 有回報用量，控制器會記錄那筆成本，並讓這次執行維持封鎖。

要用真的 client，用 `from openai import OpenAI` 匯入 `OpenAI`，檢查目前價格，並設定 `OPENAI_API_KEY`。然後用 `client = OpenAI(max_retries=0, timeout=60.0)` 建立 client。請求在 client timeout 之後仍可能繼續執行，所以預留要保留。

## 範例：為客服工單設定預算

工單 #4821 的第一個回應回報 1,200 個 input token：400 個 cached、500 個單獨計費的 cache write token。剩下 300 個是 ordinary input token。它也回報 200 個 output token：

```text
(300 x $4.00 + 400 x $2.00 + 500 x $8.00 + 200 x $20.00)
/ 1,000,000 = $0.0100
```

第一個回應花 $0.01，剩下 $0.01。下一個回應最高可能花 $0.0146，所以控制器在送出另一個模型請求之前就停下來。

![Support ticket budget: the first answer spends $0.01 and the second answer is blocked because $0.0146 exceeds the remaining $0.01.](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/per_run_spending_controller/support_ticket.svg)

把上面三個程式碼區塊和下面的離線範例，依序存成 `controller.py`。安裝 SDK 並執行：

```bash
python -m pip install "openai>=2.28.0"
python controller.py
```

工單和訂單都是虛構的，離線 client 不會送出任何網路請求：

```python
class OfflineClient:
    __slots__ = ("model_calls",)
    max_retries = 0

    def __init__(self) -> None:
        self.model_calls = 0

    @property
    def responses(self) -> "OfflineClient":
        return self

    @property
    def input_tokens(self) -> "OfflineClient":
        return self

    def count(self, **_: Any) -> SimpleNamespace:
        return SimpleNamespace(input_tokens=1200)

    def create(self, **request: Any) -> SimpleNamespace:
        self.model_calls += 1
        return SimpleNamespace(
            model=request["model"], service_tier="default", status="completed",
            output_text="Order ORD-42 has shipped and should arrive Friday.",
            usage=SimpleNamespace(
                input_tokens=1200, output_tokens=200, total_tokens=1400,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=400, cache_write_tokens=500
                ),
            ),
        )


if __name__ == "__main__":
    client = OfflineClient()
    budget = RunBudget(Fraction("0.02"))
    ticket = "Ticket #4821: order ORD-42 shipped and arrives Friday."
    print(response_with_budget(
        client, ticket + " Draft a support reply.", budget,
        EXAMPLE_RATE_CARD, allow_example=True,
    ).output_text)
    try:
        response_with_budget(
            client, ticket + " Write a second version.", budget,
            EXAMPLE_RATE_CARD, allow_example=True,
        )
    except BudgetExceeded:
        print("Ticket #4821 stopped: the next step would exceed its budget.")
    print("Spent: " + format_dollars(budget.spent))
    print("Reserved: " + format_dollars(budget.pending))
    print(f"Model calls: {client.model_calls}")
```

**預期輸出：**

```text
Order ORD-42 has shipped and should arrive Friday.
Ticket #4821 stopped: the next step would exceed its budget.
Spent: $0.01
Reserved: $0
Model calls: 1
```

## 限制與其他成本

Ordinary input、cached input、單獨計費的 cache write 和 output 都只算一次。模型沒有另外計 cache write 時，non-cached input 按一般價格收費。出現預期之外的正 cache write 數量，執行會停止。見模型的 [prompt caching 指南](https://developers.openai.com/api/docs/guides/prompt-caching)。Reasoning token 已經包含在 output 總數裡。

這個 lock 只保護單一 Python 行程。多個 worker 共用一份預算時，要用共享儲存，並在同一個操作中檢查並預留預算，這樣它們才不會預留到同一筆錢。如果請求的最終成本不明，就放棄那次執行並保留預留。啟用 retry 之前，先看 [Python SDK 的 retry 行為](https://github.com/openai/openai-python#retries)。

Hosted tools 可能產生另外的費用。例如 web search 可能每次呼叫都收費，相關的模型 token 也要錢。預算也不含儲存、非預設處理層級、區域價格、長 context 費率、streaming、background 請求、由伺服器管理的 agent 執行，以及帳號專屬的費用。Background 請求可能先回傳 `queued` 或 `in_progress`，所以需要另外的規則來追蹤最終用量。設定 `store=False` 不保證 Zero Data Retention，見[資料控制](https://developers.openai.com/api/docs/guides/your-data)。

[專案花費上限](https://developers.openai.com/api/docs/guides/spend-limits)涵蓋專案總花費，而且不一定立刻生效。警示不會擋住請求。[Costs API 參考](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs)顯示每日總額，但它沒辦法告訴你某個任務付不付得起下一次請求。

## 重點整理

- 組織或專案層級的花費上限管整體，管不到單一任務，所以要在應用層替每次執行設自己的預算。
- 送請求前用「最壞情況」預留成本（所有 input 都用最貴的價格，output 用上限），回應回來再按實際用量結算並退回差額。
- 預算不夠就在送出前停手，比事後發現超支好。
- 成本不明時（請求中斷、timeout）要保守：保留預留、永久封鎖這次執行，而不是假設沒花錢。
- 單行程的 lock 擋不住多 worker，共享預算需要原子性的檢查加預留。

## 練習

1. 把每次請求的 `max_output_tokens` 從 250 改成 500，重新算工單 #4821 的最高可能成本，看第一次請求還過不過得了預算。
2. 把工單預算從 $0.02 調成 $0.03，執行離線範例，看第二次請求會不會被放行。
3. 改 `RunBudget`，讓它在被擋下時記一筆 log，內容包含剩餘預算和被拒絕那次請求的最高成本。
