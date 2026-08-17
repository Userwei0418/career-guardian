
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    items = soup.find_all('div', class_='item')
    for item in items:
        title = item.find('div', class_='title').find('span').text.strip()
        job_category = item.find('div', class_='dt').find_all('span')[0].text.strip()
        location = item.find('div', class_='dt').find_all('span')[2].get('title', '').strip()

        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Assuming no publish time is provided in the HTML
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": "",  # Assuming this is a constant value from the HTML
            "hd_job_category": job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
