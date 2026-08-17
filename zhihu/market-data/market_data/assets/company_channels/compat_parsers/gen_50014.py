import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='list-item-main'):
        # 获取职位名称
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True) if item.find('div',
                                                                                                  class_='pos-name') else ''

        # 获取发布时间
        publish_time = item.find('div', class_='pos-pubTime').get_text(strip=True) if item.find('div',
                                                                                                class_='pos-pubTime') else ''

        # 获取职位详情链接
        post_id = item.get('id', '')
        link = ""

        # 获取职位地点
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True) if item.find('div',
                                                                                         class_='pos-locate') else ''

        # 获取招聘人数
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True) if item.find('div',
                                                                                          class_='pos-num') else ''

        # 获取职位类别
        hd_job_category = item.find('div', class_='pos-cate').get_text(strip=True) if item.find('div',
                                                                                                class_='pos-cate') else ''

        # 将职位信息添加到列表
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": '',  # Placeholder as the department is not provided
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 将结果写入文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
