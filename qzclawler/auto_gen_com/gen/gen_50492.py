
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        job_info = {}
        
        # Extracting the link
        a_tag = li.find('a')
        job_info['link'] = a_tag['href'] if a_tag else ""
        
        # Extracting the announcement name
        dd_tag = li.find('dd')
        job_info['announcement_name'] = dd_tag.get_text(strip=True) if dd_tag else ""
        
        # Extracting the publish time and other details
        ol_tag = li.find('ol')
        if ol_tag:
            details = ol_tag.get_text(strip=True).split(' ｜ ')
            if len(details) >= 3:
                job_info['hd_loc'] = details[0]  # 工作地点
                job_info['hd_dept'] = details[1]  # 所属部门或机构
                job_info['publish_time'] = details[2]  # 发布时间
            else:
                job_info['hd_loc'] = ""
                job_info['hd_dept'] = ""
                job_info['publish_time'] = ""
        else:
            job_info['hd_loc'] = ""
            job_info['hd_dept'] = ""
            job_info['publish_time'] = ""
        
        # Extracting job number and category (assuming they are not provided in the HTML)
        job_info['hd_job_num'] = ""  # 招聘人数
        job_info['hd_job_category'] = ""  # 职位类别
        
        job_list.append(job_info)

    # Writing to JSON file
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
