import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='link-2tgd22te-3'):
        job_info = {}
        link_tag = job.find('a')
        job_info['announcement_name'] = link_tag.find('div', class_='title-20V7ljm-Id').text.strip()
        job_info['publish_time'] = link_tag.find('span', class_='opened-at-20H_gh2Tqd').text.replace('发布时间：',
                                                                                                     '').strip()
        job_info['link'] = link_tag['href']

        details = link_tag.find('div', class_='status-2vTS8JvF_D').find_all('span', class_='status-item-1_w5ygMyMO')
        job_info['hd_dept'] = details[1].text.strip() if len(details) > 1 else ''
        job_info['hd_loc'] = job.find('div', class_='locations-32aEgVWFz_').text.strip()
        job_info['hd_job_num'] = ''  # Placeholder as the number is not provided in the HTML
        job_info['hd_job_category'] = details[0].text.strip() if details else ''

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
