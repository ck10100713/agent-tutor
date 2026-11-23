# 翻譯規則（批次翻譯的 prompt 就是這份）

讀者：有寫程式經驗、自學 OpenAI API 跟 agent 開發的工程師。大部分篇是網頁（docs/*.md），直接讀程式碼；要 GPU 的篇是 Colab notebook（notebooks/*.ipynb）。兩種格式規則一樣。

## 文字（md 的內文 / notebook 的 markdown cell）
- 翻成口語的繁體中文，像同事在講解。不要「值得注意的是」「綜上所述」這類套話。
- 技術名詞保留英文：agent、tool、prompt、token、embedding、fine-tuning、handoff、reasoning、schema、eval 等。第一次出現可以括號補中文。
- 程式碼、行內 `code`、URL、HTML 標籤、`<a id>` 錨點、圖片語法、LaTeX 一律不動。
- 標題翻中文，但 `[文字](#anchor)` 的 anchor 不改。
- 純連結列表、表格裡的 API 名稱不用翻。
- 網頁版不用提 Colab 或 setup cell；notebook 版講本機安裝的地方可以補一句 Colab 怎麼做。

## 程式碼（code block / code cell）和輸出
- 一個字都不動，註解也不翻。`??? note "輸出"` 區塊整段保留。

## 開頭 `<!-- tutor:goals -->`
換成：
- `## 這篇在做什麼`：2–3 句白話說明。
- `## 學完你會`：3 點，具體到能做出什麼。
- 需要額外設定的（環境變數、付費資源、外部服務帳號）寫在 `## 開跑前`，沒有就省略。

## 結尾 `<!-- tutor:summary -->`
換成：
- `## 重點整理`：3–5 點，講觀念不講步驟。
- `## 練習`：2–3 題，改頁面上的程式幾行就能動手做，由淺到深。

## frontmatter
- 翻完把開頭的 `translated: false` 改成 `true`，build.py 之後就不會覆蓋。
