load("@rules_python//python:defs.bzl", "py_library")
load("@third_party//:requirements.bzl", "requirement")

package(default_visibility = ["//visibility:public"])

py_library(
    name = "flask",
    deps = [
        requirement("Flask"),
        requirement("Werkzeug"),
        requirement("itsdangerous"),
        requirement("Jinja2"),
        requirement("MarkupSafe"),
        requirement("click"),
        requirement("flask-marshmallow"),
        requirement("marshmallow"),
        requirement("six"),
    ],
)

py_library(
  name = "requests",
  deps = [
    requirement("requests"),
    requirement("certifi"),
    requirement("chardet"),
    requirement("idna"),
    requirement("urllib3")
  ]  
)

py_library(
  name = "lxml",
  deps = [
    requirement("lxml"),
  ]
)