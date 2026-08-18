
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li'):
        if li.get('style') != 'display:none':
            publish_time = li.find('span').text.strip()
            link_tag = li.find_all('a')[1]
            announcement_name = link_tag['title']
            #踢掉[招聘公告] 为 “”
            announcement_name = announcement_name.replace('招聘公告', '')

            #https://
            link = link_tag['href']
            #添加https://
            if link.startswith('//'):
                link = 'https:' + link

            hd_company = '' #link_tag.find_previous('a', class_='lh_olistCatename').text.strip()

            announcements.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_company": hd_company
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)