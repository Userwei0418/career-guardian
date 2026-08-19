import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        # --- 职位标题 ---
        title_section = item.find("div", class_="style__STTitleSection-editor__sc-10r1nhd-2")
        job_title = ""
        if title_section:
            job_title_div = title_section.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4")
            if job_title_div:
                job_title = job_title_div.get_text(strip=True)

        # --- 发布时间与地点 ---
        other_section = item.find("div", class_="style__STOtherSection-editor__sc-10r1nhd-10")
        job_time, location = "", ""
        if other_section:
            # 发布时间
            job_time_div = other_section.find("div", class_="style__STJobTime-editor__sc-10r1nhd-16")
            job_time = job_time_div.get_text(strip=True) if job_time_div else ""

            # 所有标签文本
            label_texts = [
                div.get_text(strip=True)
                for div in other_section.find_all("div", class_="style__STLabelText-editor__sc-10r1nhd-13 cJYhpK")
            ]

            # 从中筛选出带“省”或“市”的字段
            for text in label_texts:
                if "省" in text or "市" in text:
                    location = text
                    break

        # --- 职责与任职要求 ---
        responsibilities, qualifications = "", ""
        job_details = item.find("div", class_="style__STDetailPanel-editor__sc-10r1nhd-17")
        if job_details:
            descs = job_details.find_all("div", class_="style__STDetailDesc-editor__sc-10r1nhd-19")
            if len(descs) > 0:
                responsibilities = descs[0].get_text(strip=True)
            if len(descs) > 1:
                qualifications = descs[1].get_text(strip=True)
        if "实习" in job_title :
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""
        # --- 汇总 ---
        job_list.append({
            "announcement_name": job_title,
            "publish_time": job_time,
            "link": "",              # 可后续补充职位链接
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": "",
            "hd_job_category": "",
            "hd_hopeworktype": hd_hopeworktype
        })

    # 输出到 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
