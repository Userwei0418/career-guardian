
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.am-table tbody tr')
    
    announcements = []
    
    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) >= 4:
            announcement_name = cols[0].find('a').text.strip()
            publish_time = cols[3].text.strip()
            link = cols[0].find('a')['href']
            company_name = ""
            if cols[1].find('a'):
                company_name = cols[1].find('a').text.strip()
            
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_company": company_name
            })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)