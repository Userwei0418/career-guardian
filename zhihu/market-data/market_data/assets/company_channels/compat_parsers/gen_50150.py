import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')

    # 查找所有职位条目
    positions = soup.find_all('div', class_='positionItem__fca8c0')

    data_list = []

    # 遍历每个职位
    for position in positions:
        # 提取职位ID（data-id属性）
        position_id = position['data-id'] if position.get('data-id') else ""

        # 提取职位名称
        title_tag = position.find('span', class_='positionItem-title-text')
        announcement_name = title_tag.get_text(strip=True) if title_tag else ""

        # 提取职位链接
        link = position['href'] if position.get('href') else ""

        # 提取工作地点、职位类别等信息
        sub_title_tag = position.find('div', class_='subTitle__fca8c0 positionItem-subTitle')

        hd_loc = ""
        hd_job_category = ""
        if sub_title_tag:
            spans = sub_title_tag.find_all('span')
            if spans:
                hd_loc = spans[0].get_text(strip=True) if len(spans) > 0 else ""  # 工作地点
                hd_job_category = spans[3].get_text(strip=True) if len(spans) > 3 else ""  # 职位类别

        # 假设其他字段无法从 HTML 中提取，因此保持为空
        publish_time = ""
        hd_dept = ""
        hd_job_num = ""

        # 提取职位描述
        job_desc_tag = position.find('div', class_='jobDesc__fca8c0 positionItem-jobDesc')
        job_desc = job_desc_tag.get_text(strip=True) if job_desc_tag else ""

        # 将提取的数据存入列表
        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": "",
            "hd_job_num": hd_job_num,
            "hd_job_category": "",
        })

    # 保存为JSON格式
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
