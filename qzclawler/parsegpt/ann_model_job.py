import json
import sys
sys.path.append('../')
import re

from utils import ner_logger,getMD5Str,get_local_ip,QZ_VERISON

from api.doubao_api import call_gpt as doubao_call_gpt 
from api.qwen_api import call_gpt as qwen_call_gpt 

from parsegpt.template import  get_template_cjob_annotation
from utils_resume import fix_diploma
from parsegpt.html_to_text import Html2txt

from bs4 import BeautifulSoup

#解析职位
def parse_cjob(_hfile,ann_json_data):
    _ann_dict = {}
    #执行大模型公告解析：包含 公司信息、公告主体
    try: 
        #_text = ann_json_data['FullText']
        _text  = get_cjob_html_content(_hfile)
        #调用大模型
        _t_text =  get_template_cjob_annotation(_text)
        (_ok_flag,json_str) = qwen_call_gpt(_t_text,True) 
        if not _ok_flag: 
            return  "",f"通过大模型获取公告里面的单个职位职位信息Error:{_ok_flag}\n{json_str}"
        ner_logger.info(f"通过大模型获取公告里面的单个职位信息json:{json_str}")
        #加载json
        json_data = json.loads(json_str,strict=False)  
        #如果为空则不要
        if len(json_data['JobDescribe']) + len(json_data['Jobreq']) < 30:
            return  "",f"职位信息的描述太少:{_hfile}\n{json_str}"
        #修复json_data中的学历
        fix_diploma_data_map(json_data)
        json_data['FileId'] = ann_json_data['FileId']
        json_data['JobLink'] = ann_json_data['JobLink']
        json_data['DocType'] = 'xiaozhao'
        json_data['ComLogo'] = ""
        json_data['ComName'] = ann_json_data['ComName']
        json_data['ComShortName'] = ann_json_data['ComName']
        json_data['NoticeToJob'] = 1
        json_data['WxName'] = ann_json_data['WeixinName']
        json_data['ApplyTypeLink'] = ann_json_data['ApplyTypeLink']
        json_data['GraduationYear'] = ann_json_data['GraduationYear']
        json_data['AnnouncementLabel'] = ann_json_data['AnnouncementLabel']
        json_data['JobTitle'] = ann_json_data['JobTitle']
        json_data['EmailSubject'] = ann_json_data['EmailSubject']
        json_data['ApplyTypeText'] = ann_json_data['ApplyTypeText']
        json_data['GraduationTimeRequirement'] = ann_json_data['GraduationTimeRequirement']
        json_data['mdfile'] = ann_json_data['mdfile']
        json_data['HopeWorkType'] = ann_json_data['HopeWorkType']
        json_data['PublishTime'] = ann_json_data['PublishTime']

        #需要把联系信息复制过来
        if 'ApplyContacts' in ann_json_data:
            acontacts = ann_json_data['ApplyContacts']
            if len(acontacts) > 0:
                if 'Name' in acontacts[0] and not "*" in acontacts[0]['Name']:
                    json_data['ContactPerson'] = acontacts[0]['Name']
                if 'Mobile' in acontacts[0] and not "*" in acontacts[0]['Mobile']:
                    json_data['Phone'] = acontacts[0]['Mobile']
                if 'Email' in acontacts[0] and not "*" in acontacts[0]['Email']:
                    json_data['Email'] = acontacts[0]['Email']
        #如果没有联系人
        if 'Email' in json_data and  json_data['Email'] == "" and 'ApplyTypeEmail' in ann_json_data and ann_json_data['ApplyTypeEmail'] != "":
            json_data['Email'] = ann_json_data['ApplyTypeEmail']
        #第一个节点是公告主体信
        _ann_dict['cjob'] =json_data
        _n_ann_json_data = ann_json_data
        # 如果ApplyTypeQrcode in _n_ann_json_data
        if 'ApplyTypeQrcode' in _n_ann_json_data:
            #移除
            _n_ann_json_data.pop('ApplyTypeQrcode')
        _ann_dict['other'] = _n_ann_json_data
        _ann_dict['cjob_o_field'] = {
            'RecruitProcess':"招聘流程",
            'Attention':'注意事项',
            'WelfareInfo':'薪酬福利',
            'JobDevelopment':'岗位发展',
            'ApplyTypeText' : '应聘方式'
        }
    except json.JSONDecodeError as e: 
        #输出错误信息
        import traceback
        traceback.print_exc()
        ner_logger.error(f"Error:{json_str}")
        return "",f"通过大模型获取公告里面的单个职位信息Error:\n{e}"    
    
    return "OK",_ann_dict
def fix_diploma_data_map(item): 
    if 'Degree' in item:
        need_fix = item['Degree']
        item['Degree'] = fix_diploma(need_fix)


def get_cjob_html_content(_htmlfile):

    #获取文件的html文本
    with open(_htmlfile, "r", encoding="utf-8", errors='ignore')as f1:
        htmltext = f1.read() 
        #返回全部格式化好的文本
        text =  Html2txt().clean_html(htmltext)
        #ner_logger.info(f"文件{_htmlfile} \n*****\n{text}")
        return text