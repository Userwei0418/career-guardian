
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    items = soup.select('div.list-card-item1')
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称
        title_span = item.select_one('div.pos-title-item > span.top-label')
        if title_span:
            announcement_name = title_span.get_text(strip=True)

        # 发布时间
        pub_span = item.select_one('div.pos-ft span.pub-time')
        if pub_span:
            publish_time = pub_span.get_text(strip=True).replace("更新日期：", "")

        # 链接 (从id拼接成链接，假设链接格式为某种固定格式)
        # 题目中未给出链接格式，故赋空字符串
        link = ""

        # 所属部门或机构 和 工作地点
        pos_summary = item.select_one('div.pos-summary')
        if pos_summary and pos_summary.has_attr('title'):
            title_text = pos_summary['title']
            parts = [p.strip() for p in title_text.split('|')]
            if len(parts) >= 1:
                hd_dept = parts[0]
            if len(parts) >= 2:
                hd_loc = parts[1]

        # 招聘人数（html中无相关字段，赋空字符串）
        hd_job_num = ""

        # 职位类别
        cate_span = item.select_one('div.pos-tag-item > span.pos-cate')
        if cate_span:
            hd_job_category = cate_span.get_text(strip=True)

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)