# Atelier developer builds

The [installation guide](../README.md) covers the packaged Windows release. The source checkout needs a prepared `app/resources` pack containing a matched catalogue, native metadata, schema, and a verified clean baseline for the supported game build.

Build on 64-bit Windows with Python 3.13. From the repository root, run the following in PowerShell.

```powershell
py -3.13 -m venv .\app_build_env
.\app_build_env\Scripts\python.exe -m pip install -r app/requirements.txt PyInstaller==6.22.3
.\app_build_env\Scripts\python.exe app/package_app.py --version 0.2.9.2 --output releases/v0.2.9.2
```

The builder uses `app/resources/catalogue.zip` by default and accepts a different catalogue via `--catalogue`. It checks the catalogue version and packaged baseline hashes. The packaged app locates the game on the destination PC. Zip the entire output `NarakaAtelier` folder with its `_internal` directory for distribution.

Keep generated resources, local profiles, backups, and build outputs outside Git. When the game changes, regenerate and verify the resource pack for the new build before packaging a new release.
