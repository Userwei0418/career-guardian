import json
import requests
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    # 正确请求地址
    base_url = "https://campus.boe.com/xzlb2022/"

    params = {
        "c1": "",
        "ywbk": "",
        "ky": "",
        "type": 2,          # 实习生招聘（修改这里）
        "PageIndex": 1
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/142.0.0.0 Safari/537.36",
        "Referer": "https://campus.boe.com/xzlb2022/?type=6",
    }

    cookies = {
        "Hm_lvt_4ea4fc530ed4220278c643746a5a71bf": "1765337257",
        "HMACCOUNT": "709A8FA55A8EF0D7",
        "_ga": "GA1.1.1612211053.1765337259",
    }

    def fetch_page(page_index):
        params["PageIndex"] = page_index
        resp = requests.get(
            base_url,
            params=params,
            headers=headers,
            cookies=cookies
        )
        resp.encoding = "utf-8"
        return resp.text

    job_list_all = []
    page_index = 1


    html = fetch_page(page_index)
    print(f"正在处理第 {page_index} 页…")
    print(html)
    # BOE 的分页越界提示


    soup = BeautifulSoup(html, "html.parser")
    items = []

    for li in soup.select("div.zwlb ul li"):
        a = li.select_one("a.godetail")

        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        if a:
            link = a.get("data-href", "")

            b = a.select_one("b")
            if b:
                announcement_name = b.get_text(strip=True)

            spans = a.select("div.zwtxt span")
            if len(spans) >= 1:
                hd_job_category = spans[0].get_text(strip=True)
            if len(spans) >= 3:
                hd_dept = spans[2].get_text(strip=True)
            if len(spans) >= 4:
                text = spans[3].get_text(strip=True)
                if "招聘人数" in text:
                    hd_job_num = text.replace("招聘人数：", "")

            p = a.select_one("p")
            if p:
                hd_loc = p.get_text(strip=True)

        job_list_all.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""
        })

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(job_list_all, f, ensure_ascii=False, indent=4)

    print(f"全部数据已保存到 {tempfile}")
