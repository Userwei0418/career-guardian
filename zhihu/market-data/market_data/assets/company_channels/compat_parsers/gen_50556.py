
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.find_all('tr', class_='tr_dom')

    data_list = []

    for row in rows:
        announcement_name = row.find('td', align='left').find('b').text if row.find('td', align='left') else ""
        link = row.find('td', align='left').find('a')['href'] if row.find('td', align='left') and row.find('td', align='left').find('a') else ""
        hd_dept = row.find_all('td')[2].text if len(row.find_all('td')) > 2 else ""
        hd_job_category = row.find_all('td')[3].text if len(row.find_all('td')) > 3 else ""
        hd_loc = row.find_all('td')[4].text if len(row.find_all('td')) > 4 else ""
        publish_time = row.find_all('td')[5].text if len(row.find_all('td')) > 5 else ""
        hd_job_num = ""  # Assuming this field is not present in the provided HTML structure

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
