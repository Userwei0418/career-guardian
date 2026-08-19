import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    info_lists = soup.find_all('ul', class_='infoList')
    for info in info_lists:
        announcement_name_tag = info.find('li', class_='span7').find('a')
        publish_time_tag = info.find('li', class_='span4')
        
        if announcement_name_tag and publish_time_tag:
            announcement_name = announcement_name_tag.text.strip()
            publish_time = publish_time_tag.text.strip()
            link = announcement_name_tag['href']
            
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)