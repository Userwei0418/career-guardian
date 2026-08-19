import json
from bs4 import BeautifulSoup



def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody.postListTbody tr')

    data_list = []

    for row in rows:
        td_title = row.find('td', style="cursor: pointer; width: 220px;")
        if not td_title:
            continue

        announcement_name = td_title.get('title', '').strip()
        post_id = td_title.get('data-postid', '').strip()
        recruit_type = td_title.get('data-recruittype', '').strip()
        import_post = td_title.get('importpost', '').strip()

        # 构造完整链接
        link =""

        hd_job_num = row.find_all('td')[1].text.strip() if len(row.find_all('td')) > 1 else ''
        hd_loc = row.find_all('td')[2].text.strip().replace('|', '') if len(row.find_all('td')) > 2 else ''
        publish_time = row.find_all('td')[3].text.strip() if len(row.find_all('td')) > 3 else ''

        data_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": "",  # HTML里没有提供部门信息
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": ""  # HTML里没有提供职位类别
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
