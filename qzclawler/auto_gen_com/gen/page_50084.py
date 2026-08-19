def crawl_page(page):
    try:
        # 获取下一页按钮
        next_button = page.query_selector('span.page-b-next.sweezy-custom-cursor-hover')
        if not next_button:
            print("找不到下一页按钮")
            return False

        # 判断是否是最后一页（按钮隐藏时表示最后一页）
        button_class = next_button.get_attribute('class')
        if 'ng-hide' in button_class:
            print("已经是最后一页，停止翻页")
            return False

        # 点击下一页
        next_button.click()
        # 等待列表数据刷新完成（可根据具体页面元素修改选择器）
        page.wait_for_selector('div.style__STListItem-editor__sc-10r1nhd-0', timeout=5000)
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
