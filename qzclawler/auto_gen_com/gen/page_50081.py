def crawl_page(page):
    try:
        # 直接定位你的自定义“下一页”按钮
        next_btn = page.locator('div.t-pagination__btn-next').first

        # 确保按钮能被选择
        if next_btn.count() == 0:
            print("没有找到下一页按钮")
            return False

        # disabled 属性是字符串，不是布尔
        disabled_attr = next_btn.get_attribute("disabled") or "false"

        # 判断是否被禁用
        if disabled_attr.lower() == "true":
            print("下一页按钮已禁用，已到最后一页")
            return False

        # 如果可点击，执行点击
        next_btn.click()
        page.wait_for_timeout(1000)
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
