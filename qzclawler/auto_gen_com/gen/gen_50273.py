
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for post_item in soup.find_all('div', class_='post-item'):
        title_div = post_item.find('div', class_='post-item-title')
        info_div = post_item.find('div', class_='post-item-info')
        
        announcement_name = title_div.find('span', class_='post-name').text.strip()
        publish_time = ""  # Assuming publish time is not available in the provided HTML
        link = title_div.find_parent('a')['href']
        hd_dept = info_div.find_all('span')[1].text.strip() if len(info_div.find_all('span')) > 1 else ""
        hd_loc = info_div.find_all('span')[-1].text.strip() if len(info_div.find_all('span')) > 2 else ""
        hd_job_num = ""  # Assuming job number is not available in the provided HTML
        hd_job_category = info_div.find('span').text.strip() if info_div.find('span') else ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_dept
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
