import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    """
    从凤凰表格结构中提取招聘信息并写入 JSON 文件。
    """
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    # 定位所有数据行（排除表头）
    rows = soup.select('.phoenixTableRowLayout_main.public_phoenixTableRow_main.public_phoenixTable_bodyRow')

    for row in rows:
        # 每一行中的所有单元格
        cells = row.select('.public_phoenixTableCell_cellContent')

        if len(cells) >= 4:
            # 第一列 - 职位名称（可能嵌套多层 span）
            title_tag = cells[0].select_one('.styled__jobSpan-editor__sc-i00twi-2')
            announcement_name = title_tag.get_text(strip=True) if title_tag else cells[0].get_text(strip=True)

            # 第二列 - 工作地点
            hd_loc = cells[2].get_text(strip=True).replace("/",",") if len(cells) > 1 else ""

            # 第三列 - 发布时间
            publish_time = cells[4].get_text(strip=True) if len(cells) > 2 else ""

            # 第四列 - 职位类型
            hd_job_category = cells[3].get_text(strip=True) if len(cells) > 3 else ""

            # 第五列 - 招聘机构
            hd_dept =  ""

            # 写入结果
            data_list.append({
                "announcement_name": announcement_name,
                "hd_loc": hd_loc,
                "publish_time": publish_time,
                "hd_job_category": "",
                "hd_dept": hd_dept,
                "link": "",  # 暂无超链接字段
            })

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)

    print(f"✅ 已成功提取 {len(data_list)} 条招聘信息并保存到 {tempfile}")
