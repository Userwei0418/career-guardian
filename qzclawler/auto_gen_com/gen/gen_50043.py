import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []



    for card in soup.find_all('div', class_='list-card-item1'):
        # 安全提取职位名称
        top_label_element = card.find('span', class_='top-label')
        announcement_name = top_label_element.text.strip() if top_label_element else ""
        
        # 安全提取发布时间
        pub_time_element = card.find('span', class_='pub-time')
        publish_time = ""
        if pub_time_element:
            publish_time = pub_time_element.text.replace('发布时间：', '').strip()
        
        # 安全提取部门
        pos_cate_element = card.find('span', class_='pos-cate')
        hd_dept = pos_cate_element.text.strip() if pos_cate_element else ""
        
        # 安全提取工作地点
        work_place_element = card.find('span', class_='work-place')
        hd_loc = work_place_element.text.strip().replace('|', '') if work_place_element else ""
        
        # 安全提取招聘人数
        need_people_element = card.find('span', class_='need-people')
        hd_job_num = ""
        if need_people_element:
            hd_job_num = need_people_element.text.replace('招聘人数：', '').strip()
        
        hd_job_category = hd_dept  # 如果需要可以和 hd_dept 一样，或自定义
        post_id = card.get('id', '')
        link = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)