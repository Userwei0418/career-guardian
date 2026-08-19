
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []

    for result in soup.find_all('div', class_='resultList'):
        content = result.find('div', class_='content')
        if content:
            announcement_name = content.find('span', class_='col1').get_text(strip=True)
            link = content.find('a')['href'].replace("./","")
            hd_dept = content.find_all('span', class_='col1')[1].get_text(strip=True)
            hd_job_category = content.find_all('span', class_='col3')[0].get_text(strip=True)
            hd_loc = content.find_all('span', class_='col4')[0].get_text(strip=True)
            hd_job_num = content.find_all('span', class_='col5')[0].get_text(strip=True)
            publish_time = content.find('span', class_='time').get_text(strip=True)

            result_dict = {
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            }
            results.append(result_dict)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
