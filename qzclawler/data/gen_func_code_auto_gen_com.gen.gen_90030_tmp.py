
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []
    items = soup.select("div.list-item-main > div.list-row-item")
    for item in items:
        announcement_name = ""
        hd_job_category = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        publish_time = ""
        link = ""

        # 公告名称(announcement_name) 对应 pos-name title
        pos_name = item.select_one("div.list-cell.pos-name > span.list-cell-span")
        if pos_name and pos_name.has_attr("title"):
            announcement_name = pos_name["title"].strip()
        else:
            announcement_name = ""

        # 职位类别(hd_job_category) 对应 pos-cate title
        pos_cate = item.select_one("div.list-cell.pos-cate > span.list-cell-span")
        if pos_cate and pos_cate.has_attr("title"):
            hd_job_category = pos_cate["title"].strip()
        else:
            hd_job_category = ""

        # 所属部门或机构(hd_dept) 对应 pos-department title
        pos_dept = item.select_one("div.list-cell.pos-department > span.list-cell-span")
        if pos_dept and pos_dept.has_attr("title"):
            hd_dept = pos_dept["title"].strip()
        else:
            hd_dept = ""

        # 工作地点(hd_loc) 对应 pos-locate title
        pos_loc = item.select_one("div.list-cell.pos-locate > span.list-cell-span")
        if pos_loc and pos_loc.has_attr("title"):
            hd_loc = pos_loc["title"].strip()
        else:
            hd_loc = ""

        # 招聘人数(hd_job_num) html中无此字段，赋空字符串
        hd_job_num = ""

        # 发布时间(publish_time) html中无此字段，赋空字符串
        publish_time = ""

        # 链接(link) html中无此字段，赋空字符串
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