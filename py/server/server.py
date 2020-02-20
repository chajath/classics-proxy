from flask import Flask
from flask_caching import Cache
from flask_marshmallow import Marshmallow, fields
import requests
from lxml import html, etree
import re

config = {
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 3600,
}
app = Flask(__name__)
app.config.from_mapping(config)
ma = Marshmallow(app)
cache = Cache(app)


class RootSchema(ma.Schema):
    class Meta:
        fields = ("_links",)

    _links = fields.Hyperlinks(
        {"self": fields.URLFor("root"), "collection": fields.URLFor("corpora")}
    )


root_schema = RootSchema()

CORPORA = ["itkc"]


class CorporaSchema(ma.Schema):
    class Meta:
        fields = ("_links",)

    _links = fields.Hyperlinks({x: fields.URLFor(x + "_root") for x in CORPORA})


corpora_schema = CorporaSchema()


@app.route("/")
def root():
    return root_schema.dump({})


@app.route("/corpora")
def corpora():
    return corpora_schema.dump({})


TITLE_TO_KO_CN = re.compile("(^.*)\\((.*)\\)$")
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
        t = ""
        for elem in n.xpath("node()"):
            if isinstance(elem, str):
                t = t + elem
            elif isinstance(elem, html.HtmlElement):
                if elem.tag == 'img' and elem.attrib['class'] == 'newchar':
                    code = SINCHUL_CODE_EXTRACT.match(elem.attrib['src']).groups()[0]
                    if code in SINCHUL_HANJA_LOOKUP:
                        t = t + SINCHUL_HANJA_LOOKUP.get(code)
                    else:
                        print(f"Unknown Sinchul Hanja code: {code}")
                else:
                    print(f"Unknown img tag: {etree.tostring(elem,encoding='unicode')}")
        raw_titles.append(t)
    authors = [t.split(" | ")[1] for t in tree.xpath("//li/span/@title")]
    data_id = tree.xpath("//li/@data-dataid")
    ko_titles, cn_titles = zip(*[TITLE_TO_KO_CN.match(t).groups() for t in raw_titles])
    return [
        {"authors": a, "ko_titles": kt, "cn_titles": ct, "data_id": data_id}
        for (a, kt, ct, data_id) in zip(authors, ko_titles, cn_titles, data_id)
    ]


@app.route("/corpora/itkc")
def itkc_root():
    return {"series": ["BT", "MO"]}


@app.route("/corpora/itkc/<string:series_id>")
def itkc_series(series_id):
    collections = get_all_itkc_collections(series_id)
    return {"collections": collections}


@cache.memoize()
def get_all_itkc_links(series_id, depth, data_id):
    r = requests.get(
        f"http://db.itkc.or.kr/dir/treeAjax?grpId=&itemId={series_id}&gubun=book&depth={depth}&dataId={data_id}"
    )
    tt = r.text
    tree = html.fromstring(tt)
    titles = tree.xpath("//li/span/@title")
    data_id = tree.xpath("//li/@data-dataid")
    return [
        {"title": title, "data_id": data_id}
        for (title, data_id) in zip(titles, data_id)
    ]


ITKC_DEPTH_VOLUME = 2
ITKC_DEPTH_SECTION = 3


@app.route("/corpora/itkc/<string:series_id>/<string:data_id>")
def itkc_volumes(series_id, data_id):
    volumes = get_all_itkc_links(series_id, ITKC_DEPTH_VOLUME, data_id)
    return {"volumes": volumes}


@app.route("/corpora/itkc/<string:series_id>/<string:book_id>/<string:data_id>")
def itkc_sections(series_id, book_id, data_id):
    sections = get_all_itkc_links(series_id, ITKC_DEPTH_SECTION, data_id)
    return {"sections": sections}


if __name__ == "__main__":
    app.run()
