import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 安全提取函数
    def get_text_safe(tag):
        return tag.get_text(strip=True) if tag else ""

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = get_text_safe(item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4"))
        publish_time = get_text_safe(item.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16")).replace(" 发布",
                                                                                                                "")

        # 提取链接，如果是 a 标签
        link_tag = item.find("a")
        link = link_tag['href'] if link_tag and 'href' in link_tag.attrs else ""

        hd_dept = get_text_safe(item.find("div", class_="style__STJobLabelText-editor__sc-10r1nhd-13"))

        # 提取最后一个 location，如果存在
        loc_tags = item.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13")
        hd_loc = get_text_safe(loc_tags[2]) if loc_tags else ""

        hd_job_num = "1"  # 占位
        hd_job_category = ""  # 占位

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
