@REM set CACHE_DIR=cache
@REM RMDIR cache /S /Q
@REM markbind deploy

@echo off
if "%GITHUB_TOKEN%"=="" (
    echo ERROR: GITHUB_TOKEN is not set.
    echo Create a GitHub personal access token with write access to
    echo NUS-CS2113-AY2627-S1/website, then run:  set GITHUB_TOKEN=^<your token^>
    exit /b 1
)
rem MarkBind allows --ci only when it detects a supported CI vendor
rem (TRAVIS, APPVEYOR, GITHUB_ACTIONS, or CIRCLECI), so emulate GitHub
rem Actions to run the token-based (non-interactive) deploy locally.
rem GITHUB_REPOSITORY supplies the repo slug; GITHUB_WORKSPACE keeps the
rem gh-pages clone cache outside this repo so it cannot end up in the site.
set GITHUB_ACTIONS=true
set GITHUB_REPOSITORY=NUS-CS2113-AY2627-S1/website
set GITHUB_WORKSPACE=%TEMP%\markbind-deploy-cache
if not exist "%GITHUB_WORKSPACE%" mkdir "%GITHUB_WORKSPACE%"
markbind deploy --ci
