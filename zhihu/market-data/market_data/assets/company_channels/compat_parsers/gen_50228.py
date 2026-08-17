import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 查找所有行
    rows = soup.select('.phoenixTableRowLayout_rowWrapper')
    print(f"找到 {len(rows)} 行")  # 输出行数，确认是否找到

    for row in rows:
        try:
            # 提取职位名称
            announcement_name_elem = row.select_one('.styled__jobName-editor__sc-i00twi-0 .styled__jobSpan-editor__sc-i00twi-2')
            if announcement_name_elem:
                announcement_name = announcement_name_elem.get_text(strip=True)
            else:
                announcement_name = "未提供职位名称"
                print("未找到职位名称")

            # 提取部门
            hd_dept_elem = ""
            hd_dept =""

            # 提取职位类别
            hd_job_category_elem = row.select_one('.phoenixTableCellLayout_main:nth-child(3) .public_phoenixTableCell_cellContent')
            hd_job_category = ""

            # 提取工作地点
            hd_loc_elem = row.select_one('.phoenixTableCellLayout_main:nth-child(3) .public_phoenixTableCell_cellContent')
            hd_loc = hd_loc_elem.get_text(strip=True) if hd_loc_elem else "未提供职位类别"

            # 提取发布日期
            publish_time_elem = row.select_one('.phoenixTableCellLayout_main:nth-child(4) .public_phoenixTableCell_cellContent')
            publish_time = publish_time_elem.get_text(strip=True) if hd_loc_elem else "未提供地点"

            # 提取职位数量
            hd_job_num = "1"  # 默认值为 1，假设没有提供职位数量

            # 把提取的数据添加到 job_list 中
            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": "",  # 假设没有提供链接
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

        except Exception as e:
            print(f"解析行时出错: {e}")

    # 将提取的数据写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"提取到 {len(job_list)} 条职位信息")
