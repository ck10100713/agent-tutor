---
translated: true
source: examples/book_translation/translate_latex_book.ipynb
---

# 把斯洛維尼亞文的 LaTeX 書翻成英文

> 原文：[examples/book_translation/translate_latex_book.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/book_translation/translate_latex_book.ipynb)



## 這篇在做什麼
這篇取得作者同意後，示範怎麼把 Milan Mitrović 用斯洛維尼亞文寫的《[Euclidean Plane Geometry](https://sites.google.com/site/projektivna/)》翻成英文，而且不動任何 LaTeX 指令。
做法是先把整本書切成大約一頁長的 chunk，逐塊翻成英文，最後再拼回去。

## 學完你會
- 用 tokenizer 算每個 chunk 的 token 數，挑出合適的切分方式。
- 把短 chunk 合併成接近 15000 token 的大塊，讓翻譯更連貫。
- 用範例指令引導模型只翻文字、不動 LaTeX 指令，並批次翻完整本書。

## 開跑前
- 需要 OpenAI API key。
- 整本書依序送出請求，原文說大約要 2 到 3 小時，也會產生 API 費用。

## 1. 讀入資料

```python
from openai import OpenAI
import tiktoken
client = OpenAI()

# OpenAI tiktoken tokenizer: https://github.com/openai/tiktoken
# we use it to count the number of tokens in the text
tokenizer = tiktoken.get_encoding("o200k_base")

with open("data/geometry_slovenian.tex", "r") as f:
    text = f.read()
```

### 1.1 計算每個 chunk 的 token 數

```python
chunks = text.split('\n\n')
ntokens = []
for chunk in chunks:
    ntokens.append(len(tokenizer.encode(chunk)))
print("Size of the largest chunk: ", max(ntokens))
print("Number of chunks: ", len(chunks))
```

??? note "輸出"

    ```text
    Size of the largest chunk:  1211
    Number of chunks:  5877
    ```

結果是用兩個換行當分隔符號最合適，不會打斷文章的流暢度，而且沒有任何一個 chunk 超過 1211 個 token。我們用的模型是 gpt-4o，輸出上限 16,384 token，所以不用再把 chunk 切更小。

接著把較短的 chunk 合併成約 15000 token 的大塊，這樣文字更連貫，中間斷開的次數也更少。

```python
def group_chunks(chunks, ntokens, max_len=15000, hard_max_len=16000):
    """
    Group very short chunks, to form approximately page long chunks.
    """
    batches = []
    cur_batch = ""
    cur_tokens = 0
    
    # iterate over chunks, and group the short ones together
    for chunk, ntoken in zip(chunks, ntokens):
        # discard chunks that exceed hard max length
        if ntoken > hard_max_len:
            print(f"Warning: Chunk discarded for being too long ({ntoken} tokens > {hard_max_len} token limit). Preview: '{chunk[:50]}...'")
            continue

        # if room in current batch, add new chunk
        if cur_tokens + 1 + ntoken <= max_len:
            cur_batch += "\n\n" + chunk
            cur_tokens += 1 + ntoken  # adds 1 token for the two newlines
        # otherwise, record the batch and start a new one
        else:
            batches.append(cur_batch)
            cur_batch = chunk
            cur_tokens = ntoken
            
    if cur_batch:  # add the last batch if it's not empty
        batches.append(cur_batch)
        
    return batches


chunks = group_chunks(chunks, ntokens)
len(chunks)
```

??? note "輸出"

    ```text
    39
    ```

注意，在 prompt 裡加一組「未翻譯與翻譯後」的範例指令（只有章節名稱的內容需要翻譯），能讓結果更一致。

送給模型的 prompt 格式如下：
1. 一句高層指令：只翻譯文字，不翻譯指令，翻成指定語言
2. 一個未翻譯的範例指令，其中只有章節名稱的內容需要翻譯
3. 要翻譯的文字 chunk
4. 第 2 點範例指令的翻譯版本，讓模型看到翻譯的開頭怎麼起

預期輸出就是翻譯完的文字 chunk。

```python
def translate_chunk(chunk, model='gpt-4o',
                    dest_language='English',
                    sample_translation=(
                    r"\poglavje{Osnove Geometrije} \label{osn9Geom}",
                    r"\chapter{The basics of Geometry} \label{osn9Geom}")):
    prompt = f'''Translate only the text from the following LaTeX document into {dest_language}. Leave all LaTeX commands unchanged
    
"""
{sample_translation[0]}
{chunk}"""

{sample_translation[1]}
'''
    response = client.chat.completions.create(
        messages=[{"role": "user", "content":prompt}],
        model=model,
        temperature=0,
        top_p=1,
        max_tokens=15000,
    )
    result = response.choices[0].message.content.strip()
    result = result.replace('"""', '') # remove the double quotes, as we used them to surround the text
    return result
print(translate_chunk(chunks[2], model='gpt-4o', dest_language='English'))
```

??? note "輸出"

    ```text
    Certainly! Here's the translation of the text from the LaTeX document into English, with all LaTeX commands unchanged:

    ---

    \chapter{The basics of Geometry} \label{osn9Geom}
    Let us mention that the group structure also requires the property of associativity, i.e., $\mathcal{I}_1\circ (\mathcal{I}_2\circ \mathcal{I}_3)= (\mathcal{I}_1\circ \mathcal{I}_2)\circ \mathcal{I}_3$ (for arbitrary isometries $\mathcal{I}_1$, $\mathcal{I}_2$, and $\mathcal{I}_3$), which is automatically fulfilled in the operation of function composition. Let us also mention that the \concept{identity} \index{identity} $\mathcal{E}$ from the previous axiom is a mapping for which $\mathcal{E}(A)=A$ for every point of the plane. The mapping $\mathcal{I}^{-1}$ is the \concept{inverse mapping} for the isometry $\mathcal{I}$ if $\mathcal{I}^{-1}\circ \mathcal{I} =\mathcal{I}\circ\mathcal{I}^{-1}=\mathcal{E}$. According to the previous axiom, the identity and inverse mapping of each isometry are also isometries.

    Let us prove the first consequences of the axioms of congruence. First, we will consider the following properties of isometries.

    \begin{theorem} \label{izrekIzoB} Isometry maps a line to a line, a line segment to a line segment, a ray to a ray, a half-plane to a half-plane, an angle to an angle, and an $n$-gon to an $n$-gon.
    \end{theorem}

    \textbf{\textit{Proof.}}
    According to axiom \ref{aksIII1}, isometries preserve the relation $\mathcal{B}$. Therefore, all points of the line segment $AB$ under the isometry $I$ are mapped to points lying on the line segment $A'B'$, where $A'=\mathcal{I}(A)$ and $B'=\mathcal{I}(B)$. Since the inverse mapping $\mathcal{I}^{-1}$ is also an isometry (axiom \ref{aksIII4}), every point of the line segment $A'B'$ is the image of some point lying on the line segment $AB$. Thus, the line segment $AB$ is mapped to the line segment $A'B'$ by the isometry $\mathcal{I}$.

    The remaining figures from the theorem are also defined using the relation $\mathcal{B}$, so the proof is similar to that for the line segment.
    \qed

    From the proof of the previous theorem, it follows that the endpoints of the line segment $AB$ are mapped to the endpoints of the image $A'B'$ by the isometry. Similarly, the origin of a ray is mapped to the origin of the ray, the edge of a half-plane to the edge of a half-plane, the vertex of an angle to the vertex of an angle, and the vertex of a polygon to the vertex of a polygon.

    Isometries are defined as bijective mappings that preserve the congruence of pairs of points. Is it also true that for congruent pairs of points, there exists an isometry that maps the first pair to the second? Let us provide the answer with the following theorem.

    \begin{theorem} \label{izrekAB} If $(A,B)\cong (A',B')$, then there is an isometry $\mathcal{I}$, which maps the points $A$ and $B$ to the points $A'$ and $B'$, i.e.:
    $$\mathcal{I}: A, B\mapsto A',B'.$$
    \end{theorem}

    \begin{figure}[!htb]
    \centering
    \input{sl.aks.2.3.7.pic}
    \caption{} \label{sl.aks.2.3.7.pic}
    \end{figure}

    \textbf{\textit{Proof.}}
    Let $C$ be a point that does not lie on the line $AB$, and $C'$ a point that does not lie on the line $A'B'$ (Figure \ref{sl.aks.2.3.7.pic}). According to axiom \ref{aksIII2}, there exists a unique isometry $\mathcal{I}$ that maps the point $A$ to the point $A'$, the ray $AB$ to the ray $A'B'$, and the half-plane $ABC$ to the half-plane $A'B'C'$. Since by assumption $(A,B)\cong (A',B')$ from the same axiom \ref{aksIII2}, it follows that $\mathcal{I}(B)=B'$.
    \qed

    The proof of the following theorem is similar, which will later be presented in a different form as the first theorem on the congruence of triangles.

    \begin{theorem} \label{IizrekABC} Let $(A,B,C)$ and $(A',B',C')$ be triplets of non-collinear points such that $$(A,B,C)\cong (A',B',C'),$$ then there is a single isometry $\mathcal{I}$, that maps the points $A$, $B$, and $C$ into the points $A'$, $B'$, and $C'$, i.e.:
    $$\mathcal{I}: A, B,C\mapsto A',B',C'.$$
    ... (省略 439 行)
    ```

可以看到這個 chunk 只翻了文字，LaTeX 指令都完整保留。

現在來翻整本書的所有 chunk。因為請求是依序處理，這會跑 2 到 3 個小時。

```python
dest_language = "English"

translated_chunks = []
for i, chunk in enumerate(chunks):
    print(str(i+1) + " / " + str(len(chunks)))
    # translate each chunk
    translated_chunks.append(translate_chunk(chunk, model='gpt-4o', dest_language=dest_language))

# join the chunks together
result = '\n\n'.join(translated_chunks)

# save the final result
with open(f"data/geometry_{dest_language}.tex", "w") as f:
    f.write(result)
```

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# Function to translate a single chunk
def translate_chunk_wrapper(chunk, model='gpt-4o', dest_language='English'):
    return translate_chunk(chunk, model=model, dest_language=dest_language)

# Set the destination language
dest_language = "English"

# List to store translated chunks
translated_chunks = []

# Use ThreadPoolExecutor to parallelize the translation
with ThreadPoolExecutor(max_workers=5) as executor:
    # Submit all translation tasks
    futures = {executor.submit(translate_chunk_wrapper, chunk, 'gpt-4o', dest_language): i for i, chunk in enumerate(chunks)}
    
    # Process completed tasks as they finish
    for future in as_completed(futures):
        i = futures[future]
        try:
            translated_chunk = future.result()
            translated_chunks.append(translated_chunk)
            print(f"Chunk {i+1} / {len(chunks)} translated.")
        except Exception as e:
            print(f"Chunk {i+1} failed with exception: {e}")

# Join the translated chunks together
result = '\n\n'.join(translated_chunks)

# Save the final result
with open(f"data/geometry_{dest_language}.tex", "w") as f:
    f.write(result)
```

??? note "輸出"

    ```text
    Chunk 1 / 39 translated.
    Chunk 3 / 39 translated.
    Chunk 5 / 39 translated.
    Chunk 2 / 39 translated.
    Chunk 6 / 39 translated.
    Chunk 4 / 39 translated.
    Chunk 8 / 39 translated.
    Chunk 7 / 39 translated.
    Chunk 9 / 39 translated.
    Chunk 14 / 39 translated.
    Chunk 10 / 39 translated.
    Chunk 11 / 39 translated.
    ```

## 重點整理
- 長文件翻譯要先切 chunk，並用 token 數確認每塊都在模型上限內。
- 合併成較大的 chunk 可以減少斷點，提高前後文一致性。
- prompt 裡放一個「翻譯開頭」的範例，是讓模型守住格式（不動 LaTeX）的簡單有效做法。
- 請求依序送出雖然慢，但實作單純；要加速可以改成平行請求，不過要自己處理順序和限流。

## 練習
1. 把分隔符號從兩個換行改成單一換行，重新算 token 數，看 chunk 數量和最大 token 數怎麼變。
2. 改 prompt 裡的目標語言（例如翻成日文），只翻一個 chunk，檢查 LaTeX 指令有沒有被保留。
3. 把合併 chunk 的 token 上限從 15000 改成 5000，比較翻譯的 chunk 數量和單塊翻譯結果的連貫程度。
