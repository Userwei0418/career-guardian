import time
import hashlib
import os
import requests
import sys
sys.path.append('../')
import json
from utils import ner_logger


headers = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "connection": "keep-alive",
    "content-type": "application/json; charset=UTF-8",
    "origin": "https://picc.zhiye.com",
    "referer": "https://picc.zhiye.com/custom/social?hideAll=true&ky=&c1=&c2=&d=&c=",
    "sec-ch-ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "x-requested-with": "XMLHttpRequest"
}


def get_picc_job_data(url, page_index=0, page_size=10):
    """
    获取中国人保招聘数据
    
    参数:
        url: 请求地址
        page_index: 页码
        page_size: 每页数量
        
    返回:
        (flag, data, count) 元组
    """
    try:
        # 请求体参数
        payload = {
            "Category": ["1"],
            "SpecialType": 0,
            "PageIndex": str(page_index),
            "PageSize": page_size,
            "DisplayFields": [
                "Id", "HeadCount", "JobAdId", "JobAdName", "Kind", "LocNames", "Org", 
                "PostDate", "EndTime", "Salary", "ClassificationOne", "ClassificationTwo",
                "Duty", "Require", "Degree", "YearsOfWorking", "Category"
            ]
        }
        
        # 发送请求
        with requests.Session() as s:
            resp = s.post(url, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("Code") == 200:
                    data = result.get("Data", [])
                    count = result.get("Count", 0)
                    return True, data, count
                else:
                    ner_logger.error("中国人保招聘数据接口返回错误码: %s", result.get("Code"))
                    return False, [], 0
            else:
                ner_logger.error("请求中国人保招聘数据失败，状态码: %s", resp.status_code)
                return False, [], 0
    except Exception as e:
        ner_logger.error("请求中国人保招聘数据时出错: %s", str(e))
        return False, [], 0


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
            "announcement_name": "JobAdName",       # 职位名称
            "publish_time": "PostDate",             # 发布时间
            "hd_dept": "Org",                       # 部门
            "hd_loc": "LocNames",                   # 工作地点 (注意这是数组)
            "hd_job_num": "HeadCount",              # 招聘人数
            "hd_job_category": "Kind"               # 职位类别
        }
        
        # 根据职位类型设置URL和父URL
        if job_type == "xiaozhao":
            detail_url = "https://picc.zhiye.com/custom/campus?hideAll=true&ky=&c1=&c2=&d=&c="
            parent_url = "https://picc.zhiye.com/custom/campus"
        elif job_type == "shixi":
            detail_url = "https://picc.zhiye.com/custom/shixi?hideAll=true"
            parent_url = "https://picc.zhiye.com/custom/shixi"
        else:  # 默认为社招
            detail_url = "https://picc.zhiye.com/custom/social?hideAll=true&ky=&c1=&c2=&d=&c="
            parent_url = "https://picc.zhiye.com/custom/social"
        
        # 固定字段值
        fixed_fields = {
            "link": detail_url,
            "full_url": detail_url,
            "last_url": detail_url,
            "file_path": tmp_file,
            "parent_url": parent_url,
            "channel": channel,
            "job_type": job_type
        }
        
        # 创建目标JSON
        target_json = {}
        
        # 映射源字段到目标字段
        for target_field, source_field in field_mapping.items():
            value = item.get(source_field, "")
            # 特殊处理LocNames字段，它是一个数组
            if source_field == "LocNames" and isinstance(value, list):
                value = ", ".join(value)
            # 特殊处理HeadCount字段，确保它是字符串类型
            if source_field == "HeadCount":
                value = str(value)
            target_json[target_field] = value
        
        # 添加固定字段
        target_json.update(fixed_fields)
        
        # 保存json文件
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(target_json, f, ensure_ascii=False, indent=4)
            
        return True
    except Exception as e:
        ner_logger.error("转换职位数据时出错: %s", str(e))
        return False


def generate_picc_job_html(item, tmp_file, job_type="shezhao"):
    """
    生成中国人保招聘详情页的HTML内容
    
    参数:
        item: 职位信息字典
        tmp_file: 保存文件路径
        job_type: 职位类型 (shezhao, xiaozhao, shixi)
    """
    try:
        # 获取职位信息
        job_ad_name = item.get("JobAdName", "")
        org = item.get("Org", "")
        loc_names = item.get("LocNames", [])
        # 将工作地点数组转换为字符串
        if isinstance(loc_names, list):
            loc_names_str = ", ".join(loc_names)
        else:
            loc_names_str = str(loc_names)
        head_count = item.get("HeadCount", "")
        kind = item.get("Kind", "")
        post_date = item.get("PostDate", "")
        end_time = item.get("EndTime", "")
        salary = item.get("Salary", "")
        classification_one = item.get("ClassificationOne", "")
        classification_two = item.get("ClassificationTwo", "")
        duty = item.get("Duty", "").replace("\r\n", "<br>").replace("\n", "<br>")
        require = item.get("Require", "").replace("\r\n", "<br>").replace("\n", "<br>")
        degree = item.get("Degree", "")
        years_of_working = item.get("YearsOfWorking", "")
        category = item.get("Category", "")
        job_id = item.get("JobAdId", "")
        
        # 根据职位类型设置标题和申请链接
        if job_type == "xiaozhao":
            title_prefix = "中国人保校园招聘"
            apply_url = "https://picc.zhiye.com/custom/campus?hideAll=true&ky=&c1=&c2=&d=&c="
            apply_text = "前往中国人保官方校园招聘页面"
        elif job_type == "shixi":
            title_prefix = "中国人保实习招聘"
            apply_url = "https://picc.zhiye.com/custom/shixi?hideAll=true"
            apply_text = "前往中国人保官方实习招聘页面"
        else:  # 默认为社招
            title_prefix = "中国人保招聘"
            apply_url = "https://picc.zhiye.com/custom/social?hideAll=true&ky=&c1=&c2=&d=&c="
            apply_text = "前往中国人保官方招聘页面"
        
        # 创建HTML内容
        html_content = f'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_prefix} - {job_ad_name}</title>
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
            border-left: 4px solid #c60000;
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
            background-color: #c60000;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
            margin-top: 20px;
        }}
        .apply-button:hover {{
            background-color: #a00000;
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
            <div class="job-title">{job_ad_name}</div>
            <div class="job-meta">
                <div class="meta-item">
                    <span class="meta-label">所属机构:</span>
                    <span>{org}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">工作地点:</span>
                    <span>{loc_names_str}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">招聘人数:</span>
                    <span>{head_count}人</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">职位类别:</span>
                    <span>{kind}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">发布日期:</span>
                    <span>{post_date}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">截止日期:</span>
                    <span>{end_time}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">薪资范围:</span>
                    <span>{salary}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">一级分类:</span>
                    <span>{classification_one}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">二级分类:</span>
                    <span>{classification_two}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">招聘类型:</span>
                    <span>{category}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">学历要求:</span>
                    <span>{degree}</span>
                </div>
                <div class="meta-item">
                    <span class="meta-label">工作经验:</span>
                    <span>{years_of_working}</span>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">岗位职责</h2>
            <div class="job-content">
                {duty if duty else "暂无岗位职责信息"}
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">任职要求</h2>
            <div class="job-content">
                {require if require else "暂无任职要求信息"}
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">应聘方式</h2>
            <div class="job-content">
                <p>请点击以下按钮{apply_text}投递简历：</p>
                <a href="{apply_url}" class="apply-button" target="_blank">立即申请</a>
            </div>
        </div>
        
        <div class="footer">
            <p>版权 © 中国人民保险集团股份有限公司</p>
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
        ner_logger.error("生成中国人保招聘详情页失败: %s", str(e))
        return False


def get_picc_campus_job_data(url, page_index=0, page_size=10):
    """
    获取中国人保校园招聘数据
    
    参数:
        url: 请求地址
        page_index: 页码
        page_size: 每页数量
        
    返回:
        (flag, data, count) 元组
    """
    try:
        # 请求体参数
        payload = {
            "Category": ["2"],
            "SpecialType": 0,
            "PageIndex": str(page_index),
            "PageSize": page_size,
            "DisplayFields": [
                "Id", "HeadCount", "JobAdId", "JobAdName", "Kind", "LocNames", "Org", 
                "PostDate", "EndTime", "Salary", "ClassificationOne", "ClassificationTwo",
                "Duty", "Require", "Degree", "YearsOfWorking", "Category"
            ]
        }
        
        # 更新请求头中的referer为校园招聘页面
        campus_headers = headers.copy()
        campus_headers["referer"] = "https://picc.zhiye.com/custom/campus?hideAll=true&ky=&c1=&c2=&d=&c="
        
        # 发送请求
        with requests.Session() as s:
            resp = s.post(url, json=payload, headers=campus_headers, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("Code") == 200:
                    data = result.get("Data", [])
                    count = result.get("Count", 0)
                    return True, data, count
                else:
                    ner_logger.error("中国人保校园招聘数据接口返回错误码: %s", result.get("Code"))
                    return False, [], 0
            else:
                ner_logger.error("请求中国人保校园招聘数据失败，状态码: %s", resp.status_code)
                return False, [], 0
    except Exception as e:
        ner_logger.error("请求中国人保校园招聘数据时出错: %s", str(e))
        return False, [], 0


def transform_campus_job_json(item, job_type, channel, tmp_file, json_file):
    """
    将校园招聘信息源JSON转换为目标JSON格式（已废弃，使用transform_job_json替代）
    """
    return transform_job_json(item, job_type, channel, tmp_file, json_file)


def generate_picc_campus_job_html(item, tmp_file):
    """
    生成中国人保校园招聘详情页的HTML内容（已废弃，使用generate_picc_job_html替代）
    """
    return generate_picc_job_html(item, tmp_file, "xiaozhao")


def get_picc_internship_job_data(url, page_index=0, page_size=10):
    """
    获取中国人保实习招聘数据
    
    参数:
        url: 请求地址
        page_index: 页码
        page_size: 每页数量
        
    返回:
        (flag, data, count) 元组
    """
    try:
        # 请求体参数
        payload = {
            "Category": ["3"],
            "SpecialType": 0,
            "PageIndex": str(page_index),
            "PageSize": page_size,
            "DisplayFields": [
                "Id", "HeadCount", "JobAdId", "JobAdName", "Kind", "LocNames", "Org", 
                "PostDate", "EndTime", "Salary", "ClassificationOne", "ClassificationTwo",
                "Duty", "Require", "Degree", "YearsOfWorking", "Category"
            ]
        }
        
        # 更新请求头中的referer为实习招聘页面
        internship_headers = headers.copy()
        internship_headers["referer"] = "https://picc.zhiye.com/custom/shixi?hideAll=true"
        
        # 发送请求
        with requests.Session() as s:
            resp = s.post(url, json=payload, headers=internship_headers, timeout=15)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("Code") == 200:
                    data = result.get("Data", [])
                    count = result.get("Count", 0)
                    return True, data, count
                else:
                    ner_logger.error("中国人保实习招聘数据接口返回错误码: %s", result.get("Code"))
                    return False, [], 0
            else:
                ner_logger.error("请求中国人保实习招聘数据失败，状态码: %s", resp.status_code)
                return False, [], 0
    except Exception as e:
        ner_logger.error("请求中国人保实习招聘数据时出错: %s", str(e))
        return False, [], 0


def transform_internship_job_json(item, job_type, channel, tmp_file, json_file):
    """
    将实习招聘信息源JSON转换为目标JSON格式（已废弃，使用transform_job_json替代）
    """
    return transform_job_json(item, job_type, channel, tmp_file, json_file)


def generate_picc_internship_job_html(item, tmp_file):
    """
    生成中国人保实习招聘详情页的HTML内容（已废弃，使用generate_picc_job_html替代）
    """
    return generate_picc_job_html(item, tmp_file, "shixi")


def api_proc_picc(spider_com, _key, com_info, k, url, _stat):
    """
    处理中国人保招聘数据（根据k参数判断是社招、校园招聘还是实习招聘）
    
    参数:
        spider_com: 爬虫组件
        _key: 关键字
        com_info: 公司信息
        k: 分类标识（如 shezhao_1、xiaozhao_1 或 shixi_1）
        url: 请求地址
        _stat: 状态信息
    """
    # 判断是社招、校园招聘还是实习招聘
    if "xiaozhao" in k:
        return api_proc_picc_campus(spider_com, _key, com_info, k, url, _stat)
    elif "shixi" in k:
        return api_proc_picc_internship(spider_com, _key, com_info, k, url, _stat)
    else:
        # 原有的社招处理逻辑
        ner_logger.info("开始处理中国人保招聘数据, k: %s, url: %s", k, url)
        
        # 如果URL为空，则使用默认的中国人保API地址
        if not url or url == "":
            url = "https://picc.zhiye.com/api/Jobad/GetJobAdPageList"

        job_type = "shezhao"  # 默认为社招
        
        # 渠道的临时目录
        key_tmp_dir = spider_com.get_key_dir(_key)
        ner_logger.info("临时目录: %s", key_tmp_dir)
        
        # 计算总页数
        flag, _, total_count = get_picc_job_data(url, 0, 10)
        if not flag:
            ner_logger.error("获取中国人保招聘数据总数失败")
            return False
        
        # 计算总页数，每页10条
        total_pages = (total_count // 10) + (1 if total_count % 10 > 0 else 0)
        ner_logger.info("中国人保招聘数据总共有 %s 条，共 %s 页", total_count, total_pages)
        
        # 遍历所有页面
        for page_index in range(total_pages):
            ner_logger.info("正在处理第 %s 页，共 %s 页", page_index + 1, total_pages)
            
            # 获取当前页数据
            flag, job_data, _ = get_picc_job_data(url, page_index, 10)
            if not flag or not job_data:
                ner_logger.error("获取第 %s 页数据失败", page_index + 1)
                continue
                
            # 写入临时文件名
            _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
            # 输出临时JSON文件路径
            tmp_fname = f'{key_tmp_dir}/index_{_hash}_{page_index + 1}.json'
            with open(tmp_fname, 'w', encoding='utf-8') as f:
                # 写入JSON
                json.dump(job_data, f, ensure_ascii=False, indent=4)
            
            # 处理每条职位数据
            ner_logger.info("开始处理第 %s 页的 %s 条职位数据", page_index + 1, len(job_data))
            for i, item in enumerate(job_data):
                try:
                    job_id = item.get("JobAdId", f"job_{page_index}_{i}")
                    job_ad_name = item.get("JobAdName", "")
                    
                    ner_logger.info("正在处理第 %s 页第 %s 条数据, 职位ID: %s, 职位名称: %s", 
                                  page_index + 1, i+1, job_id, job_ad_name)
                    
                    # 构造详情页URL
                    _fullurl = "https://picc.zhiye.com/custom/social?hideAll=true&ky=&c1=&c2=&d=&c="
                    
                    # 生成临时文件名
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
                        if generate_picc_job_html(item, tmp_file):
                            ner_logger.info("完成处理第 %s 页第 %s 条数据", page_index + 1, i+1)
                        else:
                            ner_logger.error("生成第 %s 页第 %s 条数据HTML失败", page_index + 1, i+1)
                    else:
                        ner_logger.error("转换第 %s 页第 %s 条数据失败", page_index + 1, i+1)
                    
                    # 添加延时，避免请求过于频繁
                    time.sleep(1)
                        
                except Exception as e:
                    ner_logger.error("处理第 %s 页第 %s 条数据时出错: %s", page_index + 1, i+1, str(e))
                    continue
                    
            time.sleep(3)  # 添加延时，避免请求过于频繁
                    
        ner_logger.info("中国人保招聘数据处理完成")
        return True


def api_proc_picc_campus(spider_com, _key, com_info, k, url, _stat):
    """
    处理中国人保校园招聘数据
    
    参数:
        spider_com: 爬虫组件
        _key: 关键字
        com_info: 公司信息
        k: 分类标识
        url: 请求地址
        _stat: 状态信息
    """
    ner_logger.info("开始处理中国人保校园招聘数据, k: %s, url: %s", k, url)
    
    # 如果URL为空，则使用默认的中国人保API地址
    if not url or url == "":
        url = "https://picc.zhiye.com/api/Jobad/GetJobAdPageList"

    job_type = "xiaozhao"  # 校园招聘
    
    # 渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    ner_logger.info("临时目录: %s", key_tmp_dir)
    
    # 计算总页数
    flag, _, total_count = get_picc_campus_job_data(url, 0, 10)
    if not flag:
        ner_logger.error("获取中国人保校园招聘数据总数失败")
        return False
    
    # 计算总页数，每页10条
    total_pages = (total_count // 10) + (1 if total_count % 10 > 0 else 0)
    ner_logger.info("中国人保校园招聘数据总共有 %s 条，共 %s 页", total_count, total_pages)
    
    # 遍历所有页面
    for page_index in range(total_pages):
        ner_logger.info("正在处理第 %s 页，共 %s 页", page_index + 1, total_pages)
        
        # 获取当前页数据
        flag, job_data, _ = get_picc_campus_job_data(url, page_index, 10)
        if not flag or not job_data:
            ner_logger.error("获取第 %s 页数据失败", page_index + 1)
            continue
            
        # 写入临时文件名
        _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        # 输出临时JSON文件路径
        tmp_fname = f'{key_tmp_dir}/index_{_hash}_{page_index + 1}.json'
        with open(tmp_fname, 'w', encoding='utf-8') as f:
            # 写入JSON
            json.dump(job_data, f, ensure_ascii=False, indent=4)
        
        # 处理每条职位数据
        ner_logger.info("开始处理第 %s 页的 %s 条职位数据", page_index + 1, len(job_data))
        for i, item in enumerate(job_data):
            try:
                job_id = item.get("JobAdId", f"job_{page_index}_{i}")
                job_ad_name = item.get("JobAdName", "")
                
                ner_logger.info("正在处理第 %s 页第 %s 条数据, 职位ID: %s, 职位名称: %s", 
                              page_index + 1, i+1, job_id, job_ad_name)
                
                # 构造详情页URL
                _fullurl = "https://picc.zhiye.com/custom/campus?hideAll=true&ky=&c1=&c2=&d=&c="
                
                # 生成临时文件名
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
                if transform_campus_job_json(item, job_type, _key, tmp_file, tmp_json_file):
                    # 生成html
                    if generate_picc_campus_job_html(item, tmp_file):
                        ner_logger.info("完成处理第 %s 页第 %s 条数据", page_index + 1, i+1)
                    else:
                        ner_logger.error("生成第 %s 页第 %s 条数据HTML失败", page_index + 1, i+1)
                else:
                    ner_logger.error("转换第 %s 页第 %s 条数据失败", page_index + 1, i+1)
                
                # 添加延时，避免请求过于频繁
                time.sleep(1)
                    
            except Exception as e:
                ner_logger.error("处理第 %s 页第 %s 条数据时出错: %s", page_index + 1, i+1, str(e))
                continue
                
        time.sleep(3)  # 添加延时，避免请求过于频繁
                
    ner_logger.info("中国人保校园招聘数据处理完成")
    return True


def api_proc_picc_internship(spider_com, _key, com_info, k, url, _stat):
    """
    处理中国人保实习招聘数据
    
    参数:
        spider_com: 爬虫组件
        _key: 关键字
        com_info: 公司信息
        k: 分类标识
        url: 请求地址
        _stat: 状态信息
    """
    ner_logger.info("开始处理中国人保实习招聘数据, k: %s, url: %s", k, url)
    
    # 如果URL为空，则使用默认的中国人保API地址
    if not url or url == "":
        url = "https://picc.zhiye.com/api/Jobad/GetJobAdPageList"

    job_type = "shixi"  # 实习招聘
    
    # 渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    ner_logger.info("临时目录: %s", key_tmp_dir)
    
    # 计算总页数
    flag, _, total_count = get_picc_internship_job_data(url, 0, 10)
    if not flag:
        ner_logger.error("获取中国人保实习招聘数据总数失败")
        return False
    
    # 计算总页数，每页10条
    total_pages = (total_count // 10) + (1 if total_count % 10 > 0 else 0)
    ner_logger.info("中国人保实习招聘数据总共有 %s 条，共 %s 页", total_count, total_pages)
    
    # 遍历所有页面
    for page_index in range(total_pages):
        ner_logger.info("正在处理第 %s 页，共 %s 页", page_index + 1, total_pages)
        
        # 获取当前页数据
        flag, job_data, _ = get_picc_internship_job_data(url, page_index, 10)
        if not flag or not job_data:
            ner_logger.error("获取第 %s 页数据失败", page_index + 1)
            continue
            
        # 写入临时文件名
        _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        # 输出临时JSON文件路径
        tmp_fname = f'{key_tmp_dir}/index_{_hash}_{page_index + 1}.json'
        with open(tmp_fname, 'w', encoding='utf-8') as f:
            # 写入JSON
            json.dump(job_data, f, ensure_ascii=False, indent=4)
        
        # 处理每条职位数据
        ner_logger.info("开始处理第 %s 页的 %s 条职位数据", page_index + 1, len(job_data))
        for i, item in enumerate(job_data):
            try:
                job_id = item.get("JobAdId", f"job_{page_index}_{i}")
                job_ad_name = item.get("JobAdName", "")
                
                ner_logger.info("正在处理第 %s 页第 %s 条数据, 职位ID: %s, 职位名称: %s", 
                              page_index + 1, i+1, job_id, job_ad_name)
                
                # 构造详情页URL
                _fullurl = "https://picc.zhiye.com/custom/shixi?hideAll=true"
                
                # 生成临时文件名
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
                if transform_internship_job_json(item, job_type, _key, tmp_file, tmp_json_file):
                    # 生成html
                    if generate_picc_internship_job_html(item, tmp_file):
                        ner_logger.info("完成处理第 %s 页第 %s 条数据", page_index + 1, i+1)
                    else:
                        ner_logger.error("生成第 %s 页第 %s 条数据HTML失败", page_index + 1, i+1)
                else:
                    ner_logger.error("转换第 %s 页第 %s 条数据失败", page_index + 1, i+1)
                
                # 添加延时，避免请求过于频繁
                time.sleep(1)
                    
            except Exception as e:
                ner_logger.error("处理第 %s 页第 %s 条数据时出错: %s", page_index + 1, i+1, str(e))
                continue
                
        time.sleep(3)  # 添加延时，避免请求过于频繁
                
    ner_logger.info("中国人保实习招聘数据处理完成")
    return True
