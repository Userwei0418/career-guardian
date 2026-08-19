import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    base_url = "https://bosera.hotjob.cn/SU648980fc0dcad412ce899514/pb/school.html"

    for item in soup.find_all('div', class_='list-item-main'):
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True)
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True).replace('|', '')
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True)
        publish_time = item.find('div', class_='pos-pubTime').get_text(strip=True)

        post_id = item.get('id', '')  # 直接取 div 的 id
        link = ""

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # 部门信息 HTML 没有提供
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # 职位类别 HTML 没有提供
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
