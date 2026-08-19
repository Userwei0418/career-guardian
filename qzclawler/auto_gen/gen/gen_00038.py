
import json
from bs4 import BeautifulSoup
import bs4

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'): 
        announcement_name = li.find('a', class_='texth').get_text(strip=True)
        publish_time = li.find('span', class_='pull-right time').get_text(strip=True)
        
        jlist = li.find('span', class_='xqzwlist') 
        
        for a in jlist: 
            if isinstance(a, bs4.element.Tag):	
                text = f'{announcement_name} {a.get_text()}' 
                href_value = a.get('href')
             
                announcements.append({
					'announcement_name': text,
					'publish_time': publish_time,
					'link': href_value
				})

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)