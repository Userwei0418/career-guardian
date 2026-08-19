
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table tbody tr')
    
    extracted_data = []
    
    for row in table_rows:
        announcement_name = row.find('td').find('a').text
        company_name = row.find_all('td')[1].text
        publish_time = row.find_all('td')[2].text
        link = row.find('td').find('a')['href']
        
        extracted_data.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": company_name
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, ensure_ascii=False, indent=4)