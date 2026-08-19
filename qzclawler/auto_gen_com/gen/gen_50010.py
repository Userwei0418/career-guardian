
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all(class_='list-item-main'):
        announcement_name = item.find(class_='pos-name').get_text(strip=True)
        publish_time = item.find(class_='pos-pubTime').get_text(strip=True)
        post_id = item.get('id', '').strip()  # 从 HTML 中获取职位 ID

        # 构造职位详情页链接
        link = (
            f"https://wecruit.hotjob.cn/SU63181444bef57c71a910505b/"
            f"pb/posDetail.html?postId={post_id}&postType=society"
        ) if post_id else ''

        hd_dept = ''  # HTML中未提供，留空
        hd_loc = item.find(class_='pos-locate').get_text(strip=True)
        hd_job_num = item.find(class_='pos-num').get_text(strip=True)
        hd_job_category = item.find(class_='pos-cate').get_text(strip=True)

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
