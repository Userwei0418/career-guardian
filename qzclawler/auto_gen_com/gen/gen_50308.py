import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    data_list = []

    # 找出所有表格行（排除表头）
    rows = soup.select('.phoenixTableRowLayout_rowWrapper ')

    for row in rows:
        # 安全提取函数
        def safe_select_text(selector, index=None):
            try:
                if index is not None:
                    elements = row.select(selector)
                    if len(elements) > index:
                        return elements[index].get_text(strip=True)
                    return ""
                el = row.select_one(selector)
                return el.get_text(strip=True) if el else ""
            except Exception:
                return ""

        # 提取字段
        announcement_name = safe_select_text('.styled__jobSpan-editor__sc-i00twi-2')
        publish_time = ""  # 当前HTML无对应字段
        link = ""          # 当前HTML无对应字段
        hd_dept = ""       # 当前HTML无对应字段
        hd_loc = safe_select_text('.phoenixTableCellLayout_main', 0)
        hd_job_num = ""    # 当前HTML无对应字段
        hd_job_category = safe_select_text('.phoenixTableCellLayout_main', 1)

        # 追加结果
        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_job_category,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    # 写出JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
