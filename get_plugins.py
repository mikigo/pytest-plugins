from __future__ import annotations

import pathlib
from textwrap import indent

import platformdirs
import tabulate
import wcwidth
from requests_cache import CachedResponse
from requests_cache import CachedSession
from requests_cache import OriginalResponse
from requests_cache import SQLiteCache
from tqdm import tqdm

FILE_HEAD = r"""
# Pytest Plugins

"""
DEVELOPMENT_STATUS_CLASSIFIERS = (
    "Development Status :: 1 - Planning",
    "Development Status :: 2 - Pre-Alpha",
    "Development Status :: 3 - Alpha",
    "Development Status :: 4 - Beta",
    "Development Status :: 5 - Production/Stable",
    "Development Status :: 6 - Mature",
    "Development Status :: 7 - Inactive",
)
ADDITIONAL_PROJECTS = {  # set of additional projects to consider as plugins
    # "logassert",
    # "nuts",
    # "flask_fixture",
}


def project_response_with_refresh(
        session: CachedSession, name: str, last_serial: int
) -> OriginalResponse | CachedResponse:
    response = session.get(f"https://pypi.org/pypi/{name}/json")
    if int(response.headers.get("X-PyPI-Last-Serial", -1)) != last_serial:
        response = session.get(f"https://pypi.org/pypi/{name}/json", refresh=True)
    return response


def get_session() -> CachedSession:
    cache_path = platformdirs.user_cache_path("pytest-plugin-list")
    cache_path.mkdir(exist_ok=True, parents=True)
    cache_file = cache_path.joinpath("http_cache.sqlite3")
    return CachedSession(backend=SQLiteCache(cache_file))


def pytest_plugin_projects_from_pypi(session: CachedSession) -> dict[str, int]:
    response = session.get(
        "https://pypi.org/simple",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        refresh=True,
    )
    return {
        name: p["_last-serial"]
        for p in response.json()["projects"]
        if (name := p["name"]).startswith("pytest-") or name in ADDITIONAL_PROJECTS
    }


def iter_plugins():
    session = get_session()
    name_2_serial = pytest_plugin_projects_from_pypi(session)

    for name, last_serial in tqdm(name_2_serial.items(), smoothing=0):
        response = project_response_with_refresh(session, name, last_serial)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        info = response.json()["info"]
        if "Development Status :: 7 - Inactive" in info["classifiers"]:
            continue
        name = info["name"]
        home_page = info["home_page"]
        yield {
            "name": f"[{name}]({home_page if home_page else info['project_url']})",
            "summary": info["summary"].strip().replace("\n", ",") if info["summary"] else "",
        }


def main(group_keywords):
    plugin_list = pathlib.Path(__file__).parent / "README.md"

    plugins = [*iter_plugins()]
    group_plugins = {}
    for plugin in plugins:
        flag = False
        for group_key, kws in group_keywords.items():
            for kw in kws:
                if kw in plugin.get("name"):
                    if group_plugins.get(group_key) is None:
                        group_plugins[group_key] = []
                    group_plugins[group_key].append(plugin)
                    flag = True
                    break
            if flag:
                break
        else:
            if group_plugins.get("other") is None:
                group_plugins["other"] = []
            group_plugins["other"].append(plugin)

    with plugin_list.open("w", encoding="UTF-8") as f:

        f.write(FILE_HEAD)
        f.write(f"这份列表包含了 {len(plugins)} 个 Pytest 插件.\n\n")
        wcwidth

        other = group_plugins.get("other")
        group_plugins.pop("other")
        for group_key in group_plugins:
            group_plugin = group_plugins.get(group_key)
            f.write(f"## {group_key}\n\n")
            plugin_table = tabulate.tabulate(group_plugin, headers="keys", tablefmt="pipe")
            f.write(indent(plugin_table, ""))
            f.write("\n\n")

        f.write(f"## other\n\n")
        plugin_table = tabulate.tabulate(other, headers="keys", tablefmt="pipe")
        f.write(indent(plugin_table, ""))

        f.write("\n\n")


if __name__ == "__main__":
    group_keywords = {
        "log": ["log", ],
        "report": ["report", "allure", "html", "json", "markdown", "rich", "email"],
        "run": ["run", "time", "retry", "random",  "reverse", "sort", ],
        "async": ["async", ],
        "api": ["api", ],
        "auto": ["auto", "selenium", "playwright", "requests"],
        "bdd": ["bdd", ],
        "check": ["check", "assert", "expect", ],
        "config": ["config", "env", "ini"],
        "cov": ["cov", ],
        "mock": ["mock", ],
        "db": ["mongodb", "mysql", ],
        "framework": ["fastapi", "django", "flask", "nginx", "nose", "redis", "docker", ],
    }
    main(group_keywords)
