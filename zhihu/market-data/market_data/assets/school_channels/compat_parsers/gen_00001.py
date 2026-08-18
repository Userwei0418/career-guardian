import json
from bs4 import BeautifulSoup

#
def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    result_list = []

    # 查找所有符合条件的infoList类ul标签
    info_lists = soup.find_all('ul', class_='infoList')
    for ul in info_lists:
        announcement_name = None
        publish_time = None
        link = None

        # 提取公告名称和链接
        name_tag = ul.find('li', class_='span7')
        if name_tag and name_tag.a:
            announcement_name = name_tag.a.text.strip()
            link = name_tag.a['href'].strip()

        # 提取发布时间
        time_tag = ul.find('li', class_='span4')
        if time_tag:
            publish_time = time_tag.text.strip()

        # 添加到结果列表
        if announcement_name and publish_time and link:
            result_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link
            })

    # 将结果写入JSON文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(result_list, f, ensure_ascii=False, indent=4)

# Note: The temp_file parameter should be a valid file path where the JSON file will be saved.