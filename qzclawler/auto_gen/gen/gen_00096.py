
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for a_tag in soup.find_all('a'):
        link = a_tag['href']
        title = a_tag.find('span', class_='title').text.strip()
        publish_time = a_tag.find('span', class_='time').text.strip()
        hd_company = ""  # Placeholder for company name, as it's not provided in the HTML

        announcement = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        }
        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)