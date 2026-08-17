import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        # 职位名称
        announcement_name = item.find(class_='pos-name').get_text(strip=True)

        # 招聘人数
        hd_job_num = item.find(class_='pos-num').get_text(strip=True)

        # 发布时间
        publish_time = item.find(class_='pos-pubTime').get_text(strip=True)

        # 工作地点
        hd_loc = item.find(class_='pos-locate').get_text(strip=True)

        # 部门
        hd_dept = item.find(class_='pos-department').get_text(strip=True)

        # 自动获取 postId
        post_id = item.get('id')  # 如果列表项没有 id，会返回 None
        link = ""
        if post_id:
            link = f"https://wecruit.hotjob.cn/SU61154abbbef57c65330a058b/pb/posDetail.html?postId={post_id}&postType=society"

        job_entry = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # 没有提供职位类别
        }

        job_list.append(job_entry)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
