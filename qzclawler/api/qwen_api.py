# Please install OpenAI SDK first: `pip3 install openai`

from openai import OpenAI

api_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "sk-2696cb11c415473d955cea4ee68b1900"
#当前使用的模型
model_name = "qwen-plus"


def call_gpt(prompt,isjson = True) -> str: 
    #提交请求
    try:
        #调用接口
        client = OpenAI(api_key=api_key, base_url=api_url)

        #组建内容
        message_text = [{"role":"system","content":prompt}]
        #返回内容
        _value_str = ""

        response = client.chat.completions.create(
            model= model_name,
            messages = message_text,
            stream=False
        )
        #默认
        choices=response.choices
        if choices:
            message=choices[0].message
            if message:
                _value_str= message.content
        # print(response.choices[0].message.content)
        
        return True,_value_str
    except Exception  as e:
        #输出错误信息
        import traceback
        traceback.print_exc()
        ner_logger.error(f"qwen error:{e}")
        send_email(f"qwen error:{e}<br>{prompt}")
        # return False,str(e)

    return False,"大模型处理失败[qwen][48]"



#获取模型的列表
def getModels():
    client = OpenAI(api_key=api_key, base_url=api_url)
    models = client.models.list()
    for model in models.data:
        print(model.id)

#版本模型
def getVers():
    return model_name


if __name__ == "__main__":
    print(getModels())