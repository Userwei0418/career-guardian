
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    import requests

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    }

    api_url = "https://job.pcitc.com/recruiting-api/position/search?"

    job_name_to_id = {}
    page_index = 1

    while True:
        params = {
            "placeCode": "",
            "typeCode": "",
            "searchKey": "",
            "pageSize": 10,
            "pageIndex": page_index
        }

        # 使用 POST 请求
        response = requests.get(api_url, headers=headers, params=params, verify=False)
        print(response.url)
        if response.status_code == 200:
            res_json = response.json()
            res = res_json.get("data", [])
            jobs = res_json.get("data", []).get("list", [])
            for job in jobs:
                job_name = job.get("jobposition", "")
                job_loc = job.get("workaddrCityname", "")
                job_id = job.get("id", "")
                job_name_to_id[f"{job_name}_{job_loc}"] = job_id
            total = int(res.get("total", 0))
            if page_index * 10 > total:
                break
            page_index += 1
    print(job_name_to_id)
    job_items = soup.find_all('div', class_='el-card job-item is-hover-shadow')
    
    job_list = []
    
    for job in job_items:
        job_name = job.find('div', class_='job-name').text.strip()
        job_center = job.find('div', class_='job-center')
        location = job_center.find_all('div')[0].text.strip()
        department = job_center.find_all('div')[1].text.strip()
        publish_time = job_center.find_all('div')[2].text.strip().split('~')[0].strip()
        job_num = job_center.find_all('div')[3].text.strip().replace('招聘人数：', '')
        job_category = department  # Assuming job category is the same as department
        job_info = f"{job_name}_{location}"
        if job_info in job_name_to_id:
            job_id = job_name_to_id[job_info]
            link = f"https://job.pcitc.com/#/JobDetail?id={job_id}&typeCode=&placeCode=&searchKey="
        else:
            link = ""
        job_info = {
            "announcement_name": job_name,
            "publish_time": "",
            "link": link,  # Link is not provided in the HTML
            "hd_dept": department,
            "hd_loc": location,
            "hd_job_num": job_num,
            "hd_job_category": job_category
        }
        
        job_list.append(job_info)
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
