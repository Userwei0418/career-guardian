import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    job_elements = soup.select('div[class*="link"]')  # 宽松匹配

    for job in job_elements:
        title_div = job.find('div', class_=lambda c: c and 'title' in c)
        title = title_div.get_text(strip=True).replace('急','') if title_div else ''

        publish_span = job.find('span', class_=lambda c: c and 'opened-at' in c)
        publish_time = publish_span.get_text(strip=True).replace('发布时间：', '') if publish_span else ''

        a_tag = job.find('a')
        link = a_tag['href'] if a_tag else ''

        loc_div = job.find('div', class_=lambda c: c and 'locations' in c)
        location = loc_div.get_text(strip=True) if loc_div else ''

        status_items = job.find_all('span', class_=lambda c: c and 'status-item' in c)
        hd_dept = status_items[1].get_text(strip=True) if len(status_items) > 1 else ''
        hd_job_category = status_items[2].get_text(strip=True) if len(status_items) > 2 else ''
        hd_job_num = ''

        job_info = {
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_dept
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"✅ 已提取 {len(job_list)} 条职位信息。")
