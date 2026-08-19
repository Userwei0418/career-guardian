
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile,url):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    position_list = []

    for item in soup.select('.position-item'):
        announcement_name = item.select_one('h2').get_text(strip=True)
        hd_dept = item.select_one('.org').get_text(strip=True)
        hd_loc = item.select_one('.mini-city').get_text(strip=True).replace('工作城市：', '')
        hd_job_category = item.select_one('.ic-category').get_text(strip=True)
        hd_job_num = ""  # Assuming the job number is indicated by "应届生"
        publish_time = ""  # Placeholder for publish time, as it's not provided in the HTML
        link = ""  # Placeholder for link, as it's not provided in the HTML

        position_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(position_list, f, ensure_ascii=False, indent=4)
