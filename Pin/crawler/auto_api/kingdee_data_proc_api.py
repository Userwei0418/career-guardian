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
from playwright.sync_api import sync_playwright
import threading
from concurrent.futures import ThreadPoolExecutor

headers = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Referer": "https://campus.51job.com/kingdee/",
    "Sec-Ch-Ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "script",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
}


def get_kingdee_job_data(url):
    """
    获取金蝶招聘数据
    
    参数:
        url: 请求地址
        
    返回:
        (flag, data) 元组
    """
    try:
        # 发送请求
        with requests.Session() as s:
            resp = s.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                # 获取响应内容
                js_content = resp.text
                
                # 提取职位数据（从js文件中提取数组部分）
                # 查找类似 var jobs = [ ... ] 或 jobs = [ ... ] 的结构
                import re
                jobs_match = re.search(r'(?:var\s+)?jobs\s*=\s*(\[.*?\]);?', js_content, re.DOTALL)
                if jobs_match:
                    jobs_str = jobs_match.group(1)
                    # 安全地解析JSON数组
                    jobs_data = json.loads(jobs_str)
                    return True, jobs_data
                else:
                    # 尝试查找任何数组结构
                    array_match = re.search(r'(\[.*\])', js_content, re.DOTALL)
                    if array_match:
                        array_str = array_match.group(1)
                        array_data = json.loads(array_str)
                        return True, array_data
                    else:
                        ner_logger.info("未能从JS文件中提取职位数据")
                        return False, []
            else:
                ner_logger.info("请求失败，状态码: %s", resp.status_code)
                return False, []
    except Exception as e:
        ner_logger.info("请求金蝶招聘数据时出错: %s", str(e))
        return False, []


def transform_job_json(item, job_type, channel, tmp_file, json_file):
    """
    将源JSON转换为目标JSON格式
    
    参数:
        item: 源数据字典
        job_type: 职位类型
        channel: 渠道
        tmp_file: 临时文件路径
        json_file: JSON文件路径
    """
    try:
        # 定义字段映射关系
        field_mapping = {
            "announcement_name": "jobname",     # 职位名称
            "publish_time": "",                 # 发布时间（金蝶数据中没有）
            "hd_dept": "organization",          # 部门
            "hd_loc": "city1",                  # 工作地点
            "hd_job_num": "",                   # 招聘人数（金蝶数据中没有）
            "hd_job_category": "type1"          # 职位类别
        }
        
        # 固定字段值
        # 使用返回数据中的link字段作为详情页链接
        detail_url = item.get("link", "")
        if not detail_url:
            # 如果没有link字段，则使用jobid构造默认链接
            job_id = item.get("jobid", "")
            if job_id:
                detail_url = f"https://campus.51job.com/kingdee/job.html?jobid={job_id}"
            else:
                detail_url = "https://campus.51job.com/kingdee/"
        
        fixed_fields = {
            "link": detail_url,
            "full_url": detail_url,
            "last_url": detail_url,
            "file_path": tmp_file,
            "parent_url": "https://campus.51job.com/kingdee/",
            "channel": channel,
            "job_type": job_type
        }
        
        # 创建目标JSON
        target_json = {}
        
        # 映射源字段到目标字段
        for target_field, source_field in field_mapping.items():
            if source_field:  # 如果源字段不为空
                target_json[target_field] = item.get(source_field, "")
            else:
                target_json[target_field] = ""
        
        # 添加固定字段
        target_json.update(fixed_fields)
        
        # 保存json文件
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(target_json, f, ensure_ascii=False, indent=4)
            
        return True
    except Exception as e:
        ner_logger.error("转换职位数据时出错: %s", str(e))
        return False


def generate_kingdee_job_html(item, tmp_file):
    """
    生成金蝶招聘详情页的HTML内容
    
    参数:
        item: 职位信息字典
        tmp_file: 保存文件路径
    """
    try:
        # 获取职位信息
        job_name = item.get("jobname", "")
        organization = item.get("organization", "")
        city = item.get("city1", "")
        job_type = item.get("type1", "")
        job_id = item.get("jobid", "")
        address = item.get("address", "")
        job_description = item.get("info", "").replace("\r\n", "<br>").replace("\n", "<br>")
        job_link = item.get("link", "")
        mobile_link = item.get("linkM", "")
        
        # 创建HTML内容
        html_content = f'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>金蝶招聘 - {job_name}</title>
    <style>
        body {{
            font-family: "Microsoft YaHei", Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background-color: #fff;
        }}
        .header {{
            border-bottom: 1px solid #eee;
            padding-bottom: 20px;
            margin-bottom: 20px;
        }}
        .job-title {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
        }}
        .job-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
            margin: 15px 0;
        }}
        .meta-item {{
            display: flex;
            align-items: center;
        }}
        .meta-label {{
            font-weight: bold;
            color: #666;
            margin-right: 5px;
        }}
        .section {{
            margin: 25px 0;
        }}
        .section-title {{
            font-size: 20px;
            color: #333;
            border-left: 4px solid #007acc;
            padding-left: 10px;
            margin-bottom: 15px;
        }}
        .job-content {{
            line-height: 1.8;
            color: #555;
        }}
        .apply-button {{
            display: inline-block;
            padding: 12px 30px;
            background-color: #007acc;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
            margin-top: 20px;
        }}
        .apply-button:hover {{
            background-color: #005fa3;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="job-title">{job_name}</div>
            <div class="job-meta">
                <div class="meta-item">
                    <span class="meta-label">所属组织:</span>
                    <span>{organization}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">工作地点:</span>
                    <span>{city}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">职位类别:</span>
                    <span>{job_type}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">职位ID:</span>
                    <span>{job_id}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">工作地址:</span>
                    <span>{address}</span>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">职位描述</h2>
            <div class="job-content">
                {job_description if job_description else "暂无职位描述"}
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">应聘方式</h2>
            <div class="job-content">
                <p>请点击以下按钮投递简历：</p>
                <a href="{job_link}" class="apply-button" target="_blank">立即申请</a>
                <p>或者访问移动端链接：<a href="{mobile_link}" target="_blank">{mobile_link}</a></p>
            </div>
        </div>
        
        <div class="footer">
            <p>版权 © 金蝶国际软件集团有限公司</p>
            <p>未经授权不得转载本网站之所有招聘信息及作品</p>
        </div>
    </div>
</body>
</html>
'''
        
        # 输出 HTML 页面，写入文件
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        return True
    except Exception as e:
        ner_logger.error("生成金蝶招聘详情页失败: %s", str(e))
        return False


def api_proc_kingdee(spider_com, _key, com_info, k, url, _stat):
    """
    处理金蝶招聘数据
    
    参数:
        spider_com: 爬虫组件
        _key: 关键字
        com_info: 公司信息
        k: 分类标识
        url: 请求地址
        _stat: 状态信息
    """
    ner_logger.info("开始处理金蝶招聘数据, k: %s, url: %s", k, url)
    
    # 如果URL为空，则使用默认的金蝶API地址
    if not url or url == "":
        url = "https://campus.51job.com/kingdee/js/jobs.js"

    job_type = "xiaozhao"  # 默认为校招
    
    # 渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    ner_logger.info("临时目录: %s", key_tmp_dir)
    
    # 获取金蝶招聘数据
    flag, job_data = get_kingdee_job_data(url)
    if flag and job_data:
        ner_logger.info("金蝶招聘数据获取成功，共 %s 条职位", len(job_data))
        
        # 写入临时文件名
        _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        # 输出临时JSON文件路径
        tmp_fname = f'{key_tmp_dir}/index_{_hash}_1.json'
        with open(tmp_fname, 'w', encoding='utf-8') as f:
            # 写入JSON
            json.dump(job_data, f, ensure_ascii=False, indent=4)
        
        # 处理每条职位数据
        ner_logger.info("开始处理 %s 条职位数据", len(job_data))
        for i, item in enumerate(job_data):
            try:
                job_id = item.get("jobid", f"job_{i}")
                job_name = item.get("jobname", "")
                
                ner_logger.info("正在处理第 %s 条数据, 职位ID: %s, 职位名称: %s", i+1, job_id, job_name)
                
                # 使用返回数据中的link字段作为详情页URL
                _fullurl = item.get("link", "")
                if not _fullurl:
                    # 如果没有link字段，则使用jobid构造默认链接
                    if job_id:
                        _fullurl = f"https://campus.51job.com/kingdee/job.html?jobid={job_id}"
                    else:
                        _fullurl = "https://campus.51job.com/kingdee/"
                
                # 生成临时文件名，包含职位ID以确保相同职位名称也能区分
                _hash = hashlib.md5(_fullurl.encode("utf-8")).hexdigest()
                tmp_file = os.path.join(key_tmp_dir, f"detail_{job_id}_{_hash}.html")
                tmp_json_file = os.path.join(key_tmp_dir, f"detail_{job_id}_{_hash}.json")
                
                # 如果文件存在，则不爬取
                if os.path.exists(tmp_file) and os.path.exists(tmp_json_file):
                    try:
                        # 更新文件的修改时间
                        current_time = time.time()
                        # 修改文件的访问时间和修改时间为当前时间
                        os.utime(tmp_file, (current_time, current_time))
                        os.utime(tmp_json_file, (current_time, current_time))
                        ner_logger.info("文件 %s 的修改时间已更新为当前时间", tmp_json_file)
                    except Exception as e:
                        ner_logger.error("更新文件 %s 的修改时间时出错: %s", tmp_json_file, str(e))
                    continue
                
                # 执行json的转换
                if transform_job_json(item, job_type, _key, tmp_file, tmp_json_file):
                    # 生成html
                    if generate_kingdee_job_html(item, tmp_file):
                        ner_logger.info("完成处理第 %s 条数据", i+1)
                    else:
                        ner_logger.error("生成第 %s 条数据HTML失败", i+1)
                else:
                    ner_logger.error("转换第 %s 条数据失败", i+1)
                
                # 添加延时，避免请求过于频繁
                time.sleep(1)
                    
            except Exception as e:
                ner_logger.error("处理第 %s 条数据时出错: %s", i+1, str(e))
                continue
                
        ner_logger.info("金蝶招聘数据处理完成")
        return True
    else:
        ner_logger.error("获取金蝶招聘数据失败")
        return False