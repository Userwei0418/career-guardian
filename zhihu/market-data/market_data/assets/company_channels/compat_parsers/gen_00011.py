
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('a', attrs={'data-id': True})

    results = []
    base_url = ""#"https://careers.bytedance.com"  # 可根据实际情况调整

    for job in job_items:
        title_tag = job.find('span', class_='positionItem-title-text')
        location_tag = job.find('div', class_='subTitle__3sRa3')
        link = job.get('href', '')

        announcement_name = title_tag.get_text(strip=True) if title_tag else ''
        hd_loc = location_tag.find_all('span')[0].get_text(strip=True) if location_tag else ''
        hd_job_category = location_tag.find('span', class_='infoText-category__25NLe')
        hd_job_category = hd_job_category.get_text(strip=True) if hd_job_category else ''

        job_data = {
            "announcement_name": announcement_name,
            "publish_time": "",  # HTML 中未提供
            "link": base_url + link,
            "hd_dept": "",  # HTML 中未提供
            "hd_loc": hd_loc,
            "hd_job_num": "",  # HTML 中未提供
            "hd_job_category": hd_job_category
        }
        results.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
