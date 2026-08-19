import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.select('#joblist tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 5:
            continue

        announcement_name = cols[0].get_text(strip=True)
        hd_dept = cols[1].get_text(strip=True)
        hd_loc = cols[2].get_text(strip=True)
        publish_time = cols[3].get_text(strip=True)
        link = cols[0].find('a')['href']

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Placeholder as the data is not provided in the HTML
            "hd_job_category": ""  # Placeholder as the data is not provided in the HTML
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)


