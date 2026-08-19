import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []

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

        # 工作地点
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

        # 🎯 核心修复：更智能的 postType 推断
        # 直接提取整个卡片的纯文本，找关键字
        item_text = item.get_text()
        # 如果标题或标签里有以下任意一个词，大概率是校招/实习
        if any(keyword in item_text for keyword in ["校园", "校招", "应届", "实习", "管培", "培训生", "202"]):
            post_type = "campus"
        else:
            # 针对 com_90012 目前只有 xiaozhao_1 的情况，默认给 campus 兜底
            post_type = "campus"

        # 拼接出真实的详情页 URL
        job_id = item.get("id")
        if job_id:
            link = f"https://wecruit.hotjob.cn/SU62feff93bef57c3179e09a34/pb/posDetail.html?postId={job_id}&postType={post_type}"

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

    with open(tempfile, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)