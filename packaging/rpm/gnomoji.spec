# Packages the tree packaging/build.sh has already laid out (passed in as the stage macro);
# build.sh calls rpmbuild with --define "stage ..." --define "pkgversion ...".
Name:           gnomoji
Version:        %{pkgversion}
Release:        1
Summary:        Gnomoji: double-tap right Shift to pick an emoji, for GNOME
License:        MIT
URL:            https://github.com/mathewdbutton/Gnomoji
BuildArch:      noarch
AutoReqProv:    no
Requires:       python3 >= 3.11, python3-gobject, gtk4, libadwaita, google-noto-color-emoji-fonts, gnome-shell >= 46

%global debug_package %{nil}
%global __os_install_post %{nil}
%define _build_id_links none

%description
Double-tap right Shift in a text field to open Gnomoji. Search or browse,
press Enter, and the emoji is typed in. A small GNOME Shell extension does the
typing, so it never touches the clipboard.

%install
cp -a %{stage}/. %{buildroot}/

%post
python3 -m compileall -q /usr/lib/gnomoji >/dev/null 2>&1 || :
sh /usr/lib/gnomoji/enable-for-everyone || :

%preun
if [ "$1" -eq 0 ]; then
    sh /usr/lib/gnomoji/disable-for-everyone || :
    find /usr/lib/gnomoji -name __pycache__ -type d -prune -exec rm -rf {} + || :
fi

%files
/usr/lib/gnomoji
/usr/bin/gnomoji
/usr/lib/systemd/user/gnomoji.service
/usr/share/gnome-shell/extensions/emoji-picker@mathewdbutton.github.io
/usr/share/applications/local.emojipicker.EmojiPicker.desktop
/usr/share/icons/hicolor/scalable/apps/local.emojipicker.EmojiPicker.svg
/usr/share/doc/gnomoji
