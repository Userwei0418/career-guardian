def crawl_page(page) -> bool:
    """
    翻页函数，返回 True 表示翻到下一页成功，
    False 表示已经是最后一页或出错
    """
    try:
        # 获取当前页码信息
        page_info = page.query_selector('div.tablefooter')
        current_page = total_pages = -1

        if page_info:
            page_text = page_info.inner_text()
            import re
            # 安全解析"当前第X/Y页"格式的文本
            match = re.search(r'当前第(\d+)\s*/\s*(\d+)页', page_text)
            if match:
                current_page = int(match.group(1))
                total_pages = int(match.group(2))
                print(f"当前页: {current_page}/{total_pages}")

                # 判断是否已经是最后一页
                if current_page >= total_pages:
                    print(f"已经是最后一页 ({current_page}/{total_pages})，停止翻页")
                    return False

        # 查找可用的"下一页"按钮，只选文本为“下一页”的
        next_buttons = page.query_selector_all('div.pager2 a.next')
        next_button = None
        for btn in next_buttons:
            text = btn.inner_text().strip()
            disabled = btn.get_attribute('disabled')
            if text == "下一页" and not disabled:
                next_button = btn
                break

        # 点击下一页
        if next_button:
            next_button.click()
            page.wait_for_timeout(1500)  # 等待页面加载完成
            print("成功点击下一页按钮")
            return True
        else:
            print("没有找到可用的下一页按钮，可能已经是最后一页")
            return False

    except Exception as e:
        print(f"翻页时出错: {e}")
        return False
