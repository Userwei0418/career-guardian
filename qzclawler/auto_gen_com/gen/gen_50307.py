
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    rows = soup.select('.phoenixTableRowLayout_bodyRow')
    for row in rows:
        announcement_name = row.select_one('.styled__jobName-editor__sc-i00twi-0').get_text(strip=True)
        publish_time = ""  # Assuming this information is not present in the provided HTML
        link = ""  # Assuming this information is not present in the provided HTML
        hd_dept = ""  # Assuming this information is not present in the provided HTML
        hd_loc = row.select_one('.phoenixTableCellLayout_main').get_text(strip=True)
        hd_job_num = ""  # Assuming this information is not present in the provided HTML
        hd_job_category = row.select_one('.phoenixTableCellLayout_main:nth-of-type(2)').get_text(strip=True)

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
