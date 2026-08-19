import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table tbody tr')
    import ssl
    import requests
    from requests.adapters import HTTPAdapter

    # 定义一个适配器，开启 legacy renegotiation
    class LegacyAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = ssl.create_default_context()
            ctx.options |= 0x4  # 等价于 ssl.OP_LEGACY_SERVER_CONNECT
            kwargs['ssl_context'] = ctx
            return super().init_poolmanager(*args, **kwargs)

        def proxy_manager_for(self, *args, **kwargs):
            ctx = ssl.create_default_context()
            ctx.options |= 0x4
            kwargs['ssl_context'] = ctx
            return super().proxy_manager_for(*args, **kwargs)

    # 全局替换 https 适配器
    session = requests.Session()
    session.mount("https://", LegacyAdapter())

    api_url = "https://job1.ccb.com/tran/WCCMainPlatV5"

    headers = {
        "User-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "referer": "https://job1.ccb.com/cn/job/job_list.html?planType=&keyword=",
        "accept": "application/json, text/javascript, */*; q=0.01"
    }
    job_name_to_ids = {}
    planType = [
        {"planType": "SH"},
        {"planType": "XY"}
    ]
    for Type in planType:
        pt = Type["planType"]
        print(f"正在抓取{pt}的职位")
        while True:
            payload = {
                "CCB_IBSVersion": "V5",
                "isAjaxRequest": "true",
                "SERVLET_NAME": "WCCMainPlatV5",
                "TXCODE": "NHR104",
                "keyWord": "",
                "viewFffectivePost": "1",
                "planType": pt,
                "orgId": "",
                "secondOrgId": "",
                "areaId": "",
                "planPostId": "",
                "planId": "",
                "PAGE_JUMP": 1,
                "REC_IN_PAGE": 4000
            }

            res = session.get(api_url, params=payload, headers=headers)
            jobs = res.json().get("planPostList", {})
            print(jobs)

            for job in jobs:
                key = f"{job['planPostName']}_{job['workPlace']}_{job['secondOName']}"
                if key not in job_name_to_ids:
                    job_name_to_ids[key] = {'planId': job['planId'], 'planPost': job['planPost'],
                                            'orgId': job['orgId'], 'secondOrgId': job['secondOrgId']}
            break

        print(job_name_to_ids)
        print(len(job_name_to_ids))

    data_list = []

    for row in table_rows:
        cols = row.find_all('td')
        announcement_name = cols[0].get_text(strip=True)
        hd_dept = cols[3].get_text(strip=True)
        hd_loc = cols[4].get_text(strip=True)
        hd_job_num = ""  # Placeholder as the job number is not provided in the HTML
        hd_job_category = ""
        publish_time = ""  # Placeholder as the publish time is not provided in the HTML
        title =f"{announcement_name}_{hd_loc}_{hd_dept}"
        print( title)
        if title in job_name_to_ids:
            plan_id = job_name_to_ids[title]["planId"]
            plan_post = job_name_to_ids[title]["planPost"]
            org_id = job_name_to_ids[title]["orgId"]
            second_org_id = job_name_to_ids[title]["secondOrgId"]
            link = f"https://job1.ccb.com/cn/job/job_detail.html?planId={plan_id}&planPost={plan_post}&orgId={org_id}&secondOrgId={second_org_id}"
        else:
            link = ""

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
