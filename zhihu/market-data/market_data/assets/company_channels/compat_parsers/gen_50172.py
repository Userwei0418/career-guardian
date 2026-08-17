import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody.postListTbody tr')
    data_list = []

    for row in rows:
        try:
            td_title = row.find('td', style="cursor: pointer; width: 260px;")
            announcement_name = td_title.get('title', '')
            post_id = td_title.get('data-postid', '')

            # 可选字段
            brand_code = td_title.get('data-brandcode', '1')
            recruit_type = td_title.get('data-recruittype', '2')
            import_post = td_title.get('data-importpost', '1')
            column_id = td_title.get('data-columnid', '2')

            # 如果你确定是 wanda
            link = (
                f"https://wanda.hotjob.cn/wt/wanda/web/index/webPositionN310!getOnePosition"
                f"?postId={post_id}&recruitType={recruit_type}&brandCode={brand_code}&importPost={import_post}&columnId={column_id}"
            ) if post_id else ''

            tds = row.find_all('td')
            hd_dept = tds[1].get_text(strip=True) if len(tds) > 1 else ''
            hd_job_num = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            hd_loc = tds[3].get_text(strip=True) if len(tds) > 3 else ''
            publish_time = tds[4].get_text(strip=True) if len(tds) > 4 else ''

            data_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": ""
            })
        except Exception as e:
            print(f"解析某一行出错: {e}")
            continue

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=4)
