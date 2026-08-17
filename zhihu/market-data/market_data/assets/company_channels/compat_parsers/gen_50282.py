
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for post_show in soup.find_all('div', class_='post-show'):
        department = post_show.find('h1').text.strip()
        for job in post_show.find_all('li'):
            job_name = job.find('h3', class_='th-1').text.strip()
            job_location =""
            job_education = job.find('h3', class_='th-3').text.strip()
            link = job.find('a', class_='post-link')['href']
            job_num = ""  # Placeholder as job number is not provided in the HTML
            job_category = ""  # Placeholder as job category is not provided in the HTML

            job_info = {
                "announcement_name": job_name,
                "publish_time": "",  # Placeholder as publish time is not provided in the HTML
                "link": link,
                "hd_dept": department,
                "hd_loc": job_location,
                "hd_job_num": job_num,
                "hd_job_category": job_category
            }
            job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
