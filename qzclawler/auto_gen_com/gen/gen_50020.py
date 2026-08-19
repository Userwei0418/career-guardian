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

        # 取出 postId（假设在 data-post-id 属性中）
        post_id = item.get('id')  # 你要确认 HTML 里是这个属性名
        link = ""


        job_info = {
            "announcement_name": announcement_name,
            "publish_time": "",  # HTML 里没有则空着
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
