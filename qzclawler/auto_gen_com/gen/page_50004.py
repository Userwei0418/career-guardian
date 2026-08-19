def crawl_page(page):
    try:
        next_btn = page.locator('li[title="下一页"]').first

        # 判断按钮是否存在
        if not next_btn:
            print("没有找到下一页按钮")
            return False

        classes = next_btn.get_attribute('class') or ''
        aria_disabled = next_btn.get_attribute('aria-disabled') or 'false'

        if 'ant-pagination-disabled' in classes or aria_disabled == 'true':
            print("下一页按钮已禁用，最后一页")
            return False

        next_btn.click()
        page.wait_for_timeout(1000)  # 等待页面加载
        return True

    except Exception as e:
        print(f"翻页异常: {e}")
        return False
