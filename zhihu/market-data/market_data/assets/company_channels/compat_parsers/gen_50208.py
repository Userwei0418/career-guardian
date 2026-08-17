
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='link-2tgd22te-3'):
        title = job.find('div', class_='title-20V7ljm-Id').get_text(strip=True).replace("急","")
        publish_time = job.find('span', class_='opened-at-20H_gh2Tqd').get_text(strip=True).replace('发布时间：', '')
        link = job.find('a')['href']
        location = job.find('div', class_='locations-32aEgVWFz_').get_text(strip=True)
        department = job.find('span', class_='status-item-1_w5ygMyMO').get_text(strip=True)
        job_num = ""  # Assuming job number is not provided in the HTML
        job_category = department  # Assuming job category is the same as department
        if "实习" in title or '训练营' in title:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": job_category,
            "hd_hopeworktype" : hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
