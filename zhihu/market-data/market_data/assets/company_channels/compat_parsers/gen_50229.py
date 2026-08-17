import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for item in soup.find_all("div", class_="style__STListItem-editor__sc-10r1nhd-0"):
        title = item.find("div", class_="style__STJobTitle-editor__sc-10r1nhd-4").get_text(strip=True)
        link = ""
        # Assuming the link is in the button, you may need to adjust this based on actual HTML structure
        # For example, if there's an <a> tag inside the button, you would extract the href from that <a> tag.
        # link = item.find("a")['href'] if item.find("a") else None

        # Placeholder values for the other fields as they are not present in the provided HTML
        publish_time = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        job_list.append({
            "announcement_name": title,
            "publish_time": publish_time,
            "link": link,

            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
