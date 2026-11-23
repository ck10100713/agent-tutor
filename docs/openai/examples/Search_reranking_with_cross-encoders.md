---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Search_reranking_with_cross-encoders.ipynb
---

# 用 cross-encoder 做搜尋結果重排序

> 原文：[examples/Search_reranking_with_cross-encoders.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Search_reranking_with_cross-encoders.ipynb)



## 這篇在做什麼
示範怎麼用 GPT 當 cross-encoder，對 arXiv 搜尋結果做 re-rank。做法是 few-shot prompt 判斷 Yes/No，再用 logprobs 排序。

## 學完你會
- 分清楚 bi-encoder 和 cross-encoder 的成本與準確度差異，知道為什麼要兩階段搭配。
- 用 Completions endpoint、few-shot 範例和 `logit_bias` 做出 Yes/No 相關性分類器。
- 用 ` Yes` 的 logprobs 當分數，把搜尋結果重新排序。

## 開跑前
- 需要 OpenAI API key。
- 範例用 arXiv 搜尋服務取得候選文件，需要能連外網。
- 原文用的 `text-davinci-003` 是舊模型，實際跑要換成你帳號可用的模型。

這個 notebook 帶你用 cross-encoder 對搜尋結果重排序。

這是客戶常見的使用情境：你已經用 embeddings（由 [bi-encoder](https://www.sbert.net/examples/applications/retrieve_rerank/README.html#retrieval-bi-encoder) 產生）做了語意搜尋，但結果不夠準，達不到你的需求。一個可能的原因是，你可以用一些商業規則來重排文件，例如文件有多新、多熱門。

不過很多時候，決定相關性的是一些細微、跟領域有關的規則，這時 cross-encoder 就派得上用場。Cross-encoder 比 bi-encoder 準，但擴展性不好，所以最適合拿來重新排序語意搜尋回傳的精簡清單。

### 範例

假設搜尋任務有 D 份文件和 Q 個 query。

暴力法是計算每一組配對的相關性，成本隨 ```D * Q``` 成長。這叫做 **cross-encoding**。

比較快的做法是 **embeddings-based search**：每份文件和每個 query 各算一次 embedding，之後重複使用來便宜地算配對相關性。因為 embedding 只算一次，成本隨 ```D + Q``` 成長。這叫做 **bi-encoding**。

Embeddings 搜尋比較快，但品質可能較差。要兩者兼得，常見做法是先用 embeddings（或其他 bi-encoder）便宜地找出前幾名候選，再用 GPT（或其他 cross-encoder）花比較多成本重排這些候選。這種混合做法的成本隨 ```(D + Q) * cost of embedding + (N * Q) * cost of re-ranking```, where ```N``` 成長，其中 N 是要重排的候選數。

### 流程

為了示範這個做法，我們用 ```text-davinci-003``` with ```logprobs``` enabled 來做一個 GPT 驅動的 cross-encoder。GPT 模型有很強的通用語言理解能力，加上幾個 few-shot 範例調整後，就是簡單又有效的 cross-encoding 選項。

這個 notebook 參考了 Weaviate 的這篇[好文章](https://weaviate.io/blog/cross-encoders-as-reranker)，以及 Sentence Transformers 對 bi-encoder 和 cross-encoder 的[精彩說明](https://www.sbert.net/examples/applications/cross-encoder/README.html)。

```python
!pip install openai
!pip install arxiv
!pip install tenacity
!pip install pandas
!pip install tiktoken
```

```python
import arxiv
from math import exp
import openai
import os
import pandas as pd
from tenacity import retry, wait_random_exponential, stop_after_attempt
import tiktoken

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

OPENAI_MODEL = "gpt-4"
```

## 搜尋

這個範例用 arXiv 搜尋服務，但這一步可以換成任何你有的搜尋服務。重點是稍微多抓一些，把所有可能相關的文件都納進來，再重新排序。


```python
query = "how do bi-encoders work for sentence embeddings"
search = arxiv.Search(
    query=query, max_results=20, sort_by=arxiv.SortCriterion.Relevance
)
```

```python
result_list = []

for result in search.results():
    result_dict = {}

    result_dict.update({"title": result.title})
    result_dict.update({"summary": result.summary})

    # Taking the first url provided
    result_dict.update({"article_url": [x.href for x in result.links][0]})
    result_dict.update({"pdf_url": [x.href for x in result.links][1]})
    result_list.append(result_dict)
```

```python
result_list[0]
```

??? note "輸出"

    ```text
    {'title': 'SBERT studies Meaning Representations: Decomposing Sentence Embeddings into Explainable Semantic Features',
     'summary': 'Models based on large-pretrained language models, such as S(entence)BERT,\nprovide effective and efficient sentence embeddings that show high correlation\nto human similarity ratings, but lack interpretability. On the other hand,\ngraph metrics for graph-based meaning representations (e.g., Abstract Meaning\nRepresentation, AMR) can make explicit the semantic aspects in which two\nsentences are similar. However, such metrics tend to be slow, rely on parsers,\nand do not reach state-of-the-art performance when rating sentence similarity.\n  In this work, we aim at the best of both worlds, by learning to induce\n$S$emantically $S$tructured $S$entence BERT embeddings (S$^3$BERT). Our\nS$^3$BERT embeddings are composed of explainable sub-embeddings that emphasize\nvarious semantic sentence features (e.g., semantic roles, negation, or\nquantification). We show how to i) learn a decomposition of the sentence\nembeddings into semantic features, through approximation of a suite of\ninterpretable AMR graph metrics, and how to ii) preserve the overall power of\nthe neural embeddings by controlling the decomposition learning process with a\nsecond objective that enforces consistency with the similarity ratings of an\nSBERT teacher model. In our experimental studies, we show that our approach\noffers interpretability -- while fully preserving the effectiveness and\nefficiency of the neural sentence embeddings.',
     'article_url': 'http://arxiv.org/abs/2206.07023v2',
     'pdf_url': 'http://arxiv.org/pdf/2206.07023v2'}
    ```

```python
for i, result in enumerate(result_list):
    print(f"{i + 1}: {result['title']}")
```

??? note "輸出"

    ```text
    1: SBERT studies Meaning Representations: Decomposing Sentence Embeddings into Explainable Semantic Features
    2: Are Classes Clusters?
    3: Semantic Composition in Visually Grounded Language Models
    4: Evaluating the Construct Validity of Text Embeddings with Application to Survey Questions
    5: Learning Probabilistic Sentence Representations from Paraphrases
    6: Exploiting Twitter as Source of Large Corpora of Weakly Similar Pairs for Semantic Sentence Embeddings
    7: How to Probe Sentence Embeddings in Low-Resource Languages: On Structural Design Choices for Probing Task Evaluation
    8: Clustering and Network Analysis for the Embedding Spaces of Sentences and Sub-Sentences
    9: Vec2Sent: Probing Sentence Embeddings with Natural Language Generation
    10: Non-Linguistic Supervision for Contrastive Learning of Sentence Embeddings
    11: SentPWNet: A Unified Sentence Pair Weighting Network for Task-specific Sentence Embedding
    12: Learning Joint Representations of Videos and Sentences with Web Image Search
    13: Character-based Neural Networks for Sentence Pair Modeling
    14: Train Once, Test Anywhere: Zero-Shot Learning for Text Classification
    15: Hierarchical GPT with Congruent Transformers for Multi-Sentence Language Models
    16: Sentence-T5: Scalable Sentence Encoders from Pre-trained Text-to-Text Models
    17: In Search for Linear Relations in Sentence Embedding Spaces
    18: Learning to Borrow -- Relation Representation for Without-Mention Entity-Pairs for Knowledge Graph Completion
    19: Efficient and Flexible Topic Modeling using Pretrained Embeddings and Bag of Sentences
    20: Relational Sentence Embedding for Flexible Semantic Matching
    ```

## Cross-encoder

我們用 ```Completions``` endpoint 建立 cross-encoder，關鍵考量有：
- 讓範例貼近你的領域。Cross-encoder 的強項在於依你的領域客製化。
- 重排的候選數量和處理速度之間要取捨。可以考慮把 cross-encoder 的請求做 batch 和平行處理來加快速度。

步驟如下：
- 建一個評估相關性的 prompt，並提供 few-shot 範例讓它適應你的領域。
- 加 ```logit bias``` for the tokens for ``` Yes``` and ``` No```，也就是對這兩個 token 加 bias，降低其他 token 出現的機率。
- 回傳 yes/no 的分類結果以及 ```logprobs```。
- Rerank the results by the ```logprobs``` keyed on ``` Yes```，也就是用 ``` Yes``` 的 logprobs 重排結果。

```python
tokens = [" Yes", " No"]
tokenizer = tiktoken.encoding_for_model(OPENAI_MODEL)
ids = [tokenizer.encode(token) for token in tokens]
ids[0], ids[1]
```

??? note "輸出"

    ```text
    ([3363], [1400])
    ```

```python
prompt = '''
You are an Assistant responsible for helping detect whether the retrieved document is relevant to the query. For a given input, you need to output a single token: "Yes" or "No" indicating the retrieved document is relevant to the query.

Query: How to plant a tree?
Document: """Cars were invented in 1886, when German inventor Carl Benz patented his Benz Patent-Motorwagen.[3][4][5] Cars became widely available during the 20th century. One of the first cars affordable by the masses was the 1908 Model T, an American car manufactured by the Ford Motor Company. Cars were rapidly adopted in the US, where they replaced horse-drawn carriages.[6] In Europe and other parts of the world, demand for automobiles did not increase until after World War II.[7] The car is considered an essential part of the developed economy."""
Relevant: No

Query: Has the coronavirus vaccine been approved?
Document: """The Pfizer-BioNTech COVID-19 vaccine was approved for emergency use in the United States on December 11, 2020."""
Relevant: Yes

Query: What is the capital of France?
Document: """Paris, France's capital, is a major European city and a global center for art, fashion, gastronomy and culture. Its 19th-century cityscape is crisscrossed by wide boulevards and the River Seine. Beyond such landmarks as the Eiffel Tower and the 12th-century, Gothic Notre-Dame cathedral, the city is known for its cafe culture and designer boutiques along the Rue du Faubourg Saint-Honoré."""
Relevant: Yes

Query: What are some papers to learn about PPO reinforcement learning?
Document: """Proximal Policy Optimization and its Dynamic Version for Sequence Generation: In sequence generation task, many works use policy gradient for model optimization to tackle the intractable backpropagation issue when maximizing the non-differentiable evaluation metrics or fooling the discriminator in adversarial learning. In this paper, we replace policy gradient with proximal policy optimization (PPO), which is a proved more efficient reinforcement learning algorithm, and propose a dynamic approach for PPO (PPO-dynamic). We demonstrate the efficacy of PPO and PPO-dynamic on conditional sequence generation tasks including synthetic experiment and chit-chat chatbot. The results show that PPO and PPO-dynamic can beat policy gradient by stability and performance."""
Relevant: Yes

Query: Explain sentence embeddings
Document: """Inside the bubble: exploring the environments of reionisation-era Lyman-α emitting galaxies with JADES and FRESCO: We present a study of the environments of 16 Lyman-α emitting galaxies (LAEs) in the reionisation era (5.8<z<8) identified by JWST/NIRSpec as part of the JWST Advanced Deep Extragalactic Survey (JADES). Unless situated in sufficiently (re)ionised regions, Lyman-α emission from these galaxies would be strongly absorbed by neutral gas in the intergalactic medium (IGM). We conservatively estimate sizes of the ionised regions required to reconcile the relatively low Lyman-α velocity offsets (ΔvLyα<300kms−1) with moderately high Lyman-α escape fractions (fesc,Lyα>5%) observed in our sample of LAEs, indicating the presence of ionised ``bubbles'' with physical sizes of the order of 0.1pMpc≲Rion≲1pMpc in a patchy reionisation scenario where the bubbles are embedded in a fully neutral IGM. Around half of the LAEs in our sample are found to coincide with large-scale galaxy overdensities seen in FRESCO at z∼5.8-5.9 and z∼7.3, suggesting Lyman-α transmission is strongly enhanced in such overdense regions, and underlining the importance of LAEs as tracers of the first large-scale ionised bubbles. Considering only spectroscopically confirmed galaxies, we find our sample of UV-faint LAEs (MUV≳−20mag) and their direct neighbours are generally not able to produce the required ionised regions based on the Lyman-α transmission properties, suggesting lower-luminosity sources likely play an important role in carving out these bubbles. These observations demonstrate the combined power of JWST multi-object and slitless spectroscopy in acquiring a unique view of the early stages of Cosmic Reionisation via the most distant LAEs."""
Relevant: No

Query: {query}
Document: """{document}"""
Relevant:
'''


@retry(wait=wait_random_exponential(min=1, max=40), stop=stop_after_attempt(3))
def document_relevance(query, document):
    response = openai.chat.completions.create(
        model="text-davinci-003",
        message=prompt.format(query=query, document=document),
        temperature=0,
        logprobs=True,
        logit_bias={3363: 1, 1400: 1},
    )

    return (
        query,
        document,
        response.choices[0].message.content,
        response.choices[0].logprobs.token_logprobs[0],
    )
```

```python
content = result_list[0]["title"] + ": " + result_list[0]["summary"]

# Set logprobs to 1 so our response will include the most probable token the model identified
response = openai.chat.completions.create(
    model=OPENAI_MODEL,
    prompt=prompt.format(query=query, document=content),
    temperature=0,
    logprobs=1,
    logit_bias={3363: 1, 1400: 1},
    max_tokens=1,
)
```

```python
result = response.choices[0]
print(f"Result was {result.message.content}")
print(f"Logprobs was {result.logprobs.token_logprobs[0]}")
print("\nBelow is the full logprobs object\n\n")
print(result["logprobs"])
```

??? note "輸出"

    ```text
    Result was Yes
    Logprobs was -0.05869877

    Below is the full logprobs object


    {
      "tokens": [
        "Yes"
      ],
      "token_logprobs": [
        -0.05869877
      ],
      "top_logprobs": [
        {
          "Yes": -0.05869877
        }
      ],
      "text_offset": [
        5764
      ]
    }
    ```

```python
output_list = []
for x in result_list:
    content = x["title"] + ": " + x["summary"]

    try:
        output_list.append(document_relevance(query, document=content))

    except Exception as e:
        print(e)
```

```python
output_list[:10]
```

??? note "輸出"

    ```text
    [('how do bi-encoders work for sentence embeddings',
      'SBERT studies Meaning Representations: Decomposing Sentence Embeddings into Explainable Semantic Features: Models based on large-pretrained language models, such as S(entence)BERT,\nprovide effective and efficient sentence embeddings that show high correlation\nto human similarity ratings, but lack interpretability. On the other hand,\ngraph metrics for graph-based meaning representations (e.g., Abstract Meaning\nRepresentation, AMR) can make explicit the semantic aspects in which two\nsentences are similar. However, such metrics tend to be slow, rely on parsers,\nand do not reach state-of-the-art performance when rating sentence similarity.\n  In this work, we aim at the best of both worlds, by learning to induce\n$S$emantically $S$tructured $S$entence BERT embeddings (S$^3$BERT). Our\nS$^3$BERT embeddings are composed of explainable sub-embeddings that emphasize\nvarious semantic sentence features (e.g., semantic roles, negation, or\nquantification). We show how to i) learn a decomposition of the sentence\nembeddings into semantic features, through approximation of a suite of\ninterpretable AMR graph metrics, and how to ii) preserve the overall power of\nthe neural embeddings by controlling the decomposition learning process with a\nsecond objective that enforces consistency with the similarity ratings of an\nSBERT teacher model. In our experimental studies, we show that our approach\noffers interpretability -- while fully preserving the effectiveness and\nefficiency of the neural sentence embeddings.',
      'Yes',
      -0.05326408),
     ('how do bi-encoders work for sentence embeddings',
      'Are Classes Clusters?: Sentence embedding models aim to provide general purpose embeddings for\nsentences. Most of the models studied in this paper claim to perform well on\nSTS tasks - but they do not report on their suitability for clustering. This\npaper looks at four recent sentence embedding models (Universal Sentence\nEncoder (Cer et al., 2018), Sentence-BERT (Reimers and Gurevych, 2019), LASER\n(Artetxe and Schwenk, 2019), and DeCLUTR (Giorgi et al., 2020)). It gives a\nbrief overview of the ideas behind their implementations. It then investigates\nhow well topic classes in two text classification datasets (Amazon Reviews (Ni\net al., 2019) and News Category Dataset (Misra, 2018)) map to clusters in their\ncorresponding sentence embedding space. While the performance of the resulting\nclassification model is far from perfect, it is better than random. This is\ninteresting because the classification model has been constructed in an\nunsupervised way. The topic classes in these real life topic classification\ndatasets can be partly reconstructed by clustering the corresponding sentence\nembeddings.',
      'No',
      -0.009535169),
     ('how do bi-encoders work for sentence embeddings',
      "Semantic Composition in Visually Grounded Language Models: What is sentence meaning and its ideal representation? Much of the expressive\npower of human language derives from semantic composition, the mind's ability\nto represent meaning hierarchically & relationally over constituents. At the\nsame time, much sentential meaning is outside the text and requires grounding\nin sensory, motor, and experiential modalities to be adequately learned.\nAlthough large language models display considerable compositional ability,\nrecent work shows that visually-grounded language models drastically fail to\nrepresent compositional structure. In this thesis, we explore whether & how\nmodels compose visually grounded semantics, and how we might improve their\nability to do so.\n  Specifically, we introduce 1) WinogroundVQA, a new compositional visual\nquestion answering benchmark, 2) Syntactic Neural Module Distillation, a\nmeasure of compositional ability in sentence embedding models, 3) Causal\nTracing for Image Captioning Models to locate neural representations vital for\nvision-language composition, 4) Syntactic MeanPool to inject a compositional\ninductive bias into sentence embeddings, and 5) Cross-modal Attention\nCongruence Regularization, a self-supervised objective function for\nvision-language relation alignment. We close by discussing connections of our\nwork to neuroscience, psycholinguistics, formal semantics, and philosophy.",
      'No',
      -0.008887106),
     ('how do bi-encoders work for sentence embeddings',
      "Evaluating the Construct Validity of Text Embeddings with Application to Survey Questions: Text embedding models from Natural Language Processing can map text data\n(e.g. words, sentences, documents) to supposedly meaningful numerical\nrepresentations (a.k.a. text embeddings). While such models are increasingly\napplied in social science research, one important issue is often not addressed:\nthe extent to which these embeddings are valid representations of constructs\nrelevant for social science research. We therefore propose the use of the\nclassic construct validity framework to evaluate the validity of text\nembeddings. We show how this framework can be adapted to the opaque and\nhigh-dimensional nature of text embeddings, with application to survey\nquestions. We include several popular text embedding methods (e.g. fastText,\nGloVe, BERT, Sentence-BERT, Universal Sentence Encoder) in our construct\nvalidity analyses. We find evidence of convergent and discriminant validity in\nsome cases. We also show that embeddings can be used to predict respondent's\nanswers to completely new survey questions. Furthermore, BERT-based embedding\ntechniques and the Universal Sentence Encoder provide more valid\nrepresentations of survey questions than do others. Our results thus highlight\nthe necessity to examine the construct validity of text embeddings before\ndeploying them in social science research.",
      'No',
      -0.008583762),
     ('how do bi-encoders work for sentence embeddings',
      'Learning Probabilistic Sentence Representations from Paraphrases: Probabilistic word embeddings have shown effectiveness in capturing notions\nof generality and entailment, but there is very little work on doing the\nanalogous type of investigation for sentences. In this paper we define\nprobabilistic models that produce distributions for sentences. Our\nbest-performing model treats each word as a linear transformation operator\napplied to a multivariate Gaussian distribution. We train our models on\nparaphrases and demonstrate that they naturally capture sentence specificity.\nWhile our proposed model achieves the best performance overall, we also show\nthat specificity is represented by simpler architectures via the norm of the\nsentence vectors. Qualitative analysis shows that our probabilistic model\ncaptures sentential entailment and provides ways to analyze the specificity and\npreciseness of individual words.',
      'No',
      -0.011975748),
     ('how do bi-encoders work for sentence embeddings',
      "Exploiting Twitter as Source of Large Corpora of Weakly Similar Pairs for Semantic Sentence Embeddings: Semantic sentence embeddings are usually supervisedly built minimizing\ndistances between pairs of embeddings of sentences labelled as semantically\nsimilar by annotators. Since big labelled datasets are rare, in particular for\nnon-English languages, and expensive, recent studies focus on unsupervised\napproaches that require not-paired input sentences. We instead propose a\nlanguage-independent approach to build large datasets of pairs of informal\ntexts weakly similar, without manual human effort, exploiting Twitter's\nintrinsic powerful signals of relatedness: replies and quotes of tweets. We use\nthe collected pairs to train a Transformer model with triplet-like structures,\nand we test the generated embeddings on Twitter NLP similarity tasks (PIT and\nTURL) and STSb. We also introduce four new sentence ranking evaluation\nbenchmarks of informal texts, carefully extracted from the initial collections\nof tweets, proving not only that our best model learns classical Semantic\nTextual Similarity, but also excels on tasks where pairs of sentences are not\nexact paraphrases. Ablation studies reveal how increasing the corpus size\ninfluences positively the results, even at 2M samples, suggesting that bigger\ncollections of Tweets still do not contain redundant information about semantic\nsimilarities.",
      'No',
      -0.01219046),
     ('how do bi-encoders work for sentence embeddings',
      "How to Probe Sentence Embeddings in Low-Resource Languages: On Structural Design Choices for Probing Task Evaluation: Sentence encoders map sentences to real valued vectors for use in downstream\napplications. To peek into these representations - e.g., to increase\ninterpretability of their results - probing tasks have been designed which\nquery them for linguistic knowledge. However, designing probing tasks for\nlesser-resourced languages is tricky, because these often lack large-scale\nannotated data or (high-quality) dependency parsers as a prerequisite of\nprobing task design in English. To investigate how to probe sentence embeddings\nin such cases, we investigate sensitivity of probing task results to structural\ndesign choices, conducting the first such large scale study. We show that\ndesign choices like size of the annotated probing dataset and type of\nclassifier used for evaluation do (sometimes substantially) influence probing\noutcomes. We then probe embeddings in a multilingual setup with design choices\nthat lie in a 'stable region', as we identify for English, and find that\nresults on English do not transfer to other languages. Fairer and more\ncomprehensive sentence-level probing evaluation should thus be carried out on\nmultiple languages in the future.",
      'No',
      -0.015550519),
     ('how do bi-encoders work for sentence embeddings',
      'Clustering and Network Analysis for the Embedding Spaces of Sentences and Sub-Sentences: Sentence embedding methods offer a powerful approach for working with short\ntextual constructs or sequences of words. By representing sentences as dense\nnumerical vectors, many natural language processing (NLP) applications have\nimproved their performance. However, relatively little is understood about the\nlatent structure of sentence embeddings. Specifically, research has not\naddressed whether the length and structure of sentences impact the sentence\nembedding space and topology. This paper reports research on a set of\ncomprehensive clustering and network analyses targeting sentence and\nsub-sentence embedding spaces. Results show that one method generates the most\nclusterable embeddings. In general, the embeddings of span sub-sentences have\nbetter clustering properties than the original sentences. The results have\nimplications for future sentence embedding models and applications.',
      'No',
      -0.012663184),
     ('how do bi-encoders work for sentence embeddings',
      'Vec2Sent: Probing Sentence Embeddings with Natural Language Generation: We introspect black-box sentence embeddings by conditionally generating from\nthem with the objective to retrieve the underlying discrete sentence. We\nperceive of this as a new unsupervised probing task and show that it correlates\nwell with downstream task performance. We also illustrate how the language\ngenerated from different encoders differs. We apply our approach to generate\nsentence analogies from sentence embeddings.',
      'Yes',
      -0.004863006),
     ('how do bi-encoders work for sentence embeddings',
      'Non-Linguistic Supervision for Contrastive Learning of Sentence Embeddings: Semantic representation learning for sentences is an important and\nwell-studied problem in NLP. The current trend for this task involves training\na Transformer-based sentence encoder through a contrastive objective with text,\ni.e., clustering sentences with semantically similar meanings and scattering\nothers. In this work, we find the performance of Transformer models as sentence\nencoders can be improved by training with multi-modal multi-task losses, using\nunpaired examples from another modality (e.g., sentences and unrelated\nimage/audio data). In particular, besides learning by the contrastive loss on\ntext, our model clusters examples from a non-linguistic domain (e.g.,\nvisual/audio) with a similar contrastive loss at the same time. The reliance of\nour framework on unpaired non-linguistic data makes it language-agnostic,\nenabling it to be widely applicable beyond English NLP. Experiments on 7\nsemantic textual similarity benchmarks reveal that models trained with the\nadditional non-linguistic (/images/audio) contrastive objective lead to higher\nquality sentence embeddings. This indicates that Transformer models are able to\ngeneralize better by doing a similar task (i.e., clustering) with unpaired\nexamples from different modalities in a multi-task fashion.',
      'No',
      -0.013869206)]
    ```

```python
output_df = pd.DataFrame(
    output_list, columns=["query", "document", "prediction", "logprobs"]
).reset_index()
# Use exp() to convert logprobs into probability
output_df["probability"] = output_df["logprobs"].apply(exp)
# Reorder based on likelihood of being Yes
output_df["yes_probability"] = output_df.apply(
    lambda x: x["probability"] * -1 + 1
    if x["prediction"] == "No"
    else x["probability"],
    axis=1,
)
output_df.head()
```

??? note "輸出"

    ```text
       index                                            query  \
    0      0  how do bi-encoders work for sentence embeddings   
    1      1  how do bi-encoders work for sentence embeddings   
    2      2  how do bi-encoders work for sentence embeddings   
    3      3  how do bi-encoders work for sentence embeddings   
    4      4  how do bi-encoders work for sentence embeddings   

                                                document prediction  logprobs  \
    0  SBERT studies Meaning Representations: Decompo...        Yes -0.053264   
    1  Are Classes Clusters?: Sentence embedding mode...         No -0.009535   
    2  Semantic Composition in Visually Grounded Lang...         No -0.008887   
    3  Evaluating the Construct Validity of Text Embe...         No -0.008584   
    4  Learning Probabilistic Sentence Representation...         No -0.011976   

       probability  yes_probability  
    0     0.948130         0.948130  
    1     0.990510         0.009490  
    2     0.991152         0.008848  
    3     0.991453         0.008547  
    4     0.988096         0.011904
    ```

```python
# Return reranked results
reranked_df = output_df.sort_values(
    by=["yes_probability"], ascending=False
).reset_index()
reranked_df.head(10)
```

??? note "輸出"

    ```text
       level_0  index                                            query  \
    0       16     16  how do bi-encoders work for sentence embeddings   
    1        8      8  how do bi-encoders work for sentence embeddings   
    2       19     19  how do bi-encoders work for sentence embeddings   
    3        0      0  how do bi-encoders work for sentence embeddings   
    4       15     15  how do bi-encoders work for sentence embeddings   
    5        6      6  how do bi-encoders work for sentence embeddings   
    6       18     18  how do bi-encoders work for sentence embeddings   
    7        9      9  how do bi-encoders work for sentence embeddings   
    8       12     12  how do bi-encoders work for sentence embeddings   
    9        7      7  how do bi-encoders work for sentence embeddings   

                                                document prediction  logprobs  \
    0  In Search for Linear Relations in Sentence Emb...        Yes -0.004824   
    1  Vec2Sent: Probing Sentence Embeddings with Nat...        Yes -0.004863   
    2  Relational Sentence Embedding for Flexible Sem...        Yes -0.038814   
    3  SBERT studies Meaning Representations: Decompo...        Yes -0.053264   
    4  Sentence-T5: Scalable Sentence Encoders from P...         No -0.291893   
    5  How to Probe Sentence Embeddings in Low-Resour...         No -0.015551   
    6  Efficient and Flexible Topic Modeling using Pr...         No -0.015296   
    7  Non-Linguistic Supervision for Contrastive Lea...         No -0.013869   
    8  Character-based Neural Networks for Sentence P...         No -0.012866   
    9  Clustering and Network Analysis for the Embedd...         No -0.012663   

       probability  yes_probability  
    0     0.995187         0.995187  
    1     0.995149         0.995149  
    2     0.961930         0.961930  
    3     0.948130         0.948130  
    4     0.746849         0.253151  
    5     0.984570         0.015430  
    6     0.984820         0.015180  
    7     0.986227         0.013773  
    8     0.987216         0.012784  
    9     0.987417         0.012583
    ```

```python
# Inspect our new top document following reranking
reranked_df["document"][0]
```

??? note "輸出"

    ```text
    'In Search for Linear Relations in Sentence Embedding Spaces: We present an introductory investigation into continuous-space vector\nrepresentations of sentences. We acquire pairs of very similar sentences\ndiffering only by a small alterations (such as change of a noun, adding an\nadjective, noun or punctuation) from datasets for natural language inference\nusing a simple pattern method. We look into how such a small change within the\nsentence text affects its representation in the continuous space and how such\nalterations are reflected by some of the popular sentence embedding models. We\nfound that vector differences of some embeddings actually reflect small changes\nwithin a sentence.'
    ```

## 結論

我們示範了怎麼建立客製的 cross-encoder 來重排學術論文。這個方法在有領域細微差異可以用來挑出最相關文件、而且已經先做過預先篩選以限制 cross-encoder 要處理的資料量時，效果最好。

常見的使用情境有：
- 回傳 100 份最相關的股票研究報告，再根據特定客戶投資組合的詳細背景，重排成前 5 或 10 名
- 接在傳統規則式搜尋後面，從前 100 或 1000 個最相關的結果中，依特定使用者的情境做修剪


### 接下來

像這裡用的 few-shot 做法，在領域夠通用、少量範例就能涵蓋大部分重排情況時效果不錯。但文件之間的差異越來越細時，你可能要考慮用 ```Fine-tuning``` endpoint，用更多樣的範例做出更精細的 cross-encoder。

使用 ```text-davinci-003``` that you'll need to consider, with even our few examples above taking a couple seconds each - again, the ```Fine-tuning``` endpoint may help 也有延遲問題要考慮，上面這幾個範例每個就要花幾秒。延遲的部分，```Fine-tuning``` endpoint may help you here if you are able to get decent results from an ```ada``` or ```babbage``` fine-tuned 模型，也就是小模型微調後效果夠用的話，就能降延遲。

我們用 OpenAI 的 ```Completions``` endpoint 建了 cross-encoder，不過開源社群在這塊也很有成果，例如 HuggingFace 上的[這個範例](https://huggingface.co/jeffwan/mmarco-mMiniLMv2-L12-H384-v1)。

希望這對你調整搜尋應用有幫助，期待看到你做出來的東西。

## 重點整理
- Bi-encoder 便宜但粗，cross-encoder 準但貴，所以常見做法是先粗篩再精排。
- 重排成本隨候選數 N 線性成長，所以要先把候選縮到合理大小。
- 用 few-shot 加領域範例，GPT 就能當 cross-encoder 用。
- `logit_bias` 限制輸出只有 Yes/No，logprobs 提供可排序的連續分數。
- 差異越細越值得考慮 fine-tuning，也要顧延遲。

## 練習
1. 把 few-shot 範例換成你熟悉領域的 2 個例子，看排序結果有沒有變。
2. 調整抓取的候選數量 N（例如 10 和 50），比較排序品質和執行時間。
3. 把逐筆呼叫改成用 `concurrent.futures` 平行處理，量一下加速多少。
