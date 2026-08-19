import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, tempfile):
    soup = BeautifulSoup(html_content, 'html.parser')
    job_list = []

    # 直接找到每个职位 a 标签
    job_cards = [a for a in soup.find_all('a') if a.find('div', class_='positionItem__fca8c0')]

    for card in job_cards:
        div_card = card.find('div', class_='positionItem__fca8c0')

        # 职位名称
        title_tag = div_card.find('span', class_='positionItem-title-text')
        announcement_name = title_tag.get_text(strip=True) if title_tag else ""

        # 地点、工作类型、职位类别
        sub_tag_spans = div_card.find('div', class_='subTitle__fca8c0').find_all('span')
        location = sub_tag_spans[0].get_text(strip=True) if len(sub_tag_spans) >= 1 else ""
        job_type = sub_tag_spans[1].get_text(strip=True) if len(sub_tag_spans) >= 2 else ""
        job_category = sub_tag_spans[2].get_text(strip=True) if len(sub_tag_spans) >= 3 else ""

        # 职位描述
        desc_tag = div_card.find('div', class_='jobDesc__fca8c0')
        job_desc = desc_tag.get_text(strip=True) if desc_tag else ""

        # 链接
        link = card.get('href', "")

        # 发布部门和职位编号暂时空
        hd_dept = ""
        hd_job_num = ""
        if "实习" in announcement_name or "Intern" in announcement_name:
            hd_hopeworktype = "实习"
        else:
            hd_hopeworktype = ""

        job_list.append({
            "announcement_name": announcement_name,
            "hd_loc": "",
            "hd_job_category": "",
            "link": link,
            "hd_dept": hd_dept,
            "hd_job_num": hd_job_num,
            "hd_hopeworktype": hd_hopeworktype
        })

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
