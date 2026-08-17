
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='container-aOp138AX_X'):
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']
        hd_dept = card.find('div', class_='sd-Ellipsis-hiddenContainer-3yguc').text.strip()
        hd_loc = card.find_all('div', class_='sd-Ellipsis-hiddenContainer-3yguc')[1].text.strip()
        hd_job_num = card.find('div', class_='short-description-hpQeFUeJUY').text.split('招聘人数：')[-1].split('人')[0].strip()
        hd_job_category = card.find('div', class_='short-description-hpQeFUeJUY').text.split('职位类别：')[-1].split(' ')[0].strip() if '职位类别：' in card.find('div', class_='short-description-hpQeFUeJUY').text else '未知'

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
