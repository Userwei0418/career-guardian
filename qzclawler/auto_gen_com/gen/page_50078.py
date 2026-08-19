def crawl_page(page):
    try:
        next_btn = page.query_selector('a.next')
        if next_btn:
            class_attr = next_btn.get_attribute('class')
            href_attr = next_btn.get_attribute('href')

            # 判断是否可点击
            if 'disabled' not in class_attr and href_attr:
                next_btn.click()
                page.wait_for_timeout(1000)  # 等待页面加载
                return True
    except Exception as e:
        print(f"翻页出错: {e}")
    return False
