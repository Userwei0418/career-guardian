import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('a', class_='PositionList__job-item')

    job_list = []

    for job in job_items:
        announcement_name = job.get('title', '')
        link = job.get('href', '')
        job_content = job.find('div', class_='PositionList__job-item-content')

        if job_content:
            job_title = job_content.find('h4', class_='job-title').get_text(strip=True) if job_content.find('h4',
                                                                                                            class_='job-title') else ""
            job_desc = job_content.find('p', class_='job-desc')
            if job_desc:
                job_desc_items = job_desc.find_all('span', class_='job-desc-item')
                hd_loc = job_desc_items[0].get_text(strip=True) if len(job_desc_items) > 0 else ""
                hd_job_num = job_desc_items[1].get_text(strip=True) if len(job_desc_items) > 1 else ""
                hd_job_category = job_title  # Assuming job title is the job category
            else:
                hd_loc = ""
                hd_job_num = ""
                hd_job_category = ""
        else:
            hd_loc = ""
            hd_job_num = ""
            hd_job_category = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming no publish time is available in the provided HTML
            "link": link,
            "hd_dept": "",  # Assuming no department is available in the provided HTML
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)


