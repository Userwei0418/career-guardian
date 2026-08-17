import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 1. 找到所有职位块：优先根据 href 结构定位
    job_blocks = soup.find_all("a", href=True)
    for a in job_blocks:
        # 必须包含职位名称和职位详情页结构
        container = a.find("div", class_=lambda x: x and x.startswith("container"))
        if not container:
            continue

        title_div = container.find("div", class_=lambda x: x and x.startswith("title"))
        if not title_div:
            continue

        announcement_name = title_div.get_text(strip=True).replace("急", "")

        link = a["href"]

        # 2. 找到上层父容器，方便解析部门、标签、地点
        parent = a.parent

        # --- 发布时间 ---
        publish_time = ""
        pub_span = parent.find("span", string=lambda x: x and "发布" in x)
        if pub_span:
            publish_time = pub_span.get_text(strip=True).replace("发布时间：", "").replace("发布：", "")

        # --- 分类 / 部门 / 标签区 ---
        hd_job_category = ""
        hd_dept = ""

        status_items = parent.find_all("span")
        text_items = [i.get_text(strip=True) for i in status_items]

        # 经验规则：一般第一个是职位类别，第二个是部门
        if len(text_items) > 0:
            hd_job_category = text_items[0]
        if len(text_items) > 1:
            hd_dept = text_items[1]

        # --- 地点 ---
        hd_loc = ""
        loc_div = parent.find("div", string=lambda x: x and ("市" in x or "区" in x))
        if loc_div:
            hd_loc = loc_div.get_text(strip=True)

        # --- 填充 ---
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": ""
        })

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
