
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('a', class_='bili-item-card'):
        title = item.find('h4', class_='item-title').find('span', class_='text').text
        tags = item.find('div', class_='bili-infotags').find_all('span')
        
        job_info = {
            "announcement_name": title,
            "publish_time": tags[3].text.replace(" 发布", ""),
            "link": "",  # Assuming the link is not provided in the HTML snippet
            "hd_dept": tags[1].text,
            "hd_loc": tags[0].text,
            "hd_job_num": "1",  # Assuming a default value as the number is not provided
            "hd_job_category": tags[2].text
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
