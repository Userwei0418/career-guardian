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
        if len(cols) > 0 and cols[0].a:
            announcement_name = cols[0].a.get('title', '')
            link = cols[0].a.get('href', '')
        
        # 安全提取发布时间
        publish_time = ""
        if len(cols) > 3:
            publish_time = cols[3].text.strip() if cols[3] else ""
        
        hd_dept = ''  # No data available in the provided HTML
        hd_job_num = ''  # No data available in the provided HTML
        hd_job_category = ''  # No data available in the provided HTML

        # 安全提取工作地点
        hd_loc = ""
        if len(cols) > 2:
            hd_loc = cols[2].get('title', '') if cols[2] else ""

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