
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    # 遍历所有class为list-item-main的div
    for item in soup.select('div.list-item-main'):
        row = item.select_one('div.list-row-item')
        if not row:
            continue
        announcement_name = ""
        hd_loc = ""
        hd_job_num = ""
        publish_time = ""
        hd_job_category = ""
        link = ""
        hd_dept = ""

        # 职位名称
        name_tag = row.select_one('div.pos-name > span.list-cell-span')
        if name_tag and name_tag.has_attr('title'):
            announcement_name = name_tag['title'].strip()
        elif name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 工作地点
        loc_tag = row.select_one('div.pos-locate > span.list-cell-span')
        if loc_tag and loc_tag.has_attr('title'):
            hd_loc = loc_tag['title'].strip()
        elif loc_tag:
            hd_loc = loc_tag.get_text(strip=True)

        # 招聘人数
        num_tag = row.select_one('div.pos-num > span.list-cell-span')
        if num_tag and num_tag.has_attr('title'):
            hd_job_num = num_tag['title'].strip()
        elif num_tag:
            hd_job_num = num_tag.get_text(strip=True)

        # 发布时间（更新日期）
        pub_tag = row.select_one('div.pos-pubTime > span.list-cell-span')
        if pub_tag and pub_tag.has_attr('title'):
            publish_time = pub_tag['title'].strip()
        elif pub_tag:
            publish_time = pub_tag.get_text(strip=True)

        # 职位类别
        cate_tag = row.select_one('div.pos-cate > span.list-cell-span')
        if cate_tag and cate_tag.has_attr('title'):
            hd_job_category = cate_tag['title'].strip()
        elif cate_tag:
            hd_job_category = cate_tag.get_text(strip=True)

        # 链接：尝试从id属性推断链接，html中无明确链接，故赋空字符串
        link = ""

        # 所属部门或机构：html中无相关字段，赋空字符串
        hd_dept = ""

        results.append({
            "announcement_name": announcement_name or "",
            "publish_time": publish_time or "",
            "link": link or "",
            "hd_dept": hd_dept or "",
            "hd_loc": hd_loc or "",
            "hd_job_num": hd_job_num or "",
            "hd_job_category": hd_job_category or ""
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`