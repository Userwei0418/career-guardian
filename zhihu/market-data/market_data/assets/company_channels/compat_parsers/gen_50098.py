import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 注意：你的 HTML 中 <a> 外面包裹 class="positionItem__fca8c0" 的 div
    for job in soup.find_all('a'):
        title = job.find('span', class_='positionItem-title-text')
        title = title.get_text(strip=True) if title else ""

        # 地点直接取 subTitle 第一个 span
        sub_title = job.find('div', class_='subTitle__fca8c0 positionItem-subTitle')
        location = sub_title.find('span').get_text(strip=True) if sub_title else ""

        # 所有 infoText__fca8c0
        info_texts = sub_title.find_all('span', class_='infoText__fca8c0') if sub_title else []
        job_category = info_texts[2].get_text(strip=True) if len(info_texts) > 2 else ""
        job_id = ""

        link = job['href'] if job.has_attr('href') else ""

        job_info = {
            "announcement_name": title,
            "publish_time": "",
            "link": link,
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": job_id,
            "hd_job_category": job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
