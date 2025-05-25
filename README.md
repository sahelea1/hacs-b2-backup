# Backblaze B2 Backup for Home Assistant

A **tiny HACS integration** that registers a Backblaze B2 bucket as a storage
_target_ for the new Home-Assistant **native backup** platform  
(HA Core ≥ 2025.1).  
*Keep the latest snapshot locally, push every backup off-site – no add-ons
needed.*

---

## Features
* 🔌 Plugs into **Settings › System › Backups** as a regular storage location  
* 💾 Streams each `.tar` straight to Backblaze B2 (retaining filename / ID)  
* 🗑️ Supports listing, download & deletion through the UI  
* 🔐 Credentials stored inside HA config-entries (not in source code)  
* 📦 Only 4 small files, single dependency `b2sdk`

---

## Requirements
| Requirement | Notes |
|-------------|-------|
| **Home Assistant Core** | 2025.1 or newer (native backup platform) |
| **Python package** | `b2sdk ≥ 1.23.0` – installed automatically by HA |
| **Backblaze account** | Application Key with **B2 Native API** access |

---

## Installation

### via HACS (recommended)
1. **HACS › Integrations › “+” › Custom repository**  
   *URL:* `https://github.com/sahelea1/hacs-b2-backup`  
   *Category:* “Integration”
2. Install **Backblaze B2 Backup**, then **restart Home Assistant**.

### manual copy
```text
<config>/custom_components/b2_backup/
    ├── __init__.py
    ├── backup.py
    ├── config_flow.py
    └── manifest.json
