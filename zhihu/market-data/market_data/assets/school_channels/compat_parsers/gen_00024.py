
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.find_all('li', class_='wow fadeInUp animated'):
        announcement_name = li.find('a', class_='texth').text.strip()
        publish_time = li.find('span', class_='pull-right time').text.strip()
        hlink = li.find('a', class_='texth').get('href')
        # 在每个li标签内定位xqzwlist类名对应的span标签元素
#    在每个li标签内查找xqzwlist类名对应的span标签元素
        xqzwlist_span = li.find('span', class_='xqzwlist')
        if xqzwlist_span:
            # 在找到的span标签内查找a标签
            a_tags = xqzwlist_span.find_all('a')
            for a_tag in a_tags:
                url = a_tag.get('href')
                link = "" + url

                #print("gen_000024: ",announcement_name, publish_time, link)    # 输出公告名称、发布时间、链接

                announcements.append({
                    'announcement_name': announcement_name,
                    'publish_time': publish_time,
                    'link': link,
                    "text": a_tag.text.strip()
                })
            if len(a_tags) == 0:
                announcements.append({
                    'announcement_name': announcement_name,
                    'publish_time': publish_time,
                    'link': hlink
                })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)