#!/usr/bin/env bash
# Copyright (c) Ansible Project
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

pushd "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
trap "{ popd; }" EXIT

# Create collection documentation into temporary directory
rm -rf rst
mkdir -p rst
chmod og-w rst  # antsibull-docs wants that directory only readable by itself
antsibull-docs \
    --config-file antsibull-docs.cfg \
    collection \
    --use-current \
    --dest-dir rst \
    cdillc.splunk

# Copy collection documentation into source directory
rsync -cprv --delete-after rst/collections/ rst/collections/

# Build Sphinx site
cp -a index.rst rst/index.rst
sphinx-build -M html rst build -c . -W --keep-going

echo Exit code: $?

echo "View docs at:  file://$PWD/build/html/index.html"
