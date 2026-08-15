python
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    result = []
    job_items = soup.find_all('div', class_='style__STListItem-editor__sc-10r1nhd-0 hjqbak')
    
    for item in job_items:
        # 提取公告名称
        title_elem = item.find('div', class_='style__STJobTitle-editor__sc-10r1nhd-4 kMriaU')
        announcement_name = title_elem.get_text(strip=True) if title_elem else ''
        
        # 提取标签信息（包含工作地点和职位类别）
        label_section = item.find('div', class_='style__STLabelSection-editor__sc-10r1nhd-11 kDWFRA')
        labels = label_section.find_all('div', class_='style__STJobLabel-editor__sc-10r1nhd-12 jALFTx') if label_section else []
        label_texts = [label.find('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK').get_text(strip=True) for label in labels if label.find('div', class_='style__STLabelText-editor__sc-10r1nhd-13 cJYhpK')]
        
        # 工作地点（第三个标签）
        hd_loc = label_texts[2] if len(label_texts) > 2 else ''
        # 职位类别（第四个标签）
        hd_job_category = label_texts[3] if len(label_texts) > 3 else ''
        
        # 构造职位信息字典
        job_info = {
            'announcement_name': announcement_name,
            'publish_time': '',  # 未找到发布时间信息
            'link': '',  # 未找到链接信息
            'hd_dept': '',  # 未找到所属部门信息
            'hd_loc': hd_loc,
            'hd_job_num': '',  # 未找到招聘人数信息
            'hd_job_category': hd_job_category
        }
        result.append(job_info)
    
    # 写入JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
