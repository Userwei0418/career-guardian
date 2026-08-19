import time

#使用playwright，查找page页面上【按职位列显示】，进行点击
def crawl_page(page):
    # 先定位到 div 元素
    div_element = page.query_selector('div.pageCount') 
    # 在 div 元素内找到 select 元素并选择值为 80 的选项
    if div_element:
        page.select_option("div.pageCount select", value="80") 
    time.sleep(3)