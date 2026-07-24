#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / "test" / "update-system.test.ts"
content = path.read_text(encoding="utf-8")
old = '''  assert.equal(manifest.createCabinetVersion, pkgVersion);\n  assert.equal(manifest.cabinetaiVersion, pkgVersion);\n'''
new = '''  if (manifest.repositoryUrl === "https://github.com/cabinetai/cabinet") {\n    assert.equal(manifest.createCabinetVersion, pkgVersion);\n    assert.equal(manifest.cabinetaiVersion, pkgVersion);\n  } else {\n    // Fork distributions do not publish the upstream npm packages and must not\n    // advertise versions that cannot be installed.\n    assert.equal(manifest.createCabinetVersion, undefined);\n    assert.equal(manifest.cabinetaiVersion, undefined);\n  }\n'''
if content.count(old) != 1:
    raise RuntimeError("Expected upstream npm manifest assertions exactly once")
path.write_text(content.replace(old, new, 1), encoding="utf-8")
print("Adjusted update manifest test for fork distributions.")
