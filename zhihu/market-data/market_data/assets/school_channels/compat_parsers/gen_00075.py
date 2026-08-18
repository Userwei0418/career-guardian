
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for item in soup.select('.wp_article_list .list_item'):
        title_tag = item.select_one('.Article_Title a')
        publish_date_tag = item.select_one('.Article_PublishDate')

        announcement = {
            "announcement_name": title_tag['title'],
            "publish_time": publish_date_tag.text,
            "link": title_tag['href'],
            "hd_company": ""  # Assuming company name is not provided in the HTML
        }
        announcements.append(announcement)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)