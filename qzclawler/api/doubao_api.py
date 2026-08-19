# -*- coding: utf-8 -*-
# @Time    : 2025/2/17 16:39
# @Author  : chang
import time
from volcenginesdkarkruntime import Ark
import sys
sys.path.append('../')

from utils import ner_logger 
from utils_log import send_email

api_key="99458ecf-4a8e-4e2a-ad96-246caf5fd213"
model_id="ep-20250613142735-f4xrw"
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
        # print(completion.get("usage"))
        content = completion["choices"][0].get("message").get("content")
        _value_str = fix_return_json(content) 
        return True ,_value_str
    except Exception  as e:
        #输出错误信息
        import traceback
        traceback.print_exc()
        ner_logger.error(f"doubao error:{e}")
        send_email(f"doubao error:{e}<br>{prompt}")
        # return False,str(e)

    return False,"大模型处理失败[openai][48]"

def call_gpt_system(prompt,isjson = False) -> str: 
  #组建内容
#   message_text = [{"role":"system","content":prompt}]
  message_text = [{"role": "system", "content":"你是用于分析招聘数据、提取结构化信息的AI机器人，帮助用户分析请求的数据，返回符合要求的json格式的数据"}]
  message_text.append({"role": "user", "content": prompt})
  
  ner_logger.info(f"{model_name}:\n {prompt}")
  #返回内容
  _value_str = ""
  #提交请求
  try:
    client = Ark(api_key=api_key)
    completion = client.chat.completions.create(
        model=model_name,  # dmx-35t  dmx-gpt4t gpt4o
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
    # print("openai :",prompt,"\n return :",completion)
    #默认
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
    #输出错误信息
    import traceback
    traceback.print_exc()
    ner_logger.error(f"openai error:{e}")
    # return False,str(e)

  return False,"大模型处理失败[openai][79]"

#版本模型
def getVers():
    return model_name


demo_str = '''
# 指令
我将提供一段公司官网“职位信息”的内容，你需要从中提取以下信息，并输出为JSON格式:
1.职位名/岗位名称(JobTitle)  
2.发布日期/开始日期(PublishTime)
3.到期日期/截止日期/结束日期(CutDate)
4.学历(Degree)：可能是多个，不重复，是个数组，可选择：“大专”，“大专及以上”、“本科”、“本科及以上”、“硕士”、“硕士/MBA”、“研究生”、“硕士及以上”、“研究生及以上”、“博士”
5.年龄要求(Age)：对候选人的岁数要求如：“18-25岁”、“40岁及以上”等
6.职位薪资(Salary)：职位的薪资情况，如：“面议”、“6k-8k”、“8k-10k”等
7.招聘人数(JobNum)：职位招聘的具体人数，如：“1人”等
8.工作年限(WorkYears)：工作经历具体年限要求，如：“1年及以上”、“5-8年”、“10年以下”等，如果是中文数字如一二三等转换成阿拉伯数字，只要年限取大的即可，无经验为空
9.专业要求(MajorRequirement)
10.工作地点(WorkPlace)：岗位所在城市、工作地区、公司所在地、工作地点、职场坐标、国外国家及地区，可能是多个，用逗号分隔，不要输出数组
11.详细地址(Address)
12.工作类型(HopeWorkType)：可选择：全职/兼职/实习等，注意职位要求的经验不能当工作类型
13.所属部门/工作部门/公司(JobDept)
14.职位描述/职位职责/工作职责/岗位职责(JobDescribe),保留原文中的换行符号,(职位描述/职位职责/工作职责/岗位职责)都为JobDescribe
15.职位要求/工作要求/任职要求/任职资格(Jobreq),保留原文中的换行符号，(职位要求/工作要求/任职要求/任职资格)都为Jobreq
16.暑期实习(SummerInternship)：可选择：有/无
17.转正机会(RegularEmployee) ： 可选择：有/无
18.职业类别(JobCategory)： 职位为的分类，如 职能 、技术、运营、市场、人事、财务、行政、客服、销售、市场、人事、财务、行政、客服、销售、市场等
19.技能标签(Skills)：提取最多5个关键词，如：python、java、大数据等
20.行业要求(IndustryRequirement)
21.语言要求(LanguageRequirement)
21.证书要求(CertificateRequirement)
22.工作时间(WorkTime)
23.工资结算方式(SalaryPayment)
24.院校要求(SchoolRequirement)

#Rules：
1. 职位信息中没有提及的信息，输出空即可；
2. 完全按照原文输出，不需要加工。
3. 你所需要的全部内容都在[webpage X begin]...[webpage X end]中，不能虚构内容。
4. 如果存在多职位，那么只返回第一个职位信息即可
5. 今天是2025-04-29

[webpage X begin] 

SSC实习生8013广州市-天河区2025-04-22发布大专无经验招聘1人工作职责1、员工档案归档：负责人事档案扫描和录入工作，按要求完成档案扫描及装订归档，并录入系统；协助归档离职员工资料，并按要求打包存库；
2、入职手续办理：协助办理员工入职手续的系统录入；
3、系统信息整理：协助日常人事档案材料收集、建立，完善HRIS系统人事信息；
4、团队协作：其他临时性事项处理、支持。任职要求1、学历：大专以上学历，档案管理、中文、人力资源、文秘或相关专业
2、相关工作经验优先

[webpage X end]
'''

if __name__ == '__main__': 
    ask = call_gpt(demo_str)
    print(ask)
 