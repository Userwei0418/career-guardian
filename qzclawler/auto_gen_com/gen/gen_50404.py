import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0')

    for item in job_items:
        title = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4').get_text(strip=True)
        publish_time = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16').get_text(strip=True).replace(
            ' 发布', '')
        link = ''  # Assuming link is not provided in the HTML snippet
        hd_dept = ''  # Assuming department is not provided in the HTML snippet
        hd_loc = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[2].get_text(strip=True)
        hd_job_num = ''  # Assuming job number is not provided in the HTML snippet
        hd_job_category = item.find('div', class_='style__STJobLabel-editor__sc-10r1nhd-12 jALFTx').get_text(strip=True)

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

