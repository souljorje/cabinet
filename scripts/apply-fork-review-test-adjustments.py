#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# Fork release manifests intentionally omit upstream npm package metadata.
test_path = root / "test" / "update-system.test.ts"
test_content = test_path.read_text(encoding="utf-8")
test_old = '''  assert.equal(manifest.createCabinetVersion, pkgVersion);\n  assert.equal(manifest.cabinetaiVersion, pkgVersion);\n'''
test_new = '''  if (manifest.repositoryUrl === "https://github.com/cabinetai/cabinet") {\n    assert.equal(manifest.createCabinetVersion, pkgVersion);\n    assert.equal(manifest.cabinetaiVersion, pkgVersion);\n  } else {\n    // Fork distributions do not publish the upstream npm packages and must not\n    // advertise versions that cannot be installed.\n    assert.equal(manifest.createCabinetVersion, undefined);\n    assert.equal(manifest.cabinetaiVersion, undefined);\n  }\n'''
if test_content.count(test_old) != 1:
    raise RuntimeError("Expected upstream npm manifest assertions exactly once")
test_path.write_text(test_content.replace(test_old, test_new, 1), encoding="utf-8")

# The normalization layer must not reintroduce unpublished package versions.
manifest_path = root / "src" / "lib" / "system" / "release-manifest.ts"
manifest_content = manifest_path.read_text(encoding="utf-8")
manifest_old = '''    createCabinetVersion: version,\n    cabinetaiVersion: manifest.cabinetaiPackage ? version : manifest.cabinetaiVersion,\n'''
manifest_new = '''    createCabinetVersion:\n      repositoryUrl === "https://github.com/cabinetai/cabinet"\n        ? version\n        : undefined,\n    cabinetaiVersion:\n      repositoryUrl === "https://github.com/cabinetai/cabinet" &&\n      manifest.cabinetaiPackage\n        ? version\n        : undefined,\n'''
if manifest_content.count(manifest_old) != 1:
    raise RuntimeError("Expected release manifest package alignment exactly once")
manifest_path.write_text(
    manifest_content.replace(manifest_old, manifest_new, 1),
    encoding="utf-8",
)

print("Adjusted fork manifest normalization and its unit test.")
