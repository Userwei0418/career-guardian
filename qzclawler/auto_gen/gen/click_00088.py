import time

#使用playwright，查找page页面上【按职位列显示】，进行点击
def crawl_page(page):
    # 定位并点击“招聘信息”菜单项
    # get_by_text 匹配文本内容，exact=True 精确匹配
    page.get_by_text("招聘信息", exact=True).nth(0).click()
    # 等待2秒，确认点击效果（可选）
    page.wait_for_timeout(2000)
    time.sleep(1)