# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-08-20

### Added
- **Initial Project Setup**
- Course tracking system (`/add`, `/del`, `/list`).
- Course availability notifications with user mentions.
- Secure configuration using `.env` for Token and `DEBUG` mode.
- Immediate course validation and feedback for the `/add` command.
- A user-friendly `/help` command with an embed.
- `README.md` for project setup and usage instructions.
- `requirements.txt` for easy dependency installation.
- `.gitignore` to exclude sensitive and unnecessary files.
- This `CHANGELOG.md` file.

### Changed
- Command responses for `/add` are now public to the channel.
- Improved web scraping stability with longer timeouts and added delays.
- Enhanced error logging to be more specific.

### Removed
- Removed the insecure `config.py` file.
