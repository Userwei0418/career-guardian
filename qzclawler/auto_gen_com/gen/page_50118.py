def crawl_page(page):
    try:
        # 获取当前页和总页数信息
        page_info_div = page.query_selector('div[data-v-404bde20].page > div:nth-child(2)')
        if not page_info_div:
            print("无法找到页面信息")
            return False

        page_text = page_info_div.inner_text()
        # 提取"第1页/2页"中的页数信息
        import re
        match = re.search(r'第(\d+)页/(\d+)页', page_text)
        if not match:
            print("无法解析页面信息")
            return False

        current_page = int(match.group(1))
        total_pages = int(match.group(2))

        # 判断是否已经是最后一页
        if current_page >= total_pages:
            print("已经是最后一页，停止翻页")
            return False

        # 查找并点击下一页按钮
        next_button = page.query_selector('div.page-button:has-text("下页")')
        if next_button and not next_button.is_visible():  # 检查是否可用
            print("下页按钮不可用，停止翻页")
            return False

        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)
            return True

    except Exception as e:
        print(f"翻页时出错: {e}")

    return False

