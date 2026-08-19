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
import asyncio
from playwright.sync_api import sync_playwright
import threading
from concurrent.futures import ThreadPoolExecutor

headers = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "application/json;charset=UTF-8",
    "Host": "career.isoftstone.com",
    "Origin": "https://career.isoftstone.com",
    "Pragma": "no-cache",
    "Referer": "https://career.isoftstone.com/talent/htmls/shehuizhaopin/index.html",
    "Sec-Ch-Ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}

# Cookie可能会变化，这里提供一个示例结构
cookie_str = ('Hm_lvt_e5e1889ee1cef86df8447e0c983cb5b5=1760151941; '
              'Hm_lvt_c31aaec3450321c4e3d4fd4f7509f181=1760151941; '
              'dreamer-cms-s=c872e558-050d-45d8-bd3d-c97534fc3757')

headers["Cookie"] = cookie_str


def get_isoftstone_job_json(url, recruitType, curPage):
    """
    获取软通动力招聘信息的JSON数据
    
    参数:
        url: 请求地址
        recruitType: 招聘类型
        curPage: 当前页码
        
    返回:
        (flag, data, total_count) 元组
    """
    # 计算skipCount
    skip_count = (curPage - 1) * 50
    if recruitType == "1":
        payload = {
            "workCity": "",
            "jobTypeId": "0",
            "keyWord": "",
            "maxcount": 100,
            "page": curPage,
            "recruitType": 1
        }
    elif recruitType == "2":
        payload = {
            "workCity": "",
            "jobTypeId": "0",
            "keyWord": "",
            "skipCount": skip_count,
            "pageCount": 100,
            "recruitType": 2
        }

    # 发送请求
    with requests.Session() as s:
        resp = s.post(url, json=payload, headers=headers, timeout=15)
        print("Status:", resp.status_code)
        # 尝试以 json 解析（如果服务端返回 JSON）
        try:
            if resp.status_code == 200:
                json_data = resp.json()
                # 检查返回数据的格式，适配不同的API端点
                if 'code' in json_data:
                    # 适配 /job/all API端点格式
                    if json_data['code'] == 0:
                        data = json_data['data']['list']
                        total = int(json_data['data']['count'])
                        # 获取json 的节点
                        return True, data, total
                elif 'results' in json_data:
                    # 适配 /campus/all API端点格式
                    data = json_data['results']
                    total = int(json_data['count'])
                    return True, data, total
                else:
                    # 未知格式
                    ner_logger.info("Unknown JSON format: %s", json_data)
                    return False, [], 0
            else:
                ner_logger.info("Request failed with status code: %s, response: %s", resp.status_code, resp.text)
                return False, [], 0
        except Exception as e:
            ner_logger.info("JSON decode error: %s, response: %s", str(e), resp.text)
            return False, [], 0


def get_isoftstone_job_html(url, tmp_file):
    """
    获取软通动力招聘详情页的HTML内容
    
    参数:
        url: 招聘详情页URL
        tmp_file: 保存文件路径
    """
    try:
        # 定义获取页面内容的函数
        def fetch_page_content():
            with sync_playwright() as p:
                # 启动浏览器
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # 设置请求头
                page.set_extra_http_headers({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": "https://career.isoftstone.com/talent/htmls/shehuizhaopin/index.html"
                })
                
                # 访问页面
                page.goto(url)
                
                # 等待页面加载完成，包括JavaScript渲染的内容
                page.wait_for_load_state("networkidle")
                
                # 额外等待确保动态内容加载完成
                page.wait_for_timeout(5000)
                
                # 获取完整的页面内容
                full_text = page.content()
                
                # 关闭浏览器
                browser.close()
                
                return full_text
        
        # 在线程池中运行函数以避免事件循环冲突
        with ThreadPoolExecutor() as executor:
            future = executor.submit(fetch_page_content)
            full_text = future.result()
        
        # 清除html里面的jsscript
        full_text = re.sub(r'<script[^>]*?>.*?</script>', '', full_text, flags=re.DOTALL)
        
        # 输出 HTML 页面，写入文件
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(full_text)
            
    except Exception as e:
        print(f"请求失败：{e}")
        return None


def transform_job_json(item, recruitType, job_type, channel, target_url, tmp_file, json_file):
    """
    将源JSON转换为目标JSON格式
    
    参数:
        item: 源JSON字典，包含待转换的字段
        
    返回:
        转换后的目标JSON字典
    """
    # 定义字段映射关系
    field_mapping = {
        "announcement_name": "job_name",
        "publish_time": "public_time",
        "hd_dept": "",  # 软通动力数据中没有明确部门信息
        "hd_loc": "work_city",
        "hd_job_num": "count",
        "hd_job_category": ""  # 软通动力数据中没有明确分类信息
    }
    
    # 检查是否是校招API格式
    if "name" in item and "address_detail" in item:
        # 校招API格式字段映射
        field_mapping = {
            "announcement_name": "name",
            "publish_time": "publish_date",
            "hd_dept": "",  # 软通动力数据中没有明确部门信息
            "hd_loc": "address_detail",
            "hd_job_num": "",  # 校招数据中没有明确数量
            "hd_job_category": ""  # 软通动力数据中没有明确分类信息
        }
    
    # 固定字段值
    fixed_fields = {
        "link": target_url,
        "full_url": target_url,
        "last_url": target_url,
        "file_path": tmp_file,
        "parent_url": "https://career.isoftstone.com/talent/htmls/shehuizhaopin/index.html",
        "channel": channel,
        "job_type": job_type
    }
    
    # 创建目标JSON
    target_json = {}
    
    # 映射源字段到目标字段
    for target_field, source_field in field_mapping.items():
        if source_field:  # 如果源字段不为空
            value = item.get(source_field, "")
            # 特别处理 hd_job_num 字段，确保数字类型转换为字符串
            if target_field == "hd_job_num" and isinstance(value, int):
                value = str(value)
            target_json[target_field] = value
        else:
            target_json[target_field] = ""
    
    # 添加固定字段
    target_json.update(fixed_fields)
    
    # 保存json文件
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(target_json, f, ensure_ascii=False, indent=4)
        time.sleep(1)


def api_proc_isoftstone(spider_com, _key, com_info, k, url, _stat):
    """
    处理软通动力招聘数据
    
    参数:
        spider_com: 爬虫组件
        _key: 关键字
        com_info: 公司信息
        k: 分类标识
        url: 请求地址
        _stat: 状态信息
    """
    # 如果URL为空，则使用默认的软通动力API地址
    if not url or url == "":
        url = "https://career.isoftstone.com/job/all"

    recruitType = "2"  # 社招
    job_type = "shezhao"
    
    if k.startswith("shezhao"):
        recruitType = "2"
        job_type = "shezhao"
    elif k.startswith("xiaozhao"):
        recruitType = "1"
        job_type = "xiaozhao"
    
    ner_logger.info("开始处理isoftstone数据, k: %s, url: %s, job_type: %s", k, url, job_type)
    # 渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    ner_logger.info("临时目录: %s", key_tmp_dir)
    
    # 总页数
    total_page = 0
    
    # curPage 循环1-99
    for curPage in range(1, 100):
        flag, json_data, totalcount = get_isoftstone_job_json(url, recruitType, curPage)
        if flag:
            if total_page == 0:
                # 根据总数据和每页数量计算页数
                total_page = int(totalcount / 100) + 1  # 每页100条数据
            ner_logger.info("总页数: %s", total_page)
                
            # 完成爬取后跳出
            if curPage >= total_page:
                ner_logger.info("已达到总页数，结束分页爬取")
                break
            if curPage > 5 and _stat.get('method', '') != "cp_full":
                ner_logger.info("已爬取5页且不是完整模式，结束分页爬取")
                break
                
            # 对json列表数据进行处理
            for i, item in enumerate(json_data):
                job_id = item.get("id")
                # 目标 URL（软通动力招聘详情页面地址）
                # 根据recruitType确定详情页URL格式
                if recruitType == "2":
                    # 社招详情页URL格式
                    _fullurl = f"https://career.isoftstone.com/talent/htmls/shezhaozhiweixiangqing/index.html?id={job_id}&recruitType={recruitType}"
                else:
                    # 校招详情页可能使用不同的URL格式，这里暂时使用默认格式
                    _fullurl = f"https://career.isoftstone.com/talent/htmls/xiaozhaozhiweixiangqing/index.html??id={job_id}&recruitType={recruitType}"
                
                # 生成临时文件名，包含职位ID以确保相同职位名称也能区分
                _hash = hashlib.md5(_fullurl.encode("utf-8")).hexdigest()
                tmp_file = os.path.join(key_tmp_dir, f"detail_{job_id}_{_hash}.html")
                tmp_json_file = os.path.join(key_tmp_dir, f"detail_{job_id}_{_hash}.json")
                
                ner_logger.info("正在处理第 %s 页第 %s 个职位", curPage, i+1)
                
                # 如果文件存在，则不爬取
                if os.path.exists(tmp_file) and os.path.exists(tmp_json_file):
                    try:
                        # 更新文件的修改时间
                        current_time = time.time()
                        # 修改文件的访问时间和修改时间为当前时间
                        os.utime(tmp_file, (current_time, current_time))
                        os.utime(tmp_json_file, (current_time, current_time))
                    except Exception as e:
                        ner_logger.error(f"更新文件 {tmp_json_file} 的修改时间时出错：{str(e)}")
                    continue
                    
                # 执行json的转换
                transform_job_json(item, recruitType, job_type, _key, _fullurl, tmp_file, tmp_json_file)
                # 等待一段时间确保页面加载完成
                time.sleep(1)
                # 保存html
                get_isoftstone_job_html(_fullurl, tmp_file)
                time.sleep(1)
        else:
            ner_logger.info("Failed to fetch data for page %s", curPage)
            # 如果第一页就失败了，直接返回
            if curPage == 1:
                ner_logger.error("第一页数据获取失败，终止处理")
                return False
        time.sleep(1)
        
    ner_logger.info("isoftstone数据处理完成")
    # 返回
    return True