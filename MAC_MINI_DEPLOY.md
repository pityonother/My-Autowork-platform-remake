# Mac mini LAN Deployment

Use the Mac mini as the LAN server for My-Autowork. Coworkers only need the LAN URL in a browser.

## First-Time Setup

```bash
cd /Users/Shared
git clone https://github.com/pityonother/My-Autowork-platform-remake.git My-Autowork-platform-remake
cd /Users/Shared/My-Autowork-platform-remake
chmod +x *.sh
./install_macos_service.sh
```

The default LAN URL is:

```text
http://Mac-mini-IP:8010
```

## Data Location

Mac runtime data is outside the code checkout:

```text
/Users/Shared/company_tools_data/my_autowork/runtime
```

Code is updated from GitHub. Runtime databases, uploads, generated files, logs, and backups are not committed.

## Update Later

```bash
cd /Users/Shared/My-Autowork-platform-remake
./update_mac_mini.sh
```

The update script backs up runtime data, pulls latest code, refreshes dependencies, regenerates the launchd plist, and restarts the service.
