"""Destino GitHub.com para las copias nativas de Home Assistant."""

import re
from urllib.parse import urlsplit

from .forgejo import REPOSITORY_README, Forgejo
from .forgejo_releases import FILE_NAME, ReleaseError, Releases, validate_web_url

GITHUB_HOSTS = {"github.com", "ssh.github.com"}
# Deja margen para la cabecera, los objetos Git y el empaquetado del push de 2 GiB.
MAX_GITHUB_SIZE = 1900 * 1024**2


def is_github(ssh_url):
    return urlsplit(ssh_url).hostname in GITHUB_HOSTS


def normalize_ssh_url(url):
    if re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git", url):
        return "ssh://" + url.replace(":", "/", 1)
    return url


def github_web_url(ssh_url):
    return "https://github.com" + urlsplit(ssh_url).path.removesuffix(".git")


def validate_github_web_url(web_url, ssh_url):
    normalized = validate_web_url(web_url, ssh_url)
    expected = github_web_url(ssh_url)
    if normalized.lower() != expected.lower():
        raise ReleaseError("Usa la URL HTTPS del mismo repositorio privado en github.com.")
    return expected


class GitHub(Forgejo):
    provider_name = "GitHub"
    max_size = MAX_GITHUB_SIZE
    readme = REPOSITORY_README.replace(
        "Private Git Manager · Forgejo Backup", "Private Git Manager"
    ).replace("Forgejo", "GitHub")

    def _links(self, backup_id):
        web = github_web_url(self.url)
        return (
            f"{web}/blob/pgm-meta-{backup_id}/metadata.json",
            f"{web}/archive/refs/tags/pgm-data-{backup_id}.zip",
            f"{web}/releases/download/pgm-data-{backup_id}/backup.tar",
        )


class GitHubReleases(Releases):
    provider_name = "GitHub"

    def __init__(self, web_url, token):
        super().__init__(web_url, token)
        path = urlsplit(web_url).path
        self.repo = f"https://api.github.com/repos{path}"
        self.upload_repo = f"https://uploads.github.com/repos{path}"

    def _upload_asset(self, release_id, source, size):
        # GitHub recibe el binario sin multipart y usa un host de subida independiente.
        with source.open("rb") as stream:
            self._request(
                "POST",
                f"/releases/{release_id}/assets?name={FILE_NAME}",
                base=self.upload_repo,
                body=stream,
                headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)},
            )

    @staticmethod
    def _asset_path(release_id, asset_id):
        return f"/releases/assets/{asset_id}"
