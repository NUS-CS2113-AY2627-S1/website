@echo off
setlocal
rem Deploys the MarkBind site to the gh-pages branch.
rem
rem We deliberately do NOT use "markbind deploy": its gh-pages library fails
rem on Windows (chokes on the '!' cache paths with wslgit, on paths longer
rem than 260 chars, and on passing every site file as one giant "git rm"
rem command line) and it swallows those errors, printing "Deployed!" even
rem when nothing was pushed. This script does the same steps explicitly.
rem
rem Uses MinGit (D:\tools\mingit, core.longpaths=true) because the default
rem git on this machine is the wslgit shim, which corrupts '!' in arguments.

set GIT=D:\tools\mingit\cmd\git.exe
set REPO_SLUG=NUS-CS2113-AY2627-S1/website
set WORKDIR=%TEMP%\site-deploy-website

if "%GITHUB_TOKEN%"=="" (
    echo ERROR: GITHUB_TOKEN is not set.
    echo Create a GitHub personal access token with write access to
    echo %REPO_SLUG%, then run:  set GITHUB_TOKEN=^<your token^>
    exit /b 1
)

echo === Building site...
call markbind build
if errorlevel 1 (
    echo ERROR: markbind build failed.
    exit /b 1
)

echo === Cloning gh-pages branch...
if exist "%WORKDIR%" rmdir /s /q "%WORKDIR%"
"%GIT%" clone --quiet --branch gh-pages --single-branch --depth 1 "https://x-access-token:%GITHUB_TOKEN%@github.com/%REPO_SLUG%.git" "%WORKDIR%"
if errorlevel 1 (
    echo ERROR: clone of gh-pages branch failed.
    exit /b 1
)

echo === Copying built site...
robocopy "_site" "%WORKDIR%" /MIR /XD .git /NFL /NDL /NJH /NJS /NP
if %ERRORLEVEL% GEQ 8 (
    echo ERROR: copying _site failed.
    exit /b 1
)

echo === Committing and pushing...
cd /d "%WORKDIR%"
"%GIT%" add -A
"%GIT%" diff-index --quiet HEAD
if not errorlevel 1 (
    echo Nothing to deploy: site is identical to what is already published.
    goto cleanup
)
"%GIT%" -c user.name="okkhoy" -c user.email="okkhoy@gmail.com" commit --quiet -m "Site Update. [skip ci]"
if errorlevel 1 (
    echo ERROR: commit failed.
    exit /b 1
)
"%GIT%" push --quiet origin gh-pages
if errorlevel 1 (
    echo ERROR: push failed.
    exit /b 1
)
echo === Deployed. Verify at: https://github.com/%REPO_SLUG%/commits/gh-pages

:cleanup
cd /d "%~dp0"
rem Remove the work dir: its .git config contains the access token.
rmdir /s /q "%WORKDIR%"
exit /b 0
