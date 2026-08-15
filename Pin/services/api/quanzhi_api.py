# -*- coding: utf-8 -*-
"""
@Desc    : 添加公告
@Date    : 2025年1月17日10:13:06
@Author  : leo
"""
import json,requests
import sys
import os
sys.path.append('../')

from utils import ner_logger
from utils_date import fix_data_format,fix_data_format_large

# 定义接口的 URL
# lc参数 表示是否验证JobLink （0或者不传 验证，1不验证）
# cloud_url = "http://192.168.1.17:6868/ann_add?lc=1"   # 测试
#测试环境 -添加公告
debug_cloud_url = "http://192.168.1.17:6868/ann_add?lc=1&ck=1"   # 测试
#正式环境 -添加公告
prod_cloud_url = "http://121.36.63.42:6868/ann_add?lc=1&ck=1"   # 正式
#测试环境 -查找重复公告
debug_check_url = "http://192.168.1.17:6868/checkrepeat"   # 测试
#正式环境 -查找重复公告
prod_check_url = "http://121.36.63.42:6868/checkrepeat"   #华为云

#大公司职位
#测试环境 
debug_job_cloud_url = "http://192.168.1.17:6868/jobparse"
#正式环境 http://121.36.63.42:6868/jobparse  # 外网IP地址
prod_job_cloud_url = "http://121.36.63.42:6868/jobparse"

# 设置请求头信息
headers = {
    "Content-Type": "application/json"
}
#返回值说明
#成功 :
#{'code': 200, 'msg': 'ok', 'data': {'jobId': "67890c78f663ba81f1c854b9"}}

#失败：
#{'code':201,'msg':'参数错误',{"JobTitle":'no'}} #  JobTitle 没值
#{'code':204,'msg':'公司不存在'}
#{'code': 300, 'msg': '公告公司名称校验失败'}  #这个是需要记录下来，人工分析公司名称。修改正确从新入库
#{'code': 301, 'msg': '公告已过期'}
#{'code': 302, 'msg': '公告职位名称包含黑名单'}
#{'code': 303, 'msg': '公告全文重复或太相似'}
#{'code':304, 'msg': '公告Joblink连接重复'}
#{'code':305, 'msg': '公告被人工修改过，不做更新处理'}
#上传云端
def upload_cloud(json_file_path,_dist = 'dev'):
    #处理云端地址
    cloud_url = debug_cloud_url
    if _dist == 'prod':
        cloud_url = prod_cloud_url   
    ner_logger.info(f"开始上传云端 - {json_file_path}  / {cloud_url}")
    
    try:
        # 检查文件是否存在
        if not os.path.exists(json_file_path):
            ner_logger.error(f"文件不存在 - {json_file_path}")
            return False,"文件不存在",""
        
        # 检查文件大小
        if os.path.getsize(json_file_path) == 0:
            ner_logger.error(f"文件为空 - {json_file_path}")
            return False,"文件为空",""
        
        # 打开 JSON 文件并读取内容
        with open(json_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                ner_logger.error(f"文件内容为空 - {json_file_path}")
                return False,"文件内容为空",""
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError as je:
                ner_logger.error(f"JSON格式错误 - {json_file_path}, 错误: {je}")
                return False,f"JSON格式错误: {str(je)}",""
            
            fix_upload_cloud(data)
            # 发送 POST 请求，并将 JSON 数据作为请求体发送
            response = requests.post(cloud_url,  headers=headers,json=data)
            # 检查响应状态码
            if response.status_code == 200: 
                response_data = response.text
                json_data = json.loads(response_data)
                if str(json_data['code']) in ['200']:
                    ner_logger.info(f"上传云端成功 - {json_data}")
                    return True,response_data,"200"
                elif str(json_data['code']) in ['301','302','303','304','305']:
                    ner_logger.info(f"上传云端成功 - {json_data}")
                    return True,response_data,str(json_data['code'])
                else:
                    ner_logger.info(f"上传云端失败 - {json_data}")
                    return False,response_data,""
            else:
                ner_logger.info(f"上传云端失败 - {json_file_path}")
                return False,response.text,""
    except Exception as e:
        ner_logger.error(f"上传云端失败 - {json_file_path}, 错误: {e}")
        import traceback
        ner_logger.error(traceback.format_exc())
        return False,str(e),""
    
# 参数
# l string 必填 连接地址
# c string 必填 公司名称
# t string 必填 全文
# g string 必填 GraduationYear 最大值
def check_cloud(_durl,_companyname,_fulltext,_jie,_dist = 'prod'):
    data = {
        "l": _durl,
        "c": _companyname, 
        "t": _fulltext,
        "g": _jie,
    }
    #处理云端地址
    cloud_url = debug_check_url
    if _dist == 'prod':
        cloud_url = prod_check_url  
    try:
        # 请求
        response = requests.post(cloud_url, data=data)
        # 检查响应状态码
        if response.status_code == 200:  
            response_data = response.json()
            if "code" in response_data and response_data["code"] == 200:
                ner_logger.info(f"云端校验成功可以传递 - {response_data}")
                return True,""
            else:
                ner_logger.info(f"云端校验失败 - {response_data}")
                return False,response_data
    except Exception as e:
        ner_logger.info(f"云端校验发生异常，没有验证成功，跳过！ - {e}")
    #返回
    return True,""


#修复上传的问题
def fix_upload_cloud(data):
    if 'ann' in data:
        json_data = data['ann']
    elif 'cjob' in data:
        json_data = data['cjob']
        #使用全称名称
        json_data['ComShortName'] = json_data['ComName']
        #检查过期日期
        if 'CutDate' in json_data:
            json_data['CutDate'] = fix_data_format_large(json_data['CutDate'])
    else:
        return
    #优化日期
    if 'OnlineStartDate' in json_data:
        json_data['OnlineStartDate'] = fix_data_format(json_data['OnlineStartDate'])
    if 'OnlineEndDate' in json_data:
        json_data['OnlineEndDate'] = fix_data_format(json_data['OnlineEndDate'])
    if 'PublishTime' in json_data:
        json_data['PublishTime'] = fix_data_format(json_data['PublishTime'])

    # ner_logger.info(f"fix_upload_cloud:{json_data['OnlineStartDate']} / {json_data['OnlineEndDate']} / {json_data['PublishTime']}")



#上传云端
def upload_cloud_job(json_file_path,_dist = 'dev',_retry =  '0'):
    #处理云端地址
    retry= 0
    if _retry == '1':
        retry = 1
    cloud_url = debug_job_cloud_url
    if _dist == 'prod':
        cloud_url = prod_job_cloud_url   
    ner_logger.info(f"开始上传云端 - {json_file_path}  / {cloud_url}")
    try:
        # 检查文件是否存在
        if not os.path.exists(json_file_path):
            ner_logger.error(f"文件不存在 - {json_file_path}")
            return False,"文件不存在",""
        
        # 检查文件大小
        if os.path.getsize(json_file_path) == 0:
            ner_logger.error(f"文件为空 - {json_file_path}")
            return False,"文件为空",""
        
        # 打开 JSON 文件并读取内容
        with open(json_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                ner_logger.error(f"文件内容为空 - {json_file_path}")
                return False,"文件内容为空",""
            
            try:
                data = json.loads(content)
            except json.JSONDecodeError as je:
                ner_logger.error(f"JSON格式错误 - {json_file_path}, 错误: {je}")
                return False,f"JSON格式错误: {str(je)}",""
            
            fix_upload_cloud(data) 
            #共有三个参数：(8.26后加了一个retry是重入的，1是重入，0是正常默认，职位名字和地区有一个不同就会有新岗位)
            #参数：
            # comFrom: 职位渠道 固定值 100000
            # fileName: 文件名称，取文档里的FileId即可
            # content: 文件内容json内容
            # 准备表单数据
            form_data = {
                "comFrom": "100000",
                "fileName":  data['cjob']['FileId'],
                "content": json.dumps(data),
                "retry": retry,
            }
            ner_logger.info(f"开始上传云端 - {form_data}")
            print(cloud_url)
            # 发送 POST 请求，并将data作为参数  
            response = requests.post(cloud_url, data=form_data)
            # 检查响应状态码 
            if response.status_code == 200: 
                response_data = response.text
                json_data = json.loads(response_data)
                # print("qqqqqqqqqqq ",str(json_data['code']))
                if str(json_data['code']) in ['200']:
                    return True,response.text,response.status_code  
            #有错误
            ner_logger.info(f"职位上传云端失败 - {json_file_path},{response.text}")
            #返回
            return False,f"未知的错误在upload_cloud_job的165行，{response.text}",""
    except Exception as e:
        import traceback
        traceback.print_exc()
        ner_logger.error(f"职位上传云端失败 - {json_file_path},{e}")
        return False,str(e),""