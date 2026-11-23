---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Function_calling_finding_nearby_places.ipynb
---

# 用 function calling 找附近地點：結合 Google Places API 與客戶 profile

> 原文：[examples/Function_calling_finding_nearby_places.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Function_calling_finding_nearby_places.ipynb)



## 這篇在做什麼

把 Google Places API 和使用者 profile 結合，讓模型用 function calling 依照個人偏好推薦附近的地點。使用者只要說一句「我餓了」，模型就會決定要呼叫哪個 function、帶什麼參數去查附近的店。

## 學完你會

- 寫一個模擬資料庫查詢的 `fetch_customer_profile`，把 profile 放進 system message 影響模型行為。
- 包裝 Google Places API 的呼叫，只取前兩筆結果以控制費用。
- 用 `functions` 參數讓 GPT-3.5-Turbo 決定何時呼叫 `call_google_places_api`，並處理它的回傳。

## 開跑前

- 需要 Google 帳號和 Google Places API key（付費服務，依呼叫次數計費，請留意用量）。
- 需要 `OPENAI_API_KEY`，以及 `requests` 套件。

這個 notebook 的重點是把 Google Places API 和自訂的使用者 profile 結合，讓位置相關的搜尋更貼近個人。我們的做法是把 Google Places API 和使用者偏好結合，讓地點探索更個人化、更相關。要注意的是，這裡雖然用 Google Places API，但還有很多其他 API 可以用類似的方式探索和應用。

我們會用到三個主要元件：

- 客戶 profile：這個模擬 profile 記錄個人對地點類型的偏好（例如餐廳、公園、博物館）、預算、偏好的評分和其他特定需求。 

- Google Places API：這個 API 提供附近地點的即時資料，會考量周圍地點的評分、場所類型、價格等各種資料。

- Function calling：只要一句指令，例如 "I'm hungry" 或 "I want to visit a museum"，就會觸發 function，結合使用者 profile 資料和 Google Places API 找出合適的場所。

這個 notebook 介紹兩個主要的使用情境：

- 以 profile 為基礎的推薦：學習怎麼建立使用者 profile，並依個人偏好推薦地點。

- 用 function calling 整合 API：了解怎麼有效整合並呼叫 Google Places API，透過 function calling 取得各種地點的即時資料。

這個系統用途很廣，但效果會依使用者偏好和可取得的地點資料而有差異。這個 notebook 的客戶資料是假的，位置也是寫死的。 

## Setup

Google Places API

要使用 Google Places API，需要兩樣東西：

- Google 帳號：如果還沒有，需要建立一個。

- Google Places API Key：API key 是唯一識別碼，用來驗證跟你的 project 相關的 request，作為用量和計費依據。你可以從 [Google Cloud Console](https://console.cloud.google.com/getting-started?authuser=1) 取得 API key。 



請注意 Google Places API 是付費服務，費用跟 API 呼叫次數有關。請持續追蹤用量，避免意外的費用。



也需要 requests 函式庫，可以用以下指令下載： 

```python
pip install requests

```python
import json
from openai import OpenAI
import os
import requests

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

這段程式碼定義了一個 function `fetch_customer_profile`，接收 `user_id` 並回傳一個模擬的使用者 profile。

這個 function 模擬從資料庫取得使用者資料的 API 呼叫。這個 demo 用的是寫死的資料。使用者 profile 包含許多細節，例如使用者的位置（這個範例設在金門大橋的座標）、飲食和活動的偏好、app 使用指標、近期互動和使用者等級。

在正式環境中，你會把這些寫死的資料換成對使用者資料庫的真實 API 呼叫。


```python
def fetch_customer_profile(user_id):
    # You can replace this with a real API call in the production code
    if user_id == "user1234":
        return {
            "name": "John Doe",
            "location": {
                "latitude": 37.7955,
                "longitude": -122.4026,
            },
            "preferences": {
                "food": ["Italian", "Sushi"],
                "activities": ["Hiking", "Reading"],
            },
            "behavioral_metrics": {
                "app_usage": {
                    "daily": 2,  # hours
                    "weekly": 14  # hours
                },
                "favourite_post_categories": ["Nature", "Food", "Books"],
                "active_time": "Evening",
            },
            "recent_searches": ["Italian restaurants nearby", "Book clubs"],
            "recent_interactions": ["Liked a post about 'Best Pizzas in New York'", "Commented on a post about 'Central Park Trails'"],
            "user_rank": "Gold",  # based on some internal ranking system
        }
    else:
        return None
```

## 向 Google Places API 請求並處理資料

function call_google_places_api 用來向 Google Places API 請求資訊，並根據給定的 place_type 和選用的 food_preference，回傳前兩個地點的清單。因為這是付費服務，我們把這個 function 限制在前兩筆結果以控制用量。你可以依需求修改，取得任意數量的結果。

這個 function 設定了寫死的位置（設在 Transamerica Pyramid 的座標）、你的 Google API key，以及特定的 request 參數。依照 place_type，它會組出適當的 API request URL。如果 place_type 是餐廳，而且指定了 food_preference，就會一起放進 API request。

送出 GET request 後，function 會檢查回應狀態。成功的話，就處理 JSON 回應，用 get_place_details function 取出相關細節，並以人類可讀的格式回傳。如果 request 失敗，就把錯誤印出來方便 debug。

get_place_details function 用來根據 place_id 取得某個地點更詳細的資訊。它會對 Google Place Details API 送 GET request，成功就回傳結果。如果 request 失敗，就把錯誤印出來方便 debug。

這兩個 function 都會處理例外，出問題時回傳錯誤訊息。 

```python
def get_place_details(place_id, api_key):
    URL = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&key={api_key}"
    response = requests.get(URL)
    if response.status_code == 200:
        result = json.loads(response.content)["result"]
        return result
    else:
        print(f"Google Place Details API request failed with status code {response.status_code}")
        print(f"Response content: {response.content}")
        return None
```

```python
def call_google_places_api(user_id, place_type, food_preference=None):
    try:
        # Fetch customer profile
        customer_profile = fetch_customer_profile(user_id)
        if customer_profile is None:
            return "I couldn't find your profile. Could you please verify your user ID?"

        # Get location from customer profile
        lat = customer_profile["location"]["latitude"]
        lng = customer_profile["location"]["longitude"]

        API_KEY = os.getenv('GOOGLE_PLACES_API_KEY')  # retrieve API key from environment variable
        LOCATION = f"{lat},{lng}"
        RADIUS = 500  # search within a radius of 500 meters
        TYPE = place_type

        # If the place_type is restaurant and food_preference is not None, include it in the API request
        if place_type == 'restaurant' and food_preference:
            URL = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={LOCATION}&radius={RADIUS}&type={TYPE}&keyword={food_preference}&key={API_KEY}"
        else:
            URL = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={LOCATION}&radius={RADIUS}&type={TYPE}&key={API_KEY}"

        response = requests.get(URL)
        if response.status_code == 200:
            results = json.loads(response.content)["results"]
            places = []
            for place in results[:2]:  # limit to top 2 results
                place_id = place.get("place_id")
                place_details = get_place_details(place_id, API_KEY)  # Get the details of the place

                place_name = place_details.get("name", "N/A")
                place_types = next((t for t in place_details.get("types", []) if t not in ["food", "point_of_interest"]), "N/A")  # Get the first type of the place, excluding "food" and "point_of_interest"
                place_rating = place_details.get("rating", "N/A")  # Get the rating of the place
                total_ratings = place_details.get("user_ratings_total", "N/A")  # Get the total number of ratings
                place_address = place_details.get("vicinity", "N/A")  # Get the vicinity of the place

                if ',' in place_address:  # If the address contains a comma
                    street_address = place_address.split(',')[0]  # Split by comma and keep only the first part
                else:
                    street_address = place_address

                # Prepare the output string for this place
                place_info = f"{place_name} is a {place_types} located at {street_address}. It has a rating of {place_rating} based on {total_ratings} user reviews."

                places.append(place_info)

            return places
        else:
            print(f"Google Places API request failed with status code {response.status_code}")
            print(f"Response content: {response.content}")  # print out the response content for debugging
            return []
    except Exception as e:
        print(f"Error during the Google Places API call: {e}")
        return []
```

## 用 GPT-3.5-Turbo 和 Google Places API 產生針對使用者的推薦

`provide_user_specific_recommendations` 這個 function 會跟 GPT-3.5-Turbo 和 Google Places API 互動，根據使用者的偏好和位置提供量身打造的回應。

首先，它用 `user_id` 取得客戶的 profile。找不到 profile 的話，就回傳錯誤訊息。

有了有效的 profile，它會取出客戶的飲食偏好，然後跟 OpenAI 模型互動。它先送出一則 system message，讓模型知道自己的角色、使用者偏好，以及怎麼使用 Google Places API function。

使用者的輸入也會當成 message 送給模型，而 `call_google_places_api` 這個 function 會定義在 `functions` 參數裡，讓模型視需要呼叫。

最後處理模型的回應。如果模型對 Google Places API 發出 function call，就用適當的參數執行該 function，並回傳附近地點的名稱。如果沒有這樣的地點，或是看不懂 request，就回傳對應的錯誤訊息。


```python
def provide_user_specific_recommendations(user_input, user_id):
    customer_profile = fetch_customer_profile(user_id)
    if customer_profile is None:
        return "I couldn't find your profile. Could you please verify your user ID?"

    customer_profile_str = json.dumps(customer_profile)

    food_preference = customer_profile.get('preferences', {}).get('food', [])[0] if customer_profile.get('preferences', {}).get('food') else None


    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
    {
        "role": "system",
        "content": f"You are a sophisticated AI assistant, a specialist in user intent detection and interpretation. Your task is to perceive and respond to the user's needs, even when they're expressed in an indirect or direct manner. You excel in recognizing subtle cues: for example, if a user states they are 'hungry', you should assume they are seeking nearby dining options such as a restaurant or a cafe. If they indicate feeling 'tired', 'weary', or mention a long journey, interpret this as a request for accommodation options like hotels or guest houses. However, remember to navigate the fine line of interpretation and assumption: if a user's intent is unclear or can be interpreted in multiple ways, do not hesitate to politely ask for additional clarification. Make sure to tailor your responses to the user based on their preferences and past experiences which can be found here {customer_profile_str}"
    },
    {"role": "user", "content": user_input}
],
        temperature=0,
        tools=[
            {
                "type": "function",
                "function" : {
                    "name": "call_google_places_api",
                    "description": "This function calls the Google Places API to find the top places of a specified type near a specific location. It can be used when a user expresses a need (e.g., feeling hungry or tired) or wants to find a certain type of place (e.g., restaurant or hotel).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "place_type": {
                                "type": "string",
                                "description": "The type of place to search for."
                            }
                        }
                    },
                    "result": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    }
                }
            }
        ],
    )

    print(response.choices[0].message.tool_calls)

    if response.choices[0].finish_reason=='tool_calls':
        function_call = response.choices[0].message.tool_calls[0].function
        if function_call.name == "call_google_places_api":
            place_type = json.loads(function_call.arguments)["place_type"]
            places = call_google_places_api(user_id, place_type, food_preference)
            if places:  # If the list of places is not empty
                return f"Here are some places you might be interested in: {' '.join(places)}"
            else:
                return "I couldn't find any places of interest nearby."

    return "I am sorry, but I could not understand your request."
```

## 執行針對使用者的推薦

執行時，function 會取得使用者 profile、跟 AI 模型互動、處理模型的回應，必要時呼叫 Google Places API，最後回傳符合使用者偏好和位置的推薦清單。印出的輸出就是這些個人化的推薦。


```python
user_id = "user1234"
user_input = "I'm hungry"
output = provide_user_specific_recommendations(user_input, user_id)
print(output)
```

??? note "輸出"

    ```text
    [ChatCompletionMessageToolCall(id='call_Q1mXIi7D6GhobfE4tkruX7nB', function=Function(arguments='{\n  "place_type": "restaurant"\n}', name='call_google_places_api'), type='function')]
    Here are some places you might be interested in: Sotto Mare is a restaurant located at 552 Green Street. It has a rating of 4.6 based on 3765 user reviews. Mona Lisa Restaurant is a restaurant located at 353 Columbus Avenue #3907. It has a rating of 4.4 based on 1888 user reviews.
    ```

## 重點整理

- function calling 讓模型自己決定要不要呼叫外部 API，以及帶什麼參數，你的程式負責真的去執行。
- 把使用者 profile 放進 system message，就能讓同一句話在不同使用者身上得到不同的推薦。
- 付費 API 要主動限制結果數量，這個範例只取前兩筆。
- 範例裡的 profile 和位置都是寫死的，正式環境要換成真實的資料庫與使用者定位。
- 外部 API 呼叫要處理例外和錯誤回應，不然模型拿到壞資料也無從判斷。

## 練習

1. 修改 `fetch_customer_profile` 裡的飲食偏好，換個菜系，看推薦結果怎麼跟著變。
2. 把 `call_google_places_api` 取前兩筆結果的限制改成前五筆，觀察輸出和用量的差別。
3. 新增一個 `place_type`（例如咖啡廳或書店）到 function 的定義裡，讓模型在使用者說出對應需求時也會呼叫它。
