
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')

    for job in job_elements:
        announcement_name = job.find('div', class_='_1RRlPtjyYmeDGCWt9lrk2P').text.strip()
        publish_time = job.find('div', class_='_3Jn5Z6PZA5H7Auzy0xlXu2').text.replace('更新于 ', '').strip()
        hd_job_category = job.find('div', class_='_1KYNSENqWg4IDHby5E9sqK').text.strip()
        hd_loc = job.find_all('div', class_='_3CJNtKfv5mLnNfeqL1jgRB')[-1].text.strip().replace('/','')

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Assuming link is not provided in the HTML
            "hd_dept": "",  # Assuming department is not provided in the HTML
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming job number is not provided in the HTML
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
