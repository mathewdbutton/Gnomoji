# Emoji Picker .deb Package — Design

> **Superseded in part (2026-10-02):** triggering, inserting and installing are now in
> `2026-10-02-v2-port-design.md`. This spec stays the reference for what that one doesn't change.

**Status:** Approved; implemented on build/deb-package.
**Date:** 2026-09-27
**Branch:** `build/deb-package`

## Intent

Let people install the picker without cloning the repo.

**Who it's for:** mainly the author, plus a few friends on Ubuntu (or other Debian-based)
GNOME desktops who are sent a link. Reaching every distro is not a goal.

**The pain it removes:** today a friend has to clone the repo, run `./install.sh`, and keep
the folder where it is, because the service runs from the clone. The author's own daily
picker also runs from the development checkout, so switching branches changes what runs.

**Success looks like:**

- A friend downloads a `.deb` from GitHub Releases, double-clicks it, installs it through
  App Center, and within seconds gets the "ready" notification. No terminal, no log-out.
- Updating means installing the newer `.deb` the same way (App Center shows **Install** again for
  the newer version). Removing works by opening the .deb in App Center again (Uninstall) or
  `sudo apt remove emoji-picker`.
- The author runs the released `.deb` day to day and develops from the repo separately.

**Decided against:**

- A self-updater (felt risky) or an apt repository/PPA. Updating is manual.
- A `curl | bash` installer. `install.sh` stays for people running from a clone.
- Flatpak, Snap, AppImage: the picker needs raw keyboard access, `/dev/uinput` and a udev rule.
- PyPI/pipx: runtime deps are distro packages, and pip can't install a udev rule.

## Platform facts this relies on

- Ubuntu 24.04's App Center installs a local `.deb` on double-click, after an update
  rolled out in mid-2024. It warns that side-loaded packages can be risky; that's expected
  for an unsigned `.deb`. (Before that update it showed an endless spinner.)
- A `.deb` installs as root, but the picker is a per-user systemd service. systemd 255
  (Ubuntu 24.04) supports `systemctl --global enable` (all users, at log-in) and
  `systemctl --user --machine=<user>@.host ...` (act on one running user manager from root).
- A user unit in `~/.config/systemd/user/` overrides one of the same name in
  `/usr/lib/systemd/user/`, and a rule in `/etc/udev/rules.d/` overrides one of the same name
  in `/usr/lib/udev/rules.d/`.
- App Center never lists a side-loaded .deb in its search or installed list, with or without
  AppStream metadata, but reopening the .deb file offers Uninstall, and a newer .deb shows
  Install (which upgrades).
- The code finds `data/` relative to its own file (`emoji_data.py`, `fonts.py`), so it runs
  from any install location unchanged.
- `systemctl --global enable` applies to every user manager, including system users such as
  GDM's greeter (whose session reaches `graphical-session.target` too), so the unit carries
  `ConditionUser=!@system`.

## Package contents

One architecture-independent package: `emoji-picker_<version>_all.deb`.

| File | Installed at |
|---|---|
| The Python package, with `data/` | `/usr/lib/python3/dist-packages/emoji_picker/` |
| Launcher (`exec /usr/bin/python3 -m emoji_picker "$@"`) | `/usr/bin/emoji-picker` |
| User service | `/usr/lib/systemd/user/emoji-picker.service` |
| Hidden desktop entry | `/usr/share/applications/local.emojipicker.EmojiPicker.desktop` |
| Icon | `/usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg` |
| udev rule | `/usr/lib/udev/rules.d/70-emoji-picker.rules` |
| Package docs | `/usr/share/doc/emoji-picker/copyright`, `changelog.gz` |

**Depends:** `python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1,
fonts-noto-color-emoji`. This is the same list `install.sh` checks and installs with apt.

**Templates, one source each:** `systemd/emoji-picker.service` and
`desktop/local.emojipicker.EmojiPicker.desktop` keep their `@SRC@` placeholders. The build
script fills them in for the package: the service loses its `Environment=PYTHONPATH=` line and
the desktop entry's `Exec=` becomes `/usr/bin/python3 -m emoji_picker`. `install.sh` fills them
in for a clone as it does today.

The application code doesn't change.

## Install, upgrade and remove

Maintainer scripts in `packaging/deb/`, run as root by dpkg (via apt or App Center).

**`postinst` (install and upgrade):**

1. Reload udev and re-trigger input and misc devices (`--action=change`), then
   `udevadm settle --timeout=10`, so the `uaccess` ACL applies to the active seat user at once
   without risking an unbounded wait.
2. `py3compile -p emoji-picker`, so the restarted picker below uses the compiled bytecode.
3. `systemctl --global enable emoji-picker.service`.
4. For each user whose systemd user manager is running (e.g. from `loginctl list-users`) **and**
   whose `graphical-session.target` is active (skipping lingering/SSH-only sessions, which have a
   user manager but no graphical session), run
   `systemctl --user --machine=<user>@.host daemon-reload` and then `restart emoji-picker`. On a
   first install this starts it and the existing first-run welcome appears. On an upgrade the new
   version replaces the old one.

**`prerm` (remove and upgrade):** `py3clean -p emoji-picker` on both, so a root-owned
`__pycache__` never blocks removal. On remove only: stop the service in each running user
manager, then `systemctl --global disable emoji-picker.service`. Upgrade never stops or
disables it.

**`postrm` (remove and purge):** reload udev and re-trigger, so the rule's removal takes
effect for new devices. Access already granted ends at the next log-in.

**Rules:**

- Steps that act on user sessions or on `--global` are best-effort: failures print one
  line and are ignored. No desktop session (e.g. installed over SSH) means the picker starts at
  the next log-in. Only genuine packaging errors may fail the install.
- The scripts never touch home directories, even on `apt purge`. Recents
  (`~/.local/state/emoji-picker/`) and config (`~/.config/emoji-picker/`) stay; UNINSTALL.md
  says how to delete them.
- A clone install coexists: its user unit in `~/.config/systemd/user/` wins over the packaged
  one, and a leftover `/etc/udev/rules.d/70-emoji-picker.rules` from `install.sh` has the same
  content. To switch a machine to the package, run `./uninstall.sh` first.

## Building

`packaging/build-deb.sh`:

- Builds from `git archive HEAD` in a temporary directory, never from the working tree, so
  uncommitted edits, test pastes, `CLAUDE.local.md`, `.superpowers/` and `__pycache__` can't
  get in. It refuses to run if `HEAD` can't be archived.
- Reads the version from `pyproject.toml`.
- Lays out the tree from the table above, fills in the templates, writes `DEBIAN/control`,
  copies the maintainer scripts, generates `copyright` from `LICENSE`, gzips a short
  `changelog`, and runs `dpkg-deb --root-owner-group --build`.
- Output: `dist/emoji-picker_<version>_all.deb`. `dist/` is git-ignored.
- It includes only runtime files: no tests, docs, tools, spike or packaging sources.

## Releasing

`.github/workflows/package.yml`, on `ubuntu-24.04`. It runs on every pull request (build and
smoke-test only, no release) and on pushing a `v*` tag (build, smoke-test, and draft release):

1. On a tag push: fail unless the tag equals `v` + `pyproject.toml`'s version.
2. `shellcheck` the build script and the maintainer scripts.
3. Run `packaging/build-deb.sh`.
4. Smoke test: `sudo apt install ./dist/*.deb`, check the files are in place and that
   `/usr/bin/python3 -c "import emoji_picker"` works without `PYTHONPATH` (the runner has no
   display, so it doesn't start the picker), then `sudo apt remove emoji-picker` and check the package's files are gone. There is
   no desktop session on the runner, so this also covers the "no session" path of `postinst`.
5. On a tag push only: create a **draft** GitHub Release for the tag with the `.deb` attached.

**Author's release steps:** bump `version` in `pyproject.toml`, commit, tag `v<version>`,
push the tag. Download the draft's `.deb`, install and try it, then publish the release.

## Licence

MIT, copyright 2026 Mathew Button. Added as `LICENSE`, as `license = "MIT"` in
`pyproject.toml`, and as the package's `copyright` file.

## Testing

**Automated (local, in `uv run pytest`):** `tests/test_package.py` runs the build script and
inspects the result with `dpkg-deb`:

- `Package`, `Version` (matches `pyproject.toml`), `Architecture: all`, and `Depends` matches
  `install.sh`'s apt package list.
- Every file in the contents table is present at its path; the launcher and maintainer scripts
  are executable.
- The installed service and desktop entry contain no `@SRC@` and no `PYTHONPATH`.
- Nothing unwanted: no `tests/`, `docs/`, `tools/`, `spike/`, `CLAUDE`, `.superpowers`,
  `__pycache__` or `.pyc`.

Skipped if `dpkg-deb` or `git` is missing. Because the build uses `HEAD`, the test checks the
last commit, not uncommitted edits.

**Automated (CI):** `shellcheck` and the install/remove smoke test above.

**Hands-on, before the first release, on the author's machine:**

1. `./uninstall.sh`, then double-click the `.deb` and install via App Center. The "ready"
   notification appears within seconds, with no log-out, and a pick works.
2. Log out and in: the picker starts by itself.
3. Upgrade: install a test build with a higher version over it. The running picker is
   replaced by the new version (check the journal).
4. Remove via App Center: the picker stops and the package's files are gone.
5. Install again; this is the daily setup from now on.
6. Optional: step 1 in a throwaway user account with any other udev rule that grants keyboard
   access moved aside, to prove the packaged rule alone grants access.

## Docs

- **README:** Install leads with "download the `.deb` from Releases and double-click it";
  updating is "install the newer `.deb`"; uninstalling is App Center or
  `sudo apt remove emoji-picker`. Clone + `./install.sh` moves to "From source".
- **UNINSTALL.md:** a section for the `.deb` listing what it installs, and that recents and
  config stay in the home folder with the commands to delete them.
- **CLAUDE.md:** the release steps, and the rule that anything installed outside the repo, by
  `install.sh` or by the package, updates UNINSTALL.md in the same commit.

## Out of scope

- Other distros, signing, an apt repository, automatic updates.
- Changes to the picker itself.
