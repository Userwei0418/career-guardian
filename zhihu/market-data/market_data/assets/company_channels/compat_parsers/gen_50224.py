
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag:
            announcement_name = a_tag.find('span', class_='job').text.strip()
            hd_dept = a_tag.find_all('span', class_='same')[0].text.strip()
            hd_loc = a_tag.find_all('span', class_='same')[1].text.strip()
            hd_job_category = a_tag.find('span', class_='kind').text.strip()
            hd_job_num = a_tag.find_all('span', class_='same')[5].text.strip()
            publish_time = a_tag.find_all('span', class_='same')[6].text.strip()
            link = a_tag['href']
            if "实习" in announcement_name:
                hd_hopeworktype = "实习"
            else:
                hd_hopeworktype = ""
            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": "",
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category,
                "hd_hopeworktype": hd_hopeworktype,
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
