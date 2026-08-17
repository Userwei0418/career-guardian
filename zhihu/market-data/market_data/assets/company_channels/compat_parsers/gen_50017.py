import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 假设每个职位信息在 class="list-item-main" 中
    for item in soup.find_all(class_='list-item-main'):
        # 提取职位名称
        announcement_name = item.find(class_='pos-name').get_text(strip=True)

        # 提取发布时间
        publish_time = item.find(class_='pos-pubTime').get_text(strip=True)

        # 提取工作地点
        hd_loc = item.find(class_='pos-locate').get_text(strip=True) if item.find(class_='pos-locate') else ''

        # 提取招聘人数
        hd_job_num = item.find(class_='pos-num').get_text(strip=True) if item.find(class_='pos-num') else ''

        # 提取职位类别
        hd_job_category = item.find(class_='pos-cate').get_text(strip=True) if item.find(class_='pos-cate') else ''

        # 提取postId用于构建职位链接
        post_id = item.get('id', '')  # 假设div的id是职位唯一标识符

        # 构造链接
        link = ""

        # 添加职位信息到列表
        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # 假设没有提供部门信息
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 保存职位信息到JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
