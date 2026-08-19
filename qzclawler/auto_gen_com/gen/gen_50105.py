
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    items = soup.find_all('div', class_='item proInfoConList')
    for item in items:
        announcement_name = item.find('div', class_='name').text.strip()
        tags = item.find('div', class_='tag').find_all('span')
        hd_dept = tags[0].text.strip()
        hd_loc = tags[1].text.strip()
        hd_job_category = tags[2].text.strip()
        hd_job_num = tags[3].text.strip()
        publish_time = tags[4].text.strip()
        link = item.find('a', class_='tool-btn')['href']

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
