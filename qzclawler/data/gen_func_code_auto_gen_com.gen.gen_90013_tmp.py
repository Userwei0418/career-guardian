
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    # 公告名称(announcement_name)、发布时间(publish_time)、链接(link)、所属部门或机构(hd_dept)、工作地点(hd_loc)、招聘人数(hd_job_num)、职位类别(hd_job_category)
    # 根据html结构，公告名称、发布时间、链接、职位类别未见，赋空字符串
    list_items = soup.select('div.list-item-main')
    for item in list_items:
        pos_name = item.select_one('div.list-cell.pos-name span.list-cell-span')
        hd_dept = item.select_one('div.list-cell.pos-department span.list-cell-span')
        hd_loc = item.select_one('div.list-cell.pos-locate span.list-cell-span')
        hd_job_num = item.select_one('div.list-cell.pos-num span.list-cell-span')

        announcement_name = ""
        publish_time = ""
        link = ""
        hd_job_category = ""

        record = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept['title'] if hd_dept and hd_dept.has_attr('title') else "",
            "hd_loc": hd_loc['title'] if hd_loc and hd_loc.has_attr('title') else "",
            "hd_job_num": hd_job_num['title'] if hd_job_num and hd_job_num.has_attr('title') else "",
            "hd_job_category": hd_job_category
        }
        results.append(record)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`