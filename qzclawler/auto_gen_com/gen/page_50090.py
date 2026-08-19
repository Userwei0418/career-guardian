def crawl_page(page):
    try:
        # 精准定位“下一页”按钮，只选中 next
        next_btn = page.locator("div.icon-box[ng-click=\"onPagingClick('next')\"]")

        # 若未找到，说明 DOM 结构改变
        if next_btn.count() == 0:
            print("未找到 next 按钮，可能页面结构变化")
            return False

        # 获取状态
        class_value = next_btn.get_attribute("class") or ""

        # 不含 disable 则允许点击
        if "disable" not in class_value:
            next_btn.click()
            page.wait_for_timeout(600)
            return True

        print("下一页已禁用，到达末页")
        return False

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
