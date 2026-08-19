
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    results = []
    # 尝试查找包含招聘信息的列表项，假设每条招聘信息在某个特定标签内
    # 由于示例html中没有实际数据，以下为通用提取逻辑，字段名对应规则要求
    # 先找所有可能的公告条目容器，假设为class="list-item"或类似，若无则空列表
    items = soup.find_all(class_='list-item')
    for item in items:
        announcement_name = item.find(class_='announcement_name')
        publish_time = item.find(class_='publish_time')
        link = item.find('a')
        hd_dept = item.find(class_='hd_dept')
        hd_loc = item.find(class_='hd_loc')
        hd_job_num = item.find(class_='hd_job_num')
        hd_job_category = item.find(class_='hd_job_category')

        data = {
            "announcement_name": announcement_name.get_text(strip=True) if announcement_name else "",
            "publish_time": publish_time.get_text(strip=True) if publish_time else "",
            "link": link['href'].strip() if link and link.has_attr('href') else "",
            "hd_dept": hd_dept.get_text(strip=True) if hd_dept else "",
            "hd_loc": hd_loc.get_text(strip=True) if hd_loc else "",
            "hd_job_num": hd_job_num.get_text(strip=True) if hd_job_num else "",
            "hd_job_category": hd_job_category.get_text(strip=True) if hd_job_category else ""
        }
        results.append(data)

    # 如果没有找到任何条目，返回空列表写入json
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`