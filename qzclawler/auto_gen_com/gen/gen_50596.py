
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='job-list'):
        announcement_name = job.find('span', class_='job-name').get_text(strip=True) if job.find('span', class_='job-name') else ""
        publish_time = ""  # No publish time in the provided HTML
        link = job.find('a', class_='join-link')['href'] if job.find('a', class_='join-link') else ""
        hd_dept = job.find('span', class_='job-info').get_text(strip=True).replace('所属部门：', '') if job.find('span', class_='job-info') else ""
        hd_loc = job.find('span', class_='job-money').get_text(strip=True).replace('工作地点：', '') if job.find('span', class_='job-address') else ""
        hd_job_num = job.find('span', class_='job-peple').get_text(strip=True).replace('招聘人数：', '') if job.find('span', class_='job-peple') else ""
        hd_job_category = job.find_all('span', class_='job-time')[1].get_text(strip=True) if len(job.find_all('span', class_='job-time')) > 1 else ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
