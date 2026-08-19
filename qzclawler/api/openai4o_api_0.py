# -*- coding: utf-8 -*-
# @Time    : 2023/12/18 13:36
# @Author  : chang
import os
import json
import openai #这个版本小于1.0.0 ，给我提示装 0.28 我装的0.28

# from utils import ner_logger

''''''
openai.api_type = "azure"
openai.api_base = "https://oa-qz1.openai.azure.com/"
openai.api_version = "2024-02-01"
openai.api_key = "8ecdeab33e774b31b13665c38e062b9e"
#当前使用的模型
model_name = "gpt-4o-mini"

def fix_return_json(_text): 
    y = _text.replace("```python", "")
    if y.strip().endswith("`"):
        y = y[:-2] 
    return y

def call_gpt(prompt) -> str: 
  #组建内容
  message_text = [{"role":"system","content":prompt}]
  #返回内容
  _value_str = ""
  #提交请求
  try:
    completion  = openai.ChatCompletion.create(
        engine=model_name, #"gpt-4o-mini",#dmx-35t,dmx-gpt4t,gpt-4o-mini gpt4o
        # response_format={"type": "json_object"},
        messages = message_text,
        temperature=0.7,
        max_tokens=4096,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None
      )

    #默认
    choices=completion.get("choices")
    if choices:
        message=choices[0].get("message")
        if message:
            _value_str=message.get("content")
  except Exception  as e:
    return True,str(e)

  print("openai :",prompt,"\n return :",_value_str)
  #_value_str = response['choices'][0]['message']['content']
  #判断是否有错误 
  _value_str = fix_return_json(_value_str) 
    #ner_logger.debug("百度返回 result:【%s】  \n 【%s】",_value_str,_fix_str)
  return True,_value_str

  # return True,"大模型处理失败[openai]"

# DEMO_STR = ''''''


# def call_gpt_demo(prompt):
#     return False,DEMO_STR

#版本模型
def getVers():
    return model_name

if __name__ == '__main__':
    print(call_gpt("hello world"))