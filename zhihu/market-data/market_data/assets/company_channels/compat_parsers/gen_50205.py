import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='link-2tgd22te-3'):
        job_info = {}
        link_tag = job.find('a')
        job_info['link'] = link_tag['href']

        title_div = job.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_div.get_text(strip=True).replace('急',"")

        publish_time_span = job.find('span', class_='opened-at-20H_gh2Tqd')
        job_info['publish_time'] = publish_time_span.get_text(strip=True).replace('发布时间：', '')

        location_div = job.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] = location_div.get_text(strip=True)

        # Assuming hd_dept and hd_job_num are not present in the provided HTML
        job_info['hd_dept'] = ""
        job_info['hd_job_num'] = ""

        if "实习" in title_div.get_text(strip=True).replace('急',""):
            job_info["hd_hopeworktype"] = "实习"
        else:
            job_info["hd_hopeworktype"] = ""
        status_span = job.find('span', class_='status-item-1_w5ygMyMO')
        job_info['hd_job_category'] = status_span.get_text(strip=True) if status_span else ""

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
