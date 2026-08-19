
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []

    # 查找所有职位条目，假设职位信息在某种列表或表格中
    # 由于示例html中无职位数据，以下为通用提取逻辑，需根据实际html结构调整
    # 这里假设每条职位信息在class为"job-item"的div中（示例中无此结构，仅示范）
    job_items = soup.find_all(class_='job-item')
    for item in job_items:
        announcement_name = item.find(class_='announcement_name')
        publish_time = item.find(class_='publish_time')
        link_tag = item.find('a', href=True)
        hd_dept = item.find(class_='hd_dept')
        hd_loc = item.find(class_='hd_loc')
        hd_job_num = item.find(class_='hd_job_num')
        hd_job_category = item.find(class_='hd_job_category')

        data = {
            "announcement_name": announcement_name.get_text(strip=True) if announcement_name else "",
            "publish_time": publish_time.get_text(strip=True) if publish_time else "",
            "link": link_tag['href'] if link_tag else "",
            "hd_dept": hd_dept.get_text(strip=True) if hd_dept else "",
            "hd_loc": hd_loc.get_text(strip=True) if hd_loc else "",
            "hd_job_num": hd_job_num.get_text(strip=True) if hd_job_num else "",
            "hd_job_category": hd_job_category.get_text(strip=True) if hd_job_category else ""
        }
        results.append(data)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`