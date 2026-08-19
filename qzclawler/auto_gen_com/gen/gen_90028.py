
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []
    items = soup.select("div.card-item-wrap.col-3 > div.list-card-item")
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称
        pos_title_item = item.select_one("div.pos-title-item")
        if pos_title_item and pos_title_item.has_attr("title"):
            announcement_name = pos_title_item["title"].strip()
        elif pos_title_item:
            announcement_name = pos_title_item.get_text(strip=True)

        # 职位类别
        pos_cate = item.select_one("span.pos-cate")
        if pos_cate and pos_cate.has_attr("title"):
            hd_job_category = pos_cate["title"].strip()
        elif pos_cate:
            hd_job_category = pos_cate.get_text(strip=True)

        # 工作地点
        pos_summary = item.select_one("div.pos-summary")
        if pos_summary and pos_summary.has_attr("title"):
            hd_loc = pos_summary["title"].strip()
        else:
            # 有些pos-summary内有多个span，尝试拼接span文本
            if pos_summary:
                spans = pos_summary.find_all("span")
                locs = []
                for sp in spans:
                    text = sp.get_text(strip=True)
                    if text:
                        locs.append(text)
                hd_loc = " | ".join(locs)

        # 发布时间 和 招聘人数
        pos_ft = item.select_one("div.pos-ft")
        if pos_ft and pos_ft.has_attr("title"):
            title_text = pos_ft["title"]
            # 例: "更新日期：2026-01-20 | 招聘人数：若干 "
            parts = title_text.split("|")
            for part in parts:
                part = part.strip()
                if part.startswith("更新日期："):
                    publish_time = part.replace("更新日期：", "").strip()
                elif part.startswith("招聘人数："):
                    hd_job_num = part.replace("招聘人数：", "").strip()
        else:
            # 备用从span中提取
            pub_span = item.select_one("span.pub-time")
            if pub_span:
                publish_time = pub_span.get_text(strip=True).replace("更新日期：", "").strip()
            need_span = item.select_one("span.need-people")
            if need_span:
                hd_job_num = need_span.get_text(strip=True).replace("招聘人数：", "").strip()

        # 链接字段html中无，赋空字符串
        link = ""

        # 所属部门或机构字段html中无，赋空字符串
        hd_dept = ""

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
