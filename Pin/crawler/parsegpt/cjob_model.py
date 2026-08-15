import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'services'))
import re
import os
from db_handler import record_parsed_file
 
from bs4 import BeautifulSoup

from utils import ner_logger,getMD5Str,get_local_ip,QZ_VERISON
from utils_html import clean_text
from utils_date import get_current_time_string,get_current_data

from parsegpt.template import  get_template_cjob ,get_context_cjob
from api.doubao_api import call_gpt_system
from api.doubao_api import call_gpt as doubao_call_gpt 
from api.qwen_api import call_gpt as qwen_call_gpt 
from api.doubao_api_new import call_gpt as new_call_gpt
from utils_resume import fix_diploma_data_map
from parsegpt.ann_md import fix_html_div
from parsegpt.html_to_text import Html2txt

#解析职位信息
def parse_cjob(spider_data,_model_file,_info,com_info,_expired_file,_hfile,_stat):
    #大模型分析的json
    _ann_dict = {}
    _title = _info['announcement_name']
    _full_text = ""
    #打开文件
    with open(_hfile,"r",encoding="utf-8") as f:
        _html = f.read()
        #获取整个html全文文本内容,写入全文字段
        _full_text = get_cjob_html_content(spider_data,com_info,_html)
    _text = clean_text(_full_text)   
    if len(_text) < 100:
        return "Err",f"通过大模型获取公司职位信息Error:文本长度不足{len(_text)}"
    #执行大模型公告解析：包含 公司信息、公告主体
    try: 
        #设置其他信息
        _a_map = get_hd_element(_html,com_info)
        #调用大模型
        _t_text =  get_template_cjob(_text)
        _T_text =  get_context_cjob(_text)
        (_ok_flag,json_str,tokens) = new_call_gpt(_t_text,_T_text,True)
        if not _ok_flag: 
            return  "",f"通过大模型获取公司职位信息Error:{_ok_flag}\n{json_str}"
        ner_logger.info(f"通过大模型获取公司职位信息json:{json_str}")

        #加载json
        _bt = chr(96)
        if _bt in json_str[:10]:
                json_str = re.sub(r"^(" + _bt + "){1,3}json\s*", "", json_str)
                json_str = re.sub(r"(" + _bt + "){1,3}\s*$", "", json_str)
        json_data = json.loads(json_str,strict=False)
        #设置其他字段
        set_other_info(com_info,_info,json_data,_text,_a_map)
        #如果为空则不要
        if len(json_data['JobDescribe']) + len(json_data['Jobreq']) < 30:
            return  "Err",f"职位信息的描述太少:{_hfile}\n{json_str}"
        #修复json_data中的学历
        fix_diploma_data_map(json_data)
        #第一个节点是公告主体信
        _ann_dict['cjob'] =json_data
    except json.JSONDecodeError as e: 
        #输出错误信息
        import traceback
        traceback.print_exc()
        ner_logger.error(f"Error:{json_str}")
        return "",f"通过大模型获取公司职位信息Error:\n{e}"    
        #增加附加json格式
    _info['mdfile_path'] = _model_file
    #第三个节点是附加信息
    _ann_dict['other'] =_info
    #判断节点是否充足
    if len(_ann_dict) != 2:
        return "",f"通过大模型获取公司职位信息Error:节点不足{len(_ann_dict)}"
    #写文件
    with open(_model_file,'w',encoding='utf-8') as fw:
        json.dump(_ann_dict,fw,ensure_ascii=False,indent=4)
        ner_logger.info(f"处理大公司职位生成模型文件成功,{_model_file}")
    
    # 更新数据库记录为已解析
    try:
        _model_path = str(_model_file)
        _parts = _model_path.replace(chr(92), '/').split('/')
        _com_id = next((p for p in _parts if p.startswith('com_')), '')
        _fname = os.path.basename(_model_path)
        _fhash = _fname.replace('detail_', '').replace('.model.json', '')
        if _com_id and _fhash:
            record_parsed_file(_com_id, _fhash, _model_path)
    except Exception as db_e:
        ner_logger.error(f"更新DB解析状态失败: {db_e}")
    
    print(tokens)
    return "ok",""

#设置其他字段
def set_other_info(com_info,_info,json_data,_text,_a_map):
        #设置内容的MD5值
        json_data['FileId'] = getMD5Str(_text)
        #增加类型,如果是微信文章，则需要标记下，后面处理 
        #增加原始链接
        json_data['JobLink'] = _info['full_url']
        #增加原始公告标题
        json_data['JobTitle'] = fix_job_name(_info['announcement_name'])
        #公司
        json_data['ComName'] = com_info['com_name']
        json_data['ComShortName'] = com_info['com_webname']
        json_data['ComLogo'] = com_info['com_logo']
        json_data['DocType'] = _info['job_type']
        #修复json_data中的学历
        fix_diploma_data_map(json_data)
        #从列表数据中获取
        if 'hd_dept' in _info and len(_info['hd_dept']) > 1:
            json_data['JobDept'] = _info['hd_dept']  
        if 'hd_loc' in _info and len(_info['hd_loc']) > 1:
            json_data['WorkPlace'] = _info['hd_loc']  
        if 'publish_time' in _info and len(_info['publish_time']) > 1:
            json_data['PublishTime'] = _info['publish_time']  
        if 'hd_job_num' in _info and len(_info['hd_job_num']) > 0:
            json_data['JobNum'] = _info['hd_job_num']
        elif "若干" in "hd_job_num" or "不限" in "hd_job_num":
            json_data['JobNum'] = _a_map["hd_job_num"]

        if 'hd_job_category' in _info and len(_info['hd_job_category']) > 0:
            json_data['JobCategory'] = _info['hd_job_category']
        if 'hd_salary' in _info and len(_info['hd_salary']) > 0:
            json_data['Salary'] = _info['hd_salary']  
        if 'hd_hopeworktype' in _info  and len(_info['hd_hopeworktype']) > 0:
            json_data['HopeWorkType'] = _info['hd_hopeworktype']
        #判断实习,校招,社招
        if 'hd_hopeworktype' in _info  and _info['hd_hopeworktype'] == '实习':
            json_data['DocType'] = 'shixi'
        if 'hd_hopeworktype' in _info  and _info['hd_hopeworktype'] == '校招':
            json_data['DocType'] = 'xiaozhao'
        if 'hd_hopeworktype' in _info  and _info['hd_hopeworktype'] == '社招':
            json_data['DocType'] = 'shezhao'

        #从详情里面获取
        if 'hd_job_category' in _a_map and len(_a_map['hd_job_category']) > 0:
            json_data['JobCategory'] = _a_map['hd_job_category']
        if 'hd_loc' in _a_map and len(_a_map['hd_loc']) > 0:
            json_data['WorkPlace'] = _a_map['hd_loc']
        if 'hd_job_num' in _a_map and len(_a_map['hd_job_num']) > 0:
            json_data['JobNum'] = _a_map['hd_job_num']
        if 'hd_publish_time' in _a_map and len(_a_map['hd_publish_time']) > 1:
            json_data['PublishTime'] = _a_map['hd_publish_time']  
        #更新地区
        if not 'WorkPlace' in json_data or json_data['WorkPlace'] in ['全部地区','全国各地','']:
            json_data['WorkPlace'] = com_info['hd_all_location']
        #补充字段，如果没有PublishTime，则为空 
        if not 'PublishTime' in json_data or json_data['PublishTime'] == '':
             json_data['PublishTime'] = get_current_data()
        #增加原始公告标题
        try:
            json_data['JobCategory'] = fix_job_category(json_data.get('JobCategory', ""))
        except Exception as e:
            json_data['JobCategory'] = ""
        #处理为空的
        if not 'JobDescribe' in json_data:
            json_data['JobDescribe'] = ''
        if not 'Jobreq' in json_data:
            json_data['Jobreq'] = ''      
        #默认给一个
        if not 'JobNum' in json_data:
            json_data['JobNum'] = ''      
        #设置其他信息中的字段
        _info['server_ip'] = get_local_ip()
        _info['qz_version'] = QZ_VERISON
        #获取当前时间的字符串
        _info['process_time'] = get_current_time_string()      


def get_cjob_html_content(spider_data,com_info,htmltext):
    #使用soup加载html文件
    soup = BeautifulSoup(htmltext, 'html.parser')   
    #修复div
    fix_html_div(spider_data,soup,com_info,{})
    
    #获取选择器配置
    class_names = com_info.get("detail_selector")
    if class_names:
        for class_name in class_names.split("|"):
            if not class_name:
                continue
            
            # 兼容处理: 可能是 tag.class, 也可能只是 tag
            cc = class_name.split(".")
            div_element = None
            
            try:
                if len(cc) >= 2:
                    # 处理 div.content 这种格式
                    div_element = soup.find(cc[0], class_=cc[1])
                elif len(cc) == 1:
                    # 处理 main, article 这种只有标签的格式
                    div_element = soup.find(cc[0])
            except Exception as e:
                ner_logger.error(f"解析选择器 {class_name} 失败: {e}")
                continue

            if div_element:
                # 将BeautifulSoup元素转换为字符串，然后使用Html2txt处理
                html_content = str(div_element)
                return Html2txt().clean_html(html_content)

    #没有找到，尝试使用正则查找
    class_name_re = com_info.get("detail_selector_re") 
    if class_name_re:
        pattern = re.compile(f'div.{class_name_re}')
        ner_logger.info(f"尝试使用正则查找:{pattern}")
        # 筛选所有 div 元素，class 属性匹配正则
        matched_divs = soup.find_all('div', class_=pattern)
        if matched_divs:
            # 将BeautifulSoup元素转换为字符串，然后使用Html2txt处理
            html_content = str(matched_divs[0])
            return Html2txt().clean_html(html_content)
            
    # 如果以上都没找到，返回全部格式化好的文本
    return Html2txt().clean_html(htmltext)

def get_hd_element(htmltext,com_info):
    #使用soup加载html文件
    soup = BeautifulSoup(htmltext, 'html.parser')   
    _map = {}
    if 'detail_hd' in com_info and com_info['detail_hd'] == "0001":
        div_span = soup.find('div', class_='pos-detail-hd__titBar')
        if div_span:
            tit_span = soup.find('span', class_='tit')
            if tit_span:
                label_span = soup.find('span', class_='label')
                if label_span:
                    _text = label_span.get_text()
                    for _t in ['职位类别：','职位类别']:
                        _text = _text.replace(_t,"")
                    _map['hd_job_category'] = _text
    if 'detail_hd' in com_info and com_info['detail_hd'] == "0002":
        div_span = soup.find('div', class_='pos-detail-hd__infoBar')
        if div_span:
            loc_span = soup.find('span', class_='item-overflow')
            if loc_span:
                _map['hd_loc'] = loc_span.get_text()
    if 'detail_hd' in com_info and com_info['detail_hd'] == "0003":
        div_span = soup.find('div', class_='pos-detail-hd__infoBar')
        if div_span:
            _text = div_span.get_text()
            #使用正则yyyy-mm-dd的格式，匹配
            match = re.search(r'\d{4}-\d{2}-\d{2}', _text)
            if match:
                _map['hd_publish_time'] = match.group()
            #使用正则匹配招聘人数，如若干人，招聘1人
            match = re.search(r'\d{1,3}人', _text)
            if match:
                _map['hd_job_num'] = match.group()
            elif '若干' in _text:
                _map['hd_job_num'] = '若干'

    ner_logger.info(f"获取hd_map成功,{_map}")
    return _map

def fix_job_name(_text):
    return _text.replace("职位名称：","").replace("热招","")

#修复职业类别
def fix_job_category(_text):
    if _text in ["热招",'社招','实习','校招']:
        return ""
    #如果符合[A-Z]类的不要
    if re.search(r'[A-Z]类', _text):
        return ""
    return _text



