import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('div', class_='link-2tgd22te-3'):
        job_info = {}

        # 安全获取 <a> 标签
        link_tag = job.find('a')
        if not link_tag:
            continue  # 如果没有 <a> 标签，跳过这一条

        # 提取职位名称
        title_tag = link_tag.find('div', class_='title-20V7ljm-Id')
        job_info['announcement_name'] = title_tag.get_text(strip=True).replace("急","") if title_tag else ''

        # 提取链接
        job_info['link'] = link_tag.get('href', '')

        # 提取状态信息（部门、岗位类型）
        status_items = link_tag.find('div', class_='status-2vTS8JvF_D')
        if status_items:
            spans = status_items.find_all('span', class_='status-item-1_w5ygMyMO')
            job_info['hd_dept'] = spans[0].get_text(strip=True) if len(spans) > 0 else ''
            job_info['hd_job_category'] = spans[2].get_text(strip=True) if len(spans) > 1 else ''
        else:
            job_info['hd_dept'] = ''
            job_info['hd_job_category'] = ''

        # 提取工作地点
        loc_tag = link_tag.find('div', class_='locations-32aEgVWFz_')
        job_info['hd_loc'] = loc_tag.get_text(strip=True) if loc_tag else ''

        # 职位编号不存在时留空
        job_info['hd_job_num'] = ''

        job_list.append(job_info)

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
