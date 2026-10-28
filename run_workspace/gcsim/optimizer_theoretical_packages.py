"""Shared theoretical package identities and canonical GCSIM set-row rendering."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
import re
from types import MappingProxyType

from .optimizer_product_contracts import GcsimTwoPlusTwoTargetPackage


class GcsimTheoreticalPackageError(ValueError):
    """Raised when a synthetic package identity/render is inconsistent."""


def gcsim_theoretical_pair_package_key(
    package: GcsimTwoPlusTwoTargetPackage,
) -> str:
    if not isinstance(package, GcsimTwoPlusTwoTargetPackage):
        raise GcsimTheoreticalPackageError("package must be a typed 2p+2p package")
    return f"pair_{package.identity_sha256}"


def freeze_gcsim_theoretical_pair_packages(
    packages: Mapping[str, GcsimTwoPlusTwoTargetPackage] | None,
):
    normalized = {}
    for key, package in (packages or {}).items():
        if not isinstance(package, GcsimTwoPlusTwoTargetPackage):
            raise GcsimTheoreticalPackageError(
                "theoretical pair package values must be typed"
            )
        expected = gcsim_theoretical_pair_package_key(package)
        if str(key) != expected:
            raise GcsimTheoreticalPackageError(
                "theoretical pair package key differs from its canonical identity"
            )
        normalized[expected] = package
    return MappingProxyType(dict(sorted(normalized.items())))


def gcsim_theoretical_pair_domain_sha256(packages) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                key: package.to_dict()
                for key, package in sorted(packages.items())
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def render_gcsim_theoretical_pair_rows(
    config_text: str,
    *,
    wearer: str,
    carrier_set_key: str,
    package: GcsimTwoPlusTwoTargetPackage,
) -> str:
    pattern = re.compile(
        rf'(?m)^[ \t]*{re.escape(wearer)}[ \t]+add[ \t]+set="'
        rf'{re.escape(carrier_set_key)}"[ \t]+count=4'
        rf'(?:[ \t]+\+params=\[[^\]\r\n]*\])?;[ \t]*(?P<ending>\r?)$'
    )
    matches = tuple(pattern.finditer(config_text))
    if len(matches) != 1:
        raise GcsimTheoreticalPackageError(
            "pair carrier config lacks one canonical 4p set row"
        )
    ending = matches[0].group("ending")
    lines = []
    for set_ref in (package.set_a, package.set_b):
        parameters = ""
        if set_ref.set_parameters:
            rendered = ",".join(
                f"{key}={set_ref.set_parameters[key]}"
                for key in sorted(set_ref.set_parameters)
            )
            parameters = f" +params=[{rendered}]"
        lines.append(
            f'{wearer} add set="{set_ref.gcsim_set_key}" '
            f"count=2{parameters};"
        )
    replacement = f"{lines[0]}{ending}\n{lines[1]}{ending}"
    return pattern.sub(replacement, config_text, count=1)


__all__ = [
    "GcsimTheoreticalPackageError",
    "freeze_gcsim_theoretical_pair_packages",
    "gcsim_theoretical_pair_domain_sha256",
    "gcsim_theoretical_pair_package_key",
    "render_gcsim_theoretical_pair_rows",
]
