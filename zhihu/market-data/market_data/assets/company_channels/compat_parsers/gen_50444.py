
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for link in soup.find_all('a', class_='link'):
        title = link.find('div', class_='title').get_text(strip=True)
        requirements = link.find('div', class_='require')
        job_category = requirements.find_all('p')[0].get_text(strip=True).replace('岗位类别: ', '')
        location = requirements.find_all('p')[1].get_text(strip=True).replace('工作城市: ', '')
        job_num = requirements.find_all('p')[2].get_text(strip=True).replace('招聘人数: ', '')
        announcement_link = link['href']

        announcement = {
            "announcement_name": title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": announcement_link,
            "hd_dept": "",  # Assuming hd_dept is not available in the provided HTML
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": job_category
        }

        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
