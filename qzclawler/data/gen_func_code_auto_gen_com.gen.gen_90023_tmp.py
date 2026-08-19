
import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []
    cards = soup.select("div.list-card-item1")
    for card in cards:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称(announcement_name) - from span.top-label
        title_span = card.select_one("div.pos-title-item > span.top-label")
        if title_span:
            announcement_name = title_span.get_text(strip=True)

        # 所属部门或机构(hd_dept) - from pos-summary spans, first two spans before work-place
        pos_summary = card.select_one("div.pos-summary")
        if pos_summary:
            spans = pos_summary.find_all("span", recursive=False)
            # The first two spans are departments
            depts = []
            for sp in spans:
                # skip span with class work-place
                if "work-place" in sp.get("class", []):
                    continue
                text = sp.get_text(strip=True)
                if text and text != "|":
                    depts.append(text)
            if len(depts) >= 1:
                hd_dept = " | ".join(depts)

            # 工作地点(hd_loc) - from span.work-place
            work_place_span = pos_summary.select_one("span.work-place")
            if work_place_span:
                hd_loc = work_place_span.get_text(strip=True)

        # 招聘人数(hd_job_num) - from div.pos-ft > div.ft-info > span.need-people text like "招聘人数：1"
        need_people_span = card.select_one("div.pos-ft > div.ft-info > span.need-people")
        if need_people_span:
            text = need_people_span.get_text(strip=True)
            if "招聘人数" in text:
                hd_job_num = text.replace("招聘人数：", "").strip()

        # 职位类别(hd_job_category) - no explicit field, assign empty string
        hd_job_category = ""

        # 链接(link) - no link in given html, assign empty string
        link = ""

        # 发布时间(publish_time) - no info in given html, assign empty string
        publish_time = ""

        results.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
`