import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    rows = soup.find_all('div',
                         class_='cc-row cc-slot--wrapper cc-row--flex cc-row--justify__start cc-row--align__top cc-row--width__default')
    print(rows)
    for row in rows:
        print(row)
        announcement_name = row.find('div', class_ = "cc-textblock__body.richtext").get_text(strip=True)
        link =row.find('a')['href']

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": "",
            "hd_dept": "",
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

