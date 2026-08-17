import json
from bs4 import BeautifulSoup

def extract_table_from_html(htmlcontext, tempfile):
    try:
        soup = BeautifulSoup(htmlcontext, 'html.parser')
        job_list = []

        # 查找所有职位条目
        items = soup.find_all(class_='list-item-main')

        for item in items:
            try:
                # 安全提取职位名称
                announcement_name_elem = item.find(class_='pos-name')
                announcement_name = announcement_name_elem.get_text(strip=True) if announcement_name_elem else ""

                # 安全提取发布时间
                publish_time_elem = item.find(class_='pos-pubTime')
                publish_time = publish_time_elem.get_text(strip=True) if publish_time_elem else ""

                # 安全提取链接（使用ID作为示例）
                base_url = "https://wecruit.hotjob.cn/SU60769cec0dcad4510451cb0e/pb/posDetail.html"
                post_id = item.get('id', '') if item.get('id') else ""
                link = f"{base_url}?postId={post_id}&postType=society" if post_id else ""
                # 安全提取地点
                hd_loc_elem = item.find(class_='pos-locate')
                hd_loc = hd_loc_elem.get_text(strip=True) if hd_loc_elem else ""

                # 安全提取职位类别
                hd_job_category_elem = item.find(class_='pos-cate')
                hd_job_category = hd_job_category_elem.get_text(strip=True) if hd_job_category_elem else ""

                # 添加默认空值
                hd_dept = ""
                hd_job_num = ""

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
                # 记录单个条目处理错误但继续处理其他条目
                print(f"处理单个职位条目时出错: {str(e)}")
                continue

        # 写入JSON文件
        with open(tempfile, 'w', encoding='utf-8') as f:
            json.dump(job_list, f, ensure_ascii=False, indent=4)

        return True
    except Exception as e:
        # 记录整体处理错误
        print(f"处理HTML时出错: {str(e)}")
        # 写入空数组以避免后续处理出错
        with open(tempfile, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=4)
        return False