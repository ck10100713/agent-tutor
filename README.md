# OpenAI & Claude 開發教材（繁中）

網站：https://ck10100713.github.io/agent-tutor/

把官方教材整理成繁體中文：

| 來源 | 網站上 |
|---|---|
| [openai/openai-cookbook](https://github.com/openai/openai-cookbook) | 全文翻譯；要 GPU 的 10 篇是 Colab notebook |
| [anthropics/claude-cookbooks](https://github.com/anthropics/claude-cookbooks) | 全文翻譯 |
| [anthropics/claude-quickstarts](https://github.com/anthropics/claude-quickstarts) | 全文翻譯（各專案 README） |
| [anthropics/prompt-eng-interactive-tutorial](https://github.com/anthropics/prompt-eng-interactive-tutorial) | 原 repo 沒有授權，只放重點導讀和原文連結 |

- `docs/`：網站內容，程式碼直接放在頁面上
- `notebooks/`：需要 GPU 的篇，用 Colab 跑
- `build.py`：從原始 repo 產生上面兩者（原始 repo 要 clone 在旁邊，見 `SOURCES`）
- `i18n.py`、`TRANSLATE_RULES.md`：翻譯流程與規則

原始內容版權屬於各自作者，OpenAI 與 Anthropic 的 cookbook 和 quickstarts 皆以 MIT 授權釋出，見 `LICENSE-*`。
