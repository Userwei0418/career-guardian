
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.l-list-no > li'):
        
        linki_tag = li.find('i')
        announcement_name = linki_tag['title']
        link_tag = li.find('a')
        company_name = link_tag['title']
        link = link_tag['href']
        publish_time = li.find('span').text.strip()
        

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": company_name
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)