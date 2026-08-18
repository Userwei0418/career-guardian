
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for li in soup.select('ul.second_right_ul li'):
        announcement_name = li.a.get_text(strip=True)
        link = li.a['href']
        #link 的实例： ./202508/t20250828_9946784.shtml
        #添加前缀https://rst.shanxi.gov.cn/ztzl/zpxx/szsydwzpgg
        link = "https://rst.shanxi.gov.cn/ztzl/zpxx/szsydwzpgg/" + link.lstrip('./')

        publish_time = li.span.get_text(strip=True)
        hd_company = "山西省"  # Assuming the company name is "山西省" based on the context

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)