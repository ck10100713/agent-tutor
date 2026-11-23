---
translated: false
source: examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb
---

# Semantic search using Elasticsearch and OpenAI

> 原文：[examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb)



<!-- tutor:goals -->



[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb)


This notebook demonstrates how to: 
- Index the OpenAI Wikipedia vector dataset into Elasticsearch 
- Embed a question with the OpenAI [`embeddings`](https://platform.openai.com/docs/api-reference/embeddings) endpoint
- Perform semantic search on the Elasticsearch index using the encoded question

## Install packages and import modules 

```python
# install packages

! python3 -m pip install -qU openai pandas wget elasticsearch

# import modules

from getpass import getpass
from elasticsearch import Elasticsearch, helpers
import wget
import zipfile
import pandas as pd
import json
from openai import OpenAI
```

## Connect to Elasticsearch

ℹ️ We're using an Elastic Cloud deployment of Elasticsearch for this notebook.
If you don't already have an Elastic deployment, you can sign up for a free [Elastic Cloud trial](https://cloud.elastic.co/registration?utm_source=github&utm_content=openai-cookbook).

To connect to Elasticsearch, you need to create a client instance with the Cloud ID and password for your deployment.

Find the Cloud ID for your deployment by going to https://cloud.elastic.co/deployments and selecting your deployment.

```python
CLOUD_ID = getpass("Elastic deployment Cloud ID")
CLOUD_PASSWORD = getpass("Elastic deployment Password")
client = Elasticsearch(
  cloud_id = CLOUD_ID,
  basic_auth=("elastic", CLOUD_PASSWORD) # Alternatively use `api_key` instead of `basic_auth`
)

# Test connection to Elasticsearch
print(client.info())
```

??? note "輸出"

    ```text
    {'name': 'instance-0000000001', 'cluster_name': '29ef9817e13142f5ba0ea7b29c2a86e2', 'cluster_uuid': 'absjWgQvRw63IlwWKisN8w', 'version': {'number': '8.9.1', 'build_flavor': 'default', 'build_type': 'docker', 'build_hash': 'a813d015ef1826148d9d389bd1c0d781c6e349f0', 'build_date': '2023-08-10T05:02:32.517455352Z', 'build_snapshot': False, 'lucene_version': '9.7.0', 'minimum_wire_compatibility_version': '7.17.0', 'minimum_index_compatibility_version': '7.0.0'}, 'tagline': 'You Know, for Search'}
    ```

## Download the dataset 

In this step we download the OpenAI Wikipedia embeddings dataset, and extract the zip file.

```python
embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'
wget.download(embeddings_url)

with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip",
"r") as zip_ref:
    zip_ref.extractall("data")
```

##  Read CSV file into a Pandas DataFrame

Next we use the Pandas library to read the unzipped CSV file into a DataFrame. This step makes it easier to index the data into Elasticsearch in bulk.

```python

wikipedia_dataframe = pd.read_csv("data/vector_database_wikipedia_articles_embedded.csv")
```

## Create index with mapping

Now we need to create an Elasticsearch index with the necessary mappings. This will enable us to index the data into Elasticsearch.

We use the `dense_vector` field type for the `title_vector` and  `content_vector` fields. This is a special field type that allows us to store dense vectors in Elasticsearch.

Later, we'll need to target the `dense_vector` field for kNN search.


```python
index_mapping= {
    "properties": {
      "title_vector": {
          "type": "dense_vector",
          "dims": 1536,
          "index": "true",
          "similarity": "cosine"
      },
      "content_vector": {
          "type": "dense_vector",
          "dims": 1536,
          "index": "true",
          "similarity": "cosine"
      },
      "text": {"type": "text"},
      "title": {"type": "text"},
      "url": { "type": "keyword"},
      "vector_id": {"type": "long"}
      
    }
}

client.indices.create(index="wikipedia_vector_index", mappings=index_mapping)
```

??? note "輸出"

    ```text
    ObjectApiResponse({'acknowledged': True, 'shards_acknowledged': True, 'index': 'wikipedia_vector_index'})
    ```

## Index data into Elasticsearch 

The following function generates the required bulk actions that can be passed to Elasticsearch's Bulk API, so we can index multiple documents efficiently in a single request.

For each row in the DataFrame, the function yields a dictionary representing a single document to be indexed. 

```python
def dataframe_to_bulk_actions(df):
    for index, row in df.iterrows():
        yield {
            "_index": 'wikipedia_vector_index',
            "_id": row['id'],
            "_source": {
                'url' : row["url"],
                'title' : row["title"],
                'text' : row["text"],
                'title_vector' : json.loads(row["title_vector"]),
                'content_vector' : json.loads(row["content_vector"]),
                'vector_id' : row["vector_id"]
            }
        }
```

As the dataframe is large, we will index data in batches of `100`. We index the data into Elasticsearch using the Python client's [helpers](https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/client-helpers.html#bulk-helpers) for the bulk API.

```python
start = 0
end = len(wikipedia_dataframe)
batch_size = 100
for batch_start in range(start, end, batch_size):
    batch_end = min(batch_start + batch_size, end)
    batch_dataframe = wikipedia_dataframe.iloc[batch_start:batch_end]
    actions = dataframe_to_bulk_actions(batch_dataframe)
    helpers.bulk(client, actions)
```

Let's test the index with a simple match query.

```python
print(client.search(index="wikipedia_vector_index", body={
    "_source": {
        "excludes": ["title_vector", "content_vector"]
    },
    "query": {
        "match": {
            "text": {
                "query": "Hummingbird"
            }
        }
    }
}))
```

??? note "輸出"

    ```text
    /var/folders/vz/v2f6_x6s0kg51j2vbm5rlhww0000gn/T/ipykernel_27262/2105931364.py:1: DeprecationWarning: The 'body' parameter is deprecated and will be removed in a future version. Instead use individual parameters.
      print(client.search(index="wikipedia_vector_index", body={
    ```

## Encode a question with OpenAI embedding model

To perform semantic search, we need to encode queries with the same embedding model used to encode the documents at index time.
In this example, we need to use the `text-embedding-3-small` model.

You'll need your OpenAI [API key](https://platform.openai.com/account/api-keys) to generate the embeddings.

```python
# Create OpenAI client
openai_client = OpenAI()

# Define question
question = 'Is the Atlantic the biggest ocean in the world?'

question_embedding = openai_client.embeddings.create(
    input=question,
    model="text-embedding-3-small"
)
```

## Run semantic search queries

Now we're ready to run queries against our Elasticsearch index using our encoded question. We'll be doing a k-nearest neighbors search, using the Elasticsearch [kNN query](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html) option.

First, we define a small function to pretty print the results.

```python
# Function to pretty print Elasticsearch results

def pretty_response(response):
    for hit in response['hits']['hits']:
        id = hit['_id']
        score = hit['_score']
        title = hit['_source']['title']
        text = hit['_source']['text']
        pretty_output = (f"\nID: {id}\nTitle: {title}\nSummary: {text}\nScore: {score}")
        print(pretty_output)
```

Now let's run our `kNN` query.

```python
response = client.search(
  index = "wikipedia_vector_index",
  knn={
      "field": "content_vector",
      "query_vector":  question_embedding.data[0].embedding,
      "k": 10,
      "num_candidates": 100
    }
)
pretty_response(response)
```

??? note "輸出"

    ```text

    ID: 1936
    Title: Atlantic Ocean
    Summary: The Atlantic Ocean is the world's second largest ocean.  It covers a total area of about . It covers about 20 percent of the Earth's surface. It is named after the god Atlas from Greek mythology.

    Geologic history 
    The Atlantic formed when the Americas moved west from Eurasia and Africa. This began sometime in the Cretaceous period, roughly 135 million years ago. It was part of the break-up of the supercontinent Pangaea.

    The east coast of South America is shaped somewhat like the west coast of Africa, and this gave a clue that continents moved over long periods of time (continental drift). The Atlantic Ocean is still growing now, because of sea-floor spreading from the mid-Atlantic Ridge, while the Pacific Ocean is said to be shrinking because the sea floor is folding under itself or subducting into the mantle.

    Geography
    The Atlantic Ocean is bounded on the west by North and South America. It connects to the Arctic Ocean through the Denmark Strait, Greenland Sea, Norwegian Sea and Barents Sea. It connects with the Mediterranean Sea through the Strait of Gibraltar.

    In the southeast, the Atlantic merges into the Indian Ocean. The 20° East meridian defines its border.

    In the southwest, the Drake Passage connects it to the Pacific Ocean. The Panama Canal links the Atlantic and Pacific.

    The Atlantic Ocean is second in size to the Pacific. It occupies an area of about . The volume of the Atlantic, along with its adjacent seas (the seas next to it), is 354,700,000 cubic kilometres.

    The average depth of the Atlantic, along with its adjacent seas, is . The greatest depth is Milwaukee Deep near Puerto Rico, where the Ocean is  deep.

    Gulf Stream 
    The Atlantic Ocean has important ocean currents.  One of these, called the Gulf Stream, flows across the North Atlantic.  Water gets heated by the sun in the Caribbean Sea and then moves northwest toward the North Pole.  This makes France, the British Isles, Iceland, and Norway in Europe much warmer in winter than Newfoundland and Nova Scotia in Canada. Without the Gulf Stream, the climates of northeast Canada and northwest Europe might be the same, because these places are about the same distance from the North Pole.

    There are currents in the South Atlantic too, but the shape of this sea means that it has less effect on South Africa.

    Geology 
    The main feature of the Atlantic Ocean's seabed is a large underwater mountain chain called the Mid-Atlantic Ridge.  It runs from north to south under the Ocean. This is at the boundary of four tectonic plates: Eurasian, North American, South American and African. The ridge extends from Iceland in the north to about 58° south.

    The salinity of the surface waters of the open ocean ranges from 3337 parts per thousand and varies with latitude and season.

    References

    Other websites 
    LA Times special Altered Oceans 
    Oceanography Image of the Day, from the Woods Hole Oceanographic Institution
    National Oceanic and Atmospheric Administration 
    NOAA In-situ Ocean Data Viewer  Plot and download ocean observations

    www.cartage.org.lb 
    ... (省略 325 行)
    ```

## Next steps

Success! Now you know how to use Elasticsearch as a vector database to store embeddings, encode queries by calling the OpenAI `embeddings` endpoint, and run semantic search.

Play around with different queries, and if you want to try with your own data, you can experiment with different embedding models.

ℹ️ Check out our other notebook [Retrieval augmented generation using Elasticsearch and OpenAI](elasticsearch-retrieval-augmented-generation.md). That notebook builds on this example to demonstrate how to use Elasticsearch together with the OpenAI [chat completions](https://platform.openai.com/docs/api-reference/chat) API for retrieval augmented generation (RAG).

<!-- tutor:summary -->
