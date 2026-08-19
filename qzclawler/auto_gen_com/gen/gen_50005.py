import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-card-item1'):
        announcement_name = item.find(class_='top-label').text.strip()
        publish_time = item.find(class_='pub-time').text.replace('发布时间：', '').strip()

        # Update link to dynamically generate the full URL for each job
        post_id = item['id']
        link = ""

        hd_dept = item.find(class_='pos-summary').contents[0].text.strip()
        hd_loc = item.find(class_='work-place').text.strip().replace('|', '')
        hd_job_num = item.find(class_='need-people').text.replace('招聘人数：', '').strip()
        hd_job_category = item.find(class_='pos-cate').text.strip()

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
