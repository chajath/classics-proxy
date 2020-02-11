load("@rules_python//python:defs.bzl", "py_binary")

py_binary(
    name = "server",
    srcs = ["server.py"],
    deps = [
        "//third_party/py:flask",
        "//third_party/py:lxml",
        "//third_party/py:requests",
    ],
    python_version="PY3",
    srcs_version="PY3",
)
