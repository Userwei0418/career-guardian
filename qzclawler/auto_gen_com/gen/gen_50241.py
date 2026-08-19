import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    """
    从 HTML 中提取职位信息并写入 JSON 文件。
    若字段缺失，则自动填充为空字符串。
    """
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 定位每个职位模块
    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')

    for job in job_elements:
        # 安全提取：如果没找到元素，返回 ""
        def safe_text(selector, cls):
            tag = job.find(selector, class_=cls)
            return tag.get_text(strip=True) if tag else ""

        announcement_name = safe_text('div', '_1RRlPtjyYmeDGCWt9lrk2P')
        publish_time_raw = safe_text('div', '_3Jn5Z6PZA5H7Auzy0xlXu2')
        publish_time = publish_time_raw.replace('更新于 ', '') if publish_time_raw else ""

        hd_job_category = safe_text('div', '_1KYNSENqWg4IDHby5E9sqK')
        hd_loc = safe_text('div', '_3CJNtKfv5mLnNfeqL1jgRB')

        # 构建字典
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",          # 若页面中无链接字段
            "hd_dept": "",       # 若无部门信息
            "hd_loc": hd_loc,
            "hd_job_num": "",    # 若无招聘人数
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"[日志] 共提取 {len(job_list)} 条职位信息，结果已写入 {tempfile}")
