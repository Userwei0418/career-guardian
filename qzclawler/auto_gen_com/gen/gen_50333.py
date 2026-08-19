
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr')
    data_list = []

    for row in rows:
        announcement_name = row.find('td', class_='join_w01').text.strip()
        hd_loc = row.find('td', class_='join_w02').text.strip().replace('、', ',')
        hd_job_num = row.find('td', class_='join_w03').text.strip()
        publish_time = row.find('td', class_='join_w04').text.strip()
        link = row['onclick'].split("'")[1]
        
        # Assuming hd_dept and hd_job_category are not provided in the HTML
        hd_dept = ""
        hd_job_category = ""
        
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
