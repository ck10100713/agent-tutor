---
translated: true
source: examples/vector_databases/chroma/hyde-with-chroma-and-openai.ipynb
---
# 用 Chroma 和 OpenAI 做更穩健的問答

> 原文：[examples/vector_databases/chroma/hyde-with-chroma-and-openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/chroma/hyde-with-chroma-and-openai.ipynb)



## 這篇在做什麼

用開源的 embedding 資料庫 [Chroma](https://trychroma.com)，加上 OpenAI 的 embedding 和 chat completion API，對一批科學論文資料做問答。從直接問模型開始，一步步加上檢索 context、距離門檻過濾，最後用 HyDE（Hypothetical Document Embeddings）改善檢索，看每一步對準確度的影響。

## 學完你會

- 把文件載入 Chroma，用 OpenAI embedding 做檢索，再把檢索結果當 context 丟給 LLM 判斷
- 用距離門檻過濾不相關的文件，並理解它帶來的取捨
- 實作 HyDE：先讓模型幻想出一篇假文件，再拿它去查，改善檢索品質

## 開跑前

- OpenAI API key，設成環境變數 `OPENAI_API_KEY`
- 範例會呼叫 API 做 embedding 和評估，會產生費用；HyDE 那段 100 個 claim 大約要跑 7 分鐘，可以減少 claim 數量

---

這份 notebook 一步一步帶你對一批資料做問答，用的是開源的 embedding 資料庫 [Chroma](https://trychroma.com)，搭配 OpenAI 的 [text embeddings](https://platform.openai.com/docs/guides/embeddings/use-cases) 和 [chat completion](https://platform.openai.com/docs/guides/chat) API。

另外，這份 notebook 也示範讓問答系統更穩健時的一些取捨。你會看到，*單純的查詢不一定產生最好的結果*！

## 用 LLM 做問答

像 OpenAI 的 ChatGPT 這類大型語言模型（LLM），可以拿來回答模型沒訓練過、或沒辦法存取的資料。例如：

- 個人資料，像 e-mail 和筆記
- 高度專門的資料，像檔案庫或法律文件
- 新產生的資料，像最近的新聞

要克服這個限制，可以用一個適合用自然語言查詢的資料庫，就像 LLM 本身一樣。像 Chroma 這樣的 embedding 資料庫，會把文件表示成 [embedding](https://openai.com/blog/introducing-text-and-code-embeddings)，並連同文件本身一起存起來。

把查詢文字做 embedding 後，Chroma 就能找到相關文件，再把這些文件交給 LLM 回答問題。我們會示範這個做法的詳細範例和變化。

# 設定與前置作業

先確認需要的 Python 套件都裝好了。

```python
%pip install -qU openai chromadb pandas
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

整份 notebook 都會用到 OpenAI 的 API。API key 可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

你可以在終端機執行 `export OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` 把 API key 設成環境變數。注意如果環境變數之前還沒設，需要重新載入 notebook。另一個做法是在 notebook 裡設定，看下面。如果是在 Colab，可以直接用下面的方式在 notebook 裡設定。

```python
import os
from openai import OpenAI

# Uncomment the following line to set the environment variable in the notebook
# os.environ["OPENAI_API_KEY"] = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    client = OpenAI(api_key=api_key)
    print("OpenAI client is ready")
else:
    print("OPENAI_API_KEY environment variable not found")
```

??? note "輸出"

    ```text
    OpenAI client is ready
    ```

```python
# Set the model for all API calls
OPENAI_MODEL = "gpt-4o"
```

# 資料集

整份 notebook 用的是 [SciFact 資料集](https://github.com/allenai/scifact)。這是一份專家標註的科學主張（claim）資料集，附帶一份由論文標題和摘要組成的文字語料。根據語料中的文件，每個 claim 可能被支持、被反駁，或是兩邊的證據都不足。

有了語料當 ground truth，就能研究下面幾種 LLM 問答做法的表現如何。

```python
# Load the claim dataset
import pandas as pd

data_path = '../../data'

claim_df = pd.read_json(f'{data_path}/scifact_claims.jsonl', lines=True)
claim_df.head()
```

??? note "輸出"

    ```text
       id                                              claim  \
    0   1  0-dimensional biomaterials show inductive prop...   
    1   3  1,000 genomes project enables mapping of genet...   
    2   5         1/2000 in UK have abnormal PrP positivity.   
    3  13  5% of perinatal mortality is due to low birth ...   
    4  36  A deficiency of vitamin B12 increases blood le...   

                                                evidence        cited_doc_ids  
    0                                                 {}           [31715818]  
    1  {'14717500': [{'sentences': [2, 5], 'label': '...           [14717500]  
    2  {'13734012': [{'sentences': [4], 'label': 'SUP...           [13734012]  
    3                                                 {}            [1606628]  
    4                                                 {}  [5152028, 11705328]
    ```

# 直接問模型

ChatGPT 訓練時用了大量科學資訊。我們想先了解，在沒有任何額外 context 的情況下，模型本來就知道多少，當作基準，才能校準整體表現。

我們建立合適的 prompt，附上一些範例事實，然後拿資料集中每個 claim 去問模型。請模型把 claim 判斷成 'True'、'False'，或證據不足的 'NEE'。

```python
def build_prompt(claim):
    return [
        {"role": "system", "content": "I will ask you to assess a scientific claim. Output only the text 'True' if the claim is true, 'False' if the claim is false, or 'NEE' if there's not enough evidence."},
        {"role": "user", "content": f"""
Example:

Claim:
0-dimensional biomaterials show inductive properties.

Assessment:
False

Claim:
1/2000 in UK have abnormal PrP positivity.

Assessment:
True

Claim:
Aspirin inhibits the production of PGE2.

Assessment:
False

End of examples. Assess the following claim:

Claim:
{claim}

Assessment:
"""}
    ]


def assess_claims(claims):
    responses = []
    # Query the OpenAI API
    for claim in claims:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=build_prompt(claim),
            max_tokens=3,
        )
        # Strip any punctuation or whitespace from the response
        responses.append(response.choices[0].message.content.strip('., '))

    return responses
```

從資料集抽樣 50 個 claim

```python
# Let's take a look at 50 claims
samples = claim_df.sample(50)

claims = samples['claim'].tolist()
```

依照資料集的標註整理 ground truth。從資料集的說明來看，每個 claim 要不是被證據支持或反駁，不然就是兩邊證據都不足。

```python
def get_groundtruth(evidence):
    groundtruth = []
    for e in evidence:
        # Evidence is empty
        if len(e) == 0:
            groundtruth.append('NEE')
        else:
            # In this dataset, all evidence for a given claim is consistent, either SUPPORT or CONTRADICT
            if list(e.values())[0][0]['label'] == 'SUPPORT':
                groundtruth.append('True')
            else:
                groundtruth.append('False')
    return groundtruth
```

```python
evidence = samples['evidence'].tolist()
groundtruth = get_groundtruth(evidence)
```

我們也輸出 confusion matrix，用容易閱讀的表格比較模型的判斷和 ground truth。

```python
def confusion_matrix(inferred, groundtruth):
    assert len(inferred) == len(groundtruth)
    confusion = {
        'True': {'True': 0, 'False': 0, 'NEE': 0},
        'False': {'True': 0, 'False': 0, 'NEE': 0},
        'NEE': {'True': 0, 'False': 0, 'NEE': 0},
    }
    for i, g in zip(inferred, groundtruth):
        confusion[i][g] += 1

    # Pretty print the confusion matrix
    print('\tGroundtruth')
    print('\tTrue\tFalse\tNEE')
    for i in confusion:
        print(i, end='\t')
        for g in confusion[i]:
            print(confusion[i][g], end='\t')
        print()

    return confusion
```

請模型在沒有額外 context 的情況下，直接評估這些 claim。

```python
gpt_inferred = assess_claims(claims)
confusion_matrix(gpt_inferred, groundtruth)
```

??? note "輸出"

    ```text
    	Groundtruth
    	True	False	NEE
    True	9	3	15	
    False	0	3	2	
    NEE	8	6	4
    ```

    ```text
    {'True': {'True': 9, 'False': 3, 'NEE': 15},
     'False': {'True': 0, 'False': 3, 'NEE': 2},
     'NEE': {'True': 8, 'False': 6, 'NEE': 4}}
    ```

## 結果

從結果看到，LLM 很偏向把 claim 判斷成 true，即使它們是 false，而且也傾向把 false 的 claim 判成證據不足。注意這裡的「證據不足」，是指模型在沒有額外 context 下對 claim 的判斷。


# 加入 context

現在加入語料裡的論文標題和摘要當作額外 context。這一段示範怎麼用 OpenAI text embedding 把文字語料載入 Chroma。

首先載入文字語料。

```python
# Load the corpus into a dataframe
corpus_df = pd.read_json(f'{data_path}/scifact_corpus.jsonl', lines=True)
corpus_df.head()
```

??? note "輸出"

    ```text
       doc_id                                              title  \
    0    4983  Microstructural development of human newborn c...   
    1    5836  Induction of myelodysplasia by myeloid-derived...   
    2    7912  BC1 RNA, the transcript from a master gene for...   
    3   18670  The DNA Methylome of Human Peripheral Blood Mo...   
    4   19238  The human myelin basic protein gene is include...   

                                                abstract  structured  
    0  [Alterations of the architecture of cerebral w...       False  
    1  [Myelodysplastic syndromes (MDS) are age-depen...       False  
    2  [ID elements are short interspersed elements (...       False  
    3  [DNA methylation plays an important role in bi...       False  
    4  [Two human Golli (for gene expressed in the ol...       False
    ```

## 把語料載入 Chroma

下一步是把語料載入 Chroma。給定 embedding function，Chroma 會自動幫每份文件做 embedding，並連同文字和 metadata 一起存起來，查詢就很簡單。

我們建立一個（暫存的）Chroma client，並為 SciFact 的標題和摘要語料建立一個 collection。
Chroma 也可以用持久化的方式建立，詳情看 [Chroma 文件](https://docs.trychroma.com/usage-guide?lang=py)。

```python
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# We initialize an embedding function, and provide it to the collection.
embedding_function = OpenAIEmbeddingFunction(api_key=os.getenv("OPENAI_API_KEY"))

chroma_client = chromadb.Client() # Ephemeral by default
scifact_corpus_collection = chroma_client.create_collection(name='scifact_corpus', embedding_function=embedding_function)
```

接著把語料載入 Chroma。因為載入資料很吃記憶體，建議分批載入，每批 50 到 1000 筆。這個例子整份語料大概花一分多鐘。它會在背景自動用我們前面指定的 `embedding_function` 做 embedding。

```python
batch_size = 100

for i in range(0, len(corpus_df), batch_size):
    batch_df = corpus_df[i:i+batch_size]
    scifact_corpus_collection.add(
        ids=batch_df['doc_id'].apply(lambda x: str(x)).tolist(), # Chroma takes string IDs.
        documents=(batch_df['title'] + '. ' + batch_df['abstract'].apply(lambda x: ' '.join(x))).to_list(), # We concatenate the title and abstract.
        metadatas=[{"structured": structured} for structured in batch_df['structured'].to_list()] # We also store the metadata, though we don't use it in this example.
    )
```

## 檢索 context

接著，針對抽樣的每個 claim，從語料中檢索可能相關的文件，當作 context 提供給 LLM 評估 claim。我們依 embedding 距離，檢索最相關的 3 份文件。

```python
claim_query_result = scifact_corpus_collection.query(query_texts=claims, include=['documents', 'distances'], n_results=3)
```

建立新的 prompt，這次把從語料檢索到的額外 context 也納入。

```python
def build_prompt_with_context(claim, context):
    return [{'role': 'system', 'content': "I will ask you to assess whether a particular scientific claim, based on evidence provided. Output only the text 'True' if the claim is true, 'False' if the claim is false, or 'NEE' if there's not enough evidence."},
            {'role': 'user', 'content': f""""
The evidence is the following:

{' '.join(context)}

Assess the following claim on the basis of the evidence. Output only the text 'True' if the claim is true, 'False' if the claim is false, or 'NEE' if there's not enough evidence. Do not output any other text.

Claim:
{claim}

Assessment:
"""}]


def assess_claims_with_context(claims, contexts):
    responses = []
    # Query the OpenAI API
    for claim, context in zip(claims, contexts):
        # If no evidence is provided, return NEE
        if len(context) == 0:
            responses.append('NEE')
            continue
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=build_prompt_with_context(claim=claim, context=context),
            max_tokens=3,
        )
        # Strip any punctuation or whitespace from the response
        responses.append(response.choices[0].message.content.strip('., '))

    return responses
```

然後請模型利用檢索到的 context 評估這些 claim。

```python
gpt_with_context_evaluation = assess_claims_with_context(claims, claim_query_result['documents'])
confusion_matrix(gpt_with_context_evaluation, groundtruth)
```

??? note "輸出"

    ```text
    	Groundtruth
    	True	False	NEE
    True	13	1	4	
    False	1	10	2	
    NEE	3	1	15
    ```

    ```text
    {'True': {'True': 13, 'False': 1, 'NEE': 4},
     'False': {'True': 1, 'False': 10, 'NEE': 2},
     'NEE': {'True': 3, 'False': 1, 'NEE': 15}}
    ```

## 結果

可以看到模型整體表現更好了，現在能明顯更準確地找出 false 的 claim。另外，大部分 NEE 的情況也能正確辨識。

看一下檢索到的文件，會發現它們有時跟 claim 不相關，這會讓模型被多餘的資訊搞混，可能在資訊其實不相關時，仍判斷證據充足。原因是我們總是要求 3 份「最」相關的文件，但超過某個點之後，它們可能一點都不相關。

## 依相關性過濾 context

除了文件本身，Chroma 也會回傳距離分數。我們可以試試對距離設門檻，讓比較少不相關的文件進到提供給模型的 context。

如果過濾後沒有任何 context 文件剩下，我們就跳過模型，直接回傳證據不足。

```python
def filter_query_result(query_result, distance_threshold=0.25):
# For each query result, retain only the documents whose distance is below the threshold
    for ids, docs, distances in zip(query_result['ids'], query_result['documents'], query_result['distances']):
        for i in range(len(ids)-1, -1, -1):
            if distances[i] > distance_threshold:
                ids.pop(i)
                docs.pop(i)
                distances.pop(i)
    return query_result
```

```python
filtered_claim_query_result = filter_query_result(claim_query_result)
```

現在用這個比較乾淨的 context 評估 claim。

```python
gpt_with_filtered_context_evaluation = assess_claims_with_context(claims, filtered_claim_query_result['documents'])
confusion_matrix(gpt_with_filtered_context_evaluation, groundtruth)
```

??? note "輸出"

    ```text
    	Groundtruth
    	True	False	NEE
    True	9	0	1	
    False	0	7	0	
    NEE	8	5	20
    ```

    ```text
    {'True': {'True': 9, 'False': 0, 'NEE': 1},
     'False': {'True': 0, 'False': 7, 'NEE': 0},
     'NEE': {'True': 8, 'False': 5, 'NEE': 20}}
    ```

## 結果


現在模型在證據不足時，判成 True 或 False 的 claim 少很多。不過它也變得謹慎很多，傾向把大部分項目標成證據不足，偏離了確定性。大部分 claim 現在被判成證據不足，因為有很大一部分被距離門檻過濾掉了。可以調整距離門檻找到最佳的操作點，但這不容易，而且依資料集和 embedding 模型而定。

# Hypothetical Document Embeddings：把幻覺變成有用的東西

我們希望檢索到相關文件，又不要檢索到可能讓模型搞混的較不相關文件。一個做法是改善檢索用的查詢。

到目前為止，我們都是用 _claim_（單句敘述）去查資料集，而語料裡是描述一篇科學論文的 _摘要_。直覺上，兩者可能相關，但結構和意義有很大差異。這些差異會被 embedding 模型編碼進去，進而影響查詢和最相關結果之間的距離。

我們可以利用 LLM 生成相關文字的能力來克服這個問題。雖然事實可能是幻覺，但模型生成的文件在內容和結構上，比起原本的查詢，更接近語料裡的文件。這可能帶來更好的查詢，因此有更好的結果。

這個做法叫 [Hypothetical Document Embeddings（HyDE）](https://arxiv.org/abs/2212.10496)，已被證明在檢索任務上相當不錯。它應該能幫我們把更多相關資訊帶進 context，又不會污染它。

簡單說：
- embed 整篇摘要，比 embed 單一句子的匹配好得多
- 但 claim 通常只有一句話
- 所以 HyDE 的做法是用 GPT3 把 claim 擴寫成幻覺出來的摘要，再用這些摘要去搜尋（claim -> 摘要 -> 結果），效果比直接搜尋（claim -> 結果）更好

首先，用 in-context 範例引導模型，針對每個要評估的 claim，生成類似語料中的文件。

```python
def build_hallucination_prompt(claim):
    return [{'role': 'system', 'content': """I will ask you to write an abstract for a scientific paper which supports or refutes a given claim. It should be written in scientific language, include a title. Output only one abstract, then stop.

    An Example:

    Claim:
    A high microerythrocyte count raises vulnerability to severe anemia in homozygous alpha (+)- thalassemia trait subjects.

    Abstract:
    BACKGROUND The heritable haemoglobinopathy alpha(+)-thalassaemia is caused by the reduced synthesis of alpha-globin chains that form part of normal adult haemoglobin (Hb). Individuals homozygous for alpha(+)-thalassaemia have microcytosis and an increased erythrocyte count. Alpha(+)-thalassaemia homozygosity confers considerable protection against severe malaria, including severe malarial anaemia (SMA) (Hb concentration < 50 g/l), but does not influence parasite count. We tested the hypothesis that the erythrocyte indices associated with alpha(+)-thalassaemia homozygosity provide a haematological benefit during acute malaria.
    METHODS AND FINDINGS Data from children living on the north coast of Papua New Guinea who had participated in a case-control study of the protection afforded by alpha(+)-thalassaemia against severe malaria were reanalysed to assess the genotype-specific reduction in erythrocyte count and Hb levels associated with acute malarial disease. We observed a reduction in median erythrocyte count of approximately 1.5 x 10(12)/l in all children with acute falciparum malaria relative to values in community children (p < 0.001). We developed a simple mathematical model of the linear relationship between Hb concentration and erythrocyte count. This model predicted that children homozygous for alpha(+)-thalassaemia lose less Hb than children of normal genotype for a reduction in erythrocyte count of >1.1 x 10(12)/l as a result of the reduced mean cell Hb in homozygous alpha(+)-thalassaemia. In addition, children homozygous for alpha(+)-thalassaemia require a 10% greater reduction in erythrocyte count than children of normal genotype (p = 0.02) for Hb concentration to fall to 50 g/l, the cutoff for SMA. We estimated that the haematological profile in children homozygous for alpha(+)-thalassaemia reduces the risk of SMA during acute malaria compared to children of normal genotype (relative risk 0.52; 95% confidence interval [CI] 0.24-1.12, p = 0.09).
    CONCLUSIONS The increased erythrocyte count and microcytosis in children homozygous for alpha(+)-thalassaemia may contribute substantially to their protection against SMA. A lower concentration of Hb per erythrocyte and a larger population of erythrocytes may be a biologically advantageous strategy against the significant reduction in erythrocyte count that occurs during acute infection with the malaria parasite Plasmodium falciparum. This haematological profile may reduce the risk of anaemia by other Plasmodium species, as well as other causes of anaemia. Other host polymorphisms that induce an increased erythrocyte count and microcytosis may confer a similar advantage.

    End of example.

    """}, {'role': 'user', 'content': f""""
    Perform the task for the following claim.

    Claim:
    {claim}

    Abstract:
    """}]


def hallucinate_evidence(claims):
    responses = []
    # Query the OpenAI API
    for claim in claims:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=build_hallucination_prompt(claim),
        )
        responses.append(response.choices[0].message.content)
    return responses
```

我們為每個 claim 幻想出一份文件。

*注意：這可能要跑一陣子，100 個 claim 約 7 分鐘*。可以減少要評估的 claim 數量，更快拿到結果。

```python
hallucinated_evidence = hallucinate_evidence(claims)
```

用這些幻想出來的文件當查詢去查語料，並用同樣的距離門檻過濾結果。

```python
hallucinated_query_result = scifact_corpus_collection.query(query_texts=hallucinated_evidence, include=['documents', 'distances'], n_results=3)
filtered_hallucinated_query_result = filter_query_result(hallucinated_query_result)
```

接著請模型用新的 context 評估這些 claim。

```python
gpt_with_hallucinated_context_evaluation = assess_claims_with_context(claims, filtered_hallucinated_query_result['documents'])
confusion_matrix(gpt_with_hallucinated_context_evaluation, groundtruth)
```

??? note "輸出"

    ```text
    	Groundtruth
    	True	False	NEE
    True	13	0	3	
    False	1	10	1	
    NEE	3	2	17
    ```

    ```text
    {'True': {'True': 13, 'False': 0, 'NEE': 3},
     'False': {'True': 1, 'False': 10, 'NEE': 1},
     'NEE': {'True': 3, 'False': 2, 'NEE': 17}}
    ```

## 結果

把 HyDE 和簡單的距離門檻結合，帶來明顯的改善。模型不再偏向判成 True，也不再偏向證據不足。在真的證據不足時，它也更常正確判斷出來。

# 結論

用文件語料給 LLM 配上 context，是把 LLM 的通用推理和自然語言互動能力，用在你自己資料上的強大技巧。不過要知道，天真的查詢和檢索不一定產生最好的結果！最終，了解你的資料才能讓以檢索為基礎的問答發揮最大效果。

## 重點整理

- 沒有 context 時，LLM 會偏向把 claim 判成 True，補上檢索到的文件能明顯改善。
- 固定取前 k 筆會混進不相關文件，模型可能被誤導，所以要看距離分數過濾。
- 距離門檻是取捨：過濾太狠就變成什麼都判證據不足，而且最佳值依資料集和 embedding 模型而定。
- HyDE 用 LLM 把短查詢擴寫成像語料的假文件再檢索，查詢和文件的結構更接近，檢索更準，幻覺的事實內容不重要。
- 檢索式問答的效果取決於你對資料的了解，不要只靠預設的查詢。

## 練習

1. 把檢索文件數從 3 改成 1 或 5，重跑 context 版本，看 confusion matrix 怎麼變。
2. 調整距離門檻（例如放寬或收緊），觀察被判成證據不足的 claim 比例。
3. 修改 HyDE 的 prompt 或範例，讓生成的假文件更短或更像真實摘要，比較最後的判斷準確度。
