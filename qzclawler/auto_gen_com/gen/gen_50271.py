
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='card-item-wrap col-3'):
        title_div = item.find('div', class_='pos-title-item')
        summary_div = item.find('div', class_='pos-summary')
        pub_time_span = item.find('span', class_='pub-time')

        announcement_name = title_div.get('title', '').strip() if title_div else ''
        publish_time = pub_time_span.get_text(strip=True).replace('发布时间：', '') if pub_time_span else ''
        link = ''  # Assuming link is not provided in the HTML
        hd_dept = summary_div.get('title', '').strip() if summary_div else ''
        hd_loc = summary_div.get_text(strip=True) if summary_div else ''
        hd_job_num = ''  # Assuming job number is not provided in the HTML
        hd_job_category = ''  # Assuming job category is not provided in the HTML

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
