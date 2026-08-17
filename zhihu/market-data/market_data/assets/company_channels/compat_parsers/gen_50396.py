import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='list-card-item1'):
        # 容错处理，每个字段都用 try-except 或 getattr-like 方法
        def safe_text(selector, default=""):
            if selector:
                return selector.text.strip()
            return default

        announcement_name = safe_text(card.find('span', class_='top-label'))
        publish_time = safe_text(card.find('span', class_='pub-time')).replace('发布时间：', '')
        link = ""  # 如果 HTML 没有 a 标签就保留空
        pos_summary = card.find('div', class_='pos-summary')
        if pos_summary:
            spans = pos_summary.find_all('span')
            hd_dept = safe_text(spans[0]) if len(spans) > 0 else ""
            hd_loc = safe_text(pos_summary.find('span', class_='work-place')).replace('|','')
        else:
            hd_dept = ""
            hd_loc = ""
        hd_job_num = safe_text(card.find('span', class_='need-people')).replace('招聘人数：', '')
        hd_job_category = safe_text(card.find('span', class_='pos-cate'))

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
