
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_cards = soup.find_all('div', class_='container-aOp138AX_X')
    
    for card in job_cards:
        link_tag = card.find('a', class_='link-txmgVOCVz9')
        announcement_name = card.find('span', class_='title-u2qk9xX9Ie target-color-container').text.strip()
        publish_time = card.find('span', class_='published-at-PQ5IBWmbJV').text.replace('发布于 ', '').strip()
        hd_loc = card.find('div',class_= 'w-full-mRUtzMQLHs').text.strip()
        # 分割字符串
        segments = hd_loc.split('|')
        print( segments)
        # 去重每一部分
        unique_segments = []
        for segment in segments:
            if segment not in unique_segments:
                unique_segments.append(segment)
        # 合并结果
        if len(unique_segments) > 2:
            hd_loc = unique_segments[2].replace(' ', '')
        else:
            hd_loc ="其他"
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link_tag['href'],
            "hd_dept": "",  # Placeholder as the data is not available in the provided HTML
            "hd_loc": hd_loc,   # Placeholder as the data is not available in the provided HTML
            "hd_job_num": "",  # Placeholder as the data is not available in the provided HTML
            "hd_job_category": ""  # Placeholder as the data is not available in the provided HTML
        }
        
        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
