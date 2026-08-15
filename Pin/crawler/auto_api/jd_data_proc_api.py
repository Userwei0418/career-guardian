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

headers = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://zhaopin.jd.com",
    "Pragma": "no-cache",
    "Referer": "https://zhaopin.jd.com/web/job_info_list/3?isHunterFlag=false",
    "Sec-Ch-Ua": '"Not;A=Brand";v="99", "Google Chrome";v="139", "Chromium";v="139"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest"
}

# 登录态不得写入源码；需要时通过本地环境变量注入。
cookie_str = os.getenv("JD_RECRUITMENT_COOKIE", "").strip()
if cookie_str:
    headers["Cookie"] = cookie_str


def get_jd_job_json(url, curPage):
    """
    获取京东招聘信息的JSON数据
    
    参数:
        url: 请求地址
        curPage: 当前页码
        
    返回:
        (flag, data, total_count) 元组
    """
    # 请求体参数
    payload_dict = {
        "pageIndex": curPage,
        "pageSize": 100,
        "workCityJson": "[]",
        "jobTypeJson": "[]",
        "jobSearch": ""
    }
    payload = urlencode(payload_dict)
    
    ner_logger.info(f"准备发送请求到 {url}，页码: {curPage}，请求体: {payload}")

    # 发送请求
    with requests.Session() as s:
        resp = s.post(url, data=payload, headers=headers, timeout=15)
        ner_logger.info(f"收到响应，状态码: {resp.status_code}，响应头: {dict(resp.headers)}")
        # 尝试以 json 解析（如果服务端返回 JSON）
        try:
            if resp.status_code == 200:
                json_data = resp.json()
                ner_logger.info(f"成功解析JSON数据，数据结构: {type(json_data)}，数据预览: {str(json_data)[:500]}")
                if isinstance(json_data, list):
                    # 如果直接返回职位列表
                    data = json_data
                    total = len(data)
                    ner_logger.info(f"返回的是职位列表，数据量: {total}")
                    return True, data, total
                elif 'data' in json_data:
                    # 如果返回的是包含data字段的结构
                    data = json_data.get('data', [])
                    total = json_data.get('total', len(data))
                    ner_logger.info(f"返回的是包含data字段的结构，数据量: {len(data)}，总数: {total}")
                    return True, data, total
                elif 'results' in json_data:
                    # 如果返回的是包含results字段的分页结构
                    data = json_data.get('results', [])
                    total = json_data.get('count', len(data))
                    ner_logger.info(f"返回的是包含results字段的结构，数据量: {len(data)}，总数: {total}")
                    return True, data, total
                else:
                    # 其他格式，尝试直接使用整个响应
                    data = [json_data] if not isinstance(json_data, list) else json_data
                    total = len(data)
                    ner_logger.info(f"返回的是其他格式的数据，数据量: {total}")
                    return True, data, total
            else:
                ner_logger.error(f"请求失败，状态码: {resp.status_code}，响应内容: {resp.text}")
                return False, [], 0
        except Exception as e:
            ner_logger.error(f"JSON解析错误: {str(e)}，响应内容: {resp.text}")
            return False, [], 0


def generate_job_html(item, tmp_file):
    """
    根据职位信息生成HTML文件
    
    参数:
        item: 职位信息字典
        tmp_file: 保存文件路径
    """
    try:
        ner_logger.info(f"开始生成HTML文件，职位信息: {item}")
        # 获取职位信息
        job_name = item.get('positionNameOpen', item.get('positionName', item.get('name', '职位名称')))
        publish_time = item.get('formatPublishTime', item.get('publishTime', ''))
        work_city = item.get('workCity', '')
        job_type = item.get('jobType', '')
        department = item.get('positionDeptName', item.get('departmentName', ''))
        work_content = item.get('workContent', '暂无职位描述信息')
        qualification = item.get('qualification', '暂无职位要求信息')
        
        ner_logger.info(f"职位信息提取结果 - 名称: {job_name}, 发布时间: {publish_time}, 工作城市: {work_city}")
        
        # 创建HTML内容
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{job_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .job-header {{ border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 20px; }}
        .job-title {{ font-size: 24px; font-weight: bold; color: #333; }}
        .job-meta {{ margin: 10px 0; }}
        .job-meta span {{ margin-right: 20px; color: #666; }}
        .job-section {{ margin-bottom: 20px; }}
        .section-title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #444; }}
        .job-description {{ line-height: 1.6; white-space: pre-wrap; }}
    </style>
</head>
<body>
    <div class="job-header">
        <div class="job-title">{job_name}</div>
        <div class="job-meta">
            <span>发布时间: {publish_time}</span>
            <span>工作地点: {work_city}</span>
            <span>职位类型: {job_type}</span>
        </div>
        <div class="job-meta">
            <span>所属部门: {department}</span>
        </div>
    </div>
    
    <div class="job-section">
        <div class="section-title">职位描述</div>
        <div class="job-description">
            {work_content}
        </div>
    </div>
    
    <div class="job-section">
        <div class="section-title">职位要求</div>
        <div class="job-description">
            {qualification}
        </div>
    </div>
</body>
</html>
        """
        
        # 写入HTML文件
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        ner_logger.info(f"成功生成HTML文件: {tmp_file}")
            
        time.sleep(1)  # 减少延迟时间以提高速度
        return True
    except Exception as e:
        ner_logger.error(f"生成HTML文件失败：{e}")
        return False


def transform_job_json(item, job_type, channel, target_url, tmp_file, json_file):
    """
    将源JSON转换为目标JSON格式
    
    参数:
        item: 源JSON字典，包含待转换的字段
        
    返回:
        转换后的目标JSON字典
    """
    ner_logger.info(f"开始转换JSON数据，原始数据: {item}")
    # 定义字段映射关系
    field_mapping = {
        "announcement_name": "positionNameOpen",
        "publish_time": "formatPublishTime",
        "hd_dept": "positionDeptName",
        "hd_loc": "workCity",
        "hd_job_num": "",  # 京东数据中没有明确数量
        "hd_job_category": "jobType"
    }
    
    # 检查是否包含特定字段，调整映射关系
    if "positionNameOpen" not in item:
        if "formatPublishTime" in item:
            field_mapping = {
                "announcement_name": "name",
                "publish_time": "formatPublishTime",
                "hd_dept": "departmentName",
                "hd_loc": "workCity",
                "hd_job_num": "",
                "hd_job_category": "jobTypeName"
            }
        elif "publishTime" in item:
            field_mapping = {
                "announcement_name": "name",
                "publish_time": "publishTime",
                "hd_dept": "departmentName",
                "hd_loc": "workCity",
                "hd_job_num": "",
                "hd_job_category": "jobTypeName"
            }

    # 固定字段值
    fixed_fields = {
        "link": target_url,
        "full_url": target_url,
        "last_url": target_url,
        "file_path": tmp_file,
        "parent_url": "https://zhaopin.jd.com/",
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
    
    ner_logger.info(f"转换后的JSON数据: {target_json}")
    
    # 保存json文件
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(target_json, f, ensure_ascii=False, indent=4)
        ner_logger.info(f"成功保存JSON文件: {json_file}")
        time.sleep(1)  # 减少延迟时间以提高速度


def api_proc_jd(spider_com, _key, com_info, k, url, _stat):
    """
    处理京东招聘数据
    
    参数:
        spider_com: 爬虫组件
        _key: 关键字
        com_info: 公司信息
        k: 分类标识
        url: 请求地址
        _stat: 状态信息
    """
    ner_logger.info(f"开始处理京东招聘数据，参数 - _key: {_key}, k: {k}, url: {url}, _stat: {_stat}")
    # 如果URL为空，则使用默认的京东API地址
    if not url or url == "":
        url = "https://zhaopin.jd.com/web/job/job_list"
        ner_logger.info(f"URL为空，使用默认URL: {url}")

    job_type = "shezhao"
    
    if k.startswith("shezhao"):
        job_type = "shezhao"
        ner_logger.info("设置job_type为shezhao")
    elif k.startswith("xiaozhao"):
        job_type = "xiaozhao"
        ner_logger.info("设置job_type为xiaozhao")

    # 渠道的临时目录
    key_tmp_dir = spider_com.get_key_dir(_key)
    ner_logger.info(f"使用临时目录: {key_tmp_dir}")
    
    # 总页数
    total_page = 50
    
    # curPage 循环1-99
    for curPage in range(1, 100):
        ner_logger.info(f"开始处理第 {curPage} 页")
        flag, json_data, totalcount = get_jd_job_json(url, curPage)
        if flag:
            ner_logger.info("jd json response: total_page=%s, data_count=%s", total_page, len(json_data))
            if total_page == 0:
                # 根据总数据和每页数量计算页数
                total_page = int(totalcount / 100) + 1  # 使用每页100条数据
                ner_logger.info(f"计算总页数: {total_page} (总数据量: {totalcount})")
                
            # 写入临时文件名
            _hash = hashlib.md5(url.encode("utf-8")).hexdigest()
            # 输出临时JSON文件路径
            tmp_fname = f'{key_tmp_dir}/index_{_hash}_{curPage}.json'
            with open(tmp_fname, 'w', encoding='utf-8') as f:
                # 写入JSON
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            ner_logger.info(f"保存页面JSON数据到: {tmp_fname}")
                
            # 完成爬取后跳出
            if curPage >= total_page:
                ner_logger.info("已达到总页数，结束循环")
                break
            if curPage > 5 and _stat.get('method', '') != "cp_full":
                ner_logger.info("页数超过5页且method不为cp_full，结束循环")
                break
                
            # 对json列表数据进行处理
            for idx, item in enumerate(json_data):
                ner_logger.info(f"处理第 {curPage} 页中的第 {idx+1} 个项目")
                job_id = item.get("id", "")
                # 目标 URL（京东招聘列表页面）
                _fullurl = f"https://zhaopin.jd.com/web/job_info_list/3"
                
                # 生成临时文件名
                _hash = hashlib.md5((_fullurl + str(job_id)).encode("utf-8")).hexdigest()
                tmp_file = os.path.join(key_tmp_dir, f"detail_{_hash}.html")
                tmp_json_file = os.path.join(key_tmp_dir, f"detail_{_hash}.json")
                
                # 生成职位详情HTML文件
                html_result = generate_job_html(item, tmp_file)
                if not html_result:
                    ner_logger.error(f"生成HTML文件失败，跳过当前项目: {item}")
                    continue
                
                # 执行json的转换
                transform_job_json(item, job_type, _key, _fullurl, tmp_file, tmp_json_file)
                time.sleep(1)  # 减少延迟时间以提高速度
        else:
            ner_logger.error(f"获取第 {curPage} 页数据失败")
            # 如果第一页就失败了，直接返回
            if curPage == 1:
                ner_logger.error("第一页数据获取失败，终止执行")
                return False
        time.sleep(1)  # 减少延迟时间以提高速度
        
    ner_logger.info("京东招聘数据处理完成")
    # 返回
    return True