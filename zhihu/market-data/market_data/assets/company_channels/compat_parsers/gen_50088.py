import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='professionItem'):
        announcement_name = item.find('b').get_text(strip=True)
        org = item.find(class_='org').get_text(strip=True)
        publish_time = item.find(class_='date').get_text(strip=True).replace('发布时间：', '')

        site_info = item.find(class_='site')
        job_category = site_info.find_all('span')[0].get_text(strip=True).replace('职位类别：', '')
        hd_loc = site_info.find_all('span')[1].get_text(strip=True).replace('工作地点：', '')

        # Assuming hd_job_num is not provided in the HTML, setting it to None
        hd_job_num = ""

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": "",  # Link is not provided in the HTML
            "hd_dept": org.strip('[]'),  # Removing brackets
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)