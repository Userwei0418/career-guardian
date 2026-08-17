
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for item in soup.find_all('a', class_='portal-list-card-item'):
        announcement_name = item.find('div', title=True).get('title', '') if item.find('div', title=True) else ""
        publish_time = item.find('span', class_='slds-col_bump-left slds-text-body_small slds-text-color--inverse-weak mobile-hide portal-list-card-item-tag position-data')
        publish_time = publish_time.get_text().replace('发布日期: ', '') if publish_time else ""
        link = item.get('href', '')
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        tags = item.find_all('span', class_='slds-text-body_small portal-list-card-item-tag')
        print(tags)
        if tags:
            hd_job_category = tags[0].get_text() if len(tags) > 0 else ""
            hd_loc = tags[1].get_text() if len(tags) > 1 else ""

        job_listings.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_listings, f, ensure_ascii=False, indent=4)
