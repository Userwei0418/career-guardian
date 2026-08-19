import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    soup = BeautifulSoup(htmlcontext, 'html.parser')
    job_list = []

    # 遍历每个职位卡片
    for card in soup.find_all('div', class_='list-card-item1'):
        try:
            # 获取职位名称
            announcement_name = card.find('span', class_='top-label').text.strip() if card.find('span', class_='top-label') else ''

            # 获取发布时间
            publish_time = card.find('span', class_='pub-time').text.replace('发布时间：', '').strip() if card.find('span', class_='pub-time') else ''

            # 构造职位链接，基于卡片的id属性
            post_id = card.get('id', '')
            link = f"https://wecruit.hotjob.cn/SU6164fa892f9d244de1513582/pb/posDetail.html?postId={post_id}&postType=society" if post_id != '' else ''

            # 获取职位部门和工作地点
            hd_dept = card.find('div', class_='pos-summary').find_all('span')[0].text.strip() if card.find('div', class_='pos-summary') else ''
            hd_loc = card.find('span', class_='work-place').text.strip() if card.find('span', class_='work-place') else ''

            # 获取招聘人数
            hd_job_num = card.find('span', class_='need-people').text.replace('招聘人数：', '').strip() if card.find('span', class_='need-people') else ''

            # 获取职位类别
            hd_job_category = card.find('span', class_='pos-cate').text.strip() if card.find('span', class_='pos-cate') else ''

            # 将信息添加到职位列表
            job_list.append({
                "announcement_name": announcement_name,
                "publish_time": publish_time,
                "link": link,
                "hd_dept": hd_dept,
                "hd_loc": hd_loc,
                "hd_job_num": hd_job_num,
                "hd_job_category": hd_job_category
            })

        except Exception as e:
            print(f"Error processing a job card: {e}")
            continue

    # 将提取的数据写入文件
    with open(tempfile, 'w', encoding='utf-8') as f:
        json.dump(job_list, f, ensure_ascii=False, indent=4)
