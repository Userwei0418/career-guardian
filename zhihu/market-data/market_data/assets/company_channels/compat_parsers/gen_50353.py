import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    items = soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0")

    for item in items:

        def safe_get(div, cls):
            t = item.find("div", class_=cls)
            return t.get_text(strip=True) if t else ""

        def safe_get_location(item):
            # 找到所有匹配的 location div
            loc_divs = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")
            if loc_divs:
                # 假设城市信息总是在最后一个 div
                return loc_divs[0].get_text(strip=True)
            return ""
        title = safe_get(item, "style__STJobTitle-editor__sc-10r1nhd-4")
        time = safe_get(item, "style__STJobTime-editor__sc-10r1nhd-16")
        location = safe_get_location(item)

        # 链接处理（通常在 a 标签中）
        link_tag = item.find("a", href=True)
        link = link_tag["href"] if link_tag else ""

        job_info = {
            "announcement_name": title,
            "publish_time": time,
            "link": link,
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": "",
            "hd_job_category": ""
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
