import time
from functools import partial
import hashlib
import os
import json
import requests

from utils import ner_logger



def  xingye_proc(spider_com,page,_key, com_info,k,url,_stat):
    #部分参数 
    job_type= "shezhao" 
    if k.startswith("shezhao"): 
        job_type= "shezhao" 
    elif k.startswith("xiaozhao"): 
        job_type= "xiaozhao" 
    elif k.startswith("shixi"): 
        job_type= "shixi" 
    #page上监控response函数
    # 用partial绑定额外参数，注意参数顺序
    wrapped_handler = partial(response_handler,spider_com,page,_key, com_info,k,url,_stat,job_type)
    page.on('response', wrapped_handler)
    #打开url
    response = page.goto(url, timeout=10000)
    time.sleep(10)
    #page量
    _page_count = 3
    if 'method' in _stat and _stat['method'] == "cp_full":
        _page_count = 100 

    #进行翻页
    for i in range(1,_page_count):
        # 定位下一页按钮并点击
        next_page_button = page.get_by_title("下一页")
        #如何判断按钮是否可以点击 
        if next_page_button and next_page_button.is_enabled():  
            ner_logger.info("兴业银行，翻页第%d页"%(i))
            # 检查 aria-disabled 属性
            aria_disabled = next_page_button.get_attribute('aria-disabled')
            if aria_disabled != 'true':
                next_page_button.click()  
            time.sleep(30)
        else:
            ner_logger.info("兴业银行，没有下一页了")
            break
# 注意参数顺序：先固定参数，后response
def response_handler(spider_com,page,_key, com_info,k,url,_stat,job_type,response):
    #如果url 是这个，则拦截获取内容：https://job.cib.com.cn/ersApi/recruitposition/portalPage
    if response.url.startswith("https://job.cib.com.cn/ersApi/recruitposition/portalPage"):
        _data_json = response.json()
        #获取message == '成功'
        if _data_json['message'] == '成功':
            _data = _data_json['data']
            _total = _data['total']
            _list = _data['list']
            #获取list
            for _item in _list:
                xingye_json(_item,spider_com,page,_key, com_info,k,url,_stat,job_type)
            #返回
#生成json转换
def xingye_json(original_data,spider_com,page,_key, com_info,k,url,_stat,job_type):
    ner_logger.info("兴业银行，开始生成json")

    #url https://job.cib.com.cn/portal/#/positionDetails/842094467529285632
    _fullurl = f"https://job.cib.com.cn/portal/#/positionDetails/{original_data['positionId']}"
    #生成临时文件名
    #渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    _hash = hashlib.md5(_fullurl.encode("utf-8")).hexdigest()
    tmp_file = os.path.join(key_tmp_dir,f"detail_{_hash}.html")  
    tmp_json_file = os.path.join(key_tmp_dir,f"detail_{_hash}.json")  
  
    _context_outtext = generate_html(original_data)
    # 输出 HTML 页面，写入文件a.html
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(_context_outtext) 
    # 转换映射
    converted_data = {
        "announcement_name": original_data["positionName"],
        "publish_time": original_data["publishTime"].split()[0],  # 提取日期部分
        "link": _fullurl,
        "hd_dept": original_data["departmentDesc"],
        "hd_loc": original_data["positionAddr"],
        "hd_job_num": str(original_data["recruitingNum"]) if original_data["recruitingNum"] != -1 else "",
        "hd_job_category": "",  # 根据职位性质推断
        "full_url": _fullurl,
        "last_url": _fullurl,
        "file_path": tmp_file,
        "parent_url": f"https://job.cib.com.cn",
        "channel": "com_91000",
        "job_type": job_type
    }
    #保存json文件
    with open(tmp_json_file, 'w', encoding='utf-8') as f:
        json.dump(converted_data, f, ensure_ascii=False, indent=4)  


    #ner_logger.info(converted_data)

#生成html内容
def generate_html(data):
    htmllist = []
    #职位名
    htmllist.append(f"<div> 职位名 {data['positionName']}")
    #地点
    htmllist.append(f"<div> 地点 {data['positionAddr']}")
    #发布机构
    htmllist.append(f"<div> 发布机构 {data['firstBusinessUnitDesc']}")
    #部门
    htmllist.append(f"<div> 部门 {data['departmentDesc']}")
    #发布日期
    htmllist.append(f"<div> 发布日期 {data['publishTime']}")
    #过期日期
    htmllist.append(f"<div> 过期日期 {data['expiryDate']}")
    #招聘类型recruitType 
    if data['recruitType'] == 'CR':
        htmllist.append(f"<div> 招聘类型： 校招")
    elif data['recruitType'] == 'TR':
        htmllist.append(f"<div> 招聘类型： 实习")
    else:
        htmllist.append(f"<div> 招聘类型： 社招")
    #招聘人数，recruitingNum如果等于-1，则不显示
    if data['recruitingNum'] != -1:
        htmllist.append(f"<div> 招聘人数： {data['recruitingNum']}")
    else:
        htmllist.append(f"<div> 招聘人数： 若干")

    htmllist.append(f"<div> 专业要求 \n{data['majorRequirment']}")
    htmllist.append(f"<div> 工作职责 \n{data['jobDuty']}")
    htmllist.append(f"<div> 任职要求 \n{data['positionRequirment']}")

    return "\n".join(htmllist)
