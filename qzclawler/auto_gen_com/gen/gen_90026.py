import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    # 找到所有职位条目
    items = soup.select('div.list-item-main > div.list-row-item')
    for item in items:
        announcement_name = ""
        hd_job_category = ""
        hd_loc = ""
        hd_job_num = ""
        publish_time = ""
        hd_dept = ""  # 所属部门或机构，html中无相关字段，赋空字符串
        link = ""     # 链接，html中无相关字段，赋空字符串

        # 职位名称
        name_tag = item.select_one('div.pos-name > span.list-cell-span')
        if name_tag and name_tag.has_attr('title'):
            announcement_name = name_tag['title'].strip()
        elif name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 职位类别
        cate_tag = item.select_one('div.pos-cate > span.list-cell-span')
        if cate_tag and cate_tag.has_attr('title'):
            hd_job_category = cate_tag['title'].strip()
        elif cate_tag:
            hd_job_category = cate_tag.get_text(strip=True)

        # 工作地点
        loc_tag = item.select_one('div.pos-locate > span.list-cell-span')
        if loc_tag and loc_tag.has_attr('title'):
            hd_loc = loc_tag['title'].strip()
        elif loc_tag:
            hd_loc = loc_tag.get_text(strip=True)

        # 招聘人数
        num_tag = item.select_one('div.pos-num > span.list-cell-span')
        if num_tag and num_tag.has_attr('title'):
            hd_job_num = num_tag['title'].strip()
        elif num_tag:
            hd_job_num = num_tag.get_text(strip=True)

        # 发布时间（更新日期）
        pubtime_tag = item.select_one('div.pos-pubTime > span.list-cell-span')
        if pubtime_tag and pubtime_tag.has_attr('title'):
            publish_time = pubtime_tag['title'].strip()
        elif pubtime_tag:
            publish_time = pubtime_tag.get_text(strip=True)

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
