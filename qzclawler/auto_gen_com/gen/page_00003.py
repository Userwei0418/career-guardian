



#进行翻页
def crawl_page(page):
    try:
        # 定位下一页按钮并点击
        next_page_button = page.get_by_title("下一页")
        #如何判断按钮是否可以点击 
        if next_page_button and next_page_button.is_enabled(): 
            # 检查 aria-disabled 属性
            aria_disabled = next_page_button.get_attribute('aria-disabled')
            if aria_disabled != 'true':
                next_page_button.click() 
                return True
    except Exception as e:
        print(f"翻页时出现错误: {e}")
    return False