
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

        # 公告名称(announcement_name) - 取pos-title-item > top-label文本
        title_tag = item.select_one('div.pos-title-item > span.top-label')
        if title_tag:
            announcement_name = title_tag.get_text(strip=True)

        # 发布时间(publish_time) - 取pos-ft > ft-info > pub-time文本，去掉"更新日期："前缀
        pub_time_tag = item.select_one('div.pos-ft > div.ft-info > span.pub-time')
        if pub_time_tag:
            publish_time = pub_time_tag.get_text(strip=True).replace("更新日期：", "")

        # 链接(link) - 该html中无链接，赋空字符串
        link = ""

        # 所属部门或机构(hd_dept) - 该html中无明确字段，赋空字符串
        hd_dept = ""

        # 工作地点(hd_loc) - 取pos-summary > span.work-place文本
        loc_tag = item.select_one('div.pos-hd > div.pos-summary > span.work-place')
        if loc_tag:
            hd_loc = loc_tag.get_text(strip=True)

        # 招聘人数(hd_job_num) - 取pos-ft > ft-info > need-people文本，去掉"招聘人数："前缀
        job_num_tag = item.select_one('div.pos-ft > div.ft-info > span.need-people')
        if job_num_tag:
            hd_job_num = job_num_tag.get_text(strip=True).replace("招聘人数：", "")

        # 职位类别(hd_job_category) - 取pos-tag-item > span.pos-cate文本
        job_cat_tag = item.select_one('div.pos-tag-item > span.pos-cate')
        if job_cat_tag:
            hd_job_category = job_cat_tag.get_text(strip=True)

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