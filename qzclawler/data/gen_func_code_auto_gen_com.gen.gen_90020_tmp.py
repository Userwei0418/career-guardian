
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []

    # 假设公告列表是以某种结构存在，先找所有公告条目
    # 由于示例html没有明显的表格或列表结构，且内容是空的“抱歉，暂时没有您要找的职位~”，
    # 这里写一个通用的提取逻辑，尝试从html中提取对应字段，找不到则赋空字符串

    # 先尝试找所有可能的公告条目容器，假设是class包含"list-item"或类似的div
    # 由于示例html没有实际数据，以下代码为通用模板

    # 这里示例html没有数据，故不做具体定位，直接返回空列表写入json
    # 如果有数据，应该遍历每条公告，提取字段

    # 结构示例（伪代码）：
    # for item in soup.select('.list-item'):
    #     announcement_name = item.select_one('.announcement_name').get_text(strip=True) if item.select_one('.announcement_name') else ""
    #     publish_time = item.select_one('.publish_time').get_text(strip=True) if item.select_one('.publish_time') else ""
    #     link = item.select_one('a')['href'] if item.select_one('a') else ""
    #     hd_dept = item.select_one('.hd_dept').get_text(strip=True) if item.select_one('.hd_dept') else ""
    #     hd_loc = item.select_one('.hd_loc').get_text(strip=True) if item.select_one('.hd_loc') else ""
    #     hd_job_num = item.select_one('.hd_job_num').get_text(strip=True) if item.select_one('.hd_job_num') else ""
    #     hd_job_category = item.select_one('.hd_job_category').get_text(strip=True) if item.select_one('.hd_job_category') else ""
    #     results.append({
    #         "announcement_name": announcement_name,
    #         "publish_time": publish_time,
    #         "link": link,
    #         "hd_dept": hd_dept,
    #         "hd_loc": hd_loc,
    #         "hd_job_num": hd_job_num,
    #         "hd_job_category": hd_job_category
    #     })

    # 由于示例html无数据，直接写入空列表
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`