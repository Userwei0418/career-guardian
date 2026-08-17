
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    items = soup.find_all('div', class_='item-wapper')
    for item in items:
        title = item.find('div', class_='item-title').text.strip()
        notes = item.find('div', class_='item-notes')
        category = notes.find_all('div', class_='note')[0].text.split('：')[1].strip()
        dept = notes.find_all('div', class_='note')[1].text.split('：')[1].strip()
        location = notes.find_all('div', class_='note')[2].text.split('：')[1].strip()
        job_num = ""  # Assuming job number is not provided in the HTML
        publish_time = ""  # Assuming publish time is not provided in the HTML
        link = ""  # Assuming link is not provided in the HTML
        if "实习" in title:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": dept,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": category,
            "hd_hopeworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
