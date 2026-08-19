
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag:
            announcement_name = a_tag.find('b').text.strip() if a_tag.find('b') else ""
            publish_time = a_tag.find_all('span')[5].text.strip() if len(a_tag.find_all('span')) > 5 else ""
            link = a_tag['data-url'] if 'data-url' in a_tag.attrs else ""
            hd_dept = a_tag.find_all('span')[2].text.strip() if len(a_tag.find_all('span')) > 2 else ""
            hd_loc = a_tag.find_all('span')[3].text.strip() if len(a_tag.find_all('span')) > 3 else ""
            hd_job_num = a_tag.find_all('span')[4].text.strip() if len(a_tag.find_all('span')) > 4 else ""
            hd_job_category = a_tag.find_all('span')[1].text.strip() if len(a_tag.find_all('span')) > 1 else ""

            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": "",
                "hd_loc": "",
                "hd_job_num": hd_job_num,
                "hd_job_category": ""
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
