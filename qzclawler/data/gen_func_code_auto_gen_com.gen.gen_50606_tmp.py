
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []
    items = soup.select("div.list-card-item1")
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称
        name_tag = item.select_one("div.pos-title-item > span.top-label")
        if name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 所属部门或机构
        dept_tag = item.select_one("div.pos-tag-item > span.pos-cate")
        if dept_tag:
            hd_dept = dept_tag.get_text(strip=True)

        # 工作地点
        loc_tag = item.select_one("div.pos-summary > span.work-place")
        if loc_tag:
            hd_loc = loc_tag.get_text(strip=True).replace(" | ", "").strip()

        # 发布时间 和 招聘人数
        pub_time_tag = item.select_one("div.pos-ft > div.ft-info > span.pub-time")
        if pub_time_tag:
            # 形如 "更新日期：2026-04-02"
            publish_time = pub_time_tag.get_text(strip=True).replace("更新日期：", "")

        job_num_tag = item.select_one("div.pos-ft > div.ft-info > span.need-people")
        if job_num_tag:
            # 形如 "招聘人数：5"
            hd_job_num = job_num_tag.get_text(strip=True).replace("招聘人数：", "")

        # 职位类别，题中html没有明确字段，赋空字符串
        hd_job_category = ""

        # 链接，html中无链接，赋空字符串
        link = ""

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
`