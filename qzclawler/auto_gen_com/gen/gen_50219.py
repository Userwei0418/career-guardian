import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    """
    解析 HTML 中的招聘表格数据，提取公告信息、岗位ID并写入 JSON 文件。
    """
    soup = BeautifulSoup(htmlcontext, 'html.parser')

    # 查找所有表格行
    rows = soup.select('tr.ant-table-row')
    if not rows:
        print("[警告] 未找到表格行！HTML可能未加载或结构已变动。")
        return

    data_list = []

    for idx, row in enumerate(rows, start=1):
        # ----------- ✅ 提取 data-row-key（岗位ID） -----------
        job_id = row.get('data-row-key', '').strip()

        # ----------- 处理列合并情况 -----------
        cells = []
        for td in row.find_all('td'):
            colspan = int(td.get('colspan', 1))
            cells.extend([td] * colspan)

        # 补齐到 6 列
        while len(cells) < 6:
            cells.append(None)

        def clean_text(td):
            if td is None:
                return ''
            return td.get_text(strip=True).replace('【置顶】', '')

        announcement_name = clean_text(cells[0])
        hd_loc = clean_text(cells[1])
        publish_time = clean_text(cells[2])
        hd_dept = ""
        hd_job_num = clean_text(cells[4])
        hd_job_category = clean_text(cells[5])

        # 提取链接
        link_tag = cells[0].find('a') if cells[0] else None
        link = f"https://job.icbc.com.cn/pc/index.html#/main/school/postDetail/{job_id}"

        # 组装结构化数据
        data_list.append({
            "id": job_id,                        # ✅ 新增字段
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # ----------- 写入 JSON 文件 -----------
    try:
        with open(tempfile, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=4)
        print(f"[完成] 数据已写入 {tempfile}，共 {len(data_list)} 条记录")
    except Exception as e:
        print(f"[错误] 写入 JSON 文件失败: {e}")
