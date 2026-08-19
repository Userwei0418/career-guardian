
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    result = []
    rows = soup.select("tbody tr.clickHot")
    for tr in rows:
        tds = tr.find_all("td")
        # 过滤空td和图片td，职位名称是第2个td，职位类别第3个，工作单位第5个，工作地点第6个，发布时间第7个
        announcement_name = ""
        hd_job_category = ""
        hd_dept = ""
        hd_loc = ""
        publish_time = ""
        link = ""
        hd_job_num = ""

        # 职位名称
        if len(tds) > 1:
            announcement_name = tds[1].get("title", "").strip()
        # 职位类别
        if len(tds) > 2:
            hd_job_category = tds[2].get("title", "").strip()
        # 所属部门或机构
        if len(tds) > 4:
            hd_dept = tds[4].get("title", "").strip()
        # 工作地点
        if len(tds) > 5:
            hd_loc = tds[5].get("title", "").strip()
        # 发布时间
        if len(tds) > 6:
            publish_time = tds[6].text.strip()
        # 链接从onclick的data_postid拼接
        data_postid = tr.get("data_postid", "").strip()
        if data_postid:
            link = f"https://hztp.hotjob.cn/wt/component1000/corp/yili/postdetail.html?postid={data_postid}"
        # 招聘人数字段html中无，赋空字符串
        hd_job_num = ""

        item = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }
        result.append(item)

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
`