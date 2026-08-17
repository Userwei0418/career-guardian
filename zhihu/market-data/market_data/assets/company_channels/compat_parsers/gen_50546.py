
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all('div', class_='join-b3-item')

    result = []

    for item in items:
        announcement_name = item.find('p', class_='tc-df fz5 fw5').get_text(strip=True) if item.find('p', class_='tc-df fz5 fw5') else ""
        link = item.find('a')['href'] if item.find('a') else ""
        publish_time = ""  # Placeholder as the HTML does not contain this information
        hd_dept = ""  # Placeholder as the HTML does not contain this information
        hd_loc = ""  # Placeholder as the HTML does not contain this information
        hd_job_num = ""  # Placeholder as the HTML does not contain this information
        hd_job_category = ""  # Placeholder as the HTML does not contain this information

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
