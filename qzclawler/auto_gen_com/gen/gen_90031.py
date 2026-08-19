import json
import re
from bs4 import BeautifulSoup


def clean_text(text):
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"\s+", "", text)
    text = text.strip("|｜/、，,;；")
    return text


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")

    results = []

    items = soup.select("div.list-card-item1")

    print(f"[gen_90031] 提取职位卡片数量: {len(items)}")

    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        title_tag = item.select_one("div.pos-title-item > span.top-label")
        if title_tag:
            announcement_name = clean_text(title_tag.get_text())

        pub_time_tag = item.select_one("div.pos-ft > div.ft-info > span.pub-time")
        if pub_time_tag:
            publish_time = clean_text(
                pub_time_tag.get_text().replace("更新日期：", "")
            )

        loc_tag = item.select_one("div.pos-hd > div.pos-summary > span.work-place")
        if loc_tag:
            hd_loc = clean_text(
                loc_tag.get_text().replace("工作地点：", "").replace("地点：", "")
            )

        job_num_tag = item.select_one("div.pos-ft > div.ft-info > span.need-people")
        if job_num_tag:
            hd_job_num = clean_text(
                job_num_tag.get_text().replace("招聘人数：", "")
            )

        job_cat_tag = item.select_one("div.pos-tag-item > span.pos-cate")
        if job_cat_tag:
            hd_job_category = clean_text(job_cat_tag.get_text())

        a_tag = item.select_one("a[href]")
        if a_tag and a_tag.get("href"):
            link = a_tag.get("href").strip()

        data_href = item.get("data-href") or item.get("data-url")
        if not link and data_href:
            link = data_href.strip()

        row = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }

        print(f"[gen_90031] row: {row}")

        results.append(row)

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return True
