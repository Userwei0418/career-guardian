
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.select('.join-tbody a.tr'):
        announcement_name = job.find('div', class_='th').get_text(strip=True) if job.find('div', class_='th') else ""
        hd_dept = job.find_all('div', class_='th')[1].get_text(strip=True) if len(job.find_all('div', class_='th')) > 1 else ""
        hd_loc = job.find_all('div', class_='th')[2].get_text(strip=True) if len(job.find_all('div', class_='th')) > 2 else ""
        hd_job_num = job.find_all('div', class_='th')[3].get_text(strip=True) if len(job.find_all('div', class_='th')) > 3 else ""
        publish_time = job.find_all('div', class_='th')[4].get_text(strip=True) if len(job.find_all('div', class_='th')) > 4 else ""
        link = job['href'] if 'href' in job.attrs else ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
