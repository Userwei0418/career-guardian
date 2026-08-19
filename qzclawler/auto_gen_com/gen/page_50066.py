def crawl_page(page):
    try:
        # 1. 滚动到底部，确保分页加载
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)

        # 2. 定位下一页按钮（忽略动态类名）
        next_button = page.locator("li.StyledPageArrow-daLCNb").last

        # 3. 等待按钮出现
        next_button.wait_for(state="visible", timeout=5000)

        # 4. 检查是否为禁用状态
        if next_button.get_attribute("disabled") is not None:
            print("已到最后一页，停止翻页。")
            return False

        # 5. 记录翻页前的内容快照
        old_html = page.content()

        # 6. 点击下一页
        next_button.click(force=True)
        print("成功点击下一页。")

        # 7. 等待页面内容变化
        for _ in range(10):
            page.wait_for_timeout(600)
            if page.content() != old_html:
                print("页面内容已更新。")
                return True

        print("页面内容未变化，可能到最后一页。")
        return False

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
