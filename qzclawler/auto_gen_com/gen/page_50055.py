def crawl_page(page):
    try:
        # 定位包含 "下一页" 文字的按钮
        next_page_button = page.query_selector('a:text("下一页")')

        # 确保找到了下一页按钮
        if next_page_button:
            # 获取按钮的class和href属性
            class_attr = next_page_button.get_attribute('class')
            href_attr = next_page_button.get_attribute('href')
            print(f"下一页按钮的class属性: {class_attr}, href: {href_attr}")

            # 只检查下一页按钮，判断是否禁用
            # 如果 href 为 None 或者 class 包含 disabled，则认为是禁用
            if 'disabled' in class_attr or not href_attr:
                print("[翻页] 下一页按钮已禁用，可能是最后一页")
                return False

            # 如果按钮没有禁用，点击下一页按钮
            next_page_button.click()
            page.wait_for_timeout(2000)  # 等待页面加载新的内容
            print("[翻页] 成功点击下一页")
            return True
        else:
            print("[翻页] 未找到下一页按钮")

    except Exception as e:
        print(f"翻页时出现错误: {e}")

    return False
