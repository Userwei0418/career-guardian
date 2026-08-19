def crawl_page(page):
    try:
        # 获取当前页码
        current_elem = page.query_selector('a.now')
        current_page = int(current_elem.inner_text()) if current_elem else -1

        # 获取所有页码，找到最大页
        page_links = page.query_selector_all('a')
        last_page = -1
        for elem in reversed(page_links):
            text = elem.inner_text().strip()
            if text.isdigit():
                last_page = int(text)
                break

        print(f"当前页: {current_page}, 最大页: {last_page}")

        # 判断是否最后一页
        if current_page >= last_page:
            print("已经是最后一页，停止翻页")
            return False

        # 点击下一页
        next_button = page.query_selector('a.next')
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)
            return True

    except Exception as e:
        print(f"翻页时出错: {e}")

    return False
