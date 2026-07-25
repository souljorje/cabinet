# Good Place fork progress

[2026-07-25] Fixed prerelease update ordering with SemVer so `gp.10` sorts after `gp.9`.
[2026-07-25] Fixed local release-manifest generation to derive the repository URL from the fork's package metadata when no explicit argument or Actions repository is present. Added an invariant test covering every generated URL.
[2026-07-25] Replaced the fork README's upstream npm installation commands with the supported Good Place desktop release and source-checkout paths, including a prominent fork notice.
