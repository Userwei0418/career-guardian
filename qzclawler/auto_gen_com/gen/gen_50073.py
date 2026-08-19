
import json
import re

from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('a', class_='result_item'):
        announcement_name = item.find('div', class_='title').get_text(strip=True)
        raw_time = item.find('div', class_='cb-f-r').get_text(strip=True)
        m = re.search(r'\d{4}-\d{2}-\d{2}', raw_time)
        publish_time = m.group(0) if m else ""
        link = item['href']
        hd_dept = item.find('div', class_='text_div text_div1').get_text(strip=True)

        color_div = item.find('div', class_='color999')
        # 删除内部更新时间的 div
        cb = color_div.find('div', class_='cb-f-r')
        if cb:
            cb.decompose()
        text_clean = color_div.get_text(strip=True)

        # 拆分 "职位类别 | 地区"
        parts = [p.strip() for p in text_clean.split('|')]
        hd_job_category = parts[0] if len(parts) > 0 else ""
        hd_loc = parts[1] if len(parts) > 1 else ""

        hd_job_num = ""  # 假设 HTML 没提供编号

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_job_category": hd_job_category,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
