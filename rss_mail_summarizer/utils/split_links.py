def split_links_by_github(links):
    github_links = [url for url in links if "github.com" in url.lower()]
    non_github_links = [url for url in links if "github.com" not in url.lower()]
    return github_links, non_github_links