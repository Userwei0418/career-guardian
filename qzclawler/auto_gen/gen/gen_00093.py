
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul#boxNewsList > li.sumary_list'):
        title_tag = li.select_one('a.titleSet')
        if title_tag:
            announcement_name = title_tag.get_text(strip=True)
            link = f"https://www.bucmdf.edu.cn/{title_tag['href']}"
            # Assuming publish_time and hd_company are not available in the provided HTML
            publish_time = None
            hd_company = None
            
            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_company": hd_company
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)