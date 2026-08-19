import json
import re
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='item job_ad_list'):
        title_tag = item.find('div', class_='t').find('a')
        announcement_name = title_tag.get_text(strip=True)
        link = title_tag['href']

        hd_job_num =  ''

        # 成员公司
        hd_dept_tag = item.find('span', text=lambda x: x and '成员公司' in x)
        hd_job_category = hd_dept_tag.get_text(strip=True).replace('成员公司：', '') if hd_dept_tag else ''

        # 工作地点
        hd_loc_tag = item.find('span', text=lambda x: x and '工作地点' in x)
        hd_loc = hd_loc_tag.get_text(strip=True).replace('工作地点：', '') if hd_loc_tag else ''

        # 发布时间
        time_tag = item.find('span', text=lambda x: x and '发布时间' in x)
        publish_time = time_tag.get_text(strip=True).replace('发布时间：', '') if time_tag else ''

        # 岗位类别
        job_category_match = re.search(r'ClassificationTwo=(.*?)&', link)
        hd_dept = job_category_match.group(1) if job_category_match else ''

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
