import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, tempfile):
    soup = BeautifulSoup(html_content, 'html.parser')
    table_rows = soup.select('#data_html tr')
    
    announcements = []
    
    for row in table_rows:
        publish_time = row.find_all('td')[1].text.strip()
        announcement_name_div = row.find_all('td')[2].find('div')
        announcement_name = announcement_name_div['title'] if announcement_name_div else ''
        link = ''  # The original HTML does not contain a link; you can modify this if links are available.
        
        announcement = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        }
        announcements.append(announcement)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)