
import json

from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests
    import time
    url_api = "https://wecruit.hotjob.cn/wecruit/positionInfo/listPosition/SU66ab2efb1c240e2e76253a76"
    url = "https://wecruit.hotjob.cn/SU66ab2efb1c240e2e76253a76/pb/posDetail.html?postId={post_id}&postType=society"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
    }

    id_name_mapping = {}
    page_num = 1

    while True:
        params = {
            "isAjax": "true",
            "request_locale": "zh_CN",
            "recruitType": 2,
            "currentPage": page_num,
            "pageSize": 10,
            "coordinateLat": "",
            "coordinateLng": ""
        }

        try:
            resp = requests.post(url_api, headers=headers, params=params)
            data = resp.json()
            positions = data.get("data", {}).get("pageForm", {}).get("pageData", [])
            print(f"第 {page_num} 页职位数:", len(positions))

            if not positions:
                print(f"第 {page_num} 页没有职位数据")
                break

            for pos in positions:
                pos_name = pos.get("postName")
                pos_id = pos.get("postId")
                if pos_name and pos_id:
                    id_name_mapping[pos_name] = pos_id

            total_pages = data.get("data", {}).get("pageForm", {}).get("totalPage", 1)
            if page_num >= total_pages:
                break

            page_num += 1
            time.sleep(0.2)

        except requests.RequestException as e:
            print(f"请求页 {page_num} 出错:", e)
            break

    print("岗位名 -> ID 映射:", id_name_mapping)
    print("总数:", len(id_name_mapping))

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        summary_div = card.find('div', class_='pos-summary')
        footer_div = card.find('div', class_='pos-ft')

        if title_div and summary_div and footer_div:
            announcement_name = title_div.get('title', '').strip()
            publish_time = footer_div.find('span', class_='pub-time').text.replace('发布时间：', '').strip()
            hd_job_num = footer_div.find('span', class_='need-people').text.replace('招聘人数：', '').strip()
            summary_parts = summary_div.get('title', '').split(' | ')
            hd_dept = summary_parts[0] if len(summary_parts) > 0 else ''
            hd_salary = summary_parts[1] if len(summary_parts) > 1 else ''
            hd_loc = summary_parts[3] if len(summary_parts) > 3 else ''
            hd_job_category = title_div.find_next_sibling('span', class_='pos-cate').text.strip()
            post_id = ""
            for title , id in id_name_mapping.items():
                if announcement_name == title:
                    post_id = id
                    break
            link = url.format(post_id=post_id) if post_id else ""

            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,  # Assuming no link is provided in the HTML
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_salary": hd_salary,
                "hd_job_category": hd_job_category
            })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
