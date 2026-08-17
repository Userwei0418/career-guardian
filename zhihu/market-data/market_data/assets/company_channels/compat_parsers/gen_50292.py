
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='cmp-teaser card')

    for job in job_cards:
        announcement_name = job.find('h3', class_='cmp-teaser__title').text.strip()
        publish_time = job.find('p', class_='cmp-teaser__job-listing cmp-teaser__job-listing-posted-date').text.strip()
        link = job.find('a', class_='cmp-teaser__title-link')['href']
        hd_dept = job.find('div', class_='cmp-teaser__pretitle cmp-teaser__address-location').find_all('div')[0].text.strip()
        hd_loc = job.find('div', class_='cmp-teaser__pretitle cmp-teaser__address-location').find_all('div')[1].text.strip()
        hd_job_num = job.find('div', class_='cmp-teaser__description').find('span', class_='cmp-teaser__job-listing-semibold skill').text.strip()
        hd_job_category = job.find('p', class_='cmp-teaser__job-listing cmp-teaser__job-listing-business-area').text.strip()
        if announcement_name == '':
            break
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": link,
            "hd_dept": hd_job_num,
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
