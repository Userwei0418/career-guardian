
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        announcement_name = li.find('span', class_='article').get_text(strip=True)
        link = li.find('a')['href']
        publish_time = li.find('span', style='float:right').get_text(strip=True)
        hd_company = ""  # Assuming company name is not provided in the HTML

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)