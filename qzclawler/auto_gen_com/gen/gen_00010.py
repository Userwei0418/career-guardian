from bs4 import BeautifulSoup
import json
import re

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []

    items = soup.find_all("div", class_="position_list_item")

    for item in items:
        # 公告名称
        title_div = item.find("div", class_="postion_name")
        announcement_name = title_div.find("div", class_="title").get_text(strip=True) if title_div else ""

        # 发布时间
        time_div = item.find("i", class_="mtdicon-time-o")
        publish_time = ""
        if time_div:
            sibling = time_div.find_next_sibling("span")
            if sibling and "更新于" in sibling.text:
                publish_time = sibling.text.replace("更新于", "").strip()

        # 链接（假设构造为：https://job.meituan.com/detail/ + data-jobunionid）
        job_id = item.get("data-jobunionid", "")
        link = f"https://zhaopin.meituan.com/web/position/detail?jobUnionId={job_id}" if job_id else ""

        # 所属部门或机构
        dept_icon = item.find("i", class_="mtdicon-floor")
        hd_dept = dept_icon.find_next_sibling("span").get_text(strip=True) if dept_icon else ""

        # 工作地点
        city_div = item.find("div", class_="zp_clamp_string_inner")
        hd_loc = city_div.get_text(strip=True) if city_div else ""

        # 招聘人数（页面中无此字段，填空）
        hd_job_num = ""

        # 职位类别（页面中为社招字段）
        edu_icon = item.find("i", class_="mtdicon-education")
        hd_job_category = edu_icon.find_next_sibling("span").get_text(strip=True) if edu_icon else ""

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