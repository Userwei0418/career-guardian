def crawl_page(page):
    try:
        # 定位下一页链接
        next_button = page.locator('li.page-item.next a[aria-label="Next page"]').first

        # 获取下一页 URL
        next_href = next_button.get_attribute("href")

        # 判断是否存在
        if not next_href:
            print("没有下一页链接，已到最后一页。")
            return False

        # 打印跳转信息
        print(f"准备跳转到下一页: {next_href}")

        # 直接跳转（更安全，不依赖 click）
        page.goto(next_href)
        page.wait_for_load_state("networkidle")

        # 等待新的岗位数据加载完成
        page.wait_for_selector('li[data-qa="searchResultItem"]', timeout=10000)
        return True

    except Exception as e:
        print(f"翻页时出现错误: {e}")
        return False
