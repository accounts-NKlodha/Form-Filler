# Opens Chrome with the dedicated MCA profile (the one the filler extension is loaded in).
# No debug port, no automation: MCA logs out any window that has a debugger attached.
$profile = Join-Path $PSScriptRoot "..\spike\profiles\mca"
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList @(
  "--user-data-dir=`"$((Resolve-Path $profile).Path)`"",
  "--no-first-run", "--no-default-browser-check",
  "https://www.mca.gov.in/content/mca/global/en/foportal/fologin.html"
)
