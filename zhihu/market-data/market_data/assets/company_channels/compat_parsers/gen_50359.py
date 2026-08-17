
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0 cEVsnE')

    for item in job_items:
        title = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4 epmacU').get_text(strip=True)
        time = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16 eKeZsF').get_text(strip=True).replace(' 发布', '')
        location = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[2].get_text(strip=True)
        department = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[3].get_text(strip=True)
        job_num = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[4].get_text(strip=True)
        job_category = item.find_all('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')[0].get_text(strip=True)

        job_data = {
            "announcement_name": title,
            "publish_time": time,
            "link": "",  # Assuming no link is provided in the HTML
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": "",
            "hd_job_category": ""
        }

        job_list.append(job_data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
