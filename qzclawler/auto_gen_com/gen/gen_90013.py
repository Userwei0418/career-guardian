import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, "html.parser")
    results = []

    # 针对旭辉集团的表格布局皮肤，提取对应的行元素
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

        # 提取所属部门
        dept_tag = item.select_one(".pos-department .list-cell-span")
        if dept_tag:
            hd_dept = dept_tag.get_text(strip=True)

        # 提取工作地点
        loc_tag = item.select_one(".pos-locate .list-cell-span")
        if loc_tag:
            hd_loc = loc_tag.get_text(strip=True).replace("|", "").strip()

        # 提取招聘人数
        num_tag = item.select_one(".pos-num .list-cell-span")
        if num_tag:
            hd_job_num = num_tag.get_text(strip=True)
            
        # 注意：这套表格皮肤中没有直接显示“发布时间”，我们可以留空，让系统走默认处理

        # 提取真实的详情页 URL
        job_id = item.get("id")
        if job_id:
            # 针对旭辉集团，配置中只有校招，统一 postType=campus
            link = f"https://cifixz.hotjob.cn/SU60865899bef57c312faeea42/pb/posDetail.html?postId={job_id}&postType=campus"

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