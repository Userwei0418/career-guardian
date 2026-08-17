
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    base_url = "https://wecruit.hotjob.cn/SU61e0e24fbef57c796ed27ff3/pb/posDetail.html"
    for card in soup.find_all('div', class_='list-card-item1'):
        announcement_name = card.find('span', class_='top-label').text.strip()
        publish_time = card.find('span', class_='pub-time').text.replace('发布时间：', '').strip()
        post_id = card.get('id', '')
        link = f"{base_url}?postId={post_id}&postType=campus" if post_id else ""
        hd_dept = ''  # Assuming no department info is provided in the HTML
        hd_loc = card.find('span', class_='work-place').text.strip().replace(' | ', '')
        hd_job_num = ''  # Assuming no job number info is provided in the HTML
        hd_job_category = card.find('span', class_='pos-cate').text.strip()

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
