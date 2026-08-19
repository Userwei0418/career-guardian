
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')
    
    for card in job_cards:
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        link = card.find('a')['href']
        info_div = card.find('div', class_='info-tPG_0QGbhl')
        info_parts = info_div.text.split('|')
        
        hd_dept = info_parts[0].strip() if len(info_parts) > 0 else ''
        hd_loc = info_parts[-1].strip() if len(info_parts) > 3 else ''
        hd_job_num = ''  # Placeholder as the job number is not provided in the HTML
        hd_job_category = info_parts[2].strip() if len(info_parts) > 2 else ''
        
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
