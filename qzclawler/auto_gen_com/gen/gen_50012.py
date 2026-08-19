import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        try:
            # 获取职位名称
            announcement_name = item.find(class_='pos-name').get_text(strip=True) if item.find(
                class_='pos-name') else ''

            # 获取发布时间
            publish_time = item.find(class_='pos-pubTime').get_text(strip=True) if item.find(
                class_='pos-pubTime') else ''

            # 获取职位详情链接
            post_id = item.get('id', '')
            link = ""

            # 获取职位部门
            hd_dept = item.find(class_='pos-cate').get_text(strip=True) if item.find(class_='pos-cate') else ''

            # 获取职位地点
            hd_loc = item.find(class_='pos-locate').get_text(strip=True) if item.find(class_='pos-locate') else ''

            # 设置招聘人数和职位类别占位符
            hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
            hd_job_category = ""  # Placeholder as the job category is not provided in the HTML

            # 将职位信息添加到列表
            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

        except Exception as e:
            print(f"Error processing a job item: {e}")
            continue

    # 将结果写入文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
