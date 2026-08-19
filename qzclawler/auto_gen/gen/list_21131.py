import time

#使用playwright，查找page页面上【按职位列显示】，进行点击
def crawl_page(page):
    # # 使用CSS选择器定位class为ui-zpxx-list的div元素
     # 点击下拉框展开选项
 # 第一步：点击下拉框
    page.click("div.ant-pagination-options-size-changer")
    time.sleep(2)
    # 第二步：点击具体的“30 条/页”选项
    page.click("text=30 条/页")
    
    time.sleep(3)