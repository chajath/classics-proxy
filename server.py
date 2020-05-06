from flask import Flask
from flask_caching import Cache
import requests
from lxml import html, etree
import re
from flask_swagger_ui import get_swaggerui_blueprint
from yaml import Loader, load

config = {
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 3600,
}
app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)


@app.route("/")
def root():
    return {"_links": {"self": "/", "collection": "/corpora"}}


@app.route("/corpora")
def corpora():
    return {"_links": {"self": "/corpora", "itkc": "/corpora/itkc",}}


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
    authors = [t.split(" | ")[1] for t in tree.xpath("//li/span/@title")]
    data_id = tree.xpath("//li/@data-dataid")
    ko_titles, zn_titles = zip(*[TITLE_TO_KO_ZN.match(t).groups() for t in raw_titles])
    return [
        {"authors": a, "title": kt, "zn_title": zt, "data_id": data_id}
        for (a, kt, zt, data_id) in zip(authors, ko_titles, zn_titles, data_id)
    ]


@app.route("/corpora/itkc")
def itkc_root():
    return {
        "series": [{"id": "BT", "name": "고전번역서",}, {"id": "MO", "name": "한국문집총간",}],
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
    all_title_nodes = tree.xpath("//div[contains(@class, 'text_body_tit') and not(contains(@class, 'ori'))]")[0]
    title_t = bt_div_to_text(all_title_nodes)
    if len(tree.xpath("//div[@class='text_body_tit ori']")) > 0:
        all_zn_title_nodes = tree.xpath("//div[@class='text_body_tit ori']")[0]
        zn_title_t = bt_div_to_text(all_zn_title_nodes)
    else:
        zn_title_t = None
    return t, zn_t, title_t, zn_title_t


@app.route("/corpora/itkc/BT/text/<string:data_id>")
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


swagger_yml = load(open("./openapi/itkc_api.yaml", "r"), Loader=Loader)
swaggerui_blueprint = get_swaggerui_blueprint(
    "/api/docs", "/api/docs/swagger.json", config={"spec": swagger_yml}
)
app.register_blueprint(swaggerui_blueprint, url_prefix="/api/docs")

if __name__ == "__main__":
    app.run()
