
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('li', class_='results-list__item'):
        announcement_name = item.find('h3', class_='results-list__item-title').get_text(strip=True)
        link = item.find('a', class_='results-list__item-title--link')['href']
        publish_time = ""  # Assuming no publish time is available in the provided HTML
        hd_dept = item.find('div', class_='results-list__categories').get_text(strip=True) if item.find('div', class_='results-list__categories') else ""
        hd_loc = item.find('span', class_='results-list__item-street--label').get_text(strip=True) if item.find('span', class_='results-list__item-street--label') else ""
        hd_job_num = ""  # Assuming no job number is available in the provided HTML
        hd_job_category = ""  # Assuming no job category is available in the provided HTML

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
