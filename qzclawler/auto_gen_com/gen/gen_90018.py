import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []

    # 提取所有列表行
    items = soup.select(".list-item-main")
    
    for item in items:
        announcement_name = ""
        publish_time = ""
        link = ""
        hd_dept = ""
        hd_loc = ""
        hd_job_num = ""
        hd_job_category = ""

        # 提取职位名称
        name_tag = item.select_one(".pos-name .list-cell-span")
        if name_tag:
            announcement_name = name_tag.get_text(strip=True)

        # 这个皮肤结构里没有明确标注部门，所以留空
        hd_dept = "" 

        # 提取工作地点
        loc_tag = item.select_one(".pos-locate .list-cell-span")
        if loc_tag:
            hd_loc = loc_tag.get_text(strip=True).replace("|", "").strip()

        # 提取招聘人数
        num_tag = item.select_one(".pos-num .list-cell-span")
        if num_tag:
            hd_job_num = num_tag.get_text(strip=True)
            
        # 提取发布时间 (更新日期)
        pub_tag = item.select_one(".pos-pubTime .list-cell-span")
        if pub_tag:
            publish_time = pub_tag.get_text(strip=True)
            
        # 提取职位类别
        cate_tag = item.select_one(".pos-cate .list-cell-span")
        if cate_tag:
            hd_job_category = cate_tag.get_text(strip=True)

        # 🎯 智能判断 URL 拼接中的 postType 参数
        item_text = item.get_text()
        if any(keyword in item_text for keyword in ["校园", "校招", "应届", "实习", "管培", "培训生", "202"]):
            post_type = "campus"
        # 兜底：如果 HTML 上下文暗示了 social 或不是 campus，就定为 society
        elif "social" in htmlcontext:
            post_type = "society"
        else:
            post_type = "campus"

        # 提取真实的详情页 URL
        job_id = item.get("id")
        if job_id:
            link = f"https://crrc-dt.hotjob.cn/SU64ca18016202cc125d482e62/pb/posDetail.html?postId={job_id}&postType={post_type}"

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