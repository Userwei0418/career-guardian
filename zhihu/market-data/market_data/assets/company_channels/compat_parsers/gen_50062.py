import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    recruit_items = soup.find_all(class_='recruit-item')

    result_list = []

    for item in recruit_items:
        title = item.find(class_='recruit-title').get_text(strip=True)
        tips = item.find(class_='recruit-tips').get_text(strip=True)
        link = item.find('a', class_='recruit-item-link')['href']

        # Extracting the details from tips
        location, department, job_category, publish_time = tips.split(' | ')

        # Assuming a fixed number for job_num as it is not provided in the HTML
        job_num = ""  # Placeholder value

        result_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result_list, f, ensure_ascii=False, indent=4)
