# -*- coding: utf-8 -*-
import json
import re
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, tmp_file):
    """
    通用 Next.js SSR 渲染页面职位提取器
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    jobs = []
    visited_links = set()

    # Next.js 页面渲染完成后，职位列表通常包裹在带有特定 href 的 <a> 标签中
    # 根据你之前抓包的数据，龙湖的职位链接特征是 /jobs/职位名-ID
    a_tags = soup.find_all('a', href=re.compile(r'/jobs/.*?\d+'))

    for a in a_tags:
        href = a.get('href')
        if href in visited_links or not href.strip():
            continue

        # Next.js 的卡片内可能有多个 div，这里用 separator=" " 提取卡片内所有文本
        raw_text = a.get_text(separator=" ", strip=True)
        
        # 尝试将第一段长文本作为 Title（实际业务中可根据需要微调）
        # 这里为了确保不出错，直接把整个卡片的文本暂存为职位名，后续你们的 parsegpt 模型可以二次清洗
        title = raw_text.split(" ")[0] if raw_text else "未知职位"

        if title and len(title) >= 2:
            jobs.append({
                "announcement_name": title,
                "link": href,
                "hd_loc": "" # 地区信息置空，后续交给明细页抽取模型处理
            })
            visited_links.add(href)

    # 只要提取到数据，就按照框架要求写入 tmp_file
    if jobs:
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, ensure_ascii=False, indent=2)
        return True

    # 如果没提取到，也尝试看看有没有可能藏在 script 数据里
    if not jobs:
        print("未在 DOM 中找到 a 标签，尝试从 Next.js RSC payload 中正则提取...")
        titles = re.findall(r'"title":"([^"]+)"', html_content)
        ids = re.findall(r'"id":(\d+)', html_content)
        
        for i in range(min(len(titles), len(ids))):
            jobs.append({
                "announcement_name": titles[i],
                "link": f"/jobs/{titles[i]}-{ids[i]}",
                "hd_loc": ""
            })
            
        if jobs:
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(jobs, f, ensure_ascii=False, indent=2)
            return True

    return False