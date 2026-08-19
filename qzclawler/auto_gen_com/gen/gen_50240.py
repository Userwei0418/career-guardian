import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    """
    解析 HTML 中的招聘信息，提取职位名称、发布时间、部门、地点等字段，并保存为 JSON。
    """

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 每个职位卡片
    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')

    for job in job_elements:
        # --- 职位名称 ---
        name_tag = job.find('div', class_='_1RRlPtjyYmeDGCWt9lrk2P')
        announcement_name = name_tag.get_text(strip=True) if name_tag else ""

        # --- 发布时间 ---
        time_tag = job.find('div', class_='_3Jn5Z6PZA5H7Auzy0xlXu2')
        publish_time = time_tag.get_text(strip=True).replace("更新于", "").strip() if time_tag else ""

        # --- 部门 ---
        dept_tag = job.find('div', class_='_1KYNSENqWg4IDHby5E9sqK')
        hd_dept = dept_tag.get_text(strip=True) if dept_tag else ""

        # --- 工作地点 ---
        loc_tag = job.find('div', class_='_3CJNtKfv5mLnNfeqL1jgRB')
        hd_loc = loc_tag.get_text(strip=True) if loc_tag else ""

        # --- 可能后续添加字段（例如职位链接、编号、分类） ---
        link = ""
        hd_job_num = ""
        hd_job_category = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_dept
        })

    # 输出 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"[日志] 成功提取 {len(job_list)} 条职位信息，已保存到 {tempfile}")
