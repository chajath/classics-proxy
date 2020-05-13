from flask import Flask
from flask_caching import Cache
import requests
from lxml import html, etree
import re
from flask_swagger_ui import get_swaggerui_blueprint
from yaml import Loader, load
from werkzeug.routing import BaseConverter
from bs4 import BeautifulSoup

config = {
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 3600,
}
app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

# RegexConverter from https://stackoverflow.com/a/5872904


class RegexConverter(BaseConverter):
    def __init__(self, url_map, *items):
        super(RegexConverter, self).__init__(url_map)
        self.regex = items[0]


app.url_map.converters["regex"] = RegexConverter


@app.route("/")
def root():
    return {"_links": {"self": "/", "collection": "/corpora"}}


@app.route("/corpora")
def corpora():
    return {
        "_links": {
            "self": "/corpora",
            "itkc": "/corpora/itkc",
            "historygokr": "/corpora/historygokr",
        }
    }


TITLE_TO_KO_ZN = re.compile("(^.*)\\((.*)\\)$")
SINCHUL_HANJA_LOOKUP = {
    "KC01783": "楸",
}
SINCHUL_CODE_EXTRACT = re.compile(".*(KC[0-9]+).*")


@cache.memoize()
def get_all_itkc_collections(series_id):
    r = requests.get(
        f"http://db.itkc.or.kr/dir/treeAjax?grpId=&itemId={series_id}&gubun=book&depth=1"
    )
    tt = r.text
    tree = html.fromstring(tt)
    raw_title_spans = tree.xpath("//li/span")
    raw_titles = []
    for n in raw_title_spans:
        t = bt_div_to_text(n)
        raw_titles.append(t)
    authors = [
        t.split(" | ")[1] if " | " in t else None
        for t in tree.xpath("//li/span/@title")
    ]
    data_id = tree.xpath("//li/@data-dataid")
    ko_titles, zn_titles = zip(*[TITLE_TO_KO_ZN.match(t).groups() for t in raw_titles])
    return [
        {"authors": a, "title": kt, "zn_title": zt, "data_id": data_id}
        for (a, kt, zt, data_id) in zip(authors, ko_titles, zn_titles, data_id)
    ]


@app.route("/corpora/itkc")
def itkc_root():
    return {
        "series": [
            {"id": "BT", "name": "고전번역서",},
            {"id": "MO", "name": "한국문집총간",},
            {"id": "JT", "name": "조선왕조실록",},
        ],
        "_links": {"self": "/corpora/itkc", "series": "/corpora/itkc/{id}"},
    }


@app.route("/corpora/itkc/<string:series_id>")
def itkc_series(series_id):
    collections = get_all_itkc_collections(series_id)
    return {
        "collections": collections,
        "_links": {
            "self": f"/corpora/itkc/{series_id}",
            "meta": f"/corpora/itkc/{series_id}/meta/{{data_id}}",
            "all_text_meta": f"/corpora/itkc/{series_id}/all_text_meta/{{data_id}}",
        },
    }


def replace_all_kc(title):
    for (k, v) in SINCHUL_HANJA_LOOKUP.items():
        title = title.replace(k, v)
    return title


@cache.memoize()
def get_all_itkc_links(series_id, data_id):
    r = requests.get(
        f"http://db.itkc.or.kr/dir/treeAjax?grpId=&itemId={series_id}&dataId={data_id}"
    )
    tt = r.text
    tree = html.fromstring(tt)
    titles = tree.xpath("//li/span/@title")
    data_id = tree.xpath("//li/@data-dataid")
    data_url = tree.xpath("//li/@data-url")
    return [
        {
            "title": replace_all_kc(title),
            "data_id": data_id,
            "is_text": "%EC%B5%9C%EC%A2%85%EC%A0%95%EB%B3%B4" in data_url,  # "최종정보"
        }
        for (title, data_id, data_url) in zip(titles, data_id, data_url)
    ]


@app.route("/corpora/itkc/<string:series_id>/meta/<string:data_id>")
def itkc_volumes(series_id, data_id):
    volumes = get_all_itkc_links(series_id, data_id)
    return {"volumes": volumes}


@app.route("/corpora/itkc/<string:series_id>/all_text_meta/<string:data_id>")
@cache.memoize()
def itkc_all_text_meta(series_id, data_id):
    volumes = []
    pioneer_data_ids = [data_id]
    while len(pioneer_data_ids) > 0:
        d_id = pioneer_data_ids.pop(0)
        print(d_id)
        vs = itkc_volumes(series_id, d_id)["volumes"]
        for v in vs:
            if v["is_text"]:
                volumes.append(v)
            else:
                pioneer_data_ids.append(v["data_id"])

    return {"volumes": volumes}


def bt_div_to_text(div: html.HtmlElement):
    tb = div.xpath("node()")
    t = ""
    for x in tb:
        if isinstance(x, str):
            t = t + x.strip()
        elif isinstance(x, html.HtmlElement) and x.tag == "br":
            t = t + "\n"
        elif isinstance(x, html.HtmlElement) and x.tag in [
            "div",
            "span",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        ]:
            t = t + bt_div_to_text(x)
        elif (
            isinstance(x, html.HtmlElement)
            and x.tag == "img"
            and "class" in x.attrib
            and x.attrib["class"] == "newchar"
        ):
            code = SINCHUL_CODE_EXTRACT.match(x.attrib["src"]).groups()[0]
            if code in SINCHUL_HANJA_LOOKUP:
                t = t + SINCHUL_HANJA_LOOKUP.get(code)
            else:
                print(f"Unknown Sinchul Hanja code: {code}")

    return t


@cache.memoize()
def get_itkc_bt_text(data_id):
    r = requests.get(f"http://db.itkc.or.kr/dir/node?dataId={data_id}&viewSync=OT")
    tt = r.text
    tree = html.fromstring(tt)
    all_nodes = tree.xpath("//div[@class='text_body ']")[0]
    t = bt_div_to_text(all_nodes)
    if len(tree.xpath("//div[@class='text_body ori']")) > 0:
        all_zn_nodes = tree.xpath("//div[@class='text_body ori']")[0]
        zn_t = bt_div_to_text(all_zn_nodes)
    else:
        zn_t = None
    all_title_nodes = tree.xpath(
        "//div[contains(@class, 'text_body_tit') and not(contains(@class, 'ori'))]"
    )[0]
    title_t = bt_div_to_text(all_title_nodes)
    if len(tree.xpath("//div[@class='text_body_tit ori']")) > 0:
        all_zn_title_nodes = tree.xpath("//div[@class='text_body_tit ori']")[0]
        zn_title_t = bt_div_to_text(all_zn_title_nodes)
    else:
        zn_title_t = None
    return t, zn_t, title_t, zn_title_t


@app.route("/corpora/itkc/BT/text/<string:data_id>")
@app.route("/corpora/itkc/JT/text/<string:data_id>")
def itkc_bt_text(data_id):
    text, zn_text, title, zn_title = get_itkc_bt_text(data_id)
    return {"text": text, "zn_text": zn_text, "title": title, "zn_title": zn_title}


@cache.memoize()
def get_itkc_mo_text(data_id):
    r = requests.get(f"http://db.itkc.or.kr/dir/node?dataId={data_id}")
    tt = r.text
    tree = html.fromstring(tt)
    all_nodes = tree.xpath("//div[@class='text_body ori']")[0]
    all_zn_title_nodes = tree.xpath("//div[@class='text_body_tit mt10 ori']")[0]
    return bt_div_to_text(all_nodes), bt_div_to_text(all_zn_title_nodes).split("\n")[0]


@app.route("/corpora/itkc/MO/text/<string:data_id>")
def itkc_mo_text(data_id):
    zn_text, zn_title = get_itkc_mo_text(data_id)
    return {"zn_text": zn_text, "zn_title": zn_title}


@cache.memoize()
@app.route("/corpora/historygokr/sillok")
def historygokr_sillok():
    r = requests.get("http://sillok.history.go.kr/main/main.do")
    tt = r.text
    tree = html.fromstring(tt)
    volumes = [
        {
            "title": a.text,
            "data_id": a.attrib["href"]
            .replace("javascript:search('", "")
            .replace("');", ""),
            "is_text": False,
        }
        for a in tree.xpath(
            "//div[@id='m_cont_list']//ul[contains(@class,'m_cont')]//a"
        )
    ]
    return {"volumes": volumes}


SILLOK_ID_EXTRACT = re.compile("k[a-z]{2}_[_0-9]+")
ALL_WS = re.compile("\\s+")


@cache.memoize()
@app.route("/corpora/historygokr/sillok/meta/<regex('k[a-z]{2}'):kid>")
def historygokr_sillok_kings(kid):
    r = requests.get(
        f"http://sillok.history.go.kr/search/inspectionMonthList.do?id={kid}"
    )
    tt = r.text
    tree = html.fromstring(tt)
    years = tree.xpath("//ul[contains(@class, 'king_year')]/li")
    vs = []
    for y in years:
        header_div = y.xpath("div")[0]
        spans = header_div.xpath("span")
        if len(spans) > 0:
            first_span = header_div.xpath("span")[0]
            year_title = ALL_WS.sub(" ", header_div.text_content().strip()).replace(
                " 원본", ""
            )
            if "onclick" in first_span.attrib:
                id = SILLOK_ID_EXTRACT.findall(first_span.attrib["onclick"])[0]
                vs.append({"title": year_title, "data_id": id, "is_text": False})
                continue
            for month in y.xpath("ul/li/a"):
                id = SILLOK_ID_EXTRACT.findall(month.attrib["href"])[0]
                vs.append(
                    {
                        "title": f"{year_title} {month.text_content()}",
                        "data_id": id,
                        "is_text": False,
                    }
                )
        else:
            first_anchor = header_div.xpath("a")[0]
            id = SILLOK_ID_EXTRACT.findall(first_anchor.attrib["href"])[0]
            title = ALL_WS.sub(" ", header_div.text_content().strip()).replace(
                " 원본", ""
            )
            vs.append(
                {"title": title, "data_id": id, "is_text": False,}
            )
    return {"volumes": vs}


@cache.memoize()
@app.route("/corpora/historygokr/sillok/meta/<regex('k[a-z]{2}_[0-9]+'):mid>")
def historygokr_sillok_month(mid):
    r = requests.get(
        f"http://sillok.history.go.kr/search/inspectionDayList.do?id={mid}"
    )
    tt = r.text
    tree = html.fromstring(tt)
    vs = []
    for a in tree.xpath("//dl[contains(@class,'ins_list_main')]//li/a"):
        id = SILLOK_ID_EXTRACT.findall(a.attrib["href"])[0]
        title = a.text_content()
        vs.append(
            {"title": title, "data_id": id, "is_text": True,}
        )

    return {"volumes": vs}


def text_content_without_sup(node):
    text = ""
    for elem in node.iter():
        # Exclude superscript, which is a pointer to a footnote.
        if elem.tag != "sup":
            if elem.text:
                text += elem.text
        if elem.tail:
            text += elem.tail
    return ALL_WS.sub(" ", text).strip()


@cache.memoize()
@app.route("/corpora/historygokr/sillok/text/<string:tid>")
def historygokr_sillok_text(tid):
    r = requests.get(f"http://sillok.history.go.kr/id/{tid}")
    tt = r.text
    # Normalize HTML text with html5lib in order to fix unclosed div tags.
    tree = html.fromstring(str(BeautifulSoup(tt, "html5lib")))
    t_tree = tree.xpath("//div[contains(@class,'ins_left_in')]//p[@class='paragraph']")
    zn_t_tree = tree.xpath(
        "//div[contains(@class,'ins_right_in')]//p[@class='paragraph']"
    )
    text = "\n".join([text_content_without_sup(p) for p in t_tree])
    zn_text = "\n".join([text_content_without_sup(p) for p in zn_t_tree])
    title_tree = tree.xpath("//*[contains(@class,'search_tit')]")
    if len(title_tree) > 0:
        title = title_tree[0].text_content()
    else:
        title = None
    tag_tree = tree.xpath("//li[@class='view_font02']//div")
    if len(tag_tree) > 0:
        tags = tag_tree[0].text_content().split(" / ")
    else:
        tags = []
    return {"text": text, "zn_text": zn_text, "title": title, "tags": tags}


swagger_yml = load(open("./openapi/itkc_api.yaml", "r"), Loader=Loader)
swaggerui_blueprint = get_swaggerui_blueprint(
    "/api/docs", "/api/docs/swagger.json", config={"spec": swagger_yml}
)
app.register_blueprint(swaggerui_blueprint, url_prefix="/api/docs")

if __name__ == "__main__":
    app.run()
