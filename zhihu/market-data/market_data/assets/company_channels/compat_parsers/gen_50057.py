import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.find_all('div', class_='link-2tgd22te-3')

    for job in job_elements:
        title_div = job.find('div', class_='title-20V7ljm-Id')
        for span in title_div.find_all('span'):
            span.decompose()
        title = title_div.get_text(strip=True)
        link = job.find('a')['href']
        status_items = job.find_all('span', class_='status-item-1_w5ygMyMO')
        hd_dept = status_items[0].get_text(strip=True) if len(status_items) > 0 else ''
        hd_job_category = status_items[1].get_text(strip=True) if len(status_items) > 1 else ''
        hd_loc = job.find('div', class_='locations-32aEgVWFz_').get_text(strip=True) if job.find('div',
                                                                                                 class_='locations-32aEgVWFz_') else ''
        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML

        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Placeholder as the publish time is not provided in the HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
