
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.select('ul.ul > li'):
        title = li.find('span', class_='tit').text.strip()
        base_info = li.find('span', class_='base').text.strip()
        location = base_info.split('：')[1].replace("、",',') if '：' in base_info else ''
        link = li.find('a', class_='more')['href']
        hd_hope_worktype = ""
        if "实习" in title:
            hd_hope_worktype = "实习"
        else:
            hd_hope_worktype = ""

        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": "",  # Assuming hd_dept is not available in the provided HTML
            "hd_loc": location,
            "hd_job_num": "",  # Assuming hd_job_num is not available in the provided HTML
            "hd_job_category": "",  # Assuming hd_job_category is not available in the provided HTML
            "hd_hopeworktype":hd_hope_worktype
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
