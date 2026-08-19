
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    departments = soup.find_all('div', class_='job-posts--table--department')
    
    for department in departments:
        dept_name = department.find('h3', class_='section-header font-primary').text.strip()
        job_posts = department.find_all('tr', class_='job-post')
        
        for job in job_posts:
            job_info = job.find('td', class_='cell')
            link = job_info.find('a')['href']
            announcement_name = job_info.find('p', class_='body body--medium').text.strip()
            publish_time = ""  # Placeholder as the HTML does not contain this information
            hd_dept = dept_name
            hd_loc = job_info.find('p', class_='body body__secondary body--metadata').text.strip()
            hd_job_num = ""  # Placeholder as the HTML does not contain this information
            hd_job_category = ""  # Placeholder as the HTML does not contain this information
            
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
