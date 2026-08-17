
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody.postListTbody tr')
    data_list = []

    for row in rows:
        announcement_name = row.find('td', style="cursor: pointer; width: 300px;").get('title', "")
        hd_job_category = ""
        hd_job_num = row.find_all('td')[2].text.strip() if len(row.find_all('td')) > 2 else ""
        hd_loc = row.find_all('td')[3].get('title', "")
        publish_time = row.find_all('td')[4].text.strip() if len(row.find_all('td')) > 4 else ""
        link = f"javascript:void(0);"  # Placeholder for the link, as the actual link is not provided in the HTML
        if '实习' in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # No data available in the provided HTML
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category,
            "hd_hopeworktype": hd_hopeworktype
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
