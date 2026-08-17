import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('li', class_='ant-list-item')

    result = []

    for item in items:
        announcement_name = item.find('div', class_='ant-typography-ellipsis').get_text(strip=True)
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc =""
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ""

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
