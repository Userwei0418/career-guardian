# Please install OpenAI SDK first: `pip3 install openai`

import os
from openai import OpenAI

api_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com")
api_key = os.getenv("DEEPSEEK_API_KEY", "")
#当前使用的模型
model_name = "deepseek-chat"


def call_gpt(prompt) -> str: 
    #调用接口
    client = OpenAI(api_key=api_key, base_url=api_url)

    response = client.chat.completions.create(
        model= model_name,
        messages=[
            {"role": "user", "content": prompt},
        ],
        stream=False
    )

    print(response.choices[0].message.content)


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