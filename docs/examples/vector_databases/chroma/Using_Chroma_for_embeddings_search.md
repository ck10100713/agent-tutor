---
translated: false
source: examples/vector_databases/chroma/Using_Chroma_for_embeddings_search.ipynb
---

# Using Chroma for embeddings search

> 原文：[examples/vector_databases/chroma/Using_Chroma_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/chroma/Using_Chroma_for_embeddings_search.ipynb)



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
- **Chroma**:
    - *Setup*: Here we'll set up the Python client for Chroma. For more details go [here](https://docs.trychroma.com/usage-guide)
    - *Index Data*: We'll create collections with vectors for __titles__ and __content__
    - *Search Data*: We'll run a few searches to confirm it works

Once you've run through this notebook you should have a basic understanding of how to setup and use vector databases, and can move on to more complex use cases making use of our embeddings.

## Setup

Import the required libraries and set the embedding model that we'd like to use.

```python
# Make sure the OpenAI library is installed
%pip install openai

# We'll need to install the Chroma client
%pip install chromadb

# Install wget to pull zip file
%pip install wget

# Install numpy for data manipulation
%pip install numpy
```

??? note "輸出"

    ```text
    Collecting openai
      Obtaining dependency information for openai from https://files.pythonhosted.org/packages/67/78/7588a047e458cb8075a4089d721d7af5e143ff85a2388d4a28c530be0494/openai-0.27.8-py3-none-any.whl.metadata
      Downloading openai-0.27.8-py3-none-any.whl.metadata (13 kB)
    Collecting requests>=2.20 (from openai)
      Obtaining dependency information for requests>=2.20 from https://files.pythonhosted.org/packages/70/8e/0e2d847013cb52cd35b38c009bb167a1a26b2ce6cd6965bf26b47bc0bf44/requests-2.31.0-py3-none-any.whl.metadata
      Using cached requests-2.31.0-py3-none-any.whl.metadata (4.6 kB)
    Collecting tqdm (from openai)
      Using cached tqdm-4.65.0-py3-none-any.whl (77 kB)
    Collecting aiohttp (from openai)
      Obtaining dependency information for aiohttp from https://files.pythonhosted.org/packages/fa/9e/49002fde2a97d7df0e162e919c31cf13aa9f184537739743d1239edd0e67/aiohttp-3.8.5-cp310-cp310-macosx_11_0_arm64.whl.metadata
      Downloading aiohttp-3.8.5-cp310-cp310-macosx_11_0_arm64.whl.metadata (7.7 kB)
    Collecting charset-normalizer<4,>=2 (from requests>=2.20->openai)
      Obtaining dependency information for charset-normalizer<4,>=2 from https://files.pythonhosted.org/packages/ec/a7/96835706283d63fefbbbb4f119d52f195af00fc747e67cc54397c56312c8/charset_normalizer-3.2.0-cp310-cp310-macosx_11_0_arm64.whl.metadata
      Using cached charset_normalizer-3.2.0-cp310-cp310-macosx_11_0_arm64.whl.metadata (31 kB)
    Collecting idna<4,>=2.5 (from requests>=2.20->openai)
      Using cached idna-3.4-py3-none-any.whl (61 kB)
    Collecting urllib3<3,>=1.21.1 (from requests>=2.20->openai)
      Obtaining dependency information for urllib3<3,>=1.21.1 from https://files.pythonhosted.org/packages/9b/81/62fd61001fa4b9d0df6e31d47ff49cfa9de4af03adecf339c7bc30656b37/urllib3-2.0.4-py3-none-any.whl.metadata
      Downloading urllib3-2.0.4-py3-none-any.whl.metadata (6.6 kB)
    Collecting certifi>=2017.4.17 (from requests>=2.20->openai)
      Using cached certifi-2023.5.7-py3-none-any.whl (156 kB)
    Collecting attrs>=17.3.0 (from aiohttp->openai)
      Using cached attrs-23.1.0-py3-none-any.whl (61 kB)
    Collecting multidict<7.0,>=4.5 (from aiohttp->openai)
      Using cached multidict-6.0.4-cp310-cp310-macosx_11_0_arm64.whl (29 kB)
    Collecting async-timeout<5.0,>=4.0.0a3 (from aiohttp->openai)
      Using cached async_timeout-4.0.2-py3-none-any.whl (5.8 kB)
    Collecting yarl<2.0,>=1.0 (from aiohttp->openai)
      Using cached yarl-1.9.2-cp310-cp310-macosx_11_0_arm64.whl (62 kB)
    Collecting frozenlist>=1.1.1 (from aiohttp->openai)
      Obtaining dependency information for frozenlist>=1.1.1 from https://files.pythonhosted.org/packages/67/6a/55a49da0fa373ac9aa49ccd5b6393ecc183e2a0904d9449ea3ee1163e0b1/frozenlist-1.4.0-cp310-cp310-macosx_11_0_arm64.whl.metadata
      Downloading frozenlist-1.4.0-cp310-cp310-macosx_11_0_arm64.whl.metadata (5.2 kB)
    Collecting aiosignal>=1.1.2 (from aiohttp->openai)
      Using cached aiosignal-1.3.1-py3-none-any.whl (7.6 kB)
    Using cached openai-0.27.8-py3-none-any.whl (73 kB)
    Using cached requests-2.31.0-py3-none-any.whl (62 kB)
    Downloading aiohttp-3.8.5-cp310-cp310-macosx_11_0_arm64.whl (343 kB)
    [2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 343.9/343.9 kB 11.4 MB/s eta 0:00:00
    [?25hUsing cached charset_normalizer-3.2.0-cp310-cp310-macosx_11_0_arm64.whl (124 kB)
    Downloading frozenlist-1.4.0-cp310-cp310-macosx_11_0_arm64.whl (46 kB)
    ... (省略 141 行)
    ```

```python
import openai
import pandas as pd
import os
import wget
from ast import literal_eval

# Chroma's client library for Python
import chromadb

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

??? note "輸出"

    ```text
    'vector_database_wikipedia_articles_embedded.zip'
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

# Chroma

We'll index these embedded documents in a vector database and search them. The first option we'll look at is **Chroma**, an easy to use open-source self-hosted in-memory vector database, designed for working with embeddings together with LLMs. 

In this section, we will:
- Instantiate the Chroma client
- Create collections for each class of embedding 
- Query each collection 

### Instantiate the Chroma client

Create the Chroma client. By default, Chroma is ephemeral and runs in memory. 
However, you can easily set up a persistent configuration which writes to disk.

```python
chroma_client = chromadb.EphemeralClient() # Equivalent to chromadb.Client(), ephemeral.
# Uncomment for persistent client
# chroma_client = chromadb.PersistentClient()
```

### Create collections

Chroma collections allow you to store and filter with arbitrary metadata, making it easy to query subsets of the embedded data. 

Chroma is already integrated with OpenAI's embedding functions. The best way to use them is on construction of a collection, as follows.
Alternatively, you can 'bring your own embeddings'. More information can be found [here](https://docs.trychroma.com/embeddings)

```python
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

if os.getenv("OPENAI_API_KEY") is not None:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    print ("OPENAI_API_KEY is ready")
else:
    print ("OPENAI_API_KEY environment variable not found")


embedding_function = OpenAIEmbeddingFunction(api_key=os.environ.get('OPENAI_API_KEY'), model_name=EMBEDDING_MODEL)

wikipedia_content_collection = chroma_client.create_collection(name='wikipedia_content', embedding_function=embedding_function)
wikipedia_title_collection = chroma_client.create_collection(name='wikipedia_titles', embedding_function=embedding_function)
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is ready
    ```

### Populate the collections

Chroma collections allow you to populate, and filter on, whatever metadata you like. Chroma can also store the text alongside the vectors, and return everything in a single `query` call, when this is more convenient. 

For this use-case, we'll just store the embeddings and IDs, and use these to index the original dataframe. 

```python
# Add the content vectors
wikipedia_content_collection.add(
    ids=article_df.vector_id.tolist(),
    embeddings=article_df.content_vector.tolist(),
)

# Add the title vectors
wikipedia_title_collection.add(
    ids=article_df.vector_id.tolist(),
    embeddings=article_df.title_vector.tolist(),
)
```

### Search the collections

Chroma handles embedding queries for you if an embedding function is set, like in this example.

```python
def query_collection(collection, query, max_results, dataframe):
    results = collection.query(query_texts=query, n_results=max_results, include=['distances']) 
    df = pd.DataFrame({
                'id':results['ids'][0], 
                'score':results['distances'][0],
                'title': dataframe[dataframe.vector_id.isin(results['ids'][0])]['title'],
                'content': dataframe[dataframe.vector_id.isin(results['ids'][0])]['text'],
                })
    
    return df
```

```python
title_query_result = query_collection(
    collection=wikipedia_title_collection,
    query="modern art in Europe",
    max_results=10,
    dataframe=article_df
)
title_query_result.head()
```

??? note "輸出"

    ```text
              id     score            title  \
    2      23266  0.249646              Art   
    11777  15436  0.271688  Hellenistic art   
    12178  23265  0.279306    Byzantine art   
    13215  11777  0.294415         Art film   
    15436  22108  0.305937  Renaissance art   

                                                     content  
    2      Art is a creative activity that expresses imag...  
    11777  The art of the Hellenistic time (from 400 B.C....  
    12178  Byzantine art is a form of Christian Greek art...  
    13215  Art films are a type of movie that is very dif...  
    15436  Many of the most famous and best-loved works o...
    ```

```python
content_query_result = query_collection(
    collection=wikipedia_content_collection,
    query="Famous battles in Scottish history",
    max_results=10,
    dataframe=article_df
)
content_query_result.head()
```

??? note "輸出"

    ```text
              id     score            title  \
    2923   13135  0.261328             1651   
    3694   13571  0.277058         Stirling   
    6248    2923  0.294823              841   
    6297   13568  0.300756             1746   
    11702  11708  0.307572  William Wallace   

                                                     content  
    2923   \n\nEvents \n January 1 – Charles II crowned K...  
    3694   Stirling () is a city in the middle of Scotlan...  
    6248   \n\nEvents \n June 25: Battle of Fontenay – Lo...  
    6297   \n\nEvents \n January 8 – Bonnie Prince Charli...  
    11702  William Wallace was a Scottish knight who foug...
    ```

Now that you've got a basic embeddings search running, you can [hop over to the Chroma docs](https://docs.trychroma.com/usage-guide#using-where-filters) to learn more about how to add filters to your query, update/delete data in your collections, and deploy Chroma.

<!-- tutor:summary -->
