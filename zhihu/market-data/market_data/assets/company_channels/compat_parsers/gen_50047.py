
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for li in soup.find_all('li'):
        job_info = {}
        link_tag = li.find('a')
        if link_tag:
            job_info['link'] = link_tag['href']
            title_tag = link_tag.find('span', class_='title')
            if title_tag:
                job_info['announcement_name'] = title_tag.text.strip()
            release_time_tag = link_tag.find('span', class_='releaseTime')
            if release_time_tag:
                job_info['publish_time'] = release_time_tag.text.replace('更新时间：', '').strip()
            bottom_info = link_tag.find('div', class_='bottomInfo')
            if bottom_info:
                for label in bottom_info.find_all('span', class_='label'):
                    txt = label.find('span', class_='txt').text.strip()
                    if '所属机构' in txt:
                        job_info['hd_dept'] = txt.replace('所属机构：', '').strip()
                    elif '职位类别' in txt:
                        job_info['hd_job_category'] = txt.replace('职位类别：', '').strip()
                    elif '招聘人数' in txt:
                        job_info['hd_job_num'] = txt.replace('招聘人数：', '').strip()
                    elif '工作地点' in txt:
                        job_info['hd_loc'] = txt.replace('工作地点：', '').strip()

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
