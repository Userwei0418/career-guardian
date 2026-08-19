import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.find_all('tr', class_='tr_dom')
    for row in rows:
        announcement_name = row.find('a', class_='w280 hidden-text').get('title', '') if row.find('a',
                                                                                                  class_='w280 hidden-text') else ""
        link = row.find('a', class_='w280 hidden-text').get('href', '') if row.find('a',
                                                                                    class_='w280 hidden-text') else ""
        hd_dept = row.find_all('a')[2].get('title', '') if len(row.find_all('a')) > 2 else ""
        hd_job_category = row.find_all('a')[3].get('title', '') if len(row.find_all('a')) > 3 else ""
        hd_loc = row.find_all('a')[4].get('title', '') if len(row.find_all('a')) > 4 else ""
        publish_time = row.find_all('a')[5].get_text(strip=True) if len(row.find_all('a')) > 5 else ""

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming this field is not present in the provided HTML
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
