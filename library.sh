# Copyright 2017 Codethink Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Library of helper functions to be used when writing automation tasks.
# Part of the Night Bus automation tool.


# We use `(cd $checkoutdir; git COMMAND)` rather than `git -C $checkoutdir
# COMMAND` because the -C option isn't present in old versions of Git. For
# example CentOS 7 has Git 1.8 and that lacks the -C option.

git_ensure_credentials() {
    checkoutdir="$1"
    if ! (cd "$checkoutdir"; git config --get user.name); then
        (cd "$checkoutdir"; git config --local user.name "Night Bus automation script")
    fi
    if ! (cd "$checkoutdir"; git config --get user.email); then
        (cd "$checkoutdir"; git config --local user.email "nightbus@localhost")
    fi
}

git_ensure_remote() {
    checkoutdir="$1"
    name="$2"
    url="$3"

    if (cd "$checkoutdir"; git remote get-url "$name"); then
        (cd "$checkoutdir"; git remote set-url "$name" "$url")
    else
        (cd "$checkoutdir"; git remote add "$name" "$url")
    fi
}

# git_ensure_tag_checkout():
#
#   Ensures that:
#
#    * the checkout directory exists and is a Git repo
#    * an up-to-date remote with the given name and URL exists in the repo
#    * the working tree contains the contents of the given ref
#
#   Remote tags shouldn't change, but this function will always update the
#   remote just in case they do.
#
#   Aborts the program if an unexpected program occurs.
git_ensure_tag_checkout() {
    checkoutdir="$1"
    remote_name="$2"
    remote_url="$3"
    remote_ref="$4"

    mkdir -p "$checkoutdir"
    if [ -e "$checkoutdir/.git" ]; then
        git_ensure_remote "$checkoutdir" "$remote_name" "$remote_url"
        (cd "$checkoutdir"; git remote update "$remote_name")
        (cd "$checkoutdir"; git checkout "$remote_ref")
    else
        git clone "$remote_url" --branch="$remote_ref" --origin "$remote_name" "$checkoutdir"
    fi
    return 0
}


# ensure_uptodate_git_branch_checkout():
#
#   Ensures that:
#
#    * the checkout directory exists and is a Git repo
#    * a remote with the given name and URL exists in the repo
#    * the repo's local copy of the remote repo is up to date
#    * the working tree is the contents of the latest commit on the given
#      remote branch.
#
#   Returns 0 if changes were pulled from the remote, 1 if the local copy
#   was already up to date.
#
#   Aborts the program if an unexpected error occurs.
git_ensure_uptodate_branch_checkout() {
    checkoutdir="$1"
    remote_name="$2"
    remote_url="$3"
    track="$4"

    mkdir -p "$checkoutdir"
    if [ -e "$checkoutdir/.git" ]; then
        git_ensure_remote "$checkoutdir" "$remote_name" "$remote_url"

        remote_ref="$remote_name/$track"
        (cd "$checkoutdir"; git checkout "$remote_ref")

        output=$(cd "$checkoutdir"; git pull "$remote_name" "$track")
        if echo "$output" | grep -q 'Already up-to-date'; then
            return 1   # No changes
        else
            return 0
        fi
    else
        git clone "$remote_url" --branch="$track" --origin "$remote_name" "$checkoutdir"
        return 0
    fi
}

# git_merge_remote_ref()
#
#   Attempts to merge commits from a remote repo into the current working tree.
#
#   Returns 0. Aborts the program if an unexpected error occurs.
git_merge_remote_ref() {
    checkoutdir="$1"
    remote_name="$2"
    remote_url="$3"
    ref="$4"

    # If Git needs to create a merge commit, it will require that we have a
    # configured user name and email address.
    git_ensure_credentials "$checkoutdir"
    git_ensure_remote "$checkoutdir" "$remote_name" "$remote_url"
    (cd "$checkoutdir"; git pull --no-edit $remote_name $ref)
}
