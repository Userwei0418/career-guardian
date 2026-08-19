import json
from bs4 import BeautifulSoup
import re 
import datetime

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    announcements = []

    for a in soup.select('a[class="animated fadeInUp"]'):
        announcement_name = a['title']
        publish_time = a.find('div', class_='ol_left').find('p').text.strip() + ' ' + a.find('div', class_='ol_left').find('span').text.strip()
        link = a['href']
        
        # 定义正则表达式模式，用于匹配类似【月-日 年】格式的内容
        pattern = r"【(\d{2}-\d{2} \d{4})】"
        # 使用re.findall方法查找所有匹配的字符串
        matches = re.findall(pattern, publish_time)
        for match in matches:
            try:
                # 将匹配到的字符串转换为日期格式
                date_obj = datetime.strptime(match, "%m-%d %Y")
                # 将日期对象格式化为指定的日期文本格式（这里是'YYYY-MM-DD'）
                publish_time = date_obj.strftime("%Y-%m-%d") 
                break
            except ValueError as e:
                print(f"日期格式错误: {e}")

        announcements.append({
            "announcement_name": announcement_name,
            "publish_time": publish_time,
            "link": link
        })

    with open(tempfile, 'w', encoding='utf-8') as json_file:
     json.dump(announcements, json_file, ensure_ascii=False, indent=4)