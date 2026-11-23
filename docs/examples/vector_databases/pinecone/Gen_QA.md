---
translated: true
source: examples/vector_databases/pinecone/Gen_QA.ipynb
---

# 用 Pinecone 做檢索增強的問答生成（RAG）

> 原文：[examples/vector_databases/pinecone/Gen_QA.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/Gen_QA.ipynb)



## 這篇在做什麼
LLM 回答專業問題時常常會亂編。這篇把 YouTube 逐字稿做成 embedding 存進 Pinecone，提問時先檢索相關內容，再一起丟給 OpenAI 模型，讓答案有真實資料當後盾。

## 學完你會
- 看懂 LLM 幻覺的樣子，以及為什麼 RAG 比 fine-tuning 更適合補特定知識
- 用 `text-embedding-3-small` 產生 embedding，並寫進 Pinecone index
- 做出「查詢向量 → 檢索 context → 塞進 prompt → 生成答案」的完整流程

## 開跑前
- OpenAI API key
- Pinecone 的 API key（有免費方案）


#### 修正會亂講的 LLM

這份 notebook 會示範怎麼從 Pinecone 撈出跟問題相關的 context，再交給 OpenAI 的生成模型，產生有真實資料支持的答案。

用 GPT-3 回答事實性問題有個常見問題：它有時會自己編。GPT 系列的通用知識很廣，但遇到比較專門的資訊就不一定對。這時我們用 Pinecone 向量資料庫當「外部知識庫」，就像 GPT-3 的*長期記憶*。

這份 notebook 需要安裝：

```python
!pip install -qU openai pinecone-client datasets
```

??? note "輸出"

    ```text
    [?25l     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/55.3 KB ? eta -:--:--
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 55.3/55.3 KB 1.7 MB/s eta 0:00:00
    [?25h  Installing build dependencies ... [?25l[?25hdone
      Getting requirements to build wheel ... [?25l[?25hdone
      Preparing metadata (pyproject.toml) ... [?25l[?25hdone
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 170.6/170.6 KB 13.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 452.9/452.9 KB 30.4 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 58.3/58.3 KB 6.8 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 213.0/213.0 KB 17.3 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 132.0/132.0 KB 13.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 182.4/182.4 KB 18.6 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 140.6/140.6 KB 6.7 MB/s eta 0:00:00
    [?25h  Building wheel for openai (pyproject.toml) ... [?25l[?25hdone
    ```

```python
import openai

# get API key from top-right dropdown on OpenAI website
openai.api_key = "OPENAI_API_KEY"
```

很多問題 *state-of-the-art (SOTA)* 的 LLM 都答得對。

```python
query = "who was the 12th person on the moon and when did they land?"

# now query `gpt-3.5-turbo-instruct` WITHOUT context
res = openai.Completion.create(
    engine='gpt-3.5-turbo-instruct',
    prompt=query,
    temperature=0,
    max_tokens=400,
    top_p=1,
    frequency_penalty=0,
    presence_penalty=0,
    stop=None
)

res['choices'][0]['text'].strip()
```

??? note "輸出"

    ```text
    'The 12th person on the moon was Harrison Schmitt, and he landed on December 11, 1972.'
    ```

但不是每次都這樣。先把上面的做法包成一個簡單的函式，之後就不用重複寫。

```python
def complete(prompt):
    res = openai.Completion.create(
        engine='gpt-3.5-turbo-instruct',
        prompt=prompt,
        temperature=0,
        max_tokens=400,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None
    )
    return res['choices'][0]['text'].strip()
```

現在問一個比較專門的問題：訓練一種叫 *sentence transformer* 的 transformer 模型。理想答案是 _"Multiple Negatives Ranking (MNR) loss"_。

這個詞不懂也沒關係，不影響我們要示範的東西。

```python
query = (
    "Which training method should I use for sentence transformers when " +
    "I only have pairs of related sentences?"
)

complete(query)
```

??? note "輸出"

    ```text
    'If you only have pairs of related sentences, then the best training method to use for sentence transformers is the supervised learning approach. This approach involves providing the model with labeled data, such as pairs of related sentences, and then training the model to learn the relationships between the sentences. This approach is often used for tasks such as natural language inference, semantic similarity, and paraphrase identification.'
    ```

常見的答案之一是：

```
The best training method to use for fine-tuning a pre-trained model with sentence transformers is the Masked Language Model (MLM) training. MLM training involves randomly masking some of the words in a sentence and then training the model to predict the masked words. This helps the model to learn the context of the sentence and better understand the relationships between words.
```

這個答案看起來很有說服力對吧？但它是錯的。MLM 通常用在 transformer 模型的預訓練階段，*不能*拿來 fine-tune sentence-transformer，也跟「成對的相關句子」無關。

另一個我們得到的答案（就是上面回傳的那個）說 `supervised learning approach` 最合適。這句話沒錯，但太籠統，沒有回答問題。

要讓 LLM 理解並正確回答這個問題，有兩個選項：

1. 用相關主題的文字資料 fine-tune LLM，例如講 sentence transformer、semantic search 訓練方法的文章和論文。

2. 用 **R**etrieval **A**ugmented **G**eneration（RAG），在生成流程中加一個資訊檢索元件。先檢索相關資訊，再當作*次要*資訊來源餵給生成模型。

我們示範選項 **2**。

---

## 建立知識庫

選項 **2** 需要一個外部「知識庫」，用來存資料並有效率地檢索。可以把它想成 LLM 外掛的*長期記憶*。

我們要找的是語意上跟問題相關的資訊，所以需要「dense vector embedding」，也就是句子*意思*的數值表示。

這些 dense vector 用 `text-embedding-3-small` 模型產生。

OpenAI 連線已經認證好了，要建立 embedding 只要這樣做：

```python
embed_model = "text-embedding-ada-002"

res = openai.Embedding.create(
    input=[
        "Sample document text goes here",
        "there will be several phrases in each batch"
    ], engine=embed_model
)
```

回應 `res` 是類似 JSON 的物件，新的 embedding 在 `'data'` 欄位裡。

```python
res.keys()
```

??? note "輸出"

    ```text
    dict_keys(['object', 'data', 'model', 'usage'])
    ```

`'data'` 裡有兩筆資料，對應剛剛 embed 的兩個句子。每個向量有 `1536` 維（`text-embedding-3-small` 的輸出維度）。

```python
len(res['data'])
```

??? note "輸出"

    ```text
    2
    ```

```python
len(res['data'][0]['embedding']), len(res['data'][1]['embedding'])
```

??? note "輸出"

    ```text
    (1536, 1536)
    ```

接著把同樣的 embedding 流程套用到一個資料集上，這個資料集包含跟我們的問題（以及很多 ML、AI 主題問題）相關的資訊。

### 資料準備

資料集用 Hugging Face _Datasets_ 上的 `jamescalam/youtube-transcriptions`，內容是幾個 ML 和科技 YouTube 頻道的語音逐字稿。下載方式：

```python
from datasets import load_dataset

data = load_dataset('jamescalam/youtube-transcriptions', split='train')
data
```

??? note "輸出"

    ```text
    Using custom data configuration jamescalam--youtube-transcriptions-6a482f3df0aedcdb
    Reusing dataset json (/Users/jamesbriggs/.cache/huggingface/datasets/jamescalam___json/jamescalam--youtube-transcriptions-6a482f3df0aedcdb/0.0.0/ac0ca5f5289a6cf108e706efcf040422dbbfa8e658dee6a819f20d76bb84d26b)
    ```

    ```text
    Dataset({
        features: ['title', 'published', 'url', 'video_id', 'channel_id', 'id', 'text', 'start', 'end'],
        num_rows: 208619
    })
    ```

```python
data[0]
```

??? note "輸出"

    ```text
    {'title': 'Training and Testing an Italian BERT - Transformers From Scratch #4',
     'published': '2021-07-06 13:00:03 UTC',
     'url': 'https://youtu.be/35Pdoyi6ZoQ',
     'video_id': '35Pdoyi6ZoQ',
     'channel_id': 'UCv83tO5cePwHMt1952IVVHw',
     'id': '35Pdoyi6ZoQ-t0.0',
     'text': 'Hi, welcome to the video.',
     'start': 0.0,
     'end': 9.36}
    ```

資料集是很多小段文字。我們要把每支影片的許多片段合併成較大的 chunk，讓每塊包含更多資訊。

```python
from tqdm.auto import tqdm

new_data = []

window = 20  # number of sentences to combine
stride = 4  # number of sentences to 'stride' over, used to create overlap

for i in tqdm(range(0, len(data), stride)):
    i_end = min(len(data)-1, i+window)
    if data[i]['title'] != data[i_end]['title']:
        # in this case we skip this entry as we have start/end of two videos
        continue
    text = ' '.join(data[i:i_end]['text'])
    # create the new merged dataset
    new_data.append({
        'start': data[i]['start'],
        'end': data[i_end]['end'],
        'title': data[i]['title'],
        'text': text,
        'id': data[i]['id'],
        'url': data[i]['url'],
        'published': data[i]['published'],
        'channel_id': data[i]['channel_id']
    })
```

??? note "輸出"

    ```text
      0%|          | 0/52155 [00:00<?, ?it/s]
    ```

```python
new_data[0]
```

??? note "輸出"

    ```text
    {'start': 0.0,
     'end': 74.12,
     'title': 'Training and Testing an Italian BERT - Transformers From Scratch #4',
     'text': "Hi, welcome to the video. So this is the fourth video in a Transformers from Scratch mini series. So if you haven't been following along, we've essentially covered what you can see on the screen. So we got some data. We built a tokenizer with it. And then we've set up our input pipeline ready to begin actually training our model, which is what we're going to cover in this video. So let's move over to the code. And we see here that we have essentially everything we've done so far. So we've built our input data, our input pipeline. And we're now at a point where we have a data loader, PyTorch data loader, ready. And we can begin training a model with it. So there are a few things to be aware of. So I mean, first, let's just have a quick look at the structure of our data.",
     'id': '35Pdoyi6ZoQ-t0.0',
     'url': 'https://youtu.be/35Pdoyi6ZoQ',
     'published': '2021-07-06 13:00:03 UTC',
     'channel_id': 'UCv83tO5cePwHMt1952IVVHw'}
    ```

現在需要一個地方存這些 embedding，並能對它們做有效率的 _vector search_。我們用 **`Pinecone`**。可以申請[免費 API key](https://app.pinecone.io)，填在下面，初始化 `Pinecone` 連線並建立新的 index。

```python
import pinecone

index_name = 'openai-youtube-transcriptions'

# initialize connection to pinecone (get API key at app.pinecone.io)
pinecone.init(
    api_key="PINECONE_API_KEY",
    environment="us-east1-gcp"  # may be different, check at app.pinecone.io
)

# check if index already exists (it shouldn't if this is first time)
if index_name not in pinecone.list_indexes():
    # if does not exist, create index
    pinecone.create_index(
        index_name,
        dimension=len(res['data'][0]['embedding']),
        metric='cosine',
        metadata_config={'indexed': ['channel_id', 'published']}
    )
# connect to index
index = pinecone.Index(index_name)
# view index stats
index.describe_index_stats()
```

??? note "輸出"

    ```text
    {'dimension': 1536,
     'index_fullness': 0.0,
     'namespaces': {},
     'total_vector_count': 0}
    ```

index 目前是空的，`total_vector_count` 是 `0`。接著用 OpenAI `text-embedding-3-small` 產生的 embedding 填進去：

```python
from tqdm.auto import tqdm
from time import sleep

batch_size = 100  # how many embeddings we create and insert at once

for i in tqdm(range(0, len(new_data), batch_size)):
    # find end of batch
    i_end = min(len(new_data), i+batch_size)
    meta_batch = new_data[i:i_end]
    # get ids
    ids_batch = [x['id'] for x in meta_batch]
    # get texts to encode
    texts = [x['text'] for x in meta_batch]
    # create embeddings (try-except added to avoid RateLimitError)
    done = False
    while not done:
        try:
            res = openai.Embedding.create(input=texts, engine=embed_model)
            done = True
        except:
            sleep(5)
    embeds = [record['embedding'] for record in res['data']]
    # cleanup metadata
    meta_batch = [{
        'start': x['start'],
        'end': x['end'],
        'title': x['title'],
        'text': x['text'],
        'url': x['url'],
        'published': x['published'],
        'channel_id': x['channel_id']
    } for x in meta_batch]
    to_upsert = list(zip(ids_batch, embeds, meta_batch))
    # upsert to Pinecone
    index.upsert(vectors=to_upsert)
```

??? note "輸出"

    ```text
      0%|          | 0/487 [00:00<?, ?it/s]
    ```

接下來搜尋，要先建立 _query vector_ `xq`：

```python
res = openai.Embedding.create(
    input=[query],
    engine=embed_model
)

# retrieve from Pinecone
xq = res['data'][0]['embedding']

# get relevant contexts (including the questions)
res = index.query(xq, top_k=2, include_metadata=True)
```

```python
res
```

??? note "輸出"

    ```text
    {'matches': [{'id': 'pNvujJ1XyeQ-t418.88',
                  'metadata': {'channel_id': 'UCv83tO5cePwHMt1952IVVHw',
                               'end': 568.4,
                               'published': datetime.date(2021, 11, 24),
                               'start': 418.88,
                               'text': 'pairs of related sentences you can go '
                                       'ahead and actually try training or '
                                       'fine-tuning using NLI with multiple '
                                       "negative ranking loss. If you don't have "
                                       'that fine. Another option is that you have '
                                       'a semantic textual similarity data set or '
                                       'STS and what this is is you have so you '
                                       'have sentence A here, sentence B here and '
                                       'then you have a score from from 0 to 1 '
                                       'that tells you the similarity between '
                                       'those two scores and you would train this '
                                       'using something like cosine similarity '
                                       "loss. Now if that's not an option and your "
                                       'focus or use case is on building a '
                                       'sentence transformer for another language '
                                       'where there is no current sentence '
                                       'transformer you can use multilingual '
                                       'parallel data. So what I mean by that is '
                                       'so parallel data just means translation '
                                       'pairs so if you have for example a English '
                                       'sentence and then you have another '
                                       'language here so it can it can be anything '
                                       "I'm just going to put XX and that XX is "
                                       'your target language you can fine-tune a '
                                       'model using something called multilingual '
                                       'knowledge distillation and what that does '
                                       'is takes a monolingual model for example '
                                       'in English and using those translation '
                                       'pairs it distills the knowledge the '
                                       'semantic similarity knowledge from that '
                                       'monolingual English model into a '
                                       'multilingual model which can handle both '
                                       'English and your target language. So '
                                       "they're three options quite popular very "
                                       'common that you can go for and as a '
    ... (省略 71 行)
    ```

```python
limit = 3750

def retrieve(query):
    res = openai.Embedding.create(
        input=[query],
        engine=embed_model
    )

    # retrieve from Pinecone
    xq = res['data'][0]['embedding']

    # get relevant contexts
    res = index.query(xq, top_k=3, include_metadata=True)
    contexts = [
        x['metadata']['text'] for x in res['matches']
    ]

    # build our prompt with the retrieved contexts included
    prompt_start = (
        "Answer the question based on the context below.\n\n"+
        "Context:\n"
    )
    prompt_end = (
        f"\n\nQuestion: {query}\nAnswer:"
    )
    # append contexts until hitting limit
    for i in range(1, len(contexts)):
        if len("\n\n---\n\n".join(contexts[:i])) >= limit:
            prompt = (
                prompt_start +
                "\n\n---\n\n".join(contexts[:i-1]) +
                prompt_end
            )
            break
        elif i == len(contexts)-1:
            prompt = (
                prompt_start +
                "\n\n---\n\n".join(contexts) +
                prompt_end
            )
    return prompt
```

```python
# first we retrieve relevant items from Pinecone
query_with_contexts = retrieve(query)
query_with_contexts
```

??? note "輸出"

    ```text
    "Answer the question based on the context below.\n\nContext:\npairs of related sentences you can go ahead and actually try training or fine-tuning using NLI with multiple negative ranking loss. If you don't have that fine. Another option is that you have a semantic textual similarity data set or STS and what this is is you have so you have sentence A here, sentence B here and then you have a score from from 0 to 1 that tells you the similarity between those two scores and you would train this using something like cosine similarity loss. Now if that's not an option and your focus or use case is on building a sentence transformer for another language where there is no current sentence transformer you can use multilingual parallel data. So what I mean by that is so parallel data just means translation pairs so if you have for example a English sentence and then you have another language here so it can it can be anything I'm just going to put XX and that XX is your target language you can fine-tune a model using something called multilingual knowledge distillation and what that does is takes a monolingual model for example in English and using those translation pairs it distills the knowledge the semantic similarity knowledge from that monolingual English model into a multilingual model which can handle both English and your target language. So they're three options quite popular very common that you can go for and as a supervised methods the chances are that probably going to outperform anything you do with unsupervised training at least for now. So if none of those sound like something\n\n---\n\nwere actually more accurate. So we can't really do that. We can't use this what is called a mean pooling approach. Or we can't use it in its current form. Now the solution to this problem was introduced by two people in 2019 Nils Reimers and Irenia Gurevich. They introduced what is the first sentence transformer or sentence BERT. And it was found that sentence BERT or S BERT outformed all of the previous Save the Art models on pretty much all benchmarks. Not all of them but most of them. And it did it in a very quick time. So if we compare it to BERT, if we wanted to find the most similar sentence pair from 10,000 sentences in that 2019 paper they found that with BERT that took 65 hours. With S BERT embeddings they could create all the embeddings in just around five seconds. And then they could compare all those with cosine similarity in 0.01 seconds. So it's a lot faster. We go from 65 hours to just over five seconds which is I think pretty incredible. Now I think that's pretty much all the context we need behind sentence transformers. And what we do now is dive into a little bit of how they actually work. Now we said before we have the core transform models and what S BERT does is fine tunes on sentence pairs using what is called a Siamese architecture or Siamese network. What we mean by a Siamese network is that we have what we can see, what can view as two BERT models that are identical and the weights between those two models are tied. Now in reality when implementing this we just use a single BERT model. And what we do is we process one sentence, a sentence A through the model and then we process another sentence, sentence B through the model. And that's the sentence pair. So with our cross-linked we were processing the sentence pair together. We were putting them both together, processing them all at once. This time we process them separately. And during training what happens is the weights\n\n---\n\nTransformer-based Sequential Denoising Autoencoder. So what we'll do is jump straight into it and take a look at where we might want to use this training approach and and how we can actually implement it. So the first question we need to ask is do we really need to resort to unsupervised training? Now what we're going to do here is just have a look at a few of the most popular training approaches and what sort of data we need for that. So the first one we're looking at here is Natural Language Inference or NLI and NLI requires that we have pairs of sentences that are labeled as either contradictory, neutral which means they're not necessarily related or as entailing or as inferring each other. So you have pairs that entail each other so they are both very similar pairs that are neutral and also pairs that are contradictory. And this is the traditional NLI data. Now using another version of fine-tuning with NLI called a multiple negatives ranking loss you can get by with only entailment pairs so pairs that are related to each other or positive pairs and it can also use contradictory pairs to improve the performance of training as well but you don't need it. So if you have positive pairs of related sentences you can go ahead and actually try training or fine-tuning using NLI with multiple negative ranking loss. If you don't have that fine. Another option is that you have a semantic textual similarity data set or STS and what this is is you have so you have sentence A here, sentence B\n\nQuestion: Which training method should I use for sentence transformers when I only have pairs of related sentences?\nAnswer:"
    ```

```python
# then we complete the context-infused query
complete(query_with_contexts)
```

??? note "輸出"

    ```text
    'You should use Natural Language Inference (NLI) with multiple negative ranking loss.'
    ```

一下子就得到很好的答案，它指出要用 _multiple-rankings loss_（也叫 _multiple negatives ranking loss_）。

## 重點整理
- LLM 對冷門、專門的問題會一本正經地答錯，這就是幻覺。
- RAG 是在生成前先檢索相關資料，當作額外 context 給模型，不用重新訓練模型。
- 檢索靠 embedding：把文字轉成向量，用向量相似度找語意相近的內容。
- 影片逐字稿片段太短，要先合併成較大的 chunk 再 embed，檢索結果才有足夠資訊。
- 向量資料庫（這裡是 Pinecone）負責存向量並做快速搜尋，OpenAI 模型負責用檢索到的內容產生答案。

## 練習
1. 把最後問的問題換成另一個 ML 相關的問題，比較「有 RAG」和「沒有 RAG」兩種答案差在哪。
2. 調整檢索時的 `top_k`（例如 1、3、5），看塞進 prompt 的 context 數量如何影響答案。
3. 改變合併逐字稿的 chunk 大小（改成更長或更短），重新 embed 並 upsert，觀察檢索品質的變化。
