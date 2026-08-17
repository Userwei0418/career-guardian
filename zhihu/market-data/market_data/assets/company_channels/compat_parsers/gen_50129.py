import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    # 找所有 <a> 标签
    for idx, a_tag in enumerate(soup.find_all('a', href=True), start=1):
        # 检查内部是否包含职位 div
        div = a_tag.find('div', class_='positionItem__fca8c0 positionItem')
        if not div:
            continue  # 不是职位卡片，跳过

        # 提取 href
        link = a_tag['href'] or ""
        if not link:
            print(f"[{idx}] Warning: 'link' not found")

        # 提取标题
        title_span = div.find('span', class_='positionItem-title-text')
        title = title_span.get_text(strip=True) if title_span else ""
        if not title:
            print(f"[{idx}] Warning: 'announcement_name' not found")

        # 提取地点、岗位类型、岗位类别
        location = ""
        job_type = ""
        job_category = ""
        location_span = div.find('div', class_='subTitle__fca8c0 positionItem-subTitle')
        if location_span:
            spans = location_span.find_all('span')
            if spans:
                location = spans[0].get_text(strip=True) if spans[0] else ""
                if not location:
                    print(f"[{idx}] Warning: 'hd_loc' not found")
            job_type_span = location_span.find('span', class_='infoText__fca8c0')
            job_type = job_type_span.get_text(strip=True) if job_type_span else ""
            if not job_type:
                print(f"[{idx}] Warning: 'job_type' not found")
            job_category_span = location_span.find('span', class_='infoText-category__fca8c0')
            job_category = job_category_span.get_text(strip=True) if job_category_span else ""
            if not job_category:
                print(f"[{idx}] Warning: 'hd_job_category' not found")

        # 构建职位字典
        positions.append({
            "announcement_name": title,
            "publish_time": "",
            "link": link,
            "hd_dept": "",
            "hd_loc": location,
            "hd_job_num": "",
            "hd_job_category": job_category
        })

    # 写入 JSON 文件
    try:
        with open(tempfile, 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=4)
        print(f"成功提取 {len(positions)} 条职位数据到 {tempfile}")
    except Exception as e:
        print(f"Error writing JSON file: {e}")
