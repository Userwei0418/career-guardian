import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 每个职位外层卡片
    job_cards = soup.find_all('div', class_='_3aZF5aJ5txyNACMzMZf7Om')

    for card in job_cards:
        try:
            # 1️⃣ 职位名称
            title_div = card.find('div', class_='_2FC_nJGFTgU6s7ZTaFvuL8')
            announcement_name = title_div.get_text(strip=True) if title_div else "未知职位"

            # 2️⃣ 时间、类型、地点所在块
            info_block = card.find('div', class_='PdO1PRpa6_xkhBzEbEq3C')

            publish_time_div = info_block.find('div', class_='oAdZgV3YZC3NawYz0Ocyy') if info_block else None
            publish_time = publish_time_div.get_text(strip=True).replace('更新于 ', '') if publish_time_div else ""

            # 3️⃣ 职位类别（技术类、职能类等）
            category_div = info_block.find('div', class_='_3vj2eS7k7Mwpko5_6OSRu2') if info_block else None
            hd_job_category = category_div.get_text(strip=True) if category_div else ""

            # 4️⃣ 工作地点
            location_div = info_block.find('div', class_='_3vj2eS7k7Mwpko5_6OSRu2')
            # 因为类别和地点类名一样，用 find_all 区分
            all_info = info_block.find_all('div', class_='_3vj2eS7k7Mwpko5_6OSRu2')
            hd_loc = all_info[1].get_text(strip=True) if len(all_info) > 1 else ""

            # 5️⃣ 占位字段
            job_info = {
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": "",  # 可扩展：从卡片<a>中取href
                "hd_dept": "",  # 暂无
                "hd_loc": hd_loc,
                "hd_job_num": "1",
                "hd_job_category": hd_job_category
            }

            job_list.append(job_info)

        except Exception as e:
            print(f"解析职位时出错: {e}")
            continue

    # 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"✅ 成功提取 {len(job_list)} 条职位数据，保存至 {tempfile}")
