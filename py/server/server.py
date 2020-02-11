from flask import Flask
from flask_marshmallow import Marshmallow, fields
import requests
from lxml import html

app = Flask(__name__)
ma = Marshmallow(app)


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


@app.route("/corpora/itkc")
def itkc_root():
    return {"_links": {"titles": "/corpora/itkc/titles"}}


@app.route("/corpora/itkc/titles")
def itkc_titles():
    r = requests.get(
        "http://db.itkc.or.kr/dir/treeAjax?grpId=&itemId=BT&gubun=book&depth=1"
    )
    tt = r.text
    tree = html.fromstring(tt)
    raw_titles = tree.xpath("//li/span/text()")
    authors = tree.xpath("//li/span/@title")
    return {"raw_titles": raw_titles, "authors": authors}


if __name__ == "__main__":
    app.run()
