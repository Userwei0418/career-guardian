import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 找到所有招聘条目
    postings = soup.find_all('div', class_='cbox-1 p_loopitem')

    for posting in postings:
        # 招聘名称
        announcement_tag = posting.find('p', class_='e_text-3 s_title')
        announcement_name = announcement_tag.get_text(strip=True) if announcement_tag else ""

        # 链接
        link_tag = posting.find('a')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""

        # 详细信息
        details_tag = posting.find('div', class_='e_richText-8 s_title clearfix')
        details_text = details_tag.get_text(strip=True) if details_tag else ""
        details = details_text.split('，') if details_text else []

        # 提取字段，没值则为空
        hd_job_num = details[0].split('：')[1] if len(details) > 0 and '：' in details[0] else ""
        hd_dept = ""  # HTML未提供
        hd_loc = ""   # HTML未提供
        hd_job_category = ""  # HTML未提供
        publish_time = ""     # HTML未提供

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 输出到JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
