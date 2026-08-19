import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 定位职位块
    job_elements = soup.find_all('div', class_='link-2tgd22te-3')

    for job in job_elements:
        # 安全提取每一个字段，如果不存在则为""
        link_tag = job.find('a')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""

        title_tag = job.find('div', class_='title-20V7ljm-Id')
        title = title_tag.get_text(strip=True).replace('急','') if title_tag else ""

        publish_tag = job.find('span', class_='opened-at-20H_gh2Tqd')
        publish_time = publish_tag.get_text(strip=True).replace('发布时间：', '') if publish_tag else ""

        location_tag = job.find('div', class_='locations-32aEgVWFz_')
        location = location_tag.get_text(strip=True) if location_tag else ""

        department_tag = job.find('span', class_='status-item-1_w5ygMyMO')
        department = department_tag.get_text(strip=True) if department_tag else ""

        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": "",         # 无信息则为空
            "hd_job_category": "department"     # 无信息则为空
        }

        job_list.append(job_info)

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
