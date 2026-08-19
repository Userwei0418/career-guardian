
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    # 找到所有职位公告条目，假设每条公告是某个特定标签或class，因示例无数据，先尝试找a标签或列表项
    # 这里根据规则，若无对应字段，赋值空字符串
    # 由于示例html无职位数据，故示例代码以通用方式写，实际使用时需根据真实html结构调整选择器

    # 假设职位列表在某个class中，先找所有a标签作为公告链接
    announcements = soup.find_all('a')
    for ann in announcements:
        announcement_name = ann.get_text(strip=True) or ""
        link = ann.get('href') or ""
        # 其他字段无法从a标签获取，赋空字符串
        publish_time = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 如果没有找到任何a标签，返回空列表
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`