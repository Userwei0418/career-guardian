import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='list-item-main'):
        # 提取职位名称
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True)

        # 提取工作地点
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True) if item.find('div',
                                                                                         class_='pos-locate') else None

        # 提取招聘人数
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True) if item.find('div',
                                                                                          class_='pos-num') else ''

        # 提取发布时间
        publish_time = item.find('div', class_='pos-pubTime').get_text(strip=True) if item.find('div',
                                                                                                class_='pos-pubTime') else ''

        # 从HTML中的id字段提取唯一id
        post_id = item['id']  # 假设HTML中的div具有id字段

        # 构造链接
        link = ""

        # 构建职位信息字典
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # Assuming department is not provided in the HTML
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # Assuming job category is not provided in the HTML
        }

        job_list.append(job_info)

    # 将职位信息保存到 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
