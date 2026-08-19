
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_listings = []

    for item in soup.find_all('div', class_='zwlist'):
        announcement_name = item.find_all('li')[2].get_text(strip=True)
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = item.find_all('li')[2].find('a')['href']
        hd_dept = item.find_all('li')[1].get_text(strip=True)
        hd_loc = item.find_all('li')[2].find('samp').get_text(strip=True).strip('()')
        hd_job_num = item.find_all('li')[5].get_text(strip=True)
        hd_job_category = item.find_all('li')[3].get_text(strip=True)

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
