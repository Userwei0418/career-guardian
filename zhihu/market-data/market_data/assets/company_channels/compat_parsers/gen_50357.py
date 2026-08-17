import json
from bs4 import BeautifulSoup

def safe_text(parent, cls):
    """通用安全取值：不存在就返回空字符串"""
    try:
        tag = parent.find(class_=cls)
        return tag.get_text(strip=True) if tag else ""
    except:
        return ""

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for item in soup.find_all(class_='positionItem'):
        title = safe_text(item, 'po_title')
        job_category = safe_text(item, 'po_jobCategory')
        org = safe_text(item, 'po_org')
        location = safe_text(item, 'po_place')
        publish_info = safe_text(item, 'po_bottom')

        # ---- 发布时间 & 招聘人数 ----
        publish_time = ""
        job_num = ""

        if "发布时间：" in publish_info:
            try:
                publish_time = publish_info.split("发布时间：")[1].split(" 招聘人数：")[0]
            except:
                publish_time = ""

        if "招聘人数：" in publish_info:
            try:
                job_num = publish_info.split("招聘人数：")[1].strip()
            except:
                job_num = ""

        # ---- 实习字段 ----
        hd_hopeworktype = "实习" if "实习" in title else ""

        position = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": "",
            "hd_dept": org,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": job_category,
            "hd_hpoeworktype": hd_hopeworktype
        }

        positions.append(position)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)
