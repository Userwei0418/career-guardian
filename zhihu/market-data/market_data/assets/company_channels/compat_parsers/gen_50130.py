
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li', class_='border-top'):
        a_tag = li.find('a')
        announcement_name = a_tag.find('h6').text.strip()
        link = a_tag['href']
        hd_loc = a_tag.find_all('p')[0].text.strip()
        hd_dept = ""
        hd_job_category = a_tag.find_all('div')[2].text.strip()

        # Assuming publish_time and hd_job_num are not available in the provided HTML
        publish_time = ""
        hd_job_num = ""

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
