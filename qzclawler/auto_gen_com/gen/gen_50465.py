import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    # 正确的行选择器
    rows = soup.select('.phoenixTableRowLayout_body')

    for row in rows:
        # 职位名称（你原来的选择器是错的）
        announcement_name = row.select_one('.styled__jobSpan-editor__sc-i00twi-2')

        # 这里 nth-child 对不上真实结构，所以改为定位内容容器
        cells = row.select('.public_phoenixTableCell_cellContent__content')

        # 按顺序取：部门、地点、学历、类别
        hd_dept = cells[1].get_text(strip=True) if len(cells) > 1 else ""
        hd_loc = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        hd_job_num = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        hd_job_category = cells[4].get_text(strip=True) if len(cells) > 4 else ""

        data = {
            "announcement_name": announcement_name.get_text(strip=True) if announcement_name else "",
            "publish_time": "",
            "link": "",
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        }

        data_list.append(data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
