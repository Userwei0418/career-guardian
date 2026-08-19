def crawl_page(page):
    try:
        # 定位“下一页”按钮（li 元素）
        next_btn = page.query_selector('li[title="下一页"]')

        if next_btn:
            # 获取 class 属性
            class_attr = next_btn.get_attribute('class')
            aria_disabled = next_btn.get_attribute('aria-disabled')

            # 判断是否可点击
            if 'ant-pagination-disabled' not in class_attr and aria_disabled != 'true':
                # 点击 a 标签（按钮内部的实际链接）
                a_tag = next_btn.query_selector('a')
                if a_tag:
                    a_tag.click()
                    page.wait_for_timeout(1000)  # 等待页面加载
                    return True
    except Exception as e:
        print(f"翻页出错: {e}")
    return False
