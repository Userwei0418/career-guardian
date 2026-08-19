import json
from bs4 import BeautifulSoup



def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody.postListTbody tr')

    data_list = []

    for row in rows:
        td_title = row.find('td', style="cursor: pointer; width: 400px;")
        if not td_title:
            continue

        announcement_name = td_title.get('title', '').strip()
        post_id = td_title.get('data-postid', '').strip()
        recruit_type = td_title.get('data-recruittype', '').strip()  # 从 HTML 读取
        import_post = td_title.get('importpost', '').strip()

        link = ""

        hd_job_num = row.find_all('td')[1].text.strip()
        hd_loc = row.find_all('td')[2].text.strip().replace("|", "")
        hd_dept = ""
        publish_time = ""
        hd_job_category = ""

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
