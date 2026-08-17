@echo off
if "%GITHUB_TOKEN%"=="" (
    echo ERROR: GITHUB_TOKEN is not set.
    echo Create a GitHub personal access token with write access to
    echo NUS-CS2113-AY2627-S1/website, then run:  set GITHUB_TOKEN=^<your token^>
    exit /b 1
)
rem Clear the gh-pages deploy cache so a previously failed deploy cannot
rem leave the cached clone in a broken state.
if exist node_modules\.cache\gh-pages rmdir /s /q node_modules\.cache\gh-pages
markbind deploy --ci
