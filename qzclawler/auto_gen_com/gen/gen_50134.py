
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    base_url = "https://ehjobs.deloitte.com.cn/SU649e304a6a9f0ef690533e9a/pb/posDetail.html?postId={}&postType=society"

    for card in soup.find_all('div', class_='list-card-item1'):
        announcement_name = card.find('span', class_='top-label').get_text(strip=True)
        publish_time = card.find('span', class_='pub-time').get_text(strip=True).replace('发布时间：', '')
        post_id = card.get('id')
        link = base_url.format(post_id) if post_id else ''
        hd_dept = card.find('span', class_='pos-cate').get_text(strip=True)
        hd_loc = card.find('span', class_='work-place').get_text(strip=True).split(' | ')[0]
        hd_job_num = ''  # Placeholder, as the job number is not provided in the HTML
        hd_job_category = card.find('span', class_='pos-cate').get_text(strip=True)

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
