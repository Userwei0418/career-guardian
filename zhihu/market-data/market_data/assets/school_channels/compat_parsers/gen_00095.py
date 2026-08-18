
import json
from bs4 import BeautifulSoup
import re

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for text_div in soup.find_all('div', class_='text'):
        link_tag = text_div.find('a')
        if link_tag:
            link = link_tag['href']
            item_div = link_tag.find('div', class_='item')
            if item_div:
                p_tag = item_div.find('p')
                span_tag = item_div.find('span')
                if p_tag and span_tag:
                    announcement_name = p_tag.get_text(strip=True).replace('【招考公告】', '')
                    #\n 替换为空格
                    announcement_name = announcement_name.replace('\n', ' ')
                    #【招考公告\n                                        】2026中国人民银行金融研究所招聘出站博士后2人公告
                    #需要替换以上例子中的招考公告\n                                        】
                    announcement_name = re.sub(r'【.*?】', '', announcement_name)

                    publish_time = span_tag.get_text(strip=True)
                    hd_company = ""  # Assuming company name is not provided in the HTML

                    announcements.append({
                        "announcement_name": announcement_name,
                        "publish_time": publish_time,
                        "link": link,
                        "hd_company": hd_company
                    })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)