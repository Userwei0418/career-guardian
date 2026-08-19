import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    """
    提取职位信息（安全版）
    即使字段缺失，也不会报错，只返回空字符串。
    """

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 1️⃣ 找到所有职位块
    job_elements = soup.find_all('div', class_='_2AOmjKmlEtuR_KEoehWYcN')

    for job in job_elements:
        # --- 安全提取函数 ---
        def safe_text(parent, selector, all_mode=False, index=-1):
            try:
                if all_mode:
                    elements = parent.find_all('div', class_=selector)
                    if elements and len(elements) > abs(index):
                        return elements[index].get_text(strip=True)
                    return ""
                tag = parent.find('div', class_=selector)
                return tag.get_text(strip=True) if tag else ""
            except Exception:
                return ""

        # 2️⃣ 分别提取字段（如不存在则为空）
        announcement_name = safe_text(job, '_1RRlPtjyYmeDGCWt9lrk2P')
        publish_time_raw = safe_text(job, '_3Jn5Z6PZA5H7Auzy0xlXu2')
        publish_time = publish_time_raw.replace('更新于 ', '').strip() if publish_time_raw else ""

        hd_loc = safe_text(job, '_3vj2eS7k7Mwpko5_6OSRu2', all_mode=True, index=-1).replace('/',',')
        hd_job_category = safe_text(job, '_1KYNSENqWg4IDHby5E9sqK')

        # 3️⃣ 组装数据
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",         # 可在后续补充职位详情页 URL
            "hd_dept": "",      # 暂无数据
            "hd_loc": hd_loc,
            "hd_job_num": "",   # 暂无数据
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    # 4️⃣ 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"[日志] 成功提取 {len(job_list)} 条职位数据。")
