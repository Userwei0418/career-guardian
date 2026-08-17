import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('li', class_='ant-list-item'):

        # 安全函数：找不到返回 ""
        def safe_text(obj):
            return obj.text.strip() if obj else ""

        # 找到多个 span
        spans = item.find_all('span', class_='acss-1afnczs')

        announcement_name = safe_text(item.find('span', class_='acss-1r0003g'))
        publish_time = safe_text(spans[-1]) if len(spans) > 0 else ""
        link_tag = item.find('a', class_='acss-l3evcl')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""

        hd_dept = safe_text(spans[0]) if len(spans) > 0 else ""
        hd_loc = safe_text(spans[1]) if len(spans) > 1 else ""
        hd_job_category = safe_text(spans[2]) if len(spans) > 2 else ""
        hd_job_num = safe_text(spans[3]) if len(spans) > 3 else ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
