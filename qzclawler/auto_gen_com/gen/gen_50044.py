import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.jobsTable tbody tr')
    
    job_list = []
    
    for row in table_rows[1:]:  # Skip the header row
        cols = row.find_all('td')
        if len(cols) < 4:
            continue
        
        # 安全提取职位名称和链接
        announcement_name = ""
        link = ""
        first_col_a = cols[0].find('a') if len(cols) > 0 else None
        if first_col_a:
            announcement_name = first_col_a.get('title', '')
            link = first_col_a.get('href', '')
        
        # 安全提取发布时间
        publish_time = ""
        if len(cols) > 3:
            publish_time = cols[3].text.strip() if cols[3] else ""
        
        # 安全提取部门信息
        hd_dept = ""
        if len(cols) > 1:
            hd_dept = cols[1].get('title', '').strip() if cols[1] else ""
        
        # 安全提取工作地点
        hd_loc = ""
        if len(cols) > 2:
            hd_loc = cols[2].get('title', '').strip() if cols[2] else ""
        
        hd_job_num = ''  # Placeholder as the data is not provided in the HTML
        hd_job_category = ''  # Placeholder as the data is not provided in the HTML
        
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