import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []
    
    # 粗略判断当前是校园招聘还是社会招聘，用于拼接真实 URL 的 postType 参数
    post_type = "campus" if "campus" in htmlcontext or "school" in htmlcontext or "校园" in htmlcontext else "society"

    items = soup.select(".list-card-item1")
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 公告名称
        name_tag = item.select_one(".top-label")
        if name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 所属部门或机构
        dept_tag = item.select_one(".pos-cate")
        if dept_tag:
            hd_dept = dept_tag.get_text(strip=True)

        # 工作地点（核心修复：彻底清洗掉竖线 '|'）
        loc_tag = item.select_one(".work-place")
        if loc_tag:
            hd_loc = loc_tag.get_text(strip=True).replace("|", "").strip()

        # 发布时间
        pub_time_tag = item.select_one(".pub-time")
        if pub_time_tag:
            publish_time = pub_time_tag.get_text(strip=True).replace("更新日期：", "").strip()

        # 招聘人数
        job_num_tag = item.select_one(".need-people")
        if job_num_tag:
            hd_job_num = job_num_tag.get_text(strip=True).replace("招聘人数：", "").strip()

        # 核心修复：提取父容器的 id 并拼接出真实的详情页 URL
        job_id = item.get("id")
        if job_id:
            link = f"https://wecruit.hotjob.cn/SU611394092f9d24229ef55ca2/pb/posDetail.html?postId={job_id}&postType={post_type}"

        # 只要抓到了有效的标题，就存入列表
        if announcement_name:
            results.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

    # 将结果直接以 JSON 格式写入 tempfile
    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)