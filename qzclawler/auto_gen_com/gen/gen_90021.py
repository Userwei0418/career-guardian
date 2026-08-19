import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []

    # 提取所有列表行 (Updated for the new card layout)
    items = soup.select(".list-card-item1")
    
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 提取职位名称
        name_tag = item.select_one(".pos-title-item .top-label")
        if name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 提取职位类别
        cate_tag = item.select_one(".pos-tag-item .pos-cate")
        if cate_tag:
            hd_job_category = cate_tag.get_text(strip=True)

        # 提取工作地点 (The title attribute cleanly holds the location, e.g., "北京市 " or "大同市 ")
        summary_tag = item.select_one(".pos-summary")
        if summary_tag and summary_tag.has_attr("title"):
            hd_loc = summary_tag["title"].strip()

        # HTML结构中没有明确的部门信息，保留为空
        hd_dept = "" 
        
        # 提取发布时间与招聘人数 (Stripping out the prefix text)
        pub_tag = item.select_one(".ft-info .pub-time")
        if pub_tag:
            publish_time = pub_tag.get_text(strip=True).replace("更新日期：", "").strip()
            
        num_tag = item.select_one(".ft-info .need-people")
        if num_tag:
            hd_job_num = num_tag.get_text(strip=True).replace("招聘人数：", "").strip()

        # 提取真实 ID 和构建链接
        job_id = item.get("id")
        if job_id:
            # 🎯 智能判断 URL 拼接中的 postType 参数
            item_text = item.get_text()
            if any(keyword in item_text for keyword in ["校园", "校招", "应届", "实习", "管培", "培训生", "202"]):
                post_type = "campus"
            # 兜底：如果 HTML 上下文暗示了 social 或不是 campus，就定为 society
            elif "social" in htmlcontext:
                post_type = "society"
            else:
                post_type = "campus"

            link = f"https://wecruit.hotjob.cn/SU617ba9b3bef57c4414193b5f/pb/posDetail.html?postId={job_id}&postType={post_type}"

        # 只要有公告名称，就添加至结果
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