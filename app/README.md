# Atelier installer and updates

Build on 64-bit Windows with Python 3.13, Inno Setup 6.7.3, and the Simplified Chinese messages file. The source checkout needs a prepared `app/resources` pack containing a matching catalogue, native metadata, schema, and a verified clean baseline for the supported game build. [Inno Setup](https://jrsoftware.org/inno-setup/downloads) · [Simplified Chinese messages](https://github.com/kira-96/Inno-Setup-Chinese-Simplified-Translation/blob/1ff90acc4ed4aee82b1cda43253243deee3daed4/ChineseSimplified.isl)

From the repository root in PowerShell, create the build environment and run the installer builder. Set the compiler and translation paths to the files on your machine.

```powershell
py -3.13 -m venv .\app_build_env
.\app_build_env\Scripts\python.exe -m pip install -r app/requirements.txt PyInstaller==6.22.3

$build = @{
    Version = '0.2.9.3'
    Python = '.\app_build_env\Scripts\python.exe'
    InnoCompiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    ChineseMessages = 'C:\BuildTools\ChineseSimplified.isl'
}
.\app\installer\build.ps1 @build
```

The output under `releases/v0.2.9.3` contains the setup executable and `latest.json`. The setup uses a stable application ID and remembers the previously selected folders. It replaces the program files on an in-place upgrade. Keep the version increasing and keep the application ID fixed across releases.

## Publish an update

1. Build with the next version number. If you distribute via a stable share folder such as Baidu Wangpan, set `-ReleasePage` to its HTTPS link so Atelier's Updates dialog can open it. For automatic version checks, also set `-UpdateFeed` to the permanent HTTPS URL of the release JSON, such as `https://downloads.example.com/atelier/latest.json`.
2. Upload the versioned setup executable. If you use an object host for downloads, place the executable next to `latest.json`. If you use a Wangpan folder, put the executable in that folder.
3. For an automatic channel, publish the generated `latest.json` after the new setup is available. If you use Wangpan, the JSON goes on a separate HTTPS host that serves it directly. The checker compares the installed version against the feed and opens the download or the share folder. Builds without a feed show the installed version and link to a release page if one was configured.

Keep the generated resource pack, user profiles, backups and build outputs outside Git. When the game updates, regenerate and verify the pack for the new game build before releasing Atelier. See the [user installation guide](../README.md) for the version this release supports.
