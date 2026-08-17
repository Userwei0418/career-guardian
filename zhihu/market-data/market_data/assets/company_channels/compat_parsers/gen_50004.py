import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='span-3 midd-4 smal-12'):
        announcement_name = item.find('div', class_='_j_tt').text.strip()
        publish_time = item.find_all('div', class_='_txt')[1].text.replace('发布时间：', '').strip()
        link = item.find('a')['href']

        # Placeholder values for the other fields
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

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