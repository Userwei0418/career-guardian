
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    cards = soup.select('div.list-card-item1')
    for card in cards:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称
        title_span = card.select_one('div.pos-title-item > span.top-label')
        if title_span:
            announcement_name = title_span.get_text(strip=True)

        # 所属部门或机构 和 工作地点
        pos_summary = card.select_one('div.pos-summary')
        if pos_summary:
            # 部门和地点都在title属性里，用" | "分割
            title_attr = pos_summary.get('title', '')
            parts = [p.strip() for p in title_attr.split('|')]
            if len(parts) >= 1:
                hd_dept = parts[0]
            if len(parts) >= 2:
                hd_loc = parts[1]

        # 发布时间 和 招聘人数
        pos_ft = card.select_one('div.pos-ft')
        if pos_ft:
            pub_span = pos_ft.select_one('span.pub-time')
            if pub_span:
                # 格式如 "更新日期：2026-05-08"
                publish_time = pub_span.get_text(strip=True).replace('更新日期：', '')
            need_span = pos_ft.select_one('span.need-people')
            if need_span:
                # 格式如 "招聘人数：若干"
                hd_job_num = need_span.get_text(strip=True).replace('招聘人数：', '')

        # 链接：从id属性拼接，id在list-card-item1的div上
        card_id = card.get('id', '')
        if card_id:
            link = f"https://example.com/job/{card_id}"  # 这里假设链接格式，html中无链接信息，故自定义

        # 职位类别字段html中无明确字段，赋空字符串
        hd_job_category = ""

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
        json.dump(results, f, ensure_ascii=False, indent=2)
`