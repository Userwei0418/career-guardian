import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        announcement_name = item.find(class_='pos-name')
        publish_time = item.find(class_='pos-pubTime')
        loc = item.find(class_='pos-locate')
        num = item.find(class_='pos-num')

        # 用 item.get('id') 直接取，不用再次 find

        link = ""

        job_list.append({
            "announcement_name": announcement_name.get_text(strip=True) if announcement_name else "",
            "publish_time": publish_time.get_text(strip=True) if publish_time else "",
            "link": link,
            "hd_dept": "",
            "hd_loc": loc.get_text(strip=True) if loc else "",
            "hd_job_num": num.get_text(strip=True) if num else "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
