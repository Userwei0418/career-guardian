
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for item in soup.find_all('div', class_='positionItem___1ZoV4'):
        announcement_name = item.find('div', class_='positionName___37NrU ellipsis-content').text.strip()
        publish_time = ""  # Assuming there's no publish time in the provided HTML
        link = ""  # Assuming there's no link in the provided HTML
        hd_dept = item.find('div', class_='positionFilterItem___s7iAV ellipsis-content').text.strip().split('｜')[1]
        hd_loc = item.find('div', class_='positionFilterItem___s7iAV ellipsis-content').text.strip().split('｜')[0]
        hd_job_num = ""  # Assuming there's no job number in the provided HTML
        hd_job_category = item.find('div', class_='positionFilterItem___s7iAV ellipsis-content').text.strip().split('｜')[2]
        if "实习" in announcement_name:
            hd_job_hopeworktype = "实习"
        else:
            hd_job_hopeworktype = ""
        position = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_job_hopeworktype": hd_job_hopeworktype
        }
        positions.append(position)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
