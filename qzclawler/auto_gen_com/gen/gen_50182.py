
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    posts = soup.find_all('li', class_='post_box')
    for post in posts:
        announcement_name = post.find('div', class_='post_title').get_text(strip=True)
        publish_time = ""  # Assuming publish_time is not available in the provided HTML
        link = ""  # Assuming link is not available in the provided HTML
        hd_dept = post.find('div', class_='post_tag_box').find_all('div', class_='post_tag')[2].get_text(strip=True).replace('｜', '').strip()
        hd_loc = post.find('div', class_='site_box').find('div', class_='site').get_text(strip=True)
        hd_job_num = ""  # Assuming hd_job_num is not available in the provided HTML
        hd_job_category = post.find('div', class_='post_tag_box').find('div', class_='post_tag').get_text(strip=True)

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
