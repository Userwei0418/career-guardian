import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 每个岗位块 li.relative
    for item in soup.find_all('li', class_='relative mb-8 flex space-x-2 rounded-lg bg-black-lightest px-4 py-8 lg:space-x-4 lg:p-8'):
        # 岗位名称
        name_tag = item.find('h3', class_='font-medium lg:text-2xl')
        announcement_name = name_tag.get_text(strip=True) if name_tag else ""

        # 工作地点
        loc_tag = item.find('span', class_='leading-loose text-[#4C576C]')
        hd_loc = loc_tag.get_text(strip=True) if loc_tag else ""

        # 初始化三类字段
        job_duty, job_require, job_plus = [], [], []

        # 找出三个板块（工作职责 / 岗位要求 / 加分项）
        # 使用 select 而非 class_ 精确匹配
        detail_blocks = item.select('li.mt-3.text-xs.text-[#4C576C]')

        for block in detail_blocks:
            title_tag = block.find('div', class_='mr-1 inline-block leading-loose text-[#8592A6]')
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # 提取每个小项的文本（去掉“•”）
            content_items = []
            for li in block.select('li.flex.space-x-2.leading-loose.text-[#4C576C]'):
                spans = li.find_all('span')
                if len(spans) > 1:
                    content_items.append(spans[1].get_text(strip=True))

            # 分类存储
            if "工作职责" in title:
                job_duty = content_items
            elif "岗位要求" in title:
                job_require = content_items
            elif "加分项" in title:
                job_plus = content_items

        job_list.append({
            "announcement_name": announcement_name,
            "hd_loc": hd_loc,
            "job_duty": job_duty,
            "job_require": job_require,
            "job_plus": job_plus
        })

    # 保存 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"✅ 数据提取完成，共 {len(job_list)} 个岗位。")





