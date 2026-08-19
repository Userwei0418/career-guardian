import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('div', class_='job-item')

    job_list = []

    for item in job_items:
        announcement_name = item.find('div', class_='job-title').text.strip() if item.find('div',
                                                                                           class_='job-title') else ""
        publish_time = ""  # No publish time in the provided HTML
        link = item.find('a', class_='apply-btn')['href'] if item.find('a', class_='apply-btn') else ""
        hd_dept = ""  # No department info in the provided HTML
        hd_loc = ""  # No location info in the provided HTML
        hd_job_num = item.find('div', class_='job-count').text.strip() if item.find('div', class_='job-count') else ""
        hd_job_category = item.find('div', class_='job-requirements').text.strip() if item.find('div',
                                                                                                class_='job-requirements') else ""

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


