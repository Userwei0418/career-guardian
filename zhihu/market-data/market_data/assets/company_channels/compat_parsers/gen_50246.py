
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr', class_='ant-table-row')

    data_list = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 7:
            announcement_name = cells[1].get_text(strip=True)
            link = cells[1].find('a')['href']
            hd_dept = cells[3].get_text(strip=True)
            hd_loc = cells[4].get_text(strip=True)
            hd_job_num = cells[5].get_text(strip=True)
            publish_time = cells[6].get_text(strip=True)
            hd_job_category = cells[2].get_text(strip=True)  # Assuming this is the correct index for job category

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
