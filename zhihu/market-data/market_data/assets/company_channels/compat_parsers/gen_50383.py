
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # Extracting job information
    for slick_slide in soup.find_all('div', class_='slick-slide'):
        department = slick_slide.find('div', class_='p1').text.strip()
        job_links = slick_slide.find('div', class_='p2').find_all('a')

        for job in job_links:
            job_info = {
                "announcement_name": job.text.strip(),
                "publish_time": "",  # Placeholder, as the HTML does not provide this information
                "link": job['href'],
                "hd_dept": department,
                "hd_loc": "",  # Placeholder, as the HTML does not provide this information
                "hd_job_num": "",  # Placeholder, as the HTML does not provide this information
                "hd_job_category": ""  # Placeholder, as the HTML does not provide this information
            }
            job_list.append(job_info)

    # Writing to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
