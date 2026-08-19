import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = [row for row in soup.find_all('tr') if len(row.find_all('td')) >= 7]

    data_list = []

    for row in rows:
        cells = row.find_all('td')
        announcement_name = cells[0].get_text(strip=True)
        hd_loc = cells[1].get_text(strip=True)
        hd_dept = cells[2].get_text(strip=True)
        hd_job_category = cells[3].get_text(strip=True)
        hd_job_num = cells[4].get_text(strip=True)
        publish_time = cells[5].get_text(strip=True)

        # 如果有 a 标签提取 href
        link_tag = cells[0].find('a')
        link = link_tag['href'] if link_tag else ''

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
