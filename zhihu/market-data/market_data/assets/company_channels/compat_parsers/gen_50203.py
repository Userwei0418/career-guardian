
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='recruit-list-item'):
        announcement_name = item.find('h3', class_='h3-recruit-item').text.strip()
        link = item.find('a')['href']
        publish_time = ''  # Assuming publish time is not available in the provided HTML
        hd_dept = ''  # Assuming department is not available in the provided HTML
        hd_loc = item.find('span').text.strip()
        hd_job_num = ""
        hd_job_category =item.find_all('span')[1].text.strip()

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
