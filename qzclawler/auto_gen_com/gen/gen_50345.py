import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 1. 行解析：改为 startswith 模式（兼容 hash 类名）
    rows = soup.find_all("div", class_=lambda x: x and x.startswith("phoenixTableRowLayout_rowWrapper"))

    if not rows:
        print("[WARN] 未找到行节点，可能是 class 名变化或 HTML 为前端渲染内容。")

    for idx, row in enumerate(rows):
        # 2. 单元格解析，兼容 hash
        cells = row.find_all("div", class_=lambda x: x and x.startswith("public_phoenixTableCell_cellContent__content"))

        if not cells:
            print(f"[WARN] 第 {idx + 1} 行未找到 cells，结构可能变化。row 内容片段:")
            print(str(row)[:200])
            continue

        # 3. 数据安全提取
        def safe_get(index):
            try:
                return cells[index].get_text(strip=True)
            except:
                return ""

        job_info = {
            "announcement_name": safe_get(0),
            "hd_loc": safe_get(1),
            "hd_job_num": safe_get(2),
            "publish_time": safe_get(3),
            "hd_salary": safe_get(4),
            "hd_degree": safe_get(5),
            "hd_job_category": safe_get(6),
        }

        job_list.append(job_info)

    # 4. 输出可观测日志
    print(f"[INFO] 共提取到 {len(job_list)} 条职位记录")

    # 5. 结果写入文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    return job_list
