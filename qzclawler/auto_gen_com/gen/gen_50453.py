
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0 hjqbak')
    
    for item in items:
        announcement = {}
        
        # 提取公告名称
        title = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4 kMriaU')
        announcement['announcement_name'] = title.get_text(strip=True) if title else ""
        
        # 提取发布时间
        publish_time = item.find('div', class_='style__STJobTime-editor__sc-10r1nhd-16 eKeZsF')
        announcement['publish_time'] = publish_time.get_text(strip=True) if publish_time else ""
        
        # 提取链接
        link = item.find('div', class_='style__STDetailBtn-editor__sc-10r1nhd-29 bvBJPZ')
        announcement['link'] = link.get_text(strip=True) if link else ""
        
        # 提取所属部门或机构
        announcement['hd_dept'] = ""
        
        # 提取工作地点
        announcement['hd_loc'] = ""
        
        # 提取招聘人数
        announcement['hd_job_num'] = ""
        
        # 提取职位类别
        announcement['hd_job_category'] = ""
        
        announcements.append(announcement)

    # 写入JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(announcements, f, ensure_ascii=False, indent=4)
