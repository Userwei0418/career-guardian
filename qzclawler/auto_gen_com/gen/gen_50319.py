import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')

    # ✅ ID 必须与 HTML 中一致（是 recuit 不是 recruit）
    table_rows = soup.select('#recuit tr')

    data_list = []

    if not table_rows:
        print("⚠️ 未找到匹配的表格行，请检查表格 ID 或确认页面是否为动态加载。")

    for row in table_rows:
        cols = row.find_all('td')
        if len(cols) > 0:
            announcement_name = cols[0].get_text(strip=True)
            hd_dept = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            hd_job_num = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            hd_loc = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            publish_time = cols[4].get_text(strip=True) if len(cols) > 4 else ""

            # ✅ 使用 get() 安全提取 href（即使没有也不会出错）
            a_tag = cols[0].find('a')
            link = a_tag.get('href', '') if a_tag else ""

            hd_job_category = ""

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    # ✅ 输出为 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

    print(f"✅ 已提取 {len(data_list)} 条记录，结果写入：{tempfile}")
