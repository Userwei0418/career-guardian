import time
import hashlib
import os 
import requests
from urllib.parse import urlencode 
import sys
sys.path.append('../')
import json
from utils import ner_logger
import re
from auto_api.isoftstone_data_proc_api import api_proc_isoftstone
 

headers = {
    "Accept": "application/json, text/plain, */*",
    # 不要手动设置 Content-Length，requests 会自动计算
    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    "Origin": "https://talent.baidu.com",
    "Referer": "https://talent.baidu.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3 Safari/605.1.15",
    # 下面几个头通常浏览器会加入，可以保留或删除
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    "Connection": "keep-alive",
}

# 如果你想精确使用提供的 Cookie 字符串，可以直接放在 headers['Cookie'] 中；
# 也可以把它拆成 dict 放到 cookies 参数里。
cookie_str = ('RT="z=1&dm=baidu.com&si=6ece4843-c53f-43cb-9190-cdeb1e60fc10&ss=mgkm3gti&sl=2&tt=m7'
              '&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=3o9k&ul=3pos&hd=3pp1"; '
              'Hm_lpvt_50e85ccdd6c1e538eb1290bc92327926=1760086734; '
              'Hm_lvt_50e85ccdd6c1e538eb1290bc92327926=1760083124; HMACCOUNT=BABEAB1BF5E31B7B; '
              'H_WISE_SIDS=60279_63144_63325_64314_64650_64695_64814_64817_64866_64840_64909_64913_64965_64988_65005_65003_65120_65141_65140_65137_65190_65203_65246_65255_65143_65273_65315_65322_65367; '
              'BAIDUID=DF45EE91831D9BA2A80B24F2DCE23BB1:FG=1; '
              'BIDUPSID=DF45EE91831D9BA2D6517973C86A9556; H_PS_PSSID=60272_63140_63325_64651_64702_64813_64815_64840_64873_64904_64923_64986_65120_65141_65140_65138_65187_65203_65216_65249_65255_65144_65277_65309_65327_65373_65367; PSTM=1758515092')

headers["Cookie"] = cookie_str


def myProxy():
    #设置请求增加代理
    _ps = getProxy()

    proxies = {
            "http": f"http://{_ps}", 
        }
    ner_logger.info("getProxy:", proxies)
    return proxies
#获取jsonson串
def get_baidu_job_json(url,recruitType,projectType,curPage):

    # 请求体参数
    payload_dict = {
        "IME类型": "application/x-www-form-urlencoded;charset=utf-8",  # 这个是你要求加的字段
        "recruitType": recruitType,  # 社会招聘
        "pageSize": 20,
        "keyWord": "",  # 可以改成搜索关键词，比如 "AI"
        "curPage": curPage,
        "projectType": projectType,  # 若无特定类型可留空
    }
    payload = urlencode(payload_dict)  # 变为 "pageIndex=1&pageSize=10&keyword=&cityId="

 
    # 发送请求
    with requests.Session() as s:
        resp = s.post(url, data=payload, headers=headers, timeout=15, verify=False,proxies=myProxy())
        print("Status:", resp.status_code)
        # 尝试以 json 解析（如果服务端返回 JSON）
        try:
            json = resp.json()
            if json['status'] == 'ok':
                data = json['data']['list']
                total = int(json['data']['total'])
                #获取json 的节点
                return True,data,total
        except Exception:
            ner_logger.info("baidu Text response:", resp.text)
            return False,-1
        

#获取百度临时文件html
def get_baidu_job_html(url,tmp_file):
    # 1. 配置请求头：伪装浏览器，避免被反爬拦截
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://talent.baidu.com/"  # 模拟从百度招聘首页跳转，提升请求合法性
    }

    try: 
        # 2. 发送 GET 请求获取页面内容
        response = requests.get(url, headers=headers, timeout=10, verify=False,proxies=myProxy())
        response.raise_for_status()  # 若状态码非200（如404、500），抛出异常
        response.encoding = response.apparent_encoding  # 自动识别编码，避免乱码
        #清除html里面的jsscript
        full_text = re.sub(r'<script[^>]*?>.*?</script>', '', response.text, flags=re.DOTALL)
        # 输出 HTML 页面，写入文件a.html
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(full_text)
        time.sleep(10)

    except requests.exceptions.RequestException as e:
        print(f"请求失败：{e}")
        return None
    
def transform_job_json(item,recruitType,job_type,channel,target_url,tmp_file,json_file):
    """
    将源JSON转换为目标JSON格式
    
    参数:
        item: 源JSON字典，包含待转换的字段
        
    返回:
        转换后的目标JSON字典
    """
    # 定义字段映射关系
    field_mapping = {
        "announcement_name": "name",
        "publish_time": "publishDate",
        "hd_dept": "bgShortName",
        "hd_loc": "workPlace",
        "hd_job_num": "recruitNum",
        "hd_job_category": "postType"
    }
    # 固定字段值
    fixed_fields = {
        "link": target_url,
        "full_url": target_url,
        "last_url": target_url,
        "file_path": tmp_file,
        "parent_url": "https://talent.baidu.com/static/index.html",
        "channel": channel,
        "job_type": job_type
    }
    
    # 创建目标JSON
    target_json = {}
    
    # 映射源字段到目标字段
    for target_field, source_field in field_mapping.items():
        target_json[target_field] = item.get(source_field, "")
    
    # 添加固定字段
    target_json.update(fixed_fields)
    
    #保存json文件
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(target_json, f, ensure_ascii=False, indent=4) 
        time.sleep(10)

#执行api处理
def api_proc(spider_com,_key, com_info,k,url,_stat):
    if _key == "com_90001":
        api_proc_baidu(spider_com,_key, com_info,k,url,_stat)
    if _key == "com_90002":
        api_proc_isoftstone(spider_com,_key, com_info,k,url,_stat)
    if _key == "com_90003":
        from auto_api.jd_data_proc_api import api_proc_jd
        api_proc_jd(spider_com,_key, com_info,k,url,_stat)
    if _key == "com_90004":
        from auto_api.kingdee_data_proc_api import api_proc_kingdee
        api_proc_kingdee(spider_com,_key, com_info,k,url,_stat)
    if _key == "com_90005":
        from auto_api.picc_data_proc_api import api_proc_picc
        api_proc_picc(spider_com,_key, com_info,k,url,_stat)
    ner_logger.info(f"api_proc_baidu: {_key}, {com_info}, {k}, {url}")
    #默认返回
    return True
#执行api处理
def api_proc_baidu(spider_com,_key, com_info,k,url,_stat):
    recruitType = "SOCIAL"
    job_type= "shezhao"
    projectType = ""
    if k.startswith("shezhao"):
        recruitType = "SOCIAL"
        job_type= "shezhao" 
    elif k.startswith("xiaozhao"):
        recruitType = "GRADUATE"
        job_type= "xiaozhao"
        projectType ="3"
    elif k.startswith("shixi"):
        recruitType = "INTERN"
        job_type= "shixi" 
    #如果method没有则增加
    if not 'method' in _stat:
        _stat["method"] = "cp_full"
    else:
        ner_logger.info("api_proc_baidu method:", _stat["method"])

    #渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    #基数
    total_page = 0
    #curPage 循环1-99
    for curPage in range(1,100):
        flag, json_data,totalcount = get_baidu_job_json(url,recruitType,projectType,curPage)
        if flag:
            #ner_logger.info("baidu json response:", json_data,total_page)
            if total_page == 0:
                #根据总数据和每页数量计算页数
                total_page = int(totalcount / 20) + 1
            #写入临时文件名
            _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
            #输出临时JSON文件路径
            tmp_fname = f'{key_tmp_dir}/index_{_hash}_{curPage}.json'
            with open(tmp_fname,'w',encoding='utf-8') as f: 
                #写入JSON
                json.dump(json_data,f,ensure_ascii=False,indent=4) 
            #完成爬取后跳出
            if curPage > total_page:
                break
            if curPage > 5 and _stat['method'] != "cp_full":
                break
            #对json列表数据进行新换
            for item in json_data:
                jobId = item.get("jobId")
                # 目标 URL（即题目中的百度招聘页面地址）
                _fullurl = f"https://talent.baidu.com/jobs/detail/{recruitType}/{jobId}"  
                #生成临时文件名
                _hash = hashlib.md5(_fullurl.encode("utf-8")).hexdigest()
                tmp_file = os.path.join(key_tmp_dir,f"detail_{_hash}.html")  
                tmp_json_file = os.path.join(key_tmp_dir,f"detail_{_hash}.json")  
                #如果文件存在，则不爬取
                if os.path.exists(tmp_file) and os.path.exists(tmp_json_file):
                    try:
                        # 更新文件的修改时间
                        current_time = time.time()
                        # 修改文件的访问时间和修改时间为当前时间
                        os.utime(tmp_file, (current_time, current_time))
                        os.utime(tmp_json_file, (current_time, current_time))
                        ner_logger.info(f"文件 {tmp_json_file} 的修改时间已更新为当前时间")
                    except Exception as e:
                        ner_logger.error(f"更新文件 {tmp_json_file} 的修改时间时出错：{str(e)}")
                    continue
                #执行json的转换
                transform_job_json(item,recruitType,job_type,_key,_fullurl,tmp_file,tmp_json_file)
                #保存html
                get_baidu_job_html(_fullurl,tmp_file)
                time.sleep(30)
        time.sleep(30)
    #返回
    return True

def getProxy(tryTimes = 0):
    '''获取代理'''
    if tryTimes >= 3:
        return ''
    params = {"channel":'yupao', "env": 1}
    proxy = ''
    try:
        import requests
        import time
        ret = requests.post('http://121.36.63.42:6868/getproxy', params=params)
        if ret.status_code == 200:
            rescontent = json.loads(ret.content.decode())
            if rescontent.get("code") == 200:
                proxy = rescontent.get('data').get('proxy')
            else:
                proxy = ''
            if proxy == '':
                tryTimes = tryTimes + 1
                time.sleep(1)
                return getProxy(tryTimes)
        ret.close()
        ner_logger.info(f"获取代理成功:{proxy}")
        return proxy
    except:
        ner_logger.info(f"获取代理失败")
        time.sleep(1)
        tryTimes = tryTimes + 1
        return getProxy(tryTimes)