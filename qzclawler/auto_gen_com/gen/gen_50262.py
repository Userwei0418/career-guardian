import json
from bs4 import BeautifulSoup

from datetime import datetime
def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.select('li[data-qa="searchResultItem"]') or soup.select('.job-grid-item')

    for job in job_items:
        title = job.find('span', class_='job-tile__title')
        link_tag = job.find('a', class_='job-grid-item__link')
        publish_time = job.select_one('.job-list-item__job-info-label--posting-date + div')
        date = publish_time.text.strip() if publish_time else ""
        date_obj = datetime.strptime(date, "%m/%d/%Y")
        new_date_str = date_obj.strftime("%Y/%m/%d")
        hd_dept = job.select_one('.job-list-item__job-info-label--locations')
        hd_loc = job.select_one('.job-list-item__job-info-value')
        hd_job_category = job.find('p', class_='job-grid-item__description')

        job_data = {
            "announcement_name": title.text.strip() if title else "",
            "publish_time":new_date_str,
            "link": link_tag['href'] if link_tag and link_tag.has_attr('href') else "",
            "hd_dept": "",
            "hd_loc": hd_loc.text.strip().replace('\n','') if hd_loc else "",
            "hd_job_category": ""
        }

        job_list.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)


