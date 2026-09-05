# LightLink Windows Git Push Agent

This local helper accepts one operation only: push the current, clean `production` HEAD of
`product-hub-production2` to the fixed SSH remote `git@github.com:lightlink029-max/dongcheng.git`.

The installed agent validates the request schema, repository, branch, remote, and expected commit.
It disables repository Git hooks, verifies the remote commit after pushing, and writes a JSON result.
Its installed code and SSH wrapper are protected for the interactive Windows user; the shared queue
contains no command or path fields.

Install once from PowerShell under the `Admin` Windows account:

```powershell
& ".\tools\windows_git_push_agent\Install-LightLinkGitPushAgent.ps1"
```

Request a production push:

```powershell
& ".\tools\windows_git_push_agent\Request-ProductionPush.ps1"
```
