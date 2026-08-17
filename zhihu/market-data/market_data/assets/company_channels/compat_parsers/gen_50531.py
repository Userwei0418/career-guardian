import json
from bs4 import BeautifulSoup

def safe_text(tag, default=""):
    if not tag:
        return default
    return tag.get_text(strip=True)

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for job in soup.find_all('li', class_='social_core_list_nub'):
        # 公告名称
        announcement_name = safe_text(job.find('div', class_='std_tit4'))

        # 链接
        link_tag = job.find('a', class_='scln_link')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""

        # 详情列表
        ul_tag = job.find('ul', class_='scln_top_text std_word')
        details = ul_tag.find_all('li') if ul_tag else []

        # 安全提取每一项
        hd_dept =  ""
        hd_loc = ""
        hd_job_num = safe_text(details[0].find('span') if len(details) > 1 else "")
        publish_time = safe_text(details[1].find('span') if len(details) > 1 else "")

        # 岗位类别：存在 p 标签，格式为 “岗位类别：xxx”
        hd_job_category = ""

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
