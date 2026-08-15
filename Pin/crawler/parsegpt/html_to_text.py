# -*-coding:utf-8-*-
import re
from bs4 import BeautifulSoup, Comment
brs_pattern = re.compile("</h\d+>|</div>|<br>|<br/>|</head>|</tr>|</li>|</title>|</dt>|</dd>|</ul>|</p>|</table>|</article>|</aside>|</details>|</figcaption>|</figure>|</footer>|</header>|</hgroup>|</menu>|</nav>|</section>|</blockquote>|</address>|</fieldset>|</caption>")

class Html2txt():

    def _html_text(self, _html):
        soup = BeautifulSoup(_html, "lxml")
        _text = soup.get_text()
        return re.sub(r"(\r\n)|\n", " ", _text).strip()


    def _table_text(self, table):
        _tables = table.find_all("table")
        if _tables:
            return table.get_text()
        trs = table.find_all("tr")  # 单元格
        if trs:
            for tr in trs:
                tds = tr.find_all("td")  # 列
                new_tds = []
                if tds:
                    for td in tds:
                        _html = td.prettify()
                        _html = re.sub(r"(\r\n+)|\n+", "", _html)
                        brs = brs_pattern.findall(_html)
                        for br in set(brs):
                            _html = _html.replace(br, br + "\n")
                        _brs = re.split(r"\n+", _html)
                        if _brs[-1] == "</td>":
                            _brs.pop(-1)
                            _brs[-1] = _brs[-1] + "</td>"
                        _brs = [_br.strip() for _br in _brs if _br and _br.strip()]
                        if _brs[-1] == "</td>":
                            _brs.pop(-1)
                            _brs[-1] = _brs[-1] + "</td>"
                        new_tds.append(_brs)
                if new_tds:
                    _len = [len(t) for t in new_tds]
                    _max = max(_len)
                    data = []
                    _ldiff = [_l for _l in _len if _max != _l]
                    if _ldiff:
                        re_tds = []
                        for t in new_tds:
                            diff_len = _max - len(t)
                            if diff_len:
                                for _ in range(0, diff_len):
                                    t.append("<td></td>")
                            re_tds.append(t)
                        for i in [list(t) for t in zip(*re_tds)]:
                            data.append("".join(i))
                    elif _max > 1:
                        try:
                            for i in [list(t) for t in zip(*new_tds)]:
                                data.append("".join(i))
                        except:
                            print("****", re_tds)
                    else:
                        data = [" ".join([k[0].strip() for k in new_tds if k[0]])]
                    data = [self._html_text(d) for d in data]
                    _re_str = "\n".join(data)
                    tr.replace_with(_re_str)
        return table.get_text()


    def clear_tables(self, s):
        soup = BeautifulSoup(s, "lxml")
        comments = soup.findAll(text=lambda text: isinstance(text, Comment))  # 去掉注释
        [comment.extract() for comment in comments]
        tables = soup.findAll("table")
        _text = soup.get_text()
        if tables:
            for table in tables:
                if table.findAll("table"):
                    continue
                _text = self._table_text(table)
                if _text:
                    table.replace_with(_text)
            _text = soup.get_text()
            self.clear_tables(_text)
        return _text


    def clean_html(self, s):
        style_filter = re.compile("(?is)<style[^>]*?>(.*?)</style>")  # 去掉css
        s = re.sub("&lt;", "<", s)
        s = re.sub("&gt;", ">", s)
        s = re.sub("&amp;", "&", s)
        """去掉script"""
        s = re.sub("(?is)<script.*?</script>", "", s)
        """把隐藏的元素替换掉"""
        # s = re.sub("(?is)<[^<]*?hidden[^>]*?>[^<]*?</\w*?>", "", s)
        s = re.sub("(?is)<[^<]*?display\s*\:\s*none[^>]*?>[^<]*?</\w*?>", "", s)
        """把select 删除掉"""
        s = re.sub("(?is)<select>.*?</select>", "", s)
        s = style_filter.sub("", s)
        # s = re.sub(r"(\r\n+)|\n+", "", s)  # 去掉文本换行
        s = re.sub(r"</td>", "</td> ", s)
        s = re.sub("<th>", "<td>", s)  # 单元格都换成td
        s = re.sub(r"</th>", "</td> ", s)
        brs = brs_pattern.findall(s)
        for br in set(brs):
            s = s.replace(br, br + "\n")
        _text = self.clear_tables(s)
        _text = re.sub("(?is)<!\[if.*?\]>", "", _text)
        _text = re.sub("(?is)<!\[endif.*?\]>", "", _text)
        _text = re.sub(r"\n", "\r\n", _text)
        _text = re.sub(r"[ \f\v]{2,}", " ", _text)
        _text = re.sub(r"\t{2,}", "\t", _text)
        _text = re.sub(r"(\r\n){2,}", "\r\n", _text)
        _text = re.sub(r"\r\n\s+", "\r\n", _text)
        _text = re.sub(r"\xa0\xa0", "", _text)
        _text = re.sub(r"\r\n\xa0", "\r\n", _text)
        _text = re.sub(r"\xa0\xa0", "", _text)

        return _text.strip()

if __name__ == '__main__':
    filepath = r"/Users/ziguangchu/source/python/clawler_data/data/ardata/sch_00131/detail_e49385645df507c84d6fd149cc93cff1.html"
    with open(filepath, "r", encoding="utf-8", errors='ignore')as f1:
        s = f1.read()
    res = Html2txt().clean_html(s)
    print(res)
