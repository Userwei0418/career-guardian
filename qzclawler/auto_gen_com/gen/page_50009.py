def crawl_page(page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，False 表示已经是最后一页或出错
    """
    try:
        # 获取所有数字页码和当前页
        page_links = page.query_selector_all('a[onclick^="getJobList"], a.now')
        max_page = -1
        current_page = -1

        for a in page_links:
            text = a.inner_text().strip()
            if text.isdigit():
                num = int(text)
                max_page = max(max_page, num)
                if "now" in (a.get_attribute('class') or ''):
                    current_page = num

        if current_page == -1 or max_page == -1:
            print("未能正确识别当前页或最大页")
            return False

        # 判断是否已经是最后一页
        if current_page >= max_page:
            print(f"当前页 {current_page} 已经是最后一页 {max_page}，停止翻页")
            return False

        # 查找文本为“下一页”且没有 disabled 的按钮
        next_buttons = page.query_selector_all('a.next')
        next_button = None
        for btn in next_buttons:
            text = btn.inner_text().strip()
            disabled = btn.get_attribute('disabled')
            # 确保点击的是“下一页”而不是“上一页”
            if text == "下一页" and not disabled:
                next_button = btn
                break

        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)
            print(f"成功点击下一页按钮，从 {current_page} 翻到 {current_page+1}")
            return True
        else:
            print("没有可用的下一页按钮，已经是最后一页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
