import json
import requests
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    base_url = "https://campus.boe.com/xzlb2022/"
    params = {
        "c1": 0,
        "ywbk": 0,
        "type": 1,
        "PageIndex": 1
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.7204.243 Safari/537.36",
        "Referer": "https://campus.boe.com/xzlb2022/",
    }

    cookies = {
        "Hm_lvt_4ea4fc530ed4220278c643746a5a71bf": "1765337257",
        "HMACCOUNT": "709A8FA55A8EF0D7",
        "_ga": "GA1.1.1612211053.1765337259",
        # ...
    }

    # 请求页面函数
    def fetch_page(page_index):
        params["PageIndex"] = page_index
        resp = requests.get(base_url, params=params, headers=headers, cookies=cookies)
        resp.encoding = "utf-8"
        return resp.text

    # 所有数据累积到这里
    job_list_all = []

    page_index = 1
    while True:
        html = fetch_page(page_index)
        print("正在处理第", page_index, "页…")

        # 停止条件：页面提示不存在 / 超范围
        if "当前页码超出范围" in html or "暂无数据" in html:
            print("已抓完所有页面")
            break

        soup = BeautifulSoup(html, 'html.parser')

        # 当页数据容器
        for li in soup.select('div.zwlb ul li a.godetail'):
            announcement_name = li.find('b').get_text(strip=True) if li.find('b') else ""
            publish_time = ""
            link = li.get('data-href', "")
            hd_dept = ""
            hd_loc = li.find('p').get_text(strip=True) if li.find('p') else ""
            hd_job_num = ""
            hd_job_category = ""

            # 职位人数和类别
            spans = li.select('div.zwtxt span')
            for span in spans:
                text = span.get_text(strip=True)
                if text.startswith("招聘人数"):
                    hd_job_num = text.replace("招聘人数：", "")
                elif text:
                    hd_job_category = text

            job_list_all.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

        page_index += 1

    # 最终一次性写入文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list_all, f, ensure_ascii=False, indent=4)

    print(f"全部数据已保存到 {tempfile}")
