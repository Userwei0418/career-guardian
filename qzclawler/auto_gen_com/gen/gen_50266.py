import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='bx--card-group__cards__col'):
        # 各字段都用安全提取
        name_tag = card.find('div', class_='bx--card__heading')
        link_tag = card.find('a')
        dept_tag = card.find('div', class_='bx--card__eyebrow')
        loc_tag = card.find('div', class_='ibm--card__copy__inner')

        announcement_name = name_tag.get_text(strip=True) if name_tag else ""
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""
        hd_dept = dept_tag.get_text(strip=True) if dept_tag else ""
        hd_loc = ""
        if loc_tag:
            text = loc_tag.get_text(strip=True)
            # 如果存在换行分隔内容则取第二行，否则整体输出
            parts = [t.strip() for t in text.split('\n') if t.strip()]
            hd_loc = parts[1] if len(parts) > 1 else parts[0] if parts else ""

        # 其他未提供字段设为空
        hd_job_num = ""
        hd_job_category = ""
        publish_time = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
