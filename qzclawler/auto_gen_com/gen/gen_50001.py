import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    rows = soup.select('tbody.postListTbody tr')
    job_list = []

    for row in rows:
        # 提取岗位信息的<td>标签
        td_post = row.find('td', style="cursor: pointer; width: 230px;")
        announcement_name = td_post.get('title')
        postid = td_post.get('data-postid')
        recruittype = td_post.get('data-recruittype')

        # 其它字段
        hd_job_category = row.find_all('td')[1].get('title', '').strip()
        hd_loc = row.find_all('td')[2].get('title', '').strip()
        publish_time = row.find_all('td')[3].text.strip()

        # 拼接详情页URL
        link = ""

        hd_dept = ""      # HTML里没有部门字段，先用占位符
        hd_job_num = ""   # HTML里没有招聘人数字段，先用占位符

        job_list.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
