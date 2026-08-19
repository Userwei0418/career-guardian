import json
import requests
from bs4 import BeautifulSoup

BASE_DETAIL_URL = "https://wecruit.hotjob.cn/SU63e5f2362f9d2414bbf056fd/pb/posDetail.html?postId={}&postType={}"
API_URL = "https://wecruit.hotjob.cn/wecruit/positionInfo/listPosition/SU63e5f2362f9d2414bbf056fd"


def extract_table_from_html(htmlcontext, tempfile):
    """自动先爬校招(recruitType=1)，再爬社招(recruitType=2)，并解析 HTML 生成职位详情列表"""

    postid_map = {}

    # -----------------------------
    # 1. 循环两种招聘类型
    # -----------------------------
    for recruit_type in [1, 2]:  # 1=校招，2=社招
        current_page = 1
        while True:
            try:
                resp = requests.post(API_URL, data={
                    "isFrompb": True,
                    "recruitType": recruit_type,
                    "pageSize": 50,
                    "currentPage": current_page
                })
                resp.raise_for_status()
                js = resp.json()
                page_data = js.get("data", {}).get("pageForm", {}).get("pageData", [])
                for item in page_data:
                    postid_map[item["postName"].strip()] = {
                        "postId": item["postId"],
                        "postType": "campus" if recruit_type == 1 else "society"
                    }

                total_page = js.get("data", {}).get("pageForm", {}).get("totalPage", 1)
                if current_page >= total_page:
                    break
                current_page += 1
            except Exception as e:
                print(f"[招聘类型 {recruit_type}] 获取 postId 映射失败: {e}")
                break

    print(f"职位名称 -> postId 映射完成，共 {len(postid_map)} 条")

    # -----------------------------
    # 2. 解析 HTML
    # -----------------------------
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for card in soup.find_all('div', class_='card-item-wrap'):
        title_div = card.find('div', class_='pos-title-item')
        summary_div = card.find('div', class_='pos-summary')
        pub_time_span = card.find('span', class_='pub-time')
        need_people_span = card.find('span', class_='need-people')

        announcement_name = title_div.get('title', '').strip() if title_div else ''
        publish_time = pub_time_span.text.replace('发布时间：', '').strip() if pub_time_span else ''
        hd_dept = title_div.find_next('span', class_='pos-cate').get('title', '').strip() if title_div else ''
        hd_loc = summary_div.get('title', '').strip() if summary_div else ''
        hd_job_num = need_people_span.text.replace('招聘人数：', '').strip() if need_people_span else ''
        hd_job_category = title_div.find_next('span', class_='pos-cate').text.strip() if title_div else ''

        # 从映射表里找 postId，并生成对应招聘类型的 link
        post_info = postid_map.get(announcement_name)
        link = BASE_DETAIL_URL.format(post_info["postId"], post_info["postType"]) if post_info else ''

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # -----------------------------
    # 3. 写入 JSON 文件
    # -----------------------------
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    return job_list
