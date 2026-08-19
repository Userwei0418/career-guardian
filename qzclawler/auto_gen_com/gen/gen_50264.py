
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for job in soup.find_all('div', class_='w-100 flex flex-row flex-wrap bb b--gray0 justify-center pv1'):
        announcement_name = job.find('a', class_='inline-link-style f4 fw7 lh-title').text.strip()
        link = job.find('a', class_='inline-link-style f4 fw7 lh-title')['href']
        hd_dept = job.find_all('div', class_='w-75 w-75-m w-60-l')[0].text.strip()
        hd_loc = job.find_all('div', class_='w-25 w-25-m w-40-l')[0].text.strip()
        hd_job_num = ""  # Placeholder as the HTML does not provide this information
        hd_job_category = ""  # Placeholder as the HTML does not provide this information

        job_listings.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Placeholder as the HTML does not provide this information
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w') as json_file:
        json.dump(job_listings, json_file, ensure_ascii=False, indent=4)
