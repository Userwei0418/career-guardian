
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('tbody.job-index-list-body tr')
    for row in rows:
        announcement_name = row.find('a').text.strip()
        link = row.find('a')['href']
        hd_dept = ''  # Assuming this information is not available in the provided HTML
        hd_loc = row.find_all('td')[2].text.strip()
        hd_job_num = row.find_all('td')[3].text.strip() or '若干'
        publish_time = row.find_all('td')[4].text.strip()
        hd_job_category = row.find_all('td')[1].text.strip()

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
