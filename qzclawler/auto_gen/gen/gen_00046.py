
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        if a_tag:
            link = a_tag['href']
            if link.startswith('../'):
                link = link.replace('../', '/')
            job_info = li.find('div', class_='jobtext').find('p', class_='jobinfo').text.strip()
            contents = li.find('span', class_='jobxjht').contents 
            publish_time = f'{contents[1].text.strip()}-{contents[0].strip()}'
            announcement_name = job_info
            
            data_list.append({
                'announcement_name': announcement_name,
                'publish_time': publish_time,
                'link': link
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)