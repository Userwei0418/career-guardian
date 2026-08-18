
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('li', class_='detail-item'):
        announcement_name = item.find('h2').text.strip()
        item1 = item.find('div', class_='item-down')
        pdivs = item1.find('div', class_='flex').find_all('div')
        publish_time =  ""
        if pdivs:
            publish_time = pdivs[-1].text.strip()
        link = ''  # Assuming no link is provided in the HTML context

        job_list.append({
            'announcement_name': announcement_name,
            'publish_time': publish_time,
            'link': link
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)