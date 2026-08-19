
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all(class_='items')
    result = []

    for item in items:
        announcement_name = item.find(class_='info').find('p').get_text(strip=True) if item.find(class_='info') else ""
        publish_time = item.find(class_='time').find('p').get_text(strip=True) if item.find(class_='time') else ""
        link = ""  # Assuming the link is not provided in the HTML snippet
        hd_dept = item.find(class_='dept').find('p').get_text(strip=True) if item.find(class_='dept') else ""
        hd_loc = item.find(class_='types').find_all('p')[0].get_text(strip=True) if item.find(class_='types') else ""
        hd_job_num = item.find(class_='types').find_all('p')[1].get_text(strip=True).replace("招聘", "").replace("人", "").strip() if item.find(class_='types') else ""
        hd_job_category = ""  # Assuming job category is not provided in the HTML snippet

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
