import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.select('.zp_list_li'):
        link = item.find('a', class_='eName')['href']
        title = item.find('div', class_='zp_list_li_title').text.strip()
        date_month = item.find('div', class_='date').find('div', class_='month').text.strip()
        date_year = item.find('div', class_='date').find('div', class_='year').text.strip()
        publish_time = f"{date_year}-{date_month}"

        announcements.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as json_file:
        json.dump(announcements, json_file, ensure_ascii=False, indent=4)