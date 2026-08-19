def crawl_page(page, action="next"):
    """
    翻页函数
    :param page: Playwright 页面对象
    :param action: 翻页动作，可选值：first, previous, next, last
    :return: True 表示成功翻页，False 表示无法翻页
    """
    try:
        # 根据 action 选择对应的按钮
        action_map = {
            "first": "div.icon-box[ng-click=\"onPagingClick('first')\"]",
            "previous": "div.icon-box[ng-click=\"onPagingClick('previous')\"]",
            "next": "div.icon-box[ng-click=\"onPagingClick('next')\"]",
            "last": "div.icon-box[ng-click=\"onPagingClick('last')\"]"
        }

        if action not in action_map:
            print(f"未知的翻页动作: {action}")
            return False

        button = page.locator(action_map[action])

        # 判断按钮是否存在
        if button.count() == 0:
            print(f"未找到 {action} 按钮")
            return False

        # 判断是否禁用
        class_name = button.get_attribute("class") or ""
        if "disable" in class_name:
            print(f"{action} 按钮被禁用")
            return False

        # 点击按钮
        button.click()
        page.wait_for_timeout(800)  # 等待页面刷新
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
