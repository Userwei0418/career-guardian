
import json
from bs4 import BeautifulSoup

def extract_table_from_html(html_content, tempfile):
    # 使用 BeautifulSoup 解析 HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # 查找表格
    table = soup.find('table', class_='fdhy_tb002')
    #循环打印table
    for table in soup.find_all('table', class_='fdhy_tb002'):
        #如果tr里面超过5个
        if len(table.find_all('tr')) > 5:
            # 初始化结果列表
            result = []

            # 遍历表格的每一行（跳过表头）
            for row in table.find_all('tr')[1:]:
                # 提取公告名称、发布时间和链接
                cells = row.find_all('td')
                if len(cells) >= 2:
                    #发现里面的所有href
                    hrefs = cells[0].find_all('a')
                    cell1 = hrefs[1]

                    announcement_name = cell1
                    publish_time = cells[1].text.strip('[]')
                    link = cell1

                    if announcement_name and publish_time and link:
                        result.append({
                            "announcement_name": announcement_name.get('title', announcement_name.text.strip()),
                            "publish_time": publish_time,
                            "link": link.get('href')
                        })

            # 将结果写入 JSON 文件
            with open(tempfile, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=4)
