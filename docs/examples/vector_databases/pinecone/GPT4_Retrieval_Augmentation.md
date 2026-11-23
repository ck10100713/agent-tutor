---
translated: true
source: examples/vector_databases/pinecone/GPT4_Retrieval_Augmentation.ipynb
---

# 用 Pinecone 為 GPT-4 做 retrieval augmentation

> 原文：[examples/vector_databases/pinecone/GPT4_Retrieval_Augmentation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/GPT4_Retrieval_Augmentation.ipynb)



## 這篇在做什麼
示範怎麼從 Pinecone 查出跟問題相關的 context，再交給 GPT-4 產生有真實資料來源支撐的答案，藉此減少 LLM 亂編。資料用的是 LangChain 文件。

## 學完你會
- 下載並處理文件、切成約 400 token 的 chunk
- 用 `text-embedding-3-small` 算 embedding，並寫入 Pinecone index
- 檢索相關 chunk，放進 GPT-4 的 prompt 做 RAG，並比較有無 augmentation 的回答差異

## 開跑前
需要 OpenAI API key 和 Pinecone 的 [免費 API key](https://app.pinecone.io/)。

#### 修正會亂編的 LLM

這份 notebook 會學到怎麼從 Pinecone 查出跟問題相關的 context，再把它們交給 GPT-4 模型，產生有真實資料來源支撐的答案。

GPT-4 比之前的 OpenAI completion 模型進步很多。它也只用 `ChatCompletion` endpoint，所以用法跟平常稍有不同。不過這個模型的能力讓這點改變很值得，尤其是搭配 Pinecone 向量資料庫這類外部知識庫時。

這份 notebook 需要安裝：

```python
!pip install -qU bs4 tiktoken openai langchain pinecone-client[grpc]
```

??? note "輸出"

    ```text
    [?25l     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0.0/1.7 MB ? eta -:--:--
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸ 1.7/1.7 MB 71.4 MB/s eta 0:00:01
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.7/1.7 MB 41.5 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 70.1/70.1 KB 6.5 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 396.0/396.0 KB 28.4 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 177.2/177.2 KB 12.1 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 62.8/62.8 KB 4.8 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 4.8 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 58.3/58.3 KB 8.0 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.1/1.1 MB 43.0 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.3/1.3 MB 77.1 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 158.8/158.8 KB 19.6 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 199.2/199.2 KB 26.0 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 264.6/264.6 KB 35.1 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 114.2/114.2 KB 15.6 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 49.1/49.1 KB 7.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 218.0/218.0 KB 27.4 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 218.0/218.0 KB 28.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 211.7/211.7 KB 12.0 MB/s eta 0:00:00
    [?25hERROR: pip's dependency resolver does not currently take into account all the packages that are installed. This behaviour is the source of the following dependency conflicts.
    google-cloud-translate 3.8.4 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    google-cloud-language 2.6.1 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    google-cloud-firestore 2.7.3 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    google-cloud-datastore 2.11.1 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    google-cloud-bigquery 3.4.2 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    google-cloud-bigquery-storage 2.19.0 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    google-api-core 2.11.0 requires protobuf!=3.20.0,!=3.20.1,!=4.21.0,!=4.21.1,!=4.21.2,!=4.21.3,!=4.21.4,!=4.21.5,<5.0.0dev,>=3.19.5, but you have protobuf 3.19.3 which is incompatible.
    ```

## 準備資料

這個範例會從 [langchain.readthedocs.io/](https://langchain.readthedocs.io/latest/en/) 下載 LangChain 文件。我們這樣取得網站上所有 `.html` 檔案：

```python
!wget -r -A.html -P rtdocs https://python.langchain.com/en/latest/
```

??? note "輸出"

    ```text
    <Response [200]>
    ```

這會把所有 HTML 下載到 `rtdocs` 目錄。接著可以用 LangChain 本身來處理這些文件，做法是用 `ReadTheDocsLoader`：

```python
from langchain.document_loaders import ReadTheDocsLoader

loader = ReadTheDocsLoader('rtdocs')
docs = loader.load()
len(docs)
```

??? note "輸出"

    ```text
    .rst .pdf Welcome to LangChain Contents Getting Started Modules Use Cases Reference Docs LangChain Ecosystem Additional Resources Welcome to LangChain# Large language models (LLMs) are emerging as a transformative technology, enabling developers to build applications that they previously could not. But using these LLMs in isolation is often not enough to create a truly powerful app - the real power comes when you are able to combine them with other sources of computation or knowledge. This library is aimed at assisting in the development of those types of applications. Common examples of these types of applications include: ❓ Question Answering over specific documents Documentation End-to-end Example: Question Answering over Notion Database 💬 Chatbots Documentation End-to-end Example: Chat-LangChain 🤖 Agents Documentation End-to-end Example: GPT+WolframAlpha Getting Started# Checkout the below guide for a walkthrough of how to get started using LangChain to create an Language Model application. Getting Started Documentation Modules# There are several main modules that LangChain provides support for. For each module we provide some examples to get started, how-to guides, reference docs, and conceptual guides. These modules are, in increasing order of complexity: Prompts: This includes prompt management, prompt optimization, and prompt serialization. LLMs: This includes a generic interface for all LLMs, and common utilities for working with LLMs. Document Loaders: This includes a standard interface for loading documents, as well as specific integrations to all types of text data sources. Utils: Language models are often more powerful when interacting with other sources of knowledge or computation. This can include Python REPLs, embeddings, search engines, and more. LangChain provides a large collection of common utils to use in your application. Chains: Chains go beyond just a single LLM call, and are sequences of calls (whether to an LLM or a different utility). LangChain provides a standard interface for chains, lots of integrations with other tools, and end-to-end chains for common applications. Indexes: Language models are often more powerful when combined with your own text data - this module covers best practices for doing exactly that. Agents: Agents involve an LLM making decisions about which Actions to take, taking that Action, seeing an Observation, and repeating that until done. LangChain provides a standard interface for agents, a selection of agents to choose from, and examples of end to end agents. Memory: Memory is the concept of persisting state between calls of a chain/agent. LangChain provides a standard interface for memory, a collection of memory implementations, and examples of chains/agents that use memory. Chat: Chat models are a variation on Language Models that expose a different API - rather than working with raw text, they work with messages. LangChain provides a standard interface for working with them and doing all the same things as above. Use Cases# The above modules can be used in a variety of ways. LangChain also provides guidance and assistance in this. Below are some of the common use cases LangChain supports. Agents: Agents are systems that use a language model to interact with other tools. These can be used to do more grounded question/answering, interact with APIs, or even take actions. Chatbots: Since language models are good at producing text, that makes them ideal for creating chatbots. Data Augmented Generation: Data Augmented Generation involves specific types of chains that first interact with an external datasource to fetch data to use in the generation step. Examples of this include summarization of long pieces of text and question/answering over specific data sources. Question Answering: Answering questions over specific documents, only utilizing the information in those documents to construct an answer. A type of Data Augmented Generation. Summarization: Summarizing longer documents into shorter, more condensed chunks of information. A type of Data Augmented Generation. Evaluation: Generative models are notoriously hard to evaluate with traditional metrics. One new way of evaluating them is using language models themselves to do the evaluation. LangChain provides some prompts/chains for assisting in this. Generate similar examples: Generating similar examples to a given input. This is a common use case for many applications, and LangChain provides some prompts/chains for assisting in this. Compare models: Experimenting with different prompts, models, and chains is a big part of developing the best possible application. The ModelLaboratory makes it easy to do so. Reference Docs# All of LangChain’s reference documentation, in one place. Full documentation on all methods, classes, installation methods, and integration setups for LangChain. Reference Documentation LangChain Ecosystem# Guides for how other companies/products can be used with LangChain LangChain Ecosystem Additional Resources# Additional collection of resources we think may be useful as you develop your application! LangChainHub: The LangChainHub is a place to share and explore other prompts, chains, and agents. Glossary: A glossary of all related terms, papers, methods, etc. Whether implemented in LangChain or not! Gallery: A collection of our favorite projects that use LangChain. Useful for finding inspiration or seeing how things were done in other applications. Deployments: A collection of instructions, code snippets, and template repositories for deploying LangChain apps. Discord: Join us on our Discord to discuss all things LangChain! Tracing: A guide on using tracing in LangChain to visualize the execution of chains and agents. Production Support: As you move your LangChains into production, we’d love to offer more comprehensive support. Please fill out this form and we’ll set up a dedicated support Slack channel. next Quickstart Guide Contents Getting Started Modules Use Cases Reference Docs LangChain Ecosystem Additional Resources By Harrison Chase © Copyright 2022, Harrison Chase. Last updated on Mar 15, 2023.
    ```

這樣我們得到數百頁處理過的文件頁面。來看看每一頁包含的格式：

```python
docs[0]
```

我們這樣取得純文字的頁面內容：

```python
print(docs[0].page_content)
```

```python
print(docs[5].page_content)
```

也可以找到每份文件的來源：

```python
docs[5].metadata['source'].replace('rtdocs/', 'https://')
```

可以用這些建立我們的 `data` 清單：

```python
data = []

for doc in docs:
    data.append({
        'url': doc.metadata['source'].replace('rtdocs/', 'https://'),
        'text': doc.page_content
    })
```

```python
data[3]
```

??? note "輸出"

    ```text
    {'url': 'https://langchain.readthedocs.io/en/latest/modules/memory/types/entity_summary_memory.html',
     'text': '.ipynb .pdf Entity Memory Contents Using in a chain Inspecting the memory store Entity Memory# This notebook shows how to work with a memory module that remembers things about specific entities. It extracts information on entities (using LLMs) and builds up its knowledge about that entity over time (also using LLMs). Let’s first walk through using this functionality. from langchain.llms import OpenAI from langchain.memory import ConversationEntityMemory llm = OpenAI(temperature=0) memory = ConversationEntityMemory(llm=llm) _input = {"input": "Deven & Sam are working on a hackathon project"} memory.load_memory_variables(_input) memory.save_context( _input, {"ouput": " That sounds like a great project! What kind of project are they working on?"} ) memory.load_memory_variables({"input": \'who is Sam\'}) {\'history\': \'Human: Deven & Sam are working on a hackathon project\\nAI: That sounds like a great project! What kind of project are they working on?\', \'entities\': {\'Sam\': \'Sam is working on a hackathon project with Deven.\'}} memory = ConversationEntityMemory(llm=llm, return_messages=True) _input = {"input": "Deven & Sam are working on a hackathon project"} memory.load_memory_variables(_input) memory.save_context( _input, {"ouput": " That sounds like a great project! What kind of project are they working on?"} ) memory.load_memory_variables({"input": \'who is Sam\'}) {\'history\': [HumanMessage(content=\'Deven & Sam are working on a hackathon project\', additional_kwargs={}), AIMessage(content=\' That sounds like a great project! What kind of project are they working on?\', additional_kwargs={})], \'entities\': {\'Sam\': \'Sam is working on a hackathon project with Deven.\'}} Using in a chain# Let’s now use it in a chain! from langchain.chains import ConversationChain from langchain.memory import ConversationEntityMemory from langchain.memory.prompt import ENTITY_MEMORY_CONVERSATION_TEMPLATE from pydantic import BaseModel from typing import List, Dict, Any conversation = ConversationChain( llm=llm, verbose=True, prompt=ENTITY_MEMORY_CONVERSATION_TEMPLATE, memory=ConversationEntityMemory(llm=llm) ) conversation.predict(input="Deven & Sam are working on a hackathon project") > Entering new ConversationChain chain... Prompt after formatting: You are an assistant to a human, powered by a large language model trained by OpenAI. You are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand. You are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics. Overall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist. Context: {\'Deven\': \'\', \'Sam\': \'\'} Current conversation: Last line: Human: Deven & Sam are working on a hackathon project You: > Finished chain. \' That sounds like a great project! What kind of project are they working on?\' conversation.memory.store {\'Deven\': \'Deven is working on a hackathon project with Sam.\', \'Sam\': \'Sam is working on a hackathon project with Deven.\'} conversation.predict(input="They are trying to add more complex memory structures to Langchain") > Entering new ConversationChain chain... Prompt after formatting: You are an assistant to a human, powered by a large language model trained by OpenAI. You are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand. You are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics. Overall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist. Context: {\'Deven\': \'Deven is working on a hackathon project with Sam.\', \'Sam\': \'Sam is working on a hackathon project with Deven.\', \'Langchain\': \'\'} Current conversation: Human: Deven & Sam are working on a hackathon project AI: That sounds like a great project! What kind of project are they working on? Last line: Human: They are trying to add more complex memory structures to Langchain You: > Finished chain. \' That sounds like an interesting project! What kind of memory structures are they trying to add?\' conversation.predict(input="They are adding in a key-value store for entities mentioned so far in the conversation.") > Entering new ConversationChain chain... Prompt after formatting: You are an assistant to a human, powered by a large language model trained by OpenAI. You are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand. You are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics. Overall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist. Context: {\'Deven\': \'Deven is working on a hackathon project with Sam, attempting to add more complex memory structures to Langchain.\', \'Sam\': \'Sam is working on a hackathon project with Deven, trying to add more complex memory structures to Langchain.\', \'Langchain\': \'Langchain is a project that is trying to add more complex memory structures.\', \'Key-Value Store\': \'\'} Current conversation: Human: Deven & Sam are working on a hackathon project AI: That sounds like a great project! What kind of project are they working on? Human: They are trying to add more complex memory structures to Langchain AI: That sounds like an interesting project! What kind of memory structures are they trying to add? Last line: Human: They are adding in a key-value store for entities mentioned so far in the conversation. You: > Finished chain. \' That sounds like a great idea! How will the key-value store work?\' conversation.predict(input="What do you know about Deven & Sam?") > Entering new ConversationChain chain... Prompt after formatting: You are an assistant to a human, powered by a large language model trained by OpenAI. You are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand. You are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics. Overall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist. Context: {\'Deven\': \'Deven is working on a hackathon project with Sam, attempting to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation.\', \'Sam\': \'Sam is working on a hackathon project with Deven, trying to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation.\'} Current conversation: Human: Deven & Sam are working on a hackathon project AI: That sounds like a great project! What kind of project are they working on? Human: They are trying to add more complex memory structures to Langchain AI: That sounds like an interesting project! What kind of memory structures are they trying to add? Human: They are adding in a key-value store for entities mentioned so far in the conversation. AI: That sounds like a great idea! How will the key-value store work? Last line: Human: What do you know about Deven & Sam? You: > Finished chain. \' Deven and Sam are working on a hackathon project together, attempting to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation.\' Inspecting the memory store# We can also inspect the memory store directly. In the following examaples, we look at it directly, and then go through some examples of adding information and watch how it changes. from pprint import pprint pprint(conversation.memory.store) {\'Deven\': \'Deven is working on a hackathon project with Sam, attempting to add \' \'more complex memory structures to Langchain, including a key-value \' \'store for entities mentioned so far in the conversation.\', \'Key-Value Store\': \'A key-value store that stores entities mentioned in the \' \'conversation.\', \'Langchain\': \'Langchain is a project that is trying to add more complex \' \'memory structures, including a key-value store for entities \' \'mentioned so far in the conversation.\', \'Sam\': \'Sam is working on a hackathon project with Deven, attempting to add \' \'more complex memory structures to Langchain, including a key-value \' \'store for entities mentioned so far in the conversation.\'} conversation.predict(input="Sam is the founder of a company called Daimon.") > Entering new ConversationChain chain... Prompt after formatting: You are an assistant to a human, powered by a large language model trained by OpenAI. You are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand. You are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics. Overall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist. Context: {\'Daimon\': \'\', \'Sam\': \'Sam is working on a hackathon project with Deven to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation.\'} Current conversation: Human: They are trying to add more complex memory structures to Langchain AI: That sounds like an interesting project! What kind of memory structures are they trying to add? Human: They are adding in a key-value store for entities mentioned so far in the conversation. AI: That sounds like a great idea! How will the key-value store work? Human: What do you know about Deven & Sam? AI: Deven and Sam are working on a hackathon project to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation. They seem to be very motivated and passionate about their project, and are working hard to make it a success. Last line: Human: Sam is the founder of a company called Daimon. You: > Finished chain. "\\nThat\'s impressive! It sounds like Sam is a very successful entrepreneur. What kind of company is Daimon?" from pprint import pprint pprint(conversation.memory.store) {\'Daimon\': \'Daimon is a company founded by Sam.\', \'Deven\': \'Deven is working on a hackathon project with Sam to add more \' \'complex memory structures to Langchain, including a key-value store \' \'for entities mentioned so far in the conversation.\', \'Key-Value Store\': \'Key-Value Store: A data structure that stores values \' \'associated with a unique key, allowing for efficient \' \'retrieval of values. Deven and Sam are adding a key-value \' \'store for entities mentioned so far in the conversation.\', \'Langchain\': \'Langchain is a project that seeks to add more complex memory \' \'structures, including a key-value store for entities mentioned \' \'so far in the conversation.\', \'Sam\': \'Sam is working on a hackathon project with Deven to add more complex \' \'memory structures to Langchain, including a key-value store for \' \'entities mentioned so far in the conversation. He is also the founder \' \'of a company called Daimon.\'} conversation.predict(input="What do you know about Sam?") > Entering new ConversationChain chain... Prompt after formatting: You are an assistant to a human, powered by a large language model trained by OpenAI. You are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand. You are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics. Overall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist. Context: {\'Sam\': \'Sam is working on a hackathon project with Deven to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation. He is also the founder of a company called Daimon.\', \'Daimon\': \'Daimon is a company founded by Sam.\'} Current conversation: Human: They are adding in a key-value store for entities mentioned so far in the conversation. AI: That sounds like a great idea! How will the key-value store work? Human: What do you know about Deven & Sam? AI: Deven and Sam are working on a hackathon project to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation. They seem to be very motivated and passionate about their project, and are working hard to make it a success. Human: Sam is the founder of a company called Daimon. AI: That\'s impressive! It sounds like Sam is a very successful entrepreneur. What kind of company is Daimon? Last line: Human: What do you know about Sam? You: > Finished chain. \' Sam is the founder of a company called Daimon. He is also working on a hackathon project with Deven to add more complex memory structures to Langchain, including a key-value store for entities mentioned so far in the conversation. He seems to be very motivated and passionate about his project, and is working hard to make it a success.\' previous ConversationBufferWindowMemory next Conversation Knowledge Graph Memory Contents Using in a chain Inspecting the memory store By Harrison Chase © Copyright 2022, Harrison Chase. Last updated on Mar 15, 2023.'}
    ```

看起來很醜，但目前夠用了。來看看怎麼處理全部這些資料。我們會把所有內容切成約 400 token 的 chunk，用 `langchain` 和 `tiktoken` 很容易做到：

```python
import tiktoken

tokenizer = tiktoken.get_encoding('p50k_base')

# create the length function
def tiktoken_len(text):
    tokens = tokenizer.encode(
        text,
        disallowed_special=()
    )
    return len(tokens)
```

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=20,
    length_function=tiktoken_len,
    separators=["\n\n", "\n", " ", ""]
)
```

用這個方式把 `data` 處理成更多 chunk。

```python
from uuid import uuid4
from tqdm.auto import tqdm

chunks = []

for idx, record in enumerate(tqdm(data)):
    texts = text_splitter.split_text(record['text'])
    chunks.extend([{
        'id': str(uuid4()),
        'text': texts[i],
        'chunk': i,
        'url': record['url']
    } for i in range(len(texts))])
```

??? note "輸出"

    ```text
      0%|          | 0/231 [00:00<?, ?it/s]
    ```

chunk 準備好了，接著要做 embedding 和索引。

## 初始化 Embedding 模型

我們用 `text-embedding-3-small` 當 embedding 模型。可以這樣對文字做 embedding：

```python
import openai

# initialize openai API key
openai.api_key = "sk-..."

embed_model = "text-embedding-3-small"

res = openai.Embedding.create(
    input=[
        "Sample document text goes here",
        "there will be several phrases in each batch"
    ], engine=embed_model
)
```

在回應 `res` 裡，會看到一個類似 JSON 的物件，新的 embedding 放在 `'data'` 欄位裡。

```python
res.keys()
```

??? note "輸出"

    ```text
    dict_keys(['object', 'data', 'model', 'usage'])
    ```

`'data'` 裡會有兩筆記錄，對應剛剛做 embedding 的兩個句子。每個向量 embedding 有 `1536` 個維度（也就是 `text-embedding-3-small` 模型輸出的維度）。

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

我們會對剛抓下來的 langchain 文件資料集套用同樣的 embedding 邏輯。但在這之前，必須先建立一個存放 embedding 的地方。

## 初始化 Index

現在需要一個地方存放這些 embedding，並能對它們做高效率的向量搜尋。為此我們用 Pinecone，可以取得[免費 API key](https://app.pinecone.io/)，填在下面，我們會初始化跟 Pinecone 的連線並建立新的 index。

```python
import pinecone

index_name = 'gpt-4-langchain-docs'

# initialize connection to pinecone
pinecone.init(
    api_key="PINECONE_API_KEY",  # app.pinecone.io (console)
    environment="PINECONE_ENVIRONMENT"  # next to API key in console
)

# check if index already exists (it shouldn't if this is first time)
if index_name not in pinecone.list_indexes():
    # if does not exist, create index
    pinecone.create_index(
        index_name,
        dimension=len(res['data'][0]['embedding']),
        metric='dotproduct'
    )
# connect to index
index = pinecone.GRPCIndex(index_name)
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

可以看到 index 目前是空的，`total_vector_count` 是 `0`。我們可以這樣開始用 OpenAI `text-embedding-3-small` 建出的 embedding 填入資料：

```python
from tqdm.auto import tqdm
import datetime
from time import sleep

batch_size = 100  # how many embeddings we create and insert at once

for i in tqdm(range(0, len(chunks), batch_size)):
    # find end of batch
    i_end = min(len(chunks), i+batch_size)
    meta_batch = chunks[i:i_end]
    # get ids
    ids_batch = [x['id'] for x in meta_batch]
    # get texts to encode
    texts = [x['text'] for x in meta_batch]
    # create embeddings (try-except added to avoid RateLimitError)
    try:
        res = openai.Embedding.create(input=texts, engine=embed_model)
    except:
        done = False
        while not done:
            sleep(5)
            try:
                res = openai.Embedding.create(input=texts, engine=embed_model)
                done = True
            except:
                pass
    embeds = [record['embedding'] for record in res['data']]
    # cleanup metadata
    meta_batch = [{
        'text': x['text'],
        'chunk': x['chunk'],
        'url': x['url']
    } for x in meta_batch]
    to_upsert = list(zip(ids_batch, embeds, meta_batch))
    # upsert to Pinecone
    index.upsert(vectors=to_upsert)
```

??? note "輸出"

    ```text
      0%|          | 0/12 [00:00<?, ?it/s]
    ```

現在我們已經把所有 langchain 文件加進 index。接著可以進入檢索，然後用 GPT-4 產生答案。

## 檢索

要搜尋我們的文件，首先要建立查詢向量 `xq`。用 `xq` 就能從 LangChain 文件檢索出最相關的 chunk，像這樣：

```python
query = "how do I use the LLMChain in LangChain?"

res = openai.Embedding.create(
    input=[query],
    engine=embed_model
)

# retrieve from Pinecone
xq = res['data'][0]['embedding']

# get relevant contexts (including the questions)
res = index.query(xq, top_k=5, include_metadata=True)
```

```python
res
```

??? note "輸出"

    ```text
    {'matches': [{'id': '1fec660b-9937-4f7e-9692-280c8cc7ce0d',
                  'metadata': {'chunk': 0.0,
                               'text': '.rst .pdf Chains Chains# Using an LLM in '
                                       'isolation is fine for some simple '
                                       'applications, but many more complex ones '
                                       'require chaining LLMs - either with each '
                                       'other or with other experts. LangChain '
                                       'provides a standard interface for Chains, '
                                       'as well as some common implementations of '
                                       'chains for ease of use. The following '
                                       'sections of documentation are provided: '
                                       'Getting Started: A getting started guide '
                                       'for chains, to get you up and running '
                                       'quickly. Key Concepts: A conceptual guide '
                                       'going over the various concepts related to '
                                       'chains. How-To Guides: A collection of '
                                       'how-to guides. These highlight how to use '
                                       'various types of chains. Reference: API '
                                       'reference documentation for all Chain '
                                       'classes. previous Vector DB Text '
                                       'Generation next Getting Started By '
                                       'Harrison Chase © Copyright 2022, Harrison '
                                       'Chase. Last updated on Mar 15, 2023.',
                               'url': 'https://langchain.readthedocs.io/en/latest/modules/chains.html'},
                  'score': 0.8848499,
                  'sparse_values': {'indices': [], 'values': []},
                  'values': []},
                 {'id': 'fe48438d-228a-4e0e-b41e-5cb5c6ba1482',
                  'metadata': {'chunk': 0.0,
                               'text': '.rst .pdf LLMs LLMs# Large Language Models '
                                       '(LLMs) are a core component of LangChain. '
                                       'LangChain is not a provider of LLMs, but '
                                       'rather provides a standard interface '
                                       'through which you can interact with a '
                                       'variety of LLMs. The following sections of '
                                       'documentation are provided: Getting '
                                       'Started: An overview of all the '
                                       'functionality the LangChain LLM class '
                                       'provides. Key Concepts: A conceptual guide '
                                       'going over the various concepts related to '
    ... (省略 129 行)
    ```

檢索完成後，接著把這些內容餵給 GPT-4 產生答案。

## Retrieval Augmented Generation

GPT-4 目前是透過 OpenAI 的 `ChatCompletions` endpoint 存取。要把檢索到的資訊加進模型，需要把它放進 user prompt，*跟*原本的問題放在一起。可以這樣做：

```python
# get list of retrieved text
contexts = [item['metadata']['text'] for item in res['matches']]

augmented_query = "\n\n---\n\n".join(contexts)+"\n\n-----\n\n"+query
```

```python
print(augmented_query)
```

??? note "輸出"

    ```text
    .rst .pdf Chains Chains# Using an LLM in isolation is fine for some simple applications, but many more complex ones require chaining LLMs - either with each other or with other experts. LangChain provides a standard interface for Chains, as well as some common implementations of chains for ease of use. The following sections of documentation are provided: Getting Started: A getting started guide for chains, to get you up and running quickly. Key Concepts: A conceptual guide going over the various concepts related to chains. How-To Guides: A collection of how-to guides. These highlight how to use various types of chains. Reference: API reference documentation for all Chain classes. previous Vector DB Text Generation next Getting Started By Harrison Chase © Copyright 2022, Harrison Chase. Last updated on Mar 15, 2023.

    ---

    .rst .pdf LLMs LLMs# Large Language Models (LLMs) are a core component of LangChain. LangChain is not a provider of LLMs, but rather provides a standard interface through which you can interact with a variety of LLMs. The following sections of documentation are provided: Getting Started: An overview of all the functionality the LangChain LLM class provides. Key Concepts: A conceptual guide going over the various concepts related to LLMs. How-To Guides: A collection of how-to guides. These highlight how to accomplish various objectives with our LLM class, as well as how to integrate with various LLM providers. Reference: API reference documentation for all LLM classes. previous Example Selector next Getting Started By Harrison Chase © Copyright 2022, Harrison Chase. Last updated on Mar 15, 2023.

    ---

    .ipynb .pdf Getting Started Contents Why do we need chains? Query an LLM with the LLMChain Combine chains with the SequentialChain Create a custom chain with the Chain class Getting Started# In this tutorial, we will learn about creating simple chains in LangChain. We will learn how to create a chain, add components to it, and run it. In this tutorial, we will cover: Using a simple LLM chain Creating sequential chains Creating a custom chain Why do we need chains?# Chains allow us to combine multiple components together to create a single, coherent application. For example, we can create a chain that takes user input, formats it with a PromptTemplate, and then passes the formatted response to an LLM. We can build more complex chains by combining multiple chains together, or by combining chains with other components. Query an LLM with the LLMChain# The LLMChain is a simple chain that takes in a prompt template, formats it with the user input and returns the response from an LLM. To use the LLMChain, first create a prompt template. from langchain.prompts import PromptTemplate from langchain.llms import OpenAI llm = OpenAI(temperature=0.9) prompt = PromptTemplate( input_variables=["product"], template="What is a good

    ---

    chain first uses a LLM to construct the url to hit, then makes that request with the Requests wrapper, and finally runs that result through the language model again in order to product a natural language response. Example Notebook LLMBash Chain Links Used: BashProcess, LLMChain Notes: This chain takes user input (a question), uses an LLM chain to convert it to a bash command to run in the terminal, and then returns that as the result. Example Notebook LLMChecker Chain Links Used: LLMChain Notes: This chain takes user input (a question), uses an LLM chain to answer that question, and then uses other LLMChains to self-check that answer. Example Notebook LLMRequests Chain Links Used: Requests, LLMChain Notes: This chain takes a URL and other inputs, uses Requests to get the data at that URL, and then passes that along with the other inputs into an LLMChain to generate a response. The example included shows how to ask a question to Google - it firsts constructs a Google url, then fetches the data there, then passes that data + the original question into an LLMChain to get an answer. Example Notebook Moderation Chain Links Used: LLMChain, ModerationChain Notes: This chain shows how to use OpenAI’s content

    ---

    Prompts: This includes prompt management, prompt optimization, and prompt serialization. LLMs: This includes a generic interface for all LLMs, and common utilities for working with LLMs. Document Loaders: This includes a standard interface for loading documents, as well as specific integrations to all types of text data sources. Utils: Language models are often more powerful when interacting with other sources of knowledge or computation. This can include Python REPLs, embeddings, search engines, and more. LangChain provides a large collection of common utils to use in your application. Chains: Chains go beyond just a single LLM call, and are sequences of calls (whether to an LLM or a different utility). LangChain provides a standard interface for chains, lots of integrations with other tools, and end-to-end chains for common applications. Indexes: Language models are often more powerful when combined with your own text data - this module covers best practices for doing exactly that. Agents: Agents involve an LLM making decisions about which Actions to take, taking that Action, seeing an Observation, and repeating that until done. LangChain provides a standard interface for agents, a selection of agents to choose from, and examples of end to end agents. Memory: Memory is the

    -----

    how do I use the LLMChain in LangChain?
    ```

現在來問問題：

```python
# system message to 'prime' the model
primer = f"""You are Q&A bot. A highly intelligent system that answers
user questions based on the information provided by the user above
each question. If the information can not be found in the information
provided by the user you truthfully say "I don't know".
"""

res = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": primer},
        {"role": "user", "content": augmented_query}
    ]
)
```

為了漂亮地顯示這個回應，我們用 markdown 來顯示。

```python
from IPython.display import Markdown

display(Markdown(res['choices'][0]['message']['content']))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

來跟沒有 augmentation 的查詢比較一下...

```python
res = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": primer},
        {"role": "user", "content": query}
    ]
)
display(Markdown(res['choices'][0]['message']['content']))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

如果把 `primer` 裡 `"I don't know"` 的部分拿掉呢？

```python
res = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are Q&A bot. A highly intelligent system that answers user questions"},
        {"role": "user", "content": query}
    ]
)
display(Markdown(res['choices'][0]['message']['content']))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 重點整理
- LLM 沒有相關知識時會亂編，把檢索到的真實資料放進 prompt 能讓答案有依據。
- RAG 的流程是切 chunk、embedding、存進向量資料庫、查詢時檢索、再塞進 prompt。
- 回答時 context 要放在 user prompt 裡，跟原問題一起送進 `ChatCompletion`。
- primer 裡有沒有「不知道就說不知道」這類指示，會直接影響模型有沒有照 context 回答。

## 練習
1. 把 chunk 的 token 大小從 400 改成 200 或 800，看檢索結果和答案有什麼變化。
2. 調整檢索回來的 chunk 數量，觀察答案的品質和 prompt 長度的取捨。
3. 把問題換成 LangChain 文件裡沒有的主題，比較有無 `"I don't know"` 指示時的回答。
