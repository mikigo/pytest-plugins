from __future__ import annotations

import datetime
import pathlib
import re
from textwrap import dedent
from textwrap import indent

import packaging.version
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
    "logassert",
    "nuts",
    "flask_fixture",
}


def escape_rst(text: str) -> str:
    text = (
        text.replace("*", "\\*")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("`", "\\`")
    )
    text = re.sub(r"_\b", "", text)
    return text


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

        def version_sort_key(version_string):
            try:
                return packaging.version.parse(version_string)
            except packaging.version.InvalidVersion:
                return packaging.version.Version("0.0.0alpha")

        last_release = ""
        releases = response.json()["releases"]
        for release in sorted(releases, key=version_sort_key, reverse=True):
            if releases[release]:
                release_date = datetime.date.fromisoformat(
                    releases[release][-1]["upload_time_iso_8601"].split("T")[0]
                )
                last_release = release_date.strftime("%b %d, %Y")
                break
        yield {
            "name": info["name"],
            "summary": info["summary"].strip() if info["summary"] else "",
            "last release": last_release,
        }


log = "log"
report = "report"
run = "run"
other = "other"

group_keywords = {
    log: [
        "log",
    ],
    report: [
        "report",
    ],
    run: [
        "run",
    ],
}

group_plugins = {
    log: [],
    report: [],
    run: [],
    other: [],
}


def main():
    plugin_list = pathlib.Path(__file__).parent.parent / "README.md"

    plugins = [*iter_plugins()]
    for plugin in plugins:
        flag = False
        for group_key, kws in group_keywords.items():
            for kw in kws:
                if kw in plugin.get("name"):
                    group_plugins[group_key].append(plugin)
                    flag = True
                    break
            if flag:
                break
        else:
            group_plugins[other].append(plugin)

    with plugin_list.open("w", encoding="UTF-8") as f:

        f.write(FILE_HEAD)
        f.write(f"这份列表包含了 {len(plugins)} 个 Pytest 插件.\n\n")
        wcwidth

        for group_key in group_plugins:
            group_plugin = group_plugins.get(group_key)
            f.write(f"## {group_key}\n\n")

            plugin_table = tabulate.tabulate(group_plugin, headers="keys", tablefmt="pipe")
            f.write(indent(plugin_table, ""))

            f.write("\n\n")


if __name__ == "__main__":
    main()
