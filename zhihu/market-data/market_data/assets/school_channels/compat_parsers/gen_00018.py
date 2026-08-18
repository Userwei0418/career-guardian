import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('#tabGrid tbody tr')

    announcements = []

    for row in rows:
        announcement_name = row.find('td').find('a').text
        link = row.find('td').find('a')['href']
        company_name = row.find_all('td')[1].text
        publish_time = row.find_all('td')[2].text

        announcement = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": company_name
        }

        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)