
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_items = soup.find_all('div', class_='job-item')
    import requests

    url = "https://pivotportal.hellobike.com/pivot-zeus/inner/getOuterPositionADs"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://careers.hellobike.com",
        "Referer": "https://careers.hellobike.com/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Sec-CH-UA": "\"Chromium\";v=\"142\", \"Google Chrome\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": "\"Windows\"",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    }
    page_index = 1
    job_name_id = {}
    while True:
        payload = {
            "categoryDescription": "社会招聘",
            "jobCategoryNames": "",
            "jobadIshot": "",
            "key": "",
            "pageNum": page_index,
            "pageSize": 50,
            "workingPlaces": [],
            "jobCategoryNameList": [],
            "jobLocale": [],
            "jobType": []
        }
        res = requests.post(url, json=payload, headers=headers)
        print(res.json())
        if res.json()["data"]["total"] == 0:
            break
        jobs = res.json()["data"]["rows"]
        for job in jobs:
            job_name_id[f'{job["jobTitle"]}_{job["workingPlace"]}'] = job["adId"]
        page_index += 1
        print(f"第 {page_index} 页")
        print(job_name_id)
        if page_index > (res.json()["data"]["total"] + 49) // 50:
            break
    print(job_name_id)
    print(len(job_name_id))
    result = []
    
    for item in job_items:
        announcement_name = item.find('h4').get_text(strip=True) if item.find('h4') else ""
        publish_time = item.find('div', class_='time').get_text(strip=True).replace(" 发布", "") if item.find('div', class_='time') else ""
        link = ""  # Assuming no link is provided in the HTML
        hd_dept = item.find('div', class_='dept-name').get_text(strip=True) if item.find('div', class_='dept-name') else ""
        hd_loc = item.find('div', class_='addr').get_text(strip=True) if item.find('div', class_='addr') else ""
        hd_job_num = ""  # Assuming no job number is provided in the HTML
        hd_job_category = ""  # Assuming no job category is provided in the HTML
        name_loc = f"{announcement_name}_{hd_loc}"
        if name_loc in job_name_id:
            id = job_name_id[name_loc]
            link = f"https://careers.hellobike.com/#/jobDetail?id={id}&from=社会招聘"
        else:
            link = ""

        result.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_dept
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
