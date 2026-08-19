
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []
    # 找到所有职位条目
    items = soup.select("div.list-item-main > div.list-row-item")
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称(announcement_name)
        name_tag = item.select_one("div.pos-name > span.list-cell-span")
        if name_tag and name_tag.has_attr("title"):
            announcement_name = name_tag["title"].strip()
        elif name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 发布时间(publish_time)
        time_tag = item.select_one("div.pos-pubTime > span.list-cell-span")
        if time_tag and time_tag.has_attr("title"):
            publish_time = time_tag["title"].strip()
        elif time_tag:
            publish_time = time_tag.get_text(strip=True)

        # 链接(link) - html中无链接，赋空字符串
        link = ""

        # 所属部门或机构(hd_dept) - html中无相关字段，赋空字符串
        hd_dept = ""

        # 工作地点(hd_loc)
        loc_tag = item.select_one("div.pos-locate > span.list-cell-span")
        if loc_tag and loc_tag.has_attr("title"):
            hd_loc = loc_tag["title"].strip()
        elif loc_tag:
            hd_loc = loc_tag.get_text(strip=True)

        # 招聘人数(hd_job_num) - html中无相关字段，赋空字符串
        hd_job_num = ""

        # 职位类别(hd_job_category) - html中无相关字段，赋空字符串
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

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`