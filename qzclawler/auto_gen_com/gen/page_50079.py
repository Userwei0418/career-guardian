def crawl_page(page):
    try:
        # 获取当前页
        current_span = page.query_selector('span.page.present')
        current_page = int(current_span.inner_text()) if current_span else 1

        # 尝试获取下一页按钮
        next_button = page.query_selector('a.pager-next')

        # 如果没有下一页或按钮被禁用，停止翻页
        if not next_button or 'disabled' in next_button.get_attribute('class'):
            print("已经是最后一页，停止翻页")
            return False

        # 点击下一页
        next_button.click()
        page.wait_for_timeout(1500)
        print(f"翻到第 {current_page + 1} 页")
        return True

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
