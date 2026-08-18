import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    items = soup.find_all(class_='ant-pro-checkcard-body')

    data_list = []
    for item in items:
        title_div = item.find(class_='ant-card-head-title')
        announcement_name = title_div.find(class_='ant-col-24').get_text(strip=True) if title_div else ''

        publish_time_div = item.find(class_='ant-col-6')
        publish_time = publish_time_div.get_text(strip=True) if publish_time_div else ''

        company_div = item.find(class_='ant-list-item-meta-title')
        hd_company = company_div.find(class_='ant-col-24').get_text(strip=True) if company_div else ''

        # 假设链接需从标题的a标签获取，若实际HTML中标题无链接，需调整获取方式
        link = title_div.find('a', href=True)['href'] if title_div.find('a', href=True) else ''

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_company": hd_company
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)