import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    job_list = []

    try:
        soup = BeautifulSoup(htmlcontext, 'html.parser')

        for card in soup.find_all('div', class_='list-card-item1'):
            try:
                # 安全地提取公告名称
                announcement_name_tag = card.find('span', class_='top-label')
                announcement_name = announcement_name_tag.get_text(strip=True) if announcement_name_tag else ''

                # 安全地提取部门信息
                hd_dept = ''
                hd_dept_tag = card.find('div', class_='pos-summary')
                if hd_dept_tag and hasattr(hd_dept_tag, 'contents') and len(hd_dept_tag.contents) > 0:
                    hd_dept = hd_dept_tag.contents[0].text.strip()

                # 安全地提取工作地点
                hd_loc_tag = card.find('span', class_='work-place')
                hd_loc = hd_loc_tag.get('title', '').strip() if hd_loc_tag else ''

                # 安全地提取招聘人数
                hd_job_num_tag = card.find('span', class_='need-people')
                hd_job_num = hd_job_num_tag.get_text(strip=True).replace('招聘人数：', '') if hd_job_num_tag else ''

                # 安全地提取职位类别
                hd_job_category_tag = card.find('span', class_='pos-cate')
                hd_job_category = hd_job_category_tag.get_text(strip=True) if hd_job_category_tag else ''

                # 安全地提取postId
                post_id = card.get('id', '').strip()

                # 构造链接
                link = ""

                job_list.append({
                    "announcement_name": announcement_name,
                    "publish_time": "",
                    "link": link,
                    "hd_dept": hd_dept,
                    "hd_loc": hd_loc,
                    "hd_job_num": hd_job_num,
                    "hd_job_category": hd_job_category
                })
            except Exception as e:
                # 如果处理单个卡片时出错，跳过该卡片并继续处理其他卡片
                continue

    except Exception as e:
        # 如果解析HTML时出现任何错误，确保至少输出一个空数组
        pass

    # 确保始终写入有效的JSON数组
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)