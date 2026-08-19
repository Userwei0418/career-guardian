import json
import requests
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 请求的 URL
    url = "https://www.nancal.com/api/web/recruit/position/list"

    # 请求头
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "keep-alive",
        "Origin": "https://www.nancal.com",
        "Referer": "https://www.nancal.com/join-us/salary?columnChildId=98423969987694592&template=jobList"
    }

    # 请求体
    data = {
        "address": "",
        "pageNo": 1,
        "pageSize": 20,
        "position": ""
    }

    # 发送 POST 请求
    response = requests.post(url, headers=headers, json=data)

    # 检查响应状态
    if response.status_code == 200:
        # 获取返回的 JSON 数据
        json_data = response.json().get("data", {}).get("records", [])

        jobs = json_data  # 直接赋值给 jobs 列表，而不是再进行 extend
    else:
        print(f"请求失败，状态码: {response.status_code}")
        jobs = []  # 如果请求失败，则将 jobs 设为空列表

    # 创建职位标题到 ID 的字典
    jobs_title_to_id = {}
    for job in jobs:
        name = job.get("position", "")
        job_id = job.get("id", "")
        if name and job_id:  # 确保职位名和 ID 都存在
            jobs_title_to_id[name] = job_id

    # 解析 HTML 并提取职位信息
    for li in soup.find_all('li', class_='flex h-70 ie-txt'):
        announcement_name = li.find_all('div')[0].get_text(strip=True)
        hd_loc = li.find_all('div')[1].get_text(strip=True)
        hd_job_num = li.find_all('div')[2].get_text(strip=True)
        publish_time = li.find_all('div')[3].get_text(strip=True)

        # Placeholder for missing information
        hd_dept = ""  # 部门
        hd_job_category = ""  # 职位类别

        # 使用字典的 get 方法获取职位 ID，如果没有找到，则返回空字符串
        post_id = jobs_title_to_id.get(announcement_name, "")

        link = f"https://www.nancal.com/join-us/salary?columnChildId=98423969987694592&template=jobList&anchor=&jobId={post_id}"

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 将职位信息写入临时文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
