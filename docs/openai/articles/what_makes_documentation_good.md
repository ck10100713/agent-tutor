---
translated: true
status: deprecated
tags:
- 原文已封存
source: articles/what_makes_documentation_good.md
---
# 好文件的條件

> 原文：[articles/what_makes_documentation_good.md](https://github.com/openai/openai-cookbook/blob/main/articles/what_makes_documentation_good.md)



## 這篇在做什麼

這是一篇寫文件的守則，分成三塊：讓人好掃讀、文句寫得好、對各種程度的讀者都有幫助。你要寫 API 文件、教學或 README 的時候，可以拿來當檢查清單。

## 學完你會

- 用標題、目錄、短段落和 topic sentence 把文件寫成容易掃讀的結構。
- 改寫難解析的句子，避開 left-branching 句型和 demonstrative pronoun。
- 判斷哪些地方該多解釋、哪些程式範例該保持獨立可複製。

文件的作用，是把有用的資訊放進別人的腦袋裡。照下面這些建議，可以寫出更好的文件。

### 讓文件好掃讀

很少人會從頭到尾線性閱讀。讀者會跳來跳去，判斷哪一段能解決他的問題，甚至判斷有沒有。要縮短他們的搜尋時間、提高成功機率，就要讓文件好掃讀。

**用標題把內容切成幾個段落。** 段落標題像路標，告訴讀者要細讀還是跳過。

**標題優先用有資訊量的句子，少用抽象名詞。** 例如標題寫「Results」，讀者得跳進後面的內文才知道結果是什麼。如果標題寫成「Streaming 讓 time to first token 降低 50%」，讀者馬上就拿到資訊，不用多跳一步。

**放目錄。** 目錄讓讀者更快找到資訊，就像 hash map 查找比 linked list 快。目錄還有一個常被忽略的好處，它給讀者關於這份文件的線索，幫他們判斷值不值得讀。

**段落要短。** 短段落比較好掃讀。如果有一個重要的點，可以讓它單獨成一個一句話的段落，減少被漏掉的機會。長段落會把資訊埋起來。

**每個段落和章節開頭用簡短的 topic sentence，而且要能單獨預覽內容。** 人在掃讀時，會特別看一個段落的第一個字、第一行、第一句。這些句子的寫法不能依賴前文。例如第一句寫「在這個基礎上，我們來談一個更快的方法。」沒讀過上一段的人會看不懂。改成能獨立理解的寫法，例如「Vector database 可以加快 embeddings 搜尋。」

**topic 的字放在 topic sentence 的開頭。** 讀者只要讀一兩個字就知道段落在講什麼，掃讀效率最高。所以寫 topic sentence 時，把主題放在句首而不是句尾。例如你在一篇談 embeddings 搜尋的長文中間，寫一段關於 vector database 的內容。與其寫「Embeddings 搜尋可以被 vector database 加速」，不如寫「Vector database 加速 embeddings 搜尋」。第二句更適合掃讀，因為段落主題在最前面。

**結論放最前面。** 最重要的資訊放在文件和章節的開頭。不要先鋪一大段蘇格拉底式的鋪陳，也不要先講流程再講結果。

**多用 bullet 和表格。** 條列和表格讓文件更好掃讀，常常用。

**重要的字加粗。** 別怕把重要文字加粗，讓讀者容易找到。

### 把字句寫好

寫得差的文字讀起來很累。把文句寫好，才能降低讀者的負擔。

**句子要簡單。** 長句拆成兩句。刪掉副詞。刪掉不必要的字詞。適合的話用祈使句。照寫作書教的做。

**寫出能毫無歧義地解析的句子。** 例如「Title sections with sentences.」這句話。讀者讀到「Title」時，大腦還不知道它是名詞、動詞還是形容詞。讀完整句的過程中要多花一點腦力追蹤，如果大腦猜錯了意思還會卡一下。就算比較長，也要偏好比較好解析的句子（例如「Write section titles as sentences」）。同樣地，避免像「Bicycle clearance exercise notice」這種名詞堆疊，它們要多花力氣解析。

**避免 left-branching 句子。** 語言學的樹狀圖顯示句子中字詞之間的關係。left-branching 的句子比 right-branching 的句子要讀者在記憶裡多記一些東西，類似 breadth-first search 和 depth-first search 的差別。left-branching 的例子是「You need flour, eggs, milk, butter and a dash of salt to make pancakes.」這句話要讀到句尾，才知道「you need」連到哪裡。比較好讀的 right-branching 版本是「To make pancakes, you need flour, eggs, milk, butter, and a dash of salt.」注意那些讀者得記住某個字好一陣子的句子，想想能不能換個說法。

**避免 demonstrative pronoun（例如「this」），尤其是跨句使用。** 例如不要說「延續我們對上一個主題的討論，現在來談 function calling」，改成「延續 message formatting，現在來談 function calling」。第二句更容易懂，因為它不用讀者回想上一個主題。盡量找機會直接刪掉 demonstrative pronoun，例如「現在來談 function calling。」

**保持一致。** 人腦是很厲害的 pattern matcher，不一致會讓讀者煩躁或分心。如果到處都用 Title Case，就都用 Title Case。如果到處都用句尾逗號，就都用句尾逗號。如果 Cookbook 所有 notebook 都用底線加 sentence case 命名，就都用底線加 sentence case。別做會讓讀者覺得「咦，好怪」的事，讓他們專心看內容，而不是被不一致的地方干擾。

**不要告訴讀者他們在想什麼或該做什麼。** 避免「現在你大概想知道怎麼呼叫 function」或「接下來你需要學怎麼呼叫 function」這種句子。兩者都預設了讀者的心態，可能惹惱他們或損害我們的可信度。用不預設讀者狀態的說法，例如「要呼叫 function，……」

### 對各種讀者都有幫助

來看文件的人，知識程度、語言能力、耐心都不同。就算我們的目標是有經驗的開發者，也應該盡量讓文件對每個人都有用。

**寫得簡單。** 解釋事情時，比你覺得需要的更簡單。很多讀者的母語可能不是英文。很多讀者可能對技術術語很困惑，沒有多餘腦力去解析英文句子。寫簡單一點。（但不要過度簡化。）

**避免縮寫。** 把字寫完整。對專家的成本很低，對初學者的好處很大。不要寫 IF，寫 instruction following。不要寫 RAG，寫 retrieval-augmented generation（或我偏好的說法：search-ask procedure）。

**主動提供可能問題的解法。** 就算 95% 的讀者都知道怎麼安裝 Python 套件或儲存環境變數，主動解釋仍然值得。加解釋對專家沒什麼成本，他們直接掃過去就好。但不加解釋對初學者成本很高，他們可能卡住甚至放棄。記得，就算是很資深的 JavaScript 或 C++ 工程師，也可能是 Python 的初學者。寧可解釋過頭，不要解釋不夠。

**偏好具體而準確的術語。** 行話不好。要為剛入行的人優化文件，而不是為我們自己。例如不要寫「prompt」，寫「input」。或者不要寫「context limit」，寫「max token limit」。後者比較不需要解釋，大概也比 base model 時代發展出來的行話更好。

**程式範例要通用、可匯出。** 在程式示範中，盡量減少依賴。不要讓使用者多裝額外套件，也不要讓他們在不同頁面或段落之間來回對照。讓範例簡單、自成一體。

**依價值排優先順序。** 涵蓋常見問題的文件（例如怎麼數 token），價值比涵蓋罕見問題的文件（例如怎麼最佳化 emoji 資料庫）高出好幾個數量級。照這個排優先順序。

**不要教壞習慣。** 如果 API key 不該存在程式碼裡，就永遠不要分享把 API key 存在程式碼裡的範例。

**用寬廣的開場介紹主題。** 例如要解釋怎麼寫一個好的 recommender，可以在開頭簡短提到推薦在網路上無所不在，從 YouTube 影片到 Amazon 商品到 Wikipedia。用寬廣的開場為窄主題打底，能讓人在踏入不確定的領域前比較有安全感。如果文字寫得好，已經懂的人也可能讀得開心。

### 有好理由的時候，就打破這些規則

最後，做你覺得最好的事。寫文件是一種同理心的練習。站在讀者的位置，做你認為對他們幫助最大的事。

## 重點整理

- 讀者不會線性閱讀，所以文件要靠標題、目錄、短段落和 topic sentence 讓人快速判斷要不要讀。
- 結論放最前面，標題直接寫出資訊，而不是只寫抽象名詞。
- 句子要能毫無歧義地解析：寫簡單句、避免 left-branching、少用 demonstrative pronoun。
- 對初學者友善的代價很低：不縮寫、主動解釋安裝等常見卡點、用具體準確的術語。
- 範例要自成一體，也不要教壞習慣，例如把 API key 寫進程式碼。

## 練習

1. 找一個你自己寫過的 README，把三個「Results」「Overview」之類的抽象標題改成有資訊量的句子。
2. 把「Embeddings search can be sped up by vector databases」這類被動、主題在句尾的句子，改成主題在句首的版本，再找你文件裡兩句同樣問題的句子一起改。
3. 挑一份你寫的教學，把裡面所有縮寫和 demonstrative pronoun 列出來，逐一改寫，然後找沒看過的人讀一次，記錄他卡在哪裡。
