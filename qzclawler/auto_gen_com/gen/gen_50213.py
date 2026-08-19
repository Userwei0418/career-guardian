import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 遍历每一个职位条目
    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0 dUmFMT"):

        # 安全提取函数：有就取文本，没有就返回空字符串
        def safe_text(tag, selector=None, multiple=False, index=-1):
            try:
                if selector:
                    found = tag.find_all(*selector) if multiple else tag.find(*selector)
                    if multiple:
                        if found and len(found) > 0:
                            return found[index].get_text(strip=True)
                    elif found:
                        return found.get_text(strip=True)
                else:
                    return tag.get_text(strip=True)
            except Exception:
                return ""
            return ""

        # --- 字段提取 ---
        announcement_name = safe_text(item, ("div", "style__STJobTitle-editor__sc-10r1nhd-4 eVDXPD"))
        publish_time = safe_text(item, ("div", "style__STJobTime-editor__sc-10r1nhd-16 eKeZsF")).replace(" 发布", "")
        hd_loc = safe_text(
            item.find("div", class_="style__STLabelSection-editor__sc-10r1nhd-11 kDWFRA") or item,
            ("div", "style__STLabelText-editor__sc-10r1nhd-13 cJYhpK"),
            multiple=True
        )

        # --- 未出现的字段置空 ---
        link = ""
        hd_dept = ""
        hd_job_num = ""
        hd_job_category = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # --- 输出结果 ---
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
