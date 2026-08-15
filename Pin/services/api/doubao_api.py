# -*- coding: utf-8 -*-
# @Time    : 2025/2/17 16:39
# @Author  : chang
import os
import time
from volcenginesdkarkruntime import Ark
import sys
sys.path.append('../')

from utils import ner_logger 

api_key = os.getenv("DOUBAO_API_KEY", "")
model_id = os.getenv("DOUBAO_MODEL", "ep-20250613142735-f4xrw")
# model_id="ep-20250219151347-fspmw"
model_name = f"model:deepseek ,model_id:{model_id}"

def fix_return_json(_text): 
    _text = _text.replace("```json", "") 
    _text = _text.replace("```", "") 
    return _text
def call_gpt(prompt,isjson = False) -> str: 
    #提交请求
    try:
        ner_logger.info(f"doubao-deepseek old:\n {prompt}")
        #调用接口
        client = Ark(api_key=api_key)
        messages = [{"role": "system", "content":"你是根据用于分析招聘数据、提取结构化信息的AI机器人"}]
        messages.append({"role": "user", "content": prompt})
        completion = client.chat.completions.create(
            model= model_id,
            messages=messages,
            temperature=0,
            max_tokens= 12288,
            top_p=0.2,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )
        completion = completion.to_dict()
        content = completion["choices"][0].get("message").get("content")
        _value_str = fix_return_json(content) 
        return True ,_value_str
    except Exception  as e:
        import traceback
        traceback.print_exc()
        ner_logger.error(f"doubao error:{e}")

    return False,"大模型处理失败[openai][48]"

def call_gpt_system(prompt,isjson = False) -> str: 
  message_text = [{"role": "system", "content":"你是用于分析招聘数据、提取结构化信息的AI机器人，帮助用户分析请求的数据，返回符合要求的json格式的数据"}]
  message_text.append({"role": "user", "content": prompt})
  
  ner_logger.info(f"{model_name}:\n {prompt}")
  _value_str = ""
  try:
    client = Ark(api_key=api_key)
    completion = client.chat.completions.create(
        model=model_name,
        messages=message_text,
        response_format={"type": "json_object"} if isjson else None,
        temperature=0,
        max_tokens=12288,
        top_p=0.1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
        timeout=60*6
    ) 
    completion=completion.to_dict()
    choices=completion.get("choices")
    if choices:
        message=choices[0].get("message")
        if message:
            _value_str=message.get("content")
            ner_logger.info(f"{model_name} return :\n{_value_str}\n")
            _value_str = fix_return_json(_value_str) 
            return True,_value_str
  except Exception  as e:
    import traceback
    traceback.print_exc()
    ner_logger.error(f"openai error:{e}")

  return False,"大模型处理失败[openai][79]"

def getVers():
    return model_name