import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []


    for item in soup.find_all(class_='list-item-main'):
        # 安全提取职位名称
        pos_name_element = item.find(class_='pos-name')
        announcement_name = pos_name_element.get_text(strip=True) if pos_name_element else ""
        
        # 安全提取职位类别
        hd_job_category = ""
        pos_cate_element = item.find(class_='pos-cate')
        if pos_cate_element:
            hd_job_category = pos_cate_element.get_text(strip=True)
        
        # 安全提取工作地点
        hd_loc = ""
        pos_locate_element = item.find(class_='pos-locate')
        if pos_locate_element:
            hd_loc = pos_locate_element.get_text(strip=True)
        
        # 安全提取招聘人数
        hd_job_num = ""
        pos_num_element = item.find(class_='pos-num')
        if pos_num_element:
            hd_job_num = pos_num_element.get_text(strip=True)
        
        publish_time = ""  # HTML 没有提供发布时间，可留空
        post_id = item.get('id', '')
        link = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # HTML 没有提供部门
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)