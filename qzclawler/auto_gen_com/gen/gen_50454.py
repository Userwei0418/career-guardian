import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    # 每一条职位行
    rows = soup.select('.public_phoenixTableRow_main')

    for row in rows:
        # 职位名称
        title_span = row.select_one('.styled__jobSpan-editor__sc-i00twi-2')
        announcement_name = title_span.get_text(strip=True) if title_span else ""

        # 右侧四列（顺序固定）
        cells = row.select('.phoenixTableCellLayout_main.public_phoenixTableCell_main')

        def get_cell(i):
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        hd_dept = get_cell(0)            # 校园招聘 / 社招
        hd_job_category = get_cell(1)    # 全职 / 实习
        hd_loc = get_cell(3)             # 工作地点      # 发布时间

        # 过滤掉“空行”（表头情况），只有真实职位才录入
        if announcement_name.strip() == "":
            continue

        data = {
            "announcement_name": announcement_name,
            "publish_time": "",
            "link": "",
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": ""
        }

        data_list.append(data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
