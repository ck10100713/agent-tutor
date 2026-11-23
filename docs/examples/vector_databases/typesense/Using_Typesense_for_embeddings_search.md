---
translated: false
source: examples/vector_databases/typesense/Using_Typesense_for_embeddings_search.ipynb
---

# Using Typesense for embeddings search

> 原文：[examples/vector_databases/typesense/Using_Typesense_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/typesense/Using_Typesense_for_embeddings_search.ipynb)



<!-- tutor:goals -->


This notebook takes you through a simple flow to download some data, embed it, and then index and search it using a selection of vector databases. This is a common requirement for customers who want to store and search our embeddings with their own data in a secure environment to support production use cases such as chatbots, topic modelling and more.

### What is a Vector Database

A vector database is a database made to store, manage and search embedding vectors. The use of embeddings to encode unstructured data (text, audio, video and more) as vectors for consumption by machine-learning models has exploded in recent years, due to the increasing effectiveness of AI in solving use cases involving natural language, image recognition and other unstructured forms of data. Vector databases have emerged as an effective solution for enterprises to deliver and scale these use cases.

### Why use a Vector Database

Vector databases enable enterprises to take many of the embeddings use cases we've shared in this repo (question and answering, chatbot and recommendation services, for example), and make use of them in a secure, scalable environment. Many of our customers make embeddings solve their problems at small scale but performance and security hold them back from going into production - we see vector databases as a key component in solving that, and in this guide we'll walk through the basics of embedding text data, storing it in a vector database and using it for semantic search.


### Demo Flow
The demo flow is:
- **Setup**: Import packages and set any required variables
- **Load data**: Load a dataset and embed it using OpenAI embeddings
- **Typesense**
    - *Setup*: Set up the Typesense Python client. For more details go [here](https://typesense.org/docs/0.24.0/api/)
    - *Index Data*: We'll create a collection and index it for both __titles__ and __content__.
    - *Search Data*: Run a few example queries with various goals in mind.

Once you've run through this notebook you should have a basic understanding of how to setup and use vector databases, and can move on to more complex use cases making use of our embeddings.

## Setup

Import the required libraries and set the embedding model that we'd like to use.

```python
# We'll need to install the Typesense client
!pip install typesense

#Install wget to pull zip file
!pip install wget
```

```python
import openai

from typing import List, Iterator
import pandas as pd
import numpy as np
import os
import wget
from ast import literal_eval

# Typesense's client library for Python
import typesense

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## Load data

In this section we'll load embedded data that we've prepared previous to this session.

```python
embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

```python
import zipfile
with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip","r") as zip_ref:
    zip_ref.extractall("../data")
```

```python
article_df = pd.read_csv('../data/vector_database_wikipedia_articles_embedded.csv')
```

```python
article_df.head()
```

??? note "輸出"

    ```text
       id                                       url   title  \
    0   1   https://simple.wikipedia.org/wiki/April   April   
    1   2  https://simple.wikipedia.org/wiki/August  August   
    2   6     https://simple.wikipedia.org/wiki/Art     Art   
    3   8       https://simple.wikipedia.org/wiki/A       A   
    4   9     https://simple.wikipedia.org/wiki/Air     Air   

                                                    text  \
    0  April is the fourth month of the year in the J...   
    1  August (Aug.) is the eighth month of the year ...   
    2  Art is a creative activity that expresses imag...   
    3  A or a is the first letter of the English alph...   
    4  Air refers to the Earth's atmosphere. Air is a...   

                                            title_vector  \
    0  [0.001009464613161981, -0.020700545981526375, ...   
    1  [0.0009286514250561595, 0.000820168002974242, ...   
    2  [0.003393713850528002, 0.0061537534929811954, ...   
    3  [0.0153952119871974, -0.013759135268628597, 0....   
    4  [0.02224554680287838, -0.02044147066771984, -0...   

                                          content_vector  vector_id  
    0  [-0.011253940872848034, -0.013491976074874401,...          0  
    1  [0.0003609954728744924, 0.007262262050062418, ...          1  
    2  [-0.004959689453244209, 0.015772193670272827, ...          2  
    3  [0.024894846603274345, -0.022186409682035446, ...          3  
    4  [0.021524671465158463, 0.018522677943110466, -...          4
    ```

```python
# Read vectors from strings back into a list
article_df['title_vector'] = article_df.title_vector.apply(literal_eval)
article_df['content_vector'] = article_df.content_vector.apply(literal_eval)

# Set vector_id to be a string
article_df['vector_id'] = article_df['vector_id'].apply(str)
```

```python
article_df.info(show_counts=True)
```

??? note "輸出"

    ```text
    <class 'pandas.core.frame.DataFrame'>
    RangeIndex: 25000 entries, 0 to 24999
    Data columns (total 7 columns):
     #   Column          Non-Null Count  Dtype 
    ---  ------          --------------  ----- 
     0   id              25000 non-null  int64 
     1   url             25000 non-null  object
     2   title           25000 non-null  object
     3   text            25000 non-null  object
     4   title_vector    25000 non-null  object
     5   content_vector  25000 non-null  object
     6   vector_id       25000 non-null  object
    dtypes: int64(1), object(6)
    memory usage: 1.3+ MB
    ```

## Typesense

The next vector store we'll look at is [Typesense](https://typesense.org/), which is an open source, in-memory search engine, that you can either self-host or run on [Typesense Cloud](https://cloud.typesense.org).

Typesense focuses on performance by storing the entire index in RAM (with a backup on disk) and also focuses on providing an out-of-the-box developer experience by simplifying available options and setting good defaults. It also lets you combine attribute-based filtering together with vector queries.

For this example, we will set up a local docker-based Typesense server, index our vectors in Typesense and then do some nearest-neighbor search queries. If you use Typesense Cloud, you can skip the docker setup part and just obtain the hostname and API keys from your cluster dashboard.

### Setup

To run Typesense locally, you'll need [Docker](https://www.docker.com/). Following the instructions contained in the Typesense documentation [here](https://typesense.org/docs/guide/install-typesense.html#docker-compose), we created an example docker-compose.yml file in this repo saved at [`docker-compose.yml`](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/typesense/docker-compose.yml).

After starting Docker, you can start Typesense locally by navigating to the `examples/vector_databases/typesense/` directory and running `docker-compose up -d`.

The default API key is set to `xyz` in the Docker compose file, and the default Typesense port to `8108`.

```python
import typesense

typesense_client = \
    typesense.Client({
        "nodes": [{
            "host": "localhost",  # For Typesense Cloud use xxx.a1.typesense.net
            "port": "8108",       # For Typesense Cloud use 443
            "protocol": "http"    # For Typesense Cloud use https
          }],
          "api_key": "xyz",
          "connection_timeout_seconds": 60
        })
```

### Index data

To index vectors in Typesense, we'll first create a Collection (which is a collection of Documents) and turn on vector indexing for a particular field. You can even store multiple vector fields in a single document.

```python
# Delete existing collections if they already exist
try:
    typesense_client.collections['wikipedia_articles'].delete()
except Exception as e:
    pass

# Create a new collection

schema = {
    "name": "wikipedia_articles",
    "fields": [
        {
            "name": "content_vector",
            "type": "float[]",
            "num_dim": len(article_df['content_vector'][0])
        },
        {
            "name": "title_vector",
            "type": "float[]",
            "num_dim": len(article_df['title_vector'][0])
        }
    ]
}

create_response = typesense_client.collections.create(schema)
print(create_response)

print("Created new collection wikipedia-articles")
```

??? note "輸出"

    ```text
    {'created_at': 1687165065, 'default_sorting_field': '', 'enable_nested_fields': False, 'fields': [{'facet': False, 'index': True, 'infix': False, 'locale': '', 'name': 'content_vector', 'num_dim': 1536, 'optional': False, 'sort': False, 'type': 'float[]'}, {'facet': False, 'index': True, 'infix': False, 'locale': '', 'name': 'title_vector', 'num_dim': 1536, 'optional': False, 'sort': False, 'type': 'float[]'}], 'name': 'wikipedia_articles', 'num_documents': 0, 'symbols_to_index': [], 'token_separators': []}
    Created new collection wikipedia-articles
    ```

```python
# Upsert the vector data into the collection we just created
#
# Note: This can take a few minutes, especially if your on an M1 and running docker in an emulated mode

print("Indexing vectors in Typesense...")

document_counter = 0
documents_batch = []

for k,v in article_df.iterrows():
    # Create a document with the vector data

    # Notice how you can add any fields that you haven't added to the schema to the document.
    # These will be stored on disk and returned when the document is a hit.
    # This is useful to store attributes required for display purposes.

    document = {
        "title_vector": v["title_vector"],
        "content_vector": v["content_vector"],
        "title": v["title"],
        "content": v["text"],
    }
    documents_batch.append(document)
    document_counter = document_counter + 1

    # Upsert a batch of 100 documents
    if document_counter % 100 == 0 or document_counter == len(article_df):
        response = typesense_client.collections['wikipedia_articles'].documents.import_(documents_batch)
        # print(response)

        documents_batch = []
        print(f"Processed {document_counter} / {len(article_df)} ")

print(f"Imported ({len(article_df)}) articles.")
```

??? note "輸出"

    ```text
    Indexing vectors in Typesense...
    Processed 100 / 25000 
    Processed 200 / 25000 
    Processed 300 / 25000 
    Processed 400 / 25000 
    Processed 500 / 25000 
    Processed 600 / 25000 
    Processed 700 / 25000 
    Processed 800 / 25000 
    Processed 900 / 25000 
    Processed 1000 / 25000 
    Processed 1100 / 25000 
    Processed 1200 / 25000 
    Processed 1300 / 25000 
    Processed 1400 / 25000 
    Processed 1500 / 25000 
    Processed 1600 / 25000 
    Processed 1700 / 25000 
    Processed 1800 / 25000 
    Processed 1900 / 25000 
    Processed 2000 / 25000 
    Processed 2100 / 25000 
    Processed 2200 / 25000 
    Processed 2300 / 25000 
    Processed 2400 / 25000 
    Processed 2500 / 25000 
    Processed 2600 / 25000 
    Processed 2700 / 25000 
    Processed 2800 / 25000 
    Processed 2900 / 25000 
    Processed 3000 / 25000 
    Processed 3100 / 25000 
    Processed 3200 / 25000 
    Processed 3300 / 25000 
    Processed 3400 / 25000 
    Processed 3500 / 25000 
    Processed 3600 / 25000 
    Processed 3700 / 25000 
    Processed 3800 / 25000 
    Processed 3900 / 25000 
    ... (省略 212 行)
    ```

```python
# Check the number of documents imported

collection = typesense_client.collections['wikipedia_articles'].retrieve()
print(f'Collection has {collection["num_documents"]} documents')
```

??? note "輸出"

    ```text
    Collection has 25000 documents
    ```

### Search Data

Now that we've imported the vectors into Typesense, we can do a nearest neighbor search on the `title_vector` or `content_vector` field.

```python
def query_typesense(query, field='title', top_k=20):

    # Creates embedding vector from user query
    openai.api_key = os.getenv("OPENAI_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    embedded_query = openai.Embedding.create(
        input=query,
        model=EMBEDDING_MODEL,
    )['data'][0]['embedding']

    typesense_results = typesense_client.multi_search.perform({
        "searches": [{
            "q": "*",
            "collection": "wikipedia_articles",
            "vector_query": f"{field}_vector:([{','.join(str(v) for v in embedded_query)}], k:{top_k})"
        }]
    }, {})

    return typesense_results
```

```python
query_results = query_typesense('modern art in Europe', 'title')

for i, hit in enumerate(query_results['results'][0]['hits']):
    document = hit["document"]
    vector_distance = hit["vector_distance"]
    print(f'{i + 1}. {document["title"]} (Distance: {vector_distance})')
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Distance: 0.12482291460037231)
    2. Western Europe (Distance: 0.13255876302719116)
    3. Renaissance art (Distance: 0.13584274053573608)
    4. Pop art (Distance: 0.1396539807319641)
    5. Northern Europe (Distance: 0.14534103870391846)
    6. Hellenistic art (Distance: 0.1472070813179016)
    7. Modernist literature (Distance: 0.15296930074691772)
    8. Art film (Distance: 0.1567266583442688)
    9. Central Europe (Distance: 0.15741699934005737)
    10. European (Distance: 0.1585891842842102)
    ```

```python
query_results = query_typesense('Famous battles in Scottish history', 'content')

for i, hit in enumerate(query_results['results'][0]['hits']):
    document = hit["document"]
    vector_distance = hit["vector_distance"]
    print(f'{i + 1}. {document["title"]} (Distance: {vector_distance})')
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn (Distance: 0.1306111216545105)
    2. Wars of Scottish Independence (Distance: 0.1384994387626648)
    3. 1651 (Distance: 0.14744246006011963)
    4. First War of Scottish Independence (Distance: 0.15033596754074097)
    5. Robert I of Scotland (Distance: 0.15376019477844238)
    6. 841 (Distance: 0.15609073638916016)
    7. 1716 (Distance: 0.15615153312683105)
    8. 1314 (Distance: 0.16280347108840942)
    9. 1263 (Distance: 0.16361045837402344)
    10. William Wallace (Distance: 0.16464537382125854)
    ```

Thanks for following along, you're now equipped to set up your own vector databases and use embeddings to do all kinds of cool things - enjoy! For more complex use cases please continue to work through other cookbook examples in this repo.

<!-- tutor:summary -->
