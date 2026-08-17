
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('div', class_='content-item')

    result = []

    for item in items:
        announcement_name = item.find('span', class_='batch-title').text.strip()
        publish_time = ""  # Assuming publish_time is not available in the provided HTML

        link = ""
        hd_dept = item.find('div', class_='describe').text.split('|')[-1].strip()
        hd_loc = item.find('div', class_='workPlace').text.split('：')[-1].strip()
        hd_job_num = ""  # Assuming job number is not specified in the provided HTML
        hd_job_category = item.find('div', class_='describe').text.split('|')[0].strip()

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
