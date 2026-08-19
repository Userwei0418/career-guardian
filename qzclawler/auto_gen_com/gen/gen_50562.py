
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for row in soup.find_all('tr', class_='vb1'):
        announcement_name = row.find('td', class_='v_sp1').get_text(strip=True) if row.find('td', class_='v_sp1') else ""
        link = row.find('a')['href'] if row.find('a') else ""
        hd_dept = row.find('td', class_='v_sp2').get_text(strip=True) if row.find('td', class_='v_sp2') else ""
        hd_loc = row.find('td', class_='v_sp3').get_text(strip=True) if row.find('td', class_='v_sp3') else ""
        publish_time = row.find('td', class_='v_sp4').get_text(strip=True) if row.find('td', class_='v_sp4') else ""
        hd_job_num = row.find('td', class_='v_sp5').get_text(strip=True) if row.find('td', class_='v_sp5') else ""
        hd_job_category = ""  # Assuming this field is not present in the provided HTML
        if hd_job_num == "0":
            hd_job_num = ""
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
