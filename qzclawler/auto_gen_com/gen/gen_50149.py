
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li', class_='is_high_need'):
        announcement_name = li.find('a', class_='golink').text.strip()
        link = li.find('a', class_='golink')['href']
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        hd_dept = li.find_all('span')[2].text.strip() # Department
        hd_loc = li.find_all('span', class_='yellow-tip')[0].text.strip()  # Location
        hd_job_num = ""  # Assuming job number is not available in the provided HTML
        hd_job_category = ""  # Job category

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
