import json
import sys
sys.path.append('../')

import os
import re
import datetime

from utils import ner_logger,getMD5Str,get_local_ip,QZ_VERISON,deduplicate_strings,all_zh
from utils_html import clean_text,get_md_content,fix_md_after_gpt
from utils_resume import fix_diploma
from utils_date import fix_data_format,is_near_month,get_current_time_string
 
from parsegpt.template import get_template_campus_wb10 as get_template_campus
# from parsegpt.template import get_template_campus_cyr10 as get_template_campus
from parsegpt.template import get_template_full_html,get_template_table_html

from parsegpt.template import  get_template_job_wb as  get_template_job
from parsegpt.template import  get_template_article as  get_template_article
from parsegpt.template import  get_template_article_fix as  get_template_article_fix

from api.doubao_api import call_gpt
from api.doubao_api import call_gpt as doubao_call_gpt
from api.qwen_api import call_gpt as qwen_call_gpt 
from api.quanzhi_api import check_cloud
from parsegpt.ann_model_job import parse_cjob
#解析职位信息
def parse_announcement(_mdfile,_htmlfile,_model_file,_info,_full_text,proc_type,sch_info,_expired_file,_stat):
    #大模型分析的json
    _ann_dict = {}
    _title = _info['announcement_name']
    _text = clean_text(_full_text) 
    _tuning_md = ""
    _tuning_full_text = ""
    #设置调优信息
    if 'tuning_content' in _info and len(_info['tuning_content']) > 0:
        _tuning_t = _info['tuning_content']
        #太长会大模型报错了
        if len(_tuning_t)> 6000:
            _tuning_t = _tuning_t[:6000]
        _tuning_full_text = "\n".join(_tuning_t)
    #执行大模型公告解析：包含 公司信息、公告主体
    try:
        _all_text = f"{_text}\n{_tuning_full_text}"
        _t_text =  get_template_campus(_title,_all_text)
        (_ok_flag,json_str) = call_gpt(_t_text,True) 
        if not _ok_flag: 
            return False,f"通过大模型获取公告信息Error:{_ok_flag}\n{json_str}"
        json_data = json.loads(json_str,strict=False)
        #判断是否项目不够
        if len(json_data) < 10:
            return False,f"通过大模型获取公告信息项目太少Error:{_ok_flag}\n{json_str}"
        #判断是否过期的文档
        if 'OnlineEndDate' in json_data and json_data['OnlineEndDate'].strip() != '':
            _datestr = fix_data_format(json_data['OnlineEndDate'].strip())
            if not is_near_month(_datestr,1):
                return False,f"处理的公告过期:{_datestr}"
        _com_name = json_data['ComName'].strip()
        #判断是否是多公司
        if 'HasMultipleCompanies' in json_data and json_data['HasMultipleCompanies'].strip() == "是":
            #如果全部是中文并且小于30个字则忽略
            if all_zh(_com_name) and len(_com_name) < 25: 
                ner_logger.info(f"处理的公告存在多公司的情况,排除掉:{_com_name}")
            else: 
                json_data['ComName'] = "校招公告"
                json_data['ComDesc'] = ""
                json_data['ComIndustry'] = ""
        #如果多公司
        elif not all_zh(_com_name) and len(_com_name) > 40:
                json_data['ComName'] = "校招公告"
                json_data['ComDesc'] = ""
                json_data['ComIndustry'] = ""
                json_data['HasMultipleCompanies'] = "是"              
        #检查是否有投递链接没有，则去info里面找
        _qrdict = get_qrcode_info(_info)
        json_data['ApplyTypeQrcode'] = _qrdict
        json_data['FullText'] = _all_text
        #设置其他字段
        set_other_info(sch_info,_info,json_data,_text,_htmlfile)
        #判断是否是三无产品
        if not json_data['ApplyTypeLink'] and not json_data['ApplyTypeText'] and not json_data['ApplyTypeEmail'] and len(json_data['ApplyTypeQrcode']) == 0 and len(json_data['ApplyContacts']) == 0:
            return False,f"处理的公告存在无链接、无应聘文本、无应聘邮箱、无联系方式的的情况"  
        #判断是否没有应聘方似乎
        if not json_data['ComName'] or not json_data['JobTitle']:
            return False,f"处理的公告存在无公司、无公告名称的情况" 
        #判断云端是否重复
        #check_cloud(_durl,_companyname,_fulltext,_jie,_dist = 'dev'):
        _ok,msg = check_cloud(json_data['JobLink'],json_data['ComName'],json_data['FullText'], json_data['GraduationYear'])
        if not _ok:
            return False,f"云端检测公告重复:{msg}"
        #修复json_data中的学历
        fix_diploma_data_map(json_data)
        #第一个节点是公告主体信
        _ann_dict['ann'] =json_data
    except json.JSONDecodeError as e: 
        #输出错误信息
        import traceback
        traceback.print_exc()
        return False,f"通过大模型获取公告信息Error:\n{e}"
    #学校白名单
    _white_list =  ['sch_98534','sch_00131','sch_98531','sch_98523','sch_21131','sch_98507','sch_00114','sch_00102']
    #判断文档的格式，如果是职位则打印输出
    if _info['channel'] in _white_list and json_data['AnnouncementType'] == "职位":
        ner_logger.info(f"处理的公告是职位信息:{_title}")
        ner_logger.info(f"处理的职位信息:{json_data}")
        #增加一些字段
        json_data['server_ip'] = get_local_ip()
        json_data['qz_version'] = QZ_VERISON
        #获取当前时间的字符串
        json_data['process_time'] = get_current_time_string()  
        #处理文件
        json_data['file_path'] = _htmlfile
        #mdfile 
        common_process_fix(_mdfile,json_data)
        #调用公告职位信息
        _ok,annjson_data = parse_cjob(_htmlfile,json_data)
        #ner_logger.info(f"处理的职位信息:{annjson_data}")
        if _ok:
            with open(_model_file,'w',encoding='utf-8') as fw:
                json.dump(annjson_data,fw,ensure_ascii=False,indent=4)
                ner_logger.info(f"处理文章生成公告内职位模型文件成功,{_model_file}")
            _job_other_file =_expired_file.replace(".json.expired",".json.job")
            with open(_job_other_file,'w',encoding='utf-8') as fw:
                fw.write(f"job 110\n")
            #返回成功
            return True,f"{_htmlfile}公告内职位解析成功"
        
        #职位解析失败
        return False,f"{_htmlfile}公告里面的职位解析失败"
    else:
        _job_other_file =_expired_file.replace(".json.expired",".json.job")
        #如果存在，则删除
        if os.path.exists(_job_other_file):
            os.remove(_job_other_file)

    #执行大模型公告解析：包含 职位信息列表
    try:
        _t_text =  get_template_job(_title,_text) 
        _ok,json_data = get_all_job_info(_t_text)
        if not _ok:
            return False,f"通过大模型获取职位信息列表Error:\n{json_str}"
        #判断没有职位,从优化的里面获取
        if len(json_data) == 0 and len(_tuning_full_text) > 10: 
            _t_text =  get_template_job(_title,_tuning_full_text) 
            _ok,json_data = get_all_job_info(_t_text)
            if not _ok:
                return False,f"通过大模型获取职位信息列表,从优化的内容里面Error:\n{json_str}"
            _tuning_md = fix_md_using_gpt_full(_tuning_full_text)
        #判断没有职位
        # if len(json_data) == 0 and len(_ann_dict['ann']["JobName"]) == 0:
        #     return False,f"处理的公告存在无职位列表、无职位名的情况"   
        #设置职位信息列表
        set_other_job_list(json_data)
        #第二个节点是职位信息列表
        _ann_dict['jobs'] =json_data
    except json.JSONDecodeError as e: 
        return False,f" 通过大模型获取职位信息列表总的 Error:\n{e}"       
    #增加附加json格式
    _info['mdfile_path'] = _model_file
    #第三个节点是附加信息
    _ann_dict['other'] =_info
    #读取_htmlfile
    with open(_htmlfile, 'r', encoding='utf-8') as f:
        _html_file_content = f.read() 
    #读取_mdfile
    #第四个节点是markdown文件的内容
    if 'is_large_image' in _info and _info['is_large_image'] == 'OK' or 'type_url' in _info and _info['type_url'] == 'wxwz':
        common_process(_mdfile,_ann_dict,_tuning_md)
    #根据是否是外部链接，来确认如何创建markdown文件
    elif 'is_external_link' in _info and _info['is_external_link'] == 'OK':
         _ann_dict['mdfile'] = fix_md_using_gpt_full(_text)
         ner_logger.info(f"使用大模型对全文进行markdown提取,{_htmlfile}")
    elif 'text_to_markdown' in sch_info and sch_info['text_to_markdown'] == 'OK':
        _ann_dict['mdfile'] = fix_md_using_gpt_full(_text) 
        ner_logger.info(f"使用大模型含table的全文进行markdown提取,{_htmlfile}")         
    elif ('has_table' in _info and _info['has_table'] == 'OK' or
          'html_to_markdown' in sch_info and sch_info['html_to_markdown'] == 'OK') and len(_tuning_full_text) == 0:
         if len(_html_file_content) < 20000:
            _ann_dict['mdfile'] = fix_md_using_gpt_table(_html_file_content)
            ner_logger.info(f"使用大模型对含table进行markdown提取,{_htmlfile}")
         else:
            _ann_dict['mdfile'] = fix_md_using_gpt_full(_text) 
            ner_logger.info(f"使用大模型含table的全文进行markdown提取1,{_htmlfile}")
    else:
        common_process(_mdfile,_ann_dict,_tuning_md)
    #第五个节点是html文件的内容
    _ann_dict['htmlfile'] = ""#_html_file_content

    if len(_ann_dict) >= 5:
        with open(_model_file,'w',encoding='utf-8') as fw:
            json.dump(_ann_dict,fw,ensure_ascii=False,indent=4)
            ner_logger.info(f"处理文章生成模型文件成功,{_model_file}")
        #清除无用的文件
        os.remove(_mdfile)
        os.remove(_htmlfile) 
        #返回成功
        return True,f"{_mdfile}解析成功"
    else:
        return False,f"{_mdfile}解析失败"
#通用处理
def common_process(_mdfile,_ann_dict,_tuning_md):   
    # with open(_mdfile, 'r', encoding='utf-8') as f:
    _ann_dict['mdfile'] = get_md_content(_mdfile,"")
    #如果是非微信，需要再用大模型给优化格式下
    if len(_ann_dict['mdfile']) < 20000:
        _ann_dict['mdfile'] = fix_md_using_gpt(_ann_dict['mdfile'])
    #大模型后重新修复文档
    _ann_dict['mdfile'] = fix_md_after_gpt(_ann_dict['mdfile'],_tuning_md)
 
#使用删减的大模型处理
def common_process_fix(_mdfile,_ann_dict):   
    # with open(_mdfile, 'r', encoding='utf-8') as f:
    _ann_dict['mdfile'] = get_md_content(_mdfile,"")
    #如果是非微信，需要再用大模型给优化格式下
    _ann_dict['mdfile'] = fix_md_using_gpt_fix(_ann_dict['mdfile']) 

    #打印mdfile
    ner_logger.info(f"处理文章生成模型文件成功,{_ann_dict['mdfile']}")

#获取职位的信息
def get_all_job_info(_t_text):
    ner_logger.info(f"开始通过大模型获取职位信息列表 {_t_text}")
    (_ok_flag,json_str) = call_gpt(_t_text,True)
    if not _ok_flag:
        return False,{}
    json_data = json.loads(json_str,strict=False)
    #检查类型，如果是map类型,需要转换一下
    if isinstance(json_data,dict) and len(json_data) == 1:
        #循环map
        for k,v in json_data.items():
            if isinstance(v,list):
                json_data = v
                break
    #修复json_data
    fix_diploma_data_list(json_data)
    #修复数据中的职位名称为空的
    json_data = fix_jobname_data_list(json_data)

    return True,json_data
#使用大模型修复markdown文件
def fix_md_using_gpt(_content):
    #如果内容长度大于5000，则不优化,因为不稳定
    if len(_content) > 20000:
        return _content
    chi = re.findall(r'[\u4E00-\u9FFF]',_content)
    if len(chi) < 100:
        return _content
    #使用大模型优化
    _t_text =  get_template_article(_content)
    #使用豆包
    (ok,json_str) = doubao_call_gpt(_t_text,True)
    if ok:
        try:
            json_data = json.loads(json_str,strict=False)
            #返回mdContent，并且值是字符串
            if 'mdContent' in json_data and isinstance(json_data['mdContent'],str):
                return json_data['mdContent']
            elif 'mdcontent' in json_data and isinstance(json_data['mdcontent'],str):
                return json_data['mdcontent']
            else:
                ner_logger.error(f"fix_md_using_gpt warning :{json_data}")
        except json.JSONDecodeError as e:
            ner_logger.error(f"fix_md_using_gpt Error:{json_str}\n{e}")
    #返回原版
    return _content

#使用大模型修复markdown文件
def fix_md_using_gpt_fix(_content):
    #如果内容长度大于5000，则不优化,因为不稳定
    if len(_content) > 20000:
        return _content
    chi = re.findall(r'[\u4E00-\u9FFF]',_content)
    if len(chi) < 100:
        return _content
    #使用大模型优化
    _t_text =  get_template_article_fix(_content)
    #使用豆包
    (ok,json_str) = qwen_call_gpt(_t_text,True)
    if ok:
        try:
            json_data = json.loads(json_str,strict=False)
            #返回mdContent，并且值是字符串
            if 'mdContent' in json_data and isinstance(json_data['mdContent'],str):
                return json_data['mdContent']
            elif 'mdcontent' in json_data and isinstance(json_data['mdcontent'],str):
                return json_data['mdcontent']
            else:
                ner_logger.error(f"fix_md_using_gpt warning :{json_data}")
        except json.JSONDecodeError as e:
            ner_logger.error(f"fix_md_using_gpt Error:{json_str}\n{e}")
    #返回原版
    return _content

def fix_md_using_gpt_full(_content):
    _t_text =  get_template_full_html(_content)
    return fix_md_using_gpt_full_inner(_content,_t_text)
def fix_md_using_gpt_table(_content):
    _t_text =  get_template_table_html(_content)
    return fix_md_using_gpt_full_inner(_content,_t_text)
#使用大模型修复markdown文件
def fix_md_using_gpt_full_inner(_content,_t_text):
    #如果内容长度大于5000，则不优化,因为不稳定
    if len(_content) > 20000:
        return _content
    ner_logger.info(f"开始通过大模型获取全文/table优化 {_t_text}")
    #使用大模型优化
    (ok,json_str) = doubao_call_gpt(_t_text,True)
    if ok:
        try:
            json_data = json.loads(json_str,strict=False)
            #返回mdContent，并且值是字符串
            if 'mdContent' in json_data and isinstance(json_data['mdContent'],str):
                return json_data['mdContent']
            elif 'mdcontent' in json_data and isinstance(json_data['mdcontent'],str):
                return json_data['mdcontent']
            else:
                ner_logger.error(f"fix_md_using_gpt full warning :{json_data}")
        except json.JSONDecodeError as e:
            ner_logger.error(f"fix_md_using_gpt full Error:{json_str}\n{e}")
    #返回原版
    return _content
#设置其他字段
def set_other_info(sch_info,_info,json_data,_text,_htmlfile):
        #设置内容的MD5值
        json_data['FileId'] = getMD5Str(_text)
        #增加类型,如果是微信文章，则需要标记下，后面处理
        json_data['AnnType'] = 'wx_ann' if _info['type_url'] == 'wxwz' else 'sch_ann'
        #增加原始链接
        json_data['JobLink'] = _info['full_url']
        #增加原始公告标题
        json_data['JobTitle'] = _info['announcement_name']
        #因为性能原因，移除没有用
        json_data['JobDescribe'] = ""
        json_data['JobReq'] = ""
        #增加对获取的公司信息进行.,如果公司名字没，则用这个名字
        if 'hd_company' in _info and _info['hd_company'] and len(_info['hd_company']) > 5:
            json_data['HdCompany'] = _info['hd_company']
            if 'ComName' in json_data and json_data['ComName'] and json_data['ComName'].strip() == '':
                json_data['ComName'] = json_data['HdCompany']
            elif 'fix_hd_company' in sch_info and sch_info['fix_hd_company'] == 'Y':
                json_data['ComName'] = json_data['HdCompany']
            #邮箱
            if 'hd_email' in _info and _info['hd_email']:
                if 'ApplyTypeEmail' in json_data and json_data['ApplyTypeEmail'].strip() == '':
                    json_data['ApplyTypeEmail'] = _info['hd_email']
        #增加对公告名称的处理,如果获取的包含在公告名称中，则用公告名称替换
        if 'hd_ann' in _info and len(_info['hd_ann']) > 10:
            _copy_jobname = json_data['JobTitle']
            # if json_data['JobTitle'] in json_data['HdAnn']:
            json_data['JobTitle'] = _info['hd_ann']
            json_data['HdAnn'] = _copy_jobname
        #增加发布日期
        if not 'PublishTime' in json_data:
            json_data['PublishTime'] = ''
        if 'publish_time' in _info:
            json_data['PublishTime'] = _info['publish_time']
        #微信id
        json_data['WeixinId'] = ''
        if 'wx_id' in _info:
            json_data['WeixinId'] = _info['wx_id']
        #微信公众号名称
        json_data['WeixinName'] = ''
        if 'wx_name' in _info:
            json_data['WeixinName'] = _info['wx_name']   
        if json_data['WeixinName'] == '' and 'sch_webname' in sch_info:
            json_data['WeixinName'] = sch_info['sch_webname']
        if json_data['WeixinName'] == '' and 'sch_name' in sch_info:
            json_data['WeixinName'] = sch_info['sch_name']
        #微信公众号名称
        json_data['WeixinTitle'] = ''
        if 'wx_title' in _info:
            json_data['WeixinTitle'] = _info['wx_title']   
        #微信发布时间
        json_data['WeixinPublishTime'] = ''
        if 'wx_public_time' in _info:
            json_data['WeixinPublishTime'] = _info['wx_public_time']
        #处理详情链接信息
        json_data['WeixinXqxx'] = ''
        if json_data['AnnType'] == 'wx_ann':
            _ok,xqxx = get_wx_xqxx(_info)
            if _ok:
                json_data['WeixinXqxx'] = xqxx
        #设置ApplyContacts
        if 'ApplyContacts' in json_data:
            for _c in json_data['ApplyContacts']:
                _c['Tel'] = ''
                _c['Dept'] = ''
        #处理地区
        # ner_logger.info(f"处理地区{ json_data['WorkPlace']},{json_data['ComPlace']}")
        if 'WorkPlace' in json_data and json_data['WorkPlace'] == '' and 'ComPlace' in json_data and json_data['ComPlace']!='':
            json_data['WorkPlace'] = json_data['ComPlace']
        #优化专业
        if 'MajorRequirement' in json_data:
            #兜底处理：如果不是字典类型，尝试解析或赋空
            if not isinstance(json_data['MajorRequirement'], dict):
                if isinstance(json_data['MajorRequirement'], str):
                    try:
                        json_data['MajorRequirement'] = json.loads(json_data['MajorRequirement'])
                    except:
                        json_data['MajorRequirement'] = {}
                else:
                    json_data['MajorRequirement'] = {}
            if len(json_data['MajorRequirement']) > 20:
                json_data['MajorRequirement'] = deduplicate_strings(json_data['MajorRequirement'])
        #优化职位
        if 'JobName' in json_data and len(json_data['JobName']) > 20:
            json_data['JobName'] = deduplicate_strings(json_data['JobName'])
        #如果没类型补充
        if not 'AnnouncementType'  in json_data: 
            json_data['AnnouncementType'] = "公告"
        #如果是公告则检查
        if json_data['AnnouncementType'] == "公告" and len(json_data['JobTitle']) <=10:
            _find_gs_kw = False
            for _kw in ['公司','公告','集团','学院']:
                if _kw in json_data['JobTitle']:
                    _find_gs_kw = True
                    break
            _find_zw_kw = False
            for _kw in ['人员','师','岗']:
                if _kw in json_data['JobTitle']:
                    _find_zw_kw = True
                    break
            if not _find_gs_kw and _find_zw_kw:
                json_data['AnnouncementType'] = '职位'
        #处理薪资 面谈
        if 'Salary' in json_data and json_data['Salary'] in ['面谈','待遇从优']:
            json_data['Salary'] = '面议'
        #HopeWorkType处理
        if  not 'HopeWorkType' in json_data:
            json_data['HopeWorkType'] = '全职'
        #处理毕业届 
        fix_graduate_year(json_data)

        _info['source_link'] = ''
        _info['source_link_text'] = ''
        #_info['channel'] ！= 'sch_88888'
        if _info['channel'] != 'sch_88888':
            #设置SourceLink
            if  'SourceLink' in json_data and json_data['SourceLink'] != '':
                _info['source_link'] = json_data['SourceLink']
            else:#从 html 里面获取
                #获取来源链接
                _ok,source_link_text,source_link = get_source_link(_htmlfile)
                if _ok:
                    _info['source_link'] = source_link
                     #替换掉“来源于”
                    _info['source_link_text'] = source_link_text.replace("来源于","")
            #设置SourceLinkText
            if _info['source_link_text'] == '' and 'SourceLinkText' in json_data and json_data['SourceLinkText'] != '':
                #替换掉“来源于”
                _info['source_link_text'] = json_data['SourceLinkText'].replace("来源于","")

        #设置其他信息中的字段
        _info['server_ip'] = get_local_ip()
        _info['qz_version'] = QZ_VERISON
        #获取当前时间的字符串
        _info['process_time'] = get_current_time_string()      
#添加职位列表中的描述
def set_other_job_list(json_data):
    for _job in json_data:
        #因为性能原因，移除没有用
        _job['JobDescribe'] = ""
        _job['JobReq'] = ""
#获取info 中的二维码信息
def get_qrcode_info(info):
    _qrcode_info = info['props']
    if 'img_urls' in _qrcode_info:
        _urls = _qrcode_info['img_urls']
        #找到full_qr
        for _k,_m in _urls.items():
            if 'full_qr' in _m and _m['full_qr'] == 'Y':
                _mm = {}
                for _kk,_v in _m.items():
                    if _kk.startswith('http'):
                        _mm['qr_url'] = _kk
                        _mm['qr_pic'] = _m['qz_img_url'] if 'qz_img_url' in _m else _k
                        _mm['all_qr_pics'] = {_mm['qr_url']:_mm['qr_pic']}
                        return _mm 
        #如果没有找到全部的，则从整图里面截取
        for _k,_m in _urls.items():
            if 'full_qr' in _m and _m['full_qr'] == 'H' and 'inside_qr_link' in _m and 'inside_qr_pic' in _m:
                _mm = {}
                _mm['qr_url'] = _m['inside_qr_link']
                _mm['qr_pic'] = _m['inside_qr_pic']
                _mm['all_qr_pics'] = _m['all_qr_pics']
                return _mm 
    #默认空
    return {}
#修复json_data
def fix_diploma_data_list(json_data):
    for item in json_data:
        if 'Degree' in item:
            need_fix = item['Degree']
            item['Degree'] = fix_diploma(need_fix)
            # ner_logger.debug(f"Degree:{need_fix}->{item['Degree']}")
def fix_diploma_data_map(item): 
    if 'Degree' in item:
        need_fix = item['Degree']
        item['Degree'] = fix_diploma(need_fix)

#修复职位名称为空的
def fix_jobname_data_list(json_data):
    _njson_data = []
    # _jobstr = []
    for item in json_data:
        if 'JobTitle' in item and item['JobTitle'] == '':
            continue
        # if 'JobTitle' in item:
        #     _jobstr.append(item['JobTitle']) 
        _njson_data.append(item)
    return _njson_data #,"".join(_jobstr)


#处理毕业
def fix_graduate_year(json_data):
    #如果没有发现
    if not 'GraduationYear' in json_data:
        json_data['GraduationYear'] = ""
    #获取
    _obj = json_data['GraduationYear']
    #如果类型是str，则复制为list
    if type(_obj) == str:
        if _obj != '':
            json_data['GraduationYear'] = [_obj]
        else:
            json_data['GraduationYear'] = []
    elif type(_obj) == list:
        json_data['GraduationYear'] = _obj

    #优先从标题里面获取
    if 'JobTitle' in json_data and len(json_data['JobTitle']) > 5:
        p = re.compile(r"(?:202\d(?=\D|\s|$))|(?:2\d(?=届|毕业|年))")
        fun = lambda y: f"20{y}" if len(y) == 2 else y
        oldy = p.findall(json_data['JobTitle'])
        oldYears = list(map(fun, oldy))
        #如果json_data['GraduationYear']  是 list，则添加
        if len(oldYears) > 0 and type(json_data['GraduationYear']) == list:
            json_data['GraduationYear'].extend(oldYears)
            ner_logger.info(f"fix_graduate_year 从标题里面获取添加: {oldYears} , {json_data['JobTitle']}")

    #处理为空，从标题里面获取
    if len(json_data['GraduationYear']) == 0:
        #正则年 
        match = re.findall(r'202[5-9]', json_data['JobTitle'])
        if match:
            json_data['GraduationYear'] = match 
            ner_logger.info(f"fix_graduate_year: {match} , {json_data['JobTitle']}")
    #处理届
    if len(json_data['GraduationYear']) == 0:
        match = re.findall(r'2[5-9][ ]*届', json_data['JobTitle'])
        if match:
            json_data['GraduationYear'] = match
            ner_logger.info(f"fix_graduate_year jie: {match} , {json_data['JobTitle']}")
    #写死代码，后面优化20250220，chu 
    if len(json_data['GraduationYear']) != 0: 
        _nl = []
        for _str in json_data['GraduationYear']:
            if _str.isdigit():
                _nl.append(_str)
            elif '25届' in _str:
                _nl.append('2025')
            elif '26届' in _str:
                _nl.append('2026')
            elif '27届' in _str:
                _nl.append('2027')
            elif '28届' in _str:
                _nl.append('2028')
        json_data['GraduationYear'] = list(set(_nl))    
    #从当前时间获取
    if len(json_data['GraduationYear']) == 0: 
        #获取当前年
        year = datetime.datetime.now().year
        month = datetime.datetime.now().month
        if month >= 8:
            year += 1
        json_data['GraduationYear'] = [f'{year}']
    
#获取微信中的详情信息
def get_wx_xqxx(_data):
    #获取图片的url地址链接
    if 'wx_code_file_config' in _data:
        _config_file = _data['wx_code_file_config']
        #加载json
        if os.path.exists(_config_file):
            with open(_config_file, 'r', encoding='utf-8') as f:
                _config = json.load(f)
                # ner_logger.info(f"加载图片实际大小配置文件 {_config}")
                if 'yqym_url' in _config:
                    return True,_config['yqym_url']
    return False,""

#获取来源get_source_link
def get_source_link(_htmlfile):
    #加载html
    with open(_htmlfile, 'r', encoding='utf-8') as f:
        _html = f.read()
    #读取<a href="https://www.baidu.com">链接</a> 里面的链接和文字
    pattern = r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    match = re.findall(pattern, _html, re.S)
    # 输出结果
    for href, text in match: 
        #如果链接是https://mp.weixin.qq.com则返回
        if 'mp.weixin.qq.com' in href:
            return True,"来源于微信文章",href
    # 输出结果
    for href, text in match: 
        if '来源' in text:
            return True,"来源于网络",href
    return False,"",""

