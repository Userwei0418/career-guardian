
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag:
            job_info = {
                "announcement_name": a_tag.find_all('span')[1].text.strip() if len(a_tag.find_all('span')) > 1 else "",
                "publish_time": "",  # No publish time in the provided HTML
                "link": a_tag['href'] if 'href' in a_tag.attrs else "",
                "hd_dept": "",
                "hd_loc": a_tag.find_all('span')[3].text.strip() if len(a_tag.find_all('span')) > 3 else "",
                "hd_job_num": "",  # No job number in the provided HTML
                "hd_job_category": a_tag.find_all('span')[0].text.strip() if len(a_tag.find_all('span')) > 0 else ""
            }
            job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
