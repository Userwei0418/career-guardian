import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='qs-column w-dyn-item'):
        # 安全获取文本
        announcement_name_tag = item.find('div', class_='title6 display')
        announcement_name = announcement_name_tag.get_text(strip=True) if announcement_name_tag else ""

        date_wrapper = item.find('div', class_='qs-career-date-wrapper')
        publish_time = ""
        if date_wrapper:
            first_label = date_wrapper.find('div', class_='label')
            if first_label:
                publish_time = first_label.get_text(strip=True)

        link_tag = item.find('a')
        link = link_tag['href'] if link_tag and link_tag.has_attr('href') else ""

        hd_dept_tag = item.find('div', fs_list_field='department')
        hd_dept = hd_dept_tag.get_text(strip=True) if hd_dept_tag else ""

        hd_loc_tag = item.find('div', fs_list_field='city')
        hd_loc = hd_loc_tag.get_text(strip=True) if hd_loc_tag else ""

        hd_job_num = ""  # HTML 没有提供，可留空或生成编号

        hd_job_category_tag = item.find('div', fs_list_field='type')
        hd_job_category = hd_job_category_tag.get_text(strip=True) if hd_job_category_tag else ""

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
