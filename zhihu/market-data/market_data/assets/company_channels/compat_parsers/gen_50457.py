
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    for li in soup.find_all('li')[1:]:  # Skip the header
        announcement_name = li.find('div', class_='mc').get_text(strip=True)
        link = li.find('div', class_='mc').find('a')['href'] if li.find('div', class_='mc').find('a') else ""
        hd_dept = ""  # No corresponding field in the provided HTML
        hd_loc = li.find('div', class_='dd').get_text(strip=True) if li.find('div', class_='dd') else ""
        publish_time = li.find('div', class_='sj').get_text(strip=True) if li.find('div', class_='sj') else ""
        hd_job_num = li.find('div', class_='rs').get_text(strip=True) if li.find('div', class_='rs') else ""
        hd_job_category = li.find('div', class_='lb').get_text(strip=True) if li.find('div', class_='lb') else ""

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
