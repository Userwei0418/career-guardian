import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.select('#data_html .item')
    
    result = []
    
    for item in items:
        announcement_name = item.select_one('.item-tit .item-link').get('title')
        publish_time = item.select_one('.item-other .io-inner .io-text').text
        link = item.select_one('.item-tit .item-link').get('href')
        hd_company = ""  # Assuming the company name is constant as per the provided HTML
        
        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)