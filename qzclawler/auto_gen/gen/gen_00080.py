
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        a_tag = li.find('a')
        span_tag = li.find('span', class_='fr')
        
        if a_tag and span_tag:
            announcement_name = a_tag.get_text(strip=True)
            publish_time = span_tag.get_text(strip=True)
            link = a_tag['href']
            # hd_company = "N/A"  # Placeholder for company name, as it's not provided in the HTML

            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
                # "hd_company": hd_company
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)