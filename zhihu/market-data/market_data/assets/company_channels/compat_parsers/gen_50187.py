import json
from bs4 import BeautifulSoup


def extract_table_from_html(html_context, tempfile):
    # 解析 HTML 内容
    soup = BeautifulSoup(html_context, 'html.parser')

    # 提取所有职位条目
    rows = soup.find_all('tr', class_='ant-table-row')

    job_list = []

    # 遍历每一行提取职位信息
    for row in rows:
        announcement_name = row.find('div', class_='p-name')
        if announcement_name:
            announcement_name = announcement_name.get_text(strip=True)
        else:
            announcement_name = ""

        hd_dept = row.find_all('td')[1].get_text(strip=True) if len(row.find_all('td')) > 1 else ""
        hd_loc = row.find_all('td')[2].get_text(strip=True) if len(row.find_all('td')) > 2 else ""
        link = row.find('a', class_='f-cp')['href'] if row.find('a', class_='f-cp') else ""
        hd_job_category = row.find_all('td')[1].get_text(strip=True) if len(row.find_all('td')) > 1 else ""

        # 创建职位字典
        job_info = {
            "announcement_name": announcement_name,
            "publish_time": "",  # Assuming no data on publish_time in the HTML provided
            "link": link,
            "hd_dept": "",
            "hd_loc": hd_loc,
            "hd_job_num": "",  # Assuming no data on job number in the HTML provided
            "hd_job_category": hd_job_category
        }

        job_list.append(job_info)

    # 将提取的数据保存为 JSON 格式
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
