
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = job.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = job.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = job.find('a')['href']
        raw_text = job.find('div', class_='sd-foundation-body-secondary-1Z7H-').get_text(strip=True)
        # 去掉重复
        hd_dept = raw_text[:len(raw_text) // 2] if raw_text[:len(raw_text) // 2] == raw_text[
            len(raw_text) // 2:] else raw_text

        hd_loc = ""  # Assuming all jobs are full-time based on the provided HTML
        hd_job_num = ""  # Placeholder as the number of positions is not provided
        hd_job_category = ""  # Placeholder as the job category is not provided

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
