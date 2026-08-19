import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all('div', class_='list-item-main'):
        announcement_name = item.find('div', class_='pos-name').get_text(strip=True)
        hd_dept = item.find('div', class_='pos-company').get_text(strip=True)
        hd_job_category = item.find('div', class_='pos-cate').get_text(strip=True)
        hd_loc = item.find('div', class_='pos-locate').get_text(strip=True)
        hd_job_num = item.find('div', class_='pos-num').get_text(strip=True)

        # 构造 link 字段，使用卡片的 id 属性（假设每个职位都有唯一 id）
        post_id = item.get('id', '')  # 如果 HTML 中有 id，可以用来构造链接
        link = f"https://wecruit.hotjob.cn/SU61154abbbef57c65330a058b/pb/posDetail.html?postId={post_id}&postType=society" if post_id else ''

        job_info = {
            "announcement_name": announcement_name,
            "publish_time": "",  # Placeholder as no publish time is provided in the HTML
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
