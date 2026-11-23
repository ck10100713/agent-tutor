---
translated: true
source: examples/Creating_slides_with_Assistants_API_and_DALL-E3.ipynb
---
# 用 Assistants API 和 DALL·E 3 做投影片

> 原文：[examples/Creating_slides_with_Assistants_API_and_DALL-E3.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Creating_slides_with_Assistants_API_and_DALL-E3.ipynb)



## 這篇在做什麼

用 Assistants API 的 Code Interpreter 讀財務 CSV、算利潤並畫圖，再讓 Assistant 針對圖產出重點和標題，用 DALL·E-3 生成封面圖，最後用 `python-pptx` 模板把所有內容組成一份 pptx 簡報。全程不用打開 PowerPoint 或 Google Slides。

## 學完你會

- 上傳檔案並建立帶 Code Interpreter 的 Assistant，讓它自己寫程式算數據、畫圖
- 在同一個 thread 追加 message，讓 Assistant 根據前面的圖產生重點和標題
- 把圖片、標題、重點餵給 Assistant，並用 `python-pptx` 模板產出 pptx 檔

## 開跑前

需要 OpenAI API key（呼叫 GPT-4、DALL·E-3 和 Code Interpreter 都會計費）。


這份 notebook 示範怎麼用新的 [Assistants API](https://platform.openai.com/docs/assistants/overview)（GPT-4）和 DALL·E-3，做出資訊豐富又好看的投影片。<br>
做投影片是很多工作的重要環節，但很費工又花時間。另外，從資料中找出洞見並在投影片上有效表達，也不容易。<br><br> 這份 cookbook 會示範怎麼用新的 Assistants API 協助你完成整個投影片製作流程，不用碰 Microsoft PowerPoint 或 Google Slides，省下寶貴的時間和精力！

## 0. 環境設定

```python
from IPython.display import display, Image
from openai import OpenAI
import os
import pandas as pd
import json
import io
from PIL import Image
import requests

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

#Lets import some helper functions for assistants from https://cookbook.openai.com/examples/assistants_api_overview_python
def show_json(obj):
    display(json.loads(obj.model_dump_json()))

def submit_message(assistant_id, thread, user_message,file_ids=None):
    params = {
        'thread_id': thread.id,
        'role': 'user',
        'content': user_message,
    }
    if file_ids:
        params['file_ids']=file_ids

    client.beta.threads.messages.create(
        **params
)
    return client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant_id,
)

def get_response(thread):
    return client.beta.threads.messages.list(thread_id=thread.id)
```

## 1. 建立內容

這份範例要為我們公司 NotReal Corporation 的季度財務檢討，做一份虛構的簡短簡報。我們想強調一些正在影響公司獲利的關鍵趨勢。<br> 假設手上有一些財務資料。來載入資料看看⋯⋯

```python
financial_data_path = 'data/NotRealCorp_financial_data.json'
financial_data = pd.read_json(financial_data_path)
financial_data.head(5)
```

??? note "輸出"

    ```text
       Year Quarter Distribution channel  Revenue ($M)  Costs ($M)  \
    0  2021      Q1         Online Sales          1.50    1.301953   
    1  2021      Q1         Direct Sales          1.50    1.380809   
    2  2021      Q1      Retail Partners          1.50    1.348246   
    3  2021      Q2         Online Sales          1.52    1.308608   
    4  2021      Q2         Direct Sales          1.52    1.413305   

       Customer count     Time  
    0             150  2021 Q1  
    1             151  2021 Q1  
    2             152  2021 Q1  
    3             152  2021 Q2  
    4             153  2021 Q2
    ```

可以看到這份資料有跨不同通路的季度營收、成本和客戶資料。來建立一個能當個人分析師的 Assistant，幫我們的 PowerPoint 做出漂亮的視覺化圖表！

首先要上傳檔案，讓 Assistant 能存取。

```python
file = client.files.create(
  file=open('data/NotRealCorp_financial_data.json',"rb"),
  purpose='assistants',
)
```

現在可以建立 Assistant 了。我們可以指示 assistant 扮演資料科學家，接受我們給的任何查詢，並執行必要的程式碼，輸出正確的資料視覺化。這裡的 instructions 參數類似 Chat Completions API 的 system instructions，可以引導 assistant。我們也可以開啟 Code Interpreter 這個 tool，讓 Assistant 能寫程式。最後，可以指定要用的檔案，這裡就是前面建立的 `financial_data` 檔。

```python
assistant = client.beta.assistants.create(
  instructions="You are a data scientist assistant. When given data and a query, write the proper code and create the proper visualization",
  model="gpt-4-1106-preview",
  tools=[{"type": "code_interpreter"}],
  file_ids=[file.id]
)
```

現在建立一個 thread，第一個請求是請 Assistant 計算季度利潤，然後畫出各通路利潤隨時間變化的圖。assistant 會自動計算每季的利潤，也會自己建立一個合併季度和年份的新欄位，不用我們直接要求。我們也可以指定每條線的顏色。

```python
thread = client.beta.threads.create(
  messages=[
    {
      "role": "user",
      "content": "Calculate profit (revenue minus cost) by quarter and year, and visualize as a line plot across the distribution channels, where the colors of the lines are green, light red, and light blue",
      "file_ids": [file.id]
    }
  ]
)
```

現在可以執行 thread 的 run

```python

run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant.id,
)
```

接著可以開始一個迴圈，檢查圖片是不是已經產生了。注意：這可能要幾分鐘

```python
messages = client.beta.threads.messages.list(thread_id=thread.id)
```

```python
import time

while True:
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    try:
        #See if image has been created
        messages.data[0].content[0].image_file
        #Sleep to make sure run has completed
        time.sleep(5)
        print('Plot created!')
        break
    except:
        time.sleep(10)
        print('Assistant still working...')
```

??? note "輸出"

    ```text
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Assistant still working...
    Plot created!
    ```

來看看 Assistant 加了哪些 messages。

```python
messages = client.beta.threads.messages.list(thread_id=thread.id)
[message.content[0] for message in messages.data]
```

??? note "輸出"

    ```text
    [MessageContentImageFile(image_file=ImageFile(file_id='file-0rKABLygI02MgwwhpgWdRFY1'), type='image_file'),
     MessageContentText(text=Text(annotations=[], value="The profit has been calculated for each distribution channel by quarter and year. Next, I'll create a line plot to visualize these profits. As specified, I will use green for the 'Online Sales', light red for 'Direct Sales', and light blue for 'Retail Partners' channels. Let's create the plot."), type='text'),
     MessageContentText(text=Text(annotations=[], value="The JSON data has been successfully restructured into a tabular dataframe format. It includes the year, quarter, distribution channel, revenue, costs, customer count, and a combined 'Time' representation of 'Year Quarter'. Now, we have the necessary information to calculate the profit (revenue minus cost) by quarter and year.\n\nTo visualize the profit across the different distribution channels with a line plot, we will proceed with the following steps:\n\n1. Calculate the profit for each row in the dataframe.\n2. Group the data by 'Time' (which is a combination of Year and Quarter) and 'Distribution channel'.\n3. Aggregate the profit for each group.\n4. Plot the aggregated profits as a line plot with the distribution channels represented in different colors as requested.\n\nLet's calculate the profit for each row and then continue with the visualization."), type='text'),
     MessageContentText(text=Text(annotations=[], value='The structure of the JSON data shows that it is a dictionary with "Year", "Quarter", "Distribution channel", and potentially other keys that map to dictionaries containing the data. The keys of the inner dictionaries are indices, indicating that the data is tabular but has been converted into a JSON object.\n\nTo properly convert this data into a DataFrame, I will restructure the JSON data into a more typical list of dictionaries, where each dictionary represents a row in our target DataFrame. Subsequent to this restructuring, I can then load the data into a Pandas DataFrame. Let\'s restructure and load the data.'), type='text'),
     MessageContentText(text=Text(annotations=[], value="The JSON data has been incorrectly loaded into a single-row DataFrame with numerous columns representing each data point. This implies the JSON structure is not as straightforward as expected, and a direct conversion to a flat table is not possible without further processing.\n\nTo better understand the JSON structure and figure out how to properly normalize it into a table format, I will print out the raw JSON data structure. We will analyze its format and then determine the correct approach to extract the profit by quarter and year, as well as the distribution channel information. Let's take a look at the JSON structure."), type='text'),
     MessageContentText(text=Text(annotations=[], value="It seems that the file content was successfully parsed as JSON, and thus, there was no exception raised. The variable `error_message` is not defined because the `except` block was not executed.\n\nI'll proceed with displaying the data that was parsed from JSON."), type='text'),
     MessageContentText(text=Text(annotations=[], value="It appears that the content of the dataframe has been incorrectly parsed, resulting in an empty dataframe with a very long column name that seems to contain JSON data rather than typical CSV columns and rows.\n\nTo address this issue, I will take a different approach to reading the file. I will attempt to parse the content as JSON. If this is not successful, I'll adjust the loading strategy accordingly. Let's try to read the contents as JSON data first."), type='text'),
     MessageContentText(text=Text(annotations=[], value="Before we can calculate profits and visualize the data as requested, I need to first examine the contents of the file that you have uploaded. Let's go ahead and read the file to understand its structure and the kind of data it contains. Once I have a clearer picture of the dataset, we can proceed with the profit calculations. I'll begin by loading the file into a dataframe and displaying the first few entries to see the data schema."), type='text'),
     MessageContentText(text=Text(annotations=[], value='Calculate profit (revenue minus cost) by quarter and year, and visualize as a line plot across the distribution channels, where the colors of the lines are green, light red, and light blue'), type='text')]
    ```

可以看到 assistant 的最後一則 message（最新的會排在最前面）包含我們要找的圖片檔。有個有趣的地方：Assistant 試了好幾次解析 JSON 資料，因為第一次解析失敗了，這顯示出 assistant 的應變能力。

```python
# Quick helper function to convert our output file to a png
def convert_file_to_png(file_id, write_path):
    data = client.files.content(file_id)
    data_bytes = data.read()
    with open(write_path, "wb") as file:
        file.write(data_bytes)
```

```python
plot_file_id = messages.data[0].content[0].image_file.file_id
image_path = "../images/NotRealCorp_chart.png"
convert_file_to_png(plot_file_id,image_path)

#Upload
plot_file = client.files.create(
  file=open(image_path, "rb"),
  purpose='assistants'
)
```

來載入圖表吧！

![The Image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/NotRealCorp_chart.png)

很棒！只用一句話，我們就讓 assistant 用 code interpreter 計算獲利，並畫出三個通路的折線圖。<br><br>
現在投影片有漂亮的視覺圖了，但我們還想要搭配一些洞見。

## 2. 產生洞見

要從圖片取得洞見，只需要在 thread 加一則新的 message。我們的 Assistant 會知道用訊息歷史，針對提供的視覺圖給出簡潔的重點。

```python
submit_message(assistant.id,thread,"Give me two medium length sentences (~20-30 words per sentence) of the \
      most important insights from the plot you just created.\
             These will be used for a slide deck, and they should be about the\
                     'so what' behind the data."
)
```

??? note "輸出"

    ```text
    Run(id='run_NWoygMcBfHUr58fCE4Cn6rxN', assistant_id='asst_3T362kLlTyAq0FUnkvjjQczO', cancelled_at=None, completed_at=None, created_at=1701827074, expires_at=1701827674, failed_at=None, file_ids=['file-piTokyHGllwGITzIpoG8dok3'], instructions='You are a data scientist assistant. When given data and a query, write the proper code and create the proper visualization', last_error=None, metadata={}, model='gpt-4-1106-preview', object='thread.run', required_action=None, started_at=None, status='queued', thread_id='thread_73TgtFoJMlEJvb13ngjTnAo3', tools=[ToolAssistantToolsCode(type='code_interpreter')])
    ```

等 run 完成後，就能看到最新的 message

```python
# Hard coded wait for a response, as the assistant may iterate on the bullets.
time.sleep(10)
response = get_response(thread)
bullet_points = response.data[0].content[0].text.value
print(bullet_points)
```

??? note "輸出"

    ```text
    The plot reveals a consistent upward trend in profits for all distribution channels, indicating successful business growth over time. Particularly, 'Online Sales' shows a notable increase, underscoring the importance of digital presence in revenue generation.
    ```

很酷！我們的 assistant 看出 Online Sales 利潤明顯成長，並推論這代表擁有大型數位通路的重要性。接下來幫投影片想一個吸引人的標題。

```python
submit_message(assistant.id,thread,"Given the plot and bullet points you created,\
 come up with a very brief title for a slide. It should reflect just the main insights you came up with."
)
```

??? note "輸出"

    ```text
    Run(id='run_q6E85J31jCw3QkHpjJKl969P', assistant_id='asst_3T362kLlTyAq0FUnkvjjQczO', cancelled_at=None, completed_at=None, created_at=1701827084, expires_at=1701827684, failed_at=None, file_ids=['file-piTokyHGllwGITzIpoG8dok3'], instructions='You are a data scientist assistant. When given data and a query, write the proper code and create the proper visualization', last_error=None, metadata={}, model='gpt-4-1106-preview', object='thread.run', required_action=None, started_at=None, status='queued', thread_id='thread_73TgtFoJMlEJvb13ngjTnAo3', tools=[ToolAssistantToolsCode(type='code_interpreter')])
    ```

標題是：

```python
#Wait as assistant may take a few steps
time.sleep(10)
response = get_response(thread)
title = response.data[0].content[0].text.value
print(title)
```

??? note "輸出"

    ```text
    "Ascending Profits & Digital Dominance"
    ```

## 3. DALL·E-3 標題圖

很好，現在有標題、圖表和兩個重點了。快可以把這些放上投影片了，不過最後一步，讓 DALL·E-3 想一張圖，當作簡報的標題頁圖片。<br><br>
*注意：* DALL·E-3 還不能在 assistants API 裡使用，但即將推出！<br> <br>
我們會給它一段公司（NotRealCorp）的簡短描述，剩下的交給 DALL·E-3！

```python
company_summary = "NotReal Corp is a prominent hardware company that manufactures and sells processors, graphics cards and other essential computer hardware."
```

```python
response = client.images.generate(
  model='dall-e-3',
  prompt=f"given this company summary {company_summary}, create an inspirational \
    photo showing the growth and path forward. This will be used at a quarterly\
       financial planning meeting",
       size="1024x1024",
       quality="hd",
       n=1
)
image_url = response.data[0].url
```

很好，現在可以把這張圖加進 thread。首先，把圖存到本機，再用 `File` 上傳 endpoint 上傳到 assistants API。順便看一下我們的圖

```python
dalle_img_path = '../images/dalle_image.png'
img = requests.get(image_url)

#Save locally
with open(dalle_img_path,'wb') as file:
  file.write(img.content)

#Upload
dalle_file = client.files.create(
  file=open(dalle_img_path, "rb"),
  purpose='assistants'
)
```

  
![Image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/dalle_image.png)

## 4. 製作投影片

現在我們有製作投影片需要的所有內容了。可以直接加一則 message 要求做投影片，但我們改成給 assistant 一個搭配 `python-pptx` library 使用的投影片模板，這樣能確保做出的簡報是我們要的風格。建立模板的說明請看 notebook 最後的 `Extensions` 一節。

```python
title_template = """
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_PARAGRAPH_ALIGNMENT
from pptx.dml.color import RGBColor

# Create a new presentation object
prs = Presentation()

# Add a blank slide layout
blank_slide_layout = prs.slide_layouts[6]
slide = prs.slides.add_slide(blank_slide_layout)

# Set the background color of the slide to black
background = slide.background
fill = background.fill
fill.solid()
fill.fore_color.rgb = RGBColor(0, 0, 0)

# Add image to the left side of the slide with a margin at the top and bottom
left = Inches(0)
top = Inches(0)
height = prs.slide_height
width = prs.slide_width * 3/5
pic = slide.shapes.add_picture(image_path, left, top, width=width, height=height)

# Add title text box positioned higher
left = prs.slide_width * 3/5
top = Inches(2)
width = prs.slide_width * 2/5
height = Inches(1)
title_box = slide.shapes.add_textbox(left, top, width, height)
title_frame = title_box.text_frame
title_p = title_frame.add_paragraph()
title_p.text = title_text
title_p.font.bold = True
title_p.font.size = Pt(38)
title_p.font.color.rgb = RGBColor(255, 255, 255)
title_p.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER

# Add subtitle text box
left = prs.slide_width * 3/5
top = Inches(3)
width = prs.slide_width * 2/5
height = Inches(1)
subtitle_box = slide.shapes.add_textbox(left, top, width, height)
subtitle_frame = subtitle_box.text_frame
subtitle_p = subtitle_frame.add_paragraph()
subtitle_p.text = subtitle_text
subtitle_p.font.size = Pt(22)
subtitle_p.font.color.rgb = RGBColor(255, 255, 255)
subtitle_p.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER
"""

data_vis_template = """
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_PARAGRAPH_ALIGNMENT
from pptx.dml.color import RGBColor

# Create a new presentation object
prs = Presentation()

# Add a blank slide layout
blank_slide_layout = prs.slide_layouts[6]
slide = prs.slides.add_slide(blank_slide_layout)

# Set the background color of the slide to black
background = slide.background
fill = background.fill
fill.solid()
fill.fore_color.rgb = RGBColor(0, 0, 0)

# Define placeholders
image_path = data_vis_img
title_text = "Maximizing Profits: The Dominance of Online Sales & Direct Sales Optimization"
bullet_points = "• Online Sales consistently lead in profitability across quarters, indicating a strong digital market presence.\n• Direct Sales show fluctuations, suggesting variable performance and the need for targeted improvements in that channel."

# Add image placeholder on the left side of the slide
left = Inches(0.2)
top = Inches(1.8)
height = prs.slide_height - Inches(3)
width = prs.slide_width * 3/5
pic = slide.shapes.add_picture(image_path, left, top, width=width, height=height)

# Add title text spanning the whole width
left = Inches(0)
top = Inches(0)
width = prs.slide_width
height = Inches(1)
title_box = slide.shapes.add_textbox(left, top, width, height)
title_frame = title_box.text_frame
title_frame.margin_top = Inches(0.1)
title_p = title_frame.add_paragraph()
title_p.text = title_text
title_p.font.bold = True
title_p.font.size = Pt(28)
title_p.font.color.rgb = RGBColor(255, 255, 255)
title_p.alignment = PP_PARAGRAPH_ALIGNMENT.CENTER

# Add hardcoded "Key Insights" text and bullet points
left = prs.slide_width * 2/3
top = Inches(1.5)
width = prs.slide_width * 1/3
height = Inches(4.5)
insights_box = slide.shapes.add_textbox(left, top, width, height)
insights_frame = insights_box.text_frame
insights_p = insights_frame.add_paragraph()
insights_p.text = "Key Insights:"
insights_p.font.bold = True
insights_p.font.size = Pt(24)
insights_p.font.color.rgb = RGBColor(0, 128, 100)
insights_p.alignment = PP_PARAGRAPH_ALIGNMENT.LEFT
insights_frame.add_paragraph()


bullet_p = insights_frame.add_paragraph()
bullet_p.text = bullet_points
bullet_p.font.size = Pt(12)
bullet_p.font.color.rgb = RGBColor(255, 255, 255)
bullet_p.line_spacing = 1.5
"""
```

設定幾個投影片用的變數。我們要在標題頁放公司名稱 NotRealCorp，簡報標題是 'Quarterly financial planning meeting, Q3, 2023'。

```python
title_text = "NotRealCorp"
subtitle_text = "Quarterly financial planning meeting, Q3 2023"
```

資料頁的部分，我們有：

這裡有一個建立標題頁的模板。下面的模板是把一張理想標題頁的圖片上傳給 GPT-V，請它產生建立該模板的 `python-pptx` 程式碼而來。模板的輸入是 image_path、title_text 和 subtitle_text。

```python
submit_message(assistant.id,thread,f"Use the included code template to create a PPTX slide that follows the template format, but uses the image, company name/title, and document name/subtitle included:\
{title_template}. IMPORTANT: Use the image file included in this message as the image_path image in this first slide, and use the Company Name {title_text} as the title_text variable, and \
  use the subtitle_text {subtitle_text} a the subtitle_text variable. \
    NEST, create a SECOND slide using the following code template: {data_vis_template} to create a PPTX slide that follows the template format, but uses the company name/title, and document name/subtitle included:\
{data_vis_template}. IMPORTANT: Use the line plot image, that is the second attached image in this message, that you created earlier in the thread as the data_vis_img image, and use the data visualization title that you created earlier for the variable title_text, and\
  the bullet points of insights you created earlier for the bullet_points variable. Output these TWO SLIDES as a .pptx file. Make sure the output is two slides, with each slide matching the respective template given in this message.",
              file_ids=[dalle_file.id, plot_file.id]
)
```

??? note "輸出"

    ```text
    Run(id='run_taLrnOnlDhoywgQFFBOLPlg0', assistant_id='asst_3T362kLlTyAq0FUnkvjjQczO', cancelled_at=None, completed_at=None, created_at=1701827118, expires_at=1701827718, failed_at=None, file_ids=['file-piTokyHGllwGITzIpoG8dok3'], instructions='You are a data scientist assistant. When given data and a query, write the proper code and create the proper visualization', last_error=None, metadata={}, model='gpt-4-1106-preview', object='thread.run', required_action=None, started_at=None, status='queued', thread_id='thread_73TgtFoJMlEJvb13ngjTnAo3', tools=[ToolAssistantToolsCode(type='code_interpreter')])
    ```

```python
#May take 1-3 mins
while True:
    try:
        response = get_response(thread)
        pptx_id = response.data[0].content[0].text.annotations[0].file_path.file_id
        print("Successfully retrieved pptx_id:", pptx_id)
        break
    except Exception as e:
        print("Assistant still working on PPTX...")
        time.sleep(10)
```

??? note "輸出"

    ```text
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Assistant still working on PPTX...
    Successfully retrieved pptx_id: file-oa0i63qPH4IaJXYj90aA6L4Q
    ```

```python
pptx_id = response.data[0].content[0].text.annotations[0].file_path.file_id
ppt_file= client.files.content(pptx_id)
file_obj = io.BytesIO(ppt_file.read())
with open("data/created_slides.pptx", "wb") as f:
    f.write(file_obj.getbuffer())
```

現在，我們有一個存好所有生成內容的 PPTX 檔了！<br>

來看看剛剛只用 assistants API 和 DALL·E-3 做出的 .pptx 截圖。Assistants API 目前還沒有 `seed` 參數，所以因為 LLM 的非確定性，DALL·E-3 的圖片和文字會跟你執行這份 notebook 看到的略有不同，不過輸出的大方向應該一樣。

標題頁：

![Title Slide](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/title_slide.png)

資料頁：

![Data Slide](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/data_vis_slide.png)

## 5. 結論

太棒了！雖然這些投影片還需要調整一下格式，但我們用 Assistants API、GPT-4 和 DALL·E-3 做出了很棒的內容。我們拿一份含財務資料的 `.csv` 檔，用 assistant 計算各通路每季的利潤，把結果畫成圖，從視覺圖找出洞見和重點，並產生摘要標題。而且只給公司 NotRealCorp 的描述，就用 DALL·E-3 做出很棒的標題圖。<br><br>
雖然要完全自動化這個流程、不需要人類介入，還有一段距離，但希望這份 notebook 能讓你做投影片稍微輕鬆一點。更重要的是，希望它能讓你一窺 assistants API 的潛力。我們很期待看到你做出什麼！

## 6. 延伸方向

- 當 DALL·E-3 整合進 Assistants API 之後，就能直接在 thread 裡要求生成標題圖。
- Assistants API 目前還不支援 GPT-4-Vision，但它本來可以用來從折線圖圖片取得洞見。
- 這份範例裡的 `python-pptx` 模板是用 GPT-4-Vision 產生的，所以一個可能的延伸專案，是示範把圖片轉成投影片模板的最佳做法。

## 重點整理

- Code Interpreter 讓 Assistant 能自己寫程式讀檔、計算和畫圖，你只要用自然語言下指令。
- 同一個 thread 會保留訊息歷史，後續的洞見和標題可以直接追加 message 取得，不用重傳圖。
- instructions 參數的作用類似 system instructions，用來決定 Assistant 的角色。
- 先給模板再要求生成，比直接叫它做投影片更能控制成品風格。
- LLM 輸出不是確定的，每次跑的圖和文字會略有不同，流程仍需要人工檢查。

## 練習

1. 把畫圖請求裡指定的線條顏色改掉，或改成要求長條圖，重跑確認 Assistant 產生的圖有跟著變。
2. 在 thread 多追加一則 message，請 Assistant 針對圖產生三個重點而不是兩個，並調整標題的要求長度。
3. 修改 `python-pptx` 模板的變數（標題文字、公司名稱），再試著新增第三頁投影片，放另一組你自己的資料圖。
