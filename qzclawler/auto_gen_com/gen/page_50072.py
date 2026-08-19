def crawl_page(page):
    try:
        # 定位“下页”按钮
        next_page_button = page.query_selector('a#result_next')

        # 如果按钮不存在，说明已经没有下一页
        if not next_page_button:
            print("未找到‘下页’按钮，停止翻页。")
            return False

        # 获取按钮的 class 属性判断是否可点击
        class_name = next_page_button.get_attribute('class') or ''
        if 'disabled' in class_name or 'paginate_button_disabled' in class_name:
            print("‘下页’按钮被禁用，已到最后一页。")
            return False

        # 如果可以点击则执行翻页
        next_page_button.click()
        print("成功点击‘下页’按钮，正在加载下一页...")
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
