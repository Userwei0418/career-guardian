
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        announcement_name = li.find('h2').get_text(strip=True)
        link = li.find('h2').find('a')['href']
        hd_dept = li.find_all('span')[0].get_text(strip=True).replace('所属公司：', '')
        hd_inst = li.find_all('span')[1].get_text(strip=True).replace('所属机构: ', '')
        hd_loc = li.find('div', class_='lh20').get_text(strip=True).replace('工作地点：', '')
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ""  # Placeholder as the job category is not provided in the HTML
        publish_time = ""  # Placeholder as the publish time is not provided in the HTML

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
