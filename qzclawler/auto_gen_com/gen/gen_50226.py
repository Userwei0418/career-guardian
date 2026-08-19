import json
from bs4 import BeautifulSoup


def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    positions = []

    for position in soup.find_all('a', class_='positionLists'):
        announcement_name = position.find('div', class_='positionName').get('title') if position.find('div',
                                                                                                      class_='positionName') else ''

        # 获取发布的时间，并处理没有找到的情况
        publish_time_span = position.find_all('span')

        publish_time = publish_time_span[3].text.replace("发布时间：","") if len(publish_time_span) > 3 else ''
        link = position.get('href', '')  # 使用默认值空字符串
        # 获取部门、职位类别、地点、人数等字段，并做空值检查
        hd_dept =publish_time_span[0].text if len(publish_time_span) > 1 else ''
        hd_job_category = publish_time_span[1].text if len(publish_time_span) > 1 else ''
        hd_loc =publish_time_span[2].text if len(publish_time_span) > 2 else ''
        hd_job_num = publish_time_span[4].text.split('：')[1] if len(publish_time_span) > 4 and '：' in publish_time_span[
            4].text else ''

        # 将职位信息添加到 positions 列表
        positions.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link,
            "hd_dept": hd_dept,
            "hd_loc": hd_loc,
            "hd_job_num": hd_job_num,
            "hd_job_category": hd_job_category
        })

    # 将提取的职位数据写入到指定的 JSON 文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(positions, f, ensure_ascii=False, indent=4)

