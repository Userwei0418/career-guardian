
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody tr')
    data_list = []

    for row in rows:
        announcement_name = row.find('a').get('title')
        link = row.find('a').get('href')
        publish_time = row.find_all('td')[2].text.strip()
        hd_dept = ''  # Placeholder as the original HTML does not provide this information
        hd_loc = row.find_all('td')[1].text.strip()
        hd_job_num = ''  # Placeholder as the original HTML does not provide this information
        hd_job_category = ''  # Placeholder as the original HTML does not provide this information

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
