
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    base_url = "https://wecruit.hotjob.cn/SU64365a780dcad43c5ae82bab/pb/posDetail.html?postId={}&postType=campus"

    for item in soup.find_all(class_='list-item-main'):
        announcement_name = item.find(class_='pos-name').get_text(strip=True)
        publish_time = item.find(class_='pos-pubTime').get_text(strip=True)
        post_id = item.get('id')
        link = base_url.format(post_id) if post_id else ''
        hd_dept = ""  # Placeholder as the department is not provided in the HTML
        hd_loc = item.find(class_='pos-locate').get_text(strip=True)
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ""  # Placeholder as the job category is not provided in the HTML

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
