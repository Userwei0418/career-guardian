# -*- coding: utf-8 -*-
# @Time    : 2023/12/18 13:36
# @Author  : chang
import os
import json
from openai import AzureOpenAI
import sys
sys.path.append('../')

from utils import ner_logger 

# api_version = "2024-02-01"
# api_key = "8ecdeab33e774b31b13665c38e062b9e"
# azure_endpoint = "https://oa-qz1.openai.azure.com/"

api_version = os.getenv("OPENAI_AZURE_API_VERSION", "2024-02-01")
azure_endpoint = os.getenv("OPENAI_AZURE_ENDPOINT", "https://quanzhidmx.openai.azure.com/")
api_key = os.getenv("OPENAI_AZURE_API_KEY", "")

# api_version = "2024-02-01"
# azure_endpoint= "https://dmxpr-m4b118qk-swedencentral.cognitiveservices.azure.com/"
# api_key = "5h0tMOtAtX30KZyb2IIDX8yTmTm3ZU44qSSRnEVsuC3cVSe5OLz8JQQJ99ALACfhMk5XJ3w3AAAAACOGtjWi"

#当前使用的模型
model_name = "gpt4omini"
model_max_tokens = 4096 * 4
def fix_return_json(_text): 
    y = _text.replace("```python", "")
    if y.strip().endswith("`"):
        y = y[:-2] 
    return y

def call_gpt(prompt,isjson = False) -> str: 
  #组建内容
  message_text = [{"role":"system","content":prompt}]
  #
  ner_logger.info(f"{model_name}:\n {prompt}")
  #返回内容
  _value_str = ""
  #提交请求
  try:
    client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
    )

    completion = client.chat.completions.create(
        model=model_name,  # dmx-35t  dmx-gpt4t gpt4o
        messages=message_text,
        response_format={"type": "json_object"} if isjson else None,
        temperature=0,
        max_tokens=model_max_tokens,
        top_p=0.2,
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
    client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            api_version=api_version
    )

    completion = client.chat.completions.create(
        model=model_name,  # dmx-35t  dmx-gpt4t gpt4o
        messages=message_text,
        response_format={"type": "json_object"} if isjson else None,
        temperature=0,
        max_tokens=model_max_tokens,
        top_p=0.2,
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

DEMO_STR = '''
我将提供一段公司“招聘公告”的内容，你需要从中提取以下信息，并输出为JSON格式：
1. 公司名称(ComName)：包含公司、学校、企业、机构等名称，不要特殊字符
2. 公司所在地区(ComPlace)：从公告标题、公司名称里能提的所在的地区，比如：“上海”、”北京”、”深圳”等，可能是多个，用逗号分隔
3. 公司简介(ComDesc)
4. 公司行业(ComIndustry)
5. 报名开始时间或网申开始时间(OnlineStartDate)，格式为yyyy-mm-dd，如果公告中没有则为“”，不是毕业时间、入职时间，如果没有年，则根据当前时间计算
6. 报名截止时间/网申截止时间(OnlineEndDate)，格式为yyyy-mm-dd，如果公告中没有则为“”，不是毕业时间、入职时间，如果没有年，则根据当前时间计算
7. 招聘岗位的名称(JobName)：如“产品经理”、“Java开发工程师”、“技术岗”等，可能是多个，用逗号分隔
8. 工作城市/工作地区/公司地区(WorkPlace)：岗位所在城市、工作地区、公司所在地、职场坐标，可能是多个，用逗号分隔，要具体城市、地区、国外国家及地区，不要多所、全部这种词语
9. 工作类型(HopeWorkType)：有如下类型 全职、实习、兼职
10. 学历要求(Degree)：可能是多个，不重复，是个数组，可选择：“大专”，“大专及以上”、“本科”、“本科及以上”、“硕士/MBA”、“硕士及以上”、“博士”
11. 专业要求(MajorRequirement)：可能是多个，用逗号分隔的文本
12. 招聘对象及毕业时间要求(GraduationTimeRequirement)：提取对应聘者毕业时间要求的一段文本，需要有具体的毕业区间或第几届毕业生，如果没有则为“”
13. 报名链接(ApplyTypeLink)：报名入口或网申通道，是一个http链接地址，不要虚拟增加链接
14. 报名或投递渠道(ApplyTypeText)：公告中会用一段文字说明如何投递，如网址、邮箱、二维码等，请完整地输出这段文字；如有换行，用<br>作为换行符
15. 应聘联系方式(ApplyContacts)：公告中会用一段文字说明如何投递，如网址、邮箱、二维码等；是个数组，包含(联系人名(Name)、手机(Mobile)、邮箱(Email))，带有*号的忽略
16. 应聘邮件主题格式(EmailSubject)：简历投递邮件的简历备注、邮件标题主题格式、简历文档名称、文件命名要求
17. 简历投递邮箱(ApplyTypeEmail)：简历投递邮箱地址，如果多个用逗号分割，带有*号的忽略
18. 公告是否允许邮箱应聘投递(AllowApplyEmail)：公告是否允许使用应聘邮箱投递，可选择：“是”、“否”，默认是“否”，如果是咨询邮箱、答疑邮箱、校招答疑，则为“否”
19. 毕业届次(GraduationYear)：从公告中提取招聘哪一年的毕业生，如“2015届、2015年、2016届”，不重复，是个数组，如果公告中没有则为“”，但不能小于当前年
20. 公告标签(AnnouncementLabel)：从公告里能提的校招的分类标签，可能是多个，不重复，是个数组，可选择：“25秋招”、”25春招”、”25春招提前批”，”25秋招补录”，”25实习”，”25春招实习”，”25暑期实习”，”往届可投”
21. 多公司招聘(HasMultipleCompanies)公告是否是多公司招聘：可选择：“是”、“否”，默认是“否”
Rules：
1. 招聘公告中没有提及的信息，输出空即可；
2. 完全按照原文输出，不需要加工。
3. 你所需要的全部内容都在[webpage X begin]...[webpage X end]中，不能虚构内容。
4. 今天是2025-04-14
5. 如果应聘邮箱、手机号中带有*号，则是保密，忽略掉，不要提取

[webpage X begin]

招聘公告：
未名JOB | 中国稀土集团2025届春季校园招聘正式启动（校招）
国
中國稀土集團
CHINA RARE EARTh GROUP CO.LTD.
Tb
创新驱动
稀土领航
中国稀土集团2025届校园招聘
正式启动	《
公司介绍
中国稀土集团有限公司（简称“中国稀土集团"）
于2021年12月23日在江西省赣州市成立，是由中国铝
业集团有限公司、中国五矿集团有限公司、赣州稀土
集团有限公司所属稀土资产重组整合，并引入中国钢
研科技集团有限公司、中国有研科技集团有限公司两
家科技型企业组建而成，是国务院国有资产监督管理
委员会直接监管的股权多元化中央企业。
中国稀土集团主要从事稀土资源开发、冶炼分
离、精深加工以及稀土产品进出口贸易等，业务范围
涵盖科技研发、勘探开采、冶炼分离、精深加工、再
生资源综合利用、新材料研发制造、成套装备、技术
咨询服务、进出口及贸易等稀土全业务领域、全产业
链条，产业遍及江西、广西、湖南、四川、江苏、山
东、云南、广东和福建等地及东南亚有关国家和地
区，拥有中国稀土（股票代码:000831）、广晟有色
（股票代码：600259）2家上市公司
中国稀土集团拥有显著的资源储备优势、深厚的
产业基础优势、领先的技术研发优势和强大的综合服
务优势，致力于建成资源保障一流、产业引领一流
自主创新一流、智能生态一流、人才团队一流、品牌
价值一流的世界一流稀土产业集团。
2025届春季校园招聘需求
招聘范围
2025届高校应届毕业生（含留学生）
招聘单位
中稀江西稀土有限公司
中稀广西稀土有限公司
中稀（湖南）稀土开发有限公司
中稀（凉山）稀土有限公司
广晟有色金属股份有限公司
再生资源事业部
招聘岗位
材料化学类	采矿冶金类
机械电气类	地质勘查类
安全环保类	新闻文学类
贸易营销类	财务金融类
基本条件
学历背景优秀，所学专业与招聘岗位资格条件匹配；
责任心、事业心强，有良好的职业道德和政治素养；
能接纳并融入企业文化，尊重和认同企业的核心价值观；
有较好的外语听说读写能力和文字写作水平；
具有较强的集体荣誉感和沟通协作意识；
遵纪守法、诚实守信、作风正派、身心健康，无不良记录。
招聘地域
湖南	四川	广东
人才发展和薪资诗遇
3
多维的	定制化的	具有竞争力的	完善的
职业发展通道	职业培训体系	薪酬	福利保障
：
Yi
舒适的	温馨的	良好的	多彩的
工作环境	人才公寓	工作氛围	业余活动
招聘流程
简历投递时间
即日起至2025年4月15日
招聘流程
网申报名	资格审查	笔试
签订三方协议	体检	面试
报到
简历投递渠道
详见国聘招聘平台,投递简历请登录
https://regcc.iguopin.com/
投递二维码
温馨提示
应聘者仅限对每单位1个招聘岗位投递简历，如同
时投递多个岗位视为服从调剂。
对通过简历筛选的应聘者，我们将以短信或邮件形
式，告知笔试等后续事项，请保持手机和电子邮箱
畅通，未通过简历筛选和过程中未入围的应聘者，
不再另行通知。
3	· 应聘者应对本人提供的信息及材料的真实性负责
如在招聘各环节发现应聘者提供虚假信息或考试作
弊，一律取消应聘资格。
中国稀土集团
期待您的加入！
Tb
AllRightsReserved
*
*温馨提示
：请关注本公众号并加个“
星标
”，读完文章点次“
分享
”、点个
“
赞
”
、点下
“
在看
”
，以后每次新文章会第一时间出现在您的订阅列表。


[webpage X end]
'''


# def call_gpt_demo(prompt):
#     return False,DEMO_STR

#版本模型
def getVers():
    return model_name

if __name__ == '__main__':
    print(call_gpt(DEMO_STR,True))