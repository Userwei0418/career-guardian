
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.select('.w-list-news li'):
        announcement_name = item.select_one('h3 a').get('title', '') if item.select_one('h3 a') else ""
        link = item.select_one('h3 a').get('href', '') if item.select_one('h3 a') else ""
        publish_time = item.select_one('.date').text.strip() if item.select_one('.date') else ""
        hd_dept = ""  # Assuming this information is not available in the provided HTML
        hd_loc = ""   # Assuming this information is not available in the provided HTML
        hd_job_num = ""
        hd_job_category = ""

        # Extracting the number of recruits from the paragraph
        recruit_info = item.select_one('p').text if item.select_one('p') else ""
        if "招聘人数：" in recruit_info:
            hd_job_num = recruit_info.split("招聘人数：")[-1].split("人")[0].strip() + "人"

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
