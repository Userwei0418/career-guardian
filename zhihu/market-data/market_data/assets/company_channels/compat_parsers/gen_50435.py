
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job_card in soup.find_all('div', class_='container-aOp138AX_X'):
        job_info = {}
        link_tag = job_card.find('a', class_='link-txmgVOCVz9')
        job_info['link'] = link_tag['href']

        title = job_card.find('span', class_='title-u2qk9xX9Ie').text
        job_info['announcement_name'] = title

        # Assuming publish_time is not available in the provided HTML
        job_info['publish_time'] = ""

        details = job_card.find('div', class_='info-tPG_0QGbhl')
        salary = details.find('div', class_='salary-AOKS3Ocnck').text
        job_info['hd_job_num'] = details.find_all('div', class_='sd-Ellipsis-hiddenContainer-3yguc')[-2].text.strip()
        job_info['hd_loc'] = details.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')[-1].text.strip()

        # Extracting department and job category
        job_info['hd_dept'] =""
        job_info['hd_job_category'] = details.find_all('div', class_='sd-foundation-body-secondary-1Z7H-')[1].text.strip()

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
