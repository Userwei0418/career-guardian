import json
from bs4 import BeautifulSoup




def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []
    import requests

    api_url = "https://job.sinopec.com/api/sz/socialJobInfo/selectSocialJobVoByPage"

    headers = {
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "referer": "https://campus.pingan.com/tech/position",
        "accept": "application/json;charset=utf-8"
    }
    job_name_to_ids = {}

    payload = {
        "searchLike": "",
        "endTag": "N",
        "page": 1,
        "limit": 50
    }

    res = requests.post(api_url, json=payload, headers=headers)
    print(res.json())

    jobs = res.json().get("data", {}).get("records", [])

    for job in jobs:
        job_name_to_ids[job["duties"]] = job["id"]

    print(job_name_to_ids)
    print(len(job_name_to_ids))

    for post_card in soup.find_all(class_='post_card'):
        title = post_card.find(class_='title_left').get('title') if post_card.find(class_='title_left') else ''
        location = post_card.find('span', title='工作地点：').find_next('span').text if post_card.find('span',
                                                                                                      title='工作地点：') else ''
        job_num = post_card.find('span', title='招聘人数：').find_next('span').text if post_card.find('span',
                                                                                                     title='招聘人数：') else ''
        company = post_card.find(class_='company').text.strip() if post_card.find(class_='company') else ''
        link = ""
        if title in job_name_to_ids:
            link = f"https://job.sinopec.com/#/social/jobDetail?id={job_name_to_ids[title]}&endTag=N"

        job_info = {
            "announcement_name": title,
            "publish_time": "",  # Assuming publish_time is not available in the provided HTML
            "link": link,  # Assuming link is not available in the provided HTML
            "hd_dept": company,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": ""  # Assuming job category is not available in the provided HTML
        }

        job_list.append(job_info)

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
