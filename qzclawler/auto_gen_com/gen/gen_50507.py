
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li', class_=['one', 'two']):
        dl = li.find('dl')
        if dl:
            announcement_name = dl.find_all('dt')[0].get_text(strip=True) if len(dl.find_all('dt')) > 0 else ""
            hd_loc = dl.find_all('dt')[1].get_text(strip=True) if len(dl.find_all('dt')) > 1 else ""
            hd_job_num = dl.find_all('dt')[2].get_text(strip=True) if len(dl.find_all('dt')) > 2 else ""
            publish_time = dl.find_all('dt')[3].get_text(strip=True) if len(dl.find_all('dt')) > 3 else ""
            link = dl.find_all('dt')[4].find('a')['href'] if len(dl.find_all('dt')) > 4 and dl.find_all('dt')[4].find('a') else ""

            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": "",
                "link": link,
                "hd_dept": "",  # No data available in the provided HTML
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": ""  # No data available in the provided HTML
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
