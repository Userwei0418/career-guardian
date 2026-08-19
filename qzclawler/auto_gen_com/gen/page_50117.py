def crawl_page(page):
    try:
        # 定位下一页按钮
        next_page_button = page.locator("a.layui-laypage-next")
        print("111 ", next_page_button)

        # 检查按钮是否被禁用 (通过layui-disabled类)
        # 注意：get_attribute("class")会返回所有class，所以检查是否包含layui-disabled
        button_classes = next_page_button.get_attribute("class") or ""
        is_disabled = "layui-disabled" in button_classes
        if is_disabled:
            print("已到达最后一页，停止翻页")
            return False  # 或者其他标识符表明结束

        # 等待元素可点击后再点击（避免元素未加载完成）
        next_page_button.wait_for(state="visible")
        next_page_button.click()

        return True
    except Exception as e:
        print(f"翻页时出错: {e}")

    return False

