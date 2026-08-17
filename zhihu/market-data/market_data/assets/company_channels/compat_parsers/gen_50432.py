import json
from bs4 import BeautifulSoup

# 安全取文本：找不到就返回 ""
def safe_get(parent, tag, cls):
    node = parent.find(tag, class_=cls)
    return node.get_text(strip=True) if node else ""

# 安全取多个：找不到就返回 ""
def safe_get_all(parent, tag, cls, index):
    nodes = parent.find_all(tag, class_=cls)
    if len(nodes) > index:
        return nodes[index].get_text(strip=True)
    return ""

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    items = soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0")

    for item in items:

        announcement_name = safe_get(item, "div", "style__STJobTitle-editor__sc-10r1nhd-4")
        publish_time = safe_get(item, "div", "style__STJobTime-editor__sc-10r1nhd-16").replace(" 发布", "")
        link = ""
        hd_dept = ""
        hd_loc = safe_get_all(item, "div", "style__STLabelText-editor__sc-10r1nhd-13", -1)
        hd_job_num = ""
        hd_job_category = ""

        # 遇到 "test" 或 "测试" 直接停止
        if "test" in announcement_name or "测试" in announcement_name:
            break

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
