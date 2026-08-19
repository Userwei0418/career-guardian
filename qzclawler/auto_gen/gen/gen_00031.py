
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    htmlcontext = htmlcontext.replace('”','')
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []
    
    # Find all list items in the news list
    for li in soup.select('ul.news-list li'):
        # print(li)
        link_tag = li.find('a')
        publish_time_tag = li.find('span')
        
        announcement = {
            "announcement_name": link_tag.get('title', ''),
            "publish_time": publish_time_tag.text.strip() if publish_time_tag else '',
            "link": link_tag.get('href', '')
        }
        
        announcements.append(announcement)
    
    # Write the list to a JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)