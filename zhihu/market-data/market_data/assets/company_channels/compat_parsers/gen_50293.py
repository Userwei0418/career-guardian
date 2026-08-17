import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_items = soup.find_all('li', class_='jobs-list-item')
    for job in job_items:
        # 使用安全获取方式，避免 None
        announcement_name = job.find('div', class_='job-title')
        announcement_name = announcement_name.get_text(strip=True) if announcement_name else ""

        publish_time_tag = job.find('a', {'data-ph-at-job-post-date-text': True})
        publish_time = publish_time_tag['data-ph-at-job-post-date-text'] if publish_time_tag else ""

        link_tag = job.find('a', class_='au-target')
        link = link_tag['href'] if link_tag else ""

        hd_dept_tag = job.find('span', class_='category')
        hd_dept = hd_dept_tag.get_text(strip=True) if hd_dept_tag else ""

        hd_loc_tag = job.find('span', class_='job-location')
        hd_loc = hd_loc_tag.get_text(strip=True) if hd_loc_tag else ""

        hd_job_num_tag = job.find('span', class_='jobId')
        hd_job_num = hd_job_num_tag.get_text(strip=True) if hd_job_num_tag else ""

        # 职位类别如果和部门是同一class，需要分辨
        hd_job_category_tag = job.find('span', class_='job-category')
        hd_job_category = hd_job_category_tag.get_text(strip=True) if hd_job_category_tag else hd_dept

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": "",
            "hd_job_num": "",
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
