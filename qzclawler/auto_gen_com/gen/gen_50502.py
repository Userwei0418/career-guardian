
import json
import re

from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        announcement_name = li.find('p', class_='tt').find('a').text.strip() if li.find('p', class_='tt') else ""
        link = li.find('p', class_='tt').find('a')['href'] if li.find('p', class_='tt') else ""
        hd_dept = li.find('div', class_='company-name').get('title', "").strip() if li.find('div', class_='company-name') else ""
        hd_loc = li.find('p', style='margin-top: 35px; width: 120px;').text.strip().replace('\xa0', '') if li.find('p', style='margin-top: 35px; width: 120px;') else ""
        hd_job_num = li.find('span', text=lambda x: x and '招聘' in x).text.replace('招聘', '').replace('人', '').strip() if li.find('span', text=lambda x: x and '招聘' in x) else ""
        name = re.sub(r'^\d+\s*', '', announcement_name)
        hd_job_category =  ""
        publish_time = ""

        job_list.append({
            "announcement_name": name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
