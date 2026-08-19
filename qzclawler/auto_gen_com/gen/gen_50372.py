import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='p_loopitem'):
        # 用 try/except 或条件判断确保即使元素不存在也不会报错
        announcement_name_tag = item.find('p', class_='e_text-5 s_title')
        announcement_name = announcement_name_tag.get_text(strip=True) if announcement_name_tag else ""

        link_tag = item.find('a', href=True)
        link = link_tag['href'] if link_tag else ""

        # 其他字段，尝试提取，如果不存在就为 None
        publish_time_tag = item.find('span', class_='publish_time')  # 假设 class 名
        publish_time = publish_time_tag.get_text(strip=True) if publish_time_tag else ""

        hd_dept_tag = item.find('span', class_='hd_dept')
        hd_dept = hd_dept_tag.get_text(strip=True) if hd_dept_tag else ""

        hd_loc_tag = item.find('span', class_='hd_loc')
        hd_loc = hd_loc_tag.get_text(strip=True) if hd_loc_tag else ""

        hd_job_num_tag = item.find('span', class_='hd_job_num')
        hd_job_num = hd_job_num_tag.get_text(strip=True) if hd_job_num_tag else ""

        hd_job_category_tag = item.find('span', class_='hd_job_category')
        hd_job_category = hd_job_category_tag.get_text(strip=True) if hd_job_category_tag else ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 保存为 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
