import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    import urllib.request
    import urllib.parse
    import ssl
    import json

    url = "https://job.phfund.com.cn/general/demand/listDemandPage"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://job.phfund.com.cn",
        "Referer": "https://job.phfund.com.cn/"
    }

    # 创建不验证SSL的上下文
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    ssl_context.set_ciphers('DEFAULT@SECLEVEL=1')

    job_name_id = {}

    # 分别爬取professionCharacter为1和2的数据
    for profession_char in ["1", "2"]:
        page_index = 1

        while True:
            payload = {
                "professionCharacter": profession_char,
                "page": page_index,
                "size": 50,
                "jobName": "",
                "workAddress": "",
                "releaseDateStart": "",
                "releaseDateEnd": "",
                "postKeyword": ""
            }

            try:
                # 将数据转换为JSON并编码
                data = json.dumps(payload).encode('utf-8')

                # 创建请求
                req = urllib.request.Request(url, data=data, headers=headers)

                # 发送请求
                response = urllib.request.urlopen(req, context=ssl_context, timeout=30)
                response_data = json.loads(response.read().decode('utf-8'))

                if response_data["data"]["total"] == 0:
                    break

                jobs = response_data["data"]["list"]
                for job in jobs:
                    job_name_id[f'{job["jobName"]}_{job["workAddress"]}'] = job["id"]

                page_index += 1
                print(f"professionCharacter={profession_char}, 第 {page_index} 页")

                if page_index > (response_data["data"]["total"] + 49) // 50:
                    break

            except Exception as e:
                print(f"请求出错: {e}")
                break

    soup = BeautifulSoup(htmlcontext, 'html.parser')
    table_rows = soup.select('table.el-table__body tr')
    
    data_list = []
    
    for row in table_rows:
        cells = row.find_all('td')
        if len(cells) < 7:
            continue
        
        announcement_name = cells[0].get_text(strip=True) if cells[0] else ""
        hd_loc = cells[1].get_text(strip=True) if cells[1] else ""
        hd_job_num = cells[2].get_text(strip=True) if cells[2] else ""
        hd_job_category = cells[3].get_text(strip=True) if cells[3] else ""
        hd_dept = cells[4].get_text(strip=True) if cells[4] else ""
        publish_time = cells[5].get_text(strip=True) if cells[5] else ""
        name_id = f"{announcement_name}_{hd_loc}"
        if name_id in job_name_id:
            link = f"https://job.phfund.com.cn/#/postdetail?id={job_name_id[name_id]}"
        else:
            link = ""

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": "",
            "hd_job_category":""
        })
    
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
