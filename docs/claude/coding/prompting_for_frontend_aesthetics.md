---
translated: true
source: coding/prompting_for_frontend_aesthetics.ipynb
---

# 用 prompt 引導 frontend 的視覺風格

> 原文：[coding/prompting_for_frontend_aesthetics.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/coding/prompting_for_frontend_aesthetics.ipynb)

教你怎麼 prompt Claude，做出有特色又精緻的 frontend 設計，避開千篇一律的風格。

## 這篇在做什麼

Claude 寫 frontend 很強，但沒有引導的話，出來的設計通常很保守、很大眾臉。這篇教你用一段 prompt，把 Claude 推向比較有個性的視覺風格，並比較有無這段 prompt 的差異。

## 學完你會

- 用三個策略（指定設計維度、參考靈感來源、點名要避開的預設）寫出 aesthetics prompt。
- 把 aesthetics prompt 放進 system prompt 或 CLAUDE.md，讓生成的 UI 風格更多變。
- 只針對單一維度（例如字體）或固定一種主題，做出更快、更可控的生成。

## 開跑前

需要 Anthropic API key，範例程式會呼叫 Claude 生成 HTML。

Claude 能產出高品質的 frontend，但沒有引導時，傾向給出通用又保守的設計。這篇示範怎麼 prompt，讓輸出更有特色、更精緻。

## 用 prompt 拿到更好的輸出

Claude 對設計原則、字體、色彩理論都有很強的知識，但除非明確鼓勵，不然它會選安全的做法。我們實驗後發現，有三個策略一直都有效：

1. **指定具體的設計維度**：分別把 Claude 的注意力導向字體、顏色、動態、背景。
2. **參考設計靈感**：提示像 IDE 主題或文化美學這類來源，但不要寫得太死。
3. **點名常見的預設選擇**：明講叫 Claude 避開它習慣的通用選項。

下面這段 prompt 把這些策略套用在四個主要的設計面向上。

## The Prompt

要套用這些改動，可以把這段 prompt 附加在你的 system prompt 或 CLAUDE.md 檔案後面。

```python
DISTILLED_AESTHETICS_PROMPT = """
<frontend_aesthetics>
You tend to converge toward generic, "on distribution" outputs. In frontend design, this creates what users call the "AI slop" aesthetic. Avoid this: make creative, distinctive frontends that surprise and delight. Focus on:

Typography: Choose fonts that are beautiful, unique, and interesting. Avoid generic fonts like Arial and Inter; opt instead for distinctive choices that elevate the frontend's aesthetics.

Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration.

Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Use Motion library for React when available. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions.

Backgrounds: Create atmosphere and depth rather than defaulting to solid colors. Layer CSS gradients, use geometric patterns, or add contextual effects that match the overall aesthetic.

Avoid generic AI-generated aesthetics:
- Overused font families (Inter, Roboto, Arial, system fonts)
- Clichéd color schemes (particularly purple gradients on white backgrounds)
- Predictable layouts and component patterns
- Cookie-cutter design that lacks context-specific character

Interpret creatively and make unexpected choices that feel genuinely designed for the context. Vary between light and dark themes, different fonts, different aesthetics. You still tend to converge on common choices (Space Grotesk, for example) across generations. Avoid this: it is critical that you think outside the box!
</frontend_aesthetics>
"""
```

## 結果

下面是有加跟沒加上面那段 prompt 的 UI 生成結果。

沒有引導時，Claude 常常做出簡陋、白底配紫色的設計。加了 aesthetics prompt 之後，設計變得更多樣、更好看。

### 範例 1：SaaS landing page
**Prompt：** `"Create a SaaS landing page for a project management tool"`

<table>
<tr>
<td width="50%" valign="top">

**沒有 aesthetics prompt**

![Baseline output without aesthetics guidance](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/frontend_aesthetics/baseline_saas.png)

</td>
<td width="50%" valign="top">

**有 aesthetics prompt**

![Enhanced output with distilled aesthetics prompt](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/frontend_aesthetics/distilled_saas.png)

</td>
</tr>
</table>

### 範例 2：部落格文章
**Prompt：** `"Build a blog post layout with author bio, reading time, and related articles"`

<table>
<tr>
<td width="50%" valign="top">

**沒有 aesthetics prompt**

![Baseline portfolio without aesthetics guidance](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/frontend_aesthetics/baseline_portfolio.png)

</td>
<td width="50%" valign="top">

**有 aesthetics prompt**

![Enhanced portfolio with distilled aesthetics prompt](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/frontend_aesthetics/distilled_portfolio.png)

</td>
</tr>
</table>

### 範例 3：後台資料表
**Prompt：** `"Create an admin panel with a data table showing users, their roles, and action buttons"`

<table>
<tr>
<td width="50%" valign="top">

**沒有 aesthetics prompt**

![Baseline dashboard without aesthetics guidance](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/frontend_aesthetics/baseline_dashboard.png)

</td>
<td width="50%" valign="top">

**有 aesthetics prompt**

![Enhanced dashboard with distilled aesthetics prompt](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/frontend_aesthetics/distilled_dashboard.png)

</td>
</tr>
</table>

## 自己試試看

先設定 helper function：

````python
import html
import os
import re
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic
from IPython.display import HTML as DisplayHTML
from IPython.display import display

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def save_html(html_content):
    os.makedirs("html_outputs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"html_outputs/{timestamp}.html"
    with open(filepath, "w") as f:
        f.write(html_content)
    return filepath


def extract_html(text):
    pattern = r"```(?:html)?\s*(.*?)\s*```"
    matches = re.findall(pattern, text, re.DOTALL)
    return matches[0] if matches else None


def open_in_browser(filepath):
    abs_path = Path(filepath).resolve()
    webbrowser.open(f"file://{abs_path}")
    print(f"🌐 Opened in browser: {filepath}")


def generate_html_with_claude(system_prompt, user_prompt):
    print("🚀 Generating HTML...\n")

    full_response = ""
    start_time = time.time()
    display_id = display(DisplayHTML(""), display_id=True)

    with client.messages.stream(
        model="claude-sonnet-5-5",
        max_tokens=64000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            full_response += text
            escaped_text = html.escape(full_response)
            display_html = f"""
            <div id="stream-container" style="border: 2px solid #667eea; border-radius: 8px; padding: 16px; background: #f8f9fa; max-height: 500px; overflow-y: auto;">
                <pre style="margin: 0; font-family: monospace; font-size: 12px; color: #2d2d2d; white-space: pre-wrap; word-wrap: break-word;">{escaped_text}</pre>
            </div>
            <script>
                requestAnimationFrame(() => {{
                    const container = document.getElementById('stream-container');
                    if (container) {{
                        container.scrollTop = container.scrollHeight;
                    }}
                }});
            </script>
            """
            display_id.update(DisplayHTML(display_html))

    elapsed = time.time() - start_time
    escaped_text = html.escape(full_response)
    final_html = f"""
    <div style="border: 2px solid #28a745; border-radius: 8px; padding: 16px; background: #f8f9fa; max-height: 500px; overflow-y: auto;">
        <pre style="margin: 0; font-family: monospace; font-size: 12px; color: #2d2d2d; white-space: pre-wrap; word-wrap: break-word;">{escaped_text}</pre>
    </div>
    """
    display_id.update(DisplayHTML(final_html))

    print(f"\n✅ Complete in {elapsed:.1f}s\n")

    html_content = extract_html(full_response)
    if html_content is None:
        print("❌ Error: Could not extract HTML from response.")
        raise ValueError("Failed to extract HTML from Claude's response.")

    filepath = save_html(html_content)
    print(f"💾 HTML saved to: {filepath}")
    open_in_browser(filepath)

    return filepath
````

用 aesthetics prompt 來生成：

````python
BASE_SYSTEM_PROMPT = """
You are an expert frontend engineer skilled at crafting beautiful, performant frontend applications.

<tech_stack>
Use vanilla HTML, CSS, & Javascript. Use Tailwind CSS for your CSS variables.
</tech_stack>

<output>
Generate complete, self-contained HTML code for the requested frontend application. Include all CSS and JavaScript inline.

CRITICAL: You must wrap your HTML code in triple backticks with html language identifier like this:
```html
<!DOCTYPE html>
<html>
...
</html>
```

Our parser depends on this format - do not deviate from it!
</output>
"""

USER_PROMPT = "Create a SaaS landing page for a project management tool"

# Generate with distilled aesthetics prompt
generate_html_with_claude(BASE_SYSTEM_PROMPT + "\n\n" + DISTILLED_AESTHETICS_PROMPT, USER_PROMPT)
````

??? note "輸出"

    ```text
    🚀 Generating HTML...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text

    ✅ Complete in 98.2s

    💾 HTML saved to: html_outputs/20251021_101010.html
    🌐 Opened in browser: html_outputs/20251021_101010.html
    ```

    ```text
    'html_outputs/20251021_101010.html'
    ```

## 單獨使用某個維度的 prompt

完整的 aesthetics prompt 很適合一般用途，但有時你想要更精準的控制。你可以單獨挑出某個維度（字體、顏色、動態），或鎖定特定主題。這樣生成比較快，輸出也更好預測。

### 範例 1：只管字體

想只改善某一個面向、其他不動的時候，就把單一設計維度獨立出來：

```python
TYPOGRAPHY_PROMPT = """
<use_interesting_fonts>
Typography instantly signals quality. Avoid using boring, generic fonts.

**Never use:** Inter, Roboto, Open Sans, Lato, default system fonts

**Impact choices:**
- Code aesthetic: JetBrains Mono, Fira Code, Space Grotesk
- Editorial: Playfair Display, Crimson Pro, Fraunces
- Startup: Clash Display, Satoshi, Cabinet Grotesk
- Technical: IBM Plex family, Source Sans 3
- Distinctive: Bricolage Grotesque, Obviously, Newsreader

**Pairing principle:** High contrast = interesting. Display + monospace, serif + geometric sans, variable font across weights.

**Use extremes:** 100/200 weight vs 800/900, not 400 vs 600. Size jumps of 3x+, not 1.5x.

Pick one distinctive font, use it decisively. Load from Google Fonts. State your choice before coding.
</use_interesting_fonts>
"""

# Generate with typography-only guidance
generate_html_with_claude(BASE_SYSTEM_PROMPT + "\n\n" + TYPOGRAPHY_PROMPT, USER_PROMPT)
```

### 範例 2：鎖定主題

想要多次生成都維持一致的風格時，就鎖定一種特定美學：

```python
SOLARPUNK_THEME_PROMPT = """
<always_use_solarpunk_theme>
Always design with Solarpunk aesthetic:
- Warm, optimistic color palettes (greens, golds, earth tones)
- Organic shapes mixed with technical elements
- Nature-inspired patterns and textures
- Bright, hopeful atmosphere
- Retro-futuristic typography
</always_use_solarpunk_theme>
"""

# Generate with theme constraint
generate_html_with_claude(
    BASE_SYSTEM_PROMPT + "\n\n" + SOLARPUNK_THEME_PROMPT,
    "Create a dashboard for renewable energy monitoring",
)
```

## 總結

Claude 的設計能力很強，但預設會選安全又通用的做法。這篇的技巧有三個：針對具體設計維度下指示、參考具體的靈感、明講要避開常見預設，這樣能穩定產出更有特色的結果。完整的 aesthetics prompt 適合當基準，要更多控制就用單一維度的 prompt，或在多次生成中鎖定特定主題。

## 重點整理

- Claude 對設計很懂，但沒被推一把就會選安全、通用的風格。
- 三個策略：指定設計維度、參考具體靈感、點名要避開的預設。
- 把 aesthetics prompt 放在 system prompt 或 CLAUDE.md，等於給所有生成一個風格基準。
- 只想調一個面向時，用單一維度（如字體）的 prompt，比完整版更快也更好預測。
- 要跨多次生成保持一致，就鎖定一種主題。

## 練習

1. 在「只管字體」的範例裡，換一組你喜歡的字體方向，重新生成並比較差異。
2. 在「鎖定主題」的範例裡，把主題換成另一種風格，同樣的 UI 需求跑兩次，看一致性如何。
3. 自己寫一段只管「顏色」的 prompt，點名要避開白底配紫色，對同一個需求跟沒加時的結果做比較。
