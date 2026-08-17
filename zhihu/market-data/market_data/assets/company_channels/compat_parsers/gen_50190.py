import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    for idx, job in enumerate(soup.find_all('div', class_='link-2tgd22te-3')):
        job_info = {}

        try:
            # ① 获取职位链接及名称
            link_tag = job.find('a')
            if link_tag:
                title_tag = link_tag.find('div', class_='title-20V7ljm-Id')
                job_info['announcement_name'] = title_tag.text.strip().replace('急', '') if title_tag else ""
                job_info['link'] = link_tag.get('href', "")
            else:
                job_info['announcement_name'] = ""
                job_info['link'] = ""

            # ② 发布时间
            publish_time_tag = job.find('span', class_='opened-at-20H_gh2Tqd')
            job_info['publish_time'] = (
                publish_time_tag.text.replace('发布时间：', '').strip()
                if publish_time_tag else ""
            )

            # ③ 工作地点
            location_tag = job.find('div', class_='locations-32aEgVWFz_')
            job_info['hd_loc'] = location_tag.text.strip() if location_tag else ""

            # ④ 招聘单位/职位类别（需要判断父节点是否存在）
            status_parent = job.find('div', class_='status-2vTS8JvF_D')
            if status_parent:
                status_tags = status_parent.find_all('span', class_='status-item-1_w5ygMyMO')
            else:
                status_tags = []

            job_info['hd_dept'] = status_tags[0].text.strip() if len(status_tags) > 0 else ""
            job_info['hd_job_category'] = status_tags[1].text.strip() if len(status_tags) > 1 else ""
            job_info['hd_job_num'] = "1"  # HTML 中未提供招聘人数

            job_list.append(job_info)

        except Exception as e:
            print(f"⚠️ 第 {idx+1} 条数据解析失败：{e}")
            print(f"HTML片段：{job}")
            continue  # 跳过当前条目

    # ⑤ 写入 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)

    print(f"✅ 成功解析 {len(job_list)} 条职位信息，结果已保存到 {tempfile}")
