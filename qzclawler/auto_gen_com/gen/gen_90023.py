def extract_table_from_html(htmlcontext, tempfile):
    import json
    import re
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(htmlcontext, "html.parser")
    result = []

    items = soup.select("div.card-item-wrap")

    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        title_el = item.select_one(".top-label")
        if title_el:
            announcement_name = title_el.get_text(strip=True)
            hd_job_category = announcement_name

        summary_el = item.select_one(".pos-summary")
        if summary_el:
            spans = summary_el.find_all("span", recursive=False)
            values = []
            for span in spans:
                text = span.get_text(" ", strip=True)
                text = re.sub(r"\s*\|\s*", "", text).strip()
                if text:
                    values.append(text)

            if len(values) >= 1:
                hd_dept = values[0]
            if len(values) >= 3:
                hd_loc = values[2]
            elif len(values) >= 2:
                hd_loc = values[-1]

        need_people_el = item.select_one(".need-people")
        if need_people_el:
            text = need_people_el.get_text(strip=True)
            match = re.search(r"招聘人数[:：]\s*(\d+)", text)
            if match:
                hd_job_num = match.group(1)

        link_el = item.select_one("a[href]")
        if link_el:
            link = link_el.get("href", "").strip()

        row = {
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        }
        result.append(row)

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
