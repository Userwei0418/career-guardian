
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        span_tag = li.find('span')
        
        announcement_name = a_tag.get('title')
        publish_time = span_tag.text
        link = a_tag.get('href')
        hd_company = ""#a_tag.text  # Assuming company name is the same as announcement name for this context
        
        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)