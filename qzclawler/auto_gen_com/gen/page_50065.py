def crawl_page(page):
    try:
        # 1. 滚动到底部，确保分页区域加载
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)

        # 2. 等待“下一页”按钮出现且可点击
        next_button = page.locator("a:has-text('下一页')")
        next_button.wait_for(state="visible", timeout=5000)

        # 3. 检查是否禁用（例如 class="next disabled"）
        is_disabled = next_button.get_attribute("class")
        if is_disabled and "disabled" in is_disabled:
            print("已到最后一页，停止翻页。")
            return False

        # 4. 点击按钮（某些站点需强制点击）
        next_button.click()
        print("成功点击下一页。")

        # 5. 等待页面内容更新（例如表格或职位卡片）
        page.wait_for_timeout(2000)
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
