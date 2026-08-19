import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.select('li.w-list-item'):
        announcement_name = item.select_one('h3.w-list-title a').get_text(strip=True) if item.select_one(
            'h3.w-list-title a') else ""
        link = item.select_one('h3.w-list-title a')['href'] if item.select_one('h3.w-list-title a') else ""
        desc = item.select_one('p.w-list-desc').get_text(strip=True) if item.select_one('p.w-list-desc') else ""

        # Extracting details from the description
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        if desc:
            parts = desc.split('|')
            if len(parts) > 0:
                hd_dept = parts[0].replace('招聘单位：', '').strip()
            if len(parts) > 1:
                hd_loc = parts[1].replace('工作地点：', '').strip()
            if len(parts) > 2:
                hd_job_num = parts[2].replace('学历要求：', '').strip()

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

